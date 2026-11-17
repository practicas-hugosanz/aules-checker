"""Convierte el HTML de la revisión de un cuestionario de Aules en datos: el enunciado, las opciones,
lo que respondiste y la respuesta correcta. Solo transforma datos: no llama a Aules ni toca el disco."""
import json
import re
from html.parser import HTMLParser


_ETIQUETAS_VACIAS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
                     "track", "wbr"}

_BLOQUES = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "pre", "blockquote"}

# Lo que solo leen los lectores de pantalla, y la letra de cada opción (va aparte).
_OCULTAS = {"accesshide", "visually-hidden", "sr-only", "answernumber"}

# La zona de respuesta nunca es parte del enunciado. Hace falta saltarla porque el HTML que pegan los profes desde Word
# a veces deja una caja sin cerrar y entonces, para el lector, las opciones quedan «dentro» del enunciado.
_ZONA_RESPUESTA = {"ablock", "ddarea", "outcome", "im-controls"}

RE_CORRECTA = re.compile(r"^\s*(la respuesta correcta es|las respuestas correctas son|the correct answers? (is|are))\s*:\s*", re.I)

COMENTARIOS_OBVIOS = {"respuesta correcta", "respuesta incorrecta", "respuesta parcialmente correcta"}


class _Nodo:
    __slots__ = ("tag", "attrs", "hijos", "padre")

    def __init__(self, tag, attrs, padre):
        self.tag, self.attrs, self.hijos, self.padre = tag, dict(attrs), [], padre

    def clases(self):
        return set((self.attrs.get("class") or "").split())

    def todos(self, clase=None, tag=None):
        for h in self.hijos:
            if isinstance(h, _Nodo):
                if (clase is None or clase in h.clases()) and (tag is None or h.tag == tag):
                    yield h
                yield from h.todos(clase, tag)

    def uno(self, clase=None, tag=None):
        return next(self.todos(clase, tag), None)


class _LectorHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = self.actual = _Nodo("raiz", {}, None)

    def handle_starttag(self, tag, attrs):
        nodo = _Nodo(tag, attrs, self.actual)
        self.actual.hijos.append(nodo)
        if tag not in _ETIQUETAS_VACIAS:
            self.actual = nodo

    def handle_startendtag(self, tag, attrs):
        self.actual.hijos.append(_Nodo(tag, attrs, self.actual))

    def handle_endtag(self, tag):
        nodo = self.actual
        while nodo is not self.raiz and nodo.tag != tag:
            nodo = nodo.padre
        if nodo is not self.raiz:
            self.actual = nodo.padre

    def handle_data(self, datos):
        self.actual.hijos.append(datos)


def _arbol_html(codigo):
    lector = _LectorHTML()
    lector.feed(codigo or "")
    lector.close()
    return lector.raiz


def _texto_html(nodo):
    """El texto de un trozo de HTML, con saltos de línea donde había párrafos."""
    if nodo is None:
        return ""
    trozos = []

    def recorrer(n):
        for h in n.hijos:
            if isinstance(h, str):
                trozos.append(h)
            elif h.tag in ("script", "style") or h.clases() & (_OCULTAS | _ZONA_RESPUESTA):
                continue
            elif h.tag == "br":
                trozos.append("\n")
            else:
                bloque = h.tag in _BLOQUES
                trozos.append("\n• " if h.tag == "li" else "\n" if bloque else "")
                recorrer(h)
                trozos.append("\n" if bloque else "")

    recorrer(nodo)
    texto = re.sub(r"[ \t\r\f\v]+", " ", "".join(trozos).replace("\xa0", " "))
    texto = re.sub(r" *\n *", "\n", texto)
    texto = re.sub(r"•\n+", "• ", texto)
    # Cada párrafo de Word dejaba una línea en blanco: en una pregunta se lee mejor línea a línea.
    return re.sub(r"\n{2,}", "\n", texto).strip()


def _imagenes_html(nodo):
    imagenes = []

    def recorrer(n):
        for h in n.hijos:
            if isinstance(h, _Nodo) and not h.clases() & _ZONA_RESPUESTA:
                if h.tag == "img" and "pluginfile.php" in (h.attrs.get("src") or ""):
                    imagenes.append(h.attrs["src"])
                recorrer(h)

    if nodo is not None:
        recorrer(nodo)
    return imagenes


def _normal(texto):
    return re.sub(r"\s+", " ", texto or "").strip().lower()


