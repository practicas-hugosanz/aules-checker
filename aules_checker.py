import base64
import hashlib
import html
import json
import os
import re
import requests
import secrets
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, time as hora_del_dia, timedelta
from requests.adapters import HTTPAdapter
from urllib.parse import unquote, urlencode, urlparse
from urllib3.util.retry import Retry

import almacen
import ia
from interfaz import asignatura_a_curso, build_report, format_due, portal_de, PORTALES, PORTALES_SSO
from lector_pdf import _letras, calendario_desde_pdf, DIAS_SEMANA, horario_desde_pdf
from lector_preguntas import _numero, analizar_pregunta


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
    # Sin respetar «Retry-After»: en mantenimiento Aules pide volver en 300 s y cada consulta se quedaba colgada
    # hasta 15 minutos (3 reintentos), con la app «revisando» sin parar. Sin lanzar error al agotar los reintentos,
    # para poder ver qué respondió Aules (p. ej. su página de mantenimiento).
    HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=(502, 503, 504), allowed_methods=None,
                                  respect_retry_after_header=False, raise_on_status=False),
                pool_maxsize=12),
)
# Las consultas van en paralelo (Aules tarda lo mismo en una que en varias a la vez), pero nunca más de
# estas a la vez, para no saturar el servidor del instituto.
CONSULTAS_A_LA_VEZ = 8
_limite_aules = threading.BoundedSemaphore(CONSULTAS_A_LA_VEZ)
_log_lock = threading.Lock()


def en_paralelo(funcion, elementos):
    """Como map(), pero a la vez. Devuelve los resultados en el mismo orden; si una falla, lanza su error."""
    elementos = list(elementos)
    if len(elementos) <= 1:
        return [funcion(e) for e in elementos]
    with ThreadPoolExecutor(min(CONSULTAS_A_LA_VEZ, len(elementos))) as ex:
        return list(ex.map(funcion, elementos))


class LoginError(Exception):
    pass


class SessionExpired(Exception):
    pass


class AulesEnMantenimiento(RuntimeError):
    pass


MENSAJE_MANTENIMIENTO = "Aules está en mantenimiento ahora mismo. Se muestra lo último guardado y se volverá a mirar solo."


def _comprobar_mantenimiento(r):
    if r.status_code == 503 and re.search(r"manteniment|mantenimiento|maintenance", r.text[:3000], re.I):
        raise AulesEnMantenimiento(MENSAJE_MANTENIMIENTO)


write_atomic = almacen.escribir_atomico


def log(message):
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line)
    # Todo dentro del cerrojo: si dos hilos recortaban el log a la vez, se perdían líneas.
    with _log_lock:
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


def account_dir(cuenta):
    return os.path.join(ACCOUNTS_DIR, sanitize(cuenta.lower()))


def clave_cuenta(username, base_url):
    """Nombre de la carpeta de una cuenta. Las de FP siguen como siempre (solo el usuario); las de otras etapas
    llevan la etapa detrás, porque el mismo usuario puede tener cuenta en dos Aules distintos."""
    portal = portal_de(base_url)
    return username if portal == "fp" else f"{username}@{portal}"


def carpeta(session):
    return account_dir(clave_cuenta(session["username"], session.get("base_url")))


def report_path(session):
    return os.path.join(carpeta(session), "informe.html")


def load_session():
    try:
        with open(SESSION_PATH, "r", encoding="utf-8") as f:
            session = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(session, dict):
        return None
    guardado = session.get("token")
    session["token"] = almacen.descifrar(guardado)
    if not session["token"]:
        # No se puede descifrar (la carpeta viene de otro PC u otro usuario de Windows): toca volver a entrar.
        return None
    if not almacen.es_cifrado(guardado):
        # Sesión guardada por una versión anterior, sin cifrar: se cifra ya.
        try:
            save_session(session)
        except OSError:
            pass
    return session


def save_session(session):
    # El token da acceso a tu cuenta de Aules: en disco va cifrado, solo tu usuario de Windows puede leerlo.
    guardar = dict(session, token=almacen.cifrar(session.get("token") or ""))
    write_atomic(SESSION_PATH, json.dumps(guardar, ensure_ascii=False, indent=2))


