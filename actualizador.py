"""Actualizaciones desde GitHub: avisa de que hay una versión nueva y la instala solo si pulsas «Actualizar».

Lee version.json de la rama principal del repositorio y descarga los archivos de la etiqueta de esa
versión, comprobando la huella SHA-256 de cada uno antes de tocar nada. Solo sustituye el código:
tus cuentas, contraseña, ajustes y marcas no se tocan.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

import requests

VERSION = "1.1.0"
# Usuario y repositorio de GitHub de donde salen las versiones nuevas.
REPO = "practicas-hugosanz/aules-checker"
RAMA = "main"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Lo que se publica y se actualiza. Nunca datos: nada de cuentas/, session.json ni ajustes.json.
ARCHIVOS = ("aules_checker.py", "servidor.py", "interfaz.py", "ia.py", "actualizador.py", "requirements.txt")
NOMBRE_VALIDO = re.compile(r"^[a-z_]+\.(py|txt)$")
HUELLA_VALIDA = re.compile(r"^[0-9a-f]{64}$")
COMPROBAR_CADA_SEGUNDOS = 6 * 3600

_nueva = None
_instalando = threading.Lock()


class ActualizacionError(Exception):
    pass


def _numeros(version):
    return tuple(int(x) for x in re.findall(r"\d+", str(version))[:3])


def es_copia_de_desarrollo():
    """En la carpeta donde se programa la app (con git) no se actualiza sola: se machacaría el trabajo."""
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
    nueva = _nueva if _nueva and not es_copia_de_desarrollo() else None
    return {
        "version": VERSION,
        "nueva": {"version": nueva["version"], "cambios": nueva["cambios"]} if nueva else None,
    }


def _pip(requisitos):
    python = sys.executable
    # pythonw no tiene consola; para pip vale igual el python.exe de al lado.
    if python.lower().endswith("pythonw.exe") and os.path.exists(python[:-5] + ".exe"):
        python = python[:-5] + ".exe"
    r = subprocess.run(
        [python, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", requisitos],
        capture_output=True, text=True, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if r.returncode != 0:
        raise ActualizacionError("No se pudieron instalar las librerías nuevas. Comprueba la conexión y vuelve a probar.")


def instalar(log=print):
    """Descarga la versión nueva, comprueba cada archivo y lo sustituye. Si algo falla, no toca nada."""
    if es_copia_de_desarrollo():
        raise ActualizacionError("Esta es la copia donde se programa la app: se actualiza con git, no desde aquí.")
    if not _instalando.acquire(blocking=False):
        raise ActualizacionError("Ya se está actualizando.")
    try:
        info = buscar()
        if not info:
            raise ActualizacionError("Ya tienes la última versión.")
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
        if not es_copia_de_desarrollo():
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
