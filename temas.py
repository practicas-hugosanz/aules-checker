"""Temas de la app: cada uno cambia colores, letra, formas y la colocación de algunas piezas.

Cada tema es CSS normal: aquí se le pone delante [data-estilo="clave"] a cada regla, así que solo se
aplica cuando <html> lleva ese tema (lo pone con_tema al servir la página, o Ajustes al elegirlo).
"""
import re

# Grupos de piezas que se repiten en casi todos los temas.
PANELES = (".stat, .ahora, .next, .course, details.forum-panel, .aviso-version, .auth-card, .mat-arbol, .mat-preview, "
           ".nota-horario, .dia, .sin-clase-lista, .profe, .dlg-propia, .menu, .otro")
BOTONES = (".icon-btn, details.account > summary, .chip, .ia-btn, .mini-btn, .anadir-curso, .atajo, .boton-p, .boton-sec, "
           ".file, .dlg-cerrar")
PRINCIPALES = ".btn-primary, .boton-apuntar, .boton-pri, .acciones-horario .principal"
CAMPOS = (".search input, .input input, .input select, .ia-cadena select, .campo-p input, .campo-p select, "
          ".campo-p textarea")

MODOS = {"auto": "Automático", "claro": "Claro", "oscuro": "Oscuro"}
_TODOS = ("auto", "claro", "oscuro")

_GOOGLE = "https://fonts.googleapis.com/css2?display=swap&family="

