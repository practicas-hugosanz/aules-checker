"""Actualizaciones desde GitHub: avisa de que hay una versión nueva y la instala solo si pulsas «Actualizar».

Lee version.json de la rama principal del repositorio y descarga los archivos de la etiqueta de esa
versión, comprobando la huella SHA-256 de cada uno antes de tocar nada. Solo sustituye el código:
tus cuentas, contraseña, ajustes y marcas no se tocan.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import requests

VERSION = "1.8.3"
# Usuario y repositorio de GitHub de donde salen las versiones nuevas.
REPO = "practicas-hugosanz/aules-checker"
RAMA = "main"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Lo que se publica y se actualiza. Nunca datos: nada de cuentas/, session.json ni ajustes.json.
ARCHIVOS = ("aules_checker.py", "servidor.py", "interfaz.py", "temas.py", "ia.py", "actualizador.py", "requirements.txt")
NOMBRE_VALIDO = re.compile(r"^[a-z_]+\.(py|txt)$")
HUELLA_VALIDA = re.compile(r"^[0-9a-f]{64}$")
COMPROBAR_CADA_SEGUNDOS = 6 * 3600
# Copia de la versión anterior, para volver a ella si la nueva no arranca.
CARPETA_ANTERIOR = os.path.join(BASE_DIR, "anterior")
CARPETA_PRUEBA = os.path.join(BASE_DIR, ".actualizacion")

# Se ejecuta en otro proceso dentro de la carpeta a probar: carga todo el código y genera las pantallas
# principales sin abrir el servidor ni conectarse a Aules.
PRUEBA_ARRANQUE = r"""
import os, sys
sys.path.insert(0, os.getcwd())
import actualizador, aules_checker, ia, interfaz, servidor, temas
sesion = {"username": "prueba", "fullname": "Ana Prueba", "firstname": "Ana"}
ajustes = {"proveedor": "anthropic", "modelo": "", "api_key": "", "base_url": ""}
paginas = [interfaz.build_report([], [], sesion, [], 48), interfaz.render_login(), interfaz.render_error("prueba"),
           interfaz.render_ajustes(ajustes, ia.PROVEEDORES), interfaz.render_horario([]), interfaz.render_profesores({})]
for clave in temas.TEMAS:
    for pagina in paginas:
        assert "data-estilo" in temas.con_tema(pagina, dict(ajustes, estilo=clave))