def clear_session():
    if os.path.exists(SESSION_PATH):
        os.remove(SESSION_PATH)


_dpapi = almacen.dpapi


def _ruta_credencial(session):
    return os.path.join(carpeta(session), "credencial.bin")


def guardar_contrasena(session, password):
    os.makedirs(carpeta(session), exist_ok=True)
    write_atomic(_ruta_credencial(session), _dpapi(password.encode("utf-8"), cifrar=True))


def leer_contrasena(session):
    try:
        with open(_ruta_credencial(session), "rb") as f:
            return _dpapi(f.read(), cifrar=False).decode("utf-8")
    except (OSError, ValueError):
        return None


def borrar_contrasena(session):
    try:
        os.remove(_ruta_credencial(session))
    except OSError:
        pass


def sesion_caducada(session):
    """Aules invalidó el token: vuelve a entrar con la contraseña guardada o, si no hay, cierra la sesión."""
    password = leer_contrasena(session)
    if password:
        try:
            nueva = login(session["username"], password, session.get("base_url") or DEFAULT_BASE_URL)
            log("Sesión de Aules renovada automáticamente")
            return nueva
        except LoginError:
            # La contraseña cambió en Aules: la guardada ya no sirve.
            borrar_contrasena(session)
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
    if r.status_code == 503:
        try:
            _comprobar_mantenimiento(r)
        except AulesEnMantenimiento:
            raise LoginError("Aules está en mantenimiento ahora mismo. Prueba a entrar dentro de un rato.") from None
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
    with _limite_aules:
        r = http.post(f"{base_url}/webservice/rest/server.php", data=payload, timeout=30)
    _comprobar_mantenimiento(r)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("exception"):
        if data.get("errorcode") == "invalidtoken":
            raise SessionExpired(data.get("message"))
        raise RuntimeError(f"{wsfunction}: {data.get('message')}")
    return data


def login(username, password, base_url=DEFAULT_BASE_URL):
    if base_url not in {url for _, url in PORTALES.values()}:
        raise LoginError("Elige una etapa de la lista.")
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


def es_gva(base_url):
    """Tareas "GVA", calendario del centro, horario de Tutoría y correos @edu.gva.es son cosas de Aules (GVA)."""
    return not base_url or (urlparse(base_url).hostname or "") == "aules.edu.gva.es"


# ---------- inicio de sesión por navegador (UACloud, de la Universidad de Alicante) ----------
# Su Moodle no acepta usuario y contraseña: se entra con el SSO de la universidad. Se hace como la app oficial de Moodle:
# se abre en el navegador launch.php con un «passport» secreto; al terminar de identificarte, Moodle redirige a
# «esquema://token=BASE64» y Windows le pasa ese enlace a esta app. La app no ve nunca la contraseña de la universidad.

# Moodle fuerza este esquema en el enlace de vuelta (ajuste tool_mobile/forcedurlscheme, que viene por defecto con este valor)
# y se salta el que pida la app: pedir uno propio no sirve y el navegador se queda sin abrir nada.
ESQUEMA_SSO = "moodlemobile"
ESQUEMA_ANTIGUO = "aulesapp"  # el que usó la 1.10.0 sin éxito: se limpia al registrar el bueno
ESQUEMA_ANTERIOR_PATH = os.path.join(BASE_DIR, "esquema_anterior.json")
SSO_PENDIENTES_PATH = os.path.join(BASE_DIR, "sso_pendientes.json")
SSO_CADUCA_SEGUNDOS = 15 * 60  # lo que Moodle recuerda los datos del inicio de sesión
RE_TOKEN_SSO = re.compile(r"token=([A-Za-z0-9+/=%_\- ]{20,4000})")
_sso_lock = threading.Lock()


class LoginSsoError(LoginError):
    """Un fallo del inicio de sesión por navegador. `ident` dice de qué intento era, si se sabe."""

    def __init__(self, mensaje, ident=""):
        super().__init__(mensaje)
        self.ident = ident


def sso_id(passport):
    return hashlib.sha256(passport.encode("utf-8")).hexdigest()[:16]