TEMAS = {
    "clasico": {
        "nombre": "Clásico",
        "descripcion": "El de siempre: cálido, redondeado y con un toque de rotulador.",
        "modos": _TODOS, "fuentes": "", "claro": {}, "oscuro": {}, "css": "",
    },

    "suizo": {
        "nombre": "Suizo",
        "descripcion": "Letra enorme, solo líneas finas y nada de adornos. En pantallas anchas, el menú pasa a la izquierda.",
        "modos": _TODOS,
        "fuentes": _GOOGLE + "Inter:wght@400;500;600;700;800;900",
        "claro": {
            "bg": "#ffffff", "bg-grad": "#ffffff", "card": "#ffffff", "card-2": "#f4f4f4", "text": "#111111", "muted": "#6b6b6b",
            "border": "#e2e2e2", "accent": "#e4002b", "accent-2": "#e4002b", "accent-ink": "#b80022", "accent-soft": "#ffe5ea",
            "accent-sombra": "transparent", "on-accent": "#ffffff", "rotulador": "#111111", "rotulador-ink": "#ffffff",
            "rotulador-trazo": "transparent", "ahora-bg": "#111111", "ahora-text": "#ffffff", "ahora-muted": "#9a9a9a",
            "ahora-borde": "#111111", "gray-soft": "#f2f2f2", "orange": "#e4002b", "orange-soft": "#ffe5ea",
            "display": '"Inter", system-ui, sans-serif',
        },
        "oscuro": {
            "bg": "#0d0d0d", "bg-grad": "#0d0d0d", "card": "#0d0d0d", "card-2": "#181818", "text": "#f2f2f2", "muted": "#8f8f8f",
            "border": "#2a2a2a", "accent": "#ff3b4f", "accent-2": "#ff3b4f", "accent-ink": "#ff6b7a", "accent-soft": "#3a0d14",
            "accent-sombra": "transparent", "on-accent": "#ffffff", "rotulador": "#f2f2f2", "rotulador-ink": "#0d0d0d",
            "rotulador-trazo": "transparent", "ahora-bg": "#1c1c1c", "ahora-text": "#f2f2f2", "ahora-muted": "#8f8f8f",
            "ahora-borde": "#2a2a2a", "gray-soft": "#181818", "orange": "#ff3b4f", "orange-soft": "#3a0d14",
            "display": '"Inter", system-ui, sans-serif',
        },
        "css": """
body, button, input, select, textarea { font-family: "Inter", system-ui, sans-serif; }
* { border-radius: 0 !important; box-shadow: none !important; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.wrap { max-width: 980px; }
h1 { font-weight: 900; letter-spacing: -.045em; }
.hero h1 { font-size: clamp(42px, 7.5vw, 76px); line-height: .92; }
.hero { border-bottom: 3px solid var(--text); padding-bottom: 22px; }
.rotulador { background: none; color: var(--accent); padding: 0; }
.eyebrow { text-transform: uppercase; letter-spacing: .16em; font-size: 11px; font-weight: 800; color: var(--text); }

/* Cifras: una fila de números grandes separados por líneas, sin tarjetas. */
.stats { gap: 0; margin-bottom: 28px; border-bottom: 1px solid var(--border); }
.stat { background: none !important; border: 0; border-left: 1px solid var(--border); padding: 6px 18px 20px; }
.stat:first-child { border-left: 0; padding-left: 0; }
.stat .i { display: none; }
.stat-label { text-transform: uppercase; letter-spacing: .12em; font-size: 10.5px; font-weight: 800; color: var(--muted) !important; }
.stat .stat-value { font-size: 60px; font-weight: 900; letter-spacing: -.06em; line-height: 1; color: var(--text) !important; }
.stat.exam .stat-value { color: var(--accent) !important; }
@media (max-width: 680px) { .stat:nth-child(3) { border-left: 0; padding-left: 0; } .stat .stat-value { font-size: 44px; } }

/* Bloques: sin caja, cada uno empieza con una raya gruesa. */
.course, details.forum-panel, .next, .profe, .dia, .sin-clase-lista, .aviso-version, .mat-arbol, .mat-preview, .nota-horario, .sin-horario {
  background: transparent !important; border: 0 !important; border-top: 3px solid var(--text) !important; }
.course { margin-bottom: 36px; overflow: visible; }
.course-head { padding: 14px 0 12px; border-bottom: 1px solid var(--border); }
.avatar { display: none; }
.course-name { font-size: 24px; font-weight: 800; letter-spacing: -.03em; }
.course-body { padding: 0; }
.item { padding: 16px 0; }
.item:hover, .practica:hover, .post:hover, details.group > summary:hover { background: none; }
.item::before { left: -14px; }
.item.kind-examen:not(.is-done) { background: transparent; border: 0; border-left: 4px solid var(--accent); padding-left: 14px; margin: 0; }
details.group { margin: 4px 0; }
details.group > summary { padding: 10px 0; text-transform: uppercase; letter-spacing: .1em; font-size: 11px; font-weight: 800; }
.pill { background: transparent !important; border: 1px solid currentColor; }
.pill-examen { background: var(--accent) !important; color: #fff !important; border-color: var(--accent); }
.pill-new { background: var(--text) !important; color: var(--bg) !important; border-color: var(--text); }
.next { padding: 18px 0; }
.next-icon { background: var(--accent) !important; color: #fff !important; }
.next-title { font-size: 20px; font-weight: 800; letter-spacing: -.02em; }
.ahora { border: 0; }
.ahora-tareas { background: rgba(255,255,255,.12); }
.toolbar { border-bottom: 1px solid var(--border); padding-bottom: 0; }
.chip { background: none !important; border: 0 !important; border-bottom: 3px solid transparent !important; padding: 8px 2px; margin-right: 14px;
  font-weight: 700; color: var(--muted); }
.chip.active { color: var(--text); border-bottom-color: var(--accent) !important; }
.search input { border: 0; border-bottom: 1px solid var(--text); background: transparent; }
.nav-logo { background: var(--accent); transform: none; }
.nav-links { background: none; border: 0; }
.nav-links a.activa { background: var(--text); color: var(--bg); }
.icon-btn, details.account > summary { border-color: var(--text); }
.auth-card, .menu, .dlg-propia { border: 1px solid var(--text); }
.file .ext { background: var(--text); color: var(--bg); }

/* Pantallas anchas: el menú se convierte en una columna fija a la izquierda. */
@media (min-width: 1180px) {
  body { padding-left: 220px; }
  .nav { position: fixed; left: 0; top: 0; bottom: 0; width: 220px; max-width: none; margin: 0; padding: 30px 22px;
    flex-direction: column; align-items: stretch; gap: 34px; border-right: 1px solid var(--border); background: var(--bg); z-index: 20; }
  .nav.ancha { max-width: none; }
  .nav-links { margin: 0; padding: 0; flex-direction: column; gap: 2px; overflow: visible; }
  .nav-links a { padding: 9px 0 9px 12px; border-left: 3px solid transparent; font-size: 15px; }
  .nav-links a.activa { background: none; color: var(--text); border-left-color: var(--accent); font-weight: 800; }
  .nav-links a:not(.activa) span { display: inline; }
  .nav + .wrap { padding-top: 40px; }
}
""",
    },

    "brutalista": {
        "nombre": "Brutalista",
        "descripcion": "Bordes gruesos, sombras duras y colores chillones. Las cifras van en bloques de dos.",
        "modos": _TODOS,
        "fuentes": _GOOGLE + "Space+Grotesk:wght@400;500;600;700&family=Archivo+Black",
        "claro": {
            "bg": "#fff4d6", "bg-grad": "#fff4d6", "card": "#ffffff", "card-2": "#fff9e8", "text": "#111111", "muted": "#4a4a4a",
            "border": "#111111", "accent": "#ff5470", "accent-2": "#ff5470", "accent-ink": "#111111", "accent-soft": "#ffd0d8",
            "accent-sombra": "#111111", "on-accent": "#111111", "rotulador": "#ffde4d", "rotulador-ink": "#111111",
            "rotulador-trazo": "#ffde4d", "ahora-bg": "#3d5afe", "ahora-text": "#ffffff", "ahora-muted": "#dfe4ff",
            "ahora-borde": "#111111", "gray-soft": "#f3ead0", "orange": "#ff5470", "orange-soft": "#ffd0d8",
            "ink": "#111111", "pop1": "#ffde4d", "pop2": "#00d1b2", "pop3": "#ff5470", "pop4": "#a78bfa",
            "display": '"Archivo Black", "Space Grotesk", sans-serif',
        },
        "oscuro": {
            "bg": "#16161a", "bg-grad": "#16161a", "card": "#232329", "card-2": "#2c2c33", "text": "#fffffe", "muted": "#c9c9d1",
            "border": "#fffffe", "accent": "#ff5470", "accent-2": "#ff5470", "accent-ink": "#fffffe", "accent-soft": "#4a1d27",
            "accent-sombra": "#fffffe", "on-accent": "#111111", "rotulador": "#ffde4d", "rotulador-ink": "#111111",
            "rotulador-trazo": "#ffde4d", "ahora-bg": "#3d5afe", "ahora-text": "#ffffff", "ahora-muted": "#dfe4ff",
            "ahora-borde": "#fffffe", "gray-soft": "#2c2c33", "orange": "#ff5470", "orange-soft": "#4a1d27",
            "ink": "#fffffe", "pop1": "#ffde4d", "pop2": "#00d1b2", "pop3": "#ff5470", "pop4": "#a78bfa",
            "display": '"Archivo Black", "Space Grotesk", sans-serif',
        },
        "css": """
body, button, input, select, textarea { font-family: "Space Grotesk", system-ui, sans-serif; }
h1, .course-name, .stat-value, .nav-marca, .next-title, .nota-valor, .dia-cab, .profe-nombre { font-weight: 400 !important; letter-spacing: 0; }
.hero h1 { font-size: clamp(36px, 6vw, 58px); text-transform: uppercase; line-height: 1.02; }
.rotulador { display: inline-block; background: var(--pop1); color: #111; padding: 0 .18em; border: 3px solid var(--ink);
  box-shadow: 5px 5px 0 var(--ink); transform: rotate(-2deg); }

PANELES { border: 3px solid var(--ink) !important; border-radius: 10px !important; box-shadow: 6px 6px 0 var(--ink) !important; }
BOTONES { border: 2.5px solid var(--ink) !important; border-radius: 8px !important; box-shadow: 3px 3px 0 var(--ink) !important; font-weight: 700; }
CAMPOS { border: 2.5px solid var(--ink) !important; border-radius: 8px !important; box-shadow: 3px 3px 0 var(--ink) !important; }
PRINCIPALES { background: var(--pop3) !important; color: #111 !important; border: 2.5px solid var(--ink) !important; border-radius: 8px !important;
  box-shadow: 4px 4px 0 var(--ink) !important; font-weight: 700; }
.btn-primary:active, .boton-apuntar:active, .boton-pri:active, .chip:active, .icon-btn:active, .ia-btn:active {
  transform: translate(3px, 3px) !important; box-shadow: 0 0 0 var(--ink) !important; }

/* Cifras: bloques de colores en dos columnas, con el número a la derecha. */
.stats { grid-template-columns: repeat(2, 1fr); gap: 18px; margin-bottom: 26px; }
.stat { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 20px; }
.stat-value { font-size: 52px; margin: 0; line-height: 1; }
.stat .stat-value, .stat .i, .stat-label { color: #111 !important; }
.stat-label { font-size: 15px; font-weight: 700; }
.stat:nth-child(1) { background: var(--pop3) !important; transform: rotate(-1.2deg); }
.stat:nth-child(2) { background: var(--pop1) !important; transform: rotate(.8deg); }
.stat:nth-child(3) { background: var(--pop2) !important; transform: rotate(.6deg); }
.stat:nth-child(4) { background: var(--pop4) !important; transform: rotate(-.9deg); }
@media (max-width: 480px) { .stats { grid-template-columns: 1fr; } }

.course { overflow: hidden; }
.course-head { background: hsl(var(--hue) 90% 74%); border-bottom: 3px solid var(--ink); }
.course-name, .course-meta { color: #111; }
.avatar { background: #fff !important; color: #111 !important; border: 2.5px solid #111; border-radius: 50% !important; }
.anadir-curso { background: #fff !important; color: #111 !important; border-color: #111 !important; box-shadow: 3px 3px 0 #111 !important; }
.item + .item, .post + .post, .practica + .practica, .nota + .nota { border-top: 2px dashed var(--ink); }
.item.kind-examen:not(.is-done) { background: var(--accent-soft); border: 2.5px solid var(--ink) !important; border-radius: 8px;
  box-shadow: 3px 3px 0 var(--ink) !important; margin: 8px 0; }
.pill { border: 2px solid var(--ink); border-radius: 6px; color: var(--text) !important; }
.pill-examen { background: var(--pop3) !important; color: #111 !important; }
.pill-new { background: var(--pop1) !important; color: #111 !important; }
.pill-aprobado, .pill-done { background: var(--pop2) !important; color: #111 !important; }
.due-rel { border: 2px solid var(--ink); }
.chip.active { background: var(--pop1) !important; color: #111 !important; }
.next { background: var(--pop2) !important; }
.next-title, .next-label, .next-course, .next-due .due-abs { color: #111 !important; }
.next-icon { background: #fff !important; color: #111 !important; border: 2.5px solid #111; }
.next-due .due-rel { background: #fff !important; color: #111 !important; border-color: #111; }
.nav-links { border: 2.5px solid var(--ink); box-shadow: 3px 3px 0 var(--ink); }
.nav-links a.activa { background: var(--pop1); color: #111; }
.nav-logo { background: var(--pop3); color: #111; border: 2.5px solid var(--ink); }
.file .ext { background: var(--pop1); color: #111; border: 1.5px solid #111; }
.nota-valor { color: var(--text) !important; }
footer { font-weight: 700; text-transform: uppercase; letter-spacing: .1em; }
""",
    },

    "terminal": {
        "nombre": "Terminal",
        "descripcion": "Pantalla de ordenador antiguo: letra de máquina, verde fósforo y las cifras como un listado.",
        "modos": ("oscuro",),
        "fuentes": _GOOGLE + "JetBrains+Mono:wght@400;500;700;800",
        "claro": {
            "bg": "#0a0e0a", "bg-grad": "#0a0e0a", "card": "#0d130e", "card-2": "#111a12", "text": "#b6f5b0", "muted": "#5f9563",
            "border": "#1f3a22", "accent": "#39ff6a", "accent-2": "#39ff6a", "accent-ink": "#39ff6a", "accent-soft": "#0f2a14",
            "accent-sombra": "transparent", "on-accent": "#0a0e0a", "rotulador": "#ffcc33", "rotulador-ink": "#0a0e0a",
            "rotulador-trazo": "transparent", "ahora-bg": "#0d130e", "ahora-text": "#b6f5b0", "ahora-muted": "#5f9563",
            "ahora-borde": "#1f3a22", "gray-soft": "#111a12", "red": "#ff5f56", "red-soft": "#2a0f0d", "amber": "#ffcc33",
            "amber-soft": "#2a230c", "green": "#39ff6a", "green-soft": "#0f2a14", "blue": "#5ccfe6", "blue-soft": "#0c2229",
            "orange": "#ffcc33", "orange-soft": "#2a230c", "display": '"JetBrains Mono", ui-monospace, Consolas, monospace',
        },
        "css": """
body, button, input, select, textarea { font-family: "JetBrains Mono", ui-monospace, Consolas, monospace !important; }
body { font-size: 14px; }
body::after { content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 100;
  background: repeating-linear-gradient(0deg, rgba(0,0,0,.22) 0 1px, transparent 1px 3px); }
* { border-radius: 0 !important; box-shadow: none !important; }
:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
::selection { background: var(--accent); color: var(--bg); }
a { color: var(--accent); }
h1, .stat-value, .nota-valor, .course-name, .next-title { text-shadow: 0 0 8px rgba(57,255,106,.35); }
h1 { font-weight: 800; letter-spacing: -.02em; }
.hero h1 { font-size: clamp(24px, 4.4vw, 36px); }
.hero h1::before { content: "> "; color: var(--muted); }
.hero h1::after { content: "_"; color: var(--accent); animation: term-cursor 1s steps(1) infinite; }
@keyframes term-cursor { 50% { opacity: 0; } }
.rotulador { background: none; color: var(--rotulador); padding: 0; }
.eyebrow::before { content: "// "; }
.eyebrow { color: var(--muted); }

PANELES { background: transparent !important; border: 1px solid var(--border) !important; }
.menu, .dlg-propia { background: var(--bg) !important; border-color: var(--accent) !important; }
BOTONES { background: transparent !important; border: 1px solid var(--border) !important; }
CAMPOS { background: transparent !important; border: 1px solid var(--border) !important; }
PRINCIPALES { background: var(--accent) !important; color: var(--bg) !important; font-weight: 700; }
.course-head { border-bottom: 1px dashed var(--border); }
.course-name::before { content: "## "; color: var(--muted); }
.course-name { font-size: 15px; }
.avatar { display: none; }

/* Cifras: un listado con puntos de relleno, como un informe de consola. */
.stats { grid-template-columns: 1fr 1fr; column-gap: 28px; row-gap: 0; padding: 10px 16px; border: 1px solid var(--border); }
.stat { border: 0 !important; background: none !important; display: flex; align-items: baseline; gap: 0; padding: 3px 0; }
.stat .i { display: none; }
.stat-label { flex: 1; display: flex; font-size: 13px; color: var(--muted) !important; }
.stat-label::after { content: ""; flex: 1; border-bottom: 1px dotted var(--muted); margin: 0 8px 4px; opacity: .6; }
.stat-value { font-size: 18px; margin: 0; color: var(--accent) !important; }
.stat.exam .stat-value { color: var(--rotulador) !important; }
@media (max-width: 680px) { .stats { grid-template-columns: 1fr; } }

.pill { background: none !important; border: 0; padding: 0; letter-spacing: 0; font-weight: 700; }
.pill::before { content: "["; } .pill::after { content: "]"; }
.pill .i { display: none; }
.pill-examen { color: var(--amber) !important; }
.pill-tarea { color: var(--blue) !important; }
.pill-new { color: var(--accent) !important; }
.item + .item, .post + .post, .practica + .practica, .nota + .nota { border-top: 1px dashed var(--border); }
.item:hover { background: var(--card-2); }
.item.kind-examen:not(.is-done) { background: var(--amber-soft); border: 0; border-left: 2px solid var(--amber); }
.due-rel { background: none !important; padding: 0 !important; }
.next-due .due-rel { color: var(--accent) !important; }
.urg-urgent .due-rel { color: var(--red) !important; }
.chip.active { background: var(--accent) !important; color: var(--bg) !important; border-color: var(--accent) !important; }
.nav-links { background: none; border: 0; }
.nav-links a::before { content: "["; } .nav-links a::after { content: "]"; }
.nav-links a.activa { background: var(--accent); color: var(--bg); }
.nav-logo { background: none; color: var(--accent); border: 1px solid var(--accent); transform: none; }
.next { border-color: var(--accent) !important; }
.next-icon { background: none !important; color: var(--accent) !important; border: 1px solid var(--accent); }
.ahora-label { color: var(--rotulador); }
.ahora-tareas { background: none; border: 1px solid var(--border); }
.file .ext { background: none; color: var(--accent); border: 1px solid var(--accent); }
.toolbar { background: var(--bg); }
""",
    },

    "cuaderno": {
        "nombre": "Cuaderno",
        "descripcion": "Hoja de libreta con renglones, post-its, cinta adhesiva y letra a mano.",
        "modos": ("claro",),
        "fuentes": _GOOGLE + "Caveat:wght@600;700&family=Nunito:wght@400;600;700;800",
        "claro": {
            "bg": "#f7f3e8", "bg-grad": "#f7f3e8", "card": "#fffdf7", "card-2": "#fbf7ec", "text": "#23324d", "muted": "#66718a",
            "border": "#dcd4c0", "accent": "#2251c7", "accent-2": "#2251c7", "accent-ink": "#1a3f9e", "accent-soft": "#e1e8fb",
            "accent-sombra": "#1a3f9e", "on-accent": "#ffffff", "rotulador": "#fff27a", "rotulador-ink": "#4d4500",
            "rotulador-trazo": "#fff27a", "ahora-bg": "#2e4a3b", "ahora-text": "#f4f1e6", "ahora-muted": "#b9c9bc",
            "ahora-borde": "#8b5e34", "gray-soft": "#efe9d8", "red": "#d6402b", "red-soft": "#fde3dc",
            "orange": "#d6402b", "orange-soft": "#fde3dc", "display": '"Caveat", cursive',
        },
        "css": """
body, button, input, select, textarea { font-family: "Nunito", system-ui, sans-serif; }
body { background-color: var(--bg); background-image: repeating-linear-gradient(transparent 0 31px, rgba(34,81,199,.13) 31px 32px); }
.wrap { position: relative; }
.wrap::before { content: ""; position: absolute; top: 0; bottom: 0; left: 4px; width: 2px; background: rgba(214,64,43,.35); }
h1, .course-name, .stat-value, .nav-marca, .next-title, .dia-cab, .profe-nombre, .nota-valor, .ahora-asig {
  font-family: "Caveat", cursive !important; font-weight: 700; letter-spacing: 0; }
.hero h1 { font-size: clamp(46px, 7.5vw, 68px); line-height: 1; }
.course-name { font-size: 27px; line-height: 1.1; }
.next-title { font-size: 25px; }
.ahora-asig { font-size: 27px !important; }
.nota-valor { font-size: 28px; color: var(--red) !important; }
.rotulador { background: linear-gradient(100deg, transparent 2%, var(--rotulador) 5% 95%, transparent 98%); padding: 0 .25em; }

PANELES { border: 1px solid var(--border) !important; border-radius: 3px !important;
  box-shadow: 0 1px 1px rgba(0,0,0,.05), 0 8px 18px -6px rgba(70,55,20,.18) !important; }
.course { position: relative; overflow: visible; margin-top: 26px; }
.course::before { content: ""; position: absolute; top: -12px; left: 50%; width: 96px; height: 24px; transform: translateX(-50%) rotate(-2deg);
  background: rgba(255,236,150,.75); border-left: 1px dashed rgba(0,0,0,.08); border-right: 1px dashed rgba(0,0,0,.08); }
.course:nth-of-type(even)::before { transform: translateX(-30%) rotate(3deg); background: rgba(190,225,255,.75); }
.avatar { border-radius: 50% !important; }

/* Cifras: post-its de colores, cada uno un poco torcido. */
.stats { gap: 16px; margin-bottom: 26px; }
.stat { border: 0 !important; border-radius: 2px !important; padding: 16px 18px 20px; box-shadow: 0 12px 18px -10px rgba(0,0,0,.35) !important; }
.stat:nth-child(1) { background: #ffd1dc !important; transform: rotate(-2deg); }
.stat:nth-child(2) { background: #fff27a !important; transform: rotate(1.5deg); }
.stat:nth-child(3) { background: #c8f0d2 !important; transform: rotate(-1deg); }
.stat:nth-child(4) { background: #cfe3ff !important; transform: rotate(2deg); }
.stat .stat-value, .stat .i, .stat-label { color: #23324d !important; }
.stat-value { font-size: 50px; line-height: 1; }

/* Formas de dibujo a mano. */
.pill, .chip, PRINCIPALES, .icon-btn, details.account > summary, .ia-btn, .due-rel {
  border-radius: 255px 15px 225px 15px / 15px 225px 15px 255px !important; }
.pill { background: transparent !important; border: 1.5px solid currentColor; text-transform: none; letter-spacing: 0; font-weight: 800; }
.pill-examen { color: var(--red) !important; }
.chip { background: transparent; border: 1.5px solid var(--text); }
.chip.active { background: var(--text); color: var(--bg); }
PRINCIPALES { box-shadow: none !important; border: 2px solid var(--accent-ink) !important; }
.item + .item, .post + .post, .practica + .practica, .nota + .nota { border-top: 1px dashed var(--border); }
.item.kind-examen:not(.is-done) { background: rgba(255,242,122,.5); border: 0; box-shadow: none !important; border-left: 3px solid var(--red); border-radius: 2px; }
.next { box-shadow: inset 4px 0 0 var(--red), 0 8px 18px -6px rgba(70,55,20,.18) !important; }
.next-label { color: var(--red); }
.ahora:not(.sin-horario) { border: 7px solid var(--ahora-borde) !important; border-radius: 4px !important; }
.ahora:not(.sin-horario) .ahora-label { color: #fff27a; }
.nav-links { background: transparent; border: 0; }
.nav-links a.activa { background: none; color: var(--accent); text-decoration: underline wavy var(--red); text-underline-offset: 6px; font-weight: 800; }
.nav-logo { font-family: "Caveat", cursive; font-size: 22px; background: var(--rotulador); color: var(--text); }
.file .ext { background: #fff27a; color: var(--text); }
""",
    },

    "cristal": {
        "nombre": "Cristal",
        "descripcion": "Fondo de colores con paneles de vidrio translúcido. La cabecera y el menú van centrados.",
        "modos": ("oscuro",),
        "fuentes": _GOOGLE + "Outfit:wght@400;500;600;700;800",
        "claro": {
            "bg": "#0b1020", "bg-grad": "#0b1020", "card": "rgba(255,255,255,.07)", "card-2": "rgba(255,255,255,.06)",
            "text": "#f5f7ff", "muted": "#aab3d1", "border": "rgba(255,255,255,.14)", "accent": "#7cc4ff", "accent-2": "#b388ff",
            "accent-ink": "#a8d8ff", "accent-soft": "rgba(124,196,255,.16)", "accent-sombra": "transparent", "on-accent": "#0b1020",
            "rotulador": "#ff9ad5", "rotulador-ink": "#2b0a1f", "rotulador-trazo": "rgba(255,154,213,.45)",
            "ahora-bg": "rgba(255,255,255,.07)", "ahora-text": "#f5f7ff", "ahora-muted": "#aab3d1", "ahora-borde": "rgba(255,255,255,.14)",
            "gray-soft": "rgba(255,255,255,.08)", "red": "#ff8a9a", "red-soft": "rgba(255,138,154,.16)", "amber": "#ffd479",
            "amber-soft": "rgba(255,212,121,.14)", "green": "#7ee2b8", "green-soft": "rgba(126,226,184,.14)", "blue": "#a5b4ff",
            "blue-soft": "rgba(165,180,255,.16)", "orange": "#7cc4ff", "orange-soft": "rgba(124,196,255,.16)",
            "av-fg": "80% 82%", "av-bg": "60% 60% / .25", "display": '"Outfit", system-ui, sans-serif',
        },
        "css": """
body, button, input, select, textarea { font-family: "Outfit", system-ui, sans-serif; }
body { background: radial-gradient(60vw 60vw at 8% -10%, #6d3cff 0, transparent 60%), radial-gradient(50vw 50vw at 100% 18%, #00a99d 0, transparent 55%),
  radial-gradient(60vw 60vw at 50% 115%, #ff4fa3 0, transparent 60%), #0b1020; background-attachment: fixed; }
h1 { font-weight: 800; letter-spacing: -.03em; }
.rotulador { background: linear-gradient(90deg, #ff9ad5, #7cc4ff); -webkit-background-clip: text; background-clip: text; color: transparent; padding: 0; }

PANELES { background: rgba(255,255,255,.07) !important; border: 1px solid rgba(255,255,255,.14) !important; border-radius: 26px !important;
  -webkit-backdrop-filter: blur(18px) saturate(140%); backdrop-filter: blur(18px) saturate(140%);
  box-shadow: 0 12px 40px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.12) !important; }
.menu, .dlg-propia { background: rgba(22,26,48,.94) !important; }
BOTONES { background: rgba(255,255,255,.08) !important; border-color: rgba(255,255,255,.16) !important; border-radius: 999px !important;
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); box-shadow: none !important; }
CAMPOS { background: rgba(255,255,255,.08) !important; border-color: rgba(255,255,255,.16) !important; }
PRINCIPALES { background: linear-gradient(135deg, #7cc4ff, #b388ff) !important; color: #0b1020 !important; border-radius: 999px !important;
  box-shadow: 0 8px 24px rgba(124,196,255,.35) !important; }

/* Todo centrado: cabecera, menú, acciones y filtros. */
.nav { flex-direction: column; gap: 12px; }
.nav-links { margin: 0; background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.14); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); }
.nav-links a.activa { background: rgba(255,255,255,.92); color: #0b1020; }
.nav-logo { background: linear-gradient(135deg, #7cc4ff, #ff9ad5); color: #0b1020; transform: none; border-radius: 50% !important; }
.hero { flex-direction: column; align-items: center; text-align: center; }
.hero .updated, .hero-actions, .chips { justify-content: center; }
.toolbar { justify-content: center; background: none; }
.stats { gap: 14px; }
.stat { text-align: center; }
.stat-label { justify-content: center; }
.stat-value { font-size: 42px; background: linear-gradient(135deg, #ffffff, var(--accent)); -webkit-background-clip: text; background-clip: text;
  color: transparent !important; }
.course-head, details.forum-panel[open] > summary { border-bottom-color: rgba(255,255,255,.1); }
.item + .item, .post + .post, .practica + .practica, .nota + .nota { border-top-color: rgba(255,255,255,.08); }
.item.kind-examen:not(.is-done) { background: rgba(124,196,255,.12); border: 0; box-shadow: inset 3px 0 0 var(--accent) !important; }
.pill-examen { background: linear-gradient(135deg, #7cc4ff, #b388ff); color: #0b1020; }
.chip.active { background: rgba(255,255,255,.92) !important; color: #0b1020 !important; }
.next-icon { background: linear-gradient(135deg, #7cc4ff, #b388ff) !important; color: #0b1020 !important; border-radius: 50% !important; }
.desc-body, .nota-fb, .ia-bloque { background: rgba(255,255,255,.05); }
""",
    },

    "retro": {
        "nombre": "Retro 95",
        "descripcion": "Ventanas grises en relieve sobre un escritorio verde azulado, con el menú como barra de tareas abajo.",
        "modos": ("claro",),
        "fuentes": _GOOGLE + "VT323",
        "claro": {
            "bg": "#008080", "bg-grad": "#008080", "card": "#c0c0c0", "card-2": "#d4d0c8", "text": "#000000", "muted": "#404040",
            "border": "#808080", "accent": "#000080", "accent-2": "#1084d0", "accent-ink": "#000080", "accent-soft": "#c8d0f0",
            "accent-sombra": "transparent", "on-accent": "#ffffff", "rotulador": "#ffff00", "rotulador-ink": "#000000",
            "rotulador-trazo": "#ffff00", "ahora-bg": "#000000", "ahora-text": "#c0c0c0", "ahora-muted": "#808080",
            "ahora-borde": "#000000", "gray-soft": "#d4d0c8", "red": "#c00000", "red-soft": "#ffd0d0", "amber": "#806000",
            "amber-soft": "#ffffc0", "green": "#006000", "green-soft": "#c8f0c8", "blue": "#000080", "blue-soft": "#c8d0f0",
            "orange": "#000080", "orange-soft": "#c8d0f0", "av-fg": "100% 22%", "av-bg": "55% 80%",
            "relieve": "#ffffff #404040 #404040 #ffffff", "hundido": "#808080 #ffffff #ffffff #808080",
            "display": '"VT323", ui-monospace, monospace',
        },
        "css": """
body, button, input, select, textarea { font-family: Tahoma, Verdana, "Segoe UI", sans-serif; }
body { font-size: 14px; padding-bottom: 60px; }
* { border-radius: 0 !important; }
:focus-visible { outline: 1px dotted #000; outline-offset: -4px; }
::selection { background: #000080; color: #fff; }
a { color: #000080; }
h1, .stat-value, .nota-valor { font-family: "VT323", ui-monospace, monospace; font-weight: 400 !important; letter-spacing: 0; }
.hero h1, .mat-top h1, .ajustes-cab h1 { font-size: clamp(44px, 6.5vw, 64px); line-height: 1; color: #fff; text-shadow: 3px 3px 0 #000; }
.auth-card h1 { color: #000; text-shadow: none; font-size: 34px; }
.hero .eyebrow, .hero .updated, footer, .empty { color: #fff !important; }
.rotulador { background: none; color: #ffff00; padding: 0; }
.course-name, .next-title, .ahora-asig, .dia-cab, .profe-nombre, .nav-marca { font-family: Tahoma, Verdana, "Segoe UI", sans-serif !important; letter-spacing: 0; }

/* Ventanas y botones en relieve. */
PANELES { background: #c0c0c0 !important; color: #000; border: 2px solid !important; border-color: var(--relieve) !important;
  box-shadow: inset -1px -1px #808080, inset 1px 1px #dfdfdf !important; }
BOTONES, PRINCIPALES { background: #c0c0c0 !important; color: #000 !important; border: 2px solid !important; border-color: var(--relieve) !important;
  box-shadow: inset -1px -1px #808080, inset 1px 1px #dfdfdf !important; transform: none !important; filter: none !important; }
.btn-primary:active, .boton-apuntar:active, .boton-pri:active, .chip:active, .icon-btn:active, .ia-btn:active, .chip.active {
  border-color: var(--hundido) !important; box-shadow: inset 1px 1px #404040 !important; }
.chip.active { background: #d4d0c8 !important; font-weight: 700; }
CAMPOS { background: #fff !important; color: #000; border: 2px solid !important; border-color: var(--hundido) !important;
  box-shadow: inset 1px 1px #404040 !important; }

/* Cada asignatura es una ventana con su barra de título. */
.course { padding: 3px; }
.course-head { background: linear-gradient(90deg, #000080, #1084d0); padding: 3px 4px 3px 6px; border: 0; gap: 8px; }
.course-name { color: #fff; font-size: 14px; font-weight: 700; }
.course-meta { color: #dfe8ff; font-size: 12px; }
.avatar { width: 20px; height: 20px; font-size: 9px; }
.anadir-curso { padding: 1px 8px; }
.course-head::after { content: "✕"; flex: none; width: 20px; height: 18px; display: grid; place-items: center; font-size: 11px; font-weight: 700;
  color: #000; background: #c0c0c0; border: 2px solid; border-color: var(--relieve); }
.item + .item, .post + .post, .practica + .practica, .nota + .nota { border-top: 1px solid #808080; box-shadow: inset 0 1px #fff; }
.item:hover, .practica:hover, .post:hover { background: #d4d0c8; }
.item.kind-examen:not(.is-done) { background: #ffffc0; border: 1px solid #000; box-shadow: none !important; }

/* Cifras: ventanitas con su título. */
.stat { padding: 3px 3px 10px; }
.stat-label { background: linear-gradient(90deg, #000080, #1084d0); color: #fff !important; font-weight: 700; padding: 2px 6px; margin-bottom: 4px; }
.stat-label .i { color: #fff !important; }
.stat-value { font-size: 46px; color: #000 !important; padding: 0 8px; }
.next-icon { background: #000080 !important; color: #fff !important; }
.next-label { color: #000080; }
.ahora:not(.sin-horario) { background: #000 !important; color: #c0c0c0; border-color: var(--hundido) !important; }
.ahora:not(.sin-horario) .ahora-asig { font-family: "VT323", monospace !important; font-size: 28px; font-weight: 400; color: #00ff66 !important; }

.pill { background: #fff !important; color: #000 !important; border: 1px solid #000; }
.pill-examen { background: #000080 !important; color: #fff !important; }
.pill-new { background: #ffff00 !important; }
.pill-aprobado, .pill-done { background: #c8f0c8 !important; }
.pill-suspendido { background: #ffd0d0 !important; }
.due-rel { background: #fff !important; color: #000 !important; border: 1px solid #808080; padding: 1px 8px !important; }
.file .ext { background: #000080; color: #fff; }

/* El menú es la barra de tareas, abajo del todo. */
.nav { position: fixed; left: 0; right: 0; bottom: 0; max-width: none !important; margin: 0; padding: 4px 6px; z-index: 50; gap: 6px;
  background: #c0c0c0; border-top: 2px solid #fff; box-shadow: inset 0 1px #dfdfdf; }
.nav + .wrap { padding-top: 34px; }
.nav + .mat-wrap { height: calc(100vh - 56px); padding-top: 12px; }
.nav + .auth { padding-top: 34px; }
.nav-marca { font-family: Tahoma, sans-serif; font-size: 14px; font-weight: 700; color: #000; padding: 3px 10px 3px 6px; gap: 6px;
  border: 2px solid; border-color: var(--relieve); box-shadow: inset -1px -1px #808080, inset 1px 1px #dfdfdf; }
.nav-marca .nav-txt { display: inline !important; }
.nav-logo { width: 18px; height: 18px; transform: none !important; color: transparent;
  background: conic-gradient(#ff3b30 0 25%, #34c759 0 50%, #0a84ff 0 75%, #ffcc00 0); }
.nav-links { margin-left: 0; background: none; border: 0; padding: 0; gap: 4px; }
.nav-links a { color: #000; padding: 3px 12px; border: 2px solid; border-color: var(--relieve); box-shadow: inset -1px -1px #808080, inset 1px 1px #dfdfdf; }
.nav-links a.activa { background: #e0e0e0; color: #000; font-weight: 700; border-color: var(--hundido); box-shadow: inset 1px 1px #404040; }
""",
    },
}

