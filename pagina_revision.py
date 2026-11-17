"""Página para repasar un cuestionario ya hecho: sus preguntas, lo que respondiste y la respuesta correcta."""
import html
from datetime import datetime
from urllib.parse import quote

from comun import _nav, _page, icon, MESES, REPORT_CSS


REVISION_CSS = """
.rev-resumen { display: flex; flex-wrap: wrap; gap: 14px 22px; align-items: center; background: var(--card); border: 1px solid var(--border);
  border-radius: 18px; box-shadow: var(--shadow); padding: 16px 20px; margin-bottom: 14px; }
.rev-nota { font-family: var(--display); font-size: 34px; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
.rev-nota small { font-size: 15px; font-weight: 600; color: var(--muted); margin-left: 3px; }
.rev-cuentas { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 14px; color: var(--muted); flex: 1; }
.rev-cuentas b { color: var(--text); }
.rev-cuentas .bien b { color: var(--green); } .rev-cuentas .mal b { color: var(--red); } .rev-cuentas .parcial b { color: var(--amber); }
.rev-aules { display: inline-flex; align-items: center; min-height: 24px; gap: 6px; color: var(--accent-ink); font-size: 13.5px; font-weight: 600; text-decoration: none; }
.rev-aules:hover { text-decoration: underline; }
.rev-barra { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 14px; }
.rev-filtro, .rev-intento { border: 1px solid var(--border); background: var(--card); color: var(--muted); border-radius: 999px; padding: 6px 13px;
  font: inherit; font-size: 13.5px; cursor: pointer; text-decoration: none; }
.rev-filtro[aria-pressed="true"], .rev-intento.activo { border-color: var(--text); color: var(--text); font-weight: 650; }
.rev-filtro:focus-visible, .rev-intento:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.rev-aviso { display: flex; gap: 10px; align-items: flex-start; background: var(--card-2); border-radius: 12px; padding: 10px 14px;
  font-size: 13.5px; color: var(--muted); margin-bottom: 14px; }
.rev-aviso .i { flex: none; margin-top: 2px; }
.pregs { display: grid; gap: 12px; }
.preg { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 16px 18px; box-shadow: inset 4px 0 0 var(--border); }
.preg.bien { box-shadow: inset 4px 0 0 var(--green); } .preg.mal { box-shadow: inset 4px 0 0 var(--red); }
.preg.parcial { box-shadow: inset 4px 0 0 var(--amber); }
.preg[hidden] { display: none; }
.preg-cab { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.preg-num { font-weight: 700; font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.preg-nota { margin-left: auto; font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }
.pill-parcial { background: var(--amber-soft); color: var(--amber); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.pill-sin { background: var(--gray-soft, var(--card-2)); color: var(--muted); text-transform: none; letter-spacing: 0; font-size: 11.5px; }
.preg-texto { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 15px; font-weight: 600; line-height: 1.5; }
/* Enunciados largos (ejercicios con datos): en negrita entera no se leen bien. */
.preg-texto.largo { font-weight: 400; font-size: 14.5px; line-height: 1.6; }
.preg-imgs img, .dd img { max-width: 100%; height: auto; border-radius: 10px; border: 1px solid var(--border); margin-top: 10px; display: block; }
.ops { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 6px; }
.op { display: flex; gap: 10px; align-items: flex-start; padding: 8px 12px; border-radius: 10px; border: 1px solid var(--border); font-size: 14px; }
.op-letra { flex: none; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-size: 12px; font-weight: 700;
  background: var(--card-2); color: var(--muted); }
.op-texto { flex: 1; min-width: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.op-etq { flex: none; display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 650; }
.op.correcta { border-color: color-mix(in srgb, var(--green) 55%, transparent); background: var(--green-soft); }
.op.correcta .op-letra { background: var(--green); color: var(--card); }
.op.correcta .op-etq { color: var(--green); }
.op.mala { border-color: color-mix(in srgb, var(--red) 55%, transparent); background: var(--red-soft); }
.op.mala .op-letra { background: var(--red); color: var(--card); }
.op.mala .op-etq { color: var(--red); }
.op.tuya:not(.correcta):not(.mala) { border-color: var(--text); }
.op.tuya:not(.correcta):not(.mala) .op-letra { background: var(--text); color: var(--card); }
.orden { margin: 12px 0 0; padding-left: 22px; display: grid; gap: 6px; font-size: 14px; }
.orden li { padding: 6px 10px; border: 1px solid var(--border); border-radius: 10px; }
.preg-sub { margin: 12px 0 0; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
.dd { position: relative; margin-top: 10px; max-width: 620px; }
.dd img { margin-top: 0; }
.dd-zona { position: absolute; transform: translate(0, 0); max-width: 45%; padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 650;
  background: var(--text); color: var(--card); box-shadow: 0 2px 8px rgba(0,0,0,.25); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dd-zona.vacia { background: var(--card); color: var(--muted); border: 1px dashed var(--muted); }
/* Las etiquetas solo se ven cuando ya están colocadas sobre la imagen (antes se amontonaban en una esquina). */
.dd:not(.lista) .dd-zona { display: none; }
.dd.sin-imagen { display: none; }
.dd-lista { margin: 8px 0 0; padding-left: 20px; font-size: 13.5px; color: var(--muted); }
.preg-tuya, .preg-correcta, .preg-fb { margin-top: 10px; padding: 9px 12px; border-radius: 10px; font-size: 14px; white-space: pre-wrap; overflow-wrap: anywhere; }
.preg-tuya { background: var(--card-2); }
.preg-correcta { background: var(--green-soft); color: var(--green); display: flex; gap: 8px; align-items: flex-start; }
.preg-correcta .i { flex: none; margin-top: 2px; }
.preg-fb { background: var(--card-2); color: var(--muted); display: flex; gap: 8px; align-items: flex-start; }
.preg-fb .i { flex: none; margin-top: 2px; color: var(--accent); }
.volver { color: inherit; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; min-height: 24px; }
.volver:hover { color: var(--accent); }
@media (max-width: 680px) { .preg { padding: 14px; } .rev-nota { font-size: 28px; } }
"""

