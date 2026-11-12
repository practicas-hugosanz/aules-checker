"""Pruebas de las partes delicadas de la app, con casos reales que ya han dado problemas.

Uso:   python -m unittest pruebas          (publicar.py las pasa solo antes de subir nada)
No se conectan a Aules ni tocan tus datos: todo se hace en carpetas temporales.
"""
import base64
import hashlib
import html
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests

import actualizador
import aules_checker as core
import ia
import interfaz
import temas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def sin_etiquetas(texto):
    return re.sub(r"<[^>]+>", "", texto)


class TextoDePdf(unittest.TestCase):
    """limpiar_texto_pdf recompone el texto que pypdf saca cortado a lo ancho de la página."""

    CABECERA = "Tema 1               Práctica 2: Instalación UBUNTU           Página {n}  "
    PIE = "Implantación de Sistemas Operativos v 25.01 "

    def pagina(self, n, *lineas):
        return "\n".join([" ", self.CABECERA.format(n=n), " ", " ", self.PIE, " ", *lineas, " ", " "])

    def test_quita_cabecera_y_pie_repetidos(self):
        contenidos = ["Ya hemos visto como crear una máquina virtual.", "Se abrirá una ventana de inicio.",
                      "Cuando el chequeo termine, pulsa Instalar.", "Reinicia la máquina."]
        texto = ia.limpiar_texto_pdf([self.pagina(n, c) for n, c in enumerate(contenidos, 1)])
        self.assertNotIn("Página", texto)
        self.assertNotIn("v 25.01", texto)
        for c in contenidos:
            self.assertIn(c, texto)

    def test_no_confunde_titulos_numerados_con_la_cabecera(self):
        paginas = [self.pagina(n, f"Ejercicio {n + 4}", f"Enunciado del ejercicio número {n + 4}.") for n in range(1, 5)]
        texto = ia.limpiar_texto_pdf(paginas)
        for n in range(5, 9):
            self.assertIn(f"Ejercicio {n}", texto)

    # Cabecera de instituto de 6 líneas (inventada), como la de las prácticas de los PDFs reales.
    BLOQUE = ["IES EJEMPLO", "Calle Mayor s/n", "03000 CIUDAD (PROVINCIA)", "info@centro.example",
              "Telf: 960000000 | Fax: 960000001 www.centro.example", "ISO . V. 2025"]

    def pagina_larga(self, n, cuerpo, pie_antes_de=0, pegadas=False):
        """Una página con el título y el bloque del instituto arriba; con `pie_antes_de` el bloque sale tras el contenido
        (salvo las últimas líneas), como hace el PDF cuando la página tiene poco texto; con `pegadas` dos líneas se unen."""
        bloque = list(self.BLOQUE)
        if pegadas:
            bloque[3:6] = ["info@centro.example ISO . V. 2025"]
        titulo = f"Tema 1 Práctica 6 - Sistema dual Página {n}"
        if pie_antes_de:
            return "\n".join([titulo, *cuerpo[:-pie_antes_de], *bloque, *cuerpo[-pie_antes_de:]])
        return "\n".join([titulo, *bloque, *cuerpo])

    def test_quita_cabeceras_largas_aunque_el_pie_salga_despues_del_contenido(self):
        cuerpos = [["Abre el administrador de discos.", "Reduce el volumen C."], ["Crea un volumen nuevo.", "Ponle la letra E."],
                   ["Asigna cuarenta gigas.", "Etiqueta el volumen como DEV."], ["Reinicia desde el disco.", "Instala el otro sistema."],
                   ["Arranca por el volumen tres.", "Termina la instalación."], ["Abre msconfig.", "Mira la pestaña de arranque."]]
        paginas = [self.pagina_larga(n, c, pie_antes_de=(1 if n % 2 == 0 else 0), pegadas=(n == 4))
                   for n, c in enumerate(cuerpos, 1)]
        texto = ia.limpiar_texto_pdf(paginas)
        for resto in ("EJEMPLO", "Calle Mayor", "CIUDAD", "centro.example", "Telf", "ISO . V.", "Página"):
            self.assertNotIn(resto, texto)
        for cuerpo in cuerpos:
            for linea in cuerpo:
                self.assertIn(linea.rstrip("."), texto)

    def test_un_numero_suelto_del_contenido_no_es_un_numero_de_pagina(self):
        paginas = [self.pagina_larga(1, ["Portada."]),
                   self.pagina_larga(2, ["Pon las fases en orden:", "3", "2", "4", "1"]),
                   self.pagina_larga(3, ["Haz capturas de las particiones de Windows 11 y windows", "10"])]
        texto = ia.limpiar_texto_pdf(paginas)
        self.assertRegex(texto, r"3\s+2\s+4\s+1")
        self.assertRegex(texto, r"windows\s+10")
        self.assertNotIn("EJEMPLO", texto)

    def test_une_parrafos_cortados_tambien_entre_paginas(self):
        largo = "Antes de esto, para hacer más cómoda la instalación, vamos a cambiar la resolución de la ventana para poder verla a "
        paginas = [
            self.pagina(1, largo),
            self.pagina(2, "un tamaño normal. Para esto pulsaremos en los tres iconos de arriba a la derecha y en el menú desplegable."),
            self.pagina(3, "Fin."),
        ]
        self.assertIn("para poder verla a un tamaño normal.", ia.limpiar_texto_pdf(paginas))

    def test_listas_titulos_y_vinetas(self):
        paginas = [self.pagina(1, "Portada de la práctica"),
                   self.pagina(2, "Objetivos ", " ", " Instalar un sistema operativo Ubuntu  ",
                               "1) Todos los clientes deben recibir el ", "direccionamiento privado por DHCP",
                               "2) El servidor recibe la .250"),
                   self.pagina(3, "Entrega la captura por Aules.")]
        texto = ia.limpiar_texto_pdf(paginas)
        self.assertIn("• Instalar un sistema operativo Ubuntu", texto)
        self.assertNotIn("", texto)
        self.assertIn("1) Todos los clientes deben recibir el direccionamiento privado por DHCP", texto)
        self.assertIn("\n2) El servidor", texto)

    def test_ligaduras_y_espacios(self):
        texto = ia.limpiar_texto_pdf(["Conﬁgura la red Wiﬁ   con   DHCP"])
        self.assertEqual(texto, "Configura la red Wifi con DHCP")

    def test_elige_el_modo_que_menos_parte_las_palabras(self):
        class Pagina:
            def __init__(self, normal, layout):
                self.textos = {None: normal, "layout": layout}

            def extract_text(self, extraction_mode=None):
                return self.textos[extraction_mode]

        # Ubuntu: el modo normal parte "iniciará"; el layout no.
        self.assertEqual(ia._texto_pagina_pdf(Pagina("Se in iciará Ubuntu", "Se  iniciará Ubuntu")), "Se  iniciará Ubuntu")
        # Examen de Xarxes: es al revés.
        self.assertEqual(ia._texto_pagina_pdf(Pagina("Todos los clientes", "To d o s l o s clientes")), "Todos los clientes")
        # El layout se salta el texto girado: si pierde letras no se usa aunque tenga menos palabras.
        self.assertEqual(ia._texto_pagina_pdf(Pagina("Hola a todos los alumnos", "Hola")), "Hola a todos los alumnos")


