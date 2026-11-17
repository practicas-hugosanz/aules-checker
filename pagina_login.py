"""Pantallas de entrada: iniciar sesión (Aules con usuario y contraseña, o UACloud), la espera mientras
se inicia sesión con UACloud y la de «preparando» mientras se hace la primera revisión."""
import html
import json

from comun import _page, icon, LOGIN_CSS, PORTALES, PORTALES_SSO


def render_login(error="", username="", can_cancel=False, portal="fp"):
    alert = f'<div class="alert" role="alert">{icon("alert-circle")}<span>{html.escape(error)}</span></div>' if error else ""
    cancel = f'<a class="btn-link" href="/">{icon("arrow-left", 14)}Volver a mi cuenta actual</a>' if can_cancel else ""
    marca_sso = ' data-sso="1"'
    opciones_portal = "".join(
        f'<option value="{clave}"{" selected" if clave == portal else ""}{marca_sso if clave in PORTALES_SSO else ""}>{html.escape(nombre)}</option>'
        for clave, (nombre, _) in PORTALES.items()
    )
    body = f"""<div class="auth">
  <div class="auth-card">
    <div class="brand"><span class="brand-mark">{icon("book-open", 20)}</span>Aules · Resumen</div>
    <h1>{'Cambiar de cuenta' if can_cancel else 'Inicia sesión'}</h1>
    <p class="auth-sub" id="login-sub">Entra con tu usuario y contraseña de Aules.</p>
    {alert}
    <form method="post" action="/login" id="login-form">
      <label class="field"><span>Etapa</span>
        <div class="input select">{icon("graduation-cap")}<select name="portal" id="portal">{opciones_portal}</select></div>
      </label>
      <div id="campos-usuario">
        <label class="field"><span>Usuario</span>
          <div class="input">{icon("user")}<input name="username" autocomplete="username" required autofocus value="{html.escape(username)}"></div>
        </label>
        <label class="field"><span>Contraseña</span>
          <div class="input">{icon("lock")}<input name="password" type="password" autocomplete="current-password" required>
            <button type="button" class="toggle" aria-label="Mostrar contraseña">{icon("eye")}</button></div>
        </label>
        <label class="recordar"><input type="checkbox" name="recordar" value="1" checked>
          <span>Volver a entrar solo si Aules cierra la sesión</span></label>
        <button class="btn-primary" type="submit" id="btn-entrar">Entrar</button>
      </div>
      <div class="sso-bloque" id="sso-bloque" hidden>
        <p class="sso-texto"><strong>Opción en pruebas.</strong> Esta universidad usa <strong>UACloud</strong> para iniciar sesión. Se abrirá su página en el navegador
          para que te identifiques allí: la app nunca ve tu contraseña, solo recibe un token de sesión.</p>
        <button class="btn-primary" type="submit" formaction="/login/sso" formnovalidate id="btn-sso">Entrar con UACloud</button>
        <p class="sso-nota">La primera vez, Windows recordará el enlace «moodlemobile://» (el que usa Moodle para volver a una app;
          solo para tu usuario, sin administrador) para que el navegador pueda devolver el acceso a esta app. Se quita al desinstalarla.</p>
      </div>
    </form>
    {cancel}
    <p class="auth-note" id="nota-contrasena">{icon("shield-check", 14)}<span>Con la casilla marcada, la contraseña se guarda cifrada con tu usuario de Windows (solo tú, en este equipo, puedes descifrarla) y se borra al cerrar sesión. Sin marcarla, solo se guarda un token de sesión.</span></p>
  </div>
</div>"""
    js = """
(function () {
  var f = document.getElementById('login-form');
  var t = f.querySelector('.toggle'), p = f.querySelector('input[name=password]');
  var sel = document.getElementById('portal'), campos = document.getElementById('campos-usuario');
  var sso = document.getElementById('sso-bloque'), sub = document.getElementById('login-sub');
  var nota = document.getElementById('nota-contrasena');
  var EYE = __EYE__, EYE_OFF = __EYE_OFF__, LOADER = __LOADER__;
  // Las etapas con UACloud no piden usuario ni contraseña: se entra por el navegador de la universidad.
  function cambiarEtapa() {
    var esSso = sel.options[sel.selectedIndex].dataset.sso === '1';
    campos.hidden = esSso;
    sso.hidden = !esSso;
    nota.hidden = esSso;
    f.elements.username.required = f.elements.password.required = !esSso;
    sub.textContent = esSso ? 'Esta etapa entra con tu cuenta de UACloud.' : 'Entra con tu usuario y contraseña de Aules.';
  }
  sel.addEventListener('change', cambiarEtapa);
  cambiarEtapa();
  t.addEventListener('click', function () {
    var show = p.type === 'password';
    p.type = show ? 'text' : 'password';
    t.innerHTML = show ? EYE_OFF : EYE;
    t.setAttribute('aria-label', show ? 'Ocultar contraseña' : 'Mostrar contraseña');
  });
  f.addEventListener('submit', function (e) {
    var b = e.submitter || f.querySelector('.btn-primary');
    setTimeout(function () { b.disabled = true; b.innerHTML = LOADER + (b.id === 'btn-sso' ? 'Preparando…' : 'Entrando…'); }, 0);
  });
})();
"""
    js = (
        js.replace("__EYE__", json.dumps(icon("eye")))
        .replace("__EYE_OFF__", json.dumps(icon("eye-off")))
        .replace("__LOADER__", json.dumps(icon("loader", 18, "spin")))
    )
    return _page("Aules · Iniciar sesión", body, LOGIN_CSS, js)


