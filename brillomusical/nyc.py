"""Nueva York: palabras en blanco y negro que se enganchan unas a otras como un crucigrama (sin Qt).

Cada palabra cantada se pega a la anterior a la derecha, debajo o en vertical. Al acabar la línea,
zoom a la última palabra, que es la primera del bloque siguiente. Todo sale de la posición de la
canción: pausa y saltos dan siempre el mismo plano. Las medidas van en "unidades" (alto de letra).
"""
import bisect
import math
import random

BGS = ("asphalt", "cover", "city")
BG_NAMES = {"asphalt": "Asfalto", "cover": "Portada en blanco y negro", "city": "Ciudad"}
GREYS = (255, 138, 92, 58)  # la que suena y las anteriores, cada vez más apagadas
GAP = 0.08
MOVE, ZOOM_MIN, ZOOM_LEAD, FADE = 0.35, 0.3, 0.4, 0.15
FILL = 0.85  # una palabra sola llena el 85 % del ancho
ASPECT = 16 / 9
VERTICAL = 0.35  # probabilidad de girar una palabra que cabe en vertical
HERO = 1.8  # la última palabra de la línea, la protagonista (unas 3 veces las demás)
DIVE, DIVE_MAX = 0.35, 8.0  # entre líneas la cámara atraviesa la placa: 0,35 s hasta ×8 y sale igual
# colores de las líneas del metro de Nueva York: el acento es el más parecido a la portada
MTA = ((238, 53, 46), (255, 99, 25), (252, 204, 10), (0, 147, 60), (0, 57, 166), (185, 51, 173), (108, 190, 69))


def next_bg(b):
    return BGS[(BGS.index(b) + 1) % len(BGS)] if b in BGS else BGS[0]


def size(letters, dur):
    """Alto de una palabra en tres escalones, como un cartel: las cortas (me, por, la) pequeñas y finas,
    el resto medianas según lo que duran; la protagonista (la última) se multiplica después."""
    return 0.45 if letters <= 3 else min(1.25, 0.85 + 0.25 * min(dur, 1.5))


def _free(r, rects):
    x, y, w, h = r[:4]
    return all(x + w + GAP <= a or a + c + GAP <= x or y + h + GAP <= b or b + d + GAP <= y
               for a, b, c, d, _ in rects)


def _shape(rects):
    """Lo lejos que queda el bloque de 16:9 (en escala logarítmica)."""
    w = max(r[0] + r[2] for r in rects) - min(r[0] for r in rects)
    h = max(r[1] + r[3] for r in rects) - min(r[1] for r in rects)
    return abs(math.log(w / h / ASPECT))


def place(words, seed, first=None):
    """[(x, y, ancho, alto, vertical)] para words = [(ancho/alto, duración, letras)], sin solapes.

    first: alto fijo de la palabra 0 (la que llega de la línea anterior). La última es 1,4 veces mayor
    y nunca vertical (es la que recibe el zoom).
    """
    rnd = random.Random(seed)
    rects, n = [], len(words)
    for i, (asp, dur, letters) in enumerate(words):
        s = first if i == 0 and first else size(letters, dur) * (HERO if i == n - 1 and i else 1.0)
        if i == 0:
            rects.append((0.0, 0.0, asp * s, s, False))
            continue
        spot = None
        for j in range(len(rects) - 1, -1, -1):  # pegada a la anterior; si no cabe, a las de antes
            px, py, pw, ph, pv = rects[j]
            opts = [(px + pw + GAP, py + ph - s, asp * s, s, False), (px, py + ph + GAP, asp * s, s, False)]
            if letters >= 4 and i < n - 1 and not pv:
                opts.append((px, py + ph + GAP, s, asp * s, True))  # vertical, leyendo hacia arriba
            rnd.shuffle(opts)  # entre las libres, la que deja el bloque más apaisado (como la pantalla)
            free = [r for r in opts if _free(r, rects)]
            vert = [r for r in free if r[4]]
            # a veces una vertical, como "GUSTAR" en la referencia; si no, la que deja el bloque más apaisado
            spot = vert[0] if vert and rnd.random() < VERTICAL else min(free, key=lambda r: _shape(rects + [r]),
                                                                       default=None)
            if spot:
                break
        if spot is None:  # debajo de todo el bloque: ahí siempre cabe
            spot = (min(r[0] for r in rects), max(r[1] + r[3] for r in rects) + GAP, asp * s, s, False)
        rects.append(spot)
    return rects


