import hashlib
import html
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import quote

from temas import MODOS, PREVIAS_CSS, TEMAS, TEMAS_CSS, con_tema, elegido

# Cada etapa tiene su propio Aules (en ESO, uno por provincia). La clave es la última parte de su dirección.
PORTALES = {
    "fp": ("FP presencial", "https://aules.edu.gva.es/fp"),
    "batxillerat": ("Bachillerato", "https://aules.edu.gva.es/batxillerat"),
    "eso46": ("ESO · Valencia", "https://aules.edu.gva.es/eso46"),
    "eso03": ("ESO · Alicante", "https://aules.edu.gva.es/eso03"),
    "eso12": ("ESO · Castellón", "https://aules.edu.gva.es/eso12"),
    "semipresencial": ("FP semipresencial", "https://aules.edu.gva.es/semipresencial"),
    "fpa": ("Personas adultas (FPA)", "https://aules.edu.gva.es/fpa"),
}


def portal_de(base_url):
    """Clave de la etapa a partir de la dirección de Aules ("fp" si no se reconoce)."""
    clave = (base_url or "").rstrip("/").rsplit("/", 1)[-1]
    return clave if clave in PORTALES else "fp"


DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
KIND_LABELS = {"examen": "Examen", "tarea": "Tarea", "aviso": "Aviso"}
KIND_ICONS = {"examen": "graduation-cap", "tarea": "clipboard-list", "aviso": "megaphone"}
DUE_PREFIXES = {"Abre": "abre ", "Cierra": "cierra "}
URL_RE = re.compile(r"https?://[^\s<>\"']+")

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


def format_due(ts):
    if not ts:
        return "Sin fecha límite"
    d = datetime.fromtimestamp(ts)
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]} · {d.strftime('%H:%M')}"


def rel_time(ts, now_ts):
    if not ts:
        return "Sin fecha"
    diff = ts - now_ts
    future = diff > 0
    diff = abs(diff)
    if diff >= 86400:
        n, unit = round(diff / 86400), "día"
    elif diff >= 3600:
        n, unit = round(diff / 3600), "hora"
    else:
        n, unit = max(1, round(diff / 60)), "minuto"
    unit += "s" if n != 1 else ""
    return f"en {n} {unit}" if future else f"hace {n} {unit}"


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


def linkify(escaped_text):
    def repl(m):
        url, trail = m.group(0), ""
        while url and url[-1] in ".,;:)":
            url, trail = url[:-1], url[-1] + trail
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>{trail}'

    return URL_RE.sub(repl, escaped_text)


# Colores del tema clásico; los demás temas (temas.py) cambian lo que necesitan.
CLARO_VARS = """
  --bg: #f6f2ea; --bg-grad: #f6f2ea; --card: #ffffff; --card-2: #fbf8f2;
  --text: #221f1a; --muted: #776f63; --border: #e7dfd2; --shadow: 0 1px 0 rgba(60,45,20,.05), 0 8px 24px rgba(60,45,20,.06);
  --accent: #ee5a2c; --accent-2: #ee5a2c; --accent-ink: #c2441c; --accent-soft: #ffe3d8; --accent-sombra: #c2441c; --on-accent: #ffffff;
  --rotulador: #ffd166; --rotulador-ink: #6b4d00; --rotulador-trazo: #ffd166;
  --ahora-bg: #221f1a; --ahora-text: #f6f2ea; --ahora-muted: #bdb4a6; --ahora-borde: #221f1a;
  --red: #c2361c; --red-soft: #ffe3d8; --amber: #946400; --amber-soft: #fff1c9;
  --green: #2f7a52; --green-soft: #dcefe4; --blue: #4a52c9; --blue-soft: #e3e6ff;
  --orange: #ee5a2c; --orange-soft: #ffe3d8; --gray-soft: #efe9df;
  --av-fg: 55% 32%; --av-bg: 75% 91%; color-scheme: light;
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
.eyebrow { font-size: 12px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); margin: 0 0 6px; }
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
.acc-avatar { width: 30px; height: 30px; border-radius: 50%; background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff;
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

.next { display: flex; align-items: center; gap: 14px; background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff;
  border-radius: 18px; padding: 18px 20px; margin-bottom: 28px; box-shadow: 0 10px 30px rgba(91,91,246,.25); }
.next-icon { flex: none; width: 44px; height: 44px; border-radius: 12px; background: rgba(255,255,255,.18); display: grid; place-items: center; }
.next-body { min-width: 0; flex: 1; }
.next-label { font-size: 12px; opacity: .85; text-transform: uppercase; letter-spacing: .07em; font-weight: 600; }
.next-title { font-weight: 650; font-size: 17px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.next-course { font-size: 13px; opacity: .85; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.next-due { text-align: right; flex: none; }
.next-due .due-rel { font-weight: 700; font-size: 15px; background: rgba(255,255,255,.2); color: #fff; padding: 4px 12px; }
.next-due .due-abs { color: rgba(255,255,255,.85); font-size: 12.5px; }

.ahora { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; background: var(--card); border: 1px solid var(--border);
  border-radius: 18px; box-shadow: var(--shadow); padding: 16px 20px; margin-bottom: 16px; text-decoration: none; color: inherit; }
.ahora .ahora-bloque + .ahora-bloque { border-left: 1px solid var(--border); padding-left: 16px; }
.ahora-label { display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }
.ahora-asig { font-weight: 650; font-size: 16px; line-height: 1.3; overflow-wrap: anywhere; }
.ahora-info { font-size: 12.5px; color: var(--muted); margin-top: 2px; }
a.ahora:hover { border-color: var(--accent); }
.ahora-ver { margin-left: auto; display: inline-flex; align-items: center; gap: 4px; color: var(--accent); letter-spacing: 0; text-transform: none; font-weight: 600; }
.ahora.en-clase #ahora-asig { color: var(--accent); }
.ahora.en-recreo #ahora-asig { color: var(--green); }
.sin-horario:hover { border-color: var(--accent); }
@media (max-width: 680px) {
  .ahora { grid-template-columns: 1fr; gap: 12px; }
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
details.desc > summary { cursor: pointer; font-size: 13px; color: var(--accent); font-weight: 550; display: inline-flex; align-items: center; gap: 4px; user-select: none; }
.desc-body { margin-top: 8px; padding: 12px 14px; background: var(--card-2); border: 1px solid var(--border); border-radius: 12px;
  font-size: 14px; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--text); }
.desc-body a { color: var(--accent); }

.files { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.file { display: inline-flex; align-items: center; gap: 8px; max-width: 100%; text-decoration: none; color: var(--text); font-size: 13px;
  border: 1px solid var(--border); background: var(--card); border-radius: 10px; padding: 5px 10px 5px 5px; transition: border-color .15s, transform .15s; }
.file:hover { border-color: var(--accent); transform: translateY(-1px); }
.file .ext { font-size: 10px; font-weight: 700; background: var(--accent-soft); color: var(--accent); border-radius: 6px; padding: 3px 6px; }
.file .fname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

details.group { margin: 4px 4px 2px; }
details.group > summary { cursor: pointer; font-size: 13px; color: var(--muted); font-weight: 550; padding: 8px; border-radius: 10px; user-select: none; display: flex; align-items: center; gap: 6px; }
details.group > summary:hover { background: var(--card-2); }
details.group .item { opacity: .85; }
.mat-sec { padding: 4px 8px 10px; }
.mat-sec-nombre { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
.mat-sec .files { margin-top: 0; }
.file .pill-new { font-size: 10px; padding: 1px 6px; }

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
.post-link { display: inline-flex; align-items: center; gap: 4px; margin-top: 8px; font-size: 12.5px; color: var(--muted); text-decoration: none; }
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
.nota-fb a { color: var(--accent); }
.nota-valor { flex: none; font-size: 20px; font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; white-space: nowrap; max-width: 50%; overflow: hidden; text-overflow: ellipsis; }
.nota-max { font-size: 12.5px; font-weight: 500; color: var(--muted); margin-left: 3px; }
.nota-item { margin-top: 10px; border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 12px; background: var(--card); }
.nota-item .nota-nombre { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--accent); }
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
.mensaje-texto a { color: var(--accent); }
.ahora-tareas { display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; font-size: 12px; font-weight: 600;
  padding: 3px 9px; border-radius: 999px; background: var(--blue-soft); color: var(--blue); max-width: 100%; }
.ahora-tareas span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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
/* El menú no puede quedar cortado ni tapado por la siguiente asignatura. */
.course:has(details.mas[open]) { overflow: visible; position: relative; z-index: 6; }
.ia-cadena { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted); max-width: 100%; }
.ia-cadena select { font: inherit; font-size: 12.5px; color: var(--text); background: var(--card); border: 1px solid var(--border);
  border-radius: 999px; padding: 3px 8px; max-width: 320px; min-width: 0; text-overflow: ellipsis; }
.ia-cadena select:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.ia-bloque { margin-top: 8px; padding: 10px 12px; border: 1px solid var(--border); border-left: 3px solid var(--accent);
  background: var(--card-2); border-radius: 10px; }
.ia-titulo { display: flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 650; color: var(--accent);
  text-transform: uppercase; letter-spacing: .04em; margin-bottom: 6px; }
.ia-texto { margin: 0; font: inherit; font-size: 13.5px; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--text); }
.ia-cargando { color: var(--muted); font-size: 13px; border-left-color: var(--muted); }
.ia-error { border-left-color: var(--red); color: var(--red); font-size: 13px; }

@media (max-width: 680px) {
  .stats { grid-template-columns: repeat(2, 1fr); }
  .item { flex-direction: column; gap: 8px; }
  .due { text-align: left; min-width: 0; display: flex; align-items: center; gap: 8px; }
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
"""

REPORT_JS = """
(function () {
  var rtf = new Intl.RelativeTimeFormat('es', { numeric: 'auto' });
  var fechaHoy = document.getElementById('fecha-hoy');
  if (fechaHoy) {
    var texto = new Intl.DateTimeFormat('es', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());
    fechaHoy.textContent = texto.charAt(0).toUpperCase() + texto.slice(1);
  }
  function rel(ts) {
    var diff = ts * 1000 - Date.now(), a = Math.abs(diff);
    if (a >= 86400000) return rtf.format(Math.round(diff / 86400000), 'day');
    if (a >= 3600000) return rtf.format(Math.round(diff / 3600000), 'hour');
    return rtf.format(Math.round(diff / 60000), 'minute');
  }
  function refreshTimes() {
    document.querySelectorAll('[data-due]').forEach(function (el) {
      var ts = +el.getAttribute('data-due');
      var r = el.querySelector('.due-rel');
      if (ts && r) r.textContent = (el.getAttribute('data-prefix') || '') + rel(ts);
    });
    var up = document.getElementById('updated-rel');
    if (up) up.textContent = rel(+up.getAttribute('data-ts'));
  }
  refreshTimes();
  setInterval(refreshTimes, 60000);

  var filter = 'all', query = '';
  var items = Array.prototype.slice.call(document.querySelectorAll('.item'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('details.forum-panel'));
  function apply() {
    items.forEach(function (it) {
      var okF = filter === 'all' || (filter === 'new' ? it.dataset.new === '1' : it.dataset.kind === filter);
      var okQ = !query || it.dataset.search.indexOf(query) !== -1;
      it.hidden = !(okF && okQ);
    });
    var filtering = filter !== 'all' || query;
    document.querySelectorAll('details.group').forEach(function (g) {
      var any = g.querySelector('.item:not([hidden])');
      g.hidden = !any;
      if (filtering && any) g.open = true;
    });
    document.querySelectorAll('.empty-course').forEach(function (p) { p.hidden = !!filtering; });
    var visible = 0;
    document.querySelectorAll('.course').forEach(function (sec) {
      sec.hidden = filtering && !sec.querySelector('.item:not([hidden])');
      if (!sec.hidden) visible++;
    });
    panels.forEach(function (panel) {
      var hits = 0;
      panel.querySelectorAll('.post').forEach(function (p) {
        p.hidden = !!query && p.dataset.search.indexOf(query) === -1;
        if (!p.hidden) hits++;
      });
      panel.hidden = filter !== 'all' || (!!query && hits === 0);
      if (query && hits) panel.open = true;
      if (!panel.hidden) visible++;
    });
    document.getElementById('empty').hidden = visible > 0;
  }
  document.querySelectorAll('.chip').forEach(function (c) {
    c.addEventListener('click', function () {
      document.querySelectorAll('.chip').forEach(function (x) { x.classList.remove('active'); });
      c.classList.add('active');
      filter = c.dataset.filter;
      apply();
    });
  });
  var input = document.getElementById('q');
  input.addEventListener('input', function () { query = input.value.trim().toLowerCase(); apply(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== input) { e.preventDefault(); input.focus(); }
    if (e.key === 'Escape') { input.value = ''; query = ''; apply(); input.blur(); }
  });

  var account = document.querySelector('details.account');
  document.addEventListener('click', function (e) {
    if (account && account.open && !account.contains(e.target)) account.open = false;
  });
  function cerrarMenus(excepto) {
    document.querySelectorAll('details.mas[open]').forEach(function (d) { if (d !== excepto) d.open = false; });
  }
  document.addEventListener('click', function (e) {
    var menu = e.target.closest('details.mas');
    cerrarMenus(menu);
    if (menu && e.target.closest('.menu-item')) menu.open = false;
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') cerrarMenus(null); });

  var refresh = document.getElementById('refresh-form');
  var refreshBtn = refresh && refresh.querySelector('button');
  function setLoading(on) {
    if (!refreshBtn) return;
    refreshBtn.disabled = on;
    refreshBtn.classList.toggle('loading', on);
  }
  if (refresh) refresh.addEventListener('submit', function () { setTimeout(function () { setLoading(true); }, 0); });

  document.querySelectorAll('.item[data-id]').forEach(function (caja) {
    var id = caja.dataset.id, salida = caja.querySelector('.ia-out');
    var botones = caja.querySelectorAll('[data-accion]');
    if (!salida) return;
    botones.forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var accion = btn.dataset.accion;
        botones.forEach(function (b) { b.disabled = true; });
        var aviso = document.createElement('div');
        aviso.className = 'ia-bloque ia-cargando';
        aviso.textContent = accion === 'resumen' ? 'Resumiendo…' : 'Abriendo el selector de carpeta…';
        salida.prepend(aviso);
        try {
          var carpeta = '';
          if (accion === 'borrador') {
            var rc = await fetch('/ia/carpeta', { method: 'POST' });
            var dc = await rc.json();
            if (dc.error) throw new Error(dc.error);
            if (!dc.carpeta) { aviso.remove(); return; }
            carpeta = dc.carpeta;
            var cadena = caja.querySelector('[data-anterior]');
            aviso.textContent = (cadena && cadena.value ? 'Leyendo tu respuesta a «' + cadena.selectedOptions[0].textContent.replace(/ [(][^()]*[)]$/, '') + '», ' : 'Leyendo ')
              + 'adjuntos y temario, y escribiendo el borrador en ' + carpeta
              + '… Tarda varios minutos (con modelos gratuitos, hasta 10). Puedes seguir usando la página.';
          }
          var r = await fetch('/ia/' + accion, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id, carpeta: carpeta, anterior: (caja.querySelector('[data-anterior]') || {}).value || '' })
          });
          var d = await r.json();
          aviso.remove();
          var bloque = document.createElement('div');
          bloque.className = 'ia-bloque';
          if (d.error) {
            bloque.classList.add('ia-error');
            bloque.textContent = d.error;
          } else if (accion === 'resumen') {
            var t = document.createElement('div'); t.className = 'ia-titulo'; t.textContent = 'Resumen IA';
            var p = document.createElement('pre'); p.className = 'ia-texto'; p.textContent = d.resumen;
            bloque.append(t, p);
          } else {
            var t2 = document.createElement('div'); t2.className = 'ia-titulo'; t2.textContent = 'Borrador en ' + d.carpeta;
            var l = document.createElement('div'); l.className = 'ia-texto'; l.textContent = (d.archivos || []).join(', ');
            bloque.append(t2, l);
            if (d.notas) { var n = document.createElement('pre'); n.className = 'ia-texto'; n.textContent = d.notas; bloque.append(n); }
          }
          salida.prepend(bloque);
        } catch (e) {
          aviso.classList.add('ia-error');
          aviso.classList.remove('ia-cargando');
          aviso.textContent = 'No se pudo completar: ' + e.message;
        } finally {
          botones.forEach(function (b) { b.disabled = false; });
        }
      });
    });
  });

})();
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

REPORT_JS_FIN = """
(function () {
  // Versión nueva de la app publicada en GitHub: se avisa y solo se instala si pulsas «Actualizar».
  var caja = document.getElementById('aviso-version');
  if (!caja) return;
  function texto(etiqueta, contenido, clase) {
    var e = document.createElement(etiqueta);
    if (clase) e.className = clase;
    e.textContent = contenido;
    return e;
  }
  // Hasta que la app no arranca con la versión nueva no se recarga (la vieja sigue respondiendo unos segundos).
  function esperarReinicio(version, intentos) {
    setTimeout(function () {
      fetch('/api/actualizacion', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.version === version || intentos <= 0) location.reload(); else esperarReinicio(version, intentos - 1);
      }).catch(function () { if (intentos <= 0) location.reload(); else esperarReinicio(version, intentos - 1); });
    }, 2000);
  }
  fetch('/api/actualizacion', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
    if (!d || !d.nueva) return;
    var clave = 'aules-version-pospuesta';
    try { if (localStorage.getItem(clave) === d.nueva.version) return; } catch (e) {}
    var cuerpo = document.createElement('div');
    cuerpo.className = 'av-texto';
    cuerpo.append(texto('strong', 'Hay una versión nueva de la app: ' + d.nueva.version),
      texto('div', 'Tienes la ' + d.version + '. Tus datos, sesión y ajustes se mantienen.'));
    if (d.nueva.cambios && d.nueva.cambios.length) {
      var lista = document.createElement('ul');
      d.nueva.cambios.forEach(function (c) { lista.append(texto('li', c)); });
      cuerpo.append(lista);
    }
    var error = texto('div', '', 'av-error');
    error.hidden = true;
    cuerpo.append(error);
    var botones = document.createElement('div');
    botones.className = 'av-botones';
    var luego = texto('button', 'Más tarde', 'boton-sec');
    var ya = texto('button', 'Actualizar', 'boton-pri');
    luego.type = ya.type = 'button';
    luego.addEventListener('click', function () {
      try { localStorage.setItem(clave, d.nueva.version); } catch (e) {}
      caja.hidden = true;
    });
    ya.addEventListener('click', async function () {
      ya.disabled = luego.disabled = true;
      ya.textContent = 'Actualizando…';
      error.hidden = true;
      try {
        var r = await fetch('/api/actualizar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        var res = {};
        try { res = await r.json(); } catch (e) {}
        if (!r.ok) throw new Error(res.error || 'No se pudo actualizar (' + r.status + ')');
        ya.textContent = 'Reiniciando…';
        esperarReinicio(res.version, 30);
      } catch (e) {
        error.textContent = e.message;
        error.hidden = false;
        ya.disabled = luego.disabled = false;
        ya.textContent = 'Reintentar';
      }
    });
    botones.append(luego, ya);
    caja.append(cuerpo, botones);
    caja.hidden = false;
  }).catch(function () {});
})();

