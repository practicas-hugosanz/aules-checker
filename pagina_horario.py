"""Página del horario de clases de la semana, con los días sin clase."""
import html
import json
import re
from datetime import datetime, timedelta
from urllib.parse import quote

from comun import _nav, _page, AHORA_JS, DIAS, HORARIO_CSS, icon, MESES, REPORT_CSS


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
