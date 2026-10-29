"""Constelación: agrupación en estrofas y colocación aleatoria sin solapes (sin Qt)."""
import math
import random

ASPECT = 16 / 9  # distancias medidas como si la ventana fuera 16:9
MARGIN = 0.08
MIN_DIST = 0.08
STEP = (0.12, 0.45)  # distancia de cada palabra a la anterior
TRIES = 30
MAX_VISIBLE = 24
MAX_LINES = 4
GAP = 5.0  # segundos de silencio que cortan la estrofa


def stanzas(lines):
    """Listas de índices de líneas no vacías: corte en línea vacía, hueco largo o más de 4 líneas."""
    groups, cur = [], []
    for i, (t, text) in enumerate(lines):
        if not text.strip():
            if cur:
                groups.append(cur)
            cur = []
            continue
        if cur:
            pt, ptext = lines[cur[-1]]
            if t - pt > GAP + 0.4 * len(ptext.split()):  # la línea anterior ya acabó hace rato
                groups.append(cur)
                cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        k = math.ceil(len(g) / MAX_LINES)
        out += [g[round(i * len(g) / k):round((i + 1) * len(g) / k)] for i in range(k)]
    return out


def stanza_of(groups, idx):
    """Estrofa que se ve en la línea `idx` (una línea vacía mantiene la anterior)."""
    found = None
    for n, g in enumerate(groups):
        if g[0] <= idx:
            found = n
    return found


def _dist(a, b):
    return math.hypot((a[0] - b[0]) * ASPECT, a[1] - b[1])


def place(n, seed, avoid=None):
    """n puntos (x, y) en 0..1, cada uno cerca del anterior y lejos de todos los demás.

    avoid: rectángulo (x0, y0, x1, y1) normalizado donde no puede caer ninguno (p. ej. la tarjeta).
    """
    rnd = random.Random(seed)
    pts = []

    def inside(p):
        if not (MARGIN <= p[0] <= 1 - MARGIN and MARGIN <= p[1] <= 1 - MARGIN):
            return False
        return not avoid or not (avoid[0] <= p[0] <= avoid[2] and avoid[1] <= p[1] <= avoid[3])

    def free(p):
        return min((_dist(p, q) for q in pts), default=1.0)

    def anywhere():
        for _ in range(100):
            p = rnd.uniform(MARGIN, 1 - MARGIN), rnd.uniform(MARGIN, 1 - MARGIN)
            if inside(p):
                return p
        return 0.5, MARGIN  # zona reservada absurda: arriba al centro

    for i in range(n):
        chosen = None
        for _ in range(TRIES if pts else 1):
            if not pts:
                p = anywhere()
            else:
                a, r = rnd.uniform(0, 2 * math.pi), rnd.uniform(*STEP)
                p = (pts[-1][0] + r * math.cos(a) / ASPECT, pts[-1][1] + r * math.sin(a))
            if inside(p) and free(p) >= MIN_DIST:
                chosen = p
                break
        if chosen is None:  # sin sitio cerca: el punto libre más lejano de unos cuantos al azar
            chosen = max((anywhere() for _ in range(TRIES)), key=free)
        pts.append(chosen)
    return pts


def _words(text):
    return {w.strip(".,;:!?¡¿\"'()").lower() for w in text.split()} - {""}


def chorus(lines, groups, similar=0.8):
    """Estrofas que se repiten en la canción (estribillos): parecido de palabras (Jaccard) ≥ 0,8."""
    sets = [set().union(*(_words(lines[i][1]) for i in g)) for g in groups]
    out = set()
    for a in range(len(sets)):
        for b in range(a + 1, len(sets)):
            if sets[a] and sets[b] and len(sets[a] & sets[b]) / len(sets[a] | sets[b]) >= similar:
                out |= {a, b}
    return out


def gaps(lines, min_s=12.0):
    """Huecos instrumentales largos (≥ min_s sin cantar): [(desde, hasta)] en segundos de la canción.

    Empiezan 2 s después de la última línea y acaban 1,5 s antes de la siguiente, que ya se conoce.
    """
    sung = [(t, text) for t, text in lines if text.strip()]
    out = []
    if sung and sung[0][0] >= min_s:  # intro larga
        out.append((2.0, sung[0][0] - 1.5))
    for (t, text), (t2, _) in zip(sung, sung[1:]):
        end = t + min(0.5 * len(text.split()) + 0.5, 6.0)  # cuándo acaba de cantarse (estimado)
        if t2 - end >= min_s:
            out.append((end + 2.0, t2 - 1.5))
    return out


def visible(indices, cur):
    """Palabras ya cantadas hasta `cur`, como mucho las últimas MAX_VISIBLE."""
    upto = [i for i in indices if i <= cur]
    return upto[-MAX_VISIBLE:]