(function () {
  var refresh = document.getElementById('refresh-form');
  var refreshBtn = refresh && refresh.querySelector('button');
  function setLoading(on) {
    if (!refreshBtn) return;
    refreshBtn.disabled = on;
    refreshBtn.classList.toggle('loading', on);
  }

  // Si el informe tiene más de 30 min (p.ej. al abrirlo por la mañana), se actualiza solo una vez.
  var up = document.getElementById('updated-rel');
  if (refresh && up && Date.now() - (+up.getAttribute('data-ts')) * 1000 > 30 * 60 * 1000) {
    var last = 0;
    try { last = +sessionStorage.getItem('aules-auto-refresh') || 0; } catch (e) {}
    if (Date.now() - last > 5 * 60 * 1000) {
      try { sessionStorage.setItem('aules-auto-refresh', String(Date.now())); } catch (e) {}
      setLoading(true);
      fetch('/refresh', { method: 'POST' }).then(function (r) {
        if (r.url.indexOf('/login') !== -1) { location.href = '/login'; return; }
        if (!r.ok) throw new Error(String(r.status));
        location.reload();
      }).catch(function () { setLoading(false); });
    }
  }

  // La app revisa Aules cada minuto y medio: si ha cambiado algo, la página se recarga sola.
  var informe = document.getElementById('informe');
  var firma = informe && informe.dataset.firma;
  function ocupado() {
    var activo = document.activeElement;
    if (activo && (activo.tagName === 'INPUT' || activo.tagName === 'TEXTAREA') && activo.value) return true;
    if (document.querySelector('.ia-cargando') || document.querySelector('dialog[open]')) return true;
    var menu = document.querySelector('details.account');
    return !!(menu && menu.open);
  }
  async function vigilar() {
    try {
      var r = await fetch('/api/informe', { cache: 'no-store' });
      if (r.url.indexOf('/login') !== -1) { location.href = '/login'; return; }
      if (!r.ok) return;
      var d = await r.json();
      revisando = !!d.comprobando;
      setLoading(revisando);
      estadoAules(d);
      if (d.actualizado && up) {
        up.setAttribute('data-ts', d.actualizado);
        var abs = document.getElementById('updated-abs'), f = new Date(d.actualizado * 1000);
        if (abs) abs.textContent = String(f.getDate()).padStart(2, '0') + '/' + String(f.getMonth() + 1).padStart(2, '0')
          + ' ' + String(f.getHours()).padStart(2, '0') + ':' + String(f.getMinutes()).padStart(2, '0');
      }
      if (firma && d.firma && d.firma !== firma && !ocupado()) {
        try { sessionStorage.setItem('aules-scroll', String(window.scrollY)); } catch (e) {}
        location.reload();
      }
    } catch (e) {}
  }
  // Si Aules está caído: popup (una vez por caída; si lo cierras queda solo la franja de arriba) y, cuando
  // vuelve, «Aules vuelve a funcionar». Lo que se ve mientras tanto es lo último guardado.
  var popup = document.getElementById('popup-aules');
  var franja = document.getElementById('aviso-revision');
  var ocultarPopup = null;
  function guardado(clave, valor) {
    try {
      if (valor === undefined) return sessionStorage.getItem(clave);
      if (valor === null) sessionStorage.removeItem(clave); else sessionStorage.setItem(clave, valor);
    } catch (e) {}
    return null;
  }
  function hace(ts) {
    var min = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
    if (min < 1) return 'de hace un momento';
    if (min < 60) return 'de hace ' + min + ' min';
    var h = Math.round(min / 60);
    return h < 24 ? 'de hace ' + h + ' h' : 'de hace ' + Math.round(h / 24) + ' días';
  }
  function abrirPopup(ok, titulo, texto) {
    clearTimeout(ocultarPopup);
    popup.classList.toggle('ok', ok);
    popup.querySelector('strong').textContent = titulo;
    popup.querySelector('p').textContent = texto;
    popup.hidden = false;
  }
  function estadoAules(d) {
    if (!popup) return;
    var mantenimiento = d.error_tipo === 'mantenimiento';
    var titulo = mantenimiento ? 'Aules está en mantenimiento' : 'No se puede conectar con Aules';
    if (franja) {
      franja.hidden = !d.error;
      franja.lastElementChild.textContent = titulo + '. Se muestra lo último guardado.';
    }
    if (d.error) {
      guardado('aules-caido', '1');
      if (guardado('aules-popup-cerrado') === String(d.error_desde) || (!popup.hidden && !popup.classList.contains('ok'))) return;
      popup.dataset.desde = String(d.error_desde);
      abrirPopup(false, titulo, (mantenimiento ? 'Aules no está disponible ahora mismo. '
        : 'Puede que Aules esté caído o que falle tu conexión a internet. ')
        + 'Ves lo último guardado' + (d.actualizado ? ' (' + hace(d.actualizado) + ')' : '')
        + '. La app vuelve a intentarlo sola y te avisará aquí cuando funcione.');
    } else if (guardado('aules-caido') && !d.comprobando) {
      guardado('aules-caido', null);
      guardado('aules-popup-cerrado', null);
      abrirPopup(true, 'Aules vuelve a funcionar', 'Ya tienes tus tareas y notas al día.');
      ocultarPopup = setTimeout(function () { popup.hidden = true; }, 6000);
    } else if (!popup.classList.contains('ok')) {
      popup.hidden = true;
    }
  }
  if (popup) popup.querySelector('.pa-cerrar').addEventListener('click', function () {
    popup.hidden = true;
    if (!popup.classList.contains('ok')) guardado('aules-popup-cerrado', String(popup.dataset.desde || ''));
  });

  // Mientras se revisa Aules se mira cada 3 s, para enseñar los datos nuevos en cuanto llegan; si no, cada 20 s.
  var revisando = false;
  async function ciclo() {
    await vigilar();
    setTimeout(ciclo, revisando ? 3000 : 20000);
  }
  if (informe) ciclo();
  try {
    var y = sessionStorage.getItem('aules-scroll');
    if (y !== null) { sessionStorage.removeItem('aules-scroll'); window.scrollTo(0, +y); }
  } catch (e) {}
})();
"""

LOGIN_CSS = """
.auth { min-height: 100vh; display: grid; place-items: center; padding: 24px 16px; }
.auth-card { width: 100%; max-width: 400px; background: var(--card); border: 1px solid var(--border); border-radius: 22px; box-shadow: var(--shadow); padding: 32px 28px; }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 650; font-size: 14px; color: var(--muted); margin-bottom: 24px; }
.brand-mark { width: 38px; height: 38px; border-radius: 11px; background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff;
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
  padding: 12px; font: inherit; font-weight: 600; font-size: 15px; color: #fff; background: linear-gradient(135deg, var(--accent), var(--accent-2));
  cursor: pointer; box-shadow: 0 8px 20px rgba(91,91,246,.28); transition: transform .1s, filter .15s; text-decoration: none; }
.btn-primary:hover { filter: brightness(1.06); }
.btn-primary:active { transform: translateY(1px); }
.btn-primary[disabled] { opacity: .85; cursor: progress; }
.btn-link { display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 14px; font-size: 13.5px; color: var(--muted);
  text-decoration: none; background: none; border: 0; font: inherit; cursor: pointer; width: 100%; }
.btn-link:hover { color: var(--text); }
.recordar { display: flex; align-items: center; gap: 8px; font-size: 13.5px; margin: 2px 0 6px; cursor: pointer; user-select: none; }
.recordar input { width: 16px; height: 16px; accent-color: var(--accent); margin: 0; }
.auth-note { display: flex; gap: 8px; align-items: flex-start; margin: 22px 0 0; padding-top: 18px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12.5px; }
.auth-note .i { margin-top: 1px; color: var(--green); }
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

AJUSTES_JS = """
(function () {
  var form = document.getElementById('form-ajustes');
  var campo = document.getElementById('campo-modelo');
  var estado = document.getElementById('estado-modelos');
  var btnCargar = document.getElementById('cargar-modelos');
  var btnManual = document.getElementById('modo-manual');

  function valorActual() {
    var el = document.querySelector('[name=modelo]');
    return el ? el.value : '';
  }
  function escribirAMano(valor) {
    campo.classList.remove('select');
    campo.querySelector('select, input[name=modelo]').remove();
    var input = document.createElement('input');
    input.name = 'modelo';
    input.value = valor || '';
    input.placeholder = 'claude-opus-5';
    input.autocomplete = 'off';
    campo.append(input);
    input.focus();
    btnManual.hidden = true;
    estado.textContent = '';
  }
  btnManual.addEventListener('click', function () { escribirAMano(valorActual()); });

  function restaurarLista(valor) {
    if (campo.classList.contains('select')) return;
    campo.querySelector('input[name=modelo]').remove();
    var select = document.createElement('select');
    select.name = 'modelo';
    if (valor) {
      var o = document.createElement('option');
      o.value = valor; o.textContent = valor; o.selected = true;
      select.append(o);
    }
    campo.classList.add('select');
    campo.append(select);
    btnManual.hidden = false;
  }

  function opcionProveedor() {
    return form.proveedor.options[form.proveedor.selectedIndex];
  }
  function necesitaClave() {
    return opcionProveedor().dataset.clave === '1';
  }
  form.proveedor.addEventListener('change', function () {
    // Cada proveedor trae su URL puesta; solo "otro compatible" la deja vacía para escribirla.
    form.base_url.value = opcionProveedor().dataset.url || '';
    estado.textContent = '';
    if (form.api_key.value.trim() || !necesitaClave()) cargar(false);
  });

  async function cargar(silencioso) {
    if (!campo.classList.contains('select')) return;
    var actual = valorActual();
    estado.textContent = 'Consultando tu proveedor…';
    btnCargar.disabled = true;
    try {
      var r = await fetch('/ajustes/modelos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          proveedor: form.proveedor.value,
          api_key: form.api_key.value,
          base_url: form.base_url.value
        })
      });
      var d = await r.json();
      if (d.error) {
        var faltaClave = d.error.indexOf('API key') !== -1;
        estado.textContent = (silencioso && faltaClave) ? '' : d.error;
        // Si el proveedor no deja listar modelos, al menos que se pueda escribir a mano.
        if (!faltaClave) escribirAMano(actual);
        return;
      }
      var select = campo.querySelector('select');
      if (!select) return;
      select.innerHTML = '';
      if (!d.modelos.length) { estado.textContent = 'Tu proveedor no devolvió ningún modelo.'; return; }
      var ids = d.modelos.map(function (m) { return m.id; });
      if (actual && ids.indexOf(actual) === -1) {
        var guardado = document.createElement('option');
        guardado.value = actual; guardado.textContent = actual + ' (guardado)'; guardado.selected = true;
        select.append(guardado);
      }
      function miles(n) { return n >= 1000 ? Math.round(n / 1000) + 'k' : String(n); }
      d.modelos.forEach(function (m) {
        var o = document.createElement('option');
        o.value = m.id;
        var extra = [];
        if (m.salida) extra.push('respuesta ' + miles(m.salida));
        if (m.contexto) extra.push('lee ' + miles(m.contexto));
        if (m.gratis) extra.push('gratis');
        if (m.salida && m.salida < 6000) extra.push('respuestas cortas');
        o.textContent = m.id + (extra.length ? '  ·  ' + extra.join(' · ') : '');
        if (m.id === actual) o.selected = true;
        select.append(o);
      });
      estado.textContent = d.modelos.length + ' modelos. Los primeros son los que pueden escribir respuestas mas largas'
        + ' (mejor para «Hacer borrador»).';
    } catch (e) {
      estado.textContent = silencioso ? '' : 'No se pudo consultar: ' + e.message;
    } finally {
      btnCargar.disabled = false;
    }
  }
  btnCargar.addEventListener('click', function () { restaurarLista(valorActual()); cargar(false); });
  form.api_key.addEventListener('change', function () { if (form.api_key.value.trim()) cargar(false); });
  if (form.dataset.clave === '1' || !necesitaClave()) cargar(true);
})();
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
"""


