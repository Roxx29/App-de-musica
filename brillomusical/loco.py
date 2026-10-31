"""Modo Loco: salta entre los estilos según la música, con transiciones de formas (sin Qt).

Decide cuándo cambiar (drops, estribillos y cada 1/2/3 estrofas según la intensidad, nunca antes de 8 s)
y da la geometría de cada transición en función del progreso p (0..1). La ventana pinta una instantánea
del estilo que se va y la recorta o la transforma encima del nuevo, que va en vivo.
"""
import math
import random

GAP = 8.0  # segundos mínimos entre cambios
EVERY = {"intense": 1, "normal": 2, "calm": 3}  # cambios de estrofa por cambio de estilo
DURATION = {"iris": 0.9, "shards": 1.0, "liquid": 0.95, "swirl": 1.0, "blinds": 0.8, "mosaic": 0.85,
            "shock": 0.7, "shear": 0.75, "door": 0.9, "glitch": 0.7, "zoom": 0.6}
BY_REASON = {"drop": ("shock", "shards", "glitch"), "chorus": ("iris", "swirl", "door"),
             "intense": ("shear", "blinds", "glitch"), "normal": ("liquid", "mosaic", "door"),
             "calm": ("liquid", "iris")}


def decide(reason, mood, stanzas, since):
    """¿Cambiar de estilo? reason: "drop", "chorus" o "stanza"; stanzas: cambios de estrofa desde el último."""
    if since < GAP:
        return False
    return reason in ("drop", "chorus") or stanzas >= EVERY.get(mood, 2)


def next_style(styles, cur, seed):
    """Otro estilo distinto del actual, elegido con la semilla (determinista)."""
    others = [s for s in styles if s != cur] or list(styles)
    return others[seed % len(others)]


def pick(reason, mood, last, seed, light=False):
    """Transición para el disparador; nunca la misma dos veces seguidas. Ligera: zoom con fundido."""
    if light:
        return "zoom"
    group = BY_REASON[reason] if reason in BY_REASON else BY_REASON.get(mood, BY_REASON["normal"])
    choices = [k for k in group if k != last] or list(group)
    return choices[seed % len(choices)]


def duration(kind, mood="normal"):
    return 1.2 if kind == "liquid" and mood == "calm" else DURATION[kind]


# --- curvas ---
def out_cubic(t):
    return 1 - (1 - t) ** 3


def in_cubic(t):
    return t ** 3


def in_out_cubic(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def out_expo(t):
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def clamp(v):
    return max(0.0, min(1.0, v))


# --- formas (radio relativo en función del ángulo) ---
def iris(theta, p, beat=0.0):
    """Radio relativo (de 0 a ~1 de la semidiagonal) del iris: círculo → estrella de 5 → hexágono, girando."""
    if p < 0.15:  # anticipación: el agujero se cierra un poco antes de abrirse
        return 0.0
    q = in_out_cubic((p - 0.15) / 0.85)
    th = theta - math.radians(40) * p
    star = 0.55 + 0.45 * (0.5 + 0.5 * math.cos(5 * th))  # 5 puntas
    hexa = math.cos(math.pi / 6) / math.cos(((th % (math.pi / 3)) - math.pi / 6))  # hexágono
    shape = (1 - 2 * q) * 1 + 2 * q * star if q < 0.5 else (2 - 2 * q) * star + (2 * q - 1) * hexa
    return 1.25 * q * shape * (1 + 0.06 * beat)


def blob(theta, p, t, energy=0.0, beat=0.0):
    """Radio relativo de la mancha líquida: crece ondulando más cuanto más energía tiene la música."""
    a = 0.04 + 0.08 * energy + 0.06 * beat
    return 1.5 * in_out_cubic(p) * (1 + a * math.sin(5 * theta + 6 * t) + 0.5 * a * math.sin(9 * theta - 4 * t))


def blinds(p, n=10):
    """Ancho (0..1) de cada franja de la persiana que aún tapa: se cierran escalonadas."""
    return [1 - out_cubic(clamp((p - i * 0.05) / 0.55)) ** 1.3 for i in range(n)]


def shards(seed, cols=6, rows=4):
    """Trozos de cristal: triángulos de una rejilla con los vértices movidos; coordenadas 0..1."""
    rnd = random.Random(seed)
    pts = {}
    for j in range(rows + 1):
        for i in range(cols + 1):
            jx = 0 if i in (0, cols) else (rnd.random() - 0.5) * 0.7 / cols
            jy = 0 if j in (0, rows) else (rnd.random() - 0.5) * 0.7 / rows
            pts[i, j] = (i / cols + jx, j / rows + jy)
    out = []
    for j in range(rows):
        for i in range(cols):
            a, b, c, d = pts[i, j], pts[i + 1, j], pts[i + 1, j + 1], pts[i, j + 1]
            out += [(a, b, c), (a, c, d)] if rnd.random() < 0.5 else [(a, b, d), (b, c, d)]
    return out


def shard_state(tri, k, p, energy=0.0):
    """(dx, dy, giro en grados, escala, opacidad) de un trozo: sale hacia fuera, cae y se desvanece."""
    cx, cy = sum(v[0] for v in tri) / 3, sum(v[1] for v in tri) / 3
    dist = math.hypot(cx - 0.5, cy - 0.5)
    t = max(0.0, (p - 0.12 - 0.025 * dist * 4) * 1.0)  # grietas primero; luego, escalonados desde el centro
    ang = math.atan2(cy - 0.5, cx - 0.5)
    v = min(1.1, (0.6 + 0.5 * ((k * 7919) % 100) / 100) * (0.7 + 0.6 * energy))  # pantallas por segundo
    spin = (90 + (k * 3571) % 180) * (1 if k % 2 else -1)
    return (math.cos(ang) * v * t, math.sin(ang) * v * t + 1.8 * t * t, spin * t, 1 - 0.15 * clamp(t / 0.9),
            1 - clamp((p - 0.6) / 0.4))