def render_sso_espera(nombre, ident, enlace, error="", enlace_alt=""):
    """Mientras te identificas en UACloud: el botón que abre su página y la espera a que Windows devuelva el acceso."""
    alerta = f'<div class="alert" role="alert">{icon("alert-circle")}<span>{html.escape(error)}</span></div>' if error else ""
    alternativa = (
        f'<p>O abre <a href="{html.escape(enlace_alt)}" target="_blank" rel="noopener">este otro enlace</a>: al terminar, la universidad te '
        'enseñará una página con un enlace para abrir la app. Haz clic derecho sobre él, elige «Copiar dirección del enlace» y pégala aquí.</p>'
        if enlace_alt else ""
    )
    body = f"""<div class="auth">
  <div class="auth-card">
    <div class="brand"><span class="brand-mark">{icon("book-open", 20)}</span>Aules · Resumen</div>
    <h1>Entra con UACloud</h1>
    <p class="auth-sub">{html.escape(nombre)}</p>
    {alerta}
    <ol class="sso-pasos">
      <li>Pulsa el botón: se abre la página de la universidad en otra pestaña.</li>
      <li>Identifícate allí con tu cuenta de UACloud.</li>
      <li>El navegador te preguntará si quiere abrir una aplicación (puede llamarse «Python» o «pythonw»): di que sí.</li>
    </ol>
    <a class="btn-primary sso-abrir" href="{html.escape(enlace)}" target="_blank" rel="noopener">{icon("external-link", 16)}Abrir UACloud</a>
    <p class="sso-estado" id="sso-estado" role="status">{icon("loader", 18, "spin")}<span>Esperando a que termines de iniciar sesión…</span></p>
    <details class="sso-pegar"{" open" if error else ""}>
      <summary>¿El navegador no vuelve a la app?</summary>
      <p>Copia el enlace al que te lleva al terminar (empieza por <code>moodlemobile://token=</code>) y pégalo aquí.</p>
      {alternativa}
      <form method="post" action="/login/sso/pegar">
        <input type="hidden" name="id" value="{html.escape(ident)}">
        <textarea name="enlace" placeholder="moodlemobile://token=…" required spellcheck="false"></textarea>
        <button class="btn-primary" type="submit">Continuar</button>
      </form>
    </details>
    <a class="btn-link" href="/login">{icon("arrow-left", 14)}Cancelar</a>
  </div>
</div>"""
    js = """
(function () {
  var id = __ID__, caja = document.getElementById('sso-estado'), texto = caja.querySelector('span'), t0 = Date.now();
  async function mirar() {
    try {
      var r = await fetch('/login/sso/estado?id=' + encodeURIComponent(id), { cache: 'no-store' });
      var d = await r.json();
      if (d.estado === 'ok') { texto.textContent = 'Listo. Entrando…'; location.href = '/'; return; }
      if (d.estado === 'error') { caja.classList.add('error'); texto.textContent = d.mensaje || 'No se pudo iniciar sesión.'; return; }
    } catch (e) {}
    if (Date.now() - t0 > 15 * 60 * 1000) { caja.classList.add('error'); texto.textContent = 'Se acabó el tiempo. Vuelve a empezar desde «Cancelar».'; return; }
    setTimeout(mirar, 1500);
  }
  mirar();
})();
""".replace("__ID__", json.dumps(ident))
    return _page("Aules · UACloud", body, LOGIN_CSS, js)


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
