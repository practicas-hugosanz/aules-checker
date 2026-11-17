"""Página de ajustes: la apariencia (tema y modo claro u oscuro) y la configuración de la IA."""
import html

from comun import _nav, _page, AJUSTES_CSS, icon, LOGIN_CSS
from temas import elegido, MODOS, PREVIAS_CSS, TEMAS


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