REVISION_JS = """
(function () {
  // Filtros: todas, falladas (mal o a medias) o correctas.
  var botones = document.querySelectorAll('.rev-filtro');
  botones.forEach(function (b) {
    b.addEventListener('click', function () {
      botones.forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      var f = b.dataset.filtro;
      document.querySelectorAll('.preg').forEach(function (p) {
        var e = p.dataset.estado;
        p.hidden = f === 'falladas' ? (e === 'bien') : f === 'bien' ? (e !== 'bien') : false;
      });
    });
  });
  // Arrastrar a una imagen: cada etiqueta en su sitio, según el tamaño real de la imagen.
  document.querySelectorAll('.dd').forEach(function (caja) {
    var img = caja.querySelector('img');
    function colocar() {
      if (!img.naturalWidth) return;
      caja.querySelectorAll('.dd-zona').forEach(function (z) {
        z.style.left = (+z.dataset.x / img.naturalWidth * 100) + '%';
        z.style.top = (+z.dataset.y / img.naturalHeight * 100) + '%';
      });
      caja.classList.add('lista');
    }
    // Si la imagen no carga, queda la lista de zonas de debajo.
    img.addEventListener('error', function () { caja.classList.add('sin-imagen'); });
    if (img.complete && img.naturalWidth) colocar(); else img.addEventListener('load', colocar);
  });
})();
"""


def _estado_pregunta(p):
    """(clase, texto) para enseñar cómo te salió. Si Aules no lo dice («Finalizado»), se deduce de la nota."""
    estado = p.get("estado")
    if estado == "correct":
        return "bien", "Correcta"
    if estado == "incorrect":
        return "mal", "Incorrecta"
    if estado == "partiallycorrect":
        return "parcial", "Parcialmente correcta"
    if estado == "notanswered":
        return "sin", "Sin responder"
    try:
        nota, maximo = float(p["nota"].replace(",", ".")), float(p["max"].replace(",", "."))
    except (ValueError, AttributeError):
        return "sin", p.get("estado_texto") or "Respondida"
    if nota >= maximo:
        return "bien", "Correcta"
    return ("mal", "Incorrecta") if nota <= 0 else ("parcial", "Parcialmente correcta")


def _imagen_revision(ruta, alt=""):
    return f'<img src="/adjuntos/{html.escape(quote(ruta))}" alt="{html.escape(alt)}" loading="lazy">'


