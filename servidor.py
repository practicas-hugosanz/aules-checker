import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests

import actualizador
import aules_checker as core
import ia
import interfaz

HOST = "127.0.0.1"
PORT = 8765
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS}
MAX_BODY = 100_000
CHECK_EVERY_SECONDS = 90

check_lock = threading.Lock()
ia_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "AulesResumen"

    # Con pythonw no hay stderr; el log por defecto de http.server fallaría.
    def log_message(self, format, *args):
        pass

    # Sin esto, una excepción cierra la conexión sin dejar rastro ni respuesta.
    def handle_error(self, request, client_address):
        core.log("ERROR en el servidor: " + traceback.format_exc().strip().replace("\n", " | "))

    def _send(self, status, body, content_type="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        # SAMEORIGIN, no DENY: la vista de materiales muestra los PDF en un marco de la propia app.
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        # "no-referrer" haría que el navegador envíe Origin: null y se bloquearían nuestros propios formularios.
        self.send_header("Referrer-Policy", "same-origin")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _host_ok(self):
        # Evita DNS rebinding: solo se aceptan peticiones dirigidas a localhost.
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _body(self):
        length = min(int(self.headers.get("Content-Length") or 0), MAX_BODY)
        return self.rfile.read(length).decode("utf-8", errors="replace") if length else ""

    def _check_or_respond(self, session):
        try:
            with check_lock:
                core.comprobar(session)
            return True
        except core.SessionExpired:
            self._redirect("/login")
        except Exception as e:
            core.log(f"ERROR: {e}")
            self._send(502, interfaz.render_error("No se pudo conectar con Aules. Comprueba tu conexión e inténtalo de nuevo."))
        return False

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "Forbidden", "text/plain")
        path = urlparse(self.path).path
        if path == "/health":
            return self._send(200, "ok", "text/plain")

        session = core.load_session()
        if path == "/login":
            return self._send(200, interfaz.render_login(can_cancel=session is not None))
        if not session:
            return self._redirect("/login")
        if path == "/ajustes":
            return self._send(200, interfaz.render_ajustes(ia.cargar_ajustes(), ia.PROVEEDORES))
        if path == "/horario":
            seleccionado = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            return self._send(200, interfaz.render_horario(
                core.horarios_todos(session), seleccionado, core.dias_sin_clase(core.account_dir(session["username"]))))
        if path == "/profesores":
            return self._send(200, interfaz.render_profesores(core.load_teachers(session)))
        if path == "/materiales":
            return self._send(200, interfaz.render_materiales(session, core.load_materials(session)))
        if path == "/api/informe":
            return self._json(200, core.load_report_status(session))
        if path == "/api/actualizacion":
            return self._json(200, actualizador.estado())
        if path in ("/", "/informe"):
            report = core.report_path(session)
            if not os.path.exists(report) and not self._check_or_respond(session):
                return
            with open(report, "r", encoding="utf-8") as f:
                return self._send(200, f.read())
        if path.startswith("/adjuntos/"):
            return self._serve_attachment(session, path)
        if path.startswith("/material/"):
            return self._serve_material(session, path)
        self._send(404, "No encontrado", "text/plain; charset=utf-8")

    def _serve_attachment(self, session, path):
        base = os.path.realpath(os.path.join(core.account_dir(session["username"]), "adjuntos"))
        target = os.path.realpath(os.path.join(base, unquote(path[len("/adjuntos/"):])))
        try:
            inside = os.path.commonpath([base, target]) == base
        except ValueError:
            inside = False
        if not inside or not os.path.isfile(target):
            return self._send(404, "No encontrado", "text/plain; charset=utf-8")
        with open(target, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        self._send(200, data, ctype, self._cabeceras_archivo(os.path.basename(target), ctype))

    def _cabeceras_archivo(self, nombre, ctype):
        cabeceras = {
            "Content-Disposition": "inline; filename*=UTF-8''" + quote(nombre),
            "X-Content-Type-Options": "nosniff",
        }
        # Solo se aísla lo que puede ejecutar scripts: un PDF aislado no se ve en el visor del navegador.
        if ctype in ("text/html", "application/xhtml+xml", "image/svg+xml"):
            cabeceras["Content-Security-Policy"] = "sandbox"
        return cabeceras

    def _serve_material(self, session, path):
        identificador = unquote(path[len("/material/"):])
        material = next((m for m in core.load_materials(session) if m["id"] == identificador), None)
        if not material:
            return self._send(404, "No encontrado", "text/plain; charset=utf-8")
        if material["externo"]:
            return self._redirect(material["url"])

        destino = os.path.join(
            core.account_dir(session["username"]),
            "material",
            core.sanitize(material["course"]),
            core.sanitize(material["filename"]),
        )
        if not os.path.exists(destino) or os.path.getmtime(destino) < (material.get("timemodified") or 0):
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            url = material["url"]
            sep = "&" if "?" in url else "?"
            try:
                r = core.http.get(f"{url}{sep}token={session['token']}", timeout=120)
                r.raise_for_status()
                core.write_atomic(destino, r.content)
                if material.get("timemodified"):
                    os.utime(destino, (material["timemodified"], material["timemodified"]))
            except Exception as e:
                core.log(f"No se pudo descargar {material['filename']}: {e}")
                return self._send(502, "No se pudo descargar el archivo desde Aules.", "text/plain; charset=utf-8")

        with open(destino, "rb") as f:
            data = f.read()
        ctype = mimetypes.guess_type(destino)[0] or "application/octet-stream"
        self._send(200, data, ctype, self._cabeceras_archivo(material["filename"], ctype))

    def do_POST(self):
        # Bloquea formularios enviados desde otras webs (CSRF contra localhost).
        if not self._host_ok() or self.headers.get("Origin") not in ALLOWED_ORIGINS:
            return self._send(403, "Forbidden", "text/plain")
        path = urlparse(self.path).path

        if path == "/login":
            return self._post_login()
        if path == "/logout":
            actual = core.load_session()
            if actual:
                core.borrar_contrasena(actual["username"])
            core.clear_session()
            core.log("Sesión cerrada")
            return self._redirect("/login")

        session = core.load_session()
        if not session:
            return self._redirect("/login") if not path.startswith("/ia/") else self._json(401, {"error": "Sesión de Aules caducada."})
        if path == "/refresh":
            if self._check_or_respond(session):
                self._redirect("/")
            return
        if path == "/ajustes":
            return self._post_ajustes()
        if path == "/ajustes/modelos":
            return self._post_modelos()
        if path.startswith("/ia/"):
            return self._post_ia(session, path)
        if path.startswith("/api/"):
            return self._post_api(session, path)
        self._send(404, "No encontrado", "text/plain; charset=utf-8")

    def _post_login(self):
        form = parse_qs(self._body())
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        can_cancel = core.load_session() is not None
        try:
            session = core.login(username, password)
        except core.LoginError as e:
            return self._send(401, interfaz.render_login(str(e), username, can_cancel))
        except requests.RequestException:
            return self._send(502, interfaz.render_login("No se pudo conectar con Aules. Inténtalo de nuevo.", username, can_cancel))
        try:
            if form.get("recordar", [""])[0] == "1":
                core.guardar_contrasena(session["username"], password)
            else:
                core.borrar_contrasena(session["username"])
        except OSError as e:
            core.log(f"No se pudo guardar la contraseña cifrada: {e}")
        if self._check_or_respond(session):
            self._redirect("/")

    def _post_ajustes(self):
        form = parse_qs(self._body(), keep_blank_values=True)
        ajustes = ia.cargar_ajustes()
        proveedor = form.get("proveedor", [ajustes["proveedor"]])[0]
        if proveedor not in ia.PROVEEDORES:
            proveedor = ajustes["proveedor"]
        ajustes["proveedor"] = proveedor
        ajustes["modelo"] = form.get("modelo", [""])[0].strip()
        ajustes["base_url"] = form.get("base_url", [""])[0].strip()
        nueva_clave = form.get("api_key", [""])[0].strip()
        # Si el campo se deja vacío, se conserva la clave ya guardada.
        if nueva_clave:
            ajustes["api_key"] = nueva_clave
        if form.get("borrar_clave"):
            ajustes["api_key"] = ""
        ia.guardar_ajustes(ajustes)

        error = correcto = ""
        if form.get("accion", [""])[0] == "probar":
            try:
                respuesta = ia.probar()
                correcto = f"Conexión correcta. El modelo respondió: {respuesta[:80]}"
            except ia.IAError as e:
                error = str(e)
            except Exception as e:
                core.log(f"ERROR IA: {e}")
                error = f"No se pudo conectar con el proveedor: {e}"
        elif not ajustes["modelo"]:
            correcto = "Ajustes guardados. Falta elegir el modelo: pulsa «Ver los modelos de mi clave»."
        else:
            correcto = "Ajustes guardados."
        self._send(200, interfaz.render_ajustes(ia.cargar_ajustes(), ia.PROVEEDORES, error, correcto))

    def _post_api(self, session, path):
        try:
            datos = json.loads(self._body() or "{}")
        except ValueError:
            return self._json(400, {"error": "Petición mal formada."})
        try:
            if path in ("/api/propia", "/api/propia/hecha", "/api/propia/borrar", "/api/marcar"):
                try:
                    if path == "/api/marcar":
                        resultado = core.marcar_tarea(session, str(datos.get("id") or ""), datos.get("marca") or "")
                    elif path == "/api/propia":
                        resultado = core.guardar_propia(session, datos)
                    elif path == "/api/propia/hecha":
                        resultado = core.marcar_propia(session, datos.get("id") or "", datos.get("done"))
                    else:
                        core.borrar_propia(session, datos.get("id") or "")
                        resultado = {"ok": True}
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
                # La pantalla principal se rehace al momento con lo guardado, sin esperar a Aules.
                with check_lock:
                    core.escribir_informe(core.load_session() or session)
                return self._json(200, resultado)
            if path == "/api/actualizar":
                try:
                    # Mientras se revisa Aules o trabaja la IA no se cambia el código por debajo.
                    with check_lock, ia_lock:
                        return self._json(200, actualizador.instalar(core.log))
                except (actualizador.ActualizacionError, requests.RequestException) as e:
                    core.log(f"No se pudo actualizar: {e}")
                    mensaje = str(e) if isinstance(e, actualizador.ActualizacionError) else "No se pudo descargar de GitHub. Comprueba la conexión."
                    return self._json(400, {"error": mensaje})
            if path == "/api/horario/releer":
                return self._json(200, core.releer_horario(session, datos.get("id") or ""))
            if path == "/api/horario/guardar":
                return self._json(200, core.guardar_horario(session, datos.get("id") or "", datos.get("horario") or {}))
        except ia.IAError as e:
            return self._json(400, {"error": str(e)})
        except core.SessionExpired:
            if core.sesion_caducada(session):
                return self._json(409, {"error": "Se ha renovado la sesión de Aules. Vuelve a intentarlo."})
            return self._json(401, {"error": "La sesión de Aules ha caducado."})
        except Exception as e:
            core.log(f"ERROR API {path}: {e}")
            return self._json(500, {"error": str(e)})
        return self._json(404, {"error": "Acción desconocida."})

    def _post_modelos(self):
        try:
            datos = json.loads(self._body() or "{}")
        except ValueError:
            return self._json(400, {"error": "Petición mal formada."})
        # Se prueban los datos escritos en el formulario sin guardarlos todavía.
        ajustes = ia.cargar_ajustes()
        if datos.get("proveedor") in ia.PROVEEDORES:
            ajustes["proveedor"] = datos["proveedor"]
        for campo in ("api_key", "base_url"):
            if (datos.get(campo) or "").strip():
                ajustes[campo] = datos[campo].strip()
        try:
            modelos = ia.listar_modelos(ajustes)
            ia.recordar_topes(modelos)
            return self._json(200, {"modelos": [dict(m, gratis=ia.es_gratis(m["id"])) for m in modelos]})
        except ia.IAError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            core.log(f"ERROR IA (modelos): {e}")
            return self._json(500, {"error": f"No se pudieron obtener los modelos: {e}"})

    def _post_ia(self, session, path):
        accion = path[len("/ia/"):]
        if accion == "carpeta":
            try:
                with ia_lock:
                    return self._json(200, {"carpeta": ia.elegir_carpeta()})
            except Exception as e:
                core.log(f"ERROR IA (selector de carpeta): {e}")
                return self._json(500, {"error": f"No se pudo abrir el selector de carpeta: {e}"})

        try:
            datos = json.loads(self._body() or "{}")
        except ValueError:
            return self._json(400, {"error": "Petición mal formada."})

        acc_dir = core.account_dir(session["username"])
        item = next((i for i in core.load_items(session) if i["id"] == datos.get("id")), None)
        if not item:
            return self._json(404, {"error": "No encuentro esa tarea. Pulsa Actualizar y vuelve a intentarlo."})

        try:
            with ia_lock:
                if accion == "resumen":
                    resultado = {"resumen": ia.resumir(item, acc_dir)}
                elif accion == "borrador":
                    carpeta = (datos.get("carpeta") or "").strip()
                    if not carpeta or not os.path.isdir(carpeta):
                        return self._json(400, {"error": "Elige una carpeta válida."})
                    materiales = []
                    if item.get("course_id"):
                        try:
                            materiales = core.fetch_course_material(session, item["course_id"], item["course"])
                        except Exception as e:
                            core.log(f"No se pudo descargar el temario: {e}")
                    # Tarea en cadena: la anterior y tu respuesta a ella (entregada en Aules o tu borrador).
                    previa = None
                    anterior = str(datos.get("anterior") or "")
                    if anterior and anterior != item["id"]:
                        previo = next((i for i in core.load_items(session) if i["id"] == anterior), None)
                        if previo:
                            previa = core.respuesta_previa(session, previo, ia.cargar_cache(acc_dir))
                    resultado = ia.borrador(item, acc_dir, carpeta, materiales, previa)
                else:
                    return self._json(404, {"error": "Acción desconocida."})

                cache = ia.cargar_cache(acc_dir)
                entrada = cache.setdefault(item["id"], {})
                entrada["resumen" if accion == "resumen" else "borrador"] = resultado.get("resumen") if accion == "resumen" else resultado
                if accion == "borrador":
                    # Se recuerda de qué tarea continúa, para dejarla elegida la próxima vez.
                    entrada["anterior"] = str(datos.get("anterior") or "")
                ia.guardar_cache(acc_dir, cache)
        except ia.IAError as e:
            return self._json(400, {"error": str(e)})
        except core.SessionExpired:
            if core.sesion_caducada(session):
                return self._json(409, {"error": "Se ha renovado la sesión de Aules. Vuelve a intentarlo."})
            return self._json(401, {"error": "La sesión de Aules ha caducado. Vuelve a iniciar sesión."})
        except Exception as e:
            core.log(f"ERROR IA: {e}")
            return self._json(500, {"error": f"Falló la IA: {e}"})

        core.log(f"IA {accion} · {item['name']}")
        self._json(200, resultado)


def _firma_codigo():
    return tuple(
        os.path.getmtime(os.path.join(core.BASE_DIR, f))
        for f in actualizador.ARCHIVOS
        if f.endswith(".py")
        if os.path.exists(os.path.join(core.BASE_DIR, f))
    )


def vigilar_codigo():
    """Reinicia la app cuando cambia su propio código, para no tener que cerrarla a mano."""
    inicial = _firma_codigo()
    while True:
        time.sleep(3)
        if _firma_codigo() == inicial:
            continue
        if check_lock.locked() or ia_lock.locked():
            continue
        core.log("Código actualizado: reiniciando la app")
        time.sleep(1)
        os.execv(sys.executable, [sys.executable, os.path.join(core.BASE_DIR, "servidor.py")])


def comprobar_periodicamente():
    """Revisa Aules cada minuto y medio mientras la app está abierta."""
    ultimo_error = None
    time.sleep(10)
    while True:
        session = core.load_session()
        if session and check_lock.acquire(blocking=False):
            try:
                core.comprobar(session)
                if ultimo_error:
                    core.log("Conexión con Aules recuperada")
                ultimo_error = None
            except core.SessionExpired:
                pass  # sesion_caducada ya avisó y cerró la sesión
            except Exception as e:
                # Sin conexión se repetiría el mismo error cada 90 s: solo se anota cuando cambia.
                if str(e) != ultimo_error:
                    core.log(f"ERROR en la comprobación automática: {e}")
                ultimo_error = str(e)
            finally:
                check_lock.release()
        time.sleep(CHECK_EVERY_SECONDS)


def already_running():
    try:
        return requests.get(f"http://{HOST}:{PORT}/health", timeout=1).text == "ok"
    except requests.RequestException:
        return False


def main():
    url = f"http://{HOST}:{PORT}/"
    if already_running():
        if "--sin-navegador" not in sys.argv:
            webbrowser.open(url)
        return
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Thread(target=vigilar_codigo, daemon=True).start()
    threading.Thread(target=comprobar_periodicamente, daemon=True).start()
    threading.Thread(target=actualizador.vigilar, args=(core.log,), daemon=True).start()
    if "--sin-navegador" not in sys.argv:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