def _nav(activa="", ancha=False):
    enlaces = (("inicio", "/", "inbox", "Inicio"), ("horario", "/horario", "calendar", "Horario"),
               ("materiales", "/materiales", "folder", "Materiales"), ("profesores", "/profesores", "mail", "Profesores"))
    links = "".join(
        f'<a href="{url}"{" class=\"activa\" aria-current=\"page\"" if clave == activa else ""}>{icon(ic, 15)}<span>{texto}</span></a>'
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


def _desc_html(summary, label):
    if not summary:
        return ""
    return (
        f'<details class="desc"><summary>{icon("chevron-right", 14, "chev")}{label}</summary>'
        f'<div class="desc-body">{linkify(html.escape(summary))}</div></details>'
    )


def _files_html(attachments):
    if not attachments:
        return ""
    return '<div class="files">' + "".join(
        f'<a class="file" href="{html.escape(quote(att["path"]))}" target="_blank" rel="noopener" title="{html.escape(att["filename"])}">'
        f'<span class="ext">{html.escape(file_ext(att["filename"]))}</span>'
        f'<span class="fname">{html.escape(att["filename"])}</span></a>'
        for att in attachments
    ) + "</div>"


RE_CADENA = re.compile(
    r"(pr[aà]ctica|tarea|ejercicio|activitat|actividad|entrega)\s+(anterior|previa|pr[eè]via)"
    r"|continuaci[oó]n de|partiendo de (la|el|tu)|a partir de (la|el|tu) (pr[aà]ctica|tarea|ejercicio)", re.I)


def sugerir_anterior(a, candidatas):
    """La tarea que esta continúa: «Práctica 2» → «Práctica 1», o la última anterior si el enunciado lo dice."""
    nombre = a["name"].lower().strip()
    for c in candidatas:
        otro = c["name"].lower().strip()
        i = next((k for k, (x, y) in enumerate(zip(nombre, otro)) if x != y), None)
        if i is None or not (nombre[i].isdigit() and otro[i].isdigit()):
            continue
        while i > 0 and nombre[i - 1].isdigit():
            i -= 1
        if int(re.match(r"\d+", otro[i:]).group()) == int(re.match(r"\d+", nombre[i:]).group()) - 1:
            return c["id"]
    if RE_CADENA.search(f'{a.get("summary", "")} {a.get("summary_file", "")}') and a["duedate"]:
        previas = [c for c in candidatas if c["duedate"] and c["duedate"] < a["duedate"]]
        if previas:
            return max(previas, key=lambda c: c["duedate"])["id"]
    return ""


def _cadena_html(a, datos, candidatas, cache):
    if not candidatas:
        return ""
    sugerida = sugerir_anterior(a, candidatas)
    elegida = datos["anterior"] if "anterior" in datos else sugerida
    opciones = ['<option value="">Ninguna (tarea independiente)</option>']
    for c in sorted(candidatas, key=lambda c: (not c["duedate"], -(c["duedate"] or 0))):
        if c["done"] and c.get("status"):
            estado = "entregada"
        elif (cache.get(c["id"]) or {}).get("borrador"):
            estado = "borrador IA"
        else:
            estado = "sin respuesta"
        extra = " · sugerida" if c["id"] == sugerida else ""
        opciones.append(
            f'<option value="{html.escape(c["id"])}"{" selected" if c["id"] == elegida else ""}>'
            f'{html.escape(c["name"][:70])} ({estado}{extra})</option>'
        )
    return (
        f'<label class="ia-cadena" title="Si esta tarea sigue a otra, la IA parte de tu respuesta a aquella: '
        f'lo que entregaste en Aules o, si no, tu borrador">{icon("link", 15)}<span>Continúa de</span>'
        f'<select data-anterior>{"".join(opciones)}</select></label>'
    )


def _ia_html(a, cache, candidatas=()):
    if a["kind"] == "aviso":
        return ""
    cache = cache or {}
    datos = cache.get(a["id"], {})
    salida = ""
    if datos.get("resumen"):
        salida += (
            f'<div class="ia-bloque"><div class="ia-titulo">{icon("sparkles", 13)}Resumen IA</div>'
            f'<pre class="ia-texto">{html.escape(datos["resumen"])}</pre></div>'
        )
    borrador = datos.get("borrador") or {}
    if borrador:
        notas = f'<pre class="ia-texto">{html.escape(borrador.get("notas", ""))}</pre>' if borrador.get("notas") else ""
        salida += (
            f'<div class="ia-bloque"><div class="ia-titulo">{icon("folder", 13)}'
            f'Borrador en {html.escape(borrador.get("carpeta", ""))}</div>'
            f'<div class="ia-texto">{html.escape(", ".join(borrador.get("archivos", [])))}</div>{notas}</div>'
        )
    return f'<div class="ia-out">{salida}</div>'


def _ia_menu(a, cache, candidatas=()):
    if a["kind"] == "aviso":
        return ""
    datos = (cache or {}).get(a["id"], {})
    return (
        _opcion('data-accion="resumen"', "sparkles", "Resumen IA")
        + _opcion('data-accion="borrador"', "pencil", "Hacer borrador")
        + _cadena_html(a, datos, candidatas, cache or {})
    )


def _opcion(atributos, ic, texto, titulo=""):
    """Una opción del menú «⋯» de cada tarea."""
    titulo = f' title="{html.escape(titulo)}"' if titulo else ""
    return f'<button type="button" class="menu-item" {atributos}{titulo}>{icon(ic, 15)}<span>{texto}</span></button>'


def _menu_mas(*grupos):
    """Botón «⋯» con las opciones de la tarea, separadas por grupos. Vacío si no hay ninguna."""
    grupos = [g for g in grupos if g]
    if not grupos:
        return ""
    return (f'<details class="mas"><summary class="icon-btn mas-btn" aria-label="Más opciones" title="Más opciones">'
            f'{icon("more", 18)}</summary><div class="menu mas-menu">'
            + '<div class="mas-sep" role="separator"></div>'.join(grupos) + "</div></details>")


def _material_html(mats):
    secciones = {}
    for m in mats:
        secciones.setdefault(m["section"] or "Material", []).append(m)
    bloques = []
    for nombre, lista in secciones.items():
        chips = "".join(
            f'<a class="file" href="/material/{html.escape(quote(m["id"]))}" target="_blank" rel="noopener" '
            f'title="{html.escape(m["filename"])}">'
            f'<span class="ext">{"WEB" if m["externo"] else html.escape(file_ext(m["filename"]))}</span>'
            f'<span class="fname">{html.escape(m["name"])}</span>'
            + (f'<span class="pill pill-new">{icon("sparkles", 11)}Nuevo</span>' if m.get("is_new") else "")
            + "</a>"
            for m in lista
        )
        bloques.append(
            f'<div class="mat-sec"><div class="mat-sec-nombre">{html.escape(nombre)}</div>'
            f'<div class="files">{chips}</div></div>'
        )
    nuevos = sum(1 for m in mats if m.get("is_new"))
    etiqueta = f"Material del curso ({len(mats)})" + (f" · {nuevos} nuevo{'s' if nuevos != 1 else ''}" if nuevos else "")
    return (
        f'<details class="group"{" open" if nuevos else ""}>'
        f'<summary>{icon("chevron-right", 14, "chev")}{etiqueta}</summary>{"".join(bloques)}</details>'
    )


def _practicas_html(ejercicios, nota_de_actividad, now_ts):
    filas = []
    hechos = 0
    for pr in ejercicios:
        nota = nota_de_actividad.get(pr["activity"])
        hechos += bool(nota)
        estado = (
            f'<span class="pill pill-done">{icon("check", 12)}Hecho · {html.escape(_texto_nota(nota["grade"]))}</span>' if nota
            else '<span class="pill pill-aviso">Sin hacer</span>'
        )
        nuevo = f'<span class="pill pill-new">{icon("sparkles", 11)}Nuevo</span>' if pr.get("is_new") else ""
        filas.append(
            f'<a class="practica{" is-done" if nota else ""}" href="{html.escape(pr["url"])}" target="_blank" rel="noopener noreferrer">'
            f'<span class="practica-nombre">{html.escape(pr["name"])}</span>{nuevo}{estado}{icon("external-link", 12)}</a>'
        )
    nuevos = sum(1 for pr in ejercicios if pr.get("is_new"))
    etiqueta = f"Ejercicios de práctica · voluntarios ({hechos} de {len(ejercicios)} hechos)"
    if nuevos:
        etiqueta += f" · {nuevos} nuevo{'s' if nuevos != 1 else ''}"
    return (
        f'<details class="group practicas"{" open" if nuevos else ""}>'
        f'<summary>{icon("chevron-right", 14, "chev")}{etiqueta}</summary>'
        f'<div class="practicas-lista">{"".join(filas)}</div></details>'
    )


PROPIAS_CSS = """
.pill-propia { background: var(--accent-soft); color: var(--accent); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.course-titulo { flex: 1; min-width: 0; }
.anadir-curso { flex: none; display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--border); background: var(--card);
  color: var(--muted); border-radius: 999px; padding: 5px 10px; font: inherit; font-size: 12.5px; cursor: pointer; }
.anadir-curso:hover { border-color: var(--accent); color: var(--accent); }
@media (max-width: 480px) { .anadir-curso span { display: none; } }
.dlg-propia { width: min(520px, calc(100vw - 32px)); border: 1px solid var(--border); border-radius: 20px; background: var(--card);
  color: var(--text); padding: 0; box-shadow: 0 24px 64px rgba(0,0,0,.35); max-height: calc(100dvh - 32px); overflow: auto; }
.dlg-propia::backdrop { background: rgba(10,12,24,.55); }
.dlg-propia form { padding: 20px 22px; display: flex; flex-direction: column; gap: 12px; }
.dlg-cab { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.dlg-cab h2 { margin: 0; font-size: 19px; }
.dlg-cerrar { border: 0; background: none; color: var(--muted); cursor: pointer; padding: 6px; border-radius: 8px; display: grid; place-items: center; }
.dlg-cerrar:hover { background: var(--card-2); color: var(--text); }
.dlg-sub { margin: -6px 0 0; color: var(--muted); font-size: 13px; }
.segmento { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; background: var(--card-2); border: 1px solid var(--border); border-radius: 12px; padding: 4px; }
.segmento input { position: absolute; opacity: 0; pointer-events: none; }
.segmento span { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 8px; border-radius: 9px; cursor: pointer;
  font-size: 14px; font-weight: 550; color: var(--muted); }
.segmento input:checked + span { background: var(--card); color: var(--text); box-shadow: var(--shadow); }
.segmento input:focus-visible + span { outline: 2px solid var(--accent); }
.campo-p { display: flex; flex-direction: column; gap: 5px; font-size: 13px; font-weight: 550; }
.campo-p em { font-style: normal; font-weight: 400; color: var(--muted); }
.campo-p input, .campo-p select, .campo-p textarea { width: 100%; border: 1px solid var(--border); background: var(--card-2); color: var(--text);
  border-radius: 10px; padding: 9px 11px; font: inherit; font-size: 14px; font-weight: 400; outline: none; }
.campo-p input:focus, .campo-p select:focus, .campo-p textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.campo-p textarea { resize: vertical; }
.dos-campos { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.atajos { display: flex; gap: 6px; flex-wrap: wrap; margin-top: -4px; }
.atajos:empty { display: none; }
.atajo { border: 1px solid var(--border); background: var(--card); color: var(--text); border-radius: 999px; padding: 4px 10px;
  font: inherit; font-size: 12.5px; cursor: pointer; }
.atajo:hover { border-color: var(--accent); color: var(--accent); }
.dlg-ayuda { margin: -4px 0 0; font-size: 12px; color: var(--muted); }
.dlg-ayuda:empty { display: none; }
.dlg-error { background: var(--red-soft); color: var(--red); border-radius: 10px; padding: 8px 12px; font-size: 13px; }
.dlg-botones { display: flex; gap: 8px; justify-content: flex-end; align-items: center; margin-top: 4px; }
.boton-pri, .boton-sec, .boton-borrar { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 8px 16px;
  font: inherit; font-size: 14px; cursor: pointer; border: 1px solid var(--border); background: var(--card); color: var(--text); }
.boton-pri { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff; border: 0; font-weight: 600; }
.boton-pri[disabled] { opacity: .7; cursor: progress; }
.boton-sec:hover { border-color: var(--accent); color: var(--accent); }
.boton-borrar { margin-right: auto; color: var(--red); }
.boton-borrar:hover { background: var(--red-soft); border-color: var(--red); }
"""

PROPIAS_JS = """
(function () {
  var dlg = document.getElementById('dlg-propia');
  if (!dlg) return;
  var f = document.getElementById('form-propia');
  var sel = f.elements.course, otra = document.getElementById('propia-otra'), otraCampo = document.getElementById('propia-otra-campo');
  var error = document.getElementById('propia-error'), borrar = document.getElementById('propia-borrar');
  var atajos = document.getElementById('propia-atajos'), ayuda = document.getElementById('propia-ayuda');
  var DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
  var horario = {};
  try { horario = JSON.parse(document.getElementById('horario-datos').textContent || '{}'); } catch (e) {}

  function iso(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  function curso() { return sel.value === '__otra__' ? otra.value.trim() : sel.value; }
  function tipo() { return f.elements.kind.value; }

  // Próximos días en que hay clase de esa asignatura, según el horario y sin festivos.
  function proximasClases(nombreCurso, cuantas) {
    var res = [], hoy = new Date(), sinClase = horario.no_lectivos || {}, pend = horario.pendientes || {};
    if (!horario.dias || !nombreCurso) return res;
    for (var i = 1; i <= 60 && res.length < cuantas; i++) {
      var d = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() + i);
      if (sinClase[iso(d)]) continue;
      var franjas = horario.dias[DIAS[d.getDay()]] || [];
      var suya = franjas.filter(function (fr) { return (pend[fr.asignatura] || {}).curso === nombreCurso; })
        .sort(function (a, b) { return a.inicio < b.inicio ? -1 : 1; })[0];
      if (suya) res.push({ fecha: d, hora: suya.inicio });
    }
    return res;
  }
  function pintarAtajos() {
    atajos.innerHTML = '';
    var opciones = [];
    var man = new Date(); man.setDate(man.getDate() + 1);
    opciones.push({ txt: 'Mañana', fecha: man });
    proximasClases(curso(), 2).forEach(function (c, i) {
      opciones.push({ txt: (i === 0 ? 'Próxima clase' : 'La siguiente') + ' (' + DIAS[c.fecha.getDay()].toLowerCase() + ' ' + c.fecha.getDate() + ')', fecha: c.fecha });
    });
    opciones.forEach(function (o) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'atajo'; b.textContent = o.txt;
      b.addEventListener('click', function () { f.elements.fecha.value = iso(o.fecha); pintarAyuda(); });
      atajos.append(b);
    });
    pintarAyuda();
  }
  function pintarAyuda() {
    if (f.elements.hora.value) { ayuda.textContent = ''; return; }
    if (tipo() === 'tarea') { ayuda.textContent = 'Sin hora, cuenta como entrega hasta las 23:59 de ese día.'; return; }
    var dia = f.elements.fecha.value;
    var clase = dia && proximasClases(curso(), 12).filter(function (c) { return iso(c.fecha) === dia; })[0];
    ayuda.textContent = clase ? 'Sin hora, se pone a las ' + clase.hora + ', cuando empieza la clase ese día.'
      : 'Sin hora, se pone a la hora de clase de esa asignatura ese día (o a las 08:00).';
  }
  function actualizarOtra() {
    otraCampo.hidden = sel.value !== '__otra__';
    pintarAtajos();
  }

  function abrir(datos) {
    datos = datos || {};
    f.reset();
    error.hidden = true;
    f.elements.id.value = datos.id || '';
    f.querySelector('input[name=kind][value=' + (datos.kind === 'examen' ? 'examen' : 'tarea') + ']').checked = true;
    f.elements.name.value = datos.name || '';
    var existe = Array.prototype.some.call(sel.options, function (o) { return o.value === datos.course; });
    if (datos.course && !existe) { sel.value = '__otra__'; otra.value = datos.course; }
    else if (datos.course) sel.value = datos.course;
    var man = new Date(); man.setDate(man.getDate() + 1);
    f.elements.fecha.value = datos.fecha || iso(man);
    f.elements.hora.value = datos.hora_auto ? '' : (datos.hora || '');
    f.elements.notes.value = datos.notes || '';
    document.getElementById('propia-titulo').textContent = datos.id ? 'Editar' : 'Apuntar tarea o examen';
    borrar.hidden = !datos.id;
    actualizarOtra();
    dlg.showModal();
    if (!datos.id) f.elements.name.focus();
  }

  async function enviar(url, cuerpo) {
    var r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
    var d = {};
    try { d = await r.json(); } catch (e) {}
    if (!r.ok) throw new Error(d.error || 'No se pudo guardar (' + r.status + ')');
    try { sessionStorage.setItem('aules-scroll', String(window.scrollY)); } catch (e) {}
    location.reload();
  }

  document.querySelectorAll('[data-anadir]').forEach(function (b) {
    b.addEventListener('click', function () { abrir({ course: b.dataset.curso || '' }); });
  });
  document.querySelectorAll('[data-editar]').forEach(function (b) {
    b.addEventListener('click', function () { abrir(JSON.parse(b.closest('[data-propia]').dataset.propia)); });
  });
  document.querySelectorAll('[data-marca]').forEach(function (b) {
    b.addEventListener('click', function () {
      b.disabled = true;
      enviar('/api/marcar', { id: b.dataset.item, marca: b.dataset.marca })
        .catch(function (e) { b.disabled = false; alert(e.message); });
    });
  });
  document.querySelectorAll('[data-hecha]').forEach(function (b) {
    b.addEventListener('click', function () {
      b.disabled = true;
      enviar('/api/propia/hecha', { id: b.dataset.hecha, done: b.dataset.valor === '1' })
        .catch(function (e) { b.disabled = false; alert(e.message); });
    });
  });
  dlg.querySelectorAll('[data-cerrar]').forEach(function (b) { b.addEventListener('click', function () { dlg.close(); }); });
  sel.addEventListener('change', actualizarOtra);
  otra.addEventListener('input', pintarAtajos);
  f.elements.fecha.addEventListener('change', pintarAyuda);
  f.elements.hora.addEventListener('input', pintarAyuda);
  f.querySelectorAll('input[name=kind]').forEach(function (r) { r.addEventListener('change', pintarAyuda); });

  borrar.addEventListener('click', function () {
    if (!confirm('¿Borrar «' + f.elements.name.value + '»?')) return;
    enviar('/api/propia/borrar', { id: f.elements.id.value }).catch(function (e) { error.textContent = e.message; error.hidden = false; });
  });
  f.addEventListener('submit', function (e) {
    e.preventDefault();
    var boton = f.querySelector('.boton-pri');
    boton.disabled = true;
    error.hidden = true;
    enviar('/api/propia', {
      id: f.elements.id.value, kind: tipo(), name: f.elements.name.value, course: curso(),
      fecha: f.elements.fecha.value, hora: f.elements.hora.value, notes: f.elements.notes.value
    }).catch(function (err) { error.textContent = err.message; error.hidden = false; boton.disabled = false; });
  });
})();
"""


def _dias_sin_clase_html(no_lectivos):
    """Próximos días sin clase agrupados: "23 dic – 6 ene · Vacaciones"."""
    if not no_lectivos:
        return ""
    tipos = {"festivo": "Festivo", "vacaciones": "Vacaciones", "no lectivo": "Día no lectivo"}
    hoy = datetime.now().date()
    fechas = sorted(d for d in no_lectivos if d >= hoy.isoformat())
    grupos = []
    for iso in fechas:
        dia = datetime.strptime(iso, "%Y-%m-%d").date()
        tipo = no_lectivos[iso]
        if grupos:
            ultimo = grupos[-1]
            hueco = (dia - ultimo["fin"]).days
            # Se unen si entre medias solo hay fin de semana.
            if tipo == ultimo["tipo"] and all(
                (ultimo["fin"] + timedelta(days=k)).weekday() >= 5 for k in range(1, hueco)
            ):
                ultimo["fin"] = dia
                continue
        grupos.append({"inicio": dia, "fin": dia, "tipo": tipo})

    def corta(d):
        return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"

    filas = "".join(
        f'<div class="sin-clase-fila tipo-{g["tipo"].replace(" ", "-")}">'
        f'<span class="sin-clase-fecha">{corta(g["inicio"]) if g["inicio"] == g["fin"] else corta(g["inicio"]) + " – " + corta(g["fin"])}</span>'
        f'<span class="pill">{tipos.get(g["tipo"], g["tipo"])}</span></div>'
        for g in grupos[:8]
    )
    if not filas:
        return ""
    return f'<section class="sin-clase-lista"><h2>{icon("calendar", 16)}Próximos días sin clase</h2>{filas}</section>'


def _due_html(ts, label, now_ts, cls="due", extra=""):
    prefix = DUE_PREFIXES.get(label, "")
    abs_text = format_due(ts)
    if ts and label in ("Abre", "Cierra", "Prórroga"):
        abs_text = f"{label} · {abs_text}"
    return (
        f'<div class="{cls}" data-due="{ts or 0}" data-prefix="{prefix}">'
        f'<span class="due-rel">{prefix}{rel_time(ts, now_ts)}</span>'
        f'<span class="due-abs">{icon("clock", 12)}{abs_text}</span>{extra}</div>'
    )


def _texto_nota(valor):
    # Por si queda en caché alguna nota antigua con el icono HTML de Aules delante.
    return html.unescape(re.sub(r"<[^>]*>", "", valor or "")).strip()


def _nota_valor(n):
    nota = _texto_nota(n["grade"])
    maximo = f'<span class="nota-max">/ {html.escape(n["max"])}</span>' if n["max"] and "%" not in nota else ""
    return f'<div class="nota-valor">{html.escape(nota)}{maximo}</div>'


def _a_numero(texto):
    try:
        return float(str(texto or "").strip().replace(",", "."))
    except ValueError:
        return None


def _estado_nota(n):
    estado = n.get("estado") or ""
    if not estado:
        encontrado = re.search(r'<i\b[^>]*\btitle="([^"]+)"', n.get("grade") or "")
        estado = html.unescape(encontrado.group(1)) if encontrado else ""
    if not estado:
        # Aules solo pone el icono si el profe configuró una nota para aprobar: si no, se aprueba con la mitad.
        nota, maximo = _a_numero(_texto_nota(n.get("grade")).rstrip(" %")), _a_numero(n.get("max"))
        if "%" in _texto_nota(n.get("grade")):
            maximo = 100
        if nota is None or not maximo:
            return ""
        estado = "Aprobado" if nota >= maximo / 2 else "Suspendido"
    clase = "pill-aprobado" if estado.lower().startswith(("aprob", "aprov", "pass")) else "pill-suspendido"
    icono = "check" if clase == "pill-aprobado" else "x"
    minimo = n.get("aprobar")
    if minimo:
        titulo = html.escape(f'Nota mínima para aprobar: {minimo}' + (f' / {n["max"]}' if n.get("max") else ""))
        return f'<span class="pill {clase}" title="{titulo}">{icon(icono, 11)}{html.escape(estado)} · mínimo {html.escape(minimo)}</span>'
    return f'<span class="pill {clase}">{icon(icono, 11)}{html.escape(estado)}</span>'


ENTREGA_CSS = """
.ent-limites { margin: -6px 0 0; font-size: 12.5px; color: var(--muted); }
.ent-aviso { display: flex; gap: 8px; align-items: flex-start; background: var(--amber-soft); color: var(--amber); border-radius: 10px;
  padding: 8px 12px; font-size: 13px; }
.ent-aviso .i { flex: none; margin-top: 2px; }
.ent-bloque { display: flex; flex-direction: column; gap: 6px; font-size: 13px; font-weight: 550; }
.ent-lista { display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 0; list-style: none; }
.ent-lista li { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: var(--card-2); border: 1px solid var(--border);
  border-radius: 10px; font-weight: 400; }
.ent-lista .ent-nombre { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.ent-lista .ent-peso { color: var(--muted); font-size: 12px; white-space: nowrap; }
.ent-lista button { border: 0; background: none; color: var(--muted); cursor: pointer; padding: 2px; display: grid; place-items: center; }
.ent-lista button:hover { color: var(--red); }
.ent-lista label { display: flex; align-items: center; gap: 8px; flex: 1; cursor: pointer; }
.ent-elegir { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; border: 1px dashed var(--muted); background: transparent;
  color: var(--text); border-radius: 10px; padding: 8px 14px; font: inherit; font-size: 13.5px; cursor: pointer; }
.ent-elegir:hover { border-color: var(--accent); color: var(--accent); }
.ent-declaracion { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; font-weight: 400; cursor: pointer; }
.ent-declaracion input { margin-top: 3px; accent-color: var(--accent); }
.ent-resumen { margin: 0; padding: 10px 12px; border-radius: 10px; background: var(--accent-soft); color: var(--text); font-size: 13px; }
.ent-resumen:empty { display: none; }
.ent-ok { background: var(--green-soft); color: var(--green); border-radius: 10px; padding: 10px 12px; font-size: 13.5px; font-weight: 600; }
"""

ENTREGA_JS = """
(function () {
  var dlg = document.getElementById('dlg-entrega');
  if (!dlg) return;
  var form = document.getElementById('form-entrega');
  var el = function (id) { return document.getElementById(id); };
  var datos = null, elegidos = [], confirmar = false;

  function peso(b) { return b >= 1048576 ? (b / 1048576).toFixed(1).replace('.', ',') + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; }
  function error(texto) { el('ent-error').textContent = texto || ''; el('ent-error').hidden = !texto; }
  function li(nombre, bytes, extra) {
    var l = document.createElement('li');
    var n = document.createElement('span'); n.className = 'ent-nombre'; n.textContent = nombre;
    var p = document.createElement('span'); p.className = 'ent-peso'; p.textContent = bytes == null ? '' : peso(bytes);
    l.append(n, p);
    if (extra) l.append(extra);
    return l;
  }
  function borradorMarcados() {
    return Array.prototype.map.call(form.querySelectorAll('input[name=borrador]:checked'), function (c) { return c.value; });
  }
  function pintarElegidos() {
    var ul = el('ent-elegidos'); ul.innerHTML = '';
    elegidos.forEach(function (f, i) {
      var quitar = document.createElement('button'); quitar.type = 'button'; quitar.title = 'Quitar'; quitar.textContent = '✕';
      quitar.addEventListener('click', function () { elegidos.splice(i, 1); pintarElegidos(); });
      ul.append(li(f.name, f.size, quitar));
    });
    resumen();
  }
  // Resumen de lo que se va a enviar, siempre a la vista antes de pulsar «Entregar».
  function resumen() {
    confirmar = false;
    if (!datos) { el('ent-enviar').disabled = true; return; }
    el('ent-enviar').lastChild.textContent = 'Entregar en Aules';
    var nombres = elegidos.map(function (f) { return f.name; }).concat(borradorMarcados());
    var texto = form.texto && form.texto.value.trim();
    var partes = [];
    if (nombres.length) partes.push(nombres.length + ' archivo' + (nombres.length > 1 ? 's' : '') + ': ' + nombres.join(', '));
    if (texto) partes.push('el texto que has escrito');
    el('ent-resumen').textContent = partes.length ? 'Se entregará ' + partes.join(' y ') + '.' : '';
    var falta = !partes.length || (datos.config.declaracion && !el('ent-acepta').checked) || !datos.estado.puede;
    el('ent-enviar').disabled = falta;
  }

  async function abrir(id) {
    error(''); el('ent-ok').hidden = true; form.hidden = false; elegidos = []; datos = null; confirmar = false;
    el('ent-enviar').disabled = true; el('ent-enviar').lastChild.textContent = 'Entregar en Aules';
    el('ent-titulo').textContent = 'Entregar tarea';
    el('ent-cuerpo').hidden = true; el('ent-cargando').hidden = false;
    dlg.showModal();
    try {
      var r = await fetch('/api/entrega?id=' + encodeURIComponent(id));
      var d = await r.json();
      if (!r.ok) throw new Error(d.error || 'No se pudo consultar Aules.');
      datos = d;
    } catch (e) { el('ent-cargando').hidden = true; error(e.message); return; }
    var c = datos.config, est = datos.estado;
    el('ent-titulo').textContent = datos.tarea.name;
    el('ent-sub').textContent = datos.tarea.course;
    var lim = [];
    if (c.archivos) lim.push('Hasta ' + c.max_archivos + ' archivo' + (c.max_archivos > 1 ? 's' : '') + (c.max_bytes ? ' de ' + peso(c.max_bytes) + ' como mucho' : ''));
    if (c.tipos) lim.push('tipos: ' + c.tipos);
    if (c.texto) lim.push(c.archivos ? 'también admite texto' : 'se entrega como texto');
    el('ent-limites').textContent = lim.join(' · ');
    el('ent-bloqueada').hidden = est.puede; el('ent-bloqueada-txt').textContent = est.motivo;
    var previo = est.archivos.slice(); if (est.texto) previo.push('texto en línea');
    el('ent-previa').hidden = !previo.length || !est.puede;
    el('ent-previa-txt').textContent = 'Ya entregaste: ' + previo.join(', ') + '. Si entregas de nuevo, lo que mandes ahora sustituye a todo eso.';
    el('ent-bloque-archivos').hidden = !c.archivos;
    el('ent-bloque-texto').hidden = !c.texto; if (form.texto) form.texto.value = '';
    var ul = el('ent-borrador'); ul.innerHTML = '';
    datos.borrador.forEach(function (b) {
      var lab = document.createElement('label');
      var cb = document.createElement('input'); cb.type = 'checkbox'; cb.name = 'borrador'; cb.value = b.nombre;
      cb.addEventListener('change', resumen);
      var n = document.createElement('span'); n.className = 'ent-nombre'; n.textContent = b.nombre;
      lab.append(cb, n);
      var l = document.createElement('li'); l.append(lab);
      var p = document.createElement('span'); p.className = 'ent-peso'; p.textContent = peso(b.bytes); l.append(p);
      ul.append(l);
    });
    el('ent-bloque-borrador').hidden = !datos.borrador.length || !c.archivos;
    el('ent-bloque-declaracion').hidden = !c.declaracion; el('ent-declaracion').textContent = c.declaracion; el('ent-acepta').checked = false;
    el('ent-cargando').hidden = true; el('ent-cuerpo').hidden = false;
    pintarElegidos();
  }

  function leer(f) {
    return new Promise(function (ok, mal) {
      var r = new FileReader();
      r.onload = function () { ok({ nombre: f.name, datos: String(r.result).split(',')[1] || '' }); };
      r.onerror = function () { mal(new Error('No se pudo leer ' + f.name)); };
      r.readAsDataURL(f);
    });
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-entregar]');
    if (b) abrir(b.dataset.entregar);
  });
  dlg.querySelectorAll('[data-cerrar]').forEach(function (b) { b.addEventListener('click', function () { dlg.close(); }); });
  el('ent-elegir').addEventListener('click', function () { el('ent-archivos').click(); });
  el('ent-archivos').addEventListener('change', function () {
    Array.prototype.forEach.call(this.files, function (f) { elegidos.push(f); });
    this.value = '';
    pintarElegidos();
  });
  form.addEventListener('input', resumen);
  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    error('');
    var boton = el('ent-enviar');
    // Dos pasos: el primer clic pide confirmación; el segundo entrega.
    if (!confirmar) { confirmar = true; boton.lastChild.textContent = '¿Seguro? Pulsa otra vez para entregar'; return; }
    boton.disabled = true; boton.lastChild.textContent = 'Entregando…';
    try {
      var archivos = await Promise.all(elegidos.map(leer));
      var r = await fetch('/api/entregar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        id: datos.tarea.id, archivos: archivos, borrador: borradorMarcados(), texto: form.texto ? form.texto.value : '',
        acepta: el('ent-acepta').checked }) });
      var d = await r.json();
      if (!r.ok) throw new Error(d.error || 'No se pudo entregar.');
      form.hidden = true; el('ent-ok').hidden = false;
      setTimeout(function () { location.reload(); }, 1800);
    } catch (err) {
      error(err.message); confirmar = false; resumen();
    }
  });
})();
"""


DIALOGO_ENTREGA = f"""<dialog class="dlg-propia dlg-entrega" id="dlg-entrega">
    <form id="form-entrega" novalidate>
      <div class="dlg-cab"><h2 id="ent-titulo">Entregar tarea</h2>
        <button type="button" class="dlg-cerrar" data-cerrar aria-label="Cerrar">{icon("x", 18)}</button></div>
      <p class="dlg-sub" id="ent-sub"></p>
      <p class="dlg-ayuda" id="ent-cargando">Consultando la tarea en Aules…</p>
      <div id="ent-cuerpo" hidden style="display: contents">
        <p class="ent-limites" id="ent-limites"></p>
        <div class="ent-aviso" id="ent-bloqueada" hidden>{icon("lock", 14)}<span id="ent-bloqueada-txt"></span></div>
        <div class="ent-aviso" id="ent-previa" hidden>{icon("alert-circle", 14)}<span id="ent-previa-txt"></span></div>
        <div class="ent-bloque" id="ent-bloque-archivos">Archivos
          <ul class="ent-lista" id="ent-elegidos"></ul>
          <input type="file" id="ent-archivos" multiple hidden>
          <button type="button" class="ent-elegir" id="ent-elegir">{icon("upload", 14)}Elegir archivos de tu ordenador</button>
        </div>
        <div class="ent-bloque" id="ent-bloque-borrador" hidden>Archivos de tu borrador con IA <em class="opt">(tal como están ahora en su carpeta, con tus cambios)</em>
          <ul class="ent-lista" id="ent-borrador"></ul>
        </div>
        <label class="campo-p" id="ent-bloque-texto" hidden><span>Texto de la entrega</span>
          <textarea name="texto" rows="5" placeholder="Escribe aquí tu respuesta…"></textarea></label>
        <div class="ent-bloque" id="ent-bloque-declaracion" hidden>
          <label class="ent-declaracion"><input type="checkbox" id="ent-acepta"><span id="ent-declaracion"></span></label>
        </div>
        <p class="ent-resumen" id="ent-resumen"></p>
      </div>
      <div class="dlg-error" id="ent-error" hidden></div>
      <div class="dlg-botones">
        <button type="button" class="boton-sec" data-cerrar>Cancelar</button>
        <button type="submit" class="boton-pri" id="ent-enviar" disabled>{icon("upload", 14)}<span>Entregar en Aules</span></button>
      </div>
    </form>
    <div class="ent-ok" id="ent-ok" hidden style="margin: 20px 22px">{icon("check-circle", 16)} Entregada en Aules. Actualizando…</div>
  </dialog>"""


def _entrega_html(a, now_ts):
    """Botón para entregar la tarea en Aules desde la app (solo en las que lo admiten y no están corregidas)."""
    if not a.get("entrega") or a.get("propia") or a.get("marcada") or a["status"].startswith("Calificada"):
        return ""
    entrega = a["entrega"]
    if entrega.get("desde") and now_ts < entrega["desde"]:
        return _opcion("disabled", "clock", f'Se podrá entregar desde el {format_due(entrega["desde"])}')
    if entrega.get("corte") and now_ts > entrega["corte"] and a.get("due_label") != "Prórroga":
        return "" if a["done"] else _opcion("disabled", "lock", "Plazo de entrega cerrado")
    return _opcion(f'data-entregar="{html.escape(a["id"])}"', "upload", "Cambiar la entrega" if a["done"] else "Entregar")


def _num(valor):
    return f"{valor:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _progreso_html(p):
    """«¿Cuánto llevo?» de una asignatura: media de lo corregido y lo que te falta para el 5."""
    if not p:
        return ""
    media = f'Llevas un <strong>{_num(p["media"])}</strong> de media en lo que ya está corregido'
    if p["corregido"] >= 100 or p["necesaria"] is None:
        detalle = "Ya está corregido todo lo que cuenta para la nota."
    elif p["necesaria"] <= 0:
        detalle = f'Lo corregido es el {p["corregido"]} % de la nota, y con eso ya tienes el 5 aunque no sumes nada más.'
    elif p["necesaria"] > 10:
        detalle = f'Lo corregido es el {p["corregido"]} % de la nota. Con lo que queda ya no se llega al 5 de media.'
    else:
        detalle = (f'Lo corregido es el {p["corregido"]} % de la nota. Para llegar al 5 te hace falta sacar '
                   f'<strong>{_num(p["necesaria"])}</strong> de media en lo que queda.')
    origen = ("Calculado con los pesos que ha puesto el profe en Aules." if p["fuente"] == "aules" else
              "Calculado con los porcentajes del nombre de cada tarea. En FP normalmente hay que aprobar cada RA por separado.")
    clase = " bien" if p["media"] >= 5 else " mal"
    return (f'<div class="progreso{clase}">{icon("graduation-cap", 16)}<div><div>{media}. {detalle}</div>'
            f'<div class="progreso-origen">{origen}</div></div></div>')


def _marcas_html(a):
    """Botones para corregir a mano una tarea de Aules: entregada fuera de Aules, o aviso puesto como tarea."""
    ident = html.escape(a["id"])
    if a.get("marcada"):
        texto = "Volver a pendiente" if a["marcada"] == "hecha" else "Sí es una tarea"
        return _opcion(f'data-marca="" data-item="{ident}"', "refresh", texto)
    if a["kind"] != "aviso" and not a["done"]:
        return (
            _opcion(f'data-marca="hecha" data-item="{ident}"', "check", "Ya está hecha",
                    "La entregaste en clase o fuera de Aules: deja de estar pendiente y no te avisa más")
            + _opcion(f'data-marca="aviso" data-item="{ident}"', "megaphone", "No es una tarea",
                      "El profe la puso como tarea pero es un aviso: pasa a «Avisos sin entrega» y no te avisa más")
        )
    return ""


def _nota_html(n, now_ts, con_nombre=True):
    nuevo = _estado_nota(n) + (f'<span class="pill pill-new">{icon("sparkles", 11)}Nueva</span>' if n.get("is_new") else "")
    fecha = f' · corregida {rel_time(n["graded"], now_ts)}' if n.get("graded") else ""
    comentario = (
        f'<div class="nota-fb">{icon("message-square", 13)}<span>{linkify(html.escape(n["feedback"]))}</span></div>'
        if n["feedback"] else ""
    )
    cabecera = (
        f'<div class="nota-nombre">{html.escape(n["name"])}{nuevo}</div>' if con_nombre
        else f'<div class="nota-nombre">{icon("graduation-cap", 13)}Nota{nuevo}</div>'
    )
    return (
        f'<div class="nota{" is-new" if n.get("is_new") else ""}"><div class="nota-main">{cabecera}'
        f'<div class="nota-meta">{html.escape(n["percentage"]) + fecha if n["percentage"] else fecha.lstrip(" ·")}</div>'
        f'{comentario}</div>{_nota_valor(n)}</div>'
    )


# Aules tiene las asignaturas en valenciano y el horario del PDF está en castellano.
_TRADUCCION = {
    "llenguatges": "lenguajes", "llenguatge": "lenguaje", "marques": "marcas", "gestio": "gestion",
    "informacio": "informacion", "planificacio": "planificacion", "administracio": "administracion",
    "xarxes": "redes", "xarxa": "red", "angles": "ingles", "projecte": "proyecto", "sistemes": "sistemas",
    "informatics": "informaticos", "fonaments": "fundamentos", "implantacio": "implantacion",
    "operatius": "operativos", "dades": "datos", "itinerari": "itinerario", "ocupabilitat": "empleabilidad",
    "professional": "profesional", "maquinari": "hardware",
}
_VACIAS = {"del", "las", "los", "per", "para", "cfsa", "asir", "grado", "superior"}


def _raices(texto):
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto.lower()) if not unicodedata.combining(c))
    palabras = (_TRADUCCION.get(p, p) for p in re.findall(r"[a-z]+", texto))
    return {p[:5] for p in palabras if len(p) > 2 and p not in _VACIAS}