def analizar_pregunta(pregunta, guardar_imagen=lambda url: ""):
    """Una pregunta de la revisión de Aules, en datos: enunciado, opciones, lo que respondiste y la correcta."""
    raiz = _arbol_html(pregunta.get("html"))
    que = raiz.uno("que") or raiz
    formulacion = que.uno("formulation") or que
    qtext = formulacion.uno("qtext")
    estado = (pregunta.get("stateclass") or "").strip()
    if not estado:
        estado = next((c for c in ("correct", "partiallycorrect", "incorrect", "notanswered") if c in que.clases()), "")
    maximo = pregunta.get("maxmark")
    datos = {
        "numero": str(pregunta.get("questionnumber") or pregunta.get("number") or ""),
        "tipo": pregunta.get("type") or "",
        "estado": estado,
        "estado_texto": (pregunta.get("status") or "").strip(),
        "nota": str(pregunta.get("mark") or "").strip(),
        "max": _numero(float(maximo)) if maximo not in (None, "") else "",
        "enunciado": _texto_html(qtext),
        "imagenes": [r for r in map(guardar_imagen, _imagenes_html(qtext)) if r],
        "opciones": [], "orden": [], "zonas": [], "fondo": "", "tu_respuesta": "", "correcta": "", "comentario": "",
    }

    # Tipo test (una o varias respuestas) y verdadero/falso.
    respuesta = formulacion.uno("answer")
    unica = True
    if respuesta is not None:
        for fila in respuesta.todos():
            clases = fila.clases()
            if not clases & {"r0", "r1"}:
                continue
            entrada = fila.uno(tag="input")
            unica = unica and (entrada is None or entrada.attrs.get("type") != "checkbox")
            letra = fila.uno("answernumber")
            acierto = next((c for c in ("correct", "partiallycorrect", "incorrect") if c in clases), "")
            datos["opciones"].append({
                "letra": _texto_html(letra).rstrip(". ") if letra is not None else "",
                "texto": _texto_html(fila),
                "imagenes": [r for r in map(guardar_imagen, _imagenes_html(fila)) if r],
                "marcada": entrada is not None and "checked" in entrada.attrs,
                "acierto": acierto,
                # Una opción marcada que Aules da por buena es una de las correctas.
                "es_correcta": entrada is not None and "checked" in entrada.attrs and acierto == "correct",
            })

    # Ordenar: los elementos en el orden en que los dejaste.
    for lista in formulacion.todos("sortablelist"):
        for li in (h for h in lista.hijos if isinstance(h, _Nodo) and h.tag == "li"):
            acierto = next((c for c in ("correct", "partiallycorrect", "incorrect") if c in li.clases()), "")
            datos["orden"].append({"texto": _texto_html(li), "acierto": acierto})

    # Arrastrar a una imagen: la imagen de fondo y lo que pusiste en cada zona.
    area = formulacion.uno("ddarea")
    if area is not None:
        fondo = area.uno("dropbackground")
        datos["fondo"] = guardar_imagen(fondo.attrs.get("src") or "") if fondo is not None else ""
        etiquetas = {}
        for n in area.todos("draghome"):
            clases = n.clases()
            grupo = next((c[5:] for c in clases if c.startswith("group") and c[5:].isdigit()), "1")
            numero = next((c[6:] for c in clases if c.startswith("choice") and c[6:].isdigit()), "")
            etiquetas.setdefault((grupo, numero), _texto_html(n))
        zonas = area.uno("dropzones")
        try:
            sitios = json.loads(zonas.attrs.get("data-place-info") or "{}") if zonas is not None else {}
        except ValueError:
            sitios = {}
        valores = {n.attrs.get("name"): n.attrs.get("value") for n in que.todos(tag="input")}
        for sitio in sitios.values():
            elegido = str(valores.get(sitio.get("fieldname")) or "")
            xy = sitio.get("xy") or [0, 0]
            datos["zonas"].append({
                "n": str(sitio.get("no") or ""),
                "x": int(float(xy[0])), "y": int(float(xy[1])),
                "texto": etiquetas.get((str(sitio.get("group") or "1"), elegido), "") if elegido not in ("", "0") else "",
            })

    # Otros tipos (respuesta corta, numérica, emparejar, rellenar huecos…): lo que escribiste o elegiste, como texto.
    if not (datos["opciones"] or datos["orden"] or datos["zonas"]):
        escritas = [n.attrs.get("value") or "" for n in formulacion.todos(tag="input") if n.attrs.get("type") == "text"]
        elegidas = []
        for desplegable in formulacion.todos(tag="select"):
            opcion = next((o for o in desplegable.todos(tag="option") if "selected" in o.attrs), None)
            if opcion is not None and _texto_html(opcion):
                elegidas.append(_texto_html(opcion))
        textos = [_texto_html(n) for n in formulacion.todos("qtype_essay_response")]
        datos["tu_respuesta"] = "\n".join(t for t in escritas + elegidas + textos if t.strip())

    derecha = que.uno("rightanswer")
    if derecha is not None:
        datos["correcta"] = RE_CORRECTA.sub("", _texto_html(derecha))
        correcta = _normal(datos["correcta"])
        for op in datos["opciones"]:
            texto = _normal(op["texto"])
            if texto and (texto == correcta or (not unica and texto in correcta)):
                op["es_correcta"] = True
    comentarios = [_texto_html(n) for clase in ("specificfeedback", "generalfeedback", "comment") for n in que.todos(clase)]
    datos["comentario"] = "\n\n".join(t for t in comentarios if t and _normal(t).rstrip(".") not in COMENTARIOS_OBVIOS)
    return datos


def _numero(valor):
    if valor is None:
        return ""
    return str(int(valor)) if float(valor).is_integer() else f"{valor:.2f}".replace(".", ",")
