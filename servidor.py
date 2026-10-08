import base64
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
# Una entrega lleva los archivos en base64 (un tercio más grandes): hasta unos 60 MB de archivos.
MAX_BODY_ENTREGA = 80_000_000
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
        if isinstance(body, str) and content_type.startswith("text/html"):
            body = interfaz.con_tema(body, ia.cargar_ajustes())
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

    def _body(self, maximo=MAX_BODY):
        length = min(int(self.headers.get("Content-Length") or 0), maximo)
        return self.rfile.read(length).decode("utf-8", errors="replace") if length else ""

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, "Forbidden", "text/plain")
        path = urlparse(self.path).path
        if path == "/health":
            return self._send(200, "ok", "text/plain")

        session = core.load_session()
        if path == "/login":
            portal = interfaz.portal_de(session.get("base_url")) if session else "fp"
            return self._send(200, interfaz.render_login(can_cancel=session is not None, portal=portal))
        if not session:
            return self._redirect("/login")
        if path == "/ajustes":
            return self._send(200, interfaz.render_ajustes(ia.cargar_ajustes(), ia.PROVEEDORES))
        if path == "/horario":
            seleccionado = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            return self._send(200, interfaz.render_horario(
                core.horarios_todos(session), seleccionado, core.dias_sin_clase(core.carpeta(session))))
        if path == "/revision":
            return self._get_revision(session)
        if path == "/profesores":
            return self._send(200, interfaz.render_profesores(core.load_teachers(session)))
        if path == "/materiales":
            return self._send(200, interfaz.render_materiales(session, core.load_materials(session)))
        if path == "/api/informe":
            # «comprobando»: la página enseña que se está revisando Aules y mira más a menudo si ha acabado.
            return self._json(200, dict(core.load_report_status(session), comprobando=check_lock.locked(),
                                        error=revision["error"], error_tipo=revision["tipo"], error_desde=revision["desde"]))
        if path == "/api/entrega":
            return self._get_entrega(session)
        if path == "/api/actualizacion":
            return self._json(200, actualizador.estado())
        if path in ("/", "/informe"):
            report = core.report_path(session)
            if not os.path.exists(report):
                # Primera vez con esta cuenta: se lee todo de Aules por detrás y mientras tanto se enseña
                # «Preparando…», que se recarga sola al acabar. Si falló, se enseña el error con «Reintentar».
                if not check_lock.locked() and not revision["error"]:
                    revisar_en_segundo_plano(session, esperar=True)
                return self._send(200, interfaz.render_preparando("" if check_lock.locked() else revision["error"]))
            with open(report, "r", encoding="utf-8") as f:
                return self._send(200, f.read())
        if path == "/foto":
            foto = core.cargar_foto(session)
            if not foto:
                return self._send(404, "Sin foto", "text/plain; charset=utf-8")
            return self._send(200, foto[0], foto[1])
        if path.startswith("/adjuntos/"):
            return self._serve_attachment(session, path)
        if path.startswith("/material/"):
            return self._serve_material(session, path)
        self._send(404, "No encontrado", "text/plain; charset=utf-8")

    def _get_revision(self, session):
        consulta = parse_qs(urlparse(self.path).query)
        quiz_id = consulta.get("id", [""])[0]
        item = next((i for i in core.load_items(session) if i["id"] == quiz_id), None)
        if not item or not quiz_id.startswith("quiz_") or not quiz_id[5:].isdigit():
            return self._redirect("/")
        nota = next((n for n in core.load_grades(session) if n.get("activity") == quiz_id), None)
        datos, error = None, ""
        try:
            datos = core.revision_cuestionario(session, quiz_id)
        except core.SessionExpired:
            if not core.sesion_caducada(session):
                return self._redirect("/login")
            error = "Se ha renovado la sesión de Aules. Recarga la página."
        except core.AulesEnMantenimiento as e:
            error = str(e)
        except Exception as e:
            core.log(f"No se pudo abrir la revisión de «{item['name']}»: {e}")
            error = "No se pudo conectar con Aules para leer este cuestionario. Inténtalo de nuevo en un momento."
        self._send(200, interfaz.render_revision(item, datos, (nota or {}).get("max", ""), consulta.get("intento", [None])[0], error))

    def _serve_attachment(self, session, path):
        base = os.path.realpath(os.path.join(core.carpeta(session), "adjuntos"))
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
            core.carpeta(session),
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
                core.borrar_contrasena(actual)
            core.clear_session()
            core.log("Sesión cerrada")
            return self._redirect("/login")

        session = core.load_session()
        if not session:
            return self._redirect("/login") if not path.startswith("/ia/") else self._json(401, {"error": "Sesión de Aules caducada."})
        if path == "/refresh":
            # No se espera a Aules: vuelves a la página al momento, el botón gira mientras se revisa y la página
            # se recarga sola con lo nuevo. Si ya se estaba revisando, esa revisión ya trae los datos frescos.
            revisar_en_segundo_plano(session)
            buscar_actualizacion_en_segundo_plano()
            return self._redirect("/")
        if path == "/ajustes":
            return self._post_ajustes()
        if path == "/ajustes/modelos":
            return self._post_modelos()
        if path == "/ajustes/apariencia":
            return self._post_apariencia()
        if path.startswith("/ia/"):
            return self._post_ia(session, path)
        if path == "/api/entregar":
            return self._post_entregar(session)
        if path.startswith("/api/"):
            return self._post_api(session, path)
        self._send(404, "No encontrado", "text/plain; charset=utf-8")

    def _post_login(self):
        form = parse_qs(self._body())
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        portal = form.get("portal", ["fp"])[0]
        portal = portal if portal in interfaz.PORTALES else "fp"
        can_cancel = core.load_session() is not None
        try:
            session = core.login(username, password, interfaz.PORTALES[portal][1])
        except core.LoginError as e:
            return self._send(401, interfaz.render_login(str(e), username, can_cancel, portal))
        except requests.RequestException:
            return self._send(502, interfaz.render_login("No se pudo conectar con Aules. Inténtalo de nuevo.", username, can_cancel, portal))
        try:
            if form.get("recordar", [""])[0] == "1":
                core.guardar_contrasena(session, password)
            else:
                core.borrar_contrasena(session)
        except OSError as e:
            core.log(f"No se pudo guardar la contraseña cifrada: {e}")
        # Entras al momento: con lo último guardado de esta cuenta o, la primera vez, con «Preparando…».
        # Aules se revisa por detrás (esperando a la revisión automática si estaba en marcha con otra cuenta).
        revisar_en_segundo_plano(session, esperar=True)
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
        self._send(200, interfaz.render_ajustes(ia.cargar_ajustes(), ia.PROVEEDORES, error, correcto, seccion="ia"))

    def _tarea(self, session, item_id):
        return next((i for i in core.load_items(session) if i["id"] == item_id), None)

    def _get_entrega(self, session):
        """Lo que necesita el diálogo de entrega: qué admite la tarea, qué entregaste ya y los archivos del borrador."""
        item = self._tarea(session, parse_qs(urlparse(self.path).query).get("id", [""])[0])
        if not item or not item.get("entrega"):
            return self._json(404, {"error": "Esta tarea no se puede entregar desde la app."})
        try:
            estado = core.estado_entrega(session, item)
        except core.SessionExpired:
            return self._json(401, {"error": "La sesión de Aules ha caducado."})
        except Exception as e:
            core.log(f"No se pudo leer el estado de entrega de «{item['name']}»: {e}")
            return self._json(502, {"error": "No se pudo consultar Aules. Inténtalo de nuevo."})
        borrador = core.archivos_del_borrador(ia.cargar_cache(core.carpeta(session)), item)
        return self._json(200, {
            "tarea": {"id": item["id"], "name": item["name"], "course": item["course"], "duedate": item.get("duedate") or 0},
            "config": item["entrega"], "estado": estado,
            "borrador": [{"nombre": os.path.basename(r), "bytes": os.path.getsize(r)} for r in borrador],
        })

    def _post_entregar(self, session):
        if int(self.headers.get("Content-Length") or 0) > MAX_BODY_ENTREGA:
            return self._json(413, {"error": "Los archivos pesan demasiado para entregarlos desde la app."})
        try:
            datos = json.loads(self._body(MAX_BODY_ENTREGA) or "{}")
            archivos = [(os.path.basename(str(a["nombre"])), base64.b64decode(a["datos"], validate=True))
                        for a in datos.get("archivos") or []]
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"error": "Petición mal formada."})
        item = self._tarea(session, str(datos.get("id") or ""))
        if not item:
            return self._json(404, {"error": "No encuentro esa tarea. Pulsa Actualizar y vuelve a intentarlo."})
        # Del borrador solo se aceptan archivos que la IA escribió para esta tarea, leídos de su carpeta.
        del_borrador = {os.path.basename(r): r for r in core.archivos_del_borrador(
            ia.cargar_cache(core.carpeta(session)), item)}
        for nombre in datos.get("borrador") or []:
            if nombre not in del_borrador:
                return self._json(400, {"error": f"«{nombre}» no es un archivo del borrador de esta tarea."})
            with open(del_borrador[nombre], "rb") as f:
                archivos.append((nombre, f.read()))
        try:
            with check_lock:
                estado = core.entregar(session, item, archivos, str(datos.get("texto") or ""), bool(datos.get("acepta")))
            return self._json(200, {"ok": True, "estado": estado})
        except core.EntregaError as e:
            return self._json(400, {"error": str(e)})
        except core.SessionExpired:
            return self._json(401, {"error": "La sesión de Aules ha caducado. Vuelve a entrar y repite la entrega."})
        except Exception as e:
            core.log(f"ERROR al entregar «{item['name']}»: {e}")
            return self._json(502, {"error": "No se pudo completar la entrega. Comprueba en Aules si llegó a entregarse."})

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
                # Mientras se revisa Aules o trabaja la IA no se cambia el código por debajo, pero sin esperar sin fin.
                if not check_lock.acquire(timeout=60):
                    return self._json(409, {"error": "Se está revisando Aules. Vuelve a pulsar «Actualizar» en un momento."})
                try:
                    if not ia_lock.acquire(timeout=5):
                        return self._json(409, {"error": "La IA está trabajando. Vuelve a pulsar «Actualizar» cuando acabe."})
                    try:
                        return self._json(200, actualizador.instalar(core.log))
                    finally:
                        ia_lock.release()
                except (actualizador.ActualizacionError, requests.RequestException) as e:
                    core.log(f"No se pudo actualizar: {e}")
                    mensaje = str(e) if isinstance(e, actualizador.ActualizacionError) else "No se pudo descargar de GitHub. Comprueba la conexión."
                    return self._json(400, {"error": mensaje})
                finally:
                    check_lock.release()
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

    def _post_apariencia(self):
        try:
            datos = json.loads(self._body() or "{}")
        except ValueError:
            return self._json(400, {"error": "Petición mal formada."})
        if datos.get("estilo") not in interfaz.TEMAS or datos.get("modo") not in interfaz.MODOS:
            return self._json(400, {"error": "Estilo o modo desconocido."})
        ajustes = ia.cargar_ajustes()
        ajustes["estilo"], ajustes["modo"] = datos["estilo"], datos["modo"]
        ia.guardar_ajustes(ajustes)
        return self._json(200, {"ok": True})

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

        acc_dir = core.carpeta(session)
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
        time.sleep(1)
        # Si el código nuevo no arranca, reiniciar dejaría la app cerrada y sin forma de actualizarla desde dentro.
        error = actualizador.probar_codigo(core.BASE_DIR)
        if error and not actualizador.restaurar_anterior(core.log):
            core.log(f"El código nuevo no arranca, la app sigue con el que tenía cargado: {error}")
            inicial = _firma_codigo()
            continue
        core.log("Código actualizado: reiniciando la app")
        os.execv(sys.executable, [sys.executable, os.path.join(core.BASE_DIR, "servidor.py")])