# Vista previa de cada tema en Ajustes: un dibujo pequeño con su estética.
PREVIAS_CSS = """
.pv { display: block; height: 86px; padding: 9px; position: relative; overflow: hidden; border-radius: 10px; border: 1px solid var(--border); }
.pv-h { display: block; height: 9px; width: 58%; margin-bottom: 8px; }
.pv-s { display: flex; gap: 5px; margin-bottom: 8px; }
.pv-s i { flex: 1; height: 16px; }
.pv-c { display: flex; align-items: center; gap: 6px; padding: 7px; }
.pv-c b { flex: 1; height: 5px; }
.pv-c u { width: 20px; height: 8px; }
.pv[data-t="clasico"] { background: #f6f2ea; }
.pv[data-t="clasico"] .pv-h { background: #221f1a; border-radius: 4px; }
.pv[data-t="clasico"] .pv-s i { border-radius: 5px; background: #ffe3d8; } .pv[data-t="clasico"] .pv-s i + i { background: #dcefe4; }
.pv[data-t="clasico"] .pv-c { background: #fff; border-radius: 8px; } .pv[data-t="clasico"] .pv-c b { background: #d8cfc2; border-radius: 3px; }
.pv[data-t="clasico"] .pv-c u { background: #ee5a2c; border-radius: 9px; }
.pv[data-t="suizo"] { background: #fff; border-radius: 0; }
.pv[data-t="suizo"] .pv-h { background: #111; height: 13px; width: 72%; }
.pv[data-t="suizo"] .pv-s i { height: 12px; border-left: 1px solid #ddd; background: linear-gradient(#111, #111) 4px 2px / 50% 8px no-repeat; }
.pv[data-t="suizo"] .pv-s i:first-child { border: 0; background: linear-gradient(#e4002b, #e4002b) 0 2px / 50% 8px no-repeat; }
.pv[data-t="suizo"] .pv-c { border-top: 3px solid #111; padding: 6px 0; } .pv[data-t="suizo"] .pv-c b { background: #ccc; }
.pv[data-t="suizo"] .pv-c u { background: #e4002b; }
.pv[data-t="brutalista"] { background: #fff4d6; }
.pv[data-t="brutalista"] .pv-h { background: #111; transform: rotate(-2deg); }
.pv[data-t="brutalista"] .pv-s i { border: 2px solid #111; box-shadow: 2px 2px 0 #111; background: #ff5470; border-radius: 3px; }
.pv[data-t="brutalista"] .pv-s i + i { background: #ffde4d; } .pv[data-t="brutalista"] .pv-s i + i + i { background: #00d1b2; }
.pv[data-t="brutalista"] .pv-c { background: #fff; border: 2px solid #111; box-shadow: 3px 3px 0 #111; border-radius: 4px; }
.pv[data-t="brutalista"] .pv-c b { background: #111; } .pv[data-t="brutalista"] .pv-c u { background: #ffde4d; border: 1.5px solid #111; }
.pv[data-t="terminal"] { background: #0a0e0a; border-radius: 0; }
.pv[data-t="terminal"] .pv-h { background: #39ff6a; width: 45%; box-shadow: 0 0 8px rgba(57,255,106,.6); }
.pv[data-t="terminal"] .pv-s i { height: 10px; border-bottom: 1px dotted #5f9563; }
.pv[data-t="terminal"] .pv-c { border: 1px solid #1f3a22; } .pv[data-t="terminal"] .pv-c b { background: #b6f5b0; opacity: .6; }
.pv[data-t="terminal"] .pv-c u { background: #ffcc33; }
.pv[data-t="cuaderno"] { background: #f7f3e8 repeating-linear-gradient(transparent 0 11px, rgba(34,81,199,.18) 11px 12px); }
.pv[data-t="cuaderno"] .pv-h { background: #23324d; border-radius: 255px 15px 225px 15px / 15px 225px 15px 255px; }
.pv[data-t="cuaderno"] .pv-s i { background: #ffd1dc; transform: rotate(-3deg); box-shadow: 0 4px 6px -3px rgba(0,0,0,.3); }
.pv[data-t="cuaderno"] .pv-s i + i { background: #fff27a; transform: rotate(2deg); }
.pv[data-t="cuaderno"] .pv-s i + i + i { background: #c8f0d2; transform: rotate(-1deg); }
.pv[data-t="cuaderno"] .pv-c { background: #fffdf7; box-shadow: 0 4px 8px -4px rgba(0,0,0,.25); } .pv[data-t="cuaderno"] .pv-c b { background: #23324d; opacity: .35; }
.pv[data-t="cuaderno"] .pv-c u { border: 1.5px solid #d6402b; border-radius: 255px 15px 225px 15px / 15px 225px 15px 255px; }
.pv[data-t="cristal"] { background: radial-gradient(circle at 10% 0, #6d3cff, transparent 60%), radial-gradient(circle at 100% 30%, #00a99d, transparent 55%),
  radial-gradient(circle at 50% 120%, #ff4fa3, transparent 60%), #0b1020; }
.pv[data-t="cristal"] .pv-h { background: #fff; margin: 0 auto 8px; border-radius: 9px; }
.pv[data-t="cristal"] .pv-s i { background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.25); border-radius: 7px; }
.pv[data-t="cristal"] .pv-c { background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); border-radius: 12px; }
.pv[data-t="cristal"] .pv-c b { background: rgba(255,255,255,.6); border-radius: 3px; }
.pv[data-t="cristal"] .pv-c u { background: linear-gradient(135deg, #7cc4ff, #b388ff); border-radius: 9px; }
.pv[data-t="retro"] { background: #008080; border-radius: 0; }
.pv[data-t="retro"] .pv-h { background: #fff; box-shadow: 2px 2px 0 #000; }
.pv[data-t="retro"] .pv-s i { background: #c0c0c0; border: 2px solid; border-color: #fff #404040 #404040 #fff; box-shadow: inset 0 4px #000080; }
.pv[data-t="retro"] .pv-c { background: #c0c0c0; border: 2px solid; border-color: #fff #404040 #404040 #fff; box-shadow: inset 0 6px #000080; padding-top: 10px; }
.pv[data-t="retro"] .pv-c b { background: #404040; } .pv[data-t="retro"] .pv-c u { background: #000080; }
"""


