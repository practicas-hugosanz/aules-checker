import html
import json
import re
import unicodedata
from datetime import datetime
from urllib.parse import quote

from comun import (
    _nav, _page, AHORA_JS, course_hue, DIAS, file_ext, icon, initials, LOGIN_CSS, MESES, nombre_portal, portal_de,
    PORTALES, PORTALES_SSO, pretty_name, REPORT_CSS,
)
from pagina_ajustes import render_ajustes
from pagina_horario import render_horario
from pagina_login import render_login, render_preparando, render_sso_espera
from pagina_materiales import render_materiales
from pagina_profesores import render_profesores
from pagina_revision import render_revision
from temas import con_tema, MODOS, TEMAS


# Lo que el resto de la app usa de aquí. Algunas cosas ya viven en otros archivos y se ofrecen también desde
# aquí: el resto del código y la prueba de arranque de las versiones antiguas de la app las buscan en este módulo.
__all__ = [
    "_entrega_html",
    "_estado_nota",
    "_progreso_html",
    "asignatura_a_curso",
    "build_report",
    "con_tema",
    "format_due",
    "MODOS",
    "nombre_portal",
    "portal_de",
    "PORTALES",
    "PORTALES_SSO",
    "render_ajustes",
    "render_error",
    "render_horario",
    "render_login",
    "render_materiales",
    "render_preparando",
    "render_profesores",
    "render_revision",
    "render_sso_espera",
    "TEMAS",
]


KIND_LABELS = {"examen": "Examen", "tarea": "Tarea", "aviso": "Aviso"}
KIND_ICONS = {"examen": "graduation-cap", "tarea": "clipboard-list", "aviso": "megaphone"}
DUE_PREFIXES = {"Abre": "abre ", "Cierra": "cierra "}
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def fecha_corta(ts):
    d = datetime.fromtimestamp(ts)
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"


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


def linkify(escaped_text):
    def repl(m):
        url, trail = m.group(0), ""
        while url and url[-1] in ".,;:)":
            url, trail = url[:-1], url[-1] + trail
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>{trail}'

    return URL_RE.sub(repl, escaped_text)