def _sso_pendientes():
    try:
        with open(SSO_PENDIENTES_PATH, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    ahora = datetime.now().timestamp()
    return {p: d for p, d in datos.items() if isinstance(d, dict) and ahora - d.get("ts", 0) < SSO_CADUCA_SEGUNDOS}


def sso_iniciar(base_url):
    """Prepara un inicio de sesión por navegador. Devuelve (id del intento, enlace que hay que abrir en el navegador)."""
    if base_url not in {PORTALES[c][1] for c in PORTALES_SSO}:
        raise LoginError("Esta etapa no entra con UACloud.")
    passport = secrets.token_hex(16)
    with _sso_lock:
        pendientes = _sso_pendientes()
        pendientes[passport] = {"base_url": base_url, "ts": datetime.now().timestamp()}
        write_atomic(SSO_PENDIENTES_PATH, json.dumps(pendientes))
    parametros = urlencode({"service": "moodle_mobile_app", "passport": passport, "urlscheme": ESQUEMA_SSO})
    return sso_id(passport), f"{base_url}/admin/tool/mobile/launch.php?{parametros}"


def sso_enlace_alternativo(enlace):
    """El mismo enlace de inicio, pidiéndole a Moodle que al terminar enseñe una página con el enlace de vuelta a la vista
    en vez de redirigir sin más. Sirve para copiarlo y pegarlo en la app si el navegador no la abre solo, sea cual sea
    el esquema que use esa universidad."""
    return enlace + "&confirmed=1"


def sso_leer_enlace(texto):
    """Del enlace de vuelta («aulesapp://token=…») saca el identificador del sitio y el token de Moodle."""
    encontrado = RE_TOKEN_SSO.search((texto or "").strip())
    if not encontrado:
        raise LoginSsoError("Ese enlace no lleva el acceso de UACloud: tiene que ser como «moodlemobile://token=…».")
    # Moodle no codifica el base64: los navegadores pueden cambiar «+» por un espacio o «=» por «%3D».
    crudo = unquote(encontrado.group(1)).strip().replace(" ", "+")
    try:
        datos = base64.b64decode(crudo + "=" * (-len(crudo) % 4), validate=True).decode("utf-8")
    except ValueError:  # base64 mal formado o texto que no es UTF-8
        raise LoginSsoError("El enlace de UACloud está incompleto o dañado. Cópialo entero y vuelve a pegarlo.") from None
    partes = datos.split(":::")
    if len(partes) < 2 or not re.fullmatch(r"[0-9a-f]{32}", partes[0]) or not partes[1].strip():
        raise LoginSsoError("El enlace de UACloud no tiene el formato que esperaba esta app.")
    return partes[0], partes[1].strip()


def sso_completar(enlace):
    """Termina un inicio de sesión por navegador con el enlace de vuelta. Devuelve (sesión, id del intento)."""
    siteid, token = sso_leer_enlace(enlace)
    # Moodle firma el enlace con md5(dirección del sitio + passport): solo vale si es de un intento que empezó esta app.
    with _sso_lock:
        pendientes = _sso_pendientes()
        passport = next((p for p, d in pendientes.items()
                         if hashlib.md5((d["base_url"] + p).encode("utf-8"), usedforsecurity=False).hexdigest() == siteid), None)
        if passport is None:
            raise LoginSsoError("Ese enlace no es de un inicio de sesión que haya empezado esta app, o ya ha caducado. "
                                "Vuelve a pulsar «Entrar con UACloud».")
        base_url = pendientes[passport]["base_url"]
    ident = sso_id(passport)
    try:
        info = call_ws(base_url, token, "core_webservice_get_site_info")
    except SessionExpired:
        raise LoginSsoError("UACloud ha devuelto un acceso que Moodle no acepta. Vuelve a intentarlo.", ident) from None
    except RuntimeError as e:
        raise LoginSsoError(f"Moodle no ha dejado entrar: {e}", ident) from None
    username = (info.get("username") or "").strip() or str(info.get("userid") or "")
    if not username:
        raise LoginSsoError("Moodle no ha dicho quién eres. Vuelve a intentarlo.", ident)
    session = {
        "base_url": base_url,
        "username": username,
        "token": token,
        "fullname": info.get("fullname") or username,
        "firstname": info.get("firstname", ""),
        "acceso": "uacloud",
    }
    save_session(session)
    with _sso_lock:  # el passport es de un solo uso
        pendientes = _sso_pendientes()
        pendientes.pop(passport, None)
        write_atomic(SSO_PENDIENTES_PATH, json.dumps(pendientes))
    log(f"Sesión iniciada por UACloud como {username}")
    return session, ident


def comando_esquema():
    """La orden que Windows ejecuta cuando el navegador abre «aulesapp://…»."""
    python = sys.executable
    sin_consola = python[: -len("python.exe")] + "pythonw.exe" if python.lower().endswith("python.exe") else python
    if os.path.exists(sin_consola):
        python = sin_consola
    return f'"{python}" "{os.path.join(BASE_DIR, "servidor.py")}" --sso "%1"'


def _clave_esquema(esquema):
    return rf"Software\Classes\{esquema}"


def _valor_registro(registro, ruta, nombre=None):
    """Un valor de HKCU, o None si no existe. Sin nombre, el valor predeterminado de la clave."""
    try:
        with registro.OpenKey(registro.HKEY_CURRENT_USER, ruta) as clave:
            return registro.QueryValue(clave, None) if nombre is None else registro.QueryValueEx(clave, nombre)[0]
    except OSError:
        return None


def _borrar_esquema(registro, esquema):
    raiz = _clave_esquema(esquema)
    for sub in (r"\shell\open\command", r"\shell\open", r"\shell", ""):  # de dentro afuera: Windows no borra claves con hijos
        try:
            registro.DeleteKey(registro.HKEY_CURRENT_USER, raiz + sub)
        except OSError:
            pass


def _es_nuestro(comando):
    return bool(comando) and "servidor.py" in comando and "--sso" in comando


def _escribir_esquema(registro, esquema, comando, descripcion="URL:Aules"):
    raiz = _clave_esquema(esquema)
    with registro.CreateKey(registro.HKEY_CURRENT_USER, raiz) as clave:
        registro.SetValue(clave, "", registro.REG_SZ, descripcion)
        registro.SetValueEx(clave, "URL Protocol", 0, registro.REG_SZ, "")
    with registro.CreateKey(registro.HKEY_CURRENT_USER, rf"{raiz}\shell\open\command") as clave:
        registro.SetValue(clave, "", registro.REG_SZ, comando)


def sso_registrar_esquema(registro=None):
    """Da de alta «moodlemobile://» en Windows solo para este usuario (HKCU, sin administrador). Es lo que permite que el
    navegador le devuelva a la app el acceso. Si otra aplicación (la de Moodle) lo tenía en HKCU, se apunta para devolvérselo
    al quitar el nuestro. Devuelve True si ha escrito algo y False si ya estaba bien."""
    if registro is None:
        import winreg as registro
    comando = comando_esquema()
    raiz = _clave_esquema(ESQUEMA_SSO)
    actual = _valor_registro(registro, rf"{raiz}\shell\open\command")
    # La 1.10.0 dejó registrado «aulesapp», que Moodle nunca usa: se limpia (solo si es nuestro).
    if _es_nuestro(_valor_registro(registro, rf"{_clave_esquema(ESQUEMA_ANTIGUO)}\shell\open\command")):
        _borrar_esquema(registro, ESQUEMA_ANTIGUO)
    if actual == comando:
        return False
    if actual and not _es_nuestro(actual):
        previo = {"comando": actual, "descripcion": _valor_registro(registro, raiz) or "",
                  "protocolo": _valor_registro(registro, raiz, "URL Protocol") is not None}
        write_atomic(ESQUEMA_ANTERIOR_PATH, json.dumps(previo))
    _escribir_esquema(registro, ESQUEMA_SSO, comando)
    log(f"Registrado el enlace {ESQUEMA_SSO}:// para el inicio de sesión con UACloud")
    return True


def sso_quitar_esquema(registro=None):
    """Quita el enlace de Windows de esta app y devuelve el que había antes, si había. Lo llama el desinstalador.
    Devuelve True si había uno nuestro. Nunca toca el de otra aplicación."""
    if registro is None:
        import winreg as registro
    if _es_nuestro(_valor_registro(registro, rf"{_clave_esquema(ESQUEMA_ANTIGUO)}\shell\open\command")):
        _borrar_esquema(registro, ESQUEMA_ANTIGUO)
    if not _es_nuestro(_valor_registro(registro, rf"{_clave_esquema(ESQUEMA_SSO)}\shell\open\command")):
        return False
    _borrar_esquema(registro, ESQUEMA_SSO)
    try:
        with open(ESQUEMA_ANTERIOR_PATH, "r", encoding="utf-8") as f:
            previo = json.load(f)
        _escribir_esquema(registro, ESQUEMA_SSO, previo["comando"], previo.get("descripcion", ""))
        os.remove(ESQUEMA_ANTERIOR_PATH)
    except (OSError, ValueError, KeyError):
        pass  # no había otro que devolver
    return True


def _rutas_foto(session):
    acc_dir = carpeta(session)
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


_enunciados_leidos = {}


def _texto_enunciado(ruta):
    """Leer un PDF o Word cuesta (unos 2 s en cada revisión): se guarda ya leído y solo se relee si el archivo cambia."""
    try:
        info = os.stat(ruta)
    except OSError:
        return ia.extraer_texto(ruta, ENUNCIADO_MAX_CHARS + 1)
    clave = (ruta, info.st_mtime_ns, info.st_size)
    if clave not in _enunciados_leidos:
        _enunciados_leidos[clave] = ia.extraer_texto(ruta, ENUNCIADO_MAX_CHARS + 1)
    return _enunciados_leidos[clave]


def leer_enunciado_de_archivos(ctx, item):
    """Muchos profes dejan el enunciado dentro del PDF o Word adjunto, no en la descripción."""
    if item["summary"] or not item["attachments"]:
        return
    for adjunto in item["attachments"][:2]:
        ruta = os.path.join(ctx.acc_dir, adjunto["path"])
        texto = _texto_enunciado(ruta)
        if len(texto) > ENUNCIADO_MAX_CHARS:
            # Se corta al final de un párrafo, no a mitad de palabra.
            corte = texto.rfind("\n\n", 0, ENUNCIADO_MAX_CHARS)
            texto = texto[:corte if corte > 0 else ENUNCIADO_MAX_CHARS].rstrip() + "\n\n[…] El enunciado sigue en el archivo."
        if texto and len(texto) > 40:
            item["summary_file"] = texto
            item["summary_file_name"] = adjunto["filename"]
            return


def fetch_assignments(ctx, module):
    # Pedir todas las asignaturas juntas tarda lo mismo que pedirlas una detrás de otra (unos 12 s):
    # por separado y a la vez, tarda lo que la más lenta.
    respuestas = en_paralelo(lambda cid: ctx.ws(f"mod_{module}_get_assignments", {"courseids[0]": cid}),
                             ctx.course_params.values())
    pares = [(course, a) for data in respuestas for course in data.get("courses", []) for a in course.get("assignments", [])]

    def leer(par):
        course, a = par
        course_name = ctx.course_names.get(course["id"], course.get("fullname", "?"))
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
        return item

    return en_paralelo(leer, pares)


def fetch_quizzes(ctx):
    data = ctx.ws("mod_quiz_get_quizzes_by_courses", ctx.course_params)
    now_ts = datetime.now().timestamp()

    def leer(q):
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
        return item

    return en_paralelo(leer, data.get("quizzes", []))


# ---------- revisión de cuestionarios terminados: preguntas, tus respuestas y las correctas ----------
# Aules da cada pregunta como el HTML de su página de revisión: se lee con el lector de HTML de Python
# (sin librerías extra) y se convierte en datos limpios. Lo que el profe no deja ver (la respuesta correcta,
# por ejemplo) simplemente no viene.

VERSION_LECTOR_REVISION = 3
_revisiones_fallidas = {}


def _guardar_imagen_revision(session, carpeta_destino):
    """Descarga una imagen de una pregunta (con tu sesión) para verla en la app, también sin conexión.
    Solo de Aules: el token nunca se manda a otra web."""
    base = session["base_url"]

    def guardar(url):
        url = html.unescape(url or "")
        for prefijo in (f"{base}/pluginfile.php/", f"{base}/webservice/pluginfile.php/"):
            if url.startswith(prefijo):
                ruta = url[len(prefijo):]
                break
        else:
            return ""
        nombre = hashlib.sha1(ruta.encode("utf-8")).hexdigest()[:16] + (os.path.splitext(ruta.split("?")[0])[1].lower()[:6] or ".img")
        destino = os.path.join(carpeta_destino, nombre)
        if not os.path.exists(destino):
            try:
                sep = "&" if "?" in ruta else "?"
                r = http.get(f"{base}/webservice/pluginfile.php/{ruta}{sep}token={session['token']}", timeout=60)
                r.raise_for_status()
                if not r.headers.get("Content-Type", "").startswith("image/"):
                    return ""
                os.makedirs(carpeta_destino, exist_ok=True)
                write_atomic(destino, r.content)
            except Exception as e:
                log(f"No se pudo descargar una imagen de un cuestionario: {e}")
                return ""
        return os.path.relpath(destino, os.path.join(carpeta(session), "adjuntos")).replace(os.sep, "/")

    return guardar


def revision_cuestionario(session, quiz_id):
    """Las preguntas de tus intentos terminados de un cuestionario, con lo que respondiste y, si el profe lo deja ver,
    la respuesta correcta. Se guarda: un intento terminado no cambia, así que luego se ve al momento y sin conexión."""
    quizid = int(str(quiz_id).split("_", 1)[1])
    acc_dir = carpeta(session)
    ruta = os.path.join(acc_dir, "revisiones", f"quiz_{quizid}.json")
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            guardada = json.load(f)
    except (OSError, ValueError):
        guardada = {}
    base, token = session["base_url"], session["token"]
    try:
        intentos = call_ws(base, token, "mod_quiz_get_user_attempts", {"quizid": quizid, "status": "finished"}).get("attempts", [])
    except SessionExpired:
        raise
    except requests.RequestException:
        if guardada.get("intentos"):  # sin internet: se sirve lo que guardaste
            return dict(guardada, guardado_local=True, offline=True)
        raise
    except Exception:
        # El cuestionario ya no responde (el profe lo quitó o lo cerró). Si lo guardaste, se sirve lo guardado.
        if guardada.get("intentos"):
            return dict(guardada, guardado_local=True)
        raise
    firma = [VERSION_LECTOR_REVISION] + [[a["id"], a.get("timemodified") or a.get("timefinish") or 0] for a in intentos]
    if guardada.get("firma") == firma:
        return guardada

    guardar_imagen = _guardar_imagen_revision(session, os.path.join(acc_dir, "adjuntos", "revisiones", str(quizid)))
    resultado = {"firma": firma, "intentos": []}
    for a in sorted(intentos, key=lambda a: -(a.get("attempt") or 0)):
        intento = {"id": a["id"], "numero": a.get("attempt") or 0, "fin": a.get("timefinish") or 0, "nota": "",
                   "preguntas": [], "error": "", "url": f"{base}/mod/quiz/review.php?attempt={a['id']}"}
        try:
            rev = call_ws(base, token, "mod_quiz_get_attempt_review", {"attemptid": a["id"], "page": -1})
            if rev.get("grade") not in (None, ""):
                intento["nota"] = _numero(float(rev["grade"]))
            preguntas = sorted(rev.get("questions") or [], key=lambda q: (q.get("number") or 0, q.get("slot") or 0))
            intento["preguntas"] = [analizar_pregunta(q, guardar_imagen) for q in preguntas]
        except SessionExpired:
            raise
        except Exception as e:
            log(f"No se pudo leer la revisión del intento {a['id']}: {e}")
            intento["error"] = ("Aules no deja ver todavía las preguntas de este intento. Depende de cómo lo configuró "
                                "el profe: a veces se pueden ver cuando cierra el cuestionario.")
        resultado["intentos"].append(intento)
    # Una copia guardada completa no se reemplaza nunca por una peor: solo se reescribe si todo se ha podido releer.
    completa = bool(resultado["intentos"]) and not any(i["error"] for i in resultado["intentos"])
    if completa:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        write_atomic(ruta, json.dumps(resultado, ensure_ascii=False, indent=1))
        return resultado
    # Aules ya no deja ver todo (cerrado o quitado por el profe): se conserva y se sirve lo que guardaste cuando lo hiciste.
    if guardada.get("intentos"):
        return dict(guardada, guardado_local=True)
    return resultado


def guardar_revisiones_nuevas(session, items):
    """En segundo plano: guarda la revisión de los cuestionarios que acabas de terminar, para tenerla al momento
    (y sin conexión). Si Aules aún no la deja ver, se vuelve a probar como mucho cada 6 horas."""
    ahora = datetime.now().timestamp()
    acc_dir = carpeta(session)
    pendientes = [a for a in items if a["id"].startswith("quiz_") and a.get("done")
                  and not os.path.exists(os.path.join(acc_dir, "revisiones", f"{a['id']}.json"))
                  and ahora - _revisiones_fallidas.get(a["id"], 0) > 6 * 3600]

    def guardar(a):
        try:
            if any(i["error"] for i in revision_cuestionario(session, a["id"])["intentos"]):
                _revisiones_fallidas[a["id"]] = ahora
        except SessionExpired:
            raise
        except Exception as e:
            _revisiones_fallidas[a["id"]] = ahora
            log(f"No se pudo guardar la revisión de «{a['name']}»: {e}")

    en_paralelo(guardar, pendientes)


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
    informes = en_paralelo(lambda c: ctx.ws("gradereport_user_get_grade_items", {"courseid": c["id"], "userid": ctx.userid}),
                           courses)
    for c, data in zip(courses, informes):
        course_name = ctx.course_names.get(c["id"], c.get("fullname", "?"))
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
    # Aules no da la nota mínima para aprobar junto a la nota, pero sí en el cuestionario.
    en_paralelo(lambda n: _nota_para_aprobar(ctx, n), [n for n in notas if n["activity"].startswith("quiz_")])
    return notas


def _nota_para_aprobar(ctx, nota):
    nota["aprobar"] = ""
    try:
        minimo = ctx.ws("mod_quiz_get_user_best_grade", {"quizid": int(nota["activity"][5:])}).get("gradetopass")
        if minimo and float(minimo) > 0:
            nota["aprobar"] = _numero(float(minimo))
    except SessionExpired:
        raise
    except Exception as e:
        log(f"No se pudo leer la nota mínima de «{nota['name']}»: {e}")


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
    acc_dir = carpeta(session)
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
    acc_dir = carpeta(session)
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
        horario = obtener_horario(session, activo, carpeta(session)) if activo else None
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
    acc_dir = carpeta(session)
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
    acc_dir = carpeta(session)
    propias = cargar_propias(acc_dir)
    for x in propias:
        if x["id"] == propia_id:
            x["done"] = bool(hecha)
            _guardar_propias(acc_dir, propias)
            return x
    raise ValueError("Esa tarea ya no existe.")


def borrar_propia(session, propia_id):
    acc_dir = carpeta(session)
    propias = cargar_propias(acc_dir)
    restantes = [x for x in propias if x["id"] != propia_id]
    if len(restantes) == len(propias):
        raise ValueError("Esa tarea ya no existe.")
    _guardar_propias(acc_dir, restantes)


# ---------- calendario escolar: festivos y vacaciones ----------

VERSION_LECTOR_CALENDARIO = 2


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
    acc_dir = carpeta(session)
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
    acc_dir = carpeta(session)
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
    acc_dir = carpeta(session)
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
                # El formato de correo de la GVA no vale para otras instituciones: ahí no se deduce.
                "email_guess": "" if correo or not es_gva(ctx.base_url) else correo_deducido(u.get("firstname"), u.get("lastname")),
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
        with open(os.path.join(carpeta(session), "profesores.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"profesores": [], "otros": []}


# Ejercicios interactivos sin fecha ni entrega (HotPot, H5P, lecciones…): práctica opcional.
PRACTICE_MODULES = ("hotpot", "h5pactivity", "lesson", "scorm", "game", "hvp")


def fetch_materials(ctx, courses, practicas=None, correos=None):
    """Archivos y enlaces que cuelgan de cada curso (apuntes, sesiones, trabajos…).

    Si se pasa la lista `practicas`, se rellena con los ejercicios de práctica del mismo recorrido."""
    materiales = []
    contenidos = en_paralelo(lambda c: ctx.ws("core_course_get_contents", {"courseid": c["id"]}), courses)
    for c, secciones in zip(courses, contenidos):
        course_name = ctx.course_names.get(c["id"], c.get("fullname", "?"))
        for section in secciones:
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
        with open(os.path.join(carpeta(session), "posts.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _load_json_list(session, nombre):
    try:
        with open(os.path.join(carpeta(session), nombre), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def load_grades(session):
    return _load_json_list(session, "notas.json")


def load_messages(session):
    return _load_json_list(session, "mensajes.json")


def load_materials(session):
    try:
        with open(os.path.join(carpeta(session), "materiales.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def descargar_material(session, material):
    """Descarga (si hace falta) un archivo del curso y devuelve su ruta local."""
    destino = os.path.join(
        carpeta(session),
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
VERSION_LECTOR_HORARIO = 8


def plantilla_horario(session, material_id):
    material = next((m for m in horarios_disponibles(session) if m["id"] == material_id), None)
    if not material:
        raise RuntimeError("Ese horario ya no está en Aules.")
    return {"nombre": material["name"], "dias": horario_desde_pdf(descargar_material(session, material))}


def obtener_horario(session, material, acc_dir=None):
    """Un horario ya listo para usar; si no está guardado (o el lector ha mejorado) se lee del PDF."""
    acc_dir = acc_dir or carpeta(session)
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
    acc_dir = carpeta(session)
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
    acc_dir = carpeta(session)
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
    acc_dir = carpeta(session)
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

    progreso = {}
    materiales = practicas = None
    toca_material = (first_sync or now_ts - state.get("materiales_ts", 0) >= MATERIALS_EVERY_SECONDS
                     or not os.path.exists(os.path.join(acc_dir, "practicas.json"))
                     or not os.path.exists(os.path.join(acc_dir, "profesores.json")))
    encontradas, correos = [], {}

    def material_y_calendario():
        materiales = fetch_materials(ctx, courses, encontradas, correos)
        try:
            if es_gva(base_url):  # el calendario del centro es de los institutos de la GVA
                actualizar_calendario(session, acc_dir, materiales)
        except Exception as e:
            log(f"No se pudo leer el calendario escolar: {e}")
        return materiales

    # Cada parte es independiente: se piden todas a la vez y se tarda lo que la más lenta, no la suma.
    with ThreadPoolExecutor(7) as ex:
        f_tareas = ex.submit(fetch_assignments, ctx, "assign")
        f_gva = ex.submit(ctx.optional, "tareas GVA", lambda: fetch_assignments(ctx, "assigngva")) if es_gva(base_url) else None
        f_cuestionarios = ex.submit(ctx.optional, "cuestionarios", lambda: fetch_quizzes(ctx))
        f_foros = ex.submit(ctx.optional, "foros", lambda: fetch_forum_posts(ctx))
        f_notas = ex.submit(ctx.optional, "notas", lambda: fetch_grades(ctx, courses, progreso))
        f_mensajes = ex.submit(ctx.optional, "mensajes", lambda: fetch_messages(ctx))
        f_material = ex.submit(ctx.optional, "material de los cursos", material_y_calendario) if toca_material else None
        items = f_tareas.result() + ((f_gva.result() or []) if f_gva else []) + (f_cuestionarios.result() or [])
        posts, notas, mensajes = f_foros.result(), f_notas.result(), f_mensajes.result()
        materiales = f_material.result() if f_material else None
    if toca_material:
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
    try:
        guardar_revisiones_nuevas(session, items)
    except SessionExpired:
        pass
    except Exception as e:
        log(f"No se pudieron guardar las revisiones de los cuestionarios: {e}")


def escribir_informe(session, warnings=None, cursos=None, actualizado=None):
    """Genera la pantalla principal con lo último guardado. Sin consultar Aules, así que es instantáneo."""
    acc_dir = carpeta(session)
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
        with open(os.path.join(carpeta(session), "estado.json"), "r", encoding="utf-8") as f:
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
