"""Genera «para_compartir/Instalar Aules.bat»: un único archivo que instala la app con doble clic.

Solo mete el código. Nunca incluye cuentas/, session.json, ajustes.json ni run.log (tus datos y claves).
Vuelve a ejecutarlo después de cambiar la app para compartir la versión nueva:  python crear_instalador.py
"""
import base64
import io
import os
import zipfile

from actualizador import ARCHIVOS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(BASE_DIR, "para_compartir", "Instalar Aules.bat")
CODIGO = ARCHIVOS
MARCA = "::PAQUETE::"

# Solo ASCII en los .bat: cmd lee el archivo antes de poder cambiar a UTF-8.
INSTALADOR = r"""@echo off
setlocal EnableExtensions
title Instalando Aules
set "DEST=%LOCALAPPDATA%\AulesApp"
if defined AULES_PRUEBA set "DEST=%AULES_PRUEBA%"
set "INSTALADOR=%~f0"
echo.
echo   =============================================
echo     AULES  -  tareas, notas y horario de Aules
echo   =============================================
echo.

echo   [1/5] Buscando Python 3.12 o superior...
set "PY="
call :buscar_python
if not defined PY (
  echo         No esta instalado. Instalandolo, puede tardar un par de minutos...
  where winget >nul 2>nul && winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements >nul
  call :buscar_python
)
if not defined PY (
  echo.
  echo   No se pudo instalar Python automaticamente.
  echo   Se abrira la web de Python: descargalo, instalalo marcando
  echo   "Add python.exe to PATH" y vuelve a abrir este instalador.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

echo   [2/5] Copiando la app...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name like 'python%%'\" | Where-Object { $_.CommandLine -like ('*' + $env:DEST + '*servidor.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
if not exist "%DEST%" mkdir "%DEST%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t = [IO.File]::ReadAllText($env:INSTALADOR); $m = '::PAQ' + 'UETE::'; $b = [Convert]::FromBase64String($t.Substring($t.LastIndexOf($m) + $m.Length).Trim()); $z = Join-Path $env:TEMP 'aules_paquete.zip'; [IO.File]::WriteAllBytes($z, $b); Expand-Archive -Path $z -DestinationPath $env:DEST -Force; Remove-Item $z"
if not exist "%DEST%\servidor.py" (
  echo   No se pudo descomprimir la app.
  pause
  exit /b 1
)

echo   [3/5] Instalando lo que necesita (la primera vez tarda un poco)...
if not exist "%DEST%\.venv\Scripts\pythonw.exe" %PY% -m venv "%DEST%\.venv"
"%DEST%\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r "%DEST%\requirements.txt"
if errorlevel 1 (
  echo   Fallo la instalacion de dependencias. Comprueba la conexion a internet y vuelve a probar.
  pause
  exit /b 1
)

if defined AULES_PRUEBA goto fin
echo   [4/5] Creando accesos directos...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = New-Object -ComObject WScript.Shell; $pyw = Join-Path $env:DEST '.venv\Scripts\pythonw.exe'; $app = '\"' + (Join-Path $env:DEST 'servidor.py') + '\"'; foreach ($d in @(@([Environment]::GetFolderPath('Desktop'), 'Aules.lnk', ''), @([Environment]::GetFolderPath('Programs'), 'Aules.lnk', ''), @([Environment]::GetFolderPath('Startup'), 'Aules (segundo plano).lnk', ' --sin-navegador'))) { $l = $s.CreateShortcut((Join-Path $d[0] $d[1])); $l.TargetPath = $pyw; $l.Arguments = $app + $d[2]; $l.WorkingDirectory = $env:DEST; $l.Description = 'Aules: tareas, notas y horario'; $l.Save() }"

echo   [5/5] Abriendo Aules...
start "" "%DEST%\.venv\Scripts\pythonw.exe" "%DEST%\servidor.py"
echo.
echo   Listo. Se abrira en el navegador: inicia sesion con tu usuario de Aules.
echo   - Tienes un acceso directo "Aules" en el escritorio.
echo   - Se abre sola en segundo plano al encender el PC y te avisa de todo.
echo   - Para quitarla: DESINSTALAR.bat en %DEST%
echo.
timeout /t 12
:fin
exit /b 0

:buscar_python
for %%C in ("py -3.13" "py -3.12" "python") do (
  if not defined PY %%~C -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul && set "PY=%%~C"
)
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe") do (
  if not defined PY if exist %%P set "PY=%%P"
)
exit /b 0
"""

