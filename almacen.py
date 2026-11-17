"""Guardar cosas en disco de forma segura.

- Escrituras atómicas: el archivo se escribe aparte y se cambia de golpe, así nunca queda a medias. Si Windows lo
  tiene bloqueado un instante (el antivirus o el navegador leyéndolo), se espera un poco y se reintenta.
- Secretos (el token de Aules, la clave de la IA, la contraseña) cifrados con DPAPI de Windows: solo tu usuario de
  Windows en este ordenador puede descifrarlos. Si alguien copia la carpeta de la app, no le sirven de nada.
"""
import base64
import ctypes
import functools
import os
import threading
import time

PREFIJO = "dpapi:"
_ENTROPIA = b"AulesChecker"
REINTENTOS_ESCRITURA = 6  # esperas de 0,05 · 0,1 · 0,2 · 0,4 · 0,8 s: algo más de 1,5 s en total


def escribir_atomico(ruta, contenido):
    # Nombre temporal único por proceso e hilo: dos hilos que guardan el mismo archivo a la vez no se pisan.
    tmp = f"{ruta}.{os.getpid()}.{threading.get_ident()}.tmp"
    modo = "wb" if isinstance(contenido, bytes) else "w"
    with open(tmp, modo, **({} if modo == "wb" else {"encoding": "utf-8"})) as f:
        f.write(contenido)
    for intento in range(REINTENTOS_ESCRITURA):
        try:
            os.replace(tmp, ruta)
            return
        except PermissionError:
            if intento == REINTENTOS_ESCRITURA - 1:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(0.05 * 2 ** intento)


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def dpapi(datos, cifrar):
    """Cifra o descifra bytes con DPAPI de Windows (atado a tu usuario de Windows en este equipo)."""
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
        raise OSError("DPAPI no pudo procesar el dato guardado")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(salida.pbData, ctypes.c_void_p))


def es_cifrado(valor):
    return isinstance(valor, str) and valor.startswith(PREFIJO)


def cifrar(texto):
    """Texto → "dpapi:…" para guardarlo en un JSON. Lo vacío se queda vacío. Si Windows no deja cifrar (no debería
    pasar), se guarda tal cual: mejor eso que perder la sesión."""
    if not texto or es_cifrado(texto):
        return texto or ""
    try:
        return PREFIJO + base64.b64encode(dpapi(texto.encode("utf-8"), cifrar=True)).decode("ascii")
    except (OSError, AttributeError, ValueError):
        return texto


@functools.lru_cache(maxsize=16)
def _descifrar(valor):
    # Se pide en cada página (la sesión se lee siempre): así solo se descifra una vez cada valor.
    return dpapi(base64.b64decode(valor[len(PREFIJO):], validate=True), cifrar=False).decode("utf-8")


def descifrar(valor):
    """"dpapi:…" → texto. Lo guardado sin cifrar (versiones anteriores de la app) se devuelve igual. Si no se puede
    descifrar (la carpeta viene de otro PC u otro usuario de Windows) devuelve "": como si no hubiera nada guardado."""
    if not isinstance(valor, str):
        return ""
    if not es_cifrado(valor):
        return valor
    try:
        return _descifrar(valor)
    except (OSError, AttributeError, ValueError):
        return ""