print("ok")
"""

_nueva = None
_instalando = threading.Lock()


class ActualizacionError(Exception):
    pass


def _numeros(version):
    return tuple(int(x) for x in re.findall(r"\d+", str(version))[:3])


def es_copia_de_desarrollo():
    """La carpeta donde se programa la app (con git): avisa igual, pero se actualiza con git y nunca pisa cambios."""
    return os.path.isdir(os.path.join(BASE_DIR, ".git"))


def _url(ref, ruta):
    return f"https://raw.githubusercontent.com/{REPO}/{ref}/{ruta}"


def huella(datos):
    return hashlib.sha256(datos).hexdigest()


def buscar():
    """Pregunta a GitHub cuál es la última versión. Devuelve su información si es más nueva que esta."""
    global _nueva
    r = requests.get(_url(RAMA, "version.json"), timeout=15, headers={"Cache-Control": "no-cache"})
    if r.status_code == 404:
        _nueva = None
        return None
    r.raise_for_status()
    info = r.json()
    archivos = info.get("archivos")
    if (not isinstance(info.get("version"), str) or not _numeros(info["version"]) or not isinstance(archivos, dict)
            or not archivos or not all(NOMBRE_VALIDO.match(n) and HUELLA_VALIDA.match(str(h)) for n, h in archivos.items())):
        raise ActualizacionError("El aviso de versión nueva de GitHub no tiene el formato esperado.")
    cambios = [str(c)[:300] for c in info.get("cambios") or [] if str(c).strip()][:20]
    _nueva = dict(info, cambios=cambios) if _numeros(info["version"]) > _numeros(VERSION) else None
    return _nueva


def estado():
    nueva = _nueva
    return {
        "version": VERSION,
        "nueva": {"version": nueva["version"], "cambios": nueva["cambios"]} if nueva else None,
    }


def _python_con_consola():
    python = sys.executable
    # pythonw no tiene consola; para pip y las pruebas vale igual el python.exe de al lado.
    if python.lower().endswith("pythonw.exe") and os.path.exists(python[:-5] + ".exe"):
        python = python[:-5] + ".exe"
    return python


def probar_codigo(carpeta):
    """Comprueba que el código de esa carpeta arranca. Devuelve "" si va bien o el error si no."""
    try:
        r = subprocess.run(
            [_python_con_consola(), "-c", PRUEBA_ARRANQUE], cwd=carpeta, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"No se pudo hacer la prueba de arranque: {e}"
    if r.returncode == 0 and r.stdout.strip().endswith("ok"):
        return ""
    lineas = (r.stderr or r.stdout).strip().splitlines()
    return " | ".join(lineas[-3:]) or f"La prueba de arranque terminó con el código {r.returncode}"


def restaurar_anterior(log=print):
    """Vuelve a la versión guardada antes de la última actualización. True si había copia y se ha restaurado."""
    if es_copia_de_desarrollo() or not os.path.isdir(CARPETA_ANTERIOR):
        return False
    for nombre in os.listdir(CARPETA_ANTERIOR):
        if NOMBRE_VALIDO.match(nombre):
            shutil.copy2(os.path.join(CARPETA_ANTERIOR, nombre), os.path.join(BASE_DIR, nombre + ".nuevo"))
            os.replace(os.path.join(BASE_DIR, nombre + ".nuevo"), os.path.join(BASE_DIR, nombre))
    shutil.rmtree(CARPETA_ANTERIOR, ignore_errors=True)
    log("La versión nueva no arrancaba: se ha vuelto a la anterior")
    return True


def _pip(requisitos):
    r = subprocess.run(
        [_python_con_consola(), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", requisitos],
        capture_output=True, text=True, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if r.returncode != 0:
        raise ActualizacionError("No se pudieron instalar las librerías nuevas. Comprueba la conexión y vuelve a probar.")


def _git(*args):
    return subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _actualizar_con_git(info, log):
    """En la copia de trabajo, la versión nueva se trae con git. Solo si no hay cambios sin publicar: nunca se pisan."""
    try:
        pendientes = _git("status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ActualizacionError(f"No se pudo usar git en esta carpeta: {e}")
    if pendientes.returncode != 0:
        raise ActualizacionError("No se pudo usar git en esta carpeta.")
    if pendientes.stdout.strip():
        raise ActualizacionError("Tienes cambios sin publicar en esta carpeta. Publícalos (o guárdalos) antes de "
                                 "actualizar, para no perderlos. No se ha cambiado nada.")
    with open(os.path.join(BASE_DIR, "requirements.txt"), "rb") as f:
        requisitos = f.read()
    try:
        r = _git("pull", "--ff-only", "-q", "origin", RAMA)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ActualizacionError(f"No se pudo traer la versión nueva con git: {e}")
    if r.returncode != 0:
        detalle = (r.stderr or r.stdout).strip().splitlines()
        raise ActualizacionError("No se pudo traer la versión nueva con git" + (f": {detalle[-1]}" if detalle else "."))
    with open(os.path.join(BASE_DIR, "requirements.txt"), "rb") as f:
        if f.read() != requisitos:
            _pip(os.path.join(BASE_DIR, "requirements.txt"))
    log(f"Copia de trabajo actualizada con git a la versión {info['version']} (desde la {VERSION})")
    return {"ok": True, "version": info["version"]}


def instalar(log=print):
    """Descarga la versión nueva, comprueba cada archivo y lo sustituye. Si algo falla, no toca nada."""
    if not _instalando.acquire(blocking=False):
        raise ActualizacionError("Ya se está actualizando.")
    try:
        info = buscar()
        if not info:
            raise ActualizacionError("Ya tienes la última versión.")
        if es_copia_de_desarrollo():
            return _actualizar_con_git(info, log)
        ref = f"v{info['version']}"
        descargados = {}
        for nombre, esperada in info["archivos"].items():
            r = requests.get(_url(ref, nombre), timeout=60)
            r.raise_for_status()
            if huella(r.content) != esperada:
                raise ActualizacionError(f"«{nombre}» ha llegado dañado o no coincide con la versión publicada. No se ha cambiado nada.")
            descargados[nombre] = r.content

        # Primero las librerías: si fallan, la app sigue como estaba.
        req_actual = os.path.join(BASE_DIR, "requirements.txt")
        req_nuevo = descargados.get("requirements.txt")
        if req_nuevo is not None:
            try:
                with open(req_actual, "rb") as f:
                    igual = f.read() == req_nuevo
            except OSError:
                igual = False
            if not igual:
                temporal = req_actual + ".nuevo"
                with open(temporal, "wb") as f:
                    f.write(req_nuevo)
                try:
                    _pip(temporal)
                finally:
                    os.remove(temporal)

        # Antes de tocar nada, la versión nueva se prueba en una carpeta aparte con el resto del código actual.
        shutil.rmtree(CARPETA_PRUEBA, ignore_errors=True)
        os.makedirs(CARPETA_PRUEBA)
        try:
            for nombre in ARCHIVOS:
                if os.path.exists(os.path.join(BASE_DIR, nombre)):
                    shutil.copy2(os.path.join(BASE_DIR, nombre), CARPETA_PRUEBA)
            for nombre, datos in descargados.items():
                with open(os.path.join(CARPETA_PRUEBA, nombre), "wb") as f:
                    f.write(datos)
            error = probar_codigo(CARPETA_PRUEBA)
        finally:
            shutil.rmtree(CARPETA_PRUEBA, ignore_errors=True)
        if error:
            log(f"La versión {info['version']} no pasó la prueba de arranque: {error}")
            raise ActualizacionError("La versión nueva no arranca en este ordenador, así que no se ha instalado. Tu app sigue igual.")

        # Copia de lo que hay ahora, por si la nueva falla al reiniciar.
        shutil.rmtree(CARPETA_ANTERIOR, ignore_errors=True)
        os.makedirs(CARPETA_ANTERIOR)
        for nombre in set(ARCHIVOS) | set(descargados):
            if os.path.exists(os.path.join(BASE_DIR, nombre)):
                shutil.copy2(os.path.join(BASE_DIR, nombre), CARPETA_ANTERIOR)

        # Se escriben todos aparte y luego se cambian de golpe, servidor.py el último: al verlo cambiar, la app se reinicia.
        orden = sorted(descargados, key=lambda n: n == "servidor.py")
        for nombre in orden:
            with open(os.path.join(BASE_DIR, nombre + ".nuevo"), "wb") as f:
                f.write(descargados[nombre])
        for nombre in orden:
            os.replace(os.path.join(BASE_DIR, nombre + ".nuevo"), os.path.join(BASE_DIR, nombre))
        log(f"Actualizada a la versión {info['version']} (desde la {VERSION})")
        return {"ok": True, "version": info["version"]}
    finally:
        _instalando.release()


def vigilar(log=print):
    """Busca versiones nuevas al arrancar y cada 6 horas. Sin internet no molesta: lo reintenta más tarde."""
    time.sleep(60)
    ultimo_error = None
    while True:
        try:
            nueva = buscar()
            if nueva and ultimo_error != f"v{nueva['version']}":
                log(f"Hay una versión nueva de la app: {nueva['version']}")
                ultimo_error = f"v{nueva['version']}"
        except (requests.RequestException, ValueError, ActualizacionError) as e:
            if str(e) != ultimo_error:
                log(f"No se pudo buscar actualizaciones: {e}")
            ultimo_error = str(e)
        time.sleep(COMPROBAR_CADA_SEGUNDOS)


def version_json(version, cambios):
    """Para publicar.py: la descripción de esa versión con la huella de cada archivo."""
    archivos = {}
    for nombre in ARCHIVOS:
        with open(os.path.join(BASE_DIR, nombre), "rb") as f:
            archivos[nombre] = huella(f.read())
    return json.dumps({"version": version, "cambios": cambios, "archivos": archivos}, ensure_ascii=False, indent=2) + "\n"