# Si Aules está caído: el aviso, el tipo («mantenimiento» o «conexion») y desde cuándo, para el popup de la página.
# Se mantiene hasta que una revisión vuelva a ir bien (pulsar refrescar no lo borra).
revision = {"error": "", "tipo": "", "desde": 0}


def mensaje_de_error(e):
    if isinstance(e, core.AulesEnMantenimiento):
        return str(e)
    return "No se pudo conectar con Aules. Comprueba tu conexión e inténtalo de nuevo."


def anotar_fallo(e):
    if not revision["error"]:
        revision["desde"] = int(time.time())
    revision["error"] = mensaje_de_error(e)
    revision["tipo"] = "mantenimiento" if isinstance(e, core.AulesEnMantenimiento) else "conexion"


def anotar_exito():
    revision.update(error="", tipo="", desde=0)


def revisar_en_segundo_plano(session, esperar=False):
    """Revisa Aules sin hacer esperar a nadie. Si ya hay una revisión en marcha, no lanza otra
    (salvo con `esperar`: entonces se pone a la cola, para cuando la que está en marcha es de otra cuenta)."""
    # El cerrojo se coge aquí y no en el hilo: así la página que se pide justo después ya ve «revisando».
    libre = check_lock.acquire(blocking=False)
    if not libre and not esperar:
        return

    def revisar():
        if not libre:
            check_lock.acquire()
        try:
            core.comprobar(session)
            anotar_exito()
        except core.SessionExpired:
            pass  # sesion_caducada ya avisó y cerró la sesión
        except Exception as e:
            core.log(f"ERROR al revisar Aules: {e}")
            anotar_fallo(e)
        finally:
            check_lock.release()

    threading.Thread(target=revisar, daemon=True).start()