def asignatura_a_curso(asignatura, cursos):
    """El curso de Aules que corresponde a una asignatura del horario, o None."""
    buscadas = _raices(asignatura)
    mejor, puntos = None, 0.0
    for curso in cursos:
        raices = _raices(curso)
        comunes = len(buscadas & raices)
        if comunes and raices:
            valor = comunes / min(len(buscadas), len(raices))
            if valor > puntos:
                mejor, puntos = curso, valor
    return mejor if puntos >= 0.5 else None


def build_report(items, posts, session, warnings, urgent_hours, ia_cache=None, courses=None, materials=None, horario=None,
                 notas=None, mensajes=None, firma="", practicas=None, foto="", progreso=None):
    now = datetime.now()
    now_ts = now.timestamp()
    notas = notas or []
    mensajes = mensajes or []
    nota_de_actividad = {n["activity"]: n for n in notas if n["activity"]}

    def urgency(a):
        if a["done"]:
            return "done"
        if not a["duedate"]:
            return "none"
        diff = a["duedate"] - now_ts
        if diff < 0:
            return "overdue"
        if diff <= urgent_hours * 3600:
            return "urgent"
        if diff <= 7 * 86400:
            return "soon"
        return "later"

    def is_pending(a):
        return a["kind"] != "aviso" and not a["done"] and (not a["duedate"] or a["duedate"] >= now_ts)

    def render_item(a):
        kind = a["kind"]
        pills = f'<span class="pill pill-{kind}">{icon(KIND_ICONS[kind], 12)}{KIND_LABELS[kind]}</span>'
        if a.get("propia"):
            pills += f'<span class="pill pill-propia">{icon("pencil", 11)}Apuntada por ti</span>'
        if a.get("marcada") == "aviso":
            pills += f'<span class="pill pill-propia">{icon("pencil", 11)}Era {KIND_LABELS[a["kind_original"]].lower()} en Aules</span>'
        if a.get("is_new"):
            pills += f'<span class="pill pill-new">{icon("sparkles", 12)}Nueva</span>'
        cambios = ""
        if a.get("cambios") and not a.get("is_new"):
            pills += f'<span class="pill pill-cambio">{icon("refresh", 12)}Modificada</span>'
            cambios = '<ul class="cambios">' + "".join(f"<li>{html.escape(c)}</li>" for c in a["cambios"]) + "</ul>"
        if a["status"]:
            cls, ic = ("pill-done", "check") if a["done"] else ("pill-draft", "pencil")
            pills += f'<span class="pill {cls}">{icon(ic, 12)}{html.escape(a["status"])}</span>'

        if a["summary"]:
            desc = _desc_html(a["summary"], "Ver descripción")
        elif a.get("summary_file"):
            # El profe dejó el enunciado dentro del adjunto: se muestra su texto.
            desc = _desc_html(a["summary_file"], f'Ver enunciado (de {html.escape(a["summary_file_name"])})')
        else:
            desc = ""

        nota = nota_de_actividad.get(a["id"])
        nota_item = f'<div class="nota-item">{_nota_html(nota, now_ts, con_nombre=False)}</div>' if nota else ""
        search = html.escape(f'{a["name"]} {a["course"]} {a["summary"]} {a.get("summary_file", "")}'.lower())
        classes = f'item kind-{kind} urg-{urgency(a)}' + (" is-done" if a["done"] else "")
        candidatas = [c for c in by_course.get(a["course"], []) if c["id"] != a["id"] and c["kind"] != "aviso"
                      and c["id"].split("_")[0] in ("assign", "assigngva")]
        extra_attr = ""
        if a.get("propia"):
            if a["summary"]:
                desc = _desc_html(a["summary"], "Ver notas")
            datos = {k: a[k] for k in ("id", "name", "course", "kind", "fecha", "hora", "hora_auto")} | {"notes": a["summary"]}
            extra_attr = f' data-propia="{html.escape(json.dumps(datos, ensure_ascii=False))}"'
            hecha = ("0", "refresh", "Volver a pendiente") if a["done"] else ("1", "check", "Marcar como hecha")
            extra = ""
            menu = _menu_mas(_opcion(f'data-hecha="{html.escape(a["id"])}" data-valor="{hecha[0]}"', hecha[1], hecha[2])
                             + _opcion("data-editar", "pencil", "Editar"))
        else:
            extra = _ia_html(a, ia_cache, candidatas)
            menu = _menu_mas(_entrega_html(a, now_ts), _ia_menu(a, ia_cache, candidatas), _marcas_html(a))
        return (
            f'<article class="{classes}" data-kind="{kind}" data-new="{int(bool(a.get("is_new")))}" data-search="{search}"'
            f' data-id="{html.escape(a["id"])}"{extra_attr}>'
            f'<div class="item-main"><div class="item-head">{pills}</div>'
            f'<h3 class="item-title">{html.escape(a["name"])}</h3>'
            f'{cambios}{desc}{_files_html(a["attachments"])}{nota_item}{extra}</div>'
            f'{_due_html(a["duedate"], a["due_label"], now_ts, extra=menu)}'
            "</article>"
        )

    def render_post(p):
        who = p["author"] or p["forum"]
        new_pill = ""
        if p["is_new"]:
            new_pill = f'<span class="pill pill-new">{icon("sparkles", 12)}{"Respuesta nueva" if p["is_reply"] else "Nuevo"}</span>'
        meta = [html.escape(x) for x in (p["author"], p["forum"], p["course"]) if x]
        if p["numreplies"]:
            meta.append(f'{p["numreplies"]} respuesta{"s" if p["numreplies"] != 1 else ""}')
        search = html.escape(f'{p["name"]} {p["forum"]} {p["course"]} {p["author"]} {p["summary"]}'.lower())
        return (
            f'<article class="post{" is-new" if p["is_new"] else ""}" data-search="{search}">'
            f'<div class="post-avatar" style="--hue: {course_hue(who)}">{html.escape(initials(who))}</div>'
            '<div class="post-main">'
            f'<div class="post-head"><h3 class="post-subject">{icon("megaphone" if p["forum_type"] == "news" else "message-square", 14)}'
            f'{html.escape(p["name"])}</h3>{new_pill}</div>'
            f'<div class="post-meta">{" · ".join(meta)}</div>'
            f'{_desc_html(p["summary"], "Leer mensaje")}{_files_html(p["attachments"])}'
            f'<a class="post-link" href="{html.escape(p["url"])}" target="_blank" rel="noopener noreferrer">Abrir en Aules{icon("external-link", 12)}</a>'
            "</div>"
            f'<div class="post-time" data-due="{p["timemodified"]}"><span class="due-rel">{rel_time(p["timemodified"], now_ts)}</span></div>'
            "</article>"
        )

    def due_sort(a):
        return a["duedate"] if a["duedate"] else float("inf")

    def group(title, group_items):
        return (
            f'<details class="group"><summary>{icon("chevron-right", 14, "chev")}{title} ({len(group_items)})</summary>'
            + "".join(render_item(a) for a in group_items) + "</details>"
        )

    practicas_por_curso = {}
    for pr in practicas or []:
        practicas_por_curso.setdefault(pr["course"], []).append(pr)

    notas_por_curso = {}
    for n in notas:
        # Todas las notas van a "Notas"; las de los ejercicios de práctica se ven además junto a cada ejercicio.
        notas_por_curso.setdefault(n["course"], []).append(n)

    por_curso_material = {}
    for m in materials or []:
        por_curso_material.setdefault(m["course"], []).append(m)

    # Se parte de todas las asignaturas matriculadas para que una clase nueva
    # aparezca aunque todavía no tenga ninguna tarea.
    by_course = {nombre: [] for nombre in (courses or [])}
    for a in items:
        by_course.setdefault(a["course"], []).append(a)

    def course_order(name):
        upcoming = [a["duedate"] for a in by_course[name] if is_pending(a) and a["duedate"]]
        has_pending = any(is_pending(a) for a in by_course[name])
        return (0 if upcoming else (1 if has_pending else 2), min(upcoming) if upcoming else 0, name.lower())

    sections = []
    for course_name in sorted(by_course, key=course_order):
        course_items = by_course[course_name]
        pending = sorted([a for a in course_items if is_pending(a)], key=lambda a: (a["kind"] != "examen", due_sort(a)))
        finished = sorted(
            [a for a in course_items if a["kind"] != "aviso" and not is_pending(a)],
            key=lambda a: -(a["duedate"] or 0),
        )
        info_items = [a for a in course_items if a["kind"] == "aviso"]

        n_exams = sum(1 for a in pending if a["kind"] == "examen")
        n_tasks = len(pending) - n_exams
        meta_parts = []
        if n_exams:
            meta_parts.append(f"{n_exams} examen{'es' if n_exams != 1 else ''}")
        meta_parts.append(f"{n_tasks} tarea{'s' if n_tasks != 1 else ''} pendiente{'s' if n_tasks != 1 else ''}")
        notas_curso = notas_por_curso.get(course_name, [])
        total = next((n for n in notas_curso if n["total"]), None)
        if total:
            nota_total = _texto_nota(total["grade"])
            meta_parts.append(f"Nota: {nota_total}" + (f" / {total['max']}" if total["max"] and "%" not in nota_total else ""))

        body = "".join(render_item(a) for a in pending)
        if not pending:
            body += f'<p class="empty-course">{icon("check-circle")}Nada pendiente por aquí</p>'
        if finished:
            body += group("Hechas o fuera de plazo", finished)
        if info_items:
            body += group("Avisos sin entrega", info_items)
        body += _progreso_html((progreso or {}).get(course_name))
        corregidas = sorted((n for n in notas_curso if not n["total"]), key=lambda n: -(n["graded"] or 0))
        if corregidas:
            nuevas = sum(1 for n in corregidas if n.get("is_new"))
            etiqueta = f"Notas ({len(corregidas)})" + (f" · {nuevas} nueva{'s' if nuevas != 1 else ''}" if nuevas else "")
            body += (
                f'<details class="group notas"{" open" if nuevas else ""}><summary>{icon("chevron-right", 14, "chev")}{etiqueta}</summary>'
                + "".join(_nota_html(n, now_ts) for n in corregidas)
                + f'<a class="post-link notas-link" href="{html.escape(corregidas[0]["url"])}" target="_blank" rel="noopener noreferrer">Ver el informe de notas en Aules{icon("external-link", 12)}</a></details>'
            )
        ejercicios = practicas_por_curso.get(course_name, [])
        if ejercicios:
            body += _practicas_html(ejercicios, nota_de_actividad, now_ts)
        mats = por_curso_material.get(course_name, [])
        if mats:
            body += _material_html(mats)

        sections.append(
            f'<section class="course" style="--hue: {course_hue(course_name)}">'
            f'<header class="course-head"><div class="avatar">{html.escape(initials(course_name))}</div>'
            f'<div class="course-titulo"><h2 class="course-name">{html.escape(course_name)}</h2>'
            f'<div class="course-meta">{" · ".join(meta_parts)}</div></div>'
            f'<button type="button" class="anadir-curso" data-anadir data-curso="{html.escape(course_name)}" '
            f'title="Apuntar una tarea o examen de esta asignatura">{icon("plus", 14)}<span>Apuntar</span></button></header>'
            f'<div class="course-body">{body}</div></section>'
        )

    pending_all = [a for a in items if is_pending(a)]
    n_exams = sum(1 for a in pending_all if a["kind"] == "examen")
    n_tasks = sum(1 for a in pending_all if a["kind"] == "tarea")
    n_week = sum(1 for a in pending_all if a["duedate"] and a["duedate"] - now_ts <= 7 * 86400)
    n_new = sum(1 for a in items if a.get("is_new"))

    upcoming = sorted([a for a in pending_all if a["duedate"]], key=lambda a: a["duedate"])
    next_html = ""
    if upcoming:
        n = upcoming[0]
        next_html = (
            '<div class="next">'
            f'<div class="next-icon">{icon(KIND_ICONS[n["kind"]], 22)}</div>'
            '<div class="next-body"><div class="next-label">Lo próximo</div>'
            f'<div class="next-title">{html.escape(n["name"])}</div>'
            f'<div class="next-course">{html.escape(n["course"])}</div></div>'
            f'{_due_html(n["duedate"], n["due_label"], now_ts, "next-due")}</div>'
        )

    warn_html = ""
    if warnings:
        warn_html = (
            f'<div class="warn" role="status">{icon("triangle-alert")}'
            f'<span>No se pudieron cargar: {html.escape(", ".join(warnings))}. Lo demás está actualizado.</span></div>'
        )

    posts_sorted = sorted(posts, key=lambda p: -p["timemodified"])
    n_new_posts = sum(1 for p in posts if p["is_new"])
    forum_badge = f'<span class="forum-badge">{n_new_posts} nuevo{"s" if n_new_posts != 1 else ""}</span>' if n_new_posts else ""
    forum_body = "".join(render_post(p) for p in posts_sorted) or (
        f'<p class="empty-course">{icon("check-circle")}Sin mensajes en los últimos 30 días</p>'
    )
    n_posts = len(posts)
    forum_html = (
        '<details class="forum-panel" id="forum-panel"><summary>'
        f'<span class="forum-icon">{icon("message-square", 18)}</span>'
        '<span class="forum-text"><span class="forum-title">Mensajes del foro</span>'
        f'<span class="forum-sub">Últimos 30 días · {n_posts} conversaci{"ones" if n_posts != 1 else "ón"}</span></span>'
        f'{forum_badge}{icon("chevron-down", 16, "chev-down")}</summary>'
        f'<div class="posts">{forum_body}</div></details>'
    )

    def render_mensaje(m):
        nuevo = f'<span class="pill pill-new">{icon("sparkles", 12)}Nuevo</span>' if m.get("is_new") else ""
        autor = "Tú" if m["from_me"] else (m["author"] or m["who"])
        search = html.escape(f'{m["who"]} {m["author"]} {m["text"]}'.lower())
        return (
            f'<article class="post{" is-new" if m.get("is_new") else ""}" data-search="{search}">'
            f'<div class="post-avatar" style="--hue: {course_hue(m["who"])}">{html.escape(initials(m["who"]))}</div>'
            '<div class="post-main">'
            f'<div class="post-head"><h3 class="post-subject">{html.escape(pretty_name(m["who"]))}</h3>{nuevo}</div>'
            f'<div class="post-meta mensaje-texto"><strong>{html.escape(pretty_name(autor))}:</strong> {linkify(html.escape(m["text"] or "(sin texto)"))}</div>'
            f'<a class="post-link" href="{html.escape(m["url"])}" target="_blank" rel="noopener noreferrer">Responder en Aules{icon("external-link", 12)}</a>'
            "</div>"
            f'<div class="post-time" data-due="{m["time"]}"><span class="due-rel">{rel_time(m["time"], now_ts)}</span></div>'
            "</article>"
        )

    mensajes_html = ""
    if mensajes:
        n_nuevos = sum(1 for m in mensajes if m.get("is_new"))
        insignia = f'<span class="forum-badge">{n_nuevos} nuevo{"s" if n_nuevos != 1 else ""}</span>' if n_nuevos else ""
        mensajes_html = (
            f'<details class="forum-panel mensajes-panel"{" open" if n_nuevos else ""}><summary>'
            f'<span class="forum-icon">{icon("users", 18)}</span>'
            '<span class="forum-text"><span class="forum-title">Mensajes privados</span>'
            f'<span class="forum-sub">Últimos 60 días · {len(mensajes)} conversaci{"ones" if len(mensajes) != 1 else "ón"}</span></span>'
            f'{insignia}{icon("chevron-down", 16, "chev-down")}</summary>'
            f'<div class="posts">{"".join(render_mensaje(m) for m in sorted(mensajes, key=lambda m: -m["time"]))}</div></details>'
        )

    # Para el cuadro de "Ahora / Después": qué tienes pendiente de cada asignatura del horario.
    horario_datos = dict(horario or {})
    if horario_datos.get("dias"):
        nombres_cursos = list(by_course)
        pendientes = {}
        for franjas in horario_datos["dias"].values():
            for f in franjas:
                asig = f.get("asignatura") or ""
                if asig in pendientes or re.search(r"descanso|recreo|patio|esbarjo", asig, re.I):
                    continue
                curso = asignatura_a_curso(asig, nombres_cursos)
                lista = sorted((a for a in by_course.get(curso, []) if is_pending(a)), key=due_sort) if curso else []
                pendientes[asig] = {
                    "curso": curso or "",
                    "n": len(lista),
                    "examenes": sum(1 for a in lista if a["kind"] == "examen"),
                    "proxima": lista[0]["name"] if lista else "",
                }
        horario_datos["pendientes"] = pendientes
    # Un nombre de tarea con "</script>" no debe poder cerrar la etiqueta.
    horario_json = json.dumps(horario_datos, ensure_ascii=False).replace("</", "<\\/")

    opciones_cursos = "".join(
        f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in sorted(by_course, key=str.lower)
    )
    dialogo_propia = f"""<dialog class="dlg-propia" id="dlg-propia">
    <form id="form-propia" novalidate>
      <div class="dlg-cab"><h2 id="propia-titulo">Apuntar tarea o examen</h2>
        <button type="button" class="dlg-cerrar" data-cerrar aria-label="Cerrar">{icon("x", 18)}</button></div>
      <p class="dlg-sub">Para lo que se dice en clase y no está en Aules. Te avisará igual que con las tareas de Aules.</p>
      <input type="hidden" name="id">
      <div class="segmento" role="radiogroup" aria-label="Tipo">
        <label><input type="radio" name="kind" value="tarea" checked><span>{icon("clipboard-list", 14)}Tarea</span></label>
        <label><input type="radio" name="kind" value="examen"><span>{icon("graduation-cap", 14)}Examen</span></label>
      </div>
      <label class="campo-p"><span>¿Qué es?</span>
        <input name="name" maxlength="200" required placeholder="Ej.: Examen del tema 2, práctica de tablas en Word…"></label>
      <label class="campo-p"><span>Asignatura</span>
        <select name="course">{opciones_cursos}<option value="__otra__">Otra asignatura…</option></select></label>
      <label class="campo-p" id="propia-otra-campo" hidden><span>Nombre de la asignatura</span>
        <input id="propia-otra" maxlength="200" placeholder="Ej.: Itinerario personal para la empleabilidad"></label>
      <div class="dos-campos">
        <label class="campo-p"><span>Fecha</span><input type="date" name="fecha" required></label>
        <label class="campo-p"><span>Hora <em>(opcional)</em></span><input type="time" name="hora"></label>
      </div>
      <div class="atajos" id="propia-atajos"></div>
      <p class="dlg-ayuda" id="propia-ayuda"></p>
      <label class="campo-p"><span>Notas <em>(opcional)</em></span>
        <textarea name="notes" rows="3" maxlength="4000" placeholder="Temas que entran, qué hay que entregar…"></textarea></label>
      <div class="dlg-error" id="propia-error" hidden></div>
      <div class="dlg-botones">
        <button type="button" class="boton-borrar" id="propia-borrar" hidden>{icon("papelera", 14)}Borrar</button>
        <button type="button" class="boton-sec" data-cerrar>Cancelar</button>
        <button type="submit" class="boton-pri">{icon("check", 14)}Guardar</button>
      </div>
    </form>
  </dialog>"""

    firstname = pretty_name(session.get("firstname", ""))
    fullname = pretty_name(session.get("fullname") or session["username"])
    greeting = f'Hola, <em class="rotulador">{html.escape(firstname)}</em>' if firstname else "Tu resumen de Aules"
    # Con foto de Aules se ve la foto; si no carga, debajo siguen las iniciales.
    acc_avatar = html.escape(initials(fullname)) + (
        f'<img src="/foto?v={html.escape(foto)}" alt="" onerror="this.remove()">' if foto else "")
    counts = {
        "all": len(items),
        "examen": sum(1 for a in items if a["kind"] == "examen"),
        "tarea": sum(1 for a in items if a["kind"] == "tarea"),
    }

    body = f"""{_nav("inicio")}
<div class="wrap" id="informe" data-firma="{html.escape(firma)}">
  <div class="hero">
    <div>
      <p class="eyebrow" id="fecha-hoy">Aules · {html.escape(PORTALES[portal_de(session.get("base_url"))][0])}</p>
      <h1>{greeting}</h1>
      <div class="updated"><span class="dot"></span>Actualizado <span id="updated-rel" data-ts="{int(now_ts)}">ahora</span> · <span id="updated-abs">{now.strftime('%d/%m %H:%M')}</span></div>
    </div>
    <div class="hero-actions">
      <button type="button" class="boton-apuntar" data-anadir title="Apuntar una tarea o examen que no está en Aules">{icon("plus", 16)}<span>Apuntar</span></button>
      <form method="post" action="/refresh" id="refresh-form">
        <button class="icon-btn" type="submit" title="Actualizar ahora" aria-label="Actualizar ahora">{icon("refresh", 18)}</button>
      </form>
      <details class="account">
        <summary aria-label="Menú de cuenta"><span class="acc-avatar{" con-foto" if foto else ""}">{acc_avatar}</span><span class="acc-name">{html.escape(fullname)}</span>{icon("chevron-down", 16, "chev-down")}</summary>
        <div class="menu">
          <div class="menu-head"><span class="acc-avatar{" con-foto" if foto else ""}">{acc_avatar}</span><div><div class="menu-name">{html.escape(fullname)}</div><div class="menu-user">{html.escape(session["username"])}</div></div></div>
          <a class="menu-item" href="/ajustes">{icon("settings")}Ajustes</a>
          <a class="menu-item" href="/login">{icon("users")}Cambiar de cuenta</a>
          <form method="post" action="/logout"><button class="menu-item danger" type="submit">{icon("log-out")}Cerrar sesión</button></form>
        </div>
      </details>
    </div>
  </div>

  <div class="aviso-version" id="aviso-version" role="status" hidden></div>
  <div class="warn" id="aviso-revision" role="status" hidden>{icon("triangle-alert")}<span></span></div>
  <div class="popup-aules" id="popup-aules" role="alertdialog" aria-labelledby="popup-aules-titulo" hidden>
    <span class="pa-icono"><span class="pa-fallo">{icon("triangle-alert", 20)}</span><span class="pa-ok">{icon("check", 20)}</span></span>
    <div class="pa-texto"><strong id="popup-aules-titulo"></strong><p></p></div>
    <button type="button" class="pa-cerrar" aria-label="Cerrar">{icon("x", 16)}</button>
  </div>
  {warn_html}

  <div class="stats">
    <div class="stat exam"><div class="stat-label">{icon("graduation-cap", 14)}Exámenes</div><div class="stat-value">{n_exams}</div></div>
    <div class="stat tasks"><div class="stat-label">{icon("clipboard-list", 14)}Tareas pendientes</div><div class="stat-value">{n_tasks}</div></div>
    <div class="stat week"><div class="stat-label">{icon("calendar", 14)}Vencen esta semana</div><div class="stat-value">{n_week}</div></div>
    <div class="stat new"><div class="stat-label">{icon("sparkles", 14)}Nuevas</div><div class="stat-value">{n_new}</div></div>
  </div>

  <a class="ahora" id="ahora" href="/horario" title="Ver el horario de toda la semana" hidden>
    <div class="ahora-bloque">
      <div class="ahora-label">{icon("clock", 12)}Ahora</div>
      <div class="ahora-asig" id="ahora-asig"></div>
      <div class="ahora-info" id="ahora-info"></div>
      <div class="ahora-tareas" id="ahora-tareas" hidden></div>
    </div>
    <div class="ahora-bloque">
      <div class="ahora-label">{icon("chevron-right", 12)}Después<span class="ahora-ver">Ver semana {icon("calendar", 12)}</span></div>
      <div class="ahora-asig" id="sig-asig"></div>
      <div class="ahora-info" id="sig-info"></div>
      <div class="ahora-tareas" id="sig-tareas" hidden></div>
    </div>
  </a>
  <a class="ahora sin-horario" id="sin-horario" href="/horario" hidden>
    <div class="ahora-bloque">
      <div class="ahora-label">{icon("calendar", 12)}Horario</div>
      <div class="ahora-asig">Todavía no has cargado tu horario</div>
      <div class="ahora-info">Pulsa aquí para interpretarlo del PDF de Tutoría o escribirlo a mano.</div>
    </div>
  </a>
  <script type="application/json" id="horario-datos">{horario_json}</script>

  {next_html}

  <div class="toolbar">
    <div class="chips">
      <button class="chip active" data-filter="all">Todo<span class="count">{counts['all']}</span></button>
      <button class="chip" data-filter="examen">Exámenes<span class="count">{counts['examen']}</span></button>
      <button class="chip" data-filter="tarea">Tareas<span class="count">{counts['tarea']}</span></button>
      <button class="chip" data-filter="new">Nuevas<span class="count">{n_new}</span></button>
    </div>
    <label class="search">
      {icon("search")}
      <input id="q" type="search" placeholder="Buscar tarea, asignatura o mensaje…  ( / )" autocomplete="off">
    </label>
  </div>

  {mensajes_html}
  {''.join(sections)}
  {forum_html}
  <div id="empty" class="empty" hidden>{icon("inbox", 40)}<p>No hay nada que mostrar.</p></div>
  {dialogo_propia}
  {DIALOGO_ENTREGA}

  <footer>{icon("clock", 13)}Se actualiza sola cada minuto y medio mientras la app está abierta</footer>
</div>"""

    return _page("Aules · Resumen", body, REPORT_CSS + PROPIAS_CSS + ENTREGA_CSS,
                 REPORT_JS + AHORA_JS + REPORT_JS_FIN + PROPIAS_JS + ENTREGA_JS)