class TextoDeArchivos(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.carpeta, True)

    def escribir(self, nombre, texto):
        ruta = os.path.join(self.carpeta, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(texto)
        return ruta

    def test_cache_se_renueva_si_cambia_el_archivo(self):
        ruta = self.escribir("enunciado.txt", "primera versión")
        self.assertEqual(ia.extraer_texto(ruta), "primera versión")
        with mock.patch.object(ia, "_leer_texto", side_effect=AssertionError("no debía releerse")):
            self.assertEqual(ia.extraer_texto(ruta), "primera versión")
        self.escribir("enunciado.txt", "segunda versión, más larga")
        os.utime(ruta, (time.time() + 5, time.time() + 5))
        self.assertEqual(ia.extraer_texto(ruta), "segunda versión, más larga")

    def test_enunciado_largo_se_corta_al_final_de_un_parrafo(self):
        parrafos = [f"Párrafo {n}. " + "texto " * 60 for n in range(200)]
        self.escribir("practica.txt", "\n\n".join(parrafos))
        item = {"summary": "", "attachments": [{"path": "practica.txt", "filename": "practica.txt"}]}
        core.leer_enunciado_de_archivos(type("Ctx", (), {"acc_dir": self.carpeta})(), item)
        texto = item["summary_file"]
        self.assertLessEqual(len(texto), core.ENUNCIADO_MAX_CHARS + 60)
        self.assertTrue(texto.endswith("[…] El enunciado sigue en el archivo."))
        self.assertRegex(texto, r"texto\n\n\[…\]")

    def test_enunciado_corto_sale_entero(self):
        self.escribir("corto.txt", "Haz la práctica 1 y entrégala en Aules antes del viernes.")
        item = {"summary": "", "attachments": [{"path": "corto.txt", "filename": "corto.txt"}]}
        core.leer_enunciado_de_archivos(type("Ctx", (), {"acc_dir": self.carpeta})(), item)
        self.assertEqual(item["summary_file"], "Haz la práctica 1 y entrégala en Aules antes del viernes.")


class Notas(unittest.TestCase):
    def nota(self, grade, maximo="10", estado="", **extra):
        return dict({"id": "nota_1", "course": "Curso", "name": "Prueba", "total": False, "grade": grade, "estado": estado,
                     "max": maximo, "percentage": "", "feedback": "", "graded": 0, "activity": "", "url": "#"}, **extra)

    def badge(self, n):
        return sin_etiquetas(interfaz._estado_nota(n))

    def test_icono_de_aules(self):
        valor, estado = core.separar_nota('<i class="icon fa fa-check text-success fa-fw" title="Aprobado" aria-label="Aprobado"></i>8,50')
        self.assertEqual((valor, estado), ("8,50", "Aprobado"))

    def test_estado_de_aules_manda(self):
        self.assertEqual(self.badge(self.nota("4,00", estado="Aprobado")), "Aprobado")

    def test_sin_nota_minima_se_calcula_con_la_mitad(self):
        self.assertEqual(self.badge(self.nota("9,06")), "Aprobado")  # T1B2: el profe no puso nota mínima
        self.assertEqual(self.badge(self.nota("5,00")), "Aprobado")
        self.assertEqual(self.badge(self.nota("4,99")), "Suspendido")
        self.assertEqual(self.badge(self.nota("85,00", maximo="100")), "Aprobado")
        self.assertEqual(self.badge(self.nota("60,00 %", maximo="")), "Aprobado")

    def test_muestra_la_nota_minima_para_aprobar(self):
        self.assertEqual(self.badge(self.nota("6,55", estado="Suspenso", aprobar="8")), "Suspenso · mínimo 8")
        self.assertEqual(self.badge(self.nota("6,55", estado="Suspenso", aprobar="")), "Suspenso")

    def test_sin_nota_numerica_no_hay_badge(self):
        self.assertEqual(self.badge(self.nota("-")), "")
        self.assertEqual(self.badge(self.nota("Apto", maximo="")), "")

    def test_las_notas_de_practica_salen_en_notas(self):
        notas = [self.nota("100,00", maximo="100", id="nota_1", course="Anglés", activity="hotpot_1", name="Quiz"),
                 self.nota("85,00", maximo="100", id="nota_2", course="Anglés", activity="hotpot_2", name="Match")]
        practicas = [{"id": "p1", "name": "Quiz", "course": "Anglés", "section": "", "activity": "hotpot_1", "url": "#"},
                     {"id": "p2", "name": "Match", "course": "Anglés", "section": "", "activity": "hotpot_2", "url": "#"}]
        pagina = interfaz.build_report([], [], {"username": "prueba"}, [], 48, courses=["Anglés"], notas=notas, practicas=practicas)
        self.assertIn("Notas (2)", pagina)
        self.assertIn("2 de 2 hechos", pagina)


class AvisoDeNuevo(unittest.TestCase):
    def test_dura_24_horas(self):
        ahora = 1_000_000
        estado = {"items": {"vieja": ahora - 24 * 3600 - 60, "reciente": ahora - 23 * 3600}}
        items = [{"id": i, "kind": "tarea", "done": False} for i in ("vieja", "reciente", "nueva")]
        core.mark_new_items(estado, items, ahora, first_sync=False)
        self.assertEqual({i["id"]: i["is_new"] for i in items}, {"vieja": False, "reciente": True, "nueva": True})


class ResumenYRecordatorios(unittest.TestCase):
    def tarea(self, id_, cuando, kind="tarea", etiqueta="Entrega"):
        return {"id": id_, "name": id_, "kind": kind, "done": False, "duedate": cuando.timestamp(), "due_label": etiqueta}

    def test_resumen_de_la_manana_y_de_la_tarde(self):
        jueves = core.datetime(2026, 10, 1)  # jueves lectivo; el viernes también
        items = [self.tarea("hoy", jueves.replace(hour=14)), self.tarea("manana", jueves.replace(hour=23) + core.timedelta(days=1)),
                 self.tarea("lunes", jueves + core.timedelta(days=4, hours=10)), self.tarea("ya_paso", jueves.replace(hour=7))]
        estado = {}
        self.assertIsNone(core.tomorrow_summary(estado, items, jueves.replace(hour=6), {}))
        manana = core.tomorrow_summary(estado, items, jueves.replace(hour=8), {})
        self.assertEqual((manana["cuando"], [a["id"] for a in manana["items"]]), ("hoy y mañana", ["hoy", "manana"]))
        self.assertIsNone(core.tomorrow_summary(estado, items, jueves.replace(hour=11), {}))  # una vez por la mañana
        tarde = core.tomorrow_summary(estado, items, jueves.replace(hour=19), {})
        self.assertEqual((tarde["cuando"], [a["id"] for a in tarde["items"]]), ("mañana", ["manana"]))

    def test_un_examen_nuevo_no_avisa_dos_veces(self):
        estado, ahora = {"reminders": {}}, 1_000_000
        examen = {"id": "quiz_1", "name": "T1B3", "kind": "examen", "done": False, "duedate": ahora + 2 * 3600, "due_label": "Abre"}
        recordatorios = core.pending_reminders(estado, [examen], ahora, "examen", core.EXAM_REMINDER_HOURS)
        self.assertEqual(core.sin_las_nuevas(recordatorios, [examen]), [])
        # Queda apuntado: en la siguiente comprobación no salta por el mismo umbral.
        self.assertEqual(core.pending_reminders(estado, [examen], ahora + 90, "examen", core.EXAM_REMINDER_HOURS), [])

    def test_titulos_de_los_cuestionarios(self):
        abre, cierra, normal = ({"due_label": e} for e in ("Abre", "Cierra", "Examen"))
        self.assertEqual(core.titulo_recordatorio([(abre, 3)], "Examen en menos de {h} h"), "Se abre en menos de 3 h")
        self.assertEqual(core.titulo_recordatorio([(cierra, 48)], "Examen en menos de {h} h"), "Cierra en menos de 48 h")
        self.assertEqual(core.titulo_recordatorio([(normal, 24), (abre, 3)], "Examen en menos de {h} h"), "Examen en menos de 3 h")


class TareasModificadas(unittest.TestCase):
    def tarea(self, **cambios):
        return dict({"id": "assign_1", "name": "Práctica 1", "course": "Redes", "kind": "tarea", "done": False, "status": "",
                     "duedate": 1_790_000_000, "due_label": "Entrega", "summary": "Haz la práctica.",
                     "attachments": [{"filename": "enunciado.pdf", "path": "x", "timemodified": 100}]}, **cambios)

    def comprobar(self, estado, tarea, ahora=1_000_000):
        items = [tarea]
        return core.mark_changed_items(estado, items, ahora), items[0]

    def test_la_primera_vez_no_avisa(self):
        cambiadas, tarea = self.comprobar({}, self.tarea())
        self.assertEqual((cambiadas, tarea["cambios"]), ([], []))

    def test_avisa_de_fecha_descripcion_y_archivos(self):
        estado = {}
        self.comprobar(estado, self.tarea())
        nueva = self.tarea(duedate=1_790_000_000 + 4 * 86400, summary="Haz la práctica y la memoria.",
                           attachments=[{"filename": "enunciado.pdf", "path": "x", "timemodified": 200},
                                        {"filename": "datos.pkt", "path": "y", "timemodified": 1}])
        cambiadas, tarea = self.comprobar(estado, nueva)
        self.assertEqual(len(cambiadas), 1)
        texto = " | ".join(tarea["cambios"])
        self.assertIn("La fecha se retrasa", texto)
        self.assertIn("El profe ha cambiado la descripción", texto)
        self.assertIn("Archivo actualizado: enunciado.pdf", texto)
        self.assertIn("Archivo nuevo: datos.pkt", texto)
        pagina = interfaz.build_report([tarea], [], {"username": "prueba"}, [], 48)
        self.assertIn("Modificada", pagina)
        self.assertIn("La fecha se retrasa", pagina)

    def test_prorroga(self):
        estado = {}
        self.comprobar(estado, self.tarea())
        _, tarea = self.comprobar(estado, self.tarea(duedate=1_790_500_000, due_label="Prórroga"))
        self.assertTrue(tarea["cambios"][0].startswith("Tienes prórroga hasta"))

    def test_un_cuestionario_que_se_abre_no_es_un_cambio(self):
        estado = {}
        self.comprobar(estado, self.tarea(kind="examen", due_label="Abre", duedate=1_790_000_000))
        cambiadas, _ = self.comprobar(estado, self.tarea(kind="examen", due_label="Cierra", duedate=1_790_003_600))
        self.assertEqual(cambiadas, [])

    def test_ni_tareas_entregadas_ni_espacios_de_mas(self):
        estado = {}
        self.comprobar(estado, self.tarea())
        self.assertEqual(self.comprobar(estado, self.tarea(summary="  Haz   la práctica. "))[0], [])
        self.assertEqual(self.comprobar(estado, self.tarea(done=True, duedate=1))[0], [])

    def test_las_tareas_que_marcaste_no_avisan(self):
        estado = {}
        core.mark_changed_items(estado, [self.tarea()], 1_000_000, marcadas={"assign_1"})
        items = [self.tarea(duedate=1)]
        self.assertEqual(core.mark_changed_items(estado, items, 1_000_100, marcadas={"assign_1"}), [])
        self.assertEqual(items[0]["cambios"], [])

    def test_si_cambia_el_enunciado_se_olvida_el_resumen_de_ia(self):
        carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, carpeta, True)
        ia.guardar_cache(carpeta, {"assign_1": {"resumen": "viejo", "borrador": {"archivos": ["a.md"]}},
                                   "assign_2": {"resumen": "sigue valiendo"}})
        cambiadas = [dict(self.tarea(), cambios=["El profe ha cambiado la descripción"]),
                     dict(self.tarea(id="assign_2"), cambios=["La fecha se retrasa: del lun al mar"])]
        with mock.patch.object(core, "log"):
            core.olvidar_resumenes(carpeta, cambiadas)
        cache = ia.cargar_cache(carpeta)
        self.assertNotIn("resumen", cache["assign_1"])
        self.assertIn("borrador", cache["assign_1"])
        self.assertEqual(cache["assign_2"]["resumen"], "sigue valiendo")

    def test_el_aviso_dura_24_horas(self):
        estado = {}
        self.comprobar(estado, self.tarea(), ahora=1_000_000)
        self.comprobar(estado, self.tarea(duedate=1), ahora=1_000_000)
        self.assertTrue(self.comprobar(estado, self.tarea(duedate=1), ahora=1_000_000 + 23 * 3600)[1]["cambios"])
        self.assertEqual(self.comprobar(estado, self.tarea(duedate=1), ahora=1_000_000 + 25 * 3600)[1]["cambios"], [])


