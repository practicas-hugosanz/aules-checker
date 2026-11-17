"""Página de profesores: quién da cada asignatura y cómo escribirle."""
import html

from comun import _nav, _page, course_hue, HORARIO_CSS, icon, initials, pretty_name, REPORT_CSS


PROFESORES_CSS = """
.profes { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr)); gap: 14px; }
.profe { background: var(--card); border: 1px solid var(--border); border-radius: 18px; box-shadow: var(--shadow); padding: 16px 18px;
  display: flex; flex-direction: column; gap: 12px; }
.profe-cab { display: flex; gap: 12px; align-items: center; }
.profe-nombre { font-weight: 650; font-size: 15.5px; line-height: 1.3; margin: 0; }
.profe-asig { font-size: 12.5px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
.correo { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; background: var(--card-2); border: 1px solid var(--border);
  border-radius: 12px; padding: 8px 10px; }
.correo-dir { flex: 1; min-width: 0; min-height: 24px; font-size: 14px; font-weight: 550; color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
.correo-dir:hover { color: var(--accent); text-decoration: underline; }
.pill-deducido { background: var(--amber-soft); color: var(--amber); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.correo-origen { font-size: 12px; color: var(--muted); margin-top: -6px; }
.profe-acciones { display: flex; gap: 8px; flex-wrap: wrap; }
.boton-p { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--border); background: var(--card); color: var(--text);
  border-radius: 999px; padding: 6px 12px; font: inherit; font-size: 13px; text-decoration: none; cursor: pointer; }
.boton-p:hover { border-color: var(--accent); color: var(--accent); }
.boton-p.principal { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: var(--on-accent); border: 0; }
.boton-p.principal:hover { color: var(--on-accent); filter: brightness(1.07); }
.copiar { border: 0; background: none; color: var(--muted); cursor: pointer; padding: 6px; border-radius: 8px; display: grid; place-items: center; }
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
