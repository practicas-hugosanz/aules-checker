"""Piezas que comparten todas las páginas de la app: los portales de Aules, los iconos, los colores y estilos
base, la barra de navegación, el esqueleto de cada página y utilidades de fechas y nombres."""
import hashlib
import html
import os
import re
from datetime import datetime

from temas import TEMAS_CSS


# Cada etapa tiene su propio Aules (en ESO, uno por provincia). La clave es la última parte de su dirección.
def _portales_ua(ahora=None):
    """El Moodle de la UA cambia cada curso (moodle2026-27.ua.es): se ofrece el de este curso y el del anterior."""
    ahora = ahora or datetime.now()
    inicio = ahora.year if ahora.month >= 8 else ahora.year - 1
    return {
        f"ua{a}": (f"Universidad de Alicante · {a}-{(a + 1) % 100:02d}",
                   f"https://moodle{a}-{(a + 1) % 100:02d}.ua.es/moodle")
        for a in (inicio, inicio - 1)
    }


PORTALES = {
    "fp": ("FP presencial", "https://aules.edu.gva.es/fp"),
    "batxillerat": ("Bachillerato", "https://aules.edu.gva.es/batxillerat"),
    "eso46": ("ESO · Valencia", "https://aules.edu.gva.es/eso46"),
    "eso03": ("ESO · Alicante", "https://aules.edu.gva.es/eso03"),
    "eso12": ("ESO · Castellón", "https://aules.edu.gva.es/eso12"),
    "semipresencial": ("FP semipresencial", "https://aules.edu.gva.es/semipresencial"),
    "fpa": ("Personas adultas (FPA)", "https://aules.edu.gva.es/fpa"),
    **_portales_ua(),
}

# Las etapas que no aceptan usuario y contraseña de Moodle: se entra con el SSO de la universidad (UACloud).
PORTALES_SSO = {clave for clave in PORTALES if clave.startswith("ua")}

RE_MOODLE_UA = re.compile(r"^https://moodle(\d{4})-\d{2}\.ua\.es(?:/|$)")


def portal_de(base_url):
    """Clave de la etapa a partir de la dirección de Aules ("fp" si no se reconoce)."""
    url = (base_url or "").rstrip("/")
    ua = RE_MOODLE_UA.match(url)
    if ua:
        return f"ua{ua.group(1)}"
    clave = url.rsplit("/", 1)[-1]
    return clave if clave in PORTALES and clave not in PORTALES_SSO else "fp"


def nombre_portal(clave):
    if clave in PORTALES:
        return PORTALES[clave][0]
    if clave.startswith("ua") and clave[2:].isdigit():  # un curso anterior que ya no sale en la lista
        a = int(clave[2:])
        return f"Universidad de Alicante · {a}-{(a + 1) % 100:02d}"
    return PORTALES["fp"][0]


DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

ICONS = {
    "more": '<circle cx="5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
    "palette": '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.93 0 1.65-.75 1.65-1.69 0-.44-.18-.84-.44-1.13-.29-.29-.44-.65-.44-1.13a1.64 1.64 0 0 1 1.67-1.67h2c3.05 0 5.55-2.5 5.55-5.55C21.97 6.01 17.46 2 12 2z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "monitor": '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "calendar": '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "clipboard-list": '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4M12 16h4M8 11h.01M8 16h.01"/>',
    "graduation-cap": '<path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
    "megaphone": '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    "message-square": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "sparkles": '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "pencil": '<path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
    "mail": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "eye": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "arrow-left": '<path d="m12 19-7-7 7-7M19 12H5"/>',
    "external-link": '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    "book-open": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "alert-circle": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
    "triangle-alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
    "shield-check": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    "loader": '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
    "settings": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "columnas": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M12 3v18"/>',
    "papelera": '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
}


def icon(name, size=16, cls=""):
    return (
        f'<svg class="i {cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-hidden="true">{ICONS[name]}</svg>'
    )


TONOS_ASIGNATURA = (16, 150, 42, 234)  # teja, verde, mostaza, azul


def course_hue(name):
    return TONOS_ASIGNATURA[int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % len(TONOS_ASIGNATURA)]


