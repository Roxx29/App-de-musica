"""Cinta: la letra recorre una cinta en S que se retuerce en perspectiva, sobre papel claro (sin Qt).

La cinta es una curva fija; el texto se desliza por ella según la posición de la canción: la palabra
que suena pasa por el ancla y las ya cantadas siguen hacia arriba a la derecha. Sin estado: pausa y
saltos dan siempre el mismo dibujo.
"""
import bisect
import math

PAPER, INK, BACK = (230, 226, 216), (20, 20, 20), (142, 138, 130)
# curva en S de abajo a la izquierda a arriba a la derecha (fracción del ancho y del alto)
P0, P1, P2, P3 = (-0.04, 0.84), (0.20, 0.40), (0.62, 0.44), (0.92, 0.16)
ANCHOR = 0.45  # la palabra que suena, a esta fracción del recorrido
WORD_STEP = 0.6  # la cinta tarda como mucho esto en pasar una palabra (luego espera a la siguiente)
CARD_END = 3.35  # rótulo del título al empezar la canción
SAMPLES = 200


def _bezier(t, a, b, c, d):
    u = 1 - t
    return u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d


def track(w, h, n=SAMPLES):
    """Tabla de la curva en px: (longitudes acumuladas, [(x, y, ángulo de la tangente)])."""
    pts = [(_bezier(i / n, P0[0], P1[0], P2[0], P3[0]) * w, _bezier(i / n, P0[1], P1[1], P2[1], P3[1]) * h)
           for i in range(n + 1)]
    lens, out = [0.0], []
    for i, (x, y) in enumerate(pts):
        nx, ny = pts[min(n, i + 1)]
        px, py = pts[max(0, i - 1)]
        out.append((x, y, math.atan2(ny - py, nx - px)))
        if i:
            lens.append(lens[-1] + math.hypot(x - pts[i - 1][0], y - pts[i - 1][1]))
    return lens, out


def at(tr, s):
    """(x, y, ángulo, u) a la distancia s por la curva; None fuera de ella."""
    lens, pts = tr
    if not 0 <= s <= lens[-1]:
        return None
    i = min(len(lens) - 2, bisect.bisect_right(lens, s) - 1)
    f = (s - lens[i]) / max(1e-9, lens[i + 1] - lens[i])
    (x0, y0, a0), (x1, y1, a1) = pts[i], pts[i + 1]
    return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, a0 + (a1 - a0) * f, s / lens[-1]


def twist(u, now=0.0, beat=0.0):
    """Giro de la cinta en u (radianes): ondula y al final da media vuelta (se ve el reverso)."""
    end = min(1.0, max(0.0, (u - 0.84) / 0.16))
    return (0.35 * math.sin(2 * math.pi * (u - 0.05 * now)) * (1 + 0.12 * beat)
            + math.pi * end * end * (3 - 2 * end))


def scroll(pos, times, offs, widths, step=WORD_STEP):
    """Desplazamiento del texto (px) en `pos`: la palabra i pasa por el ancla en `step` s desde que empieza."""
    i = bisect.bisect_right(times, pos) - 1
    if i < 0:
        return offs[0] if offs else 0.0
    dt = times[i + 1] - times[i] if i + 1 < len(times) else (step or WORD_STEP)  # pasado el final, se para
    span = (offs[i + 1] - offs[i]) if i + 1 < len(offs) else widths[i]
    lim = dt if step is None else min(step, dt)
    return offs[i] + span * min(1.0, max(0.0, (pos - times[i]) / lim if lim > 0 else 1.0))


def card(pos):
    """Rótulo del título: (entrada de las flechas, barra, fracción de letras, salida) o None si no toca."""
    if not 0 <= pos < CARD_END:
        return None
    c = lambda a, b: min(1.0, max(0.0, (pos - a) / (b - a)))  # noqa: E731
    return 1 - (1 - c(0.0, 0.45)) ** 3, c(0.15, 0.4), c(0.3, 1.6), c(3.0, CARD_END) ** 3


# --- aros de altavoz (sin Qt) ---
def cone(age, strength=1.0):
    """Escala de la cúpula del altavoz tras un golpe: se hunde en 60 ms y rebota pasándose en 220 ms."""
    if not 0 <= age < 0.28:
        return 1.0
    if age < 0.06:
        return 1 - 0.15 * strength * (age / 0.06) ** 2
    t, c = (age - 0.06) / 0.22 - 1, 1.7
    return 1 - 0.15 * strength * (1 - (1 + (c + 1) * t ** 3 + c * t ** 2))


def hop(age, v, flight=0.4):
    """Altura (0..v) de una mota de polvo que salta con el golpe y cae: parábola de flight·v segundos."""
    span = flight * v
    return 4 * v * age * (span - age) / span ** 2 if span > 0 and 0 <= age < span else 0.0


def chladni(n, m, x, y):
    """Figura de Chladni en (x, y) dentro del círculo unidad: las líneas nodales son donde vale ~0."""
    return math.cos(n * math.atan2(y, x)) * math.sin(m * math.pi * math.hypot(x, y))