class EntregarDesdeLaApp(unittest.TestCase):
    """Con Aules simulado: estas pruebas nunca entregan nada de verdad."""

    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        for parche in (mock.patch.object(core, "ACCOUNTS_DIR", self.carpeta), mock.patch.object(core, "escribir_informe"),
                       mock.patch.object(core, "log")):
            parche.start()
            self.addCleanup(parche.stop)
        self.sesion = {"username": "prueba", "token": "x", "base_url": "https://aules.test/fp"}
        os.makedirs(core.account_dir("prueba"))
        self.tarea = {"id": "assign_7", "name": "Práctica 1", "course": "Bases de datos", "kind": "tarea", "done": False,
                      "status": "", "entrega": core.config_entrega({"configs": [
                          {"subtype": "assignsubmission", "plugin": "file", "name": "enabled", "value": "1"},
                          {"subtype": "assignsubmission", "plugin": "file", "name": "maxfilesubmissions", "value": "2"},
                          {"subtype": "assignsubmission", "plugin": "file", "name": "maxsubmissionsizebytes", "value": "1000"},
                          {"subtype": "assignsubmission", "plugin": "file", "name": "filetypeslist", "value": ".sql, .pdf"}]})}
        with open(os.path.join(core.account_dir("prueba"), "items.json"), "w", encoding="utf-8") as f:
            f.write(core.json.dumps([self.tarea]))
        self.llamadas = []
        self.puede_editar, self.estado_final, self.avisos = True, "submitted", []

    def aules(self, base, token, funcion, params=None):
        self.llamadas.append((funcion, params))
        if funcion.endswith("get_submission_status"):
            ya_entregada = any(f.endswith("save_submission") for f, _ in self.llamadas)
            return {"lastattempt": {"canedit": self.puede_editar, "submission": {
                "status": self.estado_final if ya_entregada else "new", "plugins": []}}}
        if funcion.endswith("save_submission"):
            return self.avisos
        if funcion == "core_files_get_unused_draft_itemid":
            return {"itemid": 555}
        raise AssertionError(funcion)

    def entregar(self, archivos, **extra):
        subida = mock.Mock(json=lambda: [{"itemid": 4321, "filename": n} for n, _ in archivos], raise_for_status=lambda: None)
        with mock.patch.object(core, "call_ws", side_effect=self.aules), mock.patch.object(core.http, "post", return_value=subida) as post:
            resultado = core.entregar(self.sesion, self.tarea, archivos, **extra)
        return resultado, post

    def test_lee_lo_que_admite_la_tarea(self):
        self.assertEqual(self.tarea["entrega"], {"archivos": True, "max_archivos": 2, "max_bytes": 1000, "tipos": ".sql, .pdf",
                                                 "texto": False, "borradores": False, "declaracion": "", "desde": 0, "corte": 0})
        self.assertIsNone(core.config_entrega({"configs": []}))

    def test_entrega_y_marca_como_entregada(self):
        _, post = self.entregar([("consultas.sql", b"SELECT 1;")])
        self.assertTrue(post.call_args[0][0].endswith("/webservice/upload.php"))
        guardar = next(p for f, p in self.llamadas if f == "mod_assign_save_submission")
        self.assertEqual(guardar, {"assignmentid": 7, "plugindata[files_filemanager]": 4321})
        items = core._load_aules_items(core.account_dir("prueba"))
        self.assertEqual((items[0]["done"], items[0]["status"]), (True, "Entregada"))

    def test_comprueba_los_limites_antes_de_subir_nada(self):
        casos = [([], "al menos un archivo"), ([("a.sql", b"1"), ("A.sql", b"2")], "dos archivos que se llaman"),
                 ([("a.sql", b"1"), ("b.sql", b"1"), ("c.sql", b"1")], "como mucho 2"),
                 ([("grande.sql", b"x" * 2000)], "máximo"), ([("foto.png", b"1")], "tipo permitido")]
        for archivos, mensaje in casos:
            self.llamadas.clear()
            with self.assertRaisesRegex(core.EntregaError, mensaje):
                self.entregar(archivos)
            self.assertEqual(self.llamadas, [])

    def test_no_entrega_si_aules_ya_no_admite_cambios(self):
        self.puede_editar = False
        with self.assertRaisesRegex(core.EntregaError, "no admite cambios"):
            self.entregar([("a.sql", b"1")])
        self.assertFalse(any(f.endswith("save_submission") for f, _ in self.llamadas))
        # Con las fechas de la tarea, el motivo es concreto.
        self.tarea["entrega"]["desde"] = int(time.time()) + 3 * 86400
        with self.assertRaisesRegex(core.EntregaError, "Todavía no se puede entregar: se abre el"):
            self.entregar([("a.sql", b"1")])
        self.tarea["entrega"].update(desde=0, corte=int(time.time()) - 86400)
        with self.assertRaisesRegex(core.EntregaError, "El plazo de entrega ha terminado"):
            self.entregar([("a.sql", b"1")])

    def test_boton_segun_las_fechas(self):
        ahora = int(time.time())
        boton = lambda **cambios: sin_etiquetas(interfaz._entrega_html(dict(self.tarea, entrega=dict(self.tarea["entrega"], **cambios)), ahora))
        self.assertEqual(boton(), "Entregar")
        self.assertIn("Se podrá entregar desde el", boton(desde=ahora + 86400))
        self.assertEqual(boton(corte=ahora - 60), "Plazo de entrega cerrado")
        self.assertEqual(sin_etiquetas(interfaz._entrega_html(dict(self.tarea, done=True, status="Entregada"), ahora)), "Cambiar la entrega")
        self.assertEqual(interfaz._entrega_html(dict(self.tarea, done=True, status="Calificada · 9"), ahora), "")

    def test_avisa_si_aules_rechaza_o_no_confirma(self):
        self.avisos = [{"item": "Fuera de plazo"}]
        with self.assertRaisesRegex(core.EntregaError, "Fuera de plazo"):
            self.entregar([("a.sql", b"1")])
        self.avisos, self.estado_final, self.llamadas = [], "draft", []
        with self.assertRaisesRegex(core.EntregaError, "no confirma"):
            self.entregar([("a.sql", b"1")])

    def test_solo_texto_y_declaracion(self):
        self.tarea["entrega"].update(archivos=False, max_archivos=0, texto=True, declaracion="Este trabajo es mío.")
        with self.assertRaisesRegex(core.EntregaError, "declaración"):
            self.entregar([], texto="Mi respuesta")
        self.llamadas.clear()
        self.entregar([], texto="Línea 1\n<b>Línea 2</b>", acepta_declaracion=True)
        guardar = next(p for f, p in self.llamadas if f == "mod_assign_save_submission")
        self.assertEqual(guardar["plugindata[onlinetext_editor][text]"], "Línea 1<br>&lt;b&gt;Línea 2&lt;/b&gt;")

    def test_los_archivos_del_borrador_no_salen_de_su_carpeta(self):
        carpeta = os.path.join(self.carpeta, "borrador")
        os.makedirs(carpeta)
        with open(os.path.join(carpeta, "respuesta.sql"), "w") as f:
            f.write("SELECT 1;")
        cache = {"assign_7": {"borrador": {"carpeta": carpeta, "archivos": ["respuesta.sql", "../items.json", "falta.sql"]}}}
        self.assertEqual(core.archivos_del_borrador(cache, self.tarea), [os.path.join(carpeta, "respuesta.sql")])