def initials(name):
    words = [w for w in re.split(r"\s+", name) if w and w[0].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def pretty_name(name):
    return name.title() if name.isupper() else name


def file_ext(filename):
    return (os.path.splitext(filename)[1].lstrip(".").upper() or "FILE")[:4]


# Colores del tema clásico; los demás temas (temas.py) cambian lo que necesitan.
CLARO_VARS = """
  --bg: #f6f2ea; --bg-grad: #f6f2ea; --card: #ffffff; --card-2: #fbf8f2;
  --text: #221f1a; --muted: #6f675c; --border: #e7dfd2; --shadow: 0 1px 0 rgba(60,45,20,.05), 0 8px 24px rgba(60,45,20,.06);
  --accent: #ee5a2c; --accent-2: #ee5a2c; --accent-ink: #b6401a; --accent-soft: #ffe3d8; --accent-sombra: #c2441c; --on-accent: #1a0f0a;
  --rotulador: #ffd166; --rotulador-ink: #6b4d00; --rotulador-trazo: #ffd166;
  --ahora-bg: #221f1a; --ahora-text: #f6f2ea; --ahora-muted: #bdb4a6; --ahora-borde: #221f1a;
  --red: #af3119; --red-soft: #ffe3d8; --amber: #946400; --amber-soft: #fff1c9;
  --green: #2d754f; --green-soft: #dcefe4; --blue: #4a52c9; --blue-soft: #e3e6ff;
  --orange: #ee5a2c; --orange-soft: #ffe3d8; --gray-soft: #efe9df;
  --av-fg: 55% 29%; --av-bg: 75% 91%; color-scheme: light;
"""

OSCURO_VARS = """
  --bg: #171411; --bg-grad: #171411; --card: #221e1a; --card-2: #2a2520;
  --text: #f3ede3; --muted: #a89f92; --border: #352f28; --shadow: 0 1px 0 rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.3);
  --accent: #ff7a4d; --accent-2: #ff7a4d; --accent-ink: #ff9a76; --accent-soft: #3a2319; --accent-sombra: #b8471f; --on-accent: #1a0f0a;
  --rotulador: #f2c35b; --rotulador-ink: #2a1f00; --rotulador-trazo: #b4461d;
  --ahora-bg: #2e2822; --ahora-text: #f3ede3; --ahora-muted: #a89f92; --ahora-borde: #40382f;
  --red: #ff8f7a; --red-soft: #3a2319; --amber: #f2c35b; --amber-soft: #3a3018;
  --green: #7fd0a3; --green-soft: #1e3027; --blue: #9aa2ff; --blue-soft: #262a4a;
  --orange: #ff7a4d; --orange-soft: #3a2319; --gray-soft: #2a2520;
  --av-fg: 75% 74%; --av-bg: 28% 20%; color-scheme: dark;
"""

# Modo: sin data-modo (o "auto") sigue al sistema; "claro" y "oscuro" lo fuerzan.
BASE_CSS = (
    ":root {" + CLARO_VARS + '  --display: "Bricolage Grotesque", "DM Sans", system-ui, sans-serif;\n}\n'
    ':root[data-modo="oscuro"] {' + OSCURO_VARS + "}\n"
    '@media (prefers-color-scheme: dark) { :root:not([data-modo="claro"]) {' + OSCURO_VARS + "} }\n"
) + """
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html { -webkit-font-smoothing: antialiased; }
body {
  margin: 0; font-family: "DM Sans", "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
  color: var(--text); background: var(--bg); min-height: 100vh; font-size: 15px; line-height: 1.5;
}
::selection { background: var(--accent-soft); color: var(--text); }
.i { flex: none; vertical-align: -0.15em; }
.spin { animation: spin .9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
"""

REPORT_CSS = """
.wrap { max-width: 920px; margin: 0 auto; padding: 36px 20px 80px; }

.hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 28px; }
.eyebrow { font-size: 12px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--accent-ink); margin: 0 0 6px; }
h1 { font-size: clamp(26px, 4vw, 34px); line-height: 1.15; margin: 0 0 8px; letter-spacing: -.02em; font-weight: 700; }
.updated { color: var(--muted); font-size: 13px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 4px var(--green-soft); }

.hero-actions { display: flex; align-items: center; gap: 8px; flex: none; }
.hero-actions form { margin: 0; }
.icon-btn { width: 40px; height: 40px; display: grid; place-items: center; border: 1px solid var(--border); background: var(--card);
  color: var(--text); border-radius: 999px; cursor: pointer; box-shadow: var(--shadow); transition: border-color .15s; }
.icon-btn:hover { border-color: var(--accent); color: var(--accent); }
.icon-btn[disabled] { cursor: progress; }
.icon-btn.loading .i { animation: spin .9s linear infinite; }

details.account { position: relative; }
details.account > summary { display: flex; align-items: center; gap: 8px; padding: 4px 10px 4px 4px; border: 1px solid var(--border);
  background: var(--card); border-radius: 999px; cursor: pointer; box-shadow: var(--shadow); user-select: none; height: 40px; transition: border-color .15s; }
details.account > summary:hover { border-color: var(--accent); }
.acc-avatar { width: 30px; height: 30px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: var(--on-accent);
  display: grid; place-items: center; font-size: 12px; font-weight: 700; flex: none; }
.acc-name { font-size: 13.5px; font-weight: 550; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chev-down { color: var(--muted); transition: transform .15s; }
details[open] > summary > .chev-down { transform: rotate(180deg); }
.menu { position: absolute; right: 0; top: calc(100% + 8px); width: 260px; background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; box-shadow: 0 16px 48px rgba(16,20,40,.2); padding: 6px; z-index: 30; }
.menu-head { display: flex; gap: 10px; align-items: center; padding: 10px; border-bottom: 1px solid var(--border); margin-bottom: 4px; }
.menu-head .acc-avatar { width: 36px; height: 36px; font-size: 13px; }
.acc-avatar { position: relative; overflow: hidden; }
.acc-avatar img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; border-radius: inherit; }
.menu-name { font-weight: 600; font-size: 14px; line-height: 1.3; overflow-wrap: anywhere; }
.menu-user { font-size: 12.5px; color: var(--muted); overflow-wrap: anywhere; }
.menu form { margin: 0; }
.menu-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 10px; border: 0; background: none; color: var(--text);
  font: inherit; font-size: 14px; text-align: left; border-radius: 9px; cursor: pointer; text-decoration: none; }
.menu-item:hover { background: var(--card-2); }
.menu-item .i { color: var(--muted); }
.menu-item.danger, .menu-item.danger .i { color: var(--red); }
.menu-item.danger:hover { background: var(--red-soft); }

.warn { display: flex; gap: 10px; align-items: flex-start; background: var(--amber-soft); color: var(--amber); border-radius: 12px;
  padding: 10px 14px; font-size: 13.5px; margin-bottom: 16px; }
.warn .i { margin-top: 2px; }
.warn[hidden] { display: none; }
.popup-aules { position: fixed; right: 20px; bottom: 20px; z-index: 50; display: flex; gap: 12px; align-items: flex-start;
  width: min(380px, calc(100vw - 32px)); padding: 14px 14px 14px 16px; background: var(--card); color: var(--text);
  border: 1px solid var(--border); border-radius: 16px; box-shadow: inset 4px 0 0 var(--red), 0 12px 32px rgba(0,0,0,.18);
  animation: pa-entra .25s ease-out; }
.popup-aules[hidden] { display: none; }
.popup-aules.ok { box-shadow: inset 4px 0 0 var(--green), 0 12px 32px rgba(0,0,0,.18); }
.pa-icono { flex: none; width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center;
  background: var(--red-soft); color: var(--red); }
.popup-aules.ok .pa-icono { background: var(--green-soft); color: var(--green); }
.pa-icono > span { display: grid; }
.popup-aules .pa-ok, .popup-aules.ok .pa-fallo { display: none; }
.popup-aules.ok .pa-ok { display: grid; }
.pa-texto { flex: 1; min-width: 0; }
.pa-texto strong { display: block; font-size: 15px; margin-top: 1px; }
.pa-texto p { margin: 4px 0 0; font-size: 13.5px; color: var(--muted); }
.pa-cerrar { flex: none; border: 0; background: none; color: var(--muted); cursor: pointer; padding: 4px; border-radius: 8px; }
.pa-cerrar:hover { background: var(--card-2); color: var(--text); }
.pa-cerrar:focus-visible { outline: 2px solid var(--accent); }
@keyframes pa-entra { from { opacity: 0; transform: translateY(12px); } }
@media (max-width: 680px) { .popup-aules { right: 16px; left: 16px; bottom: 16px; width: auto; } }
@media (prefers-reduced-motion: reduce) { .popup-aules { animation: none; } }
.aviso-version { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; background: var(--card); border: 1px solid var(--border);
  box-shadow: inset 4px 0 0 var(--accent), var(--shadow); border-radius: 14px; padding: 12px 16px; margin-bottom: 16px; font-size: 13.5px; }
.aviso-version[hidden] { display: none; }
.aviso-version .av-texto { flex: 1 1 260px; min-width: 0; }
.aviso-version strong { font-size: 14.5px; }
.aviso-version ul { margin: 6px 0 0; padding-left: 18px; color: var(--muted); }
.aviso-version .av-botones { display: flex; gap: 8px; align-items: center; }
.aviso-version .av-error { color: var(--red); margin-top: 6px; }

.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 16px 18px; box-shadow: var(--shadow); }
.stat-label { font-size: 12.5px; color: var(--muted); font-weight: 500; display: flex; align-items: center; gap: 6px; }
.stat-value { font-size: 30px; font-weight: 700; letter-spacing: -.02em; line-height: 1.2; margin-top: 4px; font-variant-numeric: tabular-nums; }
.stat.exam .i, .stat.exam .stat-value { color: var(--orange); }
.stat.tasks .i { color: var(--blue); }
.stat.week .i, .stat.week .stat-value { color: var(--amber); }
.stat.new .i, .stat.new .stat-value { color: var(--green); }

.next { display: flex; align-items: center; gap: 14px; background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: var(--on-accent);
  border-radius: 18px; padding: 18px 20px; margin-bottom: 28px; box-shadow: 0 10px 30px rgba(91,91,246,.25); }
.next-icon { flex: none; width: 44px; height: 44px; border-radius: 12px; background: rgba(255,255,255,.18); display: grid; place-items: center; }
.next-body { min-width: 0; flex: 1; }
.next-label { font-size: 12px; opacity: .85; text-transform: uppercase; letter-spacing: .07em; font-weight: 600; }
.next-title { font-weight: 650; font-size: 17px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.next-course { font-size: 13px; opacity: .85; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.next-due { text-align: right; flex: none; }
.next-due .due-rel { font-weight: 700; font-size: 15px; background: rgba(255,255,255,.2); color: #fff; padding: 4px 12px; }
.next-due .due-abs { color: rgba(255,255,255,.85); font-size: 12.5px; }

/* minmax(0, 1fr): con «1fr» a secas una columna no baja del ancho de su contenido, y un nombre de tarea largo la ensanchaba
   hasta salirse del recuadro (y de la página). */
.ahora { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; background: var(--card); border: 1px solid var(--border);
  border-radius: 18px; box-shadow: var(--shadow); padding: 16px 20px; margin-bottom: 16px; text-decoration: none; color: inherit; }
.ahora .ahora-bloque + .ahora-bloque { border-left: 1px solid var(--border); padding-left: 16px; }
.ahora-label { display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }
.ahora-asig { font-weight: 650; font-size: 16px; line-height: 1.3; overflow-wrap: anywhere; }
.ahora .ahora-bloque { min-width: 0; }
.ahora-info { font-size: 12.5px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
a.ahora:hover { border-color: var(--accent); }
.ahora-ver { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; color: var(--accent); letter-spacing: 0; text-transform: none; font-weight: 600; }
.ahora.en-clase #ahora-asig { color: var(--accent); }
.ahora.en-recreo #ahora-asig { color: var(--green); }
.sin-horario:hover { border-color: var(--accent); }
@media (max-width: 680px) {
  .ahora { grid-template-columns: minmax(0, 1fr); gap: 12px; }
  .ahora .ahora-bloque + .ahora-bloque { border-left: 0; border-top: 1px solid var(--border); padding-left: 0; padding-top: 12px; }
}
.toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 20px; position: sticky; top: 0; z-index: 5;
  padding: 10px 0; background: linear-gradient(var(--bg) 75%, transparent); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { border: 1px solid var(--border); background: var(--card); color: var(--text); padding: 7px 14px; border-radius: 999px;
  font: inherit; font-size: 13.5px; font-weight: 500; cursor: pointer; transition: all .15s; }
.chip:hover { border-color: var(--accent); }
.chip.active { background: var(--text); color: var(--bg); border-color: var(--text); }
.chip .count { opacity: .6; margin-left: 4px; font-variant-numeric: tabular-nums; }
.search { flex: 1; min-width: 180px; position: relative; }
.search input { width: 100%; border: 1px solid var(--border); background: var(--card); color: var(--text); border-radius: 999px;
  padding: 8px 14px 8px 36px; font: inherit; font-size: 14px; outline: none; transition: border-color .15s, box-shadow .15s; }
.search input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
.search .i { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--muted); }

.course { background: var(--card); border: 1px solid var(--border); border-radius: 20px; box-shadow: var(--shadow); margin-bottom: 16px; overflow: hidden; }
.course-head { display: flex; align-items: center; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--border); }
.avatar, .post-avatar { flex: none; display: grid; place-items: center; font-weight: 700;
  color: hsl(var(--hue) 65% 42%); background: hsl(var(--hue) 80% 94%); }
.avatar { width: 38px; height: 38px; border-radius: 11px; font-size: 14px; }
.course-name { font-weight: 650; font-size: 15.5px; margin: 0; line-height: 1.3; }
.course-meta { font-size: 12.5px; color: var(--muted); }
.course-body { padding: 6px 8px 8px; }
.empty-course { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13.5px; padding: 12px 12px 6px; margin: 0; }
.empty-course .i { color: var(--green); }

.item { display: flex; gap: 16px; padding: 14px 12px; border-radius: 14px; position: relative; transition: background .15s; }
.item + .item { border-top: 1px solid var(--border); border-radius: 0 0 14px 14px; }
.item:hover { background: var(--card-2); }
.item::before { content: ""; position: absolute; left: 0; top: 16px; bottom: 16px; width: 3px; border-radius: 3px; background: transparent; }
.item.urg-urgent::before { background: var(--red); }
.item.urg-soon::before { background: var(--amber); }
.item.kind-examen:not(.is-done) { background: var(--orange-soft); border: 1px solid color-mix(in srgb, var(--orange) 35%, transparent); border-radius: 14px; margin: 6px 0; }
.item.kind-examen:not(.is-done) + .item { border-top: none; }
.item.is-done .item-title { color: var(--muted); }
.item-main { flex: 1; min-width: 0; }
.item-head { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }
.pill { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 650; text-transform: uppercase; letter-spacing: .05em; padding: 2px 8px; border-radius: 999px; white-space: nowrap; }
.pill-tarea { background: var(--blue-soft); color: var(--blue); }
.pill-examen { background: var(--orange); color: #fff; }
.is-done .pill-examen { background: var(--orange-soft); color: var(--orange); }
.pill-aviso { background: var(--gray-soft); color: var(--muted); }
.pill-new { background: var(--green-soft); color: var(--green); }
.pill-done { background: var(--green-soft); color: var(--green); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.pill-draft { background: var(--amber-soft); color: var(--amber); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.pill-abre { background: var(--blue-soft); color: var(--blue); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.pill-cambio { background: var(--amber-soft); color: var(--amber); }
.cambios { margin: 6px 0 0; padding: 8px 12px 8px 26px; background: var(--amber-soft); color: var(--amber); border-radius: 10px;
  font-size: 13px; font-weight: 600; }
.cambios li + li { margin-top: 2px; }
.progreso { display: flex; gap: 10px; align-items: flex-start; margin: 6px 4px 4px; padding: 10px 12px; border-radius: 12px;
  background: var(--card-2); border: 1px solid var(--border); font-size: 13.5px; }
.progreso > .i { flex: none; margin-top: 2px; }
.progreso.bien > .i { color: var(--green); } .progreso.mal > .i { color: var(--red); }
.progreso-origen { margin-top: 3px; font-size: 12px; color: var(--muted); }
.pill-aprobado { background: var(--green-soft); color: var(--green); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.pill-suspendido { background: var(--red-soft); color: var(--red); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.item-title { margin: 0; font-size: 15px; font-weight: 600; line-height: 1.35; overflow-wrap: anywhere; }

.due { flex: none; text-align: right; min-width: 140px; }
.due-rel { display: inline-block; font-size: 13px; font-weight: 650; padding: 3px 10px; border-radius: 999px; background: var(--gray-soft); color: var(--muted); white-space: nowrap; }
.due-abs { display: flex; justify-content: flex-end; align-items: center; gap: 5px; font-size: 12px; color: var(--muted); margin-top: 5px; white-space: nowrap; }
.urg-urgent .due-rel { background: var(--red-soft); color: var(--red); }
.urg-soon .due-rel { background: var(--amber-soft); color: var(--amber); }
.urg-later .due-rel { background: var(--green-soft); color: var(--green); }
.urg-overdue .due-rel { text-decoration: line-through; }

details > summary { list-style: none; }
details > summary::-webkit-details-marker { display: none; }
.chev { transition: transform .15s; }
details[open] > summary > .chev { transform: rotate(90deg); }
details.desc { margin-top: 8px; }
details.desc > summary { cursor: pointer; font-size: 13px; min-height: 24px; color: var(--accent-ink); font-weight: 550; display: inline-flex; align-items: center; gap: 4px; user-select: none; }
.desc-body { margin-top: 8px; padding: 12px 14px; background: var(--card-2); border: 1px solid var(--border); border-radius: 12px;
  font-size: 14px; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--text); }
.desc-body a { color: var(--accent-ink); }
/* Enunciado en PDF: vista previa del archivo en vez del texto sacado de él (que repetía cabeceras y perdía el orden). */
.pdf-caja { margin-top: 8px; border: 1px solid var(--border); border-radius: 12px; background: var(--card-2); overflow: hidden; }
.pdf-barra { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.pdf-nombre { flex: 1 1 160px; min-width: 0; font-size: 12.5px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pdf-btn { display: inline-flex; align-items: center; gap: 6px; padding: 4px 11px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--card); color: var(--muted); font-size: 12.5px; font-weight: 600; text-decoration: none;
  transition: border-color .15s, color .15s; }
.pdf-btn:hover { border-color: var(--accent); color: var(--accent); }
.pdf-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.pdf-marco { display: block; width: 100%; height: min(78vh, 900px); min-height: 420px; border: 0; background: var(--card-2); }

.files { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.file { display: inline-flex; align-items: center; gap: 8px; max-width: 100%; text-decoration: none; color: var(--text); font-size: 13px;
  border: 1px solid var(--border); background: var(--card); border-radius: 10px; padding: 5px 10px 5px 5px; transition: border-color .15s, transform .15s; }
.file:hover { border-color: var(--accent); transform: translateY(-1px); }
.file .ext { font-size: 11px; font-weight: 700; background: var(--accent-soft); color: var(--accent); border-radius: 6px; padding: 3px 6px; }
.file .fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

details.group { margin: 4px 4px 2px; }
details.group > summary { cursor: pointer; font-size: 13px; color: var(--muted); font-weight: 550; padding: 8px; border-radius: 10px; user-select: none; display: flex; align-items: center; gap: 6px; }
details.group > summary:hover { background: var(--card-2); }
.mat-sec { padding: 4px 8px 10px; }
.mat-sec-nombre { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
.mat-sec .files { margin-top: 0; }
.file .pill-new { font-size: 11px; padding: 1px 6px; }

details.forum-panel { background: var(--card); border: 1px solid var(--border); border-radius: 20px; margin-top: 28px; overflow: hidden; }
details.forum-panel > summary { display: flex; align-items: center; gap: 12px; padding: 14px 20px; cursor: pointer; user-select: none; }
details.forum-panel > summary:hover { background: var(--card-2); }
details.forum-panel[open] > summary { border-bottom: 1px solid var(--border); }
.forum-icon { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; background: var(--gray-soft); color: var(--muted); flex: none; }
.forum-text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.forum-title { font-weight: 600; font-size: 14.5px; }
.forum-sub { font-size: 12.5px; color: var(--muted); }
.forum-badge { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); white-space: nowrap; }
.posts { padding: 6px 8px 8px; }
.post { display: flex; gap: 12px; padding: 12px; border-radius: 12px; }
.post + .post { border-top: 1px solid var(--border); border-radius: 0; }
.post:hover { background: var(--card-2); }
.post-avatar { width: 32px; height: 32px; border-radius: 50%; font-size: 11.5px; }
.post-main { flex: 1; min-width: 0; }
.post-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.post-subject { margin: 0; font-size: 14px; font-weight: 550; display: flex; align-items: center; gap: 6px; overflow-wrap: anywhere; }
.post-subject .i { color: var(--muted); }
.post.is-new .post-subject { font-weight: 650; }
.post-meta { font-size: 12.5px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
.post-link { display: inline-flex; align-items: center; gap: 4px; min-height: 24px; margin-top: 8px; font-size: 12.5px; color: var(--muted); text-decoration: none; }
.post-link:hover { color: var(--accent); }
.post-time { flex: none; }
.post-time .due-rel { font-size: 12px; font-weight: 550; }

.empty { text-align: center; color: var(--muted); padding: 60px 20px; }
.empty .i { opacity: .6; }
footer { display: flex; justify-content: center; align-items: center; gap: 6px; color: var(--muted); font-size: 12px; margin-top: 32px; }

.nota { display: flex; gap: 14px; align-items: flex-start; padding: 10px 12px; border-radius: 12px; }
.nota + .nota { border-top: 1px solid var(--border); border-radius: 0; }
.nota.is-new { background: var(--green-soft); border-radius: 12px; }
.nota-main { flex: 1; min-width: 40%; }
.nota-nombre { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.nota-meta { font-size: 12px; color: var(--muted); margin-top: 2px; }
.nota-meta:empty { display: none; }
.nota-fb { display: flex; gap: 6px; align-items: flex-start; margin-top: 6px; padding: 8px 10px; background: var(--card-2);
  border: 1px solid var(--border); border-radius: 10px; font-size: 13px; white-space: pre-wrap; overflow-wrap: anywhere; }
.nota-fb .i { flex: none; margin-top: 2px; color: var(--accent); }
.nota-fb a { color: var(--accent-ink); }
/* «Ver preguntas y respuestas» de los cuestionarios: botón pequeño, como los demás de la app. */
.nota-rev { margin-top: 8px; }
.nota-revision { display: inline-flex; align-items: center; gap: 6px; padding: 4px 11px; border: 1px solid var(--border);
  border-radius: 999px; background: var(--card); color: var(--muted); font-size: 12.5px; font-weight: 600; text-decoration: none;
  transition: border-color .15s, color .15s; }
.nota-revision .i { color: var(--accent); }
.nota-revision:hover { border-color: var(--accent); color: var(--accent); }
.nota-revision:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.nota-valor { flex: none; font-size: 20px; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; white-space: nowrap; max-width: 50%; overflow: hidden; text-overflow: ellipsis; }
.nota-max { font-size: 12.5px; font-weight: 500; color: var(--muted); margin-left: 3px; }
.nota-item { margin-top: 10px; border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 12px; background: var(--card); }
.nota-item .nota-nombre { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--accent-ink); }
details.notas .notas-link { margin: 4px 12px 8px; }
.mensajes-panel { margin: 0 0 16px; }
.practicas-lista { display: flex; flex-direction: column; padding: 0 4px 8px; }
.practica { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 10px; text-decoration: none; color: var(--text); font-size: 13.5px; }
.practica + .practica { border-top: 1px solid var(--border); border-radius: 0; }
.practica:hover { background: var(--card-2); }
.practica .i { color: var(--muted); flex: none; }
.practica-nombre { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.practica.is-done .practica-nombre { color: var(--muted); }
.mensaje-texto { color: var(--text); white-space: pre-wrap; }
.mensaje-texto a { color: var(--accent-ink); }
.ahora-tareas { display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; font-size: 12px; font-weight: 600;
  padding: 3px 9px; border-radius: 12px; background: var(--blue-soft); color: var(--blue); max-width: 100%; min-width: 0; }
/* Un nombre largo ocupa hasta dos líneas (el texto entero sale al pasar el ratón) en vez de una sola que no cabe. */
.ahora-tareas span { min-width: 0; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2;
  overflow: hidden; overflow-wrap: anywhere; line-height: 1.35; }
.ahora-tareas.examen { background: var(--orange-soft); color: var(--orange); }
.ahora-tareas.ok { background: var(--green-soft); color: var(--green); }

.ia { margin-top: 10px; }
details.mas { position: relative; flex: none; width: max-content; margin: 8px 0 0 auto; text-align: left; }
@media (max-width: 680px) { details.mas { margin: 0 0 0 auto; } }
.mas-btn { width: 30px; height: 30px; box-shadow: none; color: var(--muted); }
details.mas[open] > .mas-btn { border-color: var(--accent); color: var(--accent); }
.mas-menu { top: calc(100% + 6px); width: 290px; max-width: calc(100vw - 40px); }
.mas-menu .menu-item[disabled] { color: var(--muted); cursor: default; background: none; }
.mas-sep { height: 1px; background: var(--border); margin: 5px 4px; }
.mas-menu .ia-cadena { display: flex; padding: 6px 10px 8px; flex-wrap: wrap; }
.mas-menu .ia-cadena select { flex: 1 1 100%; max-width: none; }
/* El menú no puede quedar cortado ni tapado por la siguiente asignatura, pero tampoco tapar la barra de
   búsqueda y filtros, que va pegada arriba con z-index 5: por eso 4 y no más. */
.course:has(details.mas[open]) { overflow: visible; position: relative; z-index: 4; }
/* La opacidad de las tareas de los grupos (hechas, avisos) encierra el menú en su capa: quedaba debajo de las
   tareas siguientes y medio transparente. Con el menú abierto, su tarea va opaca y por encima de las demás. */
.item:has(details.mas[open]) { z-index: 7; opacity: 1 !important; }
.ia-cadena { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted); max-width: 100%; }
.ia-cadena select { font: inherit; font-size: 12.5px; color: var(--text); background: var(--card); border: 1px solid var(--border);
  border-radius: 999px; padding: 3px 8px; max-width: 320px; min-width: 0; text-overflow: ellipsis; }
.ia-cadena select:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.ia-bloque { margin-top: 8px; padding: 10px 12px; border: 1px solid var(--border); border-left: 3px solid var(--accent);
  background: var(--card-2); border-radius: 10px; }
.ia-titulo { display: flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 650; color: var(--accent-ink);
  text-transform: uppercase; letter-spacing: .04em; margin-bottom: 6px; }
.ia-texto { margin: 0; font: inherit; font-size: 13.5px; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--text); }
.ia-cargando { color: var(--muted); font-size: 13px; border-left-color: var(--muted); }
.ia-error { border-left-color: var(--red); color: var(--red); font-size: 13px; }

@media (max-width: 680px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
  .item { flex-direction: column; gap: 8px; }
  .due { text-align: left; min-width: 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; row-gap: 4px; }
  .due-abs { margin-top: 0; }
  .next { flex-wrap: wrap; }
  .next-due { text-align: left; width: 100%; }
  .post { flex-wrap: wrap; }
  .post-time { width: 100%; padding-left: 44px; }
}
@media (max-width: 480px) {
  .acc-name { display: none; }
  details.account > summary { padding-right: 8px; }
}
/* Móvil: los botones (+, refrescar, cuenta) suben a la altura de la fecha y el saludo ocupa todo el ancho.
   Antes compartían fila y el texto se quedaba en ~150 px, partido en varias líneas. */
@media (max-width: 480px) {
  .hero:has(> .hero-actions) { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; column-gap: 12px;
    grid-template-areas: "fecha acciones" "saludo saludo" "estado estado"; }
  .hero:has(> .hero-actions) > div:first-child { display: contents; }
  .hero:has(> .hero-actions) .eyebrow { grid-area: fecha; margin: 0; }
  .hero:has(> .hero-actions) h1 { grid-area: saludo; }
  .hero:has(> .hero-actions) .updated { grid-area: estado; }
  .hero:has(> .hero-actions) > .hero-actions { grid-area: acciones; }
}
"""

AHORA_JS = """
(function () {
  var DIAS_SEMANA = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
  function aMinutos(h) { var p = (h || '').split(':'); return (+p[0] || 0) * 60 + (+p[1] || 0); }
  function esRecreo(f) { return /descanso|recreo|pausa|patio|esbarjo/i.test(f.asignatura || ''); }
  function nombreFranja(f) { return esRecreo(f) ? 'Patio' : (f.asignatura || 'Clase'); }
  function duracion(minutos) {
    if (minutos < 60) return minutos + ' min';
    var h = Math.floor(minutos / 60), m = minutos % 60;
    return h + ' h' + (m ? ' y ' + m + ' min' : '');
  }
  function detalleFranja(f, extra) {
    return f.inicio + (f.fin ? ' – ' + f.fin : '') + (f.aula ? ' · ' + f.aula : '') + (extra ? ' · ' + extra : '');
  }
  function pintarPendientes(id, franja) {
    var el = document.getElementById(id);
    if (!el) return;
    var datos = {};
    try { datos = JSON.parse(document.getElementById('horario-datos').textContent || '{}'); } catch (e) {}
    var p = franja && !esRecreo(franja) && (datos.pendientes || {})[franja.asignatura];
    el.hidden = !p;
    if (!p) return;
    el.className = 'ahora-tareas' + (p.examenes ? ' examen' : (p.n ? '' : ' ok'));
    var texto;
    if (!p.n) texto = 'Nada pendiente de esta asignatura';
    else if (p.n === 1) texto = (p.examenes ? 'Examen pendiente: ' : '1 tarea pendiente: ') + p.proxima;
    else texto = p.n + ' pendientes' + (p.examenes ? ' (' + p.examenes + (p.examenes === 1 ? ' examen)' : ' exámenes)') : '') + ' · próxima: ' + p.proxima;
    el.textContent = '';
    var s = document.createElement('span');
    s.textContent = texto;
    el.title = texto;
    el.append(s);
  }
  var TIPOS_SIN_CLASE = { 'festivo': 'Festivo', 'vacaciones': 'Vacaciones', 'no lectivo': 'Día no lectivo' };
  function isoFecha(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function pintarAhora() {
    var datos = {};
    try { datos = JSON.parse(document.getElementById('horario-datos').textContent || '{}'); } catch (e) {}
    var caja = document.getElementById('ahora'), sin = document.getElementById('sin-horario');
    if (!caja) return;
    if (!datos.dias || !Object.keys(datos.dias).length) { caja.hidden = true; if (sin) sin.hidden = false; return; }
    if (sin) sin.hidden = true;
    caja.hidden = false;

    var ahora = new Date(), min = ahora.getHours() * 60 + ahora.getMinutes();
    var sinClase = datos.no_lectivos || {};
    var tipoHoy = sinClase[isoFecha(ahora)];
    var franjas = (tipoHoy ? [] : (datos.dias[DIAS_SEMANA[ahora.getDay()]] || [])).slice()
      .sort(function (a, b) { return aMinutos(a.inicio) - aMinutos(b.inicio); });
    var actual = franjas.filter(function (f) { return min >= aMinutos(f.inicio) && min < aMinutos(f.fin || f.inicio); })[0];
    var siguiente = franjas.filter(function (f) { return aMinutos(f.inicio) > min; })[0];

    caja.classList.toggle('en-clase', !!actual && !esRecreo(actual));
    caja.classList.toggle('en-recreo', !!actual && esRecreo(actual));
    var asig = document.getElementById('ahora-asig'), info = document.getElementById('ahora-info');
    if (actual) {
      asig.textContent = nombreFranja(actual);
      info.textContent = detalleFranja(actual, 'quedan ' + duracion(aMinutos(actual.fin) - min));
    } else if (siguiente) {
      asig.textContent = 'Sin clase ahora';
      info.textContent = 'Hueco hasta las ' + siguiente.inicio;
    } else if (franjas.length) {
      asig.textContent = 'Has terminado por hoy';
      info.textContent = 'La última acabó a las ' + franjas[franjas.length - 1].fin;
    } else if (tipoHoy) {
      asig.textContent = 'Hoy no hay clase';
      info.textContent = TIPOS_SIN_CLASE[tipoHoy] || 'Día sin clase';
    } else {
      asig.textContent = 'Hoy no tienes clase';
      info.textContent = '';
    }

    pintarPendientes('ahora-tareas', actual);

    var sAsig = document.getElementById('sig-asig'), sInfo = document.getElementById('sig-info');
    pintarPendientes('sig-tareas', siguiente);
    if (siguiente) {
      sAsig.textContent = nombreFranja(siguiente);
      sInfo.textContent = detalleFranja(siguiente, 'empieza en ' + duracion(aMinutos(siguiente.inicio) - min));
    } else {
      var proximo = null;
      // Se saltan fines de semana, festivos y vacaciones (hasta 40 días, por Navidad o Pascua).
      for (var i = 1; i <= 40 && !proximo; i++) {
        var fecha = new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate() + i);
        if (sinClase[isoFecha(fecha)]) continue;
        var dia = DIAS_SEMANA[fecha.getDay()];
        var lista = (datos.dias[dia] || []).slice().sort(function (a, b) { return aMinutos(a.inicio) - aMinutos(b.inicio); });
        if (lista.length) {
          var cuando = i === 1 ? 'mañana' : (i < 7 ? 'el ' + dia.toLowerCase() : 'el ' + dia.toLowerCase() + ' ' + fecha.getDate() + '/' + (fecha.getMonth() + 1));
          proximo = { cuando: cuando, franja: lista[0] };
        }
      }
      if (proximo) {
        sAsig.textContent = nombreFranja(proximo.franja);
        sInfo.textContent = proximo.cuando + ' a las ' + proximo.franja.inicio + (proximo.franja.aula ? ' · ' + proximo.franja.aula : '');
      } else { sAsig.textContent = '—'; sInfo.textContent = ''; }
    }

    // En la página del horario, resalta el día de hoy y la franja en curso.
    var lunes = new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate() - ((ahora.getDay() + 6) % 7));
    document.querySelectorAll('[data-dia]').forEach(function (col) {
      col.classList.toggle('hoy', col.dataset.dia === DIAS_SEMANA[ahora.getDay()]);
      // En la semana en curso, marca los días que no hay clase.
      var fecha = new Date(lunes.getFullYear(), lunes.getMonth(), lunes.getDate() + DIAS_SEMANA.indexOf(col.dataset.dia) - 1);
      var tipo = sinClase[isoFecha(fecha)];
      col.classList.toggle('sin-clase', !!tipo);
      var marca = col.querySelector('.sin-clase-txt');
      if (marca) marca.textContent = tipo ? (TIPOS_SIN_CLASE[tipo] || 'Sin clase') : '';
    });
    document.querySelectorAll('[data-franja-inicio]').forEach(function (fila) {
      var hoy = fila.closest('[data-dia]');
      var enCurso = hoy && hoy.dataset.dia === DIAS_SEMANA[ahora.getDay()]
        && min >= aMinutos(fila.dataset.franjaInicio) && min < aMinutos(fila.dataset.franjaFin);
      fila.classList.toggle('en-curso', !!enCurso);
    });
  }
  pintarAhora();
  setInterval(pintarAhora, 30000);
})();
"""

LOGIN_CSS = """
.auth { min-height: 100vh; display: grid; place-items: center; padding: 24px 16px; }
.auth-card { width: 100%; max-width: 400px; background: var(--card); border: 1px solid var(--border); border-radius: 22px; box-shadow: var(--shadow); padding: 32px 28px; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 650; font-size: 14px; color: var(--muted); margin-bottom: 24px; }
.brand-mark { width: 38px; height: 38px; border-radius: 11px; background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: var(--on-accent);
  display: grid; place-items: center; box-shadow: 0 6px 18px rgba(91,91,246,.3); }
.auth h1 { font-size: 24px; margin: 0 0 4px; letter-spacing: -.02em; }
.auth-sub { color: var(--muted); margin: 0 0 22px; font-size: 14px; }
.alert { display: flex; gap: 10px; align-items: flex-start; background: var(--red-soft); color: var(--red); border-radius: 12px; padding: 10px 12px; font-size: 13.5px; margin-bottom: 16px; }
.alert .i { margin-top: 2px; }
.field { display: block; margin-bottom: 14px; }
.field > span { display: block; font-size: 13px; font-weight: 550; margin-bottom: 6px; }
.input { position: relative; display: flex; align-items: center; }
.input > .i { position: absolute; left: 12px; color: var(--muted); pointer-events: none; }
.input input { width: 100%; border: 1px solid var(--border); background: var(--card-2); color: var(--text); border-radius: 12px;
  padding: 11px 44px 11px 38px; font: inherit; font-size: 15px; outline: none; transition: border-color .15s, box-shadow .15s, background .15s; }
.input input:focus { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); background: var(--card); }
.input.select .i { z-index: 1; }
.input select { width: 100%; border: 1px solid var(--border); background: var(--card-2); color: var(--text); border-radius: 12px;
  padding: 11px 14px 11px 38px; font: inherit; font-size: 15px; outline: none; appearance: none; cursor: pointer; }
.input select:focus { border-color: var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); }
.input.select::after { content: ""; position: absolute; right: 16px; top: 50%; width: 7px; height: 7px; margin-top: -6px;
  border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted); transform: rotate(45deg); pointer-events: none; }
.input select { padding-right: 38px; }
.toggle { position: absolute; right: 6px; border: 0; background: none; color: var(--muted); padding: 6px; border-radius: 8px; cursor: pointer; display: grid; place-items: center; }
.toggle:hover { color: var(--text); background: var(--gray-soft); }
.btn-primary { width: 100%; display: flex; justify-content: center; align-items: center; gap: 8px; margin-top: 8px; border: 0; border-radius: 12px;
  padding: 12px; font: inherit; font-weight: 600; font-size: 15px; color: var(--on-accent); background: linear-gradient(135deg, var(--accent), var(--accent-2));
  cursor: pointer; box-shadow: 0 8px 20px rgba(91,91,246,.28); transition: transform .1s, filter .15s; text-decoration: none; }
.btn-primary:hover { filter: brightness(1.06); }
.btn-primary:active { transform: translateY(1px); }
.btn-primary[disabled] { opacity: .85; cursor: progress; }
.btn-link { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 14px; font-size: 13.5px; color: var(--muted); min-height: 24px;
  text-decoration: none; background: none; border: 0; font: inherit; cursor: pointer; width: 100%; }
.btn-link:hover { color: var(--text); }
.recordar { display: flex; align-items: center; gap: 8px; font-size: 13.5px; margin: 2px 0 6px; cursor: pointer; user-select: none; }
.recordar input { width: 16px; height: 16px; accent-color: var(--accent); margin: 0; }
.auth-note { display: flex; gap: 8px; align-items: flex-start; margin: 22px 0 0; padding-top: 18px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12.5px; }
.auth-note .i { margin-top: 1px; color: var(--green); }
.sso-bloque[hidden], #campos-usuario[hidden] { display: none; }
.sso-texto { color: var(--muted); font-size: 13.5px; margin: 0 0 14px; }
.sso-nota { color: var(--muted); font-size: 12.5px; margin: 12px 0 0; }
.sso-pasos { margin: 0 0 16px; padding-left: 20px; font-size: 14px; display: grid; gap: 6px; }
.sso-abrir { display: flex; align-items: center; justify-content: center; gap: 8px; text-decoration: none; margin-bottom: 14px; }
.sso-estado { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 14px; margin: 0 0 14px; }
.sso-estado .i { color: var(--accent); flex: none; }
.sso-estado.error { color: var(--red); }
.sso-pegar { margin: 14px 0; font-size: 13.5px; }
.sso-pegar summary { cursor: pointer; color: var(--accent-ink); font-weight: 550; }
.sso-pegar textarea { width: 100%; min-height: 76px; margin: 10px 0; padding: 10px 12px; border: 1px solid var(--border);
  border-radius: 12px; background: var(--card-2); color: var(--text); font: inherit; font-size: 13px; resize: vertical; }
"""

AJUSTES_CSS = """
.auth-card.ancha { max-width: 520px; }
.alert.ok { background: var(--green-soft); color: var(--green); }
.opt { color: var(--muted); font-weight: 400; }
.check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); margin: 4px 0 16px; cursor: pointer; }
.check input { accent-color: var(--accent); }
.acciones-modelo { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: -6px 0 16px; }
.mini-btn { display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--border); background: var(--card); color: var(--muted);
  border-radius: 999px; padding: 4px 10px; font: inherit; font-size: 12.5px; cursor: pointer; transition: border-color .15s, color .15s; }
.mini-btn:hover { border-color: var(--accent); color: var(--accent); }
.mini-btn[disabled] { opacity: .6; cursor: progress; }
.estado { font-size: 12.5px; color: var(--muted); }
"""


TEMA_CSS = """
/* Titulares: Bricolage Grotesque, con carácter. Texto: DM Sans. */
h1, h2, .course-name, .profe-nombre, .dlg-cab h2, .otros h2, .sin-clase-lista h2, .mat-top h1, .auth h1,
.next-title, .stat-value, .ahora-asig, .nav-marca, .nota-valor, .dia-cab { font-family: var(--display); }
h1 { font-weight: 800; letter-spacing: -.03em; }
.hero h1 { font-size: clamp(34px, 5.5vw, 48px); line-height: 1; margin-bottom: 10px; }
.course-name { font-weight: 700; font-size: 17px; letter-spacing: -.01em; }
.eyebrow { color: var(--muted); font-size: 13px; letter-spacing: 0; text-transform: none; font-weight: 500; }
.rotulador { font-style: normal; background: linear-gradient(transparent 58%, var(--rotulador-trazo) 58%); padding: 0 .08em; border-radius: 2px; }

/* Botones con acento: planos, con un pequeño "escalón" que da gracia. */
.btn-primary, .boton-pri, .acciones-horario .principal, .boton-apuntar {
  background: var(--accent) !important; color: var(--on-accent) !important; border: 0;
  box-shadow: 0 3px 0 var(--accent-sombra) !important; transition: transform .08s, box-shadow .08s, filter .15s; }
.btn-primary:active, .boton-pri:active, .boton-apuntar:active { transform: translateY(2px); box-shadow: 0 1px 0 var(--accent-sombra) !important; }
.btn-primary:hover, .boton-pri:hover, .boton-apuntar:hover, .acciones-horario .principal:hover { filter: brightness(1.05); }
.boton-p.principal { background: var(--text) !important; color: var(--bg) !important; box-shadow: none !important; }
.brand-mark { background: var(--accent) !important; color: var(--on-accent) !important; box-shadow: none !important; transform: rotate(-6deg); }
.acc-avatar { background: var(--text) !important; color: var(--bg) !important; font-family: var(--display); }

/* Navegación. */
.nav { max-width: 920px; margin: 0 auto; padding: 18px 20px 0; display: flex; align-items: center; gap: 16px; }
.nav.ancha { max-width: 1200px; }
.nav-marca { display: inline-flex; align-items: center; gap: 10px; color: var(--text); text-decoration: none;
  font-size: 22px; font-weight: 800; letter-spacing: -.02em; }
.nav-logo { width: 30px; height: 30px; border-radius: 10px; background: var(--accent); color: var(--on-accent); display: grid;
  place-items: center; font-size: 17px; font-weight: 800; transform: rotate(-6deg); }
.nav-marca:hover .nav-logo { transform: rotate(6deg); transition: transform .2s; }
.nav-links { margin-left: auto; display: flex; gap: 2px; padding: 4px; background: var(--card); border: 1px solid var(--border);
  border-radius: 999px; overflow-x: auto; scrollbar-width: none; }
.nav-links a { display: inline-flex; align-items: center; gap: 6px; padding: 6px 13px; border-radius: 999px; color: var(--muted);
  text-decoration: none; font-size: 14px; font-weight: 500; white-space: nowrap; }
.nav-links a:hover { color: var(--text); }
.nav-links a.activa { background: var(--text); color: var(--bg); }
@media (max-width: 640px) {
  .nav { gap: 10px; padding-top: 14px; }
  .nav-marca .nav-txt { display: none; }
  .nav-links a:not(.activa) span { display: none; }
}
.nav + .wrap { padding-top: 26px; }
.wrap.wrap-ancha { max-width: 1200px; }
.nav + .mat-wrap { height: calc(100vh - 64px); padding-top: 16px; }
.nav + .auth { min-height: auto; padding-top: 28px; align-items: start; }

.boton-apuntar { display: inline-flex; align-items: center; gap: 6px; height: 40px; padding: 0 18px; border-radius: 999px;
  font: inherit; font-size: 14.5px; font-weight: 700; cursor: pointer; }
@media (max-width: 480px) { .boton-apuntar span { display: none; } .boton-apuntar { width: 40px; padding: 0; justify-content: center; } }
.icon-btn, details.account > summary { box-shadow: none; }

/* Avatares de asignatura: cuatro tonos suaves. */
.avatar, .post-avatar { color: hsl(var(--hue) var(--av-fg)) !important; background: hsl(var(--hue) var(--av-bg)) !important;
  font-family: var(--display); font-weight: 700; }

/* Cifras: cada una con su color suave. */
.stats { gap: 10px; }
.stat { box-shadow: none; padding: 14px 16px; border-color: transparent; }
.stat-label { color: var(--muted); }
.stat-value { font-weight: 800; font-size: 36px; letter-spacing: -.02em; line-height: 1.1; }
.stat.exam { background: var(--accent-soft); } .stat.exam .i, .stat.exam .stat-value { color: var(--accent-ink) !important; }
.stat.tasks { background: var(--green-soft); } .stat.tasks .i, .stat.tasks .stat-value { color: var(--green) !important; }
.stat.week { background: var(--amber-soft); } .stat.week .i, .stat.week .stat-value { color: var(--amber) !important; }
.stat.new { background: var(--blue-soft); } .stat.new .i, .stat.new .stat-value { color: var(--blue) !important; }

/* Ahora / Después: el bloque que más destaca. */
.ahora { background: var(--ahora-bg); color: var(--ahora-text); border-color: var(--ahora-borde); box-shadow: none; }
.ahora .ahora-bloque + .ahora-bloque { border-left-color: rgba(255,255,255,.12); }
.ahora-label { color: var(--rotulador); letter-spacing: .08em; }
.ahora-ver { color: var(--rotulador); }
.ahora-asig { font-size: 21px; font-weight: 700; letter-spacing: -.01em; color: var(--ahora-text); }
.ahora-info { color: var(--ahora-muted); }
.ahora.en-clase #ahora-asig { color: var(--ahora-text); }
.ahora.en-recreo #ahora-asig { color: #8fdcae; }
a.ahora:hover { border-color: var(--rotulador); }
.ahora-tareas { background: rgba(255,255,255,.08); color: var(--ahora-text); border: 0; }
.ahora-tareas.examen { background: var(--accent); color: var(--on-accent); }
.ahora-tareas.ok { background: transparent; color: #8fdcae; padding-left: 0; }
.sin-horario { background: var(--card); color: var(--text); border-color: var(--border); }
.sin-horario .ahora-asig { color: var(--text); } .sin-horario .ahora-info { color: var(--muted); } .sin-horario .ahora-label { color: var(--muted); }
@media (max-width: 680px) { .ahora .ahora-bloque + .ahora-bloque { border-top-color: rgba(255,255,255,.12); } }

/* Lo próximo. */
.next { background: var(--card); color: var(--text); border: 1px solid var(--border); box-shadow: inset 5px 0 0 var(--accent); }
.next-icon { background: var(--accent-soft); color: var(--accent-ink); }
.next-label { color: var(--accent-ink); opacity: 1; }
.next-title { font-weight: 700; }
.next-course { color: var(--muted); opacity: 1; }
.next-due .due-rel { background: var(--text); color: var(--bg); }
.next-due .due-abs { color: var(--muted); }

/* Asignaturas y actividades. */
.course, .forum-panel, .profe, .dia, .sin-clase-lista { box-shadow: none; }
.item.kind-examen:not(.is-done) { background: var(--accent-soft); border: 0; border-radius: 12px; box-shadow: inset 4px 0 0 var(--accent); margin: 4px 0; }
.due-rel { background: transparent; color: var(--muted); padding-left: 0; padding-right: 0; }
.urg-soon .due-rel { background: var(--amber-soft); color: var(--amber); padding: 3px 10px; }
.urg-urgent .due-rel { background: var(--text); color: var(--bg); padding: 3px 10px; }
.urg-overdue .due-rel { color: var(--red); }

.pill { font-weight: 700; letter-spacing: .04em; border: 1px solid transparent; }
.pill-tarea, .pill-aviso { background: transparent; color: var(--muted); border-color: var(--border); }
.pill-examen { background: var(--accent); color: var(--on-accent); }
.is-done .pill-examen { background: transparent; color: var(--muted); border-color: var(--border); }
.pill-new { background: var(--rotulador); color: var(--rotulador-ink); }
.pill-propia { background: transparent; color: var(--muted); border: 1px dashed var(--muted); }
.pill-done { background: var(--green-soft); color: var(--green); }
.pill-draft { background: var(--amber-soft); color: var(--amber); }
.file .ext { background: var(--accent-soft); color: var(--accent-ink); }
.chip.active { background: var(--text); color: var(--bg); border-color: var(--text); }
.forum-badge { background: var(--rotulador); color: var(--rotulador-ink); }
.search input { background: var(--card); }

/* Notas. */
.nota-valor { color: var(--text); font-weight: 800; }
.nota.is-new { background: var(--amber-soft); }
.nota-item { box-shadow: inset 3px 0 0 var(--green); border-left-width: 1px; }
.nota-item .nota-nombre { color: var(--green); }

/* Horario. */
.dia-cab { font-weight: 700; }
.dia.hoy { border-color: var(--text); box-shadow: 0 0 0 1px var(--text); }
.dia.hoy .dia-cab { background: var(--text); color: var(--bg); }
.fila.en-curso { background: var(--amber-soft); box-shadow: inset 4px 0 0 var(--accent); }
.fila.en-curso .fila-asig { color: var(--text); }
.pestanas-horario .pill-new { background: var(--rotulador); color: var(--rotulador-ink); }
.pestanas-horario .chip.active .pill-new { background: var(--rotulador) !important; color: var(--rotulador-ink) !important; }
"""


def _nav(activa="", ancha=False):
    enlaces = (("inicio", "/", "inbox", "Inicio"), ("horario", "/horario", "calendar", "Horario"),
               ("materiales", "/materiales", "folder", "Materiales"), ("profesores", "/profesores", "mail", "Profesores"))
    links = "".join(
        f'<a href="{url}" aria-label="{texto}"{" class=\"activa\" aria-current=\"page\"" if clave == activa else ""}>'
        f'{icon(ic, 15)}<span>{texto}</span></a>'
        for clave, url, ic, texto in enlaces
    )
    return (
        f'<nav class="nav{" ancha" if ancha else ""}"><a class="nav-marca" href="/"><span class="nav-logo">A</span>'
        f'<span class="nav-txt">Aules</span></a><div class="nav-links">{links}</div></nav>'
    )


def _page(title, body, css, js=""):
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700;12..96,800&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700&display=swap" rel="stylesheet">
<style>{BASE_CSS}{css}{TEMA_CSS}{TEMAS_CSS}</style>
</head>
<body>
{body}
{f'<script>{js}</script>' if js else ''}
</body>
</html>"""


HORARIO_CSS = """
.volver-link { display: inline-flex; align-items: center; gap: 6px; font-size: 13.5px; font-weight: 550; color: var(--muted);
  text-decoration: none; margin-bottom: 10px; padding: 6px 12px 6px 8px; border: 1px solid var(--border); background: var(--card);
  border-radius: 999px; box-shadow: var(--shadow); }
.volver-link:hover { color: var(--accent); border-color: var(--accent); }
.pestanas-horario { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.pestanas-horario .chip { text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
.pestanas-horario .pill { font-size: 11px; }
.nota-horario { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 12px 16px;
  margin-bottom: 16px; color: var(--muted); font-size: 13.5px; }
.nota-horario a { color: var(--accent-ink); }
.semana { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.dia { background: var(--card); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow); overflow: hidden; }
.dia.hoy { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft), var(--shadow); }
.dia-cab { padding: 10px 14px; font-weight: 650; font-size: 14px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; }
.dia.hoy .dia-cab { background: var(--accent-soft); color: var(--accent); }
.dia-cab .hoy-txt { display: none; margin-left: auto; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.dia.hoy .dia-cab .hoy-txt { display: inline; }
.fila { display: flex; gap: 10px; padding: 10px 14px; border-top: 1px solid var(--border); }
.fila:first-of-type { border-top: 0; }
.fila-hora { flex: none; width: 42px; font-size: 11.5px; color: var(--muted); line-height: 1.35; font-variant-numeric: tabular-nums; }
.fila-asig { font-size: 13px; font-weight: 550; line-height: 1.35; overflow-wrap: anywhere; }
.fila-aula { font-size: 11.5px; color: var(--muted); font-weight: 400; margin-top: 2px; }
.fila.patio { background: var(--green-soft); }
.fila.patio .fila-asig { color: var(--green); }
.fila.en-curso { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
.fila.en-curso .fila-asig { color: var(--accent); }
.sin-clases { padding: 14px; color: var(--muted); font-size: 13px; }
.dia.sin-clase .fila { opacity: .45; }
.sin-clase-txt { margin-left: auto; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--red); }
.sin-clase-txt:empty { display: none; }
.dia.hoy.sin-clase .dia-cab .hoy-txt { display: none; }
.sin-clase-lista { margin-top: 24px; background: var(--card); border: 1px solid var(--border); border-radius: 18px; box-shadow: var(--shadow); padding: 14px 18px; }
.sin-clase-lista h2 { display: flex; align-items: center; gap: 8px; font-size: 15px; margin: 0 0 8px; }
.sin-clase-fila { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 0; border-top: 1px solid var(--border); font-size: 14px; }
.sin-clase-fila:first-of-type { border-top: 0; }
.sin-clase-fecha { text-transform: capitalize; }
.tipo-festivo .pill { background: var(--red-soft); color: var(--red); }
.tipo-vacaciones .pill { background: var(--blue-soft); color: var(--blue); }
.tipo-no-lectivo .pill { background: var(--green-soft); color: var(--green); }
.acciones-horario { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; }
.acciones-horario a, .acciones-horario button { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); border-radius: 999px; padding: 8px 14px; font: inherit; font-size: 13.5px;
  text-decoration: none; cursor: pointer; box-shadow: var(--shadow); }
.acciones-horario a:hover, .acciones-horario button:hover { border-color: var(--accent); color: var(--accent); }
.acciones-horario .principal { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: var(--on-accent); border: 0; }
.acciones-horario .principal:hover { color: var(--on-accent); filter: brightness(1.07); }
.campo { width: 100%; background: var(--card-2); border: 1px solid var(--border); border-radius: 8px; padding: 5px 8px;
  font: inherit; font-size: 12.5px; color: var(--text); outline: none; margin-bottom: 4px; }
.campo:focus { border-color: var(--accent); }
.fila-editar { padding: 10px 12px; border-top: 1px solid var(--border); }
.fila-editar .dos { display: flex; gap: 4px; }
.quitar, .anadir { border: 0; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; padding: 4px 0; }
.quitar:hover { color: var(--red); }
.anadir { padding: 10px 14px; color: var(--accent-ink); }
@media (max-width: 900px) { .semana { grid-template-columns: 1fr; } }
"""