def _dividir(selectores):
    """Separa por comas, sin romper lo que va entre paréntesis (:not(...), :has(...))."""
    partes, nivel, actual = [], 0, ""
    for c in selectores:
        nivel += (c == "(") - (c == ")")
        if c == "," and nivel == 0:
            partes.append(actual.strip())
            actual = ""
        else:
            actual += c
    return partes + [actual.strip()] if actual.strip() else partes


def _selector(prefijo, s):
    if s.startswith(":root"):
        return ":root" + prefijo + s[5:]
    return f"{prefijo} {s}"


def _prefijar(prefijo, css):
    salida, i = [], 0
    while True:
        j = css.find("{", i)
        if j == -1:
            break
        nivel, k = 1, j + 1
        while nivel:
            nivel += (css[k] == "{") - (css[k] == "}")
            k += 1
        cabeza, cuerpo = css[i:j].strip(), css[j + 1:k - 1]
        if cabeza.startswith(("@media", "@supports")):
            salida.append(f"{cabeza} {{\n{_prefijar(prefijo, cuerpo)}\n}}")
        elif cabeza.startswith("@"):
            salida.append(f"{cabeza} {{{cuerpo}}}")
        else:
            salida.append(", ".join(_selector(prefijo, s) for s in _dividir(cabeza)) + " {" + cuerpo + "}")
        i = k
    return "\n".join(salida)