def render_login(error="", username="", can_cancel=False, portal="fp"):
    alert = f'<div class="alert" role="alert">{icon("alert-circle")}<span>{html.escape(error)}</span></div>' if error else ""
    cancel = f'<a class="btn-link" href="/">{icon("arrow-left", 14)}Volver a mi cuenta actual</a>' if can_cancel else ""
    opciones_portal = "".join(
        f'<option value="{clave}"{" selected" if clave == portal else ""}>{html.escape(nombre)}</option>'
        for clave, (nombre, _) in PORTALES.items()
    )
    body = f"""<div class="auth">
  <div class="auth-card">
    <div class="brand"><span class="brand-mark">{icon("book-open", 20)}</span>Aules · Resumen</div>
    <h1>{'Cambiar de cuenta' if can_cancel else 'Inicia sesión'}</h1>
    <p class="auth-sub">Entra con tu usuario y contraseña de Aules.</p>
    {alert}
    <form method="post" action="/login" id="login-form">
      <label class="field"><span>Etapa</span>
        <div class="input select">{icon("graduation-cap")}<select name="portal">{opciones_portal}</select></div>
      </label>
      <label class="field"><span>Usuario</span>
        <div class="input">{icon("user")}<input name="username" autocomplete="username" required autofocus value="{html.escape(username)}"></div>
      </label>
      <label class="field"><span>Contraseña</span>
        <div class="input">{icon("lock")}<input name="password" type="password" autocomplete="current-password" required>
          <button type="button" class="toggle" aria-label="Mostrar contraseña">{icon("eye")}</button></div>
      </label>
      <label class="recordar"><input type="checkbox" name="recordar" value="1" checked>
        <span>Volver a entrar solo si Aules cierra la sesión</span></label>
      <button class="btn-primary" type="submit">Entrar</button>
    </form>
    {cancel}
    <p class="auth-note">{icon("shield-check", 14)}<span>Con la casilla marcada, la contraseña se guarda cifrada con tu usuario de Windows (solo tú, en este equipo, puedes descifrarla) y se borra al cerrar sesión. Sin marcarla, solo se guarda un token de sesión.</span></p>
  </div>
</div>"""
    js = """
(function () {
  var f = document.getElementById('login-form'), b = f.querySelector('.btn-primary');
  var t = f.querySelector('.toggle'), p = f.querySelector('input[name=password]');
  var EYE = __EYE__, EYE_OFF = __EYE_OFF__, LOADER = __LOADER__;
  t.addEventListener('click', function () {
    var show = p.type === 'password';
    p.type = show ? 'text' : 'password';
    t.innerHTML = show ? EYE_OFF : EYE;
    t.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
  });
  f.addEventListener('submit', function () {
    setTimeout(function () { b.disabled = true; b.innerHTML = LOADER + 'Entrando…'; }, 0);
  });
})();
"""
    js = (
        js.replace("__EYE__", json.dumps(icon("eye")))
        .replace("__EYE_OFF__", json.dumps(icon("eye-off")))
        .replace("__LOADER__", json.dumps(icon("loader", 18, "spin")))
    )
    return _page("Aules · Iniciar sesión", body, LOGIN_CSS, js)


