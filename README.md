<h1 align="center">Aules</h1>

<p align="center">
  Tus tareas, exámenes, notas y horario de Aules en una sola página,<br>
  con avisos en Windows cuando hay algo nuevo.
</p>

<p align="center">
  <a href="https://github.com/practicas-hugosanz/aules-checker/releases/latest/download/Instalar-Aules.bat">
    <img src="docs/descargar.svg" alt="Descargar Aules para Windows" width="420">
  </a>
</p>

<p align="center">
  <sub>Windows 10 y 11 · gratis · no necesita permisos de administrador ·
  <a href="https://github.com/practicas-hugosanz/aules-checker/releases/latest">ver todas las versiones</a></sub>
</p>

## Instalar en 3 pasos

1. **Descarga** el instalador con el botón de arriba (`Instalar-Aules.bat`).
2. **Ábrelo** con doble clic: lo encuentras en la carpeta *Descargas* o en el aviso de descarga del navegador. Se abre una ventana negra que va diciendo lo que hace; **no la cierres hasta que termine** (tarda unos minutos la primera vez).
3. **Inicia sesión** con tu usuario de Aules cuando la app se abra en el navegador, y elige tu etapa.

Ya está. Se queda revisando Aules en segundo plano y te avisa de lo nuevo cada vez que enciendes el ordenador. Si no tienes Python, el instalador lo instala por ti.

### Si Windows o el navegador te avisan

Es normal: el instalador no está firmado por una empresa (eso cuesta dinero), así que el navegador y Windows desconfían de cualquier archivo `.bat` que se baja de internet. Es un archivo de texto que puedes abrir con el Bloc de notas para ver lo que hace, y todo el código de la app está publicado en este repositorio.

| Cuándo | Qué te dice | Qué hacer |
|---|---|---|
| Al descargar, en Chrome o Edge | Que el archivo no se descarga habitualmente o que puede ser peligroso | Elige **Conservar** (en Edge, los tres puntos → **Conservar** → **Conservar de todos modos**) |
| Al abrir el instalador | «Windows protegió su PC» | Pulsa **Más información** y luego **Ejecutar de todas formas** |

### ¿Ya la tienes instalada?

No hace falta que descargues nada: la app te avisa cuando hay una versión nueva, con la lista de cambios y un botón **Actualizar**.

## Qué hace

Sirve para **FP presencial, Bachillerato, ESO (Valencia, Alicante y Castellón), FP semipresencial y Personas adultas**: al iniciar sesión eliges tu etapa.

- **Todo en una página:** tareas y exámenes pendientes de todas tus asignaturas, ordenados por fecha, con su enunciado (si viene en un PDF, lo ves directamente), notas, mensajes, foros y material.
- **Avisos en Windows:** tareas, exámenes, notas, mensajes y material nuevos, y cuando un profe cambia una tarea (fecha, prórroga, descripción o archivos).
- **Recordatorios:** antes de cada entrega y examen, y un resumen por la mañana con lo que vence hoy y mañana.
- **Entregar desde la app:** eliges los archivos, ves un resumen de lo que se envía y confirmas.
- **¿Cuánto llevo?:** tu media en cada asignatura y lo que te falta para el 5, cuando los pesos de las notas lo permiten.
- **Repasar cuestionarios:** las preguntas de los tests que ya has hecho, lo que respondiste y, si el profe lo deja ver, la respuesta correcta.
- **Horario:** la clase de ahora y la siguiente, leído del PDF de horario de Tutoría.
- **Tareas propias:** apunta lo que se dice en clase y no está en Aules.
- **Temas:** siete estilos para la app (Clásico, Suizo, Brutalista, Terminal, Cuaderno, Cristal y Retro 95), en claro u oscuro.
- **IA opcional:** resumen de cada tarea y borradores, con tu propia clave de un proveedor de IA.

## Actualizaciones

Cuando haya una versión nueva, la app te avisará con la lista de cambios y un botón «Actualizar». Antes de instalarla, la prueba en tu ordenador: si no arranca, no se instala y tu app sigue igual. Tus datos y ajustes se mantienen.

## Privacidad

Todo se queda en tu PC. La contraseña solo se guarda, cifrada con tu usuario de Windows, si marcas la casilla al iniciar sesión.

Tu usuario, tu contraseña y tus datos de Aules solo se envían a Aules. La app también consulta este repositorio de GitHub para saber si hay una versión nueva (solo lee, no envía nada), y al abrir la página el navegador pide las tipografías a Google Fonts. Si configuras la IA, el enunciado de una tarea solo se manda a tu proveedor cuando pulsas «Resumen IA» o «Hacer borrador».

## Desinstalar

Abre `%LOCALAPPDATA%\AulesApp` y haz doble clic en `DESINSTALAR.bat`.
