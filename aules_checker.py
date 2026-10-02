import ctypes
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import uuid
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time as hora_del_dia, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import ia
from interfaz import asignatura_a_curso, build_report, format_due

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BASE_URL = "https://aules.edu.gva.es/fp"
SESSION_PATH = os.path.join(BASE_DIR, "session.json")
ACCOUNTS_DIR = os.path.join(BASE_DIR, "cuentas")
LOG_PATH = os.path.join(BASE_DIR, "run.log")
LOG_MAX_BYTES = 200_000

EXAM_REMINDER_HOURS = (48, 24, 3)
TASK_REMINDER_HOURS = (24, 3)
NEW_BADGE_SECONDS = 24 * 3600
FORUM_MAX_AGE_SECONDS = 30 * 86400
MESSAGE_MAX_AGE_SECONDS = 60 * 86400
# El material cambia poco y es lo que más consultas cuesta: se revisa cada 10 min, no en cada vuelta.
MATERIALS_EVERY_SECONDS = 10 * 60
# Hora a partir de la cual se avisa de lo que vence al día siguiente.
DAILY_SUMMARY_HOUR = 18
# Desde esta hora, la primera comprobación del día avisa de lo que vence hoy y mañana. Hace falta porque
# muchos solo tienen la app abierta en clase, por la mañana, y el resumen de la tarde no les llegaría nunca.
MORNING_SUMMARY_HOUR = 7
SERVER_HEALTH_URL = "http://127.0.0.1:8765/health"

http = requests.Session()
# Reintenta cortes de red y errores 502/503/504 puntuales de Aules (solo son consultas).
http.mount(
    "https://",
    HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=(502, 503, 504), allowed_methods=None)),
)


class LoginError(Exception):
    pass


class SessionExpired(Exception):
    pass


def write_atomic(path, content):
    tmp = f"{path}.{os.getpid()}.tmp"
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(tmp, mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as f:
        f.write(content)
    os.replace(tmp, path)


def log(message):
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        if os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
            with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-1000:]
            write_atomic(LOG_PATH, "".join(lines))
    except OSError:
        pass