MATERIALES_CSS = """
.mat-wrap { max-width: 1200px; margin: 0 auto; padding: 24px 20px 28px; display: flex; flex-direction: column; height: 100vh; }
.mat-top { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.mat-top h1 { font-size: 20px; margin: 0; flex: none; }
.mat-top .search { max-width: 320px; }
.volver { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); text-decoration: none; font-size: 13.5px;
  border: 1px solid var(--border); background: var(--card); border-radius: 999px; padding: 7px 12px; }
.volver:hover { border-color: var(--accent); color: var(--accent); }
.mat-layout { display: grid; grid-template-columns: 340px 1fr; gap: 14px; flex: 1; min-height: 0; }
.mat-arbol, .mat-preview { background: var(--card); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow); }
.mat-arbol { overflow: auto; padding: 8px; }
.mat-preview { overflow: hidden; display: flex; flex-direction: column; }
.mat-preview-head { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.mat-preview-nombre { font-weight: 600; font-size: 14px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mat-preview-sub { font-size: 12px; color: var(--muted); font-weight: 400; }
.mat-preview iframe { flex: 1; width: 100%; border: 0; background: #fff; }
.mat-vacio { flex: 1; display: grid; place-items: center; align-content: center; gap: 10px; color: var(--muted); font-size: 14px; text-align: center; padding: 30px; }
.mat-vacio .i { opacity: .5; }
details.arbol-curso > summary, details.arbol-seccion > summary { display: flex; align-items: center; gap: 7px; cursor: pointer;
  border-radius: 9px; padding: 7px 8px; user-select: none; }
details.arbol-curso > summary:hover, details.arbol-seccion > summary:hover { background: var(--card-2); }
details.arbol-curso > summary { font-weight: 650; font-size: 13.5px; }
details.arbol-seccion > summary { font-size: 13px; color: var(--muted); margin-left: 10px; }
details.arbol-seccion { margin-bottom: 2px; }
.arbol-archivos { margin-left: 26px; }
.arbol-archivo { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; border: 0; background: none; color: var(--text);
  font: inherit; font-size: 13px; text-align: left; border-radius: 8px; cursor: pointer; }
.arbol-archivo:hover { background: var(--card-2); }
.arbol-archivo.activo { background: var(--accent-soft); color: var(--accent); }
.arbol-archivo .ext { font-size: 9.5px; font-weight: 700; background: var(--gray-soft); color: var(--muted); border-radius: 5px; padding: 2px 5px; flex: none; }
.arbol-archivo.activo .ext { background: var(--accent); color: #fff; }
.arbol-nombre { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.arbol-meta { color: var(--muted); font-size: 11px; flex: none; }
.arbol-archivo .pill-new { font-size: 9.5px; padding: 1px 5px; }
.mat-sin-resultados { color: var(--muted); font-size: 13px; padding: 12px; }
@media (max-width: 860px) {
  .mat-wrap { height: auto; }
  .mat-layout { grid-template-columns: 1fr; }
  .mat-arbol { max-height: 45vh; }
  .mat-preview { min-height: 70vh; }
}
"""

MATERIALES_JS = """
(function () {
  var marco = document.getElementById('marco');
  var vacio = document.getElementById('vacio');
  var nombre = document.getElementById('preview-nombre');
  var sub = document.getElementById('preview-sub');
  var abrir = document.getElementById('abrir');
  var descargar = document.getElementById('descargar');
  var botones = Array.prototype.slice.call(document.querySelectorAll('.arbol-archivo'));

  function mostrar(btn) {
    botones.forEach(function (b) { b.classList.remove('activo'); });
    btn.classList.add('activo');
    var url = btn.dataset.externo === '1' ? btn.dataset.url : '/material/' + encodeURIComponent(btn.dataset.id);
    nombre.textContent = btn.dataset.nombre;
    sub.textContent = btn.dataset.ruta;
    abrir.href = url;
    descargar.href = url;
    descargar.hidden = btn.dataset.externo === '1';
    if (btn.dataset.previsualizable === '1') {
      marco.src = url;
      marco.hidden = false;
      vacio.hidden = true;
    } else {
      marco.removeAttribute('src');
      marco.hidden = true;
      vacio.hidden = false;
      vacio.querySelector('p').textContent = btn.dataset.externo === '1'
        ? 'Es un enlace externo. Ábrelo en una pestaña nueva.'
        : 'Este tipo de archivo no se puede previsualizar en el navegador. Descárgalo para abrirlo.';
    }
    try { sessionStorage.setItem('aules-material', btn.dataset.id); } catch (e) {}
  }
  botones.forEach(function (b) { b.addEventListener('click', function () { mostrar(b); }); });

  var buscador = document.getElementById('buscar-material');
  buscador.addEventListener('input', function () {
    var q = buscador.value.trim().toLowerCase();
    botones.forEach(function (b) { b.hidden = !!q && b.dataset.busqueda.indexOf(q) === -1; });
    document.querySelectorAll('details.arbol-seccion').forEach(function (s) {
      var hay = s.querySelector('.arbol-archivo:not([hidden])');
      s.hidden = !hay;
      if (q && hay) s.open = true;
    });
    document.querySelectorAll('details.arbol-curso').forEach(function (c) {
      var hay = c.querySelector('.arbol-archivo:not([hidden])');
      c.hidden = !hay;
      if (q && hay) c.open = true;
    });
    document.getElementById('sin-resultados').hidden = !!document.querySelector('.arbol-archivo:not([hidden])');
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== buscador) { e.preventDefault(); buscador.focus(); }
  });

  var guardado = null;
  try { guardado = sessionStorage.getItem('aules-material'); } catch (e) {}
  var inicial = guardado && botones.filter(function (b) { return b.dataset.id === guardado; })[0];
  // Si no hay nada guardado, se abre el primero que se pueda previsualizar.
  if (!inicial) inicial = botones.filter(function (b) { return b.dataset.previsualizable === '1'; })[0] || botones[0];
  if (inicial) mostrar(inicial);
})();
"""

PREVISUALIZABLES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".txt", ".md", ".csv", ".html"}


def _tamano(bytes_):
    if not bytes_:
        return ""
    if bytes_ >= 1024 * 1024:
        return f"{bytes_ / (1024 * 1024):.1f} MB"
    return f"{max(1, bytes_ // 1024)} KB"