class CuantoLlevo(unittest.TestCase):
    def nota(self, nombre, nota=None, maximo=10, peso=None, tipo="mod", id_=None):
        return {"id": id_ or nombre, "itemtype": tipo, "itemname": nombre, "graderaw": nota, "grademax": maximo, "weightraw": peso}

    def test_con_los_pesos_de_aules(self):
        # Implantación: cuatro baterías al 25 % y las prácticas al 0 %.
        notas = [self.nota(f"B{i}", n, peso=0.25) for i, n in enumerate((9.25, 9.0625, 10, 8.5))] + [self.nota("Práctica", None, 2, 0)]
        p = core.progreso_asignatura(notas)
        self.assertEqual((p["fuente"], p["media"], p["corregido"], p["necesaria"]), ("aules", 9.2, 100, None))
        self.assertIn("Ya está corregido todo", sin_etiquetas(interfaz._progreso_html(p)))

    def test_con_porcentajes_en_el_nombre_y_lo_que_falta(self):
        # IPO: «RA 1 (30%)» sobre 3, «RA 3 (40%)» sobre 4…; la tarea sin porcentaje no cuenta.
        notas = [self.nota("RA 1 (30%) PRL", 1.2, 3), self.nota("RA 2 (10%)", None, 1), self.nota("RA 3 (40%) Derecho", None, 4),
                 self.nota("RA 4 (10%)", None, 1), self.nota("RA 5 (10%)", None, 1), self.nota("Documental", 90, 100)]
        p = core.progreso_asignatura(notas)
        self.assertEqual((p["fuente"], p["media"], p["corregido"]), ("nombres", 4, 30))
        self.assertAlmostEqual(p["necesaria"], 5.43, places=2)  # (0,5 - 0,12) / 0,7
        texto = sin_etiquetas(interfaz._progreso_html(p))
        self.assertIn("Para llegar al 5 te hace falta sacar 5,43", texto)
        self.assertIn("cada RA por separado", texto)

    def test_ya_aprobado_o_imposible(self):
        bien = core.progreso_asignatura([self.nota("A (60%)", 10), self.nota("B (40%)")])
        self.assertIn("ya tienes el 5", sin_etiquetas(interfaz._progreso_html(bien)))
        mal = core.progreso_asignatura([self.nota("A (80%)", 0), self.nota("B (20%)")])
        self.assertIn("ya no se llega al 5", sin_etiquetas(interfaz._progreso_html(mal)))

    def test_sin_pesos_fiables_no_se_inventa(self):
        sin_pesos = [self.nota("Práctica 1", 8)]
        con_subcategorias = [self.nota("Unidad 1", tipo="category", peso=0.7), self.nota("Quiz", 85, 100, peso=None)]
        no_suman_100 = [self.nota("A (30%)", 8), self.nota("B (30%)")]
        sin_corregir = [self.nota("A (50%)"), self.nota("B (50%)")]
        for notas in (sin_pesos, con_subcategorias, no_suman_100, sin_corregir, []):
            self.assertIsNone(core.progreso_asignatura(notas))
        self.assertEqual(interfaz._progreso_html(None), "")


class Etapas(unittest.TestCase):
    def test_cada_etapa_tiene_su_carpeta_y_fp_sigue_igual(self):
        fp = {"username": "10901748", "base_url": "https://aules.edu.gva.es/fp"}
        bach = dict(fp, base_url="https://aules.edu.gva.es/batxillerat")
        eso = dict(fp, base_url="https://aules.edu.gva.es/eso46/")
        self.assertEqual(os.path.basename(core.carpeta(fp)), "10901748")  # las cuentas de FP no se mueven
        self.assertEqual(os.path.basename(core.carpeta(bach)), "10901748@batxillerat")
        self.assertEqual(os.path.basename(core.carpeta(eso)), "10901748@eso46")
        self.assertEqual(os.path.basename(core.carpeta({"username": "10901748"})), "10901748")  # sesiones antiguas

    def test_solo_se_entra_en_los_aules_de_la_lista(self):
        with mock.patch.object(core, "get_token", side_effect=AssertionError("no debía conectarse")):
            with self.assertRaisesRegex(core.LoginError, "Elige una etapa"):
                core.login("alumno", "clave", "https://otra-web.example/moodle")
        sitio = {"firstname": "Ana", "fullname": "Ana Prueba"}
        with mock.patch.object(core, "get_token", return_value="t") as token, \
                mock.patch.object(core, "call_ws", return_value=sitio), mock.patch.object(core, "save_session"), \
                mock.patch.object(core, "log"):
            sesion = core.login("alumno", "clave", interfaz.PORTALES["eso03"][1])
        self.assertEqual(token.call_args[0][0], "https://aules.edu.gva.es/eso03")
        self.assertEqual(interfaz.portal_de(sesion["base_url"]), "eso03")

    def test_formulario_y_cabecera(self):
        formulario = interfaz.render_login(portal="batxillerat")
        self.assertIn('<option value="batxillerat" selected>Bachillerato</option>', formulario)
        for clave in ("fp", "eso03", "eso46", "eso12"):
            self.assertIn(f'<option value="{clave}"', formulario)
        pagina = interfaz.build_report([], [], {"username": "x", "base_url": "https://aules.edu.gva.es/eso12"}, [], 48)
        self.assertIn("Aules · ESO · Castellón", pagina)


class Temas(unittest.TestCase):
    def test_todos_los_temas_generan_su_css(self):
        for clave, tema in temas.TEMAS.items():
            if clave != "clasico":
                self.assertIn(f'[data-estilo="{clave}"]', temas.TEMAS_CSS)
            self.assertIn(tema["modos"][0], ("auto", "claro", "oscuro"))
        # Ninguna regla de tema se queda sin prefijo: afectaría a todos los temas a la vez.
        for regla in re.findall(r"(?m)^([^@\s{}][^{}]*)\{", temas.TEMAS_CSS):
            for selector in temas._dividir(regla):
                self.assertIn("[data-estilo=", selector, selector)

    def test_tema_con_un_solo_modo_lo_impone(self):
        self.assertEqual(temas.elegido({"estilo": "terminal", "modo": "claro"}), ("terminal", "oscuro"))
        self.assertEqual(temas.elegido({"estilo": "suizo", "modo": "oscuro"}), ("suizo", "oscuro"))
        self.assertEqual(temas.elegido({"estilo": "inventado", "modo": "raro"}), ("clasico", "auto"))

    def test_con_tema_marca_la_pagina_y_carga_la_letra(self):
        pagina = interfaz.render_error("prueba")
        marcada = temas.con_tema(pagina, {"estilo": "retro"})
        self.assertIn('<html lang="es" data-estilo="retro" data-modo="claro">', marcada)
        self.assertIn("family=VT323", marcada)


