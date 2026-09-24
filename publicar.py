"""Publica una versión nueva en GitHub: la app de todos los que la tienen instalada les avisará para actualizar.

Uso:   python publicar.py 1.1.0 "Qué ha cambiado" "Otro cambio"

Sube el código a la rama main con su etiqueta (v1.1.0), un version.json con la huella de cada archivo y el
instalador regenerado. Solo se sube el código: el .gitignore deja fuera cuentas/, session.json, ajustes.json...
"""
import os
import re
import subprocess
import sys

import actualizador
import crear_instalador

BASE_DIR = actualizador.BASE_DIR
PERMITIDOS = set(actualizador.ARCHIVOS) | {
    "version.json", "crear_instalador.py", "publicar.py", ".gitignore", ".gitattributes", "README.md",
    "para_compartir/Instalar Aules.bat",
}


def git(*args, comprobar=True):
    r = subprocess.run(["git", *args], cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8")
    if comprobar and r.returncode != 0:
        sys.exit(f"Falló «git {' '.join(args)}»:\n{(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


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
    print(f"Instalador para gente nueva: https://github.com/{actualizador.REPO}/raw/main/para_compartir/Instalar%20Aules.bat")


if __name__ == "__main__":
    main()