def _variables(colores):
    return " ".join(f"--{k}: {v};" for k, v in colores.items())


def _css_tema(clave, tema):
    prefijo = f'[data-estilo="{clave}"]'
    partes = []
    if tema["claro"]:
        partes.append(f":root{prefijo} {{ {_variables(tema['claro'])} }}")
    if tema.get("oscuro"):
        assert set(tema["oscuro"]) == set(tema["claro"]), f"El tema {clave} no tiene las mismas variables en claro y oscuro"
        oscuro = _variables(tema["oscuro"])
        partes.append(f':root{prefijo}[data-modo="oscuro"] {{ {oscuro} }}')
        partes.append(f'@media (prefers-color-scheme: dark) {{ :root{prefijo}:not([data-modo="claro"]) {{ {oscuro} }} }}')
    css = re.sub(r"/\*.*?\*/", "", tema["css"], flags=re.S)
    for nombre, lista in (("PANELES", PANELES), ("BOTONES", BOTONES), ("PRINCIPALES", PRINCIPALES), ("CAMPOS", CAMPOS)):
        css = css.replace(nombre, lista)
    partes.append(_prefijar(prefijo, css))
    return "\n".join(partes)


TEMAS_CSS = "\n".join(_css_tema(clave, tema) for clave, tema in TEMAS.items())


def elegido(ajustes):
    """El tema y el modo que hay que aplicar. Un tema con un solo modo lo impone."""
    clave = ajustes.get("estilo") if ajustes.get("estilo") in TEMAS else "clasico"
    modos = TEMAS[clave]["modos"]
    modo = ajustes.get("modo") if ajustes.get("modo") in modos else modos[0]
    return clave, modo


def con_tema(pagina, ajustes):
    """Pone en <html> el tema y el modo elegidos, y carga su tipografía (también en la pantalla principal, que se guarda ya hecha)."""
    clave, modo = elegido(ajustes)
    pagina = pagina.replace('<html lang="es">', f'<html lang="es" data-estilo="{clave}" data-modo="{modo}">', 1)
    if TEMAS[clave]["fuentes"]:
        pagina = pagina.replace("</head>", f'<link rel="stylesheet" href="{TEMAS[clave]["fuentes"]}">\n</head>', 1)
    return pagina