class FotoDePerfil(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        parche = mock.patch.object(core, "ACCOUNTS_DIR", self.carpeta)
        parche.start()
        self.addCleanup(parche.stop)
        self.sesion = {"username": "prueba", "token": "x"}
        os.makedirs(core.account_dir("prueba"))

    def test_sin_foto_propia_se_usan_las_iniciales(self):
        ruta, datos = core._rutas_foto(self.sesion)
        for f in (ruta, datos):
            with open(f, "w") as fh:
                fh.write('{"url": "u", "tipo": "image/jpeg"}')
        core.actualizar_foto(self.sesion, {"userpictureurl": "https://aules.edu.gva.es/fp/theme/image.php/aules/core/1/u/f1"})
        self.assertFalse(os.path.exists(ruta) or os.path.exists(datos))
        self.assertEqual(core.version_foto(self.sesion), "")
        pagina = interfaz.build_report([], [], {"username": "prueba", "fullname": "Hugo Sanz"}, [], 48)
        self.assertNotIn('src="/foto', pagina)

    def test_con_foto_se_muestra_y_no_se_redescarga(self):
        url = "https://aules.edu.gva.es/fp/pluginfile.php/9/user/icon/aules/f1?rev=1"
        respuesta = mock.Mock(content=b"jpeg", headers={"Content-Type": "image/jpeg"})
        with mock.patch.object(core.http, "get", return_value=respuesta) as get:
            core.actualizar_foto(self.sesion, {"userpictureurl": url})
            core.actualizar_foto(self.sesion, {"userpictureurl": url})
        self.assertEqual(get.call_count, 1)
        self.assertIn("/webservice/pluginfile.php/", get.call_args[0][0])
        self.assertEqual(core.cargar_foto(self.sesion), (b"jpeg", "image/jpeg"))
        pagina = interfaz.build_report([], [], {"username": "prueba", "fullname": "Hugo Sanz"}, [], 48,
                                       foto=core.version_foto(self.sesion))
        self.assertIn('src="/foto?v=', pagina)


class Actualizaciones(unittest.TestCase):
    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        for nombre in actualizador.ARCHIVOS:
            shutil.copy2(os.path.join(BASE_DIR, nombre), self.carpeta)

    def test_el_codigo_actual_arranca(self):
        self.assertEqual(actualizador.probar_codigo(self.carpeta), "")

    def test_detecta_un_archivo_que_falta(self):
        os.remove(os.path.join(self.carpeta, "temas.py"))
        self.assertIn("temas", actualizador.probar_codigo(self.carpeta))

    def test_detecta_un_error_al_generar_pantallas(self):
        ruta = os.path.join(self.carpeta, "interfaz.py")
        with open(ruta, "a", encoding="utf-8") as f:
            f.write("\ndef render_error(message):\n    raise RuntimeError('pantalla rota')\n")
        self.assertIn("pantalla rota", actualizador.probar_codigo(self.carpeta))

    def test_restaura_la_version_anterior(self):
        anterior = os.path.join(self.carpeta, "anterior")
        os.makedirs(anterior)
        with open(os.path.join(anterior, "servidor.py"), "w", encoding="utf-8") as f:
            f.write("# versión buena\n")
        with mock.patch.multiple(actualizador, BASE_DIR=self.carpeta, CARPETA_ANTERIOR=anterior):
            self.assertTrue(actualizador.restaurar_anterior(log=lambda m: None))
            self.assertFalse(actualizador.restaurar_anterior(log=lambda m: None))  # ya no queda copia
        with open(os.path.join(self.carpeta, "servidor.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "# versión buena\n")

    def instalar_simulado(self, nuevos):
        """Ejecuta instalar() sobre la carpeta temporal como si GitHub publicara esos archivos."""
        info = {"version": "99.0.0", "cambios": [], "archivos": {n: actualizador.huella(d) for n, d in nuevos.items()}}
        respuestas = {n: mock.Mock(content=d, raise_for_status=lambda: None) for n, d in nuevos.items()}
        with mock.patch.multiple(actualizador, BASE_DIR=self.carpeta, CARPETA_ANTERIOR=os.path.join(self.carpeta, "anterior"),
                                 CARPETA_PRUEBA=os.path.join(self.carpeta, ".actualizacion"), buscar=lambda: info), \
                mock.patch.object(actualizador.requests, "get", side_effect=lambda url, **k: respuestas[url.rsplit("/", 1)[1]]):
            return actualizador.instalar(log=lambda m: None)

    def leer(self, nombre):
        with open(os.path.join(self.carpeta, nombre), "rb") as f:
            return f.read()

    def test_una_version_rota_no_se_instala(self):
        antes = self.leer("temas.py")
        with self.assertRaises(actualizador.ActualizacionError):
            self.instalar_simulado({"temas.py": b"esto no es python ("})
        self.assertEqual(self.leer("temas.py"), antes)
        self.assertFalse(os.path.exists(os.path.join(self.carpeta, "anterior")))
        self.assertFalse(os.path.exists(os.path.join(self.carpeta, ".actualizacion")))

    def test_una_version_buena_se_instala_y_guarda_copia(self):
        antes = self.leer("temas.py")
        nuevo = antes + b"\n# version nueva\n"
        self.assertEqual(self.instalar_simulado({"temas.py": nuevo}), {"ok": True, "version": "99.0.0"})
        self.assertEqual(self.leer("temas.py"), nuevo)
        with open(os.path.join(self.carpeta, "anterior", "temas.py"), "rb") as f:
            self.assertEqual(f.read(), antes)

    def test_en_la_copia_de_desarrollo_nunca_restaura(self):
        os.makedirs(os.path.join(self.carpeta, ".git"))
        os.makedirs(os.path.join(self.carpeta, "anterior"))
        with mock.patch.multiple(actualizador, BASE_DIR=self.carpeta, CARPETA_ANTERIOR=os.path.join(self.carpeta, "anterior")):
            self.assertFalse(actualizador.restaurar_anterior(log=lambda m: None))


class EnunciadoEnPdf(unittest.TestCase):
    """Si el enunciado está en un PDF se enseña el PDF; si está en un Word, su texto."""

    def pagina(self, nombre, adjuntos):
        tarea = {"id": "assign_9", "name": "Práctica 5", "course": "Sistemas", "kind": "tarea", "done": False, "status": "",
                 "duedate": 1_790_000_000, "due_label": "Entrega", "summary": "", "summary_file": "Texto sacado del archivo " * 3,
                 "summary_file_name": nombre, "attachments": adjuntos}
        return interfaz.build_report([tarea], [], {"username": "prueba"}, [], 48)

    def test_pdf_se_enseña_como_vista_previa(self):
        pagina = self.pagina("Práctica 5.pdf", [{"filename": "Práctica 5.pdf", "path": "adjuntos/Curso 1/Tarea/Práctica 5.pdf"}])
        self.assertIn('class="desc desc-pdf"', pagina)
        self.assertIn('data-src="/adjuntos/Curso%201/Tarea/Pr%C3%A1ctica%205.pdf#view=FitH&amp;navpanes=0"', pagina)
        self.assertIn('class="pdf-marco"', pagina)
        self.assertNotIn('class="desc-body"', pagina)  # ya no se enseña el texto sacado del PDF
        self.assertNotIn(' src="/adjuntos/', pagina)  # y el PDF no se carga hasta abrir el desplegable

    def test_word_sigue_enseñando_su_texto(self):
        pagina = self.pagina("Enunciado.docx", [{"filename": "Enunciado.docx", "path": "adjuntos/Curso/Tarea/Enunciado.docx"}])
        self.assertNotIn("desc-pdf", pagina.split("</style>", 1)[1].split("<script", 1)[0])
        self.assertIn("Texto sacado del archivo", pagina)

    def test_sin_el_archivo_guardado_cae_al_texto(self):
        pagina = self.pagina("Práctica 5.pdf", [])
        self.assertNotIn('class="desc desc-pdf"', pagina)
        self.assertIn("Texto sacado del archivo", pagina)


class RevisionDeCuestionarios(unittest.TestCase):
    """analizar_pregunta convierte el HTML de la revisión de Aules en preguntas, opciones y respuestas."""

    @staticmethod
    def opcion(letra, texto, marcada=False, clase=""):
        return (f'<div class="r0 {clase}"><input type="radio" disabled="disabled" value="0"{" checked=\"checked\"" if marcada else ""} />'
                f'<div class="d-flex w-auto" data-region="answer-label"><span class="answernumber">{letra}. </span>'
                f'<div class="flex-fill ms-1">{texto}</div></div></div>')

    def pregunta(self, opciones, estado="incorrect", correcta="", comentario=""):
        html = (f'<div class="que multichoice deferredfeedback {estado}"><div class="info"><h3 class="no">Pregunta <span class="qno">3</span></h3></div>'
                '<div class="content"><div class="formulation clearfix"><h4 class="accesshide">Enunciado de la pregunta</h4>'
                '<div class="qtext"><p>¿Cuál es la memoria más rápida?</p></div><fieldset class="ablock"><div class="answer">'
                + "".join(opciones) + '</div></fieldset></div><div class="outcome clearfix"><div class="feedback">'
                + (f'<div class="specificfeedback">{comentario}</div>' if comentario else "")
                + (f'<div class="rightanswer">La respuesta correcta es: {correcta}</div>' if correcta else "")
                + '</div></div></div></div><script>var x = 1;</script>')
        return {"html": html, "questionnumber": "3", "type": "multichoice", "stateclass": estado,
                "status": "Incorrecta", "mark": "-0,25", "maxmark": 1}

    def test_fallada_con_respuesta_correcta(self):
        p = core.analizar_pregunta(self.pregunta(
            [self.opcion("a", "Registros"), self.opcion("b", "Memoria caché", marcada=True, clase="incorrect")],
            correcta="Registros", comentario="Los registros están dentro de la CPU."))
        self.assertEqual(p["enunciado"], "¿Cuál es la memoria más rápida?")
        self.assertEqual([(o["letra"], o["texto"], o["marcada"], o["es_correcta"]) for o in p["opciones"]],
                         [("a", "Registros", False, True), ("b", "Memoria caché", True, False)])
        self.assertEqual(p["correcta"], "Registros")
        self.assertEqual(p["comentario"], "Los registros están dentro de la CPU.")
        self.assertEqual((p["estado"], p["nota"], p["max"]), ("incorrect", "-0,25", "1"))

    def test_sin_respuesta_correcta_visible_vale_la_marcada_si_acerto(self):
        p = core.analizar_pregunta(self.pregunta(
            [self.opcion("a", "Registros", marcada=True, clase="correct"), self.opcion("b", "Disco")], estado="correct",
            comentario="Respuesta correcta"))
        self.assertEqual([o["es_correcta"] for o in p["opciones"]], [True, False])
        self.assertEqual((p["correcta"], p["comentario"]), ("", ""))  # «Respuesta correcta» a secas no aporta nada

    def test_arrastrar_a_una_imagen(self):
        zonas = ('{"1":{"no":"1","group":"1","xy":["239","66"],"fieldname":"q1:5_p1"},'
                 '"2":{"no":"2","group":"1","xy":["224","147"],"fieldname":"q1:5_p2"}}').replace('"', "&quot;")
        html = ('<div class="que ddimageortext correct"><div class="formulation"><div class="qtext"><p>Ordena las memorias</p></div>'
                '<div class="ddarea"><div class="droparea"><img class="dropbackground" src="https://aules.edu.gva.es/fp/pluginfile.php/1/fondo.jpg" />'
                f'<div class="dropzones" data-place-info="{zonas}"></div></div><div class="draghomes"><div class="dragitemgroup1">'
                '<div class="group1 draghome choice1">Memoria caché</div><div class="group1 draghome choice2">Registros</div></div></div></div>'
                '<input type="hidden" name="q1:5_p1" value="2" /><input type="hidden" name="q1:5_p2" value="0" /></div></div>')
        p = core.analizar_pregunta({"html": html, "type": "ddimageortext"}, guardar_imagen=lambda url: "revisiones/1/fondo.jpg")
        self.assertEqual(p["fondo"], "revisiones/1/fondo.jpg")
        self.assertEqual([(z["n"], z["x"], z["texto"]) for z in p["zonas"]], [("1", 239, "Registros"), ("2", 224, "")])

    def test_la_pagina_marca_tu_respuesta_y_la_correcta(self):
        p = core.analizar_pregunta(self.pregunta(
            [self.opcion("a", "Registros"), self.opcion("b", "Memoria caché", marcada=True, clase="incorrect")], correcta="Registros"))
        pagina = interfaz.render_revision({"id": "quiz_1", "name": "Batería 1", "course": "Sistemas"},
                                          {"intentos": [{"id": 9, "numero": 1, "fin": 0, "nota": "9,06", "preguntas": [p],
                                                         "error": "", "url": "https://aules.edu.gva.es/fp/mod/quiz/review.php?attempt=9"}]}, "10")
        self.assertIn('class="op correcta"', pagina)
        self.assertIn('class="op tuya mala"', pagina)
        self.assertIn("Respuesta correcta:", pagina)
        self.assertIn("9,06", sin_etiquetas(pagina))

    def test_html_de_word_sin_cerrar_no_mete_las_respuestas_en_el_enunciado(self):
        html = ('<div class="que ordering complete"><div class="formulation"><div class="qtext"><div class="clearfix">'
                '<p>Ordena los pasos</p><div>caja de Word sin cerrar</div></div>'
                '<div class="ablock"><div class="answer ordering"><ul class="sortablelist"><li>Paso B</li><li>Paso A</li></ul></div></div>'
                '</div></div>')
        p = core.analizar_pregunta({"html": html, "type": "ordering", "mark": "0,20", "maxmark": 1})
        self.assertNotIn("Paso", p["enunciado"])
        self.assertEqual([o["texto"] for o in p["orden"]], ["Paso B", "Paso A"])

    def test_imagenes_solo_de_aules(self):
        sesion = {"base_url": "https://aules.edu.gva.es/fp", "token": "secreto", "username": "u"}
        guardar = core._guardar_imagen_revision(sesion, tempfile.gettempdir())
        with mock.patch.object(core.http, "get") as get:
            self.assertEqual(guardar("https://otra-web.com/pluginfile.php/1/a.jpg"), "")
            get.assert_not_called()  # el token nunca va a otra web


class RegistroFalso:
    """Un winreg de mentira, para probar el alta del enlace de Windows sin tocar el registro de verdad."""
    HKEY_CURRENT_USER, REG_SZ = "HKCU", 1

    class _Clave:
        def __init__(self, ruta):
            self.ruta = ruta

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def __init__(self):
        self.claves, self.valores, self.raices = set(), {}, set()

    def OpenKey(self, raiz, ruta):
        self.raices.add(raiz)
        if ruta not in self.claves:
            raise FileNotFoundError(ruta)
        return self._Clave(ruta)

    def CreateKey(self, raiz, ruta):
        self.raices.add(raiz)
        partes = ruta.split("\\")
        for i in range(1, len(partes) + 1):  # como Windows, crea también las claves de en medio
            self.claves.add("\\".join(partes[:i]))
        return self._Clave(ruta)

    def DeleteKey(self, raiz, ruta):
        self.raices.add(raiz)
        if ruta not in self.claves:
            raise FileNotFoundError(ruta)
        if any(c.startswith(ruta + "\\") for c in self.claves):
            raise PermissionError(ruta)  # como Windows: no borra una clave que aún tiene hijas
        self.claves.discard(ruta)
        for k in [k for k in self.valores if k[0] == ruta]:
            del self.valores[k]

    def SetValue(self, clave, sub, tipo, valor):
        self.valores[(clave.ruta, sub)] = valor

    def SetValueEx(self, clave, nombre, reservado, tipo, valor):
        self.valores[(clave.ruta, nombre)] = valor

    def QueryValue(self, clave, sub):
        return self.valores.get((clave.ruta, sub or ""), "")

    def QueryValueEx(self, clave, nombre):
        if (clave.ruta, nombre) not in self.valores:
            raise FileNotFoundError(nombre)
        return self.valores[(clave.ruta, nombre)], self.REG_SZ


class UACloud(unittest.TestCase):
    """Entrar en el Moodle de la Universidad de Alicante: usa el SSO de UACloud, no usuario y contraseña."""

    def setUp(self):
        self.carpeta = tempfile.mkdtemp(prefix="aules_ua_")
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        for parche in (mock.patch.object(core, "SESSION_PATH", os.path.join(self.carpeta, "session.json")),
                       mock.patch.object(core, "SSO_PENDIENTES_PATH", os.path.join(self.carpeta, "sso.json")),
                       mock.patch.object(core, "ESQUEMA_ANTERIOR_PATH", os.path.join(self.carpeta, "anterior.json")),
                       mock.patch.object(core, "ACCOUNTS_DIR", self.carpeta), mock.patch.object(core, "log")):
            parche.start()
            self.addCleanup(parche.stop)
        self.clave = max(interfaz.PORTALES_SSO)  # el curso actual
        self.base = interfaz.PORTALES[self.clave][1]

    def enlace(self, passport, token="TOKEN-de-prueba-1234567890", privado=None, base=None, esquema="moodlemobile"):
        """El enlace de vuelta que Moodle fabrica: base64(md5(sitio + passport) ::: token [::: token privado])."""
        firma = hashlib.md5(((base or self.base) + passport).encode()).hexdigest()
        crudo = ":::".join(x for x in (firma, token, privado) if x)
        return f"{esquema}://token={base64.b64encode(crudo.encode()).decode()}"

    def iniciar(self):
        ident, enlace = core.sso_iniciar(self.base)
        return ident, enlace, parse_qs(urlparse(enlace).query)["passport"][0]

    SITIO = {"username": "alu1", "fullname": "Ana Prueba García", "firstname": "Ana", "userid": 5}

    def test_cada_curso_tiene_su_carpeta(self):
        self.assertEqual(os.path.basename(core.carpeta({"username": "alu1", "base_url": self.base})), f"alu1@{self.clave}")
        vieja = {"username": "alu1", "base_url": "https://moodle2023-24.ua.es/moodle/"}
        self.assertEqual(os.path.basename(core.carpeta(vieja)), "alu1@ua2023")  # aunque ya no salga en la lista
        self.assertEqual(interfaz.nombre_portal("ua2023"), "Universidad de Alicante · 2023-24")
        self.assertEqual(interfaz.portal_de("https://aules.edu.gva.es/fp"), "fp")
        # Un dominio que solo lo parece no cuenta como de la UA.
        self.assertEqual(interfaz.portal_de("https://moodle2026-27.ua.es.otra-web.example/moodle"), "fp")

    def test_el_enlace_de_inicio_lleva_el_passport_y_el_esquema(self):
        ident, enlace, passport = self.iniciar()
        consulta = parse_qs(urlparse(enlace).query)
        self.assertTrue(enlace.startswith(f"{self.base}/admin/tool/mobile/launch.php?"))
        self.assertEqual((consulta["service"], consulta["urlscheme"]), (["moodle_mobile_app"], ["moodlemobile"]))
        self.assertRegex(passport, r"^[0-9a-f]{32}$")
        self.assertEqual(ident, core.sso_id(passport))
        self.assertNotEqual(self.iniciar()[2], passport)  # cada intento, un passport nuevo
        with self.assertRaises(core.LoginError):
            core.sso_iniciar("https://aules.edu.gva.es/fp")  # Aules (GVA) sigue entrando con usuario y contraseña

    def test_acepta_el_enlace_de_vuelta_una_sola_vez(self):
        ident, _, passport = self.iniciar()
        with mock.patch.object(core, "call_ws", return_value=self.SITIO) as ws:
            sesion, ident_vuelta = core.sso_completar(self.enlace(passport, token="MITOKEN-abcdefghij"))
            self.assertEqual(ident_vuelta, ident)
            self.assertEqual(ws.call_args[0], (self.base, "MITOKEN-abcdefghij", "core_webservice_get_site_info"))
            self.assertEqual((sesion["username"], sesion["token"], sesion["base_url"]), ("alu1", "MITOKEN-abcdefghij", self.base))
            self.assertEqual(core.load_session(), sesion)  # queda guardada, como con el inicio de sesión de siempre
            with self.assertRaisesRegex(core.LoginError, "ya ha caducado"):
                core.sso_completar(self.enlace(passport))  # el passport es de un solo uso

    def test_entiende_las_formas_en_que_llega_el_enlace(self):
        siteid = hashlib.md5(b"x").hexdigest()
        token = ">>>???>>>???"  # su base64 lleva «+» y «/»
        crudo = base64.b64encode(f"{siteid}:::{token}".encode()).decode()
        self.assertTrue("+" in crudo and "/" in crudo)
        formas = [f"moodlemobile://token={crudo}", f"cualquierapp://token={crudo}", f"  moodlemobile://token={crudo}\n",
                  f"moodlemobile://token={crudo.replace('+', ' ')}", f"moodlemobile://token={crudo.replace('=', '%3D').replace('/', '%2F')}",
                  f"moodlemobile://token={crudo.rstrip('=')}", f"moodlemobile://token={base64.b64encode(f'{siteid}:::{token}:::privado'.encode()).decode()}"]
        for forma in formas:
            self.assertEqual(core.sso_leer_enlace(forma), (siteid, token), forma)

    def test_rechaza_lo_que_no_es_de_un_intento_suyo(self):
        _, _, passport = self.iniciar()
        casos = {
            "basura": "https://moodle.example/?x=1",
            "base64 roto": "moodlemobile://token=" + "%%%@@@" * 8,
            "sin firma": "moodlemobile://token=" + base64.b64encode(b"hola:::mundo-token-largo-123").decode(),
            "passport de otro": self.enlace("0" * 32),
            "otro sitio": self.enlace(passport, base="https://moodle2020-21.ua.es/moodle"),
        }
        with mock.patch.object(core, "call_ws", side_effect=AssertionError("no debía contactar con Moodle")):
            for nombre, enlace in casos.items():
                with self.assertRaises(core.LoginError, msg=nombre):
                    core.sso_completar(enlace)
        self.assertIsNone(core.load_session())

    def test_un_intento_caducado_no_vale(self):
        _, _, passport = self.iniciar()
        with mock.patch.object(core, "SSO_CADUCA_SEGUNDOS", -1), mock.patch.object(core, "call_ws", side_effect=AssertionError):
            with self.assertRaisesRegex(core.LoginError, "caducado"):
                core.sso_completar(self.enlace(passport))

    def test_un_token_que_moodle_rechaza_no_deja_sesion(self):
        ident, _, passport = self.iniciar()
        with mock.patch.object(core, "call_ws", side_effect=core.SessionExpired("invalidtoken")):
            with self.assertRaises(core.LoginSsoError) as error:
                core.sso_completar(self.enlace(passport))
        self.assertEqual(error.exception.ident, ident)
        self.assertIsNone(core.load_session())

    CMD = r"Software\Classes\moodlemobile\shell\open\command"

    @staticmethod
    def poner(registro, esquema, comando):
        """Deja registrada otra aplicación para un esquema, como si ya estuviera instalada."""
        with registro.CreateKey("HKCU", rf"Software\Classes\{esquema}") as clave:
            registro.SetValue(clave, "", 1, "URL:Otra app")
            registro.SetValueEx(clave, "URL Protocol", 0, 1, "")
        with registro.CreateKey("HKCU", rf"Software\Classes\{esquema}\shell\open\command") as clave:
            registro.SetValue(clave, "", 1, comando)

    def test_el_enlace_de_windows_es_el_que_moodle_fuerza_y_solo_para_este_usuario(self):
        self.assertEqual(core.ESQUEMA_SSO, "moodlemobile")  # Moodle ignora el esquema que pida la app
        registro = RegistroFalso()
        self.assertTrue(core.sso_registrar_esquema(registro))
        comando = registro.valores[(self.CMD, "")]
        self.assertTrue(comando.endswith('servidor.py" --sso "%1"'), comando)
        self.assertEqual(registro.valores[(r"Software\Classes\moodlemobile", "URL Protocol")], "")
        self.assertEqual(registro.raices, {"HKCU"})  # nunca HKLM: no pide administrador
        self.assertFalse(core.sso_registrar_esquema(registro))  # ya estaba bien: no se vuelve a escribir
        self.assertFalse(os.path.exists(core.ESQUEMA_ANTERIOR_PATH))
        self.assertTrue(core.sso_quitar_esquema(registro))  # y al desinstalar no queda nada
        self.assertEqual([c for c in registro.claves if "moodlemobile" in c], [])

    def test_no_pisa_a_otra_aplicacion_sin_apuntarla_y_se_la_devuelve(self):
        registro = RegistroFalso()
        ajeno = r'"C:\Program Files\Moodle\Moodle.exe" "%1"'  # p. ej. la app de escritorio de Moodle
        self.poner(registro, "moodlemobile", ajeno)
        self.assertTrue(core.sso_registrar_esquema(registro))
        self.assertIn("--sso", registro.valores[(self.CMD, "")])
        self.assertTrue(os.path.exists(core.ESQUEMA_ANTERIOR_PATH))  # apuntada, para devolverla
        self.assertTrue(core.sso_quitar_esquema(registro))
        self.assertEqual(registro.valores[(self.CMD, "")], ajeno)  # el usuario recupera la suya
        self.assertEqual(registro.valores[(r"Software\Classes\moodlemobile", "")], "URL:Otra app")
        self.assertFalse(os.path.exists(core.ESQUEMA_ANTERIOR_PATH))
        self.assertFalse(core.sso_quitar_esquema(registro))  # lo que queda no es nuestro: no se toca
        self.assertEqual(registro.valores[(self.CMD, "")], ajeno)

    def test_limpia_el_aulesapp_de_la_1_10_0_solo_si_es_nuestro(self):
        nuestro = RegistroFalso()
        self.poner(nuestro, "aulesapp", core.comando_esquema())
        core.sso_registrar_esquema(nuestro)
        self.assertNotIn(r"Software\Classes\aulesapp", nuestro.claves)
        ajeno = RegistroFalso()
        self.poner(ajeno, "aulesapp", r'"C:\Otra\app.exe" "%1"')
        core.sso_registrar_esquema(ajeno)
        self.assertIn(r"Software\Classes\aulesapp", ajeno.claves)  # no era nuestro: se deja como estaba

    def test_la_espera_ofrece_una_salida_que_vale_con_cualquier_esquema(self):
        inicio = "https://moodle.example/admin/tool/mobile/launch.php?service=moodle_mobile_app&passport=" + "a" * 32
        alternativo = core.sso_enlace_alternativo(inicio)
        self.assertTrue(alternativo.endswith("&confirmed=1"))
        pagina = interfaz.render_sso_espera("Universidad de Alicante", "id1", inicio, "", alternativo)
        self.assertIn("confirmed=1", pagina)
        self.assertIn("Copiar dirección del enlace", pagina)
        self.assertNotIn("este otro enlace", interfaz.render_sso_espera("UA", "id1", inicio))  # sin alternativa, no se menciona

    def test_lo_que_es_solo_de_la_gva_se_apaga_fuera_de_aules(self):
        for url in ("https://aules.edu.gva.es/fp", "https://aules.edu.gva.es/eso03", None, ""):
            self.assertTrue(core.es_gva(url), url)
        self.assertFalse(core.es_gva(self.base))

        class Ctx:
            course_names = {1: "Redes"}

            def __init__(self, base_url):
                self.base_url = base_url

            def ws(self, funcion, params=None):
                if funcion == "core_course_get_courses_by_field":
                    return {"courses": [{"id": 1, "fullname": "Redes", "summary": "", "contacts": [{"id": 7}]}]}
                return [{"id": 7, "fullname": "Ana Profe García", "firstname": "Ana", "lastname": "Profe García", "email": ""}]

        gva = core.fetch_teachers(Ctx("https://aules.edu.gva.es/fp"), [{"id": 1}], {})
        ua = core.fetch_teachers(Ctx(self.base), [{"id": 1}], {})
        self.assertTrue(gva["profesores"][0]["email_guess"].endswith("@edu.gva.es"))
        self.assertEqual(ua["profesores"][0]["email_guess"], "")  # el formato de correo de la GVA no vale en la UA

    def test_la_pagina_de_entrada_ofrece_uacloud(self):
        pagina = interfaz.render_login(portal=self.clave)
        self.assertIn(f'<option value="{self.clave}" selected data-sso="1">', pagina)
        self.assertIn('formaction="/login/sso"', pagina)
        self.assertIn('<option value="fp">FP presencial</option>', pagina)  # las de Aules no cambian
        espera = interfaz.render_sso_espera("Universidad de Alicante", "abc123", "https://x.example/launch.php?a=1&b=2")
        self.assertIn("a=1&amp;b=2", espera)
        self.assertIn('action="/login/sso/pegar"', espera)
        self.assertIn('"abc123"', espera)


class UACloudServidor(unittest.TestCase):
    """El inicio de sesión de punta a punta con el servidor de la app de verdad y un Moodle de mentira."""

    def setUp(self):
        import servidor
        self.servidor = servidor
        self.carpeta = tempfile.mkdtemp(prefix="aules_ua_srv_")
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        self.registrar, self.revisar = mock.Mock(), mock.Mock()
        self.http = servidor.ThreadingHTTPServer(("127.0.0.1", 0), servidor.Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        parches = [
            mock.patch.object(core, "SESSION_PATH", os.path.join(self.carpeta, "session.json")),
            mock.patch.object(core, "SSO_PENDIENTES_PATH", os.path.join(self.carpeta, "sso.json")),
            mock.patch.object(core, "ACCOUNTS_DIR", self.carpeta), mock.patch.object(core, "log"),
            mock.patch.object(ia, "AJUSTES_PATH", os.path.join(self.carpeta, "ajustes.json")),
            mock.patch.object(core, "sso_registrar_esquema", self.registrar),  # sin tocar el registro de Windows
            mock.patch.object(servidor, "revisar_en_segundo_plano", self.revisar),
            mock.patch.object(servidor, "PORT", self.http.server_port),
            mock.patch.object(servidor, "ALLOWED_HOSTS", {f"127.0.0.1:{self.http.server_port}"}),
            mock.patch.object(servidor, "ALLOWED_ORIGINS", {self.url}),
            mock.patch.object(core, "call_ws", return_value=UACloud.SITIO),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        hilo = threading.Thread(target=self.http.serve_forever, daemon=True)
        hilo.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.clave = max(interfaz.PORTALES_SSO)
        self.base = interfaz.PORTALES[self.clave][1]
        self.web = requests.Session()

    def empezar(self):
        pagina = self.web.post(f"{self.url}/login/sso", data={"portal": self.clave}, headers={"Origin": self.url})
        self.assertEqual(pagina.status_code, 200)
        enlace = html.unescape(re.search(r'class="btn-primary sso-abrir" href="([^"]+)"', pagina.text).group(1))
        passport = parse_qs(urlparse(enlace).query)["passport"][0]
        return pagina, core.sso_id(passport), passport

    def vuelta(self, passport, token="TOKEN-de-prueba-1234567890"):
        firma = hashlib.md5((self.base + passport).encode()).hexdigest()
        return "moodlemobile://token=" + base64.b64encode(f"{firma}:::{token}".encode()).decode()

    def estado(self, ident):
        return self.web.get(f"{self.url}/login/sso/estado?id={ident}").json()["estado"]

    def test_de_punta_a_punta(self):
        pagina, ident, passport = self.empezar()
        self.assertIn("Abrir UACloud", pagina.text)
        self.assertIn("confirmed=1", pagina.text)  # la salida de emergencia, para copiar el enlace
        self.registrar.assert_called_once()  # se dio de alta el enlace de Windows antes de abrir nada
        self.assertEqual(self.estado(ident), "esperando")
        self.servidor.modo_callback_sso(self.vuelta(passport))  # lo que ejecuta Windows con el enlace de vuelta
        self.assertEqual(self.estado(ident), "ok")
        self.assertEqual(core.load_session()["token"], "TOKEN-de-prueba-1234567890")
        self.revisar.assert_called_once()  # y empieza a leer Moodle

    def test_pegar_el_enlace_si_el_navegador_no_vuelve(self):
        _, ident, passport = self.empezar()
        respuesta = self.web.post(f"{self.url}/login/sso/pegar", data={"id": ident, "enlace": self.vuelta(passport)},
                                  headers={"Origin": self.url}, allow_redirects=False)
        self.assertEqual((respuesta.status_code, respuesta.headers["Location"]), (303, "/"))
        self.assertEqual(self.estado(ident), "ok")
        mal = self.web.post(f"{self.url}/login/sso/pegar", data={"id": ident, "enlace": "esto no es un enlace"}, headers={"Origin": self.url})
        self.assertEqual(mal.status_code, 400)
        self.assertIn("moodlemobile://token=", mal.text)

    def test_un_enlace_falso_no_estropea_el_intento_en_marcha(self):
        _, ident, passport = self.empezar()
        self.servidor.modo_callback_sso("moodlemobile://token=" + base64.b64encode(b"cualquier-cosa:::sin-firma-valida-12345").decode())
        self.assertEqual(self.estado(ident), "esperando")
        self.assertIsNone(core.load_session())
        self.servidor.modo_callback_sso(self.vuelta(passport))  # y el bueno sigue funcionando
        self.assertEqual(self.estado(ident), "ok")

    def test_solo_la_propia_app_puede_entregar_el_enlace(self):
        _, _, passport = self.empezar()
        for cabeceras in ({"Origin": "https://web-ajena.example"}, {}):
            r = self.web.post(f"{self.url}/api/sso/token", json={"enlace": self.vuelta(passport)}, headers=cabeceras)
            self.assertEqual(r.status_code, 403, cabeceras)
        self.assertIsNone(core.load_session())

    def test_el_formulario_de_usuario_y_contrasena_no_vale_para_la_ua(self):
        with mock.patch.object(core, "login", side_effect=AssertionError("no debía intentar entrar con contraseña")):
            r = self.web.post(f"{self.url}/login", data={"portal": self.clave, "username": "alu1", "password": "x"},
                              headers={"Origin": self.url})
        self.assertEqual(r.status_code, 400)
        self.assertIn("UACloud", r.text)


if __name__ == "__main__":
    unittest.main()