def _pregunta_html(p):
    clase, texto_estado = _estado_pregunta(p)
    pill = {"bien": ("pill-aprobado", "check"), "mal": ("pill-suspendido", "x"), "parcial": ("pill-parcial", "alert-circle"),
            "sin": ("pill-sin", "clock")}[clase]
    nota = f'<span class="preg-nota">{html.escape(p["nota"])}{" / " + html.escape(p["max"]) if p["max"] else ""}</span>' if p["nota"] else ""
    partes = [
        f'<header class="preg-cab"><span class="preg-num">Pregunta {html.escape(p["numero"])}</span>'
        f'<span class="pill {pill[0]}">{icon(pill[1], 11)}{texto_estado}</span>{nota}</header>',
        f'<div class="preg-texto{" largo" if len(p["enunciado"]) > 180 else ""}">{html.escape(p["enunciado"])}</div>'
        if p["enunciado"] else "",
    ]
    if p["imagenes"]:
        partes.append('<div class="preg-imgs">' + "".join(_imagen_revision(r, "Imagen del enunciado") for r in p["imagenes"]) + "</div>")
    if p["opciones"]:
        filas = []
        for op in p["opciones"]:
            mala = op["marcada"] and op["acierto"] in ("incorrect", "partiallycorrect") and not op["es_correcta"]
            correcta = op["es_correcta"]
            clases = " ".join(c for c, si in (("tuya", op["marcada"]), ("correcta", correcta), ("mala", mala)) if si)
            if op["marcada"] and correcta:
                etiqueta = f'{icon("check", 13)}Tu respuesta'
            elif mala:
                etiqueta = f'{icon("x", 13)}Tu respuesta'
            elif op["marcada"]:
                etiqueta = "Tu respuesta"
            elif correcta:
                etiqueta = f'{icon("check", 13)}Correcta'
            else:
                etiqueta = ""
            imagenes = "".join(_imagen_revision(r) for r in op["imagenes"])
            filas.append(
                f'<li class="op {clases}"><span class="op-letra">{html.escape(op["letra"] or "·")}</span>'
                f'<span class="op-texto">{html.escape(op["texto"])}{imagenes}</span>'
                + (f'<span class="op-etq">{etiqueta}</span>' if etiqueta else "") + "</li>"
            )
        partes.append(f'<ul class="ops">{"".join(filas)}</ul>')
    if p["orden"]:
        partes.append('<p class="preg-sub">Tu orden</p><ol class="orden">'
                      + "".join(f'<li>{html.escape(o["texto"])}</li>' for o in p["orden"]) + "</ol>")
        # Aules solo da la nota de las preguntas de ordenar, no qué pasos estaban en su sitio: mejor decirlo.
        if not p["correcta"] and not any(o["acierto"] for o in p["orden"]) and clase != "bien":
            partes.append(f'<div class="preg-fb">{icon("alert-circle", 15)}<span>Era una pregunta de ordenar. El profe no deja ver '
                          f'el orden correcto ni qué pasos estaban bien: solo la nota{" (" + html.escape(p["nota"]) + " de " + html.escape(p["max"]) + ")" if p["nota"] and p["max"] else ""}. '
                          'Si quieres saberlo, pregúntale o repásalo en el tema.</span></div>')
    if p["zonas"]:
        zonas = sorted(p["zonas"], key=lambda z: z["n"])
        if p["fondo"]:
            etiquetas = "".join(
                f'<span class="dd-zona{"" if z["texto"] else " vacia"}" data-x="{z["x"]}" data-y="{z["y"]}" '
                f'title="{html.escape(z["texto"] or "Sin poner")}">{z["n"]}. {html.escape(z["texto"] or "(vacía)")}</span>'
                for z in zonas)
            partes.append(f'<p class="preg-sub">Lo que pusiste</p><div class="dd">{_imagen_revision(p["fondo"], "Imagen de la pregunta")}{etiquetas}</div>')
        partes.append('<ol class="dd-lista">' + "".join(
            f'<li>Zona {html.escape(z["n"])}: <b>{html.escape(z["texto"] or "(vacía)")}</b></li>' for z in zonas) + "</ol>")
    if p["tu_respuesta"]:
        partes.append(f'<div class="preg-tuya"><b>Tu respuesta:</b> {html.escape(p["tu_respuesta"])}</div>')
    # La correcta se repite solo si no se ve ya marcada en las opciones o si fallaste.
    if p["correcta"] and (clase != "bien" or not any(op["es_correcta"] for op in p["opciones"])):
        partes.append(f'<div class="preg-correcta">{icon("check-circle", 15)}<span><b>Respuesta correcta:</b> {html.escape(p["correcta"])}</span></div>')
    if p["comentario"]:
        partes.append(f'<div class="preg-fb">{icon("message-square", 15)}<span>{html.escape(p["comentario"])}</span></div>')
    return f'<article class="preg {clase}" data-estado="{clase}">{"".join(partes)}</article>'


