"""Lee el horario de clases y el calendario escolar a partir del texto de sus PDF.
Solo transforma datos: no llama a Aules ni toca el disco."""
import re
import unicodedata
from datetime import date


MESES_CALENDARIO = {
    "septiembre": 9, "setembre": 9, "octubre": 10, "noviembre": 11, "novembre": 11, "diciembre": 12, "desembre": 12,
    "enero": 1, "gener": 1, "febrero": 2, "febrer": 2, "marzo": 3, "marc": 3, "abril": 4, "mayo": 5, "maig": 5,
    "junio": 6, "juny": 6, "julio": 7, "juliol": 7, "agosto": 8, "agost": 8,
}

LEYENDA_CALENDARIO = (("festiu", "festivo"), ("festivo", "festivo"), ("vacaciones", "vacaciones"), ("vacances", "vacaciones"),
                      ("consejo", "no lectivo"), ("consell", "no lectivo"), ("no lectivo", "no lectivo"), ("no lectiu", "no lectivo"))


def calendario_desde_pdf(ruta):
    """Lee un calendario escolar en PDF donde los días sin clase van coloreados según una leyenda.

    Devuelve {"2026-10-12": "festivo", ...} solo con días de lunes a viernes."""
    from pypdf import PdfReader
    from pypdf.generic import ContentStream

    lector = PdfReader(ruta)
    textos_pdf = []
    resultado = {}
    for pagina in lector.pages:
        mitad = float(pagina.mediabox.width) / 2
        textos = []

        def visitor(texto, cm, tm, _fd, _fs):
            texto = (texto or "").strip()
            if texto:
                textos.append((texto, tm[4] * cm[0] + tm[5] * cm[2] + cm[4], tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))

        pagina.extract_text(visitor_text=visitor)
        textos_pdf += [t for t, _, _ in textos]

        # Rectángulos rellenos con un color de verdad (no gris/blanco/negro).
        rects, color, pendientes, pila = [], None, [], []
        for operandos, op in ContentStream(pagina.get_contents(), lector).operations:
            # q/Q guardan y restauran el color: sin la pila, el color del texto "tapa" el del recuadro.
            if op == b"q":
                pila.append(color)
            elif op == b"Q":
                color = pila.pop() if pila else None
            elif op == b"rg":
                color = tuple(float(v) for v in operandos)
            elif op == b"g":
                color = (float(operandos[0]),) * 3
            elif op == b"k":
                c, m, y, k = (float(v) for v in operandos)
                color = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
            elif op == b"re":
                x, y, w, h = (float(v) for v in operandos)
                pendientes.append((min(x, x + w), min(y, y + h), max(x, x + w), max(y, y + h)))
            elif op in (b"f", b"f*", b"F", b"B", b"B*", b"b", b"b*"):
                if color and max(color) - min(color) > 0.25:
                    rects += [(color, r) for r in pendientes]
                pendientes = []
            elif op in (b"n", b"S", b"s"):
                pendientes = []

        def color_en(x, y):
            for c, (x0, y0, x1, y1) in reversed(rects):
                if x0 <= x <= x1 and y0 <= y <= y1:
                    return c
            return None

        # Leyenda: el cuadro de color que hay justo a la izquierda de "FESTIVO", "VACACIONES"…
        leyenda = []
        for texto, x, y in textos:
            normal = " ".join(_letras(texto))
            tipo = next((t for clave, t in LEYENDA_CALENDARIO if clave in normal), None)
            if not tipo:
                continue
            cerca = [(x - x1, c) for c, (x0, y0, x1, y1) in rects if x1 <= x + 3 and x - x1 < 40 and y0 - 4 <= y <= y1 + 4]
            if cerca:
                leyenda.append((min(cerca)[1], tipo))
        if not leyenda:
            continue

        titulos = []
        for texto, x, y in textos:
            primera = (_letras(texto) or [""])[0]
            if primera in MESES_CALENDARIO:
                titulos.append((MESES_CALENDARIO[primera], x < mitad, y))

        anyos = re.search(r"(20\d\d)\D{1,5}(20\d\d)", " ".join(t for t, _, _ in textos))
        for texto, x, y in textos:
            if not re.fullmatch(r"\d{1,2}", texto):
                continue
            encima = [(ty - y, mes) for mes, izquierda, ty in titulos if izquierda == (x < mitad) and ty > y]
            color = color_en(x + 1.5, y + 2)
            if not encima or not color:
                continue
            mes = min(encima)[1]
            distancia, tipo = min((sum((a - b) ** 2 for a, b in zip(color, c)) ** 0.5, t) for c, t in leyenda)
            if distancia > 0.35:
                continue
            if anyos:
                anyo = int(anyos.group(1)) if mes >= 8 else int(anyos.group(2))
            else:
                hoy = date.today()
                anyo = hoy.year + (1 if mes < 8 <= hoy.month else 0) - (1 if mes >= 8 > hoy.month else 0)
            try:
                dia = date(anyo, mes, int(texto))
            except ValueError:
                continue
            if dia.weekday() < 5:
                resultado[dia.isoformat()] = tipo
    return dict(sorted(resultado.items()))