def sanitize(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip().rstrip(".") or "sin_nombre"


def account_dir(username):
    return os.path.join(ACCOUNTS_DIR, sanitize(username.lower()))


def report_path(session):
    return os.path.join(account_dir(session["username"]), "informe.html")


def load_session():
    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_session(session):
    write_atomic(SESSION_PATH, json.dumps(session, ensure_ascii=False, indent=2))


def clear_session():
    if os.path.exists(SESSION_PATH):
        os.remove(SESSION_PATH)


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


_ENTROPIA = b"AulesChecker"


def _dpapi(datos, cifrar):
    """Cifra con DPAPI de Windows: solo tu usuario de Windows en este equipo puede descifrarlo."""
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buf = ctypes.create_string_buffer(datos, len(datos))
    ent = ctypes.create_string_buffer(_ENTROPIA, len(_ENTROPIA))
    entrada = _Blob(len(datos), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    entropia = _Blob(len(_ENTROPIA), ctypes.cast(ent, ctypes.POINTER(ctypes.c_char)))
    salida = _Blob()
    funcion = crypt32.CryptProtectData if cifrar else crypt32.CryptUnprotectData
    # 0x1 = CRYPTPROTECT_UI_FORBIDDEN: nunca muestra ventanas.
    if not funcion(ctypes.byref(entrada), None, ctypes.byref(entropia), None, None, 0x1, ctypes.byref(salida)):
        raise OSError("DPAPI no pudo procesar la contraseña guardada")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(salida.pbData, ctypes.c_void_p))


def _ruta_credencial(username):
    return os.path.join(account_dir(username), "credencial.bin")


def guardar_contrasena(username, password):
    os.makedirs(account_dir(username), exist_ok=True)
    write_atomic(_ruta_credencial(username), _dpapi(password.encode("utf-8"), cifrar=True))


def leer_contrasena(username):
    try:
        with open(_ruta_credencial(username), "rb") as f:
            return _dpapi(f.read(), cifrar=False).decode("utf-8")
    except (OSError, ValueError):
        return None


def borrar_contrasena(username):
    try:
        os.remove(_ruta_credencial(username))
    except OSError:
        pass


def sesion_caducada(session):
    """Aules invalidó el token: vuelve a entrar con la contraseña guardada o, si no hay, cierra la sesión."""
    password = leer_contrasena(session["username"])
    if password:
        try:
            nueva = login(session["username"], password, session.get("base_url") or DEFAULT_BASE_URL)
            log("Sesión de Aules renovada automáticamente")
            return nueva
        except LoginError:
            # La contraseña cambió en Aules: la guardada ya no sirve.
            borrar_contrasena(session["username"])
    log("La sesión de Aules ha caducado")
    clear_session()
    toast("Sesión de Aules caducada", "Abre Aules e inicia sesión de nuevo")
    return None


def comprobar(session):
    """run_check con reconexión automática. Devuelve la sesión vigente."""
    try:
        run_check(session)
        return session
    except SessionExpired:
        nueva = sesion_caducada(session)
        if not nueva:
            raise
        run_check(nueva)
        return nueva


def get_token(base_url, username, password):
    r = http.post(
        f"{base_url}/login/token.php",
        data={"username": username, "password": password, "service": "moodle_mobile_app"},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if "token" not in data:
        if data.get("errorcode") == "invalidlogin":
            raise LoginError("Usuario o contraseña incorrectos.")
        raise LoginError(data.get("error") or "No se pudo iniciar sesión en Aules.")
    return data["token"]


def call_ws(base_url, token, wsfunction, params=None):
    payload = {"wstoken": token, "wsfunction": wsfunction, "moodlewsrestformat": "json"}
    if params:
        payload.update(params)
    r = http.post(f"{base_url}/webservice/rest/server.php", data=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("exception"):
        if data.get("errorcode") == "invalidtoken":
            raise SessionExpired(data.get("message"))
        raise RuntimeError(f"{wsfunction}: {data.get('message')}")
    return data


def login(username, password, base_url=DEFAULT_BASE_URL):
    username = username.strip()
    if not username or not password:
        raise LoginError("Introduce tu usuario y contraseña.")
    token = get_token(base_url, username, password)
    info = call_ws(base_url, token, "core_webservice_get_site_info")
    session = {
        "base_url": base_url,
        "username": username,
        "token": token,
        "fullname": info.get("fullname") or username,
        "firstname": info.get("firstname", ""),
    }
    save_session(session)
    log(f"Sesión iniciada como {username}")
    return session


def _rutas_foto(session):
    acc_dir = account_dir(session["username"])
    return os.path.join(acc_dir, "foto"), os.path.join(acc_dir, "foto.json")


def actualizar_foto(session, site_info):
    """Descarga la foto de perfil de Aules cuando cambia. Sin foto propia se borra y la app usa las iniciales."""
    ruta, ruta_datos = _rutas_foto(session)
    url = site_info.get("userpictureurl") or ""
    # Quien no ha subido foto recibe la imagen genérica del tema (theme/image.php/.../u/f1), no un archivo suyo.
    if "/pluginfile.php/" not in url or "/user/icon/" not in url:
        for f in (ruta, ruta_datos):
            if os.path.exists(f):
                os.remove(f)
        return
    try:
        with open(ruta_datos, "r", encoding="utf-8") as f:
            previo = json.load(f)
    except (OSError, ValueError):
        previo = {}
    # La URL lleva "rev=": cambia cuando cambias la foto en Aules, así que solo se descarga entonces.
    if previo.get("url") == url and os.path.exists(ruta):
        return
    # La dirección normal pide la sesión web de Aules; la del servicio web acepta el token de la app.
    descarga = url.replace("/pluginfile.php/", "/webservice/pluginfile.php/", 1)
    r = http.get(f"{descarga}{'&' if '?' in descarga else '?'}token={session['token']}", timeout=20)
    r.raise_for_status()
    tipo = r.headers.get("Content-Type", "").split(";")[0].strip()
    if not tipo.startswith("image/") or tipo == "image/svg+xml":
        return
    write_atomic(ruta, r.content)
    write_atomic(ruta_datos, json.dumps({"url": url, "tipo": tipo}))


def cargar_foto(session):
    """(bytes, tipo) de la foto de perfil guardada, o None si no hay."""
    ruta, ruta_datos = _rutas_foto(session)
    try:
        with open(ruta_datos, "r", encoding="utf-8") as f:
            tipo = json.load(f)["tipo"]
        with open(ruta, "rb") as f:
            return f.read(), tipo
    except (OSError, ValueError, KeyError):
        return None


def version_foto(session):
    """Cambia cuando cambia la foto, para que el navegador no muestre la anterior. Vacío si no hay foto."""
    ruta, ruta_datos = _rutas_foto(session)
    try:
        with open(ruta_datos, "r", encoding="utf-8") as f:
            url = json.load(f)["url"]
    except (OSError, ValueError, KeyError):
        return ""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10] if os.path.exists(ruta) else ""


def _link_text(match):
    href = html.unescape(match.group(1)).strip()
    label = html.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
    # Los enlaces a pluginfile.php necesitan sesión web de Aules: solo se conserva el texto.
    if "pluginfile.php" in href or not href.startswith(("http://", "https://")):
        return label
    return href if not label or label == href else f"{label} ({href})"


def html_to_text(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", raw_html, flags=re.I | re.S)
    text = re.sub(r"<a\s[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", _link_text, text, flags=re.I | re.S)
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.I)
    text = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


@dataclass
class Ctx:
    base_url: str
    token: str
    userid: int
    acc_dir: str
    course_names: dict
    course_params: dict
    warnings: list = field(default_factory=list)

    def ws(self, wsfunction, params=None):
        return call_ws(self.base_url, self.token, wsfunction, params)

    def optional(self, label, fn):
        try:
            return fn()
        except SessionExpired:
            raise
        except Exception as e:
            log(f"No se pudo obtener {label}: {e}")
            self.warnings.append(label)
            return None


def download_attachments(ctx, course_name, item_name, attachments, raiz="adjuntos"):
    if not attachments:
        return []
    folder = os.path.join(ctx.acc_dir, raiz, sanitize(course_name), sanitize(item_name))
    os.makedirs(folder, exist_ok=True)
    saved = []
    for att in attachments:
        filename = sanitize(att["filename"])
        dest = os.path.join(folder, filename)
        remote_mtime = att.get("timemodified") or 0
        if not os.path.exists(dest) or os.path.getmtime(dest) < remote_mtime:
            url = att["fileurl"]
            sep = "&" if "?" in url else "?"
            try:
                r = http.get(f"{url}{sep}token={ctx.token}", timeout=60)
                r.raise_for_status()
                write_atomic(dest, r.content)
                if remote_mtime:
                    os.utime(dest, (remote_mtime, remote_mtime))
            except Exception as e:
                log(f"No se pudo descargar {filename}: {e}")
                if not os.path.exists(dest):
                    continue
        saved.append({"filename": att["filename"], "path": os.path.relpath(dest, ctx.acc_dir).replace(os.sep, "/"),
                      "timemodified": remote_mtime})
    return saved


def config_entrega(a):
    """Qué admite la entrega de una tarea de Aules: archivos (cuántos, tamaño, tipos), texto, declaración..."""
    conf = {(c.get("plugin"), c.get("name")): str(c.get("value") or "") for c in a.get("configs") or []
            if c.get("subtype") == "assignsubmission"}
    archivos, texto = conf.get(("file", "enabled")) == "1", conf.get(("onlinetext", "enabled")) == "1"
    if not (archivos or texto):
        return None
    return {
        "archivos": archivos,
        "max_archivos": int(conf.get(("file", "maxfilesubmissions")) or 1) if archivos else 0,
        "max_bytes": int(conf.get(("file", "maxsubmissionsizebytes")) or 0),
        "tipos": conf.get(("file", "filetypeslist"), ""),
        "texto": texto,
        "borradores": bool(a.get("submissiondrafts")),
        "declaracion": html_to_text(a.get("submissionstatement") or "") if a.get("requiresubmissionstatement") else "",
        # Desde cuándo se puede entregar y la fecha de corte (después ya no se admite nada, salvo prórroga).
        "desde": int(a.get("allowsubmissionsfromdate") or 0),
        "corte": int(a.get("cutoffdate") or 0),
    }


def apply_submission_status(ctx, module, assignid, item):
    """Rellena el estado de entrega y devuelve si la actividad admite entregas."""
    try:
        st = ctx.ws(f"mod_{module}_get_submission_status", {"assignid": assignid})
    except SessionExpired:
        raise
    except Exception as e:
        log(f"No se pudo leer el estado de entrega de «{item['name']}»: {e}")
        return None
    last = st.get("lastattempt") or {}
    submission = last.get("submission") or last.get("teamsubmission") or {}
    if last.get("extensionduedate"):
        item["duedate"], item["due_label"] = last["extensionduedate"], "Prórroga"
    grade = re.sub(r"\s+", " ", html_to_text((st.get("feedback") or {}).get("gradefordisplay") or ""))
    if last.get("gradingstatus") == "graded" and grade:
        item["done"], item["status"] = True, f"Calificada · {grade}"
    elif submission.get("status") == "submitted":
        item["done"], item["status"] = True, "Entregada"
    elif submission.get("status") == "draft":
        item["status"] = "Borrador"
    # Moodle crea un registro con estado "new" aunque la actividad no admita entregas,
    # así que solo cuenta como prueba una entrega empezada de verdad.
    entregado = submission.get("status") in ("submitted", "draft", "reopened")
    return bool(last.get("submissionsenabled") or last.get("cansubmit") or entregado)


ENUNCIADO_MAX_CHARS = 20_000


def leer_enunciado_de_archivos(ctx, item):
    """Muchos profes dejan el enunciado dentro del PDF o Word adjunto, no en la descripción."""
    if item["summary"] or not item["attachments"]:
        return
    for adjunto in item["attachments"][:2]:
        ruta = os.path.join(ctx.acc_dir, adjunto["path"])
        texto = ia.extraer_texto(ruta, ENUNCIADO_MAX_CHARS + 1)
        if len(texto) > ENUNCIADO_MAX_CHARS:
            # Se corta al final de un párrafo, no a mitad de palabra.
            corte = texto.rfind("\n\n", 0, ENUNCIADO_MAX_CHARS)
            texto = texto[:corte if corte > 0 else ENUNCIADO_MAX_CHARS].rstrip() + "\n\n[…] El enunciado sigue en el archivo."
        if texto and len(texto) > 40:
            item["summary_file"] = texto
            item["summary_file_name"] = adjunto["filename"]
            return


def fetch_assignments(ctx, module):
    data = ctx.ws(f"mod_{module}_get_assignments", ctx.course_params)
    result = []
    for course in data.get("courses", []):
        course_name = ctx.course_names.get(course["id"], course.get("fullname", "?"))
        for a in course.get("assignments", []):
            item = {
                "id": f"{module}_{a['id']}",
                "name": a["name"],
                "course": course_name,
                "course_id": course["id"],
                "kind": "tarea",
                "duedate": a.get("duedate") or 0,
                "due_label": "Entrega" if a.get("duedate") else "",
                "summary": html_to_text(a.get("intro", "")),
                "attachments": download_attachments(ctx, course_name, a["name"], a.get("introattachments") or []),
                "done": False,
                "status": "",
            }
            config = config_entrega(a)
            if config:
                item["entrega"] = config
            admite_entregas = apply_submission_status(ctx, module, a["id"], item)
            # Lo que de verdad distingue una tarea de un apartado administrativo (p.ej. "Resultados
            # de Aprendizaje") es si admite entregas; la fecha o la nota solo valen como respaldo.
            if admite_entregas is None:
                admite_entregas = bool(a.get("duedate")) or (a.get("grade") or 0) > 0
            if not admite_entregas and not a.get("duedate") and not (a.get("grade") or 0) > 0:
                item["kind"] = "aviso"
            leer_enunciado_de_archivos(ctx, item)
            result.append(item)
    return result


def fetch_quizzes(ctx):
    data = ctx.ws("mod_quiz_get_quizzes_by_courses", ctx.course_params)
    now_ts = datetime.now().timestamp()
    result = []
    for q in data.get("quizzes", []):
        course_name = ctx.course_names.get(q["course"], "?")
        opens, closes = q.get("timeopen") or 0, q.get("timeclose") or 0
        if opens > now_ts:
            due, label = opens, "Abre"
        elif closes:
            due, label = closes, "Cierra"
        else:
            due, label = 0, ""
        item = {
            "id": f"quiz_{q['id']}",
            "name": q["name"],
            "course": course_name,
            "course_id": q["course"],
            "kind": "examen",
            "duedate": due,
            "due_label": label,
            "summary": html_to_text(q.get("intro", "")),
            "attachments": download_attachments(ctx, course_name, q["name"], q.get("introfiles") or []),
            "done": False,
            "status": "",
        }
        try:
            attempts = ctx.ws("mod_quiz_get_user_attempts", {"quizid": q["id"], "status": "finished"}).get("attempts", [])
            if attempts:
                item["done"], item["status"] = True, "Hecho"
        except SessionExpired:
            raise
        except Exception as e:
            log(f"No se pudieron leer los intentos de «{q['name']}»: {e}")
        result.append(item)
    return result


def fetch_forum_posts(ctx):
    forums = ctx.ws("mod_forum_get_forums_by_courses", ctx.course_params)
    cutoff = datetime.now().timestamp() - FORUM_MAX_AGE_SECONDS
    posts = []
    for f in forums:
        if f.get("numdiscussions") == 0:
            continue
        course_name = ctx.course_names.get(f["course"], "?")
        data = ctx.ws("mod_forum_get_forum_discussions", {"forumid": f["id"], "page": 0, "perpage": 10})
        for d in data.get("discussions", []):
            modified = d.get("timemodified") or d.get("modified") or d.get("created") or 0
            if modified < cutoff:
                continue
            discussion = d.get("discussion") or d["id"]
            subject = d.get("subject") or d.get("name") or "(sin asunto)"
            posts.append(
                {
                    "id": f"forum_{discussion}",
                    "discussion": discussion,
                    "name": subject,
                    "forum": f.get("name", ""),
                    "forum_type": f.get("type", ""),
                    "course": course_name,
                    "author": d.get("usermodifiedfullname") or d.get("userfullname") or "",
                    "author_id": d.get("usermodified") or d.get("userid"),
                    "timemodified": modified,
                    "numreplies": d.get("numreplies") or 0,
                    "summary": html_to_text(d.get("message", "")),
                    "attachments": download_attachments(ctx, course_name, f"Foro - {subject}", d.get("attachments") or []),
                    "url": f"{ctx.base_url}/mod/forum/discuss.php?d={discussion}",
                }
            )
    return posts


def _numero(valor):
    if valor is None:
        return ""
    return str(int(valor)) if float(valor).is_integer() else f"{valor:.2f}".replace(".", ",")


RE_ETIQUETA = re.compile(r"<[^>]*>")
RE_ESTADO_NOTA = re.compile(r'<i\b[^>]*\b(?:title|aria-label)="([^"]+)"', re.I)


def separar_nota(valor):
    """Aules pone un icono HTML de aprobado/suspendido delante del número: se separan las dos cosas."""
    valor = valor or ""
    estado = RE_ESTADO_NOTA.search(valor)
    return html.unescape(RE_ETIQUETA.sub("", valor)).strip(), html.unescape(estado.group(1)).strip() if estado else ""


RE_PORCENTAJE = re.compile(r"\((\d{1,3}(?:[.,]\d+)?)\s*%\)")


def progreso_asignatura(elementos):
    """Cuánto llevas en una asignatura según los pesos de sus notas. None si los pesos no son fiables.

    Los pesos salen de Aules cuando el profe los deja ver y todas las notas cuelgan de la asignatura (sin
    subcategorías, cuyos pesos suelen estar ocultos). Si no, de porcentajes en el nombre, como «RA 1 (30%)»,
    pero solo si suman 100 %. Con cualquier otra cosa el cálculo sería inventado, así que no se muestra.
    """
    hojas = [g for g in elementos if g.get("itemtype") in ("mod", "manual")]
    if not hojas:
        return None
    if not any(g.get("itemtype") == "category" for g in elementos) and all(g.get("weightraw") is not None for g in hojas):
        pesos, fuente = {g["id"]: float(g["weightraw"]) for g in hojas}, "aules"
    else:
        pesos = {}
        for g in hojas:
            m = RE_PORCENTAJE.search(g.get("itemname") or "")
            if m:
                pesos[g["id"]] = float(m.group(1).replace(",", ".")) / 100
        fuente = "nombres"
        if not 0.98 <= sum(pesos.values()) <= 1.02:
            return None
    total = sum(pesos.values())
    if total <= 0:
        return None
    corregido = conseguido = 0.0
    for g in hojas:
        peso = pesos.get(g["id"], 0) / total
        if peso and g.get("graderaw") is not None and g.get("grademax"):
            corregido += peso
            conseguido += peso * float(g["graderaw"]) / float(g["grademax"])
    if corregido < 0.001:
        return None
    queda = 1 - corregido
    return {
        "fuente": fuente,
        "media": round(conseguido / corregido * 10, 2),
        "corregido": round(corregido * 100),
        # Media que te hace falta en lo que queda para llegar al 5 (puede salir por debajo de 0 o por encima de 10).
        "necesaria": round((0.5 - conseguido) / queda * 10, 2) if queda > 0.005 else None,
    }


def fetch_grades(ctx, courses, progreso=None):
    """Notas ya puestas (con el comentario del profe) y la nota total de cada asignatura."""
    notas = []
    for c in courses:
        course_name = ctx.course_names.get(c["id"], c.get("fullname", "?"))
        data = ctx.ws("gradereport_user_get_grade_items", {"courseid": c["id"], "userid": ctx.userid})
        if progreso is not None and data.get("usergrades"):
            calculo = progreso_asignatura(data["usergrades"][0].get("gradeitems", []))
            if calculo:
                progreso[course_name] = calculo
        for usuario in data.get("usergrades", []):
            for g in usuario.get("gradeitems", []):
                valor, estado = separar_nota(g.get("gradeformatted"))
                tipo = g.get("itemtype")
                # Las categorías son subtotales internos; "-" o vacío es que aún no hay nota.
                if valor in ("", "-") or tipo not in ("mod", "manual", "course") or g.get("gradehiddenbydate"):
                    continue
                total = tipo == "course"
                notas.append(
                    {
                        "id": f"nota_{g['id']}",
                        "course": course_name,
                        "name": "Nota de la asignatura" if total else (g.get("itemname") or "Nota"),
                        "total": total,
                        "grade": valor,
                        "estado": estado,
                        "max": _numero(g.get("grademax")),
                        "percentage": separar_nota(g.get("percentageformatted"))[0].strip(" -"),
                        "feedback": html_to_text(g.get("feedback") or ""),
                        "graded": g.get("gradedategraded") or 0,
                        # Enlaza la nota con su tarea o cuestionario (ids "assign_123", "quiz_45"…).
                        "activity": f"{g['itemmodule']}_{g['iteminstance']}" if g.get("itemmodule") else "",
                        "url": f"{ctx.base_url}/grade/report/user/index.php?id={c['id']}",
                    }
                )
    return notas


def fetch_messages(ctx):
    """Últimos mensajes privados de Aules (profes o compañeros), uno por conversación."""
    data = ctx.ws("core_message_get_conversations", {"userid": ctx.userid, "limitnum": 20})
    cutoff = datetime.now().timestamp() - MESSAGE_MAX_AGE_SECONDS
    mensajes = []
    for conv in data.get("conversations", []):
        ultimos = conv.get("messages") or []
        # Tipo 3 = "notas personales" (conversación contigo mismo).
        if conv.get("type") == 3 or not ultimos:
            continue
        m = max(ultimos, key=lambda x: (x.get("timecreated") or 0, x.get("id") or 0))
        if (m.get("timecreated") or 0) < cutoff:
            continue
        otros = [u for u in conv.get("members") or [] if u.get("id") != ctx.userid]
        quien = conv.get("name") or ", ".join(u.get("fullname", "") for u in otros) or "Conversación"
        autor = next((u.get("fullname", "") for u in conv.get("members") or [] if u.get("id") == m.get("useridfrom")), "")
        mensajes.append(
            {
                "id": f"msg_{conv['id']}",
                "conversation": conv["id"],
                "last_id": m.get("id") or 0,
                "who": quien,
                "author": autor,
                "from_me": m.get("useridfrom") == ctx.userid,
                "text": html_to_text(m.get("text") or ""),
                "time": m.get("timecreated") or 0,
                "unread": not conv.get("isread", True),
                "url": f"{ctx.base_url}/message/index.php?convid={conv['id']}",
            }
        )
    return mensajes


MATERIAL_EXTS =(".pdf", ".pptx", ".ppt", ".docx", ".odp", ".odt", ".txt", ".md")
MATERIAL_MAX_BYTES = 30_000_000


def load_items(session):
    """Tareas y exámenes de Aules más los que has apuntado tú."""
    acc_dir = account_dir(session["username"])
    return _load_aules_items(acc_dir) + items_propios(acc_dir)


def _load_aules_items(acc_dir):
    try:
        with open(os.path.join(acc_dir, "items.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


# ---------- marcas a mano sobre tareas de Aules ----------
# "hecha": la entregaste fuera de Aules (en clase, en papel...). "aviso": el profe puso un aviso como si fuera tarea.
MARCAS = ("hecha", "aviso")


def cargar_marcas(acc_dir):
    try:
        with open(os.path.join(acc_dir, "marcas.json"), "r", encoding="utf-8") as f:
            marcas = json.load(f)
        return {k: v for k, v in marcas.items() if v in MARCAS} if isinstance(marcas, dict) else {}
    except (OSError, ValueError):
        return {}


def aplicar_marcas(acc_dir, items):
    """Devuelve las tareas con tus marcas puestas, sin tocar lo que se guarda de Aules (así se puede deshacer)."""
    marcas = cargar_marcas(acc_dir)
    resultado = []
    for a in items:
        marca = marcas.get(a["id"])
        if marca == "aviso" and a["kind"] != "aviso":
            a = dict(a, kind="aviso", kind_original=a["kind"], marcada="aviso", is_new=False)
        elif marca == "hecha" and not a["done"] and a["kind"] != "aviso":
            a = dict(a, done=True, status="Hecha (marcada por ti)", marcada="hecha", is_new=False)
        resultado.append(a)
    return resultado


def marcar_tarea(session, item_id, marca):
    """Pone o quita (marca vacía) una marca a una tarea de Aules. Lanza ValueError con un mensaje para el usuario."""
    acc_dir = account_dir(session["username"])
    if marca and marca not in MARCAS:
        raise ValueError("Marca desconocida.")
    if not any(a["id"] == item_id for a in _load_aules_items(acc_dir)):
        raise ValueError("Esa tarea ya no está en Aules.")
    marcas = cargar_marcas(acc_dir)
    if marca:
        marcas[item_id] = marca
    else:
        marcas.pop(item_id, None)
    write_atomic(os.path.join(acc_dir, "marcas.json"), json.dumps(marcas, ensure_ascii=False, indent=2))
    return {"ok": True}


# ---------- tareas y exámenes que apuntas tú (los que se dicen en clase y no están en Aules) ----------

def cargar_propias(acc_dir):
    try:
        with open(os.path.join(acc_dir, "propias.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _guardar_propias(acc_dir, propias):
    os.makedirs(acc_dir, exist_ok=True)
    write_atomic(os.path.join(acc_dir, "propias.json"), json.dumps(propias, ensure_ascii=False, indent=2))


def items_propios(acc_dir):
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "course": p["course"],
            "course_id": None,
            "kind": p["kind"],
            "duedate": p["duedate"],
            "due_label": "Examen" if p["kind"] == "examen" else "Entrega",
            "summary": p.get("notes", ""),
            "attachments": [],
            "done": bool(p.get("done")),
            "status": "Hecho" if p.get("done") else "",
            "propia": True,
            "fecha": p["fecha"],
            "hora": p["hora"],
            "hora_auto": bool(p.get("hora_auto")),
        }
        for p in cargar_propias(acc_dir)
    ]


def hora_de_clase(session, curso, dia):
    """Hora a la que empieza esa asignatura ese día según el horario, o None."""
    try:
        activo = horario_para_fecha(horarios_disponibles(session), datetime.combine(dia, hora_del_dia()))
        horario = obtener_horario(session, activo, account_dir(session["username"])) if activo else None
    except Exception:
        return None
    if dia.weekday() >= 5 or not horario:
        return None
    for franja in sorted(horario.get("dias", {}).get(DIAS_SEMANA[dia.weekday()], []), key=lambda f: f.get("inicio", "")):
        if asignatura_a_curso(franja.get("asignatura") or "", [curso]) == curso:
            return franja["inicio"]
    return None


def guardar_propia(session, datos):
    """Crea o edita una tarea/examen apuntado a mano. Lanza ValueError con un mensaje para el usuario."""
    acc_dir = account_dir(session["username"])
    nombre = " ".join(str(datos.get("name") or "").split())[:200]
    curso = " ".join(str(datos.get("course") or "").split())[:200]
    tipo = datos.get("kind")
    notas = str(datos.get("notes") or "").strip()[:4000]
    if not nombre:
        raise ValueError("Escribe qué hay que hacer o de qué es el examen.")
    if not curso:
        raise ValueError("Elige la asignatura.")
    if tipo not in ("tarea", "examen"):
        raise ValueError("Elige si es una tarea o un examen.")
    try:
        dia = date.fromisoformat(str(datos.get("fecha") or ""))
    except ValueError:
        raise ValueError("Pon la fecha.") from None
    hora = str(datos.get("hora") or "").strip()
    hora_auto = False
    if hora:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hora):
            raise ValueError("La hora no es válida.")
    elif tipo == "examen":
        # Sin hora, el examen es a la hora de clase de esa asignatura ese día.
        hora, hora_auto = hora_de_clase(session, curso, dia) or "08:00", True
    else:
        hora = "23:59"
    duedate = datetime.combine(dia, hora_del_dia(int(hora[:2]), int(hora[3:]))).timestamp()

    propias = cargar_propias(acc_dir)
    existente = next((x for x in propias if x["id"] == datos.get("id")), None)
    entrada = existente or {"id": f"propia_{uuid.uuid4().hex[:12]}", "done": False, "created": int(datetime.now().timestamp())}
    entrada.update({"name": nombre, "course": curso, "kind": tipo, "notes": notas, "fecha": dia.isoformat(),
                    "hora": hora, "hora_auto": hora_auto, "duedate": duedate})
    if not existente:
        propias.append(entrada)
    _guardar_propias(acc_dir, propias)
    log(f"{'Editada' if existente else 'Apuntada'} a mano: {tipo} «{nombre}» ({curso}, {dia.isoformat()} {hora})")
    return entrada


def marcar_propia(session, propia_id, hecha):
    acc_dir = account_dir(session["username"])
    propias = cargar_propias(acc_dir)
    for x in propias:
        if x["id"] == propia_id:
            x["done"] = bool(hecha)
            _guardar_propias(acc_dir, propias)
            return x
    raise ValueError("Esa tarea ya no existe.")


def borrar_propia(session, propia_id):
    acc_dir = account_dir(session["username"])
    propias = cargar_propias(acc_dir)
    restantes = [x for x in propias if x["id"] != propia_id]
    if len(restantes) == len(propias):
        raise ValueError("Esa tarea ya no existe.")
    _guardar_propias(acc_dir, restantes)


# ---------- calendario escolar: festivos y vacaciones ----------

VERSION_LECTOR_CALENDARIO = 2
MESES_CALENDARIO = {
    "septiembre": 9, "setembre": 9, "octubre": 10, "noviembre": 11, "novembre": 11, "diciembre": 12, "desembre": 12,
    "enero": 1, "gener": 1, "febrero": 2, "febrer": 2, "marzo": 3, "marc": 3, "abril": 4, "mayo": 5, "maig": 5,
    "junio": 6, "juny": 6, "julio": 7, "juliol": 7, "agosto": 8, "agost": 8,
}
LEYENDA_CALENDARIO = (("festiu", "festivo"), ("festivo", "festivo"), ("vacaciones", "vacaciones"), ("vacances", "vacaciones"),
                      ("consejo", "no lectivo"), ("consell", "no lectivo"), ("no lectivo", "no lectivo"), ("no lectiu", "no lectivo"))


def calendario_desde_pdf(ruta):
    """Lee un calendario escolar en PDF donde los días sin clase van coloreados según una leyenda.

    Devuelve {"2026-10-12": "festivo", ...} solo con días de lunes a viernes."""
    from pypdf import PdfReader
    from pypdf.generic import ContentStream

    lector = PdfReader(ruta)
    textos_pdf = []
    resultado = {}
    for pagina in lector.pages:
        mitad = float(pagina.mediabox.width) / 2
        textos = []

        def visitor(texto, cm, tm, _fd, _fs):
            texto = (texto or "").strip()
            if texto:
                textos.append((texto, tm[4] * cm[0] + tm[5] * cm[2] + cm[4], tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))

        pagina.extract_text(visitor_text=visitor)
        textos_pdf += [t for t, _, _ in textos]

        # Rectángulos rellenos con un color de verdad (no gris/blanco/negro).
        rects, color, pendientes, pila = [], None, [], []
        for operandos, op in ContentStream(pagina.get_contents(), lector).operations:
            # q/Q guardan y restauran el color: sin la pila, el color del texto "tapa" el del recuadro.
            if op == b"q":
                pila.append(color)
            elif op == b"Q":
                color = pila.pop() if pila else None
            elif op == b"rg":
                color = tuple(float(v) for v in operandos)
            elif op == b"g":
                color = (float(operandos[0]),) * 3
            elif op == b"k":
                c, m, y, k = (float(v) for v in operandos)
                color = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
            elif op == b"re":
                x, y, w, h = (float(v) for v in operandos)
                pendientes.append((min(x, x + w), min(y, y + h), max(x, x + w), max(y, y + h)))
            elif op in (b"f", b"f*", b"F", b"B", b"B*", b"b", b"b*"):
                if color and max(color) - min(color) > 0.25:
                    rects += [(color, r) for r in pendientes]
                pendientes = []
            elif op in (b"n", b"S", b"s"):
                pendientes = []

        def color_en(x, y):
            for c, (x0, y0, x1, y1) in reversed(rects):
                if x0 <= x <= x1 and y0 <= y <= y1:
                    return c
            return None

        # Leyenda: el cuadro de color que hay justo a la izquierda de "FESTIVO", "VACACIONES"…
        leyenda = []
        for texto, x, y in textos:
            normal = " ".join(_letras(texto))
            tipo = next((t for clave, t in LEYENDA_CALENDARIO if clave in normal), None)
            if not tipo:
                continue
            cerca = [(x - x1, c) for c, (x0, y0, x1, y1) in rects if x1 <= x + 3 and x - x1 < 40 and y0 - 4 <= y <= y1 + 4]
            if cerca:
                leyenda.append((min(cerca)[1], tipo))
        if not leyenda:
            continue

        titulos = []
        for texto, x, y in textos:
            primera = (_letras(texto) or [""])[0]
            if primera in MESES_CALENDARIO:
                titulos.append((MESES_CALENDARIO[primera], x < mitad, y))

        anyos = re.search(r"(20\d\d)\D{1,5}(20\d\d)", " ".join(t for t, _, _ in textos))
        for texto, x, y in textos:
            if not re.fullmatch(r"\d{1,2}", texto):
                continue
            encima = [(ty - y, mes) for mes, izquierda, ty in titulos if izquierda == (x < mitad) and ty > y]
            color = color_en(x + 1.5, y + 2)
            if not encima or not color:
                continue
            mes = min(encima)[1]
            distancia, tipo = min((sum((a - b) ** 2 for a, b in zip(color, c)) ** 0.5, t) for c, t in leyenda)
            if distancia > 0.35:
                continue
            if anyos:
                anyo = int(anyos.group(1)) if mes >= 8 else int(anyos.group(2))
            else:
                hoy = date.today()
                anyo = hoy.year + (1 if mes < 8 <= hoy.month else 0) - (1 if mes >= 8 > hoy.month else 0)
            try:
                dia = date(anyo, mes, int(texto))
            except ValueError:
                continue
            if dia.weekday() < 5:
                resultado[dia.isoformat()] = tipo
    return dict(sorted(resultado.items()))


def cargar_calendario(acc_dir):
    try:
        with open(os.path.join(acc_dir, "calendario.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def dias_sin_clase(acc_dir):
    return cargar_calendario(acc_dir).get("dias", {})


def actualizar_calendario(session, acc_dir, materiales):
    """Busca el calendario escolar entre el material de los cursos y lo lee si es nuevo o ha cambiado."""
    candidatos = [
        m for m in materiales
        if "calendari" in f"{m['name']} {m['filename']}".lower()
        and (m["filename"].lower().endswith(".pdf") or m["url"].lower().split("?")[0].endswith(".pdf"))
    ]
    if not candidatos:
        return
    m = candidatos[0]
    firma = f"{m['url']}|{m.get('timemodified') or 0}"
    actual = cargar_calendario(acc_dir)
    if actual.get("firma") == firma and actual.get("version") == VERSION_LECTOR_CALENDARIO:
        return
    if m["externo"]:
        # Enlace a la web del instituto: se descarga sin el token de Aules (no debe salir hacia otra web).
        r = http.get(m["url"], timeout=60)
        r.raise_for_status()
        ruta = os.path.join(acc_dir, "material", "calendario_escolar.pdf")
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        write_atomic(ruta, r.content)
    else:
        ruta = descargar_material(session, m)
    dias = calendario_desde_pdf(ruta)
    write_atomic(
        os.path.join(acc_dir, "calendario.json"),
        json.dumps({"firma": firma, "version": VERSION_LECTOR_CALENDARIO, "nombre": m["name"], "curso": m["course"],
                    "url": m["url"], "dias": dias}, ensure_ascii=False, indent=2),
    )
    log(f"Calendario escolar leído ({m['name']}): {len(dias)} días entre semana sin clase")


def siguiente_dia_lectivo(desde, sin_clase):
    dia = desde + timedelta(days=1)
    for _ in range(60):
        if dia.weekday() < 5 and dia.isoformat() not in sin_clase:
            return dia
        dia += timedelta(days=1)
    return dia


RESPUESTA_EXTS = (".pdf", ".docx", ".pptx", ".txt", ".md", ".csv", ".sql", ".py", ".html", ".json", ".java", ".js", ".css",
                  ".xml", ".c", ".cpp", ".sh", ".php")


def respuesta_entregada(session, item):
    """Lo que entregaste en Aules en esa tarea: el texto en línea y los archivos (se descargan). Devuelve (texto, rutas)."""
    modulo, _, assignid = item["id"].partition("_")
    if modulo not in ("assign", "assigngva") or not assignid.isdigit():
        return "", []
    acc_dir = account_dir(session["username"])
    st = call_ws(session["base_url"], session["token"], f"mod_{modulo}_get_submission_status", {"assignid": int(assignid)})
    last = st.get("lastattempt") or {}
    entrega = last.get("submission") or last.get("teamsubmission") or {}
    if entrega.get("status") not in ("submitted", "draft", "reopened"):
        return "", []
    textos, archivos = [], []
    for plugin in entrega.get("plugins") or []:
        for campo in plugin.get("editorfields") or []:
            texto = html_to_text(campo.get("text") or "").strip()
            if texto:
                textos.append(texto)
        for area in plugin.get("fileareas") or []:
            archivos += [f for f in area.get("files") or [] if f.get("filename", "").lower().endswith(RESPUESTA_EXTS)
                         and (f.get("filesize") or 0) <= MATERIAL_MAX_BYTES]
    ctx = Ctx(base_url=session["base_url"], token=session["token"], userid=0, acc_dir=acc_dir, course_names={}, course_params={})
    guardados = download_attachments(ctx, item["course"], item["name"], archivos[:8], raiz="entregas")
    return "\n\n".join(textos), [os.path.join(acc_dir, g["path"]) for g in guardados]


class EntregaError(Exception):
    pass


def _tarea_de_aules(item):
    modulo, _, assignid = item["id"].partition("_")
    if modulo not in ("assign", "assigngva") or not assignid.isdigit():
        raise EntregaError("Solo se pueden entregar desde la app las tareas de Aules.")
    return modulo, int(assignid)


def motivo_sin_entrega(item, now_ts):
    """Por qué no se puede entregar todavía o ya no, según las fechas de la tarea. Vacío si está abierta."""
    config = item.get("entrega") or {}
    if config.get("desde") and now_ts < config["desde"]:
        return f"Se abre el {format_due(config['desde'])}"
    if config.get("corte") and now_ts > config["corte"] and item.get("due_label") != "Prórroga":
        return "Plazo cerrado"
    return ""


def estado_entrega(session, item):
    """Cómo está tu entrega en Aules ahora mismo y si todavía se puede cambiar."""
    modulo, assignid = _tarea_de_aules(item)
    st = call_ws(session["base_url"], session["token"], f"mod_{modulo}_get_submission_status", {"assignid": assignid})
    last = st.get("lastattempt") or {}
    entrega = last.get("submission") or last.get("teamsubmission") or {}
    archivos, con_texto = [], False
    for plugin in entrega.get("plugins") or []:
        con_texto |= any(html_to_text(c.get("text") or "").strip() for c in plugin.get("editorfields") or [])
        for area in plugin.get("fileareas") or []:
            archivos += [f["filename"] for f in area.get("files") or [] if f.get("filename") and f["filename"] != "."]
    por_fecha = motivo_sin_entrega(item, datetime.now().timestamp())
    if last.get("locked"):
        motivo = "El profe ha bloqueado las entregas de esta tarea."
    elif not last.get("canedit") and por_fecha.startswith("Se abre"):
        motivo = f"Todavía no se puede entregar: {por_fecha[0].lower()}{por_fecha[1:]}."
    elif not last.get("canedit") and por_fecha:
        motivo = "El plazo de entrega ha terminado: Aules ya no admite entregas en esta tarea."
    elif not last.get("canedit"):
        motivo = "Aules no admite cambios en esta entrega: puede que esté cerrada o ya corregida."
    else:
        motivo = ""
    return {"puede": not motivo, "motivo": motivo, "estado": entrega.get("status") or "", "archivos": archivos,
            "texto": con_texto}


def _tipo_permitido(nombre, tipos):
    """Moodle guarda los tipos como ".pdf, .docx" o como grupos ("document"); los grupos se dejan a Aules."""
    extensiones = [t.strip().lower() for t in re.split(r"[,;\s]+", tipos or "") if t.strip().startswith(".")]
    return not extensiones or os.path.splitext(nombre.lower())[1] in extensiones


def _subir_al_borrador(session, archivos):
    """Sube los archivos a una zona temporal de tu usuario en Aules y devuelve su número (itemid)."""
    r = http.post(f"{session['base_url']}/webservice/upload.php",
                  data={"token": session["token"], "filearea": "draft", "itemid": 0},
                  files={f"file_{i}": (nombre, datos) for i, (nombre, datos) in enumerate(archivos, 1)}, timeout=300)
    r.raise_for_status()
    datos = r.json()
    if isinstance(datos, dict):
        raise EntregaError(f"Aules no aceptó los archivos: {datos.get('error') or datos.get('message') or datos}")
    return int(datos[0]["itemid"])


def _zona_vacia(session):
    return int(call_ws(session["base_url"], session["token"], "core_files_get_unused_draft_itemid")["itemid"])


def entregar(session, item, archivos, texto="", acepta_declaracion=False):
    """Entrega la tarea en Aules con esos archivos [(nombre, bytes)] y/o texto. Sustituye lo entregado antes."""
    config = item.get("entrega")
    if not config:
        raise EntregaError("Esta tarea no admite entregas desde la app. Ábrela en Aules.")
    modulo, assignid = _tarea_de_aules(item)
    texto = (texto or "").strip()
    if not archivos and not texto:
        raise EntregaError("Elige al menos un archivo" + (" o escribe el texto." if config["texto"] else "."))
    if archivos and not config["archivos"]:
        raise EntregaError("Esta tarea no admite archivos, solo texto.")
    if texto and not config["texto"]:
        raise EntregaError("Esta tarea no admite texto, solo archivos.")
    nombres = [nombre.lower() for nombre, _ in archivos]
    repetido = next((n for n in nombres if nombres.count(n) > 1), None)
    if repetido:
        raise EntregaError(f"Hay dos archivos que se llaman «{repetido}». Quita uno o cámbiale el nombre.")
    if len(archivos) > config["max_archivos"]:
        raise EntregaError(f"Esta tarea admite como mucho {config['max_archivos']} archivo(s).")
    for nombre, datos in archivos:
        if config["max_bytes"] and len(datos) > config["max_bytes"]:
            raise EntregaError(f"«{nombre}» pasa del máximo de {config['max_bytes'] // (1024 * 1024)} MB por archivo.")
        if not _tipo_permitido(nombre, config["tipos"]):
            raise EntregaError(f"«{nombre}» no es de un tipo permitido ({config['tipos']}).")
    if config["declaracion"] and not acepta_declaracion:
        raise EntregaError("Tienes que aceptar la declaración de autoría de la entrega.")
    # Justo antes de entregar se vuelve a mirar en Aules: la tarea pudo cerrarse desde que abriste el diálogo.
    estado = estado_entrega(session, item)
    if not estado["puede"]:
        raise EntregaError(estado["motivo"])

    datos_entrega = {"assignmentid": assignid}
    if config["archivos"]:
        # La zona de archivos se sustituye entera: sin archivos nuevos, se manda vacía.
        datos_entrega["plugindata[files_filemanager]"] = _subir_al_borrador(session, archivos) if archivos else _zona_vacia(session)
    if config["texto"]:
        datos_entrega["plugindata[onlinetext_editor][text]"] = html.escape(texto).replace("\n", "<br>")
        datos_entrega["plugindata[onlinetext_editor][format]"] = 1
        datos_entrega["plugindata[onlinetext_editor][itemid]"] = _zona_vacia(session)
    avisos = call_ws(session["base_url"], session["token"], f"mod_{modulo}_save_submission", datos_entrega)
    if avisos:
        raise EntregaError("Aules no aceptó la entrega: " + "; ".join(a.get("item") or a.get("message") or str(a) for a in avisos))
    if config["borradores"]:
        avisos = call_ws(session["base_url"], session["token"], f"mod_{modulo}_submit_for_grading",
                         {"assignmentid": assignid, "acceptsubmissionstatement": int(bool(acepta_declaracion))})
        if avisos:
            raise EntregaError("Se guardó como borrador, pero Aules no la envió para calificar: "
                               + "; ".join(a.get("item") or a.get("message") or str(a) for a in avisos))

    final = estado_entrega(session, item)
    if final["estado"] != "submitted":
        raise EntregaError("Aules no confirma la entrega. Ábrela en Aules para comprobarlo.")
    log(f"Entregada desde la app: {item['name']} ({len(archivos)} archivo(s){', con texto' if texto else ''})")
    _marcar_entregada(session, item["id"])
    return final


def _marcar_entregada(session, item_id):
    """Pone la tarea como entregada al momento, sin esperar a la siguiente comprobación."""
    acc_dir = account_dir(session["username"])
    items = _load_aules_items(acc_dir)
    for a in items:
        if a["id"] == item_id:
            a.update(done=True, status="Entregada", is_new=False, cambios=[])
    write_atomic(os.path.join(acc_dir, "items.json"), json.dumps(items, ensure_ascii=False, indent=2))
    escribir_informe(session)


def archivos_del_borrador(cache_ia, item):
    """Los archivos que te escribió la IA para esa tarea, tal como están ahora en su carpeta (con tus cambios)."""
    borrador = (cache_ia.get(item["id"]) or {}).get("borrador") or {}
    carpeta = borrador.get("carpeta") or ""
    rutas = []
    for nombre in borrador.get("archivos") or []:
        ruta = os.path.join(carpeta, os.path.basename(nombre))
        if carpeta and os.path.isfile(ruta):
            rutas.append(ruta)
    return rutas


def respuesta_previa(session, previa, cache_ia):
    """Tu respuesta a una tarea anterior: primero lo que entregaste en Aules; si no, el borrador que te hizo la IA
    (leído tal como esté ahora, con lo que hayas corregido)."""
    texto, rutas, origen = "", [], ""
    try:
        texto, rutas = respuesta_entregada(session, previa)
        origen = "lo que entregaste en Aules" if (texto or rutas) else ""
    except SessionExpired:
        raise
    except Exception as e:
        log(f"No se pudo leer tu entrega de «{previa['name']}»: {e}")
    if not origen:
        borrador = (cache_ia.get(previa["id"]) or {}).get("borrador") or {}
        carpeta = borrador.get("carpeta") or ""
        rutas = [os.path.join(carpeta, n) for n in borrador.get("archivos") or [] if os.path.isfile(os.path.join(carpeta, n))]
        origen = "tu borrador de esa tarea (tal como está ahora en tu carpeta)" if rutas else ""
    return {"item": previa, "texto": texto, "rutas": rutas, "origen": origen}


def fetch_course_material(session, course_id, course_name, limit=12):
    acc_dir = account_dir(session["username"])
    ctx = Ctx(
        base_url=session["base_url"],
        token=session["token"],
        userid=0,
        acc_dir=acc_dir,
        course_names={},
        course_params={},
    )
    files = []
    for section in ctx.ws("core_course_get_contents", {"courseid": course_id}):
        for module in section.get("modules", []):
            if module.get("modname") not in ("resource", "folder"):
                continue
            for f in module.get("contents", []):
                if f.get("type") != "file" or not f.get("filename", "").lower().endswith(MATERIAL_EXTS):
                    continue
                if (f.get("filesize") or 0) > MATERIAL_MAX_BYTES:
                    continue
                files.append(f)
    saved = download_attachments(ctx, course_name, "Temario", files[:limit])
    return [os.path.join(acc_dir, s["path"]) for s in saved]


RE_CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
CORREO_EXTS = (".pdf", ".docx", ".pptx", ".txt", ".md")


def _letras(texto):
    texto = "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower()) if not unicodedata.combining(c))
    return re.findall(r"[a-z]+", texto)


def buscar_correos(texto, origen, correos):
    for correo in RE_CORREO.findall(html.unescape(texto or "")):
        correos.setdefault(correo.lower(), set()).add(origen)


def correo_deducido(firstname, lastname):
    """Formato de la GVA: iniciales del nombre, punto y apellidos juntos (Ryan Adam Davis Tunmore → ra.davistunmore)."""
    iniciales = "".join(p[0] for p in _letras(firstname))
    apellidos = "".join(_letras(lastname))
    return f"{iniciales}.{apellidos}@edu.gva.es" if iniciales and apellidos else ""


def correos_en_archivos(acc_dir, cache, correos):
    """Correos escritos dentro de los PDF y documentos ya descargados. Solo relee los que han cambiado."""
    vigentes = {}
    for carpeta in ("material", "adjuntos"):
        for raiz, _, archivos in os.walk(os.path.join(acc_dir, carpeta)):
            for nombre in archivos:
                if not nombre.lower().endswith(CORREO_EXTS):
                    continue
                ruta = os.path.join(raiz, nombre)
                relativa = os.path.relpath(ruta, acc_dir)
                mtime = os.path.getmtime(ruta)
                previo = cache.get(relativa)
                if previo and previo[0] == mtime:
                    encontrados = previo[1]
                else:
                    encontrados = sorted({c.lower() for c in RE_CORREO.findall(ia.extraer_texto(ruta, 300_000) or "")})
                vigentes[relativa] = [mtime, encontrados]
                for correo in encontrados:
                    correos.setdefault(correo, set()).add(f"el archivo «{nombre}»")
    return vigentes


def fetch_teachers(ctx, courses, correos):
    """Profesores de cada asignatura con su correo: el del perfil, uno publicado en Aules o el deducido."""
    data = ctx.ws("core_course_get_courses_by_field", {"field": "ids", "value": ",".join(str(c["id"]) for c in courses)})
    asignaturas = {}
    for c in data.get("courses", []):
        nombre = ctx.course_names.get(c["id"], c.get("fullname", "?"))
        buscar_correos(c.get("summary"), f"la descripción de {nombre}", correos)
        for contacto in c.get("contacts") or []:
            asignaturas.setdefault(contacto["id"], []).append(nombre)
    if not asignaturas:
        return {"profesores": [], "otros": []}
    usuarios = ctx.ws(
        "core_user_get_users_by_field",
        {"field": "id", **{f"values[{i}]": uid for i, uid in enumerate(sorted(asignaturas))}},
    )
    profesores, usados = [], set()
    for u in usuarios:
        apellidos = "".join(_letras(u.get("lastname")))
        correo = (u.get("email") or "").lower()
        origen = "su perfil de Aules" if correo else ""
        if not correo and len(apellidos) >= 5:
            for candidato, fuentes in sorted(correos.items()):
                if apellidos in re.sub(r"[^a-z]", "", candidato.split("@")[0]):
                    correo, origen = candidato, sorted(fuentes)[0]
                    break
        if correo:
            usados.add(correo)
        profesores.append(
            {
                "id": u["id"],
                "name": u.get("fullname") or "",
                "courses": sorted(asignaturas.get(u["id"], [])),
                "email": correo,
                "email_origin": origen,
                "email_guess": "" if correo else correo_deducido(u.get("firstname"), u.get("lastname")),
                "message_url": f"{ctx.base_url}/message/index.php?id={u['id']}",
            }
        )
    otros = [
        {"email": c, "sources": sorted(f)}
        for c, f in sorted(correos.items())
        if c not in usados and not c.startswith(("noreply", "no-reply"))
    ]
    return {"profesores": sorted(profesores, key=lambda p: p["name"]), "otros": otros}


def load_teachers(session):
    try:
        with open(os.path.join(account_dir(session["username"]), "profesores.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"profesores": [], "otros": []}


# Ejercicios interactivos sin fecha ni entrega (HotPot, H5P, lecciones…): práctica opcional.
PRACTICE_MODULES = ("hotpot", "h5pactivity", "lesson", "scorm", "game", "hvp")


def fetch_materials(ctx, courses, practicas=None, correos=None):
    """Archivos y enlaces que cuelgan de cada curso (apuntes, sesiones, trabajos…).

    Si se pasa la lista `practicas`, se rellena con los ejercicios de práctica del mismo recorrido."""
    materiales = []
    for c in courses:
        course_name = ctx.course_names.get(c["id"], c.get("fullname", "?"))
        for section in ctx.ws("core_course_get_contents", {"courseid": c["id"]}):
            if correos is not None:
                buscar_correos(section.get("summary"), f"la página de {course_name}", correos)
            for module in section.get("modules", []):
                if correos is not None:
                    buscar_correos(module.get("description"), f"la página de {course_name}", correos)
                if practicas is not None and module.get("modname") in PRACTICE_MODULES and module.get("uservisible", True):
                    practicas.append(
                        {
                            "id": f"practica_{module['id']}",
                            "name": module["name"],
                            "course": course_name,
                            "section": section.get("name") or "",
                            "activity": f"{module['modname']}_{module.get('instance')}",
                            "url": module.get("url") or f"{ctx.base_url}/mod/{module['modname']}/view.php?id={module['id']}",
                        }
                    )
                    continue
                if module.get("modname") not in ("resource", "folder", "url"):
                    continue
                for indice, f in enumerate(module.get("contents") or []):
                    if not f.get("fileurl"):
                        continue
                    materiales.append(
                        {
                            "id": f"mat_{module['id']}_{indice}",
                            "name": module["name"] if indice == 0 else (f.get("filename") or module["name"]),
                            "filename": f.get("filename") or module["name"],
                            "course": course_name,
                            "section": section.get("name") or "",
                            "externo": module.get("modname") == "url",
                            "url": f["fileurl"],
                            "size": f.get("filesize") or 0,
                            "timemodified": f.get("timemodified") or module.get("timemodified") or 0,
                        }
                    )
    return materiales


def mark_new_materials(state, materiales, now_ts, first_sync, clave="materiales"):
    baseline = first_sync or clave not in state
    visto = state.setdefault(clave, {})
    nuevos = []
    for m in materiales:
        if m["id"] not in visto:
            visto[m["id"]] = 0 if baseline else now_ts
            if not baseline:
                nuevos.append(m)
        m["is_new"] = bool(visto[m["id"]]) and now_ts - visto[m["id"]] <= NEW_BADGE_SECONDS
    return nuevos


def load_posts(session):
    try:
        with open(os.path.join(account_dir(session["username"]), "posts.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _load_json_list(session, nombre):
    try:
        with open(os.path.join(account_dir(session["username"]), nombre), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def load_grades(session):
    return _load_json_list(session, "notas.json")


def load_messages(session):
    return _load_json_list(session, "mensajes.json")


def load_materials(session):
    try:
        with open(os.path.join(account_dir(session["username"]), "materiales.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def descargar_material(session, material):
    """Descarga (si hace falta) un archivo del curso y devuelve su ruta local."""
    destino = os.path.join(
        account_dir(session["username"]),
        "material",
        sanitize(material["course"]),
        sanitize(material["filename"]),
    )
    if not os.path.exists(destino) or os.path.getmtime(destino) < (material.get("timemodified") or 0):
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        url = material["url"]
        sep = "&" if "?" in url else "?"
        r = http.get(f"{url}{sep}token={session['token']}", timeout=120)
        r.raise_for_status()
        write_atomic(destino, r.content)
        if material.get("timemodified"):
            os.utime(destino, (material["timemodified"], material["timemodified"]))
    return destino


def horarios_disponibles(session):
    pdfs = [
        m for m in load_materials(session)
        if not m["externo"] and "horario" in m["name"].lower() and m["filename"].lower().endswith(".pdf")
    ]
    # "Horario X Color" es el mismo horario con colores: se oculta si existe la versión normal.
    normales = {m["name"].lower() for m in pdfs if "color" not in m["name"].lower()}
    return [m for m in pdfs if "color" not in m["name"].lower() or m["name"].lower().replace(" color", "") not in normales]


def horario_para_fecha(lista, fecha=None):
    """En septiembre y junio el horario es distinto al del resto del curso."""
    fecha = fecha or datetime.now()
    quiere_sep_jun = fecha.month in (9, 6)
    candidatos = [m for m in lista if "color" not in m["name"].lower()] or lista
    for m in candidatos:
        nombre = m["name"].lower()
        es_sep_jun = "septiembre" in nombre or "junio" in nombre
        if es_sep_jun == quiere_sep_jun:
            return m
    return candidatos[0] if candidatos else None


def cargar_horarios(acc_dir):
    try:
        with open(os.path.join(acc_dir, "horarios.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
VERSION_LECTOR_HORARIO = 8
RE_HORA_EXACTA = re.compile(r"\[\s*(\d{1,2}[:.]\d{2})\s*/\s*(\d{1,2}[:.]\d{2})\s*\]")


def normalizar_hora(hora):
    return hora.replace(".", ":").rjust(5, "0")
RE_HORA = re.compile(r"^\d{1,2}[:.]\d{2}$")
RE_AULA = re.compile(r"\(?\s*(AULA[^)]*)\)?", re.I)


def horario_desde_pdf(ruta):
    """Saca del PDF las franjas horarias (exactas) y una propuesta de asignatura por celda.

    Las celdas combinadas del PDF hacen que el nombre de la asignatura sea solo una sugerencia:
    las horas son fiables, el texto hay que revisarlo.
    """
    from pypdf import PdfReader

    trozos = []

    def visitante(texto, cm, tm, fuente, tam):
        t = (texto or "").strip()
        if t:
            trozos.append({"y": round(tm[5], 1), "x": round(tm[4], 1), "t": t})

    PdfReader(ruta).pages[0].extract_text(visitor_text=visitante)

    por_y = {}
    for f in trozos:
        por_y.setdefault(f["y"], []).append(f)
    cabecera, mejor = None, 0
    for y, fila in por_y.items():
        n = sum(1 for f in fila if f["t"].strip().rstrip(":") in DIAS_SEMANA)
        if n > mejor:
            cabecera, mejor = y, n
    if not cabecera:
        raise RuntimeError("No encuentro la fila de días en el PDF del horario.")
    columnas = sorted((f["x"], f["t"].strip().rstrip(":")) for f in por_y[cabecera] if f["t"].strip().rstrip(":") in DIAS_SEMANA)

    horas = [f for f in trozos if RE_HORA.match(f["t"]) and f["y"] < cabecera]
    grupos_x = []
    for x in sorted({round(f["x"]) for f in horas}):
        if grupos_x and x - grupos_x[-1][-1] <= 12:
            grupos_x[-1].append(x)
        else:
            grupos_x.append([x])
    columnas_hora = [sum(g) / len(g) for g in grupos_x]

    manda = {}
    for i, xh in enumerate(columnas_hora):
        siguiente = columnas_hora[i + 1] if i + 1 < len(columnas_hora) else 10 ** 6
        for x, dia in columnas:
            if xh < x < siguiente:
                manda[dia] = xh

    franjas_col = {}
    for xh in columnas_hora:
        propias = sorted((f for f in horas if abs(f["x"] - xh) <= 12), key=lambda f: -f["y"])
        pares = []
        for i in range(0, len(propias) - 1, 2):
            pares.append({
                "inicio": propias[i]["t"].replace(".", ":").rjust(5, "0"),
                "fin": propias[i + 1]["t"].replace(".", ":").rjust(5, "0"),
                "y_top": propias[i]["y"],
                "y_fin": propias[i + 1]["y"],
            })
        franjas_col[xh] = pares

    limites = []
    for i, (x, dia) in enumerate(columnas):
        izq = (columnas[i - 1][0] + x) / 2 if i else x - 120
        der = (columnas[i + 1][0] + x) / 2 if i + 1 < len(columnas) else x + 140
        limites.append((izq, der, dia))

    # Cada fila del horario va desde su etiqueta de hora hasta la de la fila siguiente.
    for pares in franjas_col.values():
        alturas = [pares[i]["y_top"] - pares[i + 1]["y_top"] for i in range(len(pares) - 1)]
        tipica = sorted(alturas)[len(alturas) // 2] if alturas else 52
        for i, franja in enumerate(pares):
            franja["y_bottom"] = pares[i + 1]["y_top"] if i + 1 < len(pares) else franja["y_top"] - tipica

    # La columna de horas de un día no siempre es la de su izquierda (en septiembre el jueves usa
    # las del lunes). El "DESCANSO" escrito en la columna del día delata qué rejilla le toca.
    for izq, der, dia in limites:
        descansos = [f["y"] for f in trozos if izq <= f["x"] < der and f["y"] < cabecera and "DESCANSO" in f["t"].upper()]
        if not descansos:
            continue
        encajan = [
            xh for xh, pares in franjas_col.items()
            if any(es_descanso(p) and p["y_bottom"] < descansos[0] <= p["y_top"] + 6 for p in pares)
        ]
        # Varias rejillas pueden tener el recreo a la misma altura: entonces manda la cercanía.
        if encajan and manda.get(dia) not in encajan:
            centro = (izq + der) / 2
            manda[dia] = min(encajan, key=lambda xh: abs(xh - centro))

    # Debajo de la última fila está el pie del PDF (listas de profesores, fechas…): se descarta.
    suelo = min((p[-1]["y_bottom"] for p in franjas_col.values() if p), default=0) - 4

    por_dia = {d: [] for _, _, d in limites}
    for f in trozos:
        if f["y"] >= cabecera or f["y"] < suelo or RE_HORA.match(f["t"]):
            continue
        dia = next((d for izq, der, d in limites if izq <= f["x"] < der), None)
        if dia:
            por_dia[dia].append(f)

    resultado = {d: [] for d in DIAS_SEMANA}
    for dia in DIAS_SEMANA:
        franjas = franjas_col.get(manda.get(dia), [])
        if not franjas:
            continue

        # Una celda acaba en su línea de aula (o en DESCANSO); si no la hay, en un hueco grande.
        lineas = sorted(por_dia.get(dia, []), key=lambda f: -f["y"])
        celdas, actual = [], []
        for i, f in enumerate(lineas):
            # Una hora entre corchetes pegada a la línea de aula anterior pertenece a esa misma casilla.
            if not actual and RE_HORA_EXACTA.search(f["t"]) and celdas and celdas[-1][-1]["y"] - f["y"] <= 12:
                celdas[-1].append(f)
                continue
            actual.append(f)
            hueco = actual[-1]["y"] - lineas[i + 1]["y"] if i + 1 < len(lineas) else 10 ** 6
            if RE_AULA.search(f["t"]) or "DESCANSO" in f["t"].upper() or hueco > 25:
                celdas.append(actual)
                actual = []
        if actual:
            celdas.append(actual)

        contenido = []
        for celda in celdas:
            texto = re.sub(r"\s+", " ", " ".join(p["t"] for p in sorted(celda, key=lambda f: (-f["y"], f["x"])))).strip(" .·")
            aula = ""
            encontrada = RE_AULA.search(texto)
            if encontrada:
                aula = encontrada.group(1).strip().rstrip(").")
                texto = RE_AULA.sub("", texto).strip(" .·")
            # Las clases fuera de la rejilla normal llevan su hora exacta entre corchetes: "[13:15 / 14:10]".
            exacta = RE_HORA_EXACTA.search(texto)
            texto = re.sub(r"\[[^\]]*\]", "", texto).strip(" .·")
            profesor = ""
            # En el horario del curso las iniciales del profesor van al final del nombre.
            iniciales = re.search(r"\s([A-ZÑ]{2,5})\d?$", texto)
            if iniciales:
                profesor = iniciales.group(1)
                texto = texto[: iniciales.start()].strip(" .·")
            texto = re.sub(r"\s\d$", "", texto).strip(" .·")
            if texto and not re.match(r"^(lectivas|materia|profesores|\d{2}/\d{2}/\d{4})", texto, re.I):
                # Las anotaciones sueltas ("[13:15 / 14:10]", números) no forman parte del bloque centrado.
                utiles = [p["y"] for p in celda if not re.fullmatch(r"\[.*\]|\d+", p["t"].strip())] or [p["y"] for p in celda]
                contenido.append({"arriba": celda[0]["y"] + 6, "abajo": celda[-1]["y"] - 6,
                                  "centro": (max(utiles) + min(utiles)) / 2,
                                  "texto": texto, "aula": aula, "profesor": profesor,
                                  "exacta": (normalizar_hora(exacta.group(1)), normalizar_hora(exacta.group(2))) if exacta else None})

        # Las celdas "DESCANSO" no siempre están en la columna de su día; los descansos se sacan de las horas.
        contenido = [c for c in contenido if not re.fullmatch(r"(?i)descanso|recreo|pati|esbarjo", c["texto"])]

        # En el PDF, el texto va centrado en vertical dentro de su casilla, y la hora de cada franja
        # también. Una asignatura de dos franjas seguidas (p.ej. 8:00-9:20) queda centrada entre ambas.
        # Se prueba cada tramo de 1 a 3 franjas y se elige el que tiene el centro más parecido al texto.
        centros = [(fr["y_top"] + fr["y_fin"]) / 2 for fr in franjas]

        # Las casillas con hora exacta no se encajan: van tal cual y bloquean las franjas que pisan.
        exactas = [c for c in contenido if c["exacta"]]
        contenido = [c for c in contenido if not c["exacta"]]
        pisadas = set()
        for c in exactas:
            ini, fin = a_minutos(c["exacta"][0]), a_minutos(c["exacta"][1])
            pisadas |= {k for k, fr in enumerate(franjas) if a_minutos(fr["inicio"]) < fin and a_minutos(fr["fin"]) > ini}
            resultado[dia].append({"inicio": c["exacta"][0], "fin": c["exacta"][1],
                                   "asignatura": c["texto"], "aula": c["aula"], "profesor": c["profesor"]})

        propuestas = []
        for celda in contenido:
            for k in range(len(franjas)):
                for j in range(k, min(k + 3, len(franjas))):
                    # Una clase larga solo abarca franjas seguidas: ni descansos ni huecos entre medias.
                    if es_descanso(franjas[j]) or (j > k and franjas[j]["inicio"] != franjas[j - 1]["fin"]):
                        break
                    # Pequeña penalización por franja extra: ante la duda, la casilla más corta.
                    error = abs(celda["centro"] - (centros[k] + centros[j]) / 2) + 4 * (j - k)
                    propuestas.append((error, k, j, celda))
        # Primero las casillas que encajan de lleno en una sola franja; luego el resto por precisión.
        propuestas.sort(key=lambda p: (not (p[1] == p[2] and p[0] <= 8), p[0]))

        tramos, ocupadas, colocadas = {}, set(pisadas), set()
        for error, k, j, celda in propuestas:
            filas = set(range(k, j + 1))
            if error > 30 or id(celda) in colocadas or filas & ocupadas:
                continue
            tramos[k] = (j, celda)
            ocupadas |= filas
            colocadas.add(id(celda))

        i = 0
        while i < len(franjas):
            if es_descanso(franjas[i]):
                resultado[dia].append({"inicio": franjas[i]["inicio"], "fin": franjas[i]["fin"],
                                       "asignatura": "DESCANSO", "aula": "", "profesor": ""})
                i += 1
                continue
            if i not in tramos:
                i += 1
                continue
            j, celda = tramos[i]
            resultado[dia].append({
                "inicio": franjas[i]["inicio"],
                "fin": franjas[j]["fin"],
                "asignatura": celda["texto"],
                "aula": celda["aula"],
                "profesor": celda.get("profesor", ""),
            })
            i = j + 1
        resultado[dia].sort(key=lambda f: f["inicio"])
        resultado[dia] = rellenar_descansos(resultado[dia])

    # El recreo es común a toda la semana: si un día tiene hora libre justo antes, también lo lleva.
    recreos = {(f["inicio"], f["fin"]) for franjas in resultado.values() for f in franjas if f["asignatura"] == "DESCANSO"}
    for dia, franjas in resultado.items():
        for inicio, fin in recreos:
            if any(f["inicio"] == inicio and f["fin"] == fin for f in franjas):
                continue
            ocupado = any(a_minutos(f["inicio"]) < a_minutos(fin) and a_minutos(f["fin"]) > a_minutos(inicio) for f in franjas)
            antes = any(a_minutos(f["fin"]) <= a_minutos(inicio) for f in franjas)
            despues = any(a_minutos(f["inicio"]) >= a_minutos(fin) for f in franjas)
            if not ocupado and antes and despues:
                franjas.append({"inicio": inicio, "fin": fin, "asignatura": "DESCANSO", "aula": "", "profesor": ""})
        franjas.sort(key=lambda f: f["inicio"])
    return resultado


DESCANSO_MAX_MIN = 30


def a_minutos(hora):
    try:
        h, m = hora.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def es_descanso(franja):
    duracion = a_minutos(franja["fin"]) - a_minutos(franja["inicio"])
    return 0 < duracion <= DESCANSO_MAX_MIN


def rellenar_descansos(franjas):
    """Un hueco corto entre dos clases es un descanso aunque el PDF no lo escriba."""
    resultado = []
    for actual in franjas:
        if resultado:
            anterior = resultado[-1]
            hueco = a_minutos(actual["inicio"]) - a_minutos(anterior["fin"])
            if 0 < hueco <= DESCANSO_MAX_MIN and "DESCANSO" not in (anterior["asignatura"], actual["asignatura"]):
                resultado.append({"inicio": anterior["fin"], "fin": actual["inicio"],
                                  "asignatura": "DESCANSO", "aula": "", "profesor": ""})
        resultado.append(actual)
    # Un descanso al principio o al final del día no tiene sentido: sería un hueco sin clases.
    while resultado and resultado[0]["asignatura"] == "DESCANSO":
        resultado.pop(0)
    while resultado and resultado[-1]["asignatura"] == "DESCANSO":
        resultado.pop()
    return resultado


def plantilla_horario(session, material_id):
    material = next((m for m in horarios_disponibles(session) if m["id"] == material_id), None)
    if not material:
        raise RuntimeError("Ese horario ya no está en Aules.")
    return {"nombre": material["name"], "dias": horario_desde_pdf(descargar_material(session, material))}


def obtener_horario(session, material, acc_dir=None):
    """Un horario ya listo para usar; si no está guardado (o el lector ha mejorado) se lee del PDF."""
    acc_dir = acc_dir or account_dir(session["username"])
    guardado = cargar_horarios(acc_dir).get(material["id"])
    # Lo editado a mano se respeta siempre; lo leído del PDF se vuelve a leer si el lector ha mejorado.
    if guardado and (guardado.get("modelo") != "leído del PDF" or guardado.get("version") == VERSION_LECTOR_HORARIO):
        return guardado
    try:
        horario = guardar_horario(session, material["id"], plantilla_horario(session, material["id"]), "leído del PDF")
        log(f"Horario leído del PDF: {material['name']}")
        return horario
    except Exception as e:
        log(f"No se pudo leer el horario del PDF «{material['name']}»: {e}")
        return guardado


def releer_horario(session, material_id):
    """Descarta las correcciones a mano y vuelve a leer el horario del PDF."""
    acc_dir = account_dir(session["username"])
    cache = cargar_horarios(acc_dir)
    cache.pop(material_id, None)
    write_atomic(os.path.join(acc_dir, "horarios.json"), json.dumps(cache, ensure_ascii=False, indent=2))
    material = next((m for m in horarios_disponibles(session) if m["id"] == material_id), None)
    if not material:
        raise RuntimeError("Ese horario ya no está en Aules.")
    return obtener_horario(session, material, acc_dir)


def horario_actual(session, acc_dir=None):
    """El horario del mes en curso (septiembre y junio tienen el suyo)."""
    activo = horario_para_fecha(horarios_disponibles(session))
    return obtener_horario(session, activo, acc_dir) if activo else None


def nombre_corto_horario(nombre):
    corto = re.sub(r"(?i)^horario\s*", "", nombre).strip()
    return corto[:1].upper() + corto[1:] if corto else nombre


def horarios_todos(session):
    lista = horarios_disponibles(session)
    activo = horario_para_fecha(lista)
    return [
        {
            "id": m["id"],
            "nombre": nombre_corto_horario(m["name"]),
            "activo": bool(activo and m["id"] == activo["id"]),
            "horario": obtener_horario(session, m),
        }
        for m in lista
    ]


def guardar_horario(session, material_id, horario, origen="editado a mano"):
    """Guarda un horario editado a mano, con la misma forma que el interpretado por la IA."""
    acc_dir = account_dir(session["username"])
    dias = {}
    for dia, franjas in (horario.get("dias") or {}).items():
        limpias = []
        for f in franjas if isinstance(franjas, list) else []:
            inicio = str(f.get("inicio", "")).strip()[:5]
            if not inicio:
                continue
            limpias.append({
                "inicio": inicio,
                "fin": str(f.get("fin", "")).strip()[:5],
                "asignatura": str(f.get("asignatura", "")).strip(),
                "aula": str(f.get("aula", "")).strip(),
                "profesor": str(f.get("profesor", "")).strip(),
            })
        dias[str(dia).strip().capitalize()] = sorted(limpias, key=lambda f: f["inicio"])
    cache = cargar_horarios(acc_dir)
    cache[material_id] = {
        "nombre": horario.get("nombre") or material_id,
        "dias": dias,
        "material_id": material_id,
        "modelo": origen,
        "version": VERSION_LECTOR_HORARIO,
        "analizado": datetime.now().isoformat(timespec="seconds"),
    }
    write_atomic(os.path.join(acc_dir, "horarios.json"), json.dumps(cache, ensure_ascii=False, indent=2))
    return cache[material_id]


def load_state(acc_dir):
    try:
        with open(os.path.join(acc_dir, "state.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_state(acc_dir, state):
    write_atomic(os.path.join(acc_dir, "state.json"), json.dumps(state, ensure_ascii=False, indent=2))


def normalize_state(raw):
    state = dict(raw or {})
    if "seen_ids" in state:
        state.setdefault("items", {i: 0 for i in state.pop("seen_ids")})
    state.setdefault("items", {})
    state.setdefault("reminders", {})
    return state


def mark_new_items(state, items, now_ts, first_sync):
    seen = state["items"]
    new_items = []
    for a in items:
        if a["id"] not in seen:
            # En la primera sincronización de una cuenta todo "ya existía": no se avisa.
            seen[a["id"]] = 0 if first_sync else now_ts
            if not first_sync and a["kind"] != "aviso" and not a["done"]:
                new_items.append(a)
        a["is_new"] = a["kind"] != "aviso" and not a["done"] and bool(seen[a["id"]]) and now_ts - seen[a["id"]] <= NEW_BADGE_SECONDS
    return new_items


def _firma_item(a):
    """Lo que, si cambia, merece un aviso: la fecha, la descripción del profe y los archivos adjuntos."""
    return {
        "fecha": int(a.get("duedate") or 0),
        "etiqueta": a.get("due_label") or "",
        "texto": hashlib.sha1(" ".join((a.get("summary") or "").split()).encode("utf-8")).hexdigest()[:12],
        "adjuntos": {f["filename"]: int(f.get("timemodified") or 0) for f in a.get("attachments") or []},
    }


def describir_cambios(antes, ahora):
    cambios = []
    # Un cuestionario pasa de «Abre» a «Cierra» al abrirse: su fecha cambia sin que el profe toque nada.
    if antes["fecha"] != ahora["fecha"] and {antes["etiqueta"], ahora["etiqueta"]} != {"Abre", "Cierra"}:
        if not ahora["fecha"]:
            cambios.append("Ya no tiene fecha límite")
        elif not antes["fecha"]:
            cambios.append(f"Ahora tiene fecha: {format_due(ahora['fecha'])}")
        elif ahora["etiqueta"] == "Prórroga" and antes["etiqueta"] != "Prórroga":
            cambios.append(f"Tienes prórroga hasta el {format_due(ahora['fecha'])}")
        else:
            sentido = "se adelanta" if ahora["fecha"] < antes["fecha"] else "se retrasa"
            cambios.append(f"La fecha {sentido}: del {format_due(antes['fecha'])} al {format_due(ahora['fecha'])}")
    if antes["texto"] != ahora["texto"]:
        cambios.append("El profe ha cambiado la descripción")
    adjuntos_antes = antes.get("adjuntos", {})
    for nombre, fecha in ahora["adjuntos"].items():
        if nombre not in adjuntos_antes:
            cambios.append(f"Archivo nuevo: {nombre}")
        elif fecha and adjuntos_antes[nombre] and fecha != adjuntos_antes[nombre]:
            cambios.append(f"Archivo actualizado: {nombre}")
    cambios += [f"Ya no está el archivo: {nombre}" for nombre in adjuntos_antes if nombre not in ahora["adjuntos"]]
    return cambios


def mark_changed_items(state, items, now_ts, marcadas=()):
    """Compara cada tarea con cómo era en la comprobación anterior. Devuelve las que el profe ha cambiado.

    Las que marcaste como aviso o como hecha no avisan: ya dijiste que no te importan o que están hechas.
    """
    firmas = state.setdefault("items_firma", {})
    recientes = state.setdefault("items_cambios", {})
    cambiadas = []
    for a in items:
        ahora, antes = _firma_item(a), firmas.get(a["id"])
        firmas[a["id"]] = ahora
        # La primera vez que se ve una tarea (o tras actualizar a esta versión) solo se guarda cómo es.
        if antes is None or a["kind"] == "aviso" or a["done"] or a["id"] in marcadas:
            continue
        cambios = describir_cambios(antes, ahora)
        if cambios:
            previos = recientes.get(a["id"], {}).get("cambios", [])
            recientes[a["id"]] = {"ts": now_ts, "cambios": previos + [c for c in cambios if c not in previos]}
            cambiadas.append(dict(a, cambios=cambios))
    for clave in [c for c, v in recientes.items() if now_ts - v["ts"] > NEW_BADGE_SECONDS]:
        del recientes[clave]
    for a in items:
        a["cambios"] = [] if a["done"] or a["id"] in marcadas else recientes.get(a["id"], {}).get("cambios", [])
    return cambiadas


def olvidar_resumenes(acc_dir, cambiadas):
    """Borra el resumen de IA de las tareas cuyo enunciado ha cambiado: así no se muestra uno que ya no es cierto."""
    afectadas = [a["id"] for a in cambiadas if any(not c.startswith(("La fecha", "Ya no tiene fecha", "Ahora tiene fecha", "Tienes prórroga"))
                                                    for c in a["cambios"])]
    if not afectadas:
        return
    cache = ia.cargar_cache(acc_dir)
    borradas = [i for i in afectadas if cache.get(i, {}).pop("resumen", None) is not None]
    if borradas:
        ia.guardar_cache(acc_dir, cache)
        log(f"Resumen de IA descartado porque cambió la tarea: {', '.join(borradas)}")


def mark_new_posts(state, posts, now_ts, first_sync, userid):
    baseline = first_sync or "forum" not in state
    last_seen = state.setdefault("forum", {})
    detected = state.setdefault("forum_new", {})
    new_posts = []
    for p in posts:
        key = str(p["discussion"])
        previous = last_seen.get(key)
        if previous is None or p["timemodified"] > previous:
            if not baseline and p["author_id"] != userid:
                detected[key] = now_ts
                new_posts.append(p)
            last_seen[key] = p["timemodified"]
        p["is_new"] = bool(detected.get(key)) and now_ts - detected[key] <= NEW_BADGE_SECONDS
        p["is_reply"] = p["is_new"] and p["numreplies"] > 0
    state["forum_new"] = {k: v for k, v in detected.items() if now_ts - v <= NEW_BADGE_SECONDS}
    return new_posts


def mark_new_grades(state, notas, now_ts, first_sync):
    baseline = first_sync or "notas" not in state
    vistas = state.setdefault("notas", {})
    detectadas = state.setdefault("notas_new", {})
    nuevas = []
    for n in notas:
        firma = f"{n['grade']}|{n['feedback']}"
        # Las firmas antiguas llevaban el icono HTML de aprobado: se limpia para no avisar de una nota que no ha cambiado.
        if RE_ETIQUETA.sub("", vistas.get(n["id"]) or "") != firma:
            # La nota total cambia sola cuando corrigen algo: se muestra, pero no se avisa aparte.
            if not baseline and not n["total"]:
                detectadas[n["id"]] = now_ts
                nuevas.append(n)
            vistas[n["id"]] = firma
        n["is_new"] = bool(detectadas.get(n["id"])) and now_ts - detectadas[n["id"]] <= NEW_BADGE_SECONDS
    state["notas_new"] = {k: v for k, v in detectadas.items() if now_ts - v <= NEW_BADGE_SECONDS}
    return nuevas


def mark_new_messages(state, mensajes, now_ts, first_sync):
    baseline = first_sync or "mensajes" not in state
    vistos = state.setdefault("mensajes", {})
    detectados = state.setdefault("mensajes_new", {})
    nuevos = []
    for m in mensajes:
        clave = str(m["conversation"])
        if m["last_id"] > vistos.get(clave, 0):
            if not baseline and not m["from_me"]:
                detectados[clave] = now_ts
                nuevos.append(m)
            vistos[clave] = m["last_id"]
        m["is_new"] = not m["from_me"] and bool(detectados.get(clave)) and now_ts - detectados[clave] <= NEW_BADGE_SECONDS
    state["mensajes_new"] = {k: v for k, v in detectados.items() if now_ts - v <= NEW_BADGE_SECONDS}
    return nuevos


def titulo_recordatorio(recordatorios, normal):
    """Un cuestionario avisa de cuándo se abre o cuándo se cierra; si no, de cuándo vence."""
    horas = min(h for _, h in recordatorios)
    etiquetas = {a.get("due_label") for a, _ in recordatorios}
    if etiquetas == {"Abre"}:
        return f"Se abre en menos de {horas} h"
    if etiquetas == {"Cierra"}:
        return f"Cierra en menos de {horas} h"
    return normal.format(h=horas)


def sin_las_nuevas(recordatorios, nuevas):
    """Lo que acaba de aparecer ya se avisa como nuevo: un segundo aviso a la vez solo molesta.

    El recordatorio ya queda apuntado como enviado, así que no salta luego por ese mismo umbral.
    """
    ids = {a["id"] for a in nuevas}
    return [(a, h) for a, h in recordatorios if a["id"] not in ids]


def pending_reminders(state, items, now_ts, kind, hours):
    """Actividades de `kind` sin hacer que acaban de cruzar alguno de los umbrales de `hours`."""
    sent_by_key = state["reminders"]
    due = []
    for a in items:
        if a["kind"] != kind or a["done"] or not a["duedate"]:
            continue
        remaining = a["duedate"] - now_ts
        crossed = [h for h in hours if 0 < remaining <= h * 3600]
        if not crossed:
            continue
        # La fecha va en la clave: si la cambian (o cambias la tuya), se vuelve a avisar.
        key = f"{a['id']}:{a['due_label']}:{int(a['duedate'])}"
        sent = set(sent_by_key.get(key, []))
        if min(crossed) not in sent:
            sent_by_key[key] = sorted(sent | set(crossed))
            due.append((a, min(crossed)))
    return due


DIAS_NOMBRE = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def tomorrow_summary(state, items, now, sin_clase=None):
    """Lo que vence pronto y aún no has hecho, una vez por la mañana (hoy y mañana) y otra por la tarde (mañana)."""
    hoy = now.strftime("%Y-%m-%d")
    # Fines de semana, festivos y vacaciones se saltan: se mira hasta que vuelve a haber clase.
    proximo = siguiente_dia_lectivo(now.date(), sin_clase or {})
    fin = datetime.combine(proximo, hora_del_dia()) + timedelta(days=1)
    manana = datetime(now.year, now.month, now.day) + timedelta(days=1)
    hasta = "mañana" if (fin - manana).days == 1 else f"antes de volver a clase ({DIAS_NOMBRE[proximo.weekday()]} {proximo.day})"
    if now.hour >= DAILY_SUMMARY_HOUR:
        if state.get("resumen_dia") == hoy:
            return None
        state["resumen_dia"] = hoy
        inicio, cuando = manana, hasta
    elif now.hour >= MORNING_SUMMARY_HOUR:
        if state.get("resumen_manana") == hoy:
            return None
        state["resumen_manana"] = hoy
        inicio, cuando = now, "hoy y " + hasta
    else:
        return None
    pendientes = sorted(
        (
            a
            for a in items
            if a["kind"] in ("tarea", "examen") and not a["done"] and a["duedate"]
            and inicio.timestamp() <= a["duedate"] < fin.timestamp()
        ),
        key=lambda a: a["duedate"],
    )
    return {"cuando": cuando, "items": pendientes}


def toast(title, message, timeout=15):
    try:
        from plyer import notification

        notification.notify(title=title, message=message[:250], timeout=timeout)
    except Exception as e:
        log(f"No se pudo mostrar la notificación: {e}")


def notify(title, items, timeout=15):
    names = ", ".join(a["name"] for a in items[:3])
    if len(items) > 3:
        names += f" y {len(items) - 3} más"
    toast(title, names, timeout)


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def send_notifications(username, new_items, exam_reminders, new_posts, new_materials=(), task_reminders=(),
                       new_grades=(), new_messages=(), summary=None, new_practices=(), changed_items=()):
    new_exams = [a for a in new_items if a["kind"] == "examen"]
    new_tasks = [a for a in new_items if a["kind"] == "tarea"]
    if new_exams:
        log("Examen/cuestionario nuevo: " + ", ".join(a["name"] for a in new_exams))
        notify("Nuevo examen o cuestionario en Aules", new_exams, timeout=30)
    if exam_reminders:
        hours = min(h for _, h in exam_reminders)
        exams = [a for a, _ in exam_reminders]
        log(f"Recordatorio examen (<{hours} h): " + ", ".join(a["name"] for a in exams))
        notify(titulo_recordatorio(exam_reminders, "Examen en menos de {h} h"), exams, timeout=30)
    if task_reminders:
        hours = min(h for _, h in task_reminders)
        tasks = [a for a, _ in task_reminders]
        log(f"Recordatorio entrega (<{hours} h): " + ", ".join(a["name"] for a in tasks))
        notify(titulo_recordatorio(task_reminders, "Sin entregar: vence en menos de {h} h"), tasks, timeout=20)
    if new_tasks:
        log(f"{len(new_tasks)} tarea(s) nueva(s): " + ", ".join(a["name"] for a in new_tasks))
        notify(f"Aules: {len(new_tasks)} tarea(s) nueva(s)", new_tasks)
    if changed_items:
        log("Tarea(s) modificada(s): " + "; ".join(f"{a['name']} ({', '.join(a['cambios'])})" for a in changed_items))
        if len(changed_items) == 1:
            a = changed_items[0]
            toast(f"Cambio en «{a['name']}»", f"{a['course']}: " + ". ".join(a["cambios"]), 30)
        else:
            notify(f"Aules: {len(changed_items)} tareas modificadas", changed_items, timeout=30)
    if new_grades:
        log(f"{len(new_grades)} nota(s) nueva(s): " + ", ".join(f"{n['name']} ({n['grade']})" for n in new_grades))
        if len(new_grades) == 1:
            n = new_grades[0]
            toast(f"Nota nueva: {n['grade']}" + (f" / {n['max']}" if n["max"] else ""), f"{n['name']} · {n['course']}", 20)
        else:
            toast(f"Aules: {len(new_grades)} notas nuevas", ", ".join(f"{n['name']} ({n['grade']})" for n in new_grades[:4]), 20)
    if new_messages:
        log(f"{len(new_messages)} mensaje(s) privado(s) nuevo(s) de: " + ", ".join(m["author"] or m["who"] for m in new_messages))
        if len(new_messages) == 1:
            m = new_messages[0]
            toast(f"Mensaje de {m['author'] or m['who']}", m["text"] or "(sin texto)", 20)
        else:
            toast(f"Aules: {len(new_messages)} mensajes nuevos", ", ".join(m["author"] or m["who"] for m in new_messages), 20)
    if new_posts:
        n = len(new_posts)
        log(f"{n} mensaje(s) de foro nuevo(s): " + ", ".join(p["name"] for p in new_posts))
        # Aviso discreto y breve: los foros tienen menos prioridad que tareas y exámenes.
        notify(f"Foro: {n} mensaje{'s' if n != 1 else ''} nuevo{'s' if n != 1 else ''}", new_posts, timeout=6)
    if new_materials:
        n = len(new_materials)
        log(f"{n} archivo(s) nuevo(s) de material: " + ", ".join(m["name"] for m in new_materials[:5]))
        # Aviso discreto, como el de los foros: es material de clase, no una entrega.
        notify(f"Material nuevo en Aules ({n})", new_materials, timeout=6)
    if new_practices:
        n = len(new_practices)
        log(f"{n} ejercicio(s) de práctica nuevo(s): " + ", ".join(p["name"] for p in new_practices[:5]))
        # Son voluntarios: aviso discreto, como el del material.
        notify(f"Ejercicios de práctica nuevos ({n})", new_practices, timeout=6)
    if summary and summary["items"]:
        pendientes = summary["items"]
        log(f"Resumen del día ({summary['cuando']}): " + ", ".join(a["name"] for a in pendientes))
        notify(f"{_plural(len(pendientes), 'entrega', 'entregas')} {summary['cuando']}", pendientes, timeout=20)


def run_check(session):
    acc_dir = account_dir(session["username"])
    os.makedirs(acc_dir, exist_ok=True)
    base_url, token = session["base_url"], session["token"]

    now_ts = datetime.now().timestamp()
    raw_state = load_state(acc_dir)
    state = normalize_state(raw_state)
    first_sync = raw_state is None

    site_info = call_ws(base_url, token, "core_webservice_get_site_info")
    try:
        actualizar_foto(session, site_info)
    except Exception as e:
        log(f"No se pudo descargar la foto de perfil: {e}")
    courses = call_ws(base_url, token, "core_enrol_get_users_courses", {"userid": site_info["userid"]})
    ctx = Ctx(
        base_url=base_url,
        token=token,
        userid=site_info["userid"],
        acc_dir=acc_dir,
        course_names={c["id"]: c["fullname"] for c in courses},
        # Moodle espera arrays como courseids[0], courseids[1]... en el POST.
        course_params={f"courseids[{i}]": c["id"] for i, c in enumerate(courses)},
    )

    items = fetch_assignments(ctx, "assign")
    items += ctx.optional("tareas GVA", lambda: fetch_assignments(ctx, "assigngva")) or []
    items += ctx.optional("cuestionarios", lambda: fetch_quizzes(ctx)) or []
    posts = ctx.optional("foros", lambda: fetch_forum_posts(ctx))
    progreso = {}
    notas = ctx.optional("notas", lambda: fetch_grades(ctx, courses, progreso))
    mensajes = ctx.optional("mensajes", lambda: fetch_messages(ctx))
    materiales = practicas = None
    if (first_sync or now_ts - state.get("materiales_ts", 0) >= MATERIALS_EVERY_SECONDS
            or not os.path.exists(os.path.join(acc_dir, "practicas.json"))
            or not os.path.exists(os.path.join(acc_dir, "profesores.json"))):
        encontradas, correos = [], {}
        materiales = ctx.optional("material de los cursos", lambda: fetch_materials(ctx, courses, encontradas, correos))
        if materiales is not None:
            state["materiales_ts"] = now_ts
            practicas = encontradas
            # Los profes cambian poco: se revisan a la vez que el material.
            for a in items:
                buscar_correos(a["summary"], f"la tarea «{a['name']}»", correos)
            for p in posts or []:
                buscar_correos(p["summary"], f"el foro «{p['name']}»", correos)
            try:
                state["correos_archivos"] = correos_en_archivos(acc_dir, state.get("correos_archivos", {}), correos)
            except Exception as e:
                log(f"No se pudieron revisar los archivos en busca de correos: {e}")
            try:
                actualizar_calendario(session, acc_dir, materiales)
            except Exception as e:
                log(f"No se pudo leer el calendario escolar: {e}")
            profesores = ctx.optional("profesores", lambda: fetch_teachers(ctx, courses, correos))
            if profesores is not None:
                write_atomic(os.path.join(acc_dir, "profesores.json"), json.dumps(profesores, ensure_ascii=False, indent=2))

    new_items = mark_new_items(state, items, now_ts, first_sync)
    changed_items = mark_changed_items(state, items, now_ts, set(cargar_marcas(acc_dir)))
    olvidar_resumenes(acc_dir, changed_items)
    new_posts = mark_new_posts(state, posts, now_ts, first_sync, ctx.userid) if posts is not None else []
    new_materials = mark_new_materials(state, materiales, now_ts, first_sync) if materiales is not None else []
    new_practices = mark_new_materials(state, practicas, now_ts, first_sync, "practicas") if practicas is not None else []
    new_grades = mark_new_grades(state, notas, now_ts, first_sync) if notas is not None else []
    # La nota de un ejercicio de práctica la acabas de sacar tú: no hace falta avisarte.
    new_grades = [n for n in new_grades if n["activity"].split("_")[0] not in PRACTICE_MODULES]
    new_messages = mark_new_messages(state, mensajes, now_ts, first_sync) if mensajes is not None else []
    # Recordatorios y resumen también para lo que has apuntado tú, y sin lo que marcaste como hecho o como aviso.
    todos = aplicar_marcas(acc_dir, items) + items_propios(acc_dir)
    exam_reminders = sin_las_nuevas(pending_reminders(state, todos, now_ts, "examen", EXAM_REMINDER_HOURS), new_items)
    task_reminders = sin_las_nuevas(pending_reminders(state, todos, now_ts, "tarea", TASK_REMINDER_HOURS), new_items)
    summary = tomorrow_summary(state, todos, datetime.now(), dias_sin_clase(acc_dir))

    # Si algo no se pudo leer esta vez, se muestra lo último que sí se leyó.
    if posts is None:
        posts = load_posts(session)
    if notas is None:
        notas = load_grades(session)
    if mensajes is None:
        mensajes = load_messages(session)
    if materiales is None:
        materiales = load_materials(session)
    if practicas is None:
        practicas = _load_json_list(session, "practicas.json")

    if notas is not None:
        write_atomic(os.path.join(acc_dir, "progreso.json"), json.dumps(progreso, ensure_ascii=False, indent=2))
    for nombre, datos in (("items.json", items), ("posts.json", posts), ("notas.json", notas),
                          ("mensajes.json", mensajes), ("materiales.json", materiales), ("practicas.json", practicas)):
        write_atomic(os.path.join(acc_dir, nombre), json.dumps(datos, ensure_ascii=False, indent=2))

    escribir_informe(session, ctx.warnings, [c["fullname"] for c in courses], int(now_ts))
    save_state(acc_dir, state)
    send_notifications(session["username"], new_items, exam_reminders, new_posts, new_materials,
                       task_reminders, new_grades, new_messages, summary, new_practices, changed_items)


def escribir_informe(session, warnings=None, cursos=None, actualizado=None):
    """Genera la pantalla principal con lo último guardado. Sin consultar Aules, así que es instantáneo."""
    acc_dir = account_dir(session["username"])
    previo = load_report_status(session)
    warnings = previo.get("warnings", []) if warnings is None else warnings
    cursos = previo.get("cursos", []) if cursos is None else cursos
    actualizado = actualizado or previo.get("actualizado") or int(datetime.now().timestamp())
    items = aplicar_marcas(acc_dir, _load_aules_items(acc_dir)) + items_propios(acc_dir)
    posts, notas, mensajes = load_posts(session), load_grades(session), load_messages(session)
    materiales, practicas = load_materials(session), _load_json_list(session, "practicas.json")
    sin_clase = dias_sin_clase(acc_dir)
    horario = horario_actual(session, acc_dir)
    if horario:
        horario = dict(horario, no_lectivos=sin_clase)

    foto = version_foto(session)
    try:
        with open(os.path.join(acc_dir, "progreso.json"), "r", encoding="utf-8") as f:
            progreso = json.load(f)
    except (OSError, ValueError):
        progreso = {}
    # Huella del contenido: la página solo se recarga sola cuando cambia algo de verdad.
    firma = hashlib.sha1(
        json.dumps([items, posts, notas, mensajes, materiales, practicas, warnings, sin_clase, foto, progreso], sort_keys=True,
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    write_atomic(
        report_path(session),
        build_report(items, posts, session, warnings, EXAM_REMINDER_HOURS[0], ia.cargar_cache(acc_dir), cursos,
                     materiales, horario, notas, mensajes, firma, practicas, foto, progreso),
    )
    write_atomic(
        os.path.join(acc_dir, "estado.json"),
        json.dumps({"firma": firma, "actualizado": actualizado, "cursos": cursos, "warnings": warnings}, ensure_ascii=False),
    )


def load_report_status(session):
    try:
        with open(os.path.join(account_dir(session["username"]), "estado.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def server_running():
    try:
        return http.get(SERVER_HEALTH_URL, timeout=2).text == "ok"
    except requests.RequestException:
        return False


def start_server_in_background():
    """Arranca la app sin abrir el navegador; ella se encarga de comprobar cada minuto y medio."""
    ejecutable = sys.executable
    if ejecutable.lower().endswith("python.exe"):
        ejecutable = ejecutable[: -len("python.exe")] + "pythonw.exe"
    orden = [ejecutable, os.path.join(BASE_DIR, "servidor.py"), "--sin-navegador"]
    base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    # Se separa del trabajo del Programador de tareas para que no la cierre al terminar esta tarea.
    for flags in (base | subprocess.CREATE_BREAKAWAY_FROM_JOB, base):
        try:
            subprocess.Popen(orden, creationflags=flags, close_fds=True, cwd=BASE_DIR)
            return True
        except OSError:
            continue
    return False


def main():
    # La app abierta ya comprueba Aules cada minuto y medio: aquí basta con asegurarse de que está en marcha.
    if server_running():
        return
    if start_server_in_background():
        log("App arrancada en segundo plano por la tarea programada")
        return
    session = load_session()
    if not session:
        log("Sin sesión iniciada: abre Aules desde el acceso directo para iniciar sesión")
        return
    try:
        comprobar(session)
    except SessionExpired:
        pass
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