def render_materiales(session, materiales):
    por_curso = {}
    for m in materiales:
        por_curso.setdefault(m["course"], {}).setdefault(m["section"] or "Material", []).append(m)

    cursos_html = []
    for curso, secciones in por_curso.items():
        total = sum(len(v) for v in secciones.values())
        bloques = []
        for seccion, archivos in secciones.items():
            filas = []
            for m in archivos:
                ext = "WEB" if m["externo"] else file_ext(m["filename"])
                previsualizable = (not m["externo"]) and os.path.splitext(m["filename"])[1].lower() in PREVISUALIZABLES
                nuevo = f'<span class="pill pill-new">{icon("sparkles", 11)}Nuevo</span>' if m.get("is_new") else ""
                busqueda = html.escape(f'{m["name"]} {m["filename"]} {seccion} {curso}'.lower())
                filas.append(
                    f'<button type="button" class="arbol-archivo" data-id="{html.escape(m["id"])}" '
                    f'data-nombre="{html.escape(m["name"])}" data-ruta="{html.escape(curso)} · {html.escape(seccion)}" '
                    f'data-externo="{int(bool(m["externo"]))}" data-url="{html.escape(m["url"])}" '
                    f'data-previsualizable="{int(previsualizable)}" data-busqueda="{busqueda}">'
                    f'<span class="ext">{html.escape(ext)}</span>'
                    f'<span class="arbol-nombre">{html.escape(m["name"])}</span>{nuevo}'
                    f'<span class="arbol-meta">{_tamano(m.get("size"))}</span></button>'
                )
            bloques.append(
                f'<details class="arbol-seccion" open><summary>{icon("chevron-right", 13, "chev")}'
                f'{icon("folder", 14)}{html.escape(seccion)}<span class="arbol-meta">{len(archivos)}</span></summary>'
                f'<div class="arbol-archivos">{"".join(filas)}</div></details>'
            )
        cursos_html.append(
            f'<details class="arbol-curso" open><summary>{icon("chevron-right", 13, "chev")}'
            f'{icon("book-open", 15)}<span class="arbol-nombre">{html.escape(curso)}</span>'
            f'<span class="arbol-meta">{total}</span></summary>{"".join(bloques)}</details>'
        )

    arbol = "".join(cursos_html) or f'<p class="mat-sin-resultados">No hay material todavía.</p>'
    body = f"""{_nav("materiales", ancha=True)}
<div class="mat-wrap">
  <div class="mat-top">
    <h1>Materiales</h1>
    <label class="search">{icon("search")}
      <input id="buscar-material" type="search" placeholder="Buscar archivo…  ( / )" autocomplete="off">
    </label>
  </div>
  <div class="mat-layout">
    <aside class="mat-arbol">{arbol}<p class="mat-sin-resultados" id="sin-resultados" hidden>Ningún archivo coincide.</p></aside>
    <section class="mat-preview">
      <div class="mat-preview-head">
        {icon("clipboard-list", 16)}
        <div class="mat-preview-nombre" id="preview-nombre">Elige un archivo</div>
        <span class="mat-preview-sub" id="preview-sub"></span>
        <a class="mini-btn" id="abrir" href="#" target="_blank" rel="noopener">{icon("external-link", 13)}Abrir</a>
        <a class="mini-btn" id="descargar" href="#" download>{icon("folder", 13)}Descargar</a>
      </div>
      <iframe id="marco" title="Vista previa" hidden></iframe>
      <div class="mat-vacio" id="vacio">{icon("inbox", 34)}<p>Elige un archivo del árbol para verlo aquí.</p></div>
    </section>
  </div>
</div>"""
    return _page("Aules · Materiales", body, REPORT_CSS + AJUSTES_CSS + MATERIALES_CSS, MATERIALES_JS)


HORARIO_CSS = """
.volver-link { display: inline-flex; align-items: center; gap: 6px; font-size: 13.5px; font-weight: 550; color: var(--muted);
  text-decoration: none; margin-bottom: 10px; padding: 6px 12px 6px 8px; border: 1px solid var(--border); background: var(--card);
  border-radius: 999px; box-shadow: var(--shadow); }
.volver-link:hover { color: var(--accent); border-color: var(--accent); }
.pestanas-horario { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.pestanas-horario .chip { text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
.pestanas-horario .pill { font-size: 10px; }
.nota-horario { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 12px 16px;
  margin-bottom: 16px; color: var(--muted); font-size: 13.5px; }
.nota-horario a { color: var(--accent); }
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
.acciones-horario .principal { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff; border: 0; }
.acciones-horario .principal:hover { color: #fff; filter: brightness(1.07); }
.campo { width: 100%; background: var(--card-2); border: 1px solid var(--border); border-radius: 8px; padding: 5px 8px;
  font: inherit; font-size: 12.5px; color: var(--text); outline: none; margin-bottom: 4px; }
.campo:focus { border-color: var(--accent); }
.fila-editar { padding: 10px 12px; border-top: 1px solid var(--border); }
.fila-editar .dos { display: flex; gap: 4px; }
.quitar, .anadir { border: 0; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; padding: 4px 0; }
.quitar:hover { color: var(--red); }
.anadir { padding: 10px 14px; color: var(--accent); }
@media (max-width: 900px) { .semana { grid-template-columns: 1fr; } }
"""

HORARIO_JS = """
(function () {
  var editar = document.getElementById('editar');
  if (!editar) return;
  var DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'];
  var datos = JSON.parse(document.getElementById('horario-editar').textContent || '{}');
  var idHorario = document.getElementById('semana').dataset.id;
  var editor = document.getElementById('editor'), semana = document.getElementById('semana');
  var acciones = document.getElementById('acciones-vista'), accionesEditor = document.getElementById('acciones-editor');
  var tabla = {};

  function campo(fila, clave, ejemplo) {
    var input = document.createElement('input');
    input.className = 'campo'; input.value = fila[clave] || ''; input.placeholder = ejemplo;
    input.addEventListener('input', function () { fila[clave] = input.value; });
    return input;
  }
  function pintar() {
    editor.innerHTML = '';
    DIAS.forEach(function (dia) {
      var col = document.createElement('section'); col.className = 'dia';
      var cab = document.createElement('header'); cab.className = 'dia-cab'; cab.textContent = dia; col.append(cab);
      tabla[dia].forEach(function (fila, i) {
        var caja = document.createElement('div'); caja.className = 'fila-editar';
        var dos = document.createElement('div'); dos.className = 'dos';
        dos.append(campo(fila, 'inicio', '08:00'), campo(fila, 'fin', '08:55'));
        var quitar = document.createElement('button'); quitar.type = 'button'; quitar.className = 'quitar'; quitar.textContent = 'Quitar';
        quitar.addEventListener('click', function () { tabla[dia].splice(i, 1); pintar(); });
        caja.append(dos, campo(fila, 'asignatura', 'Asignatura o DESCANSO'), campo(fila, 'aula', 'Aula'), quitar);
        col.append(caja);
      });
      var anadir = document.createElement('button'); anadir.type = 'button'; anadir.className = 'anadir'; anadir.textContent = '+ Añadir franja';
      anadir.addEventListener('click', function () { tabla[dia].push({ inicio: '', fin: '', asignatura: '', aula: '', profesor: '' }); pintar(); });
      col.append(anadir);
      editor.append(col);
    });
  }
  function modo(editando) {
    editor.hidden = !editando; semana.hidden = editando;
    acciones.hidden = editando; accionesEditor.hidden = !editando;
  }
  async function enviar(ruta, cuerpo) {
    var r = await fetch(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) });
    var d = await r.json().catch(function () { return {}; });
    if (!r.ok || d.error) throw new Error(d.error || 'No se pudo guardar');
  }
  editar.addEventListener('click', function () {
    DIAS.forEach(function (d) { tabla[d] = ((datos.dias || {})[d] || []).map(function (f) { return Object.assign({}, f); }); });
    pintar(); modo(true);
  });
  document.getElementById('cancelar').addEventListener('click', function () { modo(false); });
  document.getElementById('guardar').addEventListener('click', async function () {
    try { await enviar('/api/horario/guardar', { id: idHorario, horario: { nombre: datos.nombre, dias: tabla } }); location.reload(); }
    catch (e) { alert(e.message); }
  });
  var releer = document.getElementById('releer');
  if (releer) releer.addEventListener('click', async function () {
    if (!confirm('Se descartarán tus correcciones y se volverá a leer el PDF. ¿Seguro?')) return;
    try { await enviar('/api/horario/releer', { id: idHorario }); location.reload(); }
    catch (e) { alert(e.message); }
  });
})();
"""


def render_horario(horarios, seleccionado=None, no_lectivos=None):
    elegido = next((h for h in horarios if h["id"] == seleccionado), None) \
        or next((h for h in horarios if h["activo"]), None) \
        or (horarios[0] if horarios else None)

    pestanas = "".join(
        f'<a class="chip{" active" if elegido and h["id"] == elegido["id"] else ""}" href="/horario?id={html.escape(quote(h["id"]))}">'
        f'{icon("calendar", 13)}{html.escape(h["nombre"])}'
        + (f'<span class="pill pill-new">Ahora</span>' if h["activo"] else "")
        + "</a>"
        for h in horarios
    )

    cuerpo = ""
    datos = (elegido or {}).get("horario") or {}
    if not elegido:
        cuerpo = '<div class="nota-horario">No encuentro ningún PDF de horario en el curso de Tutoría.</div>'
    elif not datos.get("dias"):
        cuerpo = '<div class="nota-horario">No se pudo leer este PDF. Pulsa «Corregir horario» para escribirlo a mano.</div>'
    else:
        if elegido["activo"]:
            cuerpo += f"""<a class="ahora" id="ahora" hidden>
    <div class="ahora-bloque"><div class="ahora-label">{icon("clock", 12)}Ahora</div>
      <div class="ahora-asig" id="ahora-asig"></div><div class="ahora-info" id="ahora-info"></div></div>
    <div class="ahora-bloque"><div class="ahora-label">{icon("chevron-right", 12)}Después</div>
      <div class="ahora-asig" id="sig-asig"></div><div class="ahora-info" id="sig-info"></div></div>
  </a>
  <script type="application/json" id="horario-datos">{json.dumps(dict(datos, no_lectivos=no_lectivos or {}), ensure_ascii=False)}</script>"""
        else:
            actual = next((h for h in horarios if h["activo"]), None)
            cuerpo += (
                f'<div class="nota-horario">Estás viendo el horario de <strong>{html.escape(elegido["nombre"].lower())}</strong>. '
                + (f'Ahora mismo toca el de <a href="/horario">{html.escape(actual["nombre"].lower())}</a>.' if actual else "")
                + "</div>"
            )

        columnas = []
        for dia in ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]:
            filas = []
            for f in datos["dias"].get(dia, []):
                patio = bool(re.search(r"(?i)descanso|recreo|patio", f.get("asignatura", "")))
                detalle = " · ".join(x for x in (f.get("aula"), f.get("profesor")) if x)
                atributos = f' data-franja-inicio="{html.escape(f["inicio"])}" data-franja-fin="{html.escape(f.get("fin", ""))}"' if elegido["activo"] else ""
                filas.append(
                    f'<div class="fila{" patio" if patio else ""}"{atributos}>'
                    f'<div class="fila-hora">{html.escape(f["inicio"])}<br>{html.escape(f.get("fin", ""))}</div>'
                    f'<div class="fila-asig">{"Patio" if patio else html.escape(f.get("asignatura", ""))}'
                    + (f'<div class="fila-aula">{html.escape(detalle)}</div>' if detalle and not patio else "")
                    + "</div></div>"
                )
            contenido = "".join(filas) or '<div class="sin-clases">Sin clases</div>'
            marca_dia = f' data-dia="{dia}"' if elegido["activo"] else ""
            columnas.append(
                f'<section class="dia"{marca_dia}><header class="dia-cab">{dia}<span class="sin-clase-txt"></span><span class="hoy-txt">Hoy</span></header>{contenido}</section>'
            )
        cuerpo += f'<div class="semana" id="semana" data-id="{html.escape(elegido["id"])}">{"".join(columnas)}</div>'
        cuerpo += '<div class="semana" id="editor" hidden></div>'

    origen = datos.get("modelo", "")
    releer = '<button type="button" id="releer">' + icon("refresh", 14) + 'Volver a leer del PDF</button>' if origen and origen != "leído del PDF" else ""
    acciones = ""
    if elegido:
        acciones = f"""<div class="acciones-horario" id="acciones-vista">
    <button type="button" id="editar">{icon("pencil", 14)}Corregir horario</button>
    <a href="/material/{html.escape(quote(elegido["id"]))}" target="_blank" rel="noopener">{icon("folder", 14)}Ver el PDF original</a>
    {releer}
  </div>
  <div class="acciones-horario" id="acciones-editor" hidden>
    <button type="button" class="principal" id="guardar">{icon("check", 14)}Guardar horario</button>
    <button type="button" id="cancelar">Cancelar</button>
  </div>
  <script type="application/json" id="horario-editar">{json.dumps(datos, ensure_ascii=False)}</script>"""

    procedencia = ""
    if origen:
        procedencia = "Leído automáticamente del PDF de Tutoría" if origen == "leído del PDF" else "Corregido por ti"

    body = f"""{_nav("horario", ancha=True)}
<div class="wrap wrap-ancha">
  <div class="hero">
    <div>
      <p class="eyebrow">Semana de clase</p>
      <h1>Horario</h1>
      <div class="updated">{html.escape(procedencia)}</div>
    </div>
  </div>
  <div class="pestanas-horario">{pestanas}</div>
  {cuerpo}
  {acciones}
  {_dias_sin_clase_html(no_lectivos)}
</div>"""
    return _page("Aules · Horario", body, REPORT_CSS + HORARIO_CSS, AHORA_JS + HORARIO_JS)


PROFESORES_CSS = """
.profes { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr)); gap: 14px; }
.profe { background: var(--card); border: 1px solid var(--border); border-radius: 18px; box-shadow: var(--shadow); padding: 16px 18px;
  display: flex; flex-direction: column; gap: 12px; }
.profe-cab { display: flex; gap: 12px; align-items: center; }
.profe-nombre { font-weight: 650; font-size: 15.5px; line-height: 1.3; margin: 0; }
.profe-asig { font-size: 12.5px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
.correo { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; background: var(--card-2); border: 1px solid var(--border);
  border-radius: 12px; padding: 8px 10px; }
.correo-dir { flex: 1; min-width: 0; font-size: 14px; font-weight: 550; color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
.correo-dir:hover { color: var(--accent); text-decoration: underline; }
.pill-deducido { background: var(--amber-soft); color: var(--amber); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.correo-origen { font-size: 12px; color: var(--muted); margin-top: -6px; }
.profe-acciones { display: flex; gap: 8px; flex-wrap: wrap; }
.boton-p { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--border); background: var(--card); color: var(--text);
  border-radius: 999px; padding: 6px 12px; font: inherit; font-size: 13px; text-decoration: none; cursor: pointer; }
.boton-p:hover { border-color: var(--accent); color: var(--accent); }
.boton-p.principal { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff; border: 0; }
.boton-p.principal:hover { color: #fff; filter: brightness(1.07); }
.copiar { border: 0; background: none; color: var(--muted); cursor: pointer; padding: 4px; border-radius: 8px; display: grid; place-items: center; }
.copiar:hover { color: var(--accent); background: var(--accent-soft); }
.copiado { font-size: 12px; color: var(--green); font-weight: 600; }
.otros { margin-top: 28px; }
.otros h2 { font-size: 16px; margin: 0 0 4px; }
.otros p { color: var(--muted); font-size: 13px; margin: 0 0 10px; }
.otro { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 12px; background: var(--card); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 8px; }
.otro-fuente { font-size: 12px; color: var(--muted); width: 100%; margin-top: -4px; }
.buscar-profes { margin-bottom: 16px; }
"""

PROFESORES_JS = """
(function () {
  document.querySelectorAll('.copiar').forEach(function (b) {
    b.addEventListener('click', async function () {
      var texto = b.dataset.correo;
      try { await navigator.clipboard.writeText(texto); }
      catch (e) {
        var t = document.createElement('textarea'); t.value = texto; document.body.append(t); t.select();
        try { document.execCommand('copy'); } catch (e2) {} t.remove();
      }
      var aviso = b.parentNode.querySelector('.copiado');
      if (aviso) { aviso.hidden = false; setTimeout(function () { aviso.hidden = true; }, 1600); }
    });
  });
  var q = document.getElementById('q');
  if (q) q.addEventListener('input', function () {
    var v = q.value.trim().toLowerCase();
    document.querySelectorAll('.profe').forEach(function (c) { c.hidden = !!v && c.dataset.search.indexOf(v) === -1; });
  });
})();
"""


def _correo_html(correo, etiqueta):
    return (
        f'<div class="correo">{icon("mail", 15)}'
        f'<a class="correo-dir" href="mailto:{html.escape(correo)}">{html.escape(correo)}</a>{etiqueta}'
        f'<button type="button" class="copiar" data-correo="{html.escape(correo)}" title="Copiar el correo" aria-label="Copiar el correo">{icon("copy", 15)}</button>'
        '<span class="copiado" hidden>Copiado</span></div>'
    )