DESINSTALADOR = r"""@echo off
setlocal EnableExtensions
title Desinstalar Aules
rem Se ejecuta desde una copia temporal para poder borrar su propia carpeta.
if /i not "%~dp0"=="%TEMP%\" (
  copy /y "%~f0" "%TEMP%\desinstalar_aules.bat" >nul
  "%TEMP%\desinstalar_aules.bat" "%~dp0"
  exit /b
)
set "DEST=%~1"
if "%DEST:~-1%"=="\" set "DEST=%DEST:~0,-1%"
echo.
echo   Se va a quitar Aules de este equipo, junto con tus datos guardados en
echo   %DEST%
echo   (sesion, contrasena cifrada, notas, horario y archivos descargados).
echo.
choice /c SN /m "  Quieres continuar"
if errorlevel 2 exit /b 0
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name like 'python%%'\" | Where-Object { $_.CommandLine -like ('*' + $env:DEST + '*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
powershell -NoProfile -Command "foreach ($p in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Aules.lnk'), (Join-Path ([Environment]::GetFolderPath('Programs')) 'Aules.lnk'), (Join-Path ([Environment]::GetFolderPath('Startup')) 'Aules (segundo plano).lnk'))) { Remove-Item -LiteralPath $p -ErrorAction SilentlyContinue }"
timeout /t 2 >nul
rmdir /s /q "%DEST%"
echo.
echo   Aules se ha desinstalado.
timeout /t 6
"""

LEEME = """AULES - tareas, notas y horario de Aules FP sin entrar en la web
=================================================================

Que hace
- Te avisa de tareas, examenes, notas, mensajes y foros nuevos de Aules.
- Recordatorios antes de cada entrega y examen, y un resumen por la tarde.
- Horario con la clase de ahora y la siguiente (lo lee del PDF de Tutoria).
- Materiales con vista previa, correos de profesores y tareas que apuntas tu.
- Opcional: resumen y borradores con IA usando tu propia clave.

Instalar
- Doble clic en "Instalar Aules.bat". Si Windows avisa de que protegio el
  equipo, pulsa "Mas informacion" y luego "Ejecutar de todas formas".
- Se instala en tu carpeta de usuario (no necesita administrador).

Actualizaciones
- Cuando haya una version nueva, la app te lo dira arriba con la lista de
  cambios y un boton "Actualizar". Tus datos y ajustes se mantienen.

Privacidad
- Todo se queda en tu PC. La contrasena solo se guarda (cifrada con tu usuario
  de Windows) si marcas la casilla al iniciar sesion.

Desinstalar
- Abre %LOCALAPPDATA%\\AulesApp y haz doble clic en DESINSTALAR.bat.
"""


def crear():
    paquete = io.BytesIO()
    with zipfile.ZipFile(paquete, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre in CODIGO:
            z.write(os.path.join(BASE_DIR, nombre), nombre)
        z.writestr("DESINSTALAR.bat", DESINSTALADOR.replace("\n", "\r\n"))
        z.writestr("LEEME.txt", LEEME.replace("\n", "\r\n"))
    datos = base64.b64encode(paquete.getvalue()).decode("ascii")
    lineas = "\r\n".join(datos[i:i + 76] for i in range(0, len(datos), 76))
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="ascii", newline="") as f:
        f.write(INSTALADOR.replace("\n", "\r\n") + "\r\n" + MARCA + "\r\n" + lineas + "\r\n")
    print(f"Creado: {SALIDA} ({os.path.getsize(SALIDA) // 1024} KB)")


if __name__ == "__main__":
    crear()
