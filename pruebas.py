"""Pruebas de las partes delicadas de la app, con casos reales que ya han dado problemas.

Uso:   python -m unittest pruebas          (publicar.py las pasa solo antes de subir nada)
No se conectan a Aules ni tocan tus datos: todo se hace en carpetas temporales.
"""
import os
import re
import shutil
import tempfile
import time
import unittest
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
