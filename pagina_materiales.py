"""Página del material del curso: los archivos y enlaces de cada asignatura, con vista previa."""
import html
import os

from comun import _nav, _page, AJUSTES_CSS, file_ext, icon, REPORT_CSS


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
.arbol-archivo.activo { background: var(--accent-soft); color: var(--accent-ink); }
.arbol-archivo .ext { font-size: 11px; font-weight: 700; background: var(--gray-soft); color: var(--muted); border-radius: 5px; padding: 2px 5px; flex: none; }
.arbol-archivo.activo .ext { background: var(--card); color: var(--accent-ink); }
.arbol-nombre { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.arbol-meta { color: var(--muted); font-size: 11px; flex: none; }
.arbol-archivo .pill-new { font-size: 11px; padding: 1px 5px; }
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