def mta(rgb):
    """Color de línea de metro más cercano en tono al de la portada (gris → amarillo, el del taxi)."""
    r, g, b = (c / 255 for c in rgb)
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 0.12:
        return MTA[2]

    def hue(c):
        cr, cg, cb = (v / 255 for v in c)
        a, z = max(cr, cg, cb), min(cr, cg, cb)
        d = a - z or 1e-9
        hh = ((cg - cb) / d) % 6 if a == cr else (cb - cr) / d + 2 if a == cg else (cr - cg) / d + 4
        return hh / 6
    h0 = hue(rgb)
    return min(MTA, key=lambda c: min(abs(hue(c) - h0), 1 - abs(hue(c) - h0)))


def dive(pos, line_start, t_next):
    """Multiplicador de zoom del paso entre líneas: entra en la placa antes de t_next y sale del negro al empezar."""
    m = 1.0
    if t_next is not None:
        d = min(DIVE, 0.25 * (t_next - line_start))  # líneas cortas (rap): más corto, no brusco
        if d > 0 and t_next - d < pos <= t_next:
            m *= DIVE_MAX ** (((pos - (t_next - d)) / d) ** 3)
    d = DIVE if t_next is None else min(DIVE, 0.25 * (t_next - line_start))
    if d > 0 and line_start <= pos < line_start + d:
        m *= DIVE_MAX ** ((1 - (pos - line_start) / d) ** 3)
    return m


def frame(rects, w, h):
    """(centro x, centro y, px por unidad) que encuadra esos rectángulos en una ventana w×h."""
    x0, y0 = min(r[0] for r in rects), min(r[1] for r in rects)
    x1, y1 = max(r[0] + r[2] for r in rects), max(r[1] + r[3] for r in rects)
    return (x0 + x1) / 2, (y0 + y1) / 2, min(FILL * w / (x1 - x0), 0.8 * h / (y1 - y0))


def _mix(a, b, f):
    """Mezcla de dos planos: centro en línea recta y escala en logarítmico (el zoom se siente uniforme)."""
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * f))


def camera(pos, starts, rects, t_next, w, h):
    """(cx, cy, escala, opacidad de las demás) en `pos`; starts: inicio de cada palabra (la 0, la que llega)."""
    k = max(0, min(len(rects) - 1, bisect.bisect_right(starts, pos) - 1))
    cam = frame(rects[:1], w, h)
    for j in range(1, k + 1):  # cada palabra mueve la cámara desde donde estaba (aunque no hubiera llegado)
        t = min(1.0, max(0.0, (min(pos, starts[j + 1] if j < k else pos) - starts[j]) / MOVE))
        cam = _mix(cam, frame(rects[:j + 1], w, h), 1 - (1 - t) ** 3)
    others = 1.0
    if t_next is not None and k == len(rects) - 1 and len(rects) > 1:
        # siempre hay zoom, aunque la última palabra llegue justo antes de la línea siguiente (rap)
        z0 = max(starts[-1], min(max(starts[-1] + ZOOM_MIN, t_next - ZOOM_LEAD), t_next - 0.08))
        if pos >= z0 and t_next > z0:
            f = min(1.0, (pos - z0) / (t_next - z0))
            cam = _mix(cam, frame(rects[-1:], w, h), 4 * f ** 3 if f < 0.5 else 1 - (-2 * f + 2) ** 3 / 2)
            others = min(1.0, max(0.0, (t_next - pos) / FADE))
    return cam[0], cam[1], cam[2], others