def render_profesores(datos):
    tarjetas = []
    for p in datos.get("profesores", []):
        nombre = pretty_name(p["name"])
        if p["email"]:
            correo = _correo_html(p["email"], f'<span class="pill pill-done">{icon("check", 11)}Confirmado</span>')
            origen = f'<div class="correo-origen">Sacado de {html.escape(p["email_origin"])}</div>'
        elif p["email_guess"]:
            correo = _correo_html(p["email_guess"], '<span class="pill pill-deducido">Deducido</span>')
            origen = ('<div class="correo-origen">No está publicado en Aules. Sigue el formato de los correos de la GVA '
                      '(iniciales del nombre + apellidos), así que casi seguro es este, pero no está confirmado.</div>')
        else:
            correo, origen = "", '<div class="correo-origen">No se ha encontrado su correo: escríbele por Aules.</div>'
        search = html.escape(f'{p["name"]} {" ".join(p["courses"])} {p["email"] or p["email_guess"]}'.lower())
        tarjetas.append(
            f'<article class="profe" data-search="{search}">'
            f'<div class="profe-cab"><div class="avatar" style="--hue: {course_hue(p["name"])}">{html.escape(initials(nombre))}</div>'
            f'<div><h2 class="profe-nombre">{html.escape(nombre)}</h2>'
            f'<div class="profe-asig">{html.escape(" · ".join(p["courses"]))}</div></div></div>'
            f'{correo}{origen}'
            '<div class="profe-acciones">'
            + (f'<a class="boton-p principal" href="mailto:{html.escape(p["email"] or p["email_guess"])}">{icon("mail", 14)}Escribir un correo</a>'
               if p["email"] or p["email_guess"] else "")
            + f'<a class="boton-p" href="{html.escape(p["message_url"])}" target="_blank" rel="noopener noreferrer">{icon("message-square", 14)}Mensaje por Aules</a>'
            "</div></article>"
        )
    if not tarjetas:
        tarjetas.append('<div class="nota-horario">Todavía no hay datos de profesores. Se cargan en la próxima actualización (como mucho, en unos minutos).</div>')

    otros = ""
    if datos.get("otros"):
        filas = "".join(
            f'<div class="otro">{icon("mail", 14)}<a class="correo-dir" href="mailto:{html.escape(o["email"])}">{html.escape(o["email"])}</a>'
            f'<button type="button" class="copiar" data-correo="{html.escape(o["email"])}" title="Copiar el correo" aria-label="Copiar el correo">{icon("copy", 15)}</button>'
            '<span class="copiado" hidden>Copiado</span>'
            f'<div class="otro-fuente">Aparece en {html.escape(", ".join(o["sources"]))}</div></div>'
            for o in datos["otros"]
        )
        otros = (
            '<section class="otros"><h2>Otros correos que aparecen en Aules</h2>'
            '<p>Direcciones escritas en descripciones, foros o documentos que no son de tus profesores (secretaría, jefatura, el instituto…).</p>'
            f'{filas}</section>'
        )

    body = f"""{_nav("profesores")}
<div class="wrap">
  <div class="hero">
    <div>
      <p class="eyebrow">Contacto</p>
      <h1>Profesores y correos</h1>
      <div class="updated">Un profesor por asignatura, con su correo y un acceso para escribirle por Aules.</div>
    </div>
  </div>
  <label class="search buscar-profes">{icon("search")}<input id="q" type="search" placeholder="Buscar por nombre o asignatura…" autocomplete="off"></label>
  <div class="profes">{"".join(tarjetas)}</div>
  {otros}
</div>"""
    return _page("Aules · Profesores", body, REPORT_CSS + HORARIO_CSS + PROFESORES_CSS, PROFESORES_JS)


APARIENCIA_CSS = """
.temas { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(150px, 100%), 1fr)); gap: 10px; margin-bottom: 8px; }
.tema { position: relative; display: flex; flex-direction: column; gap: 8px; padding: 8px 8px 10px; border: 1px solid var(--border);
  border-radius: 14px; background: var(--card-2); cursor: pointer; font-size: 14px; font-weight: 700; transition: border-color .15s, box-shadow .15s; }
.tema:hover { border-color: var(--muted); }
.tema:has(input:checked) { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.tema:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
.tema input { position: absolute; opacity: 0; pointer-events: none; }
.tema-nombre { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 0 2px; }
.tema-nombre .i { color: var(--accent); visibility: hidden; }
.tema:has(input:checked) .tema-nombre .i { visibility: visible; }
.tema-desc { min-height: 38px; margin: 0 0 16px; font-size: 13px; color: var(--muted); }
.modos { display: flex; gap: 4px; padding: 4px; background: var(--card-2); border: 1px solid var(--border); border-radius: 999px; margin-bottom: 6px; }
.modo { flex: 1; min-width: 0; display: flex; justify-content: center; align-items: center; gap: 6px; padding: 7px 6px; border-radius: 999px;
  font-size: 13.5px; font-weight: 600; color: var(--muted); cursor: pointer; white-space: nowrap; }
@media (max-width: 420px) { .modo .i { display: none; } }
.modo input { position: absolute; opacity: 0; pointer-events: none; }
.modo:has(input:checked) { background: var(--text); color: var(--bg); }
.modo:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
.modo:has(input:disabled) { opacity: .4; cursor: not-allowed; }
.modo-nota { font-size: 12.5px; color: var(--muted); min-height: 18px; }
.estado-apariencia { min-height: 18px; margin: 6px 0 18px; }
.ajustes { place-items: start center; }
.ajustes-col { width: 100%; max-width: 560px; display: flex; flex-direction: column; gap: 16px; }
.ajustes-col .auth-card { max-width: none; }
.ajustes-col > .btn-link { margin-top: 0; }
.ajustes-cab { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.ajustes-cab h1 { margin: 0; font-size: clamp(28px, 5vw, 36px); letter-spacing: -.03em; }
.pestanas-ajustes { display: flex; gap: 6px; flex-wrap: wrap; }
.pestanas-ajustes .chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--border); background: var(--card); color: var(--text);
  padding: 7px 14px; border-radius: 999px; font-size: 13.5px; font-weight: 600; text-decoration: none; }
.pestanas-ajustes .chip:hover { border-color: var(--accent); }
.pestanas-ajustes .chip.active { background: var(--text); color: var(--bg); border-color: var(--text); }
.seccion-titulo { display: flex; align-items: center; gap: 10px; margin: 0 0 4px; font-family: var(--display); font-size: 23px; letter-spacing: -.02em; }
.seccion-titulo .i { color: var(--accent); }
""" + PREVIAS_CSS

PESTANAS_AJUSTES_JS = """
(function () {
  var pestanas = document.querySelectorAll('.pestanas-ajustes [data-seccion]');
  function mostrar(clave) {
    if (!document.getElementById(clave)) return;
    pestanas.forEach(function (p) {
      var activa = p.dataset.seccion === clave;
      p.classList.toggle('active', activa);
      p.setAttribute('aria-selected', activa ? 'true' : 'false');
      document.getElementById(p.dataset.seccion).hidden = !activa;
    });
  }
  pestanas.forEach(function (p) {
    p.addEventListener('click', function (e) {
      e.preventDefault();
      mostrar(p.dataset.seccion);
      history.replaceState(null, '', '#' + p.dataset.seccion);
    });
  });
  if (location.hash) mostrar(location.hash.slice(1));
})();
"""

APARIENCIA_JS = """
(function () {
  var form = document.getElementById('form-apariencia');
  if (!form) return;
  var estado = document.getElementById('estado-apariencia');
  var desc = document.getElementById('tema-desc');
  var nota = document.getElementById('modo-nota');
  var raiz = document.documentElement;
  function cargarFuente(url) {
    if (!url || document.querySelector('link[href="' + url + '"]')) return;
    var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = url; document.head.append(l);
  }
  // Un tema con un solo modo (p. ej. Terminal, siempre oscuro) bloquea los demás.
  function ajustarModos() {
    var tema = form.querySelector('input[name=estilo]:checked');
    var permitidos = tema.dataset.modos.split(' ');
    form.querySelectorAll('input[name=modo]').forEach(function (r) { r.disabled = permitidos.indexOf(r.value) === -1; });
    nota.textContent = permitidos.length === 1 ? 'Este tema solo tiene modo ' + permitidos[0] + '.' : '';
    desc.textContent = tema.dataset.desc;
    var modo = form.querySelector('input[name=modo]:checked');
    return permitidos.length === 1 ? permitidos[0] : (modo ? modo.value : 'auto');
  }
  ajustarModos();
  form.addEventListener('change', function () {
    var tema = form.querySelector('input[name=estilo]:checked');
    var datos = { estilo: tema.value, modo: form.modo.value };
    cargarFuente(tema.dataset.fuentes);
    // Se ve al momento; luego se guarda para el resto de pantallas.
    raiz.dataset.estilo = datos.estilo;
    raiz.dataset.modo = ajustarModos();
    estado.textContent = 'Guardando…';
    fetch('/ajustes/apariencia', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(datos) })
      .then(function (r) { if (!r.ok) throw new Error(); estado.textContent = 'Guardado'; })
      .catch(function () { estado.textContent = 'No se pudo guardar. Inténtalo de nuevo.'; });
  });
})();
"""


def _apariencia_html(ajustes):
    actual, _ = elegido(ajustes)
    modo_guardado = ajustes.get("modo") if ajustes.get("modo") in MODOS else "auto"
    temas = "".join(
        f'<label class="tema"><input type="radio" name="estilo" value="{clave}"{" checked" if clave == actual else ""} '
        f'data-modos="{" ".join(t["modos"])}" data-fuentes="{html.escape(t["fuentes"])}" data-desc="{html.escape(t["descripcion"])}">'
        f'<span class="pv" data-t="{clave}" aria-hidden="true"><span class="pv-h"></span><span class="pv-s"><i></i><i></i><i></i></span>'
        f'<span class="pv-c"><b></b><u></u></span></span>'
        f'<span class="tema-nombre">{html.escape(t["nombre"])}{icon("check-circle", 15)}</span></label>'
        for clave, t in TEMAS.items()
    )
    iconos = {"auto": "monitor", "claro": "sun", "oscuro": "moon"}
    modos = "".join(
        f'<label class="modo"><input type="radio" name="modo" value="{clave}"{" checked" if clave == modo_guardado else ""}>'
        f'{icon(iconos[clave], 14)}{nombre}</label>'
        for clave, nombre in MODOS.items()
    )
    return f"""<h2 class="seccion-titulo">{icon("palette", 20)}Apariencia</h2>
    <p class="auth-sub">Cada tema cambia toda la estética de la app: colores, letra, formas y cómo se colocan algunas cosas.</p>
    <form id="form-apariencia" onsubmit="return false">
      <div class="field"><span>Tema</span><div class="temas" role="radiogroup" aria-label="Tema">{temas}</div></div>
      <p class="tema-desc" id="tema-desc">{html.escape(TEMAS[actual]["descripcion"])}</p>
      <div class="field"><span>Modo</span><div class="modos" role="radiogroup" aria-label="Modo">{modos}</div>
        <div class="modo-nota" id="modo-nota"></div></div>
      <div class="estado estado-apariencia" id="estado-apariencia" role="status"></div>
    </form>"""


def render_ajustes(ajustes, proveedores, error="", correcto="", seccion="apariencia"):
    opciones = "".join(
        f'<option value="{p}" data-url="{html.escape(d.get("url", ""))}" data-clave="{int(d.get("clave", True))}"'
        f'{" selected" if ajustes["proveedor"] == p else ""}>{html.escape(d["nombre"])}</option>'
        for p, d in proveedores.items()
    )
    avisos = ""
    if error:
        avisos += f'<div class="alert" role="alert">{icon("alert-circle")}<span>{html.escape(error)}</span></div>'
    if correcto:
        avisos += f'<div class="alert ok" role="status">{icon("check-circle")}<span>{html.escape(correcto)}</span></div>'
    clave_guardada = bool(ajustes.get("api_key"))
    modelo = ajustes.get("modelo", "")
    opcion_modelo = (
        f'<option value="{html.escape(modelo)}">{html.escape(modelo)}</option>'
        if modelo
        else '<option value="">— elige un modelo —</option>'
    )
    secciones = (("apariencia", "palette", "Apariencia"), ("ia", "sparkles", "Inteligencia artificial"))
    pestanas = "".join(
        f'<a class="chip{" active" if clave == seccion else ""}" href="#{clave}" role="tab" data-seccion="{clave}" '
        f'aria-selected="{"true" if clave == seccion else "false"}" aria-controls="{clave}">{icon(ic, 15)}{texto}</a>'
        for clave, ic, texto in secciones
    )
    body = f"""{_nav()}
<div class="auth ajustes">
  <div class="ajustes-col">
    <div class="ajustes-cab">
      <h1>Ajustes</h1>
      <div class="pestanas-ajustes" role="tablist" aria-label="Secciones de ajustes">{pestanas}</div>
    </div>
  <section class="auth-card ancha" id="apariencia" role="tabpanel"{"" if seccion == "apariencia" else " hidden"}>
    {_apariencia_html(ajustes)}
  </section>
  <section class="auth-card ancha" id="ia" role="tabpanel"{"" if seccion == "ia" else " hidden"}>
    <h2 class="seccion-titulo">{icon("sparkles", 20)}Inteligencia artificial</h2>
    <p class="auth-sub">Se usa para resumir tareas y escribir borradores. La clave se guarda solo en este equipo.</p>
    {avisos}
    <form method="post" action="/ajustes#ia" id="form-ajustes" data-clave="{1 if clave_guardada else 0}">
      <label class="field"><span>1 · Proveedor</span>
        <div class="input select">{icon("sparkles")}<select name="proveedor">{opciones}</select></div>
      </label>
      <label class="field"><span>2 · API key</span>
        <div class="input">{icon("lock")}<input name="api_key" type="password" autocomplete="off" placeholder="{'guardada · escribe otra para cambiarla' if clave_guardada else 'pega aquí tu clave'}"></div>
      </label>
      <label class="field"><span>3 · Modelo</span>
        <div class="input select" id="campo-modelo">{icon("clipboard-list")}<select name="modelo" id="modelo">{opcion_modelo}</select></div>
      </label>
      <div class="acciones-modelo">
        <button type="button" class="mini-btn" id="cargar-modelos">{icon("refresh", 13)}Ver los modelos de mi clave</button>
        <button type="button" class="mini-btn" id="modo-manual">Escribirlo a mano</button>
        <span class="estado" id="estado-modelos"></span>
      </div>
      <label class="field"><span>URL del proveedor <span class="opt">(solo para compatibles con OpenAI)</span></span>
        <div class="input">{icon("external-link")}<input name="base_url" value="{html.escape(ajustes.get("base_url", ""))}" placeholder="https://api.groq.com/openai/v1" autocomplete="off"></div>
      </label>
      <label class="check"><input type="checkbox" name="borrar_clave" value="1"><span>Borrar la clave guardada</span></label>
      <button class="btn-primary" type="submit" name="accion" value="probar">{icon("refresh", 18)}Guardar y probar</button>
      <button class="btn-link" type="submit" name="accion" value="guardar">Guardar sin probar</button>
    </form>
    <p class="auth-note">{icon("shield-check", 14)}<span>Los borradores son un punto de partida para que los revises y corrijas: la IA se ciñe al enunciado y al temario, pero puede equivocarse.</span></p>
  </section>
  <a class="btn-link" href="/">{icon("arrow-left", 14)}Volver a mis tareas</a>
  </div>
</div>"""
    return _page("Aules · Ajustes", body, LOGIN_CSS + AJUSTES_CSS + APARIENCIA_CSS, AJUSTES_JS + APARIENCIA_JS + PESTANAS_AJUSTES_JS)


def render_preparando(error=""):
    """La primera vez con una cuenta, mientras se lee todo de Aules: en vez de dejar el navegador colgado."""
    if error:
        estado = (
            f'<div class="alert" role="alert">{icon("alert-circle")}<span>{html.escape(error)}</span></div>'
            f'<form method="post" action="/refresh"><button class="btn-primary" type="submit">{icon("refresh", 18)}Reintentar</button></form>'
        )
    else:
        estado = (
            f'<p class="preparando" role="status">{icon("loader", 18, "spin")}<span>Leyendo tus tareas, notas y mensajes de Aules…</span></p>'
            '<p class="auth-sub">La primera vez tarda unos segundos. Las siguientes entrarás al momento.</p>'
        )
    body = f"""<div class="auth">
  <div class="auth-card">
    <div class="brand"><span class="brand-mark">{icon("book-open", 20)}</span>Aules · Resumen</div>
    <h1>Preparando tu resumen</h1>
    {estado}
    <form method="post" action="/logout"><button class="btn-link" type="submit">{icon("log-out", 14)}Cerrar sesión</button></form>
  </div>
</div>"""
    css = """
.preparando { display: flex; align-items: center; gap: 10px; margin: 14px 0 6px; font-weight: 550; }
.preparando .i { color: var(--accent); }
"""
    # Mira cada segundo y medio si ya está: entonces (o si falló, para enseñar el error) recarga.
    js = "" if error else """
(function () {
  async function mirar() {
    try {
      var r = await fetch('/api/informe', { cache: 'no-store' });
      if (r.url.indexOf('/login') !== -1) { location.href = '/login'; return; }
      var d = await r.json();
      if (d.actualizado || (d.error && !d.comprobando)) { location.reload(); return; }
    } catch (e) {}
    setTimeout(mirar, 1500);
  }
  setTimeout(mirar, 1500);
})();
"""
    return _page("Aules · Preparando", body, LOGIN_CSS + css, js)


def render_error(message):
    body = f"""<div class="auth">
  <div class="auth-card">
    <div class="brand"><span class="brand-mark">{icon("book-open", 20)}</span>Aules · Resumen</div>
    <div class="alert" role="alert">{icon("alert-circle")}<span>{html.escape(message)}</span></div>
    <form method="post" action="/refresh"><button class="btn-primary" type="submit">{icon("refresh", 18)}Reintentar</button></form>
    <form method="post" action="/logout"><button class="btn-link" type="submit">{icon("log-out", 14)}Cerrar sesión</button></form>
  </div>
</div>"""
    return _page("Aules · Error", body, LOGIN_CSS)
