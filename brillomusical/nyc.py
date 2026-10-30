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


def next_bg(b):
    return BGS[(BGS.index(b) + 1) % len(BGS)] if b in BGS else BGS[0]


def size(letters, dur):
    """Alto de una palabra: las largas o las que duran más, más grandes."""
    return max(0.5, min(1.6, 0.55 + 0.08 * letters + 0.5 * dur))


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
        s = first if i == 0 and first else size(letters, dur) * (1.4 if i == n - 1 and i else 1.0)
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
        z0 = max(starts[-1] + ZOOM_MIN, t_next - ZOOM_LEAD)
        if pos >= z0 and t_next > z0:
            f = min(1.0, (pos - z0) / (t_next - z0))
            cam = _mix(cam, frame(rects[-1:], w, h), 4 * f ** 3 if f < 0.5 else 1 - (-2 * f + 2) ** 3 / 2)
            others = min(1.0, max(0.0, (t_next - pos) / FADE))
    return cam[0], cam[1], cam[2], others