def render_revision(item, datos, nota_max="", intento_id=None, error=""):
    """Las preguntas de un cuestionario terminado: lo que respondiste, si estaba bien y, si se ve, la correcta."""
    nombre = item.get("name") or "Cuestionario"
    intentos = (datos or {}).get("intentos") or []
    intento = next((i for i in intentos if str(i["id"]) == str(intento_id)), intentos[0] if intentos else None)
    avisos, cuerpo, terminado = [], "", ""
    if error:
        avisos.append((icon("alert-circle"), error))
    elif not intento:
        avisos.append((icon("clock"), "Todavía no has terminado este cuestionario. Cuando lo acabes, aquí verás sus preguntas y tus respuestas."))
    else:
        if (datos or {}).get("offline"):
            avisos.append((icon("triangle-alert"), "No se pudo conectar con Aules ahora mismo: esto es lo que la app guardó cuando lo hiciste."))
        elif (datos or {}).get("guardado_local"):
            avisos.append((icon("shield-check"), "Este cuestionario ya no está en Aules, pero la app guardó tus preguntas y respuestas de cuando lo hiciste."))
        if intento["error"]:
            avisos.append((icon("lock"), intento["error"]))
        preguntas = intento["preguntas"]
        cuentas = {"bien": 0, "mal": 0, "parcial": 0, "sin": 0}
        for p in preguntas:
            cuentas[_estado_pregunta(p)[0]] += 1
        if preguntas and not any(p["correcta"] for p in preguntas) and any(p["opciones"] for p in preguntas):
            avisos.append((icon("lock"), "El profe no deja ver las respuestas correctas de este cuestionario: ves lo que marcaste "
                                         "y si estaba bien o mal."))
        fin = datetime.fromtimestamp(intento["fin"]) if intento["fin"] else None
        terminado = f'Terminado el {fin.day} {MESES[fin.month - 1]} a las {fin.strftime("%H:%M")}' if fin else ""
        textos = (("bien", "correcta", "correctas"), ("mal", "fallada", "falladas"), ("parcial", "a medias", "a medias"),
                  ("sin", "sin responder", "sin responder"))
        resumen = "".join(
            f'<span class="{c}"><b>{cuentas[c]}</b> {uno if cuentas[c] == 1 else varios}</span>' for c, uno, varios in textos if cuentas[c] or c == "bien")
        cuerpo += (
            '<div class="rev-resumen">'
            + (f'<div class="rev-nota">{html.escape(intento["nota"])}<small>{"/ " + html.escape(nota_max) if nota_max else "nota"}</small></div>'
               if intento["nota"] else "")
            + f'<div class="rev-cuentas">{resumen}<span>{len(preguntas)} preguntas</span></div>'
            f'<a class="rev-aules" href="{html.escape(intento["url"])}" target="_blank" rel="noopener noreferrer">Abrir en Aules{icon("external-link", 13)}</a>'
            "</div>"
        )
        barra = ""
        if len(intentos) > 1:
            barra += "".join(
                f'<a class="rev-intento{" activo" if i is intento else ""}" href="/revision?id={html.escape(quote(item["id"]))}&amp;intento={i["id"]}"'
                f'{" aria-current=\"page\"" if i is intento else ""}>Intento {i["numero"]}{" · " + html.escape(i["nota"]) if i["nota"] else ""}</a>'
                for i in intentos)
        if cuentas["mal"] + cuentas["parcial"] + cuentas["sin"] and cuentas["bien"]:
            falladas = cuentas["mal"] + cuentas["parcial"] + cuentas["sin"]
            barra += (f'<button type="button" class="rev-filtro" data-filtro="todas" aria-pressed="true">Todas ({len(preguntas)})</button>'
                      f'<button type="button" class="rev-filtro" data-filtro="falladas" aria-pressed="false">Para repasar ({falladas})</button>'
                      f'<button type="button" class="rev-filtro" data-filtro="bien" aria-pressed="false">Correctas ({cuentas["bien"]})</button>')
        if barra:
            cuerpo += f'<div class="rev-barra">{barra}</div>'
        cuerpo += '<div class="pregs">' + "".join(_pregunta_html(p) for p in preguntas) + "</div>"
    avisos_html = "".join(f'<div class="rev-aviso">{ic}<span>{html.escape(t)}</span></div>' for ic, t in avisos)
    sub = " · ".join(x for x in (item.get("course", ""), terminado) if x)
    body = f"""{_nav("inicio")}
<div class="wrap">
  <div class="hero">
    <div>
      <p class="eyebrow"><a href="/" class="volver">{icon("arrow-left", 13)}Volver</a></p>
      <h1>{html.escape(nombre)}</h1>
      <div class="updated">{html.escape(sub)}</div>
    </div>
  </div>
  {avisos_html}
  {cuerpo}
</div>"""
    return _page(f"Aules · {nombre}", body, REPORT_CSS + REVISION_CSS, REVISION_JS)