REPORT_JS = """
(function () {
  // Enunciados en PDF: se cargan al abrir el desplegable por primera vez.
  document.querySelectorAll('details.desc-pdf').forEach(function (d) {
    d.addEventListener('toggle', function () {
      var marco = d.querySelector('.pdf-marco');
      if (d.open && marco && !marco.getAttribute('src')) marco.setAttribute('src', d.dataset.src);
    });
  });
})();
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

  // La app revisa Aules cada media hora: si ha cambiado algo, la página se recarga sola.
  var informe = document.getElementById('informe');
  var firma = informe && informe.dataset.firma;
  function ocupado() {
    var activo = document.activeElement;
    if (activo && (activo.tagName === 'INPUT' || activo.tagName === 'TEXTAREA') && activo.value) return true;
    if (document.querySelector('.ia-cargando') || document.querySelector('dialog[open]')) return true;
    // Leyendo un enunciado en PDF: recargar la página lo cerraría y perderías por dónde ibas.
    if (document.querySelector('details.desc-pdf[open]')) return true;
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
    var mantenimiento = d.error_tipo === 'mantenimiento', interno = d.error_tipo === 'interno';
    var titulo = mantenimiento ? 'Aules está en mantenimiento'
      : interno ? 'La app no ha podido revisar Aules' : 'No se puede conectar con Aules';
    if (franja) {
      franja.hidden = !d.error;
      franja.lastElementChild.textContent = titulo + '. Se muestra lo último guardado.';
    }
    if (d.error) {
      guardado('aules-caido', '1');
      if (guardado('aules-popup-cerrado') === String(d.error_desde) || (!popup.hidden && !popup.classList.contains('ok'))) return;
      popup.dataset.desde = String(d.error_desde);
      abrirPopup(false, titulo, (mantenimiento ? 'Aules no está disponible ahora mismo. '
        : interno ? 'No es culpa de Aules ni de tu conexión: algo ha fallado en la app. '
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


def _desc_html(summary, label):
    if not summary:
        return ""
    return (
        f'<details class="desc"><summary>{icon("chevron-right", 14, "chev")}{label}</summary>'
        f'<div class="desc-body">{linkify(html.escape(summary))}</div></details>'
    )


def _pdf_enunciado_html(a):
    """Vista previa del PDF donde está el enunciado de la tarea, o "" si el enunciado no viene de un PDF guardado."""
    nombre = a.get("summary_file_name") or ""
    adjunto = next((x for x in a.get("attachments") or [] if x.get("filename") == nombre), None)
    if not adjunto or not nombre.lower().endswith(".pdf") or not adjunto.get("path"):
        return ""
    url = "/" + quote(adjunto["path"].lstrip("/"))
    seguro = html.escape(url)
    return (
        # El PDF solo se carga al abrir el desplegable: la página tiene muchas tareas y no se descargan todos de golpe.
        f'<details class="desc desc-pdf" data-src="{html.escape(url + "#view=FitH&navpanes=0")}">'
        f'<summary>{icon("chevron-right", 14, "chev")}Ver enunciado (PDF)</summary>'
        '<div class="pdf-caja"><div class="pdf-barra">'
        f'<span class="pdf-nombre" title="{html.escape(nombre)}">{html.escape(nombre)}</span>'
        f'<a class="pdf-btn" href="{seguro}" target="_blank" rel="noopener">{icon("external-link", 13)}Abrir en otra pestaña</a>'
        f'<a class="pdf-btn" href="{seguro}" download="{html.escape(nombre)}">{icon("folder", 13)}Descargar</a>'
        "</div>"
        f'<iframe class="pdf-marco" title="Enunciado: {html.escape(nombre)}"></iframe></div></details>'
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
.boton-pri { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: var(--on-accent); border: 0; font-weight: 600; }
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


def _enlace_revision(n):
    if not (n.get("activity") or "").startswith("quiz_"):
        return ""
    return (f'<div class="nota-rev"><a class="nota-revision" href="/revision?id={html.escape(quote(n["activity"]))}">'
            f'{icon("book-open", 13)}Ver preguntas y respuestas</a></div>')


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
        f'{comentario}{_enlace_revision(n)}</div>{_nota_valor(n)}</div>'
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
        # La entrega todavía no está abierta: Aules deja ver la tarea pero aún no se puede entregar.
        desde = (a.get("entrega") or {}).get("desde") or 0
        if desde > now_ts and not a["done"]:
            pills += f'<span class="pill pill-abre">{icon("clock", 12)}Entrega desde el {fecha_corta(desde)}</span>'

        if a["summary"]:
            desc = _desc_html(a["summary"], "Ver descripción")
        elif a.get("summary_file"):
            # El profe dejó el enunciado dentro del adjunto: si es un PDF se ve el PDF; si es un Word o PowerPoint
            # (que el navegador no enseña), su texto.
            desc = _pdf_enunciado_html(a) or _desc_html(a["summary_file"], f'Ver enunciado (de {html.escape(a["summary_file_name"])})')
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
            revision = (f'<a class="menu-item" href="/revision?id={html.escape(quote(a["id"]))}">{icon("book-open", 15)}'
                        '<span>Ver preguntas y respuestas</span></a>') if a["id"].startswith("quiz_") and a["done"] else ""
            menu = _menu_mas(revision, _entrega_html(a, now_ts), _ia_menu(a, ia_cache, candidatas), _marcas_html(a))
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
      <p class="eyebrow" id="fecha-hoy">Aules · {html.escape(nombre_portal(portal_de(session.get("base_url"))))}</p>
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

  <footer>{icon("clock", 13)}Se actualiza sola cada media hora mientras la app está abierta</footer>
</div>"""

    return _page("Aules · Resumen", body, REPORT_CSS + PROPIAS_CSS + ENTREGA_CSS,
                 REPORT_JS + AHORA_JS + REPORT_JS_FIN + PROPIAS_JS + ENTREGA_JS)


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