def buscar_actualizacion_en_segundo_plano():
    """Al refrescar también se busca una versión nueva de la app, sin esperar a la comprobación de cada 6 horas."""

    def buscar():
        try:
            actualizador.buscar()
        except (requests.RequestException, ValueError, actualizador.ActualizacionError) as e:
            core.log(f"No se pudo buscar actualizaciones: {e}")

    threading.Thread(target=buscar, daemon=True).start()


def comprobar_periodicamente():
    """Revisa Aules cada minuto y medio mientras la app está abierta."""
    ultimo_error = None
    # La pantalla principal se guarda ya hecha: tras actualizar o reiniciar se rehace al momento con el código
    # nuevo y lo último guardado, sin esperar a que responda Aules.
    session = core.load_session()
    if session:
        try:
            with check_lock:
                core.escribir_informe(session)
        except Exception as e:
            core.log(f"No se pudo rehacer la pantalla principal al arrancar: {e}")
    time.sleep(10)
    while True:
        session = core.load_session()
        if session and check_lock.acquire(blocking=False):
            try:
                core.comprobar(session)
                anotar_exito()
                if ultimo_error:
                    core.log("Conexión con Aules recuperada")
                ultimo_error = None
            except core.SessionExpired:
                pass  # sesion_caducada ya avisó y cerró la sesión
            except Exception as e:
                # La página avisa también de los fallos de la revisión automática (sin conexión, mantenimiento).
                anotar_fallo(e)
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