def _letras(texto):
    texto = "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower()) if not unicodedata.combining(c))
    return re.findall(r"[a-z]+", texto)


DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

RE_HORA_EXACTA = re.compile(r"\[\s*(\d{1,2}[:.]\d{2})\s*/\s*(\d{1,2}[:.]\d{2})\s*\]")


def normalizar_hora(hora):
    return hora.replace(".", ":").rjust(5, "0")

RE_HORA = re.compile(r"^\d{1,2}[:.]\d{2}$")

RE_AULA = re.compile(r"\(?\s*(AULA[^)]*)\)?", re.I)


def horario_desde_pdf(ruta):
    """Saca del PDF las franjas horarias (exactas) y una propuesta de asignatura por celda.

    Las celdas combinadas del PDF hacen que el nombre de la asignatura sea solo una sugerencia:
    las horas son fiables, el texto hay que revisarlo.
    """
    from pypdf import PdfReader

    trozos = []

    def visitante(texto, cm, tm, fuente, tam):
        t = (texto or "").strip()
        if t:
            trozos.append({"y": round(tm[5], 1), "x": round(tm[4], 1), "t": t})

    PdfReader(ruta).pages[0].extract_text(visitor_text=visitante)

    por_y = {}
    for f in trozos:
        por_y.setdefault(f["y"], []).append(f)
    cabecera, mejor = None, 0
    for y, fila in por_y.items():
        n = sum(1 for f in fila if f["t"].strip().rstrip(":") in DIAS_SEMANA)
        if n > mejor:
            cabecera, mejor = y, n
    if not cabecera:
        raise RuntimeError("No encuentro la fila de días en el PDF del horario.")
    columnas = sorted((f["x"], f["t"].strip().rstrip(":")) for f in por_y[cabecera] if f["t"].strip().rstrip(":") in DIAS_SEMANA)

    horas = [f for f in trozos if RE_HORA.match(f["t"]) and f["y"] < cabecera]
    grupos_x = []
    for x in sorted({round(f["x"]) for f in horas}):
        if grupos_x and x - grupos_x[-1][-1] <= 12:
            grupos_x[-1].append(x)
        else:
            grupos_x.append([x])
    columnas_hora = [sum(g) / len(g) for g in grupos_x]

    manda = {}
    for i, xh in enumerate(columnas_hora):
        siguiente = columnas_hora[i + 1] if i + 1 < len(columnas_hora) else 10 ** 6
        for x, dia in columnas:
            if xh < x < siguiente:
                manda[dia] = xh

    franjas_col = {}
    for xh in columnas_hora:
        propias = sorted((f for f in horas if abs(f["x"] - xh) <= 12), key=lambda f: -f["y"])
        pares = []
        for i in range(0, len(propias) - 1, 2):
            pares.append({
                "inicio": propias[i]["t"].replace(".", ":").rjust(5, "0"),
                "fin": propias[i + 1]["t"].replace(".", ":").rjust(5, "0"),
                "y_top": propias[i]["y"],
                "y_fin": propias[i + 1]["y"],
            })
        franjas_col[xh] = pares

    limites = []
    for i, (x, dia) in enumerate(columnas):
        izq = (columnas[i - 1][0] + x) / 2 if i else x - 120
        der = (columnas[i + 1][0] + x) / 2 if i + 1 < len(columnas) else x + 140
        limites.append((izq, der, dia))

    # Cada fila del horario va desde su etiqueta de hora hasta la de la fila siguiente.
    for pares in franjas_col.values():
        alturas = [pares[i]["y_top"] - pares[i + 1]["y_top"] for i in range(len(pares) - 1)]
        tipica = sorted(alturas)[len(alturas) // 2] if alturas else 52
        for i, franja in enumerate(pares):
            franja["y_bottom"] = pares[i + 1]["y_top"] if i + 1 < len(pares) else franja["y_top"] - tipica

    # La columna de horas de un día no siempre es la de su izquierda (en septiembre el jueves usa
    # las del lunes). El "DESCANSO" escrito en la columna del día delata qué rejilla le toca.
    for izq, der, dia in limites:
        descansos = [f["y"] for f in trozos if izq <= f["x"] < der and f["y"] < cabecera and "DESCANSO" in f["t"].upper()]
        if not descansos:
            continue
        encajan = [
            xh for xh, pares in franjas_col.items()
            if any(es_descanso(p) and p["y_bottom"] < descansos[0] <= p["y_top"] + 6 for p in pares)
        ]
        # Varias rejillas pueden tener el recreo a la misma altura: entonces manda la cercanía.
        if encajan and manda.get(dia) not in encajan:
            centro = (izq + der) / 2
            manda[dia] = min(encajan, key=lambda xh: abs(xh - centro))

    # Debajo de la última fila está el pie del PDF (listas de profesores, fechas…): se descarta.
    suelo = min((p[-1]["y_bottom"] for p in franjas_col.values() if p), default=0) - 4

    por_dia = {d: [] for _, _, d in limites}
    for f in trozos:
        if f["y"] >= cabecera or f["y"] < suelo or RE_HORA.match(f["t"]):
            continue
        dia = next((d for izq, der, d in limites if izq <= f["x"] < der), None)
        if dia:
            por_dia[dia].append(f)

    resultado = {d: [] for d in DIAS_SEMANA}
    for dia in DIAS_SEMANA:
        franjas = franjas_col.get(manda.get(dia), [])
        if not franjas:
            continue

        # Una celda acaba en su línea de aula (o en DESCANSO); si no la hay, en un hueco grande.
        lineas = sorted(por_dia.get(dia, []), key=lambda f: -f["y"])
        celdas, actual = [], []
        for i, f in enumerate(lineas):
            # Una hora entre corchetes pegada a la línea de aula anterior pertenece a esa misma casilla.
            if not actual and RE_HORA_EXACTA.search(f["t"]) and celdas and celdas[-1][-1]["y"] - f["y"] <= 12:
                celdas[-1].append(f)
                continue
            actual.append(f)
            hueco = actual[-1]["y"] - lineas[i + 1]["y"] if i + 1 < len(lineas) else 10 ** 6
            if RE_AULA.search(f["t"]) or "DESCANSO" in f["t"].upper() or hueco > 25:
                celdas.append(actual)
                actual = []
        if actual:
            celdas.append(actual)

        contenido = []
        for celda in celdas:
            texto = re.sub(r"\s+", " ", " ".join(p["t"] for p in sorted(celda, key=lambda f: (-f["y"], f["x"])))).strip(" .·")
            aula = ""
            encontrada = RE_AULA.search(texto)
            if encontrada:
                aula = encontrada.group(1).strip().rstrip(").")
                texto = RE_AULA.sub("", texto).strip(" .·")
            # Las clases fuera de la rejilla normal llevan su hora exacta entre corchetes: "[13:15 / 14:10]".
            exacta = RE_HORA_EXACTA.search(texto)
            texto = re.sub(r"\[[^\]]*\]", "", texto).strip(" .·")
            profesor = ""
            # En el horario del curso las iniciales del profesor van al final del nombre.
            iniciales = re.search(r"\s([A-ZÑ]{2,5})\d?$", texto)
            if iniciales:
                profesor = iniciales.group(1)
                texto = texto[: iniciales.start()].strip(" .·")
            texto = re.sub(r"\s\d$", "", texto).strip(" .·")
            if texto and not re.match(r"^(lectivas|materia|profesores|\d{2}/\d{2}/\d{4})", texto, re.I):
                # Las anotaciones sueltas ("[13:15 / 14:10]", números) no forman parte del bloque centrado.
                utiles = [p["y"] for p in celda if not re.fullmatch(r"\[.*\]|\d+", p["t"].strip())] or [p["y"] for p in celda]
                contenido.append({"arriba": celda[0]["y"] + 6, "abajo": celda[-1]["y"] - 6,
                                  "centro": (max(utiles) + min(utiles)) / 2,
                                  "texto": texto, "aula": aula, "profesor": profesor,
                                  "exacta": (normalizar_hora(exacta.group(1)), normalizar_hora(exacta.group(2))) if exacta else None})

        # Las celdas "DESCANSO" no siempre están en la columna de su día; los descansos se sacan de las horas.
        contenido = [c for c in contenido if not re.fullmatch(r"(?i)descanso|recreo|pati|esbarjo", c["texto"])]

        # En el PDF, el texto va centrado en vertical dentro de su casilla, y la hora de cada franja
        # también. Una asignatura de dos franjas seguidas (p.ej. 8:00-9:20) queda centrada entre ambas.
        # Se prueba cada tramo de 1 a 3 franjas y se elige el que tiene el centro más parecido al texto.
        centros = [(fr["y_top"] + fr["y_fin"]) / 2 for fr in franjas]

        # Las casillas con hora exacta no se encajan: van tal cual y bloquean las franjas que pisan.
        exactas = [c for c in contenido if c["exacta"]]
        contenido = [c for c in contenido if not c["exacta"]]
        pisadas = set()
        for c in exactas:
            ini, fin = a_minutos(c["exacta"][0]), a_minutos(c["exacta"][1])
            pisadas |= {k for k, fr in enumerate(franjas) if a_minutos(fr["inicio"]) < fin and a_minutos(fr["fin"]) > ini}
            resultado[dia].append({"inicio": c["exacta"][0], "fin": c["exacta"][1],
                                   "asignatura": c["texto"], "aula": c["aula"], "profesor": c["profesor"]})

        propuestas = []
        for celda in contenido:
            for k in range(len(franjas)):
                for j in range(k, min(k + 3, len(franjas))):
                    # Una clase larga solo abarca franjas seguidas: ni descansos ni huecos entre medias.
                    if es_descanso(franjas[j]) or (j > k and franjas[j]["inicio"] != franjas[j - 1]["fin"]):
                        break
                    # Pequeña penalización por franja extra: ante la duda, la casilla más corta.
                    error = abs(celda["centro"] - (centros[k] + centros[j]) / 2) + 4 * (j - k)
                    propuestas.append((error, k, j, celda))
        # Primero las casillas que encajan de lleno en una sola franja; luego el resto por precisión.
        propuestas.sort(key=lambda p: (not (p[1] == p[2] and p[0] <= 8), p[0]))

        tramos, ocupadas, colocadas = {}, set(pisadas), set()
        for error, k, j, celda in propuestas:
            filas = set(range(k, j + 1))
            if error > 30 or id(celda) in colocadas or filas & ocupadas:
                continue
            tramos[k] = (j, celda)
            ocupadas |= filas
            colocadas.add(id(celda))

        i = 0
        while i < len(franjas):
            if es_descanso(franjas[i]):
                resultado[dia].append({"inicio": franjas[i]["inicio"], "fin": franjas[i]["fin"],
                                       "asignatura": "DESCANSO", "aula": "", "profesor": ""})
                i += 1
                continue
            if i not in tramos:
                i += 1
                continue
            j, celda = tramos[i]
            resultado[dia].append({
                "inicio": franjas[i]["inicio"],
                "fin": franjas[j]["fin"],
                "asignatura": celda["texto"],
                "aula": celda["aula"],
                "profesor": celda.get("profesor", ""),
            })
            i = j + 1
        resultado[dia].sort(key=lambda f: f["inicio"])
        resultado[dia] = rellenar_descansos(resultado[dia])

    # El recreo es común a toda la semana: si un día tiene hora libre justo antes, también lo lleva.
    recreos = {(f["inicio"], f["fin"]) for franjas in resultado.values() for f in franjas if f["asignatura"] == "DESCANSO"}
    for dia, franjas in resultado.items():
        for inicio, fin in recreos:
            if any(f["inicio"] == inicio and f["fin"] == fin for f in franjas):
                continue
            ocupado = any(a_minutos(f["inicio"]) < a_minutos(fin) and a_minutos(f["fin"]) > a_minutos(inicio) for f in franjas)
            antes = any(a_minutos(f["fin"]) <= a_minutos(inicio) for f in franjas)
            despues = any(a_minutos(f["inicio"]) >= a_minutos(fin) for f in franjas)
            if not ocupado and antes and despues:
                franjas.append({"inicio": inicio, "fin": fin, "asignatura": "DESCANSO", "aula": "", "profesor": ""})
        franjas.sort(key=lambda f: f["inicio"])
    return resultado


DESCANSO_MAX_MIN = 30


def a_minutos(hora):
    try:
        h, m = hora.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return 0


def es_descanso(franja):
    duracion = a_minutos(franja["fin"]) - a_minutos(franja["inicio"])
    return 0 < duracion <= DESCANSO_MAX_MIN


def rellenar_descansos(franjas):
    """Un hueco corto entre dos clases es un descanso aunque el PDF no lo escriba."""
    resultado = []
    for actual in franjas:
        if resultado:
            anterior = resultado[-1]
            hueco = a_minutos(actual["inicio"]) - a_minutos(anterior["fin"])
            if 0 < hueco <= DESCANSO_MAX_MIN and "DESCANSO" not in (anterior["asignatura"], actual["asignatura"]):
                resultado.append({"inicio": anterior["fin"], "fin": actual["inicio"],
                                  "asignatura": "DESCANSO", "aula": "", "profesor": ""})
        resultado.append(actual)
    # Un descanso al principio o al final del día no tiene sentido: sería un hueco sin clases.
    while resultado and resultado[0]["asignatura"] == "DESCANSO":
        resultado.pop(0)
    while resultado and resultado[-1]["asignatura"] == "DESCANSO":
        resultado.pop()
    return resultado
