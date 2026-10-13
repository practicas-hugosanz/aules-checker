"""Publica una versión nueva en GitHub: la app de todos los que la tienen instalada les avisará para actualizar.

Uso:   python publicar.py 1.1.0 "Qué ha cambiado" "Otro cambio"

Antes de nada pasa las pruebas (pruebas.py) y comprueba que la app arranca: si algo falla, no sube nada.
Sube el código a la rama main con su etiqueta (v1.1.0), un version.json con la huella de cada archivo y el
instalador regenerado. Solo se sube el código: el .gitignore deja fuera cuentas/, session.json, ajustes.json...
Después crea la «Release» de GitHub con el instalador adjunto (si tienes GitHub CLI): es lo que busca la gente para
descargar la app, y el botón del README siempre baja la última.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

import actualizador
import crear_instalador

BASE_DIR = actualizador.BASE_DIR
PERMITIDOS = set(actualizador.ARCHIVOS) | {
    "version.json", "crear_instalador.py", "publicar.py", "pruebas.py", ".gitignore", ".gitattributes", "README.md",
    "para_compartir/Instalar Aules.bat", "docs/descargar.svg",
}
# Nombre fijo del archivo en la Release: el botón del README apunta a releases/latest/download/<este nombre>.
NOMBRE_INSTALADOR = "Instalar-Aules.bat"


def git(*args, comprobar=True):
    r = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8")
    if comprobar and r.returncode != 0:
        sys.exit(f"Falló «git {' '.join(args)}»:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def comprobar_antes_de_publicar():
    """Una versión rota dejaría a todos sin app: no se publica nada si fallan las pruebas o el arranque."""
    print("Pasando las pruebas...")
    r = subprocess.run([sys.executable, "-m", "unittest", "-q", "pruebas"], cwd=BASE_DIR, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"Fallan las pruebas, no se ha publicado nada:\n{(r.stderr or r.stdout).strip()}")
    error = actualizador.probar_codigo(BASE_DIR)
    if error:
        sys.exit(f"La app no arranca, no se ha publicado nada:\n{error}")


def buscar_gh():
    """GitHub CLI, si está instalado: en el PATH o donde lo deja winget (un terminal ya abierto no lo ve en el PATH)."""
    ruta = shutil.which("gh")
    if ruta:
        return ruta
    local = os.environ.get("LOCALAPPDATA", "")
    for patron in (os.path.join(local, "Microsoft", "WinGet", "Links", "gh.exe"),
                   os.path.join(local, "Microsoft", "WinGet", "Packages", "GitHub.cli_*", "bin", "gh.exe")):
        encontrados = glob.glob(patron)
        if encontrados:
            return encontrados[0]
    return None


def crear_release(version, cambios, instalador=None):
    """Crea la «Release» de GitHub con el instalador adjunto. Es lo que busca la gente para descargar la app y hace que
    releases/latest/download/Instalar-Aules.bat baje siempre la última. Si algo falla solo avisa: la versión ya está subida."""
    gh = buscar_gh()
    if not gh:
        print("No he creado la Release en GitHub porque falta GitHub CLI (winget install GitHub.cli y luego gh auth login). "
              "La versión sí está publicada y las apps se actualizarán igual.")
        return False
    notas = "\n".join(f"- {c}" for c in cambios) + (
        "\n\n**Instalar:** descarga `Instalar-Aules.bat` y ábrelo con doble clic. "
        "Si ya tienes la app, no hace falta: te avisa sola y se actualiza con un botón.")
    with tempfile.TemporaryDirectory() as carpeta:
        copia = os.path.join(carpeta, NOMBRE_INSTALADOR)
        shutil.copyfile(instalador or crear_instalador.SALIDA, copia)
        r = subprocess.run([gh, "release", "create", f"v{version}", copia, "--repo", actualizador.REPO,
                            "--title", f"Aules {version}", "--notes", notas, "--latest", "--verify-tag"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"No se pudo crear la Release en GitHub (¿has hecho gh auth login?): {(r.stderr or r.stdout).strip()}")
        return False
    print(f"Release creada: {r.stdout.strip()}")
    return True


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    version, cambios = sys.argv[1].lstrip("vV"), [c.strip() for c in sys.argv[2:] if c.strip()]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit("La versión tiene que ser como 1.2.0")
    if actualizador._numeros(version) < actualizador._numeros(actualizador.VERSION):
        sys.exit(f"La versión {version} es más vieja que la actual ({actualizador.VERSION}).")
    if not os.path.isdir(os.path.join(BASE_DIR, ".git")):
        sys.exit("Esta carpeta aún no es un repositorio de git.")
    if not git("remote", comprobar=False):
        sys.exit(f"Falta conectar con GitHub:  git remote add origin https://github.com/{actualizador.REPO}.git")
    if git("tag", "--list", f"v{version}"):
        sys.exit(f"La versión {version} ya está publicada: usa un número mayor.")
    comprobar_antes_de_publicar()

    # Los commits se firman con la dirección privada de GitHub, no con tu correo real.
    usuario = actualizador.REPO.split("/")[0]
    if not git("config", "user.email", comprobar=False):
        git("config", "user.name", usuario)
        git("config", "user.email", f"{usuario}@users.noreply.github.com")

    ruta = os.path.join(BASE_DIR, "actualizador.py")
    with open(ruta, "r", encoding="utf-8", newline="") as f:
        codigo = f.read()
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        f.write(re.sub(r'^VERSION = "[^"]*"', f'VERSION = "{version}"', codigo, count=1, flags=re.M))
    with open(os.path.join(BASE_DIR, "version.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(actualizador.version_json(version, cambios))
    crear_instalador.crear()

    git("add", "-A")
    subidos = set(git("diff", "--cached", "--name-only").splitlines())
    raros = subidos - PERMITIDOS
    if raros:
        git("reset", "-q")
        sys.exit(f"Se iban a subir archivos que no son código: {', '.join(sorted(raros))}. No se ha subido nada.")
    git("commit", "-q", "-m", f"Versión {version}", *[a for c in cambios for a in ("-m", f"- {c}")])
    git("tag", f"v{version}")
    print("Subiendo a GitHub (la primera vez se abre el navegador para iniciar sesión)...")
    git("push", "-q", "origin", "HEAD:main")
    git("push", "-q", "origin", f"v{version}")
    print(f"Publicada la versión {version}. Las apps instaladas lo verán en unas horas (o al reiniciarse).")
    crear_release(version, cambios)
    print(f"Instalador para gente nueva: https://github.com/{actualizador.REPO}/releases/latest/download/{NOMBRE_INSTALADOR}")


if __name__ == "__main__":
    main()
