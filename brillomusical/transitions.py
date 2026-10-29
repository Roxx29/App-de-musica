"""Transiciones entre estrofas (sin Qt).

Cada estilo da, para cada estrella y cada instante, su estado en pantalla:
(x, y, escala, opacidad de estrella, opacidad de etiqueta, estela en px).
La variación (centro, giro, viento, orden…) sale de una semilla por estrofa.
"""
import math
import random

STYLES = ("travel", "swirl", "explode", "rain", "dust", "reconstellate", "wave")
NAMES = {"travel": "Viaje", "swirl": "Remolino", "explode": "Explosión", "rain": "Lluvia de estrellas",
         "dust": "Polvo", "reconstellate": "Reconstelar", "wave": "Onda"}
SETTINGS = ("auto", "random") + STYLES
SETTING_NAMES = {"auto": "Automática (según la música)", "random": "Aleatoria", **NAMES}
GROUPS = {"calm": ("reconstellate", "dust", "swirl"), "normal": ("travel", "swirl", "rain"),
          "intense": ("explode", "wave", "travel")}
IMPACT = ("explode", "wave")  # drops y estribillos
# (salida, retraso de la llegada, llegada) en segundos antes del factor de velocidad
TIMES = {"travel": (0.7, 0.15, 0.9), "swirl": (0.8, 0.25, 1.0), "explode": (0.65, 0.2, 0.7),
         "rain": (0.9, 0.1, 0.8), "dust": (0.9, 0.0, 0.9), "reconstellate": (0.35, 0.0, 1.1),
         "wave": (0.75, 0.3, 0.7), "cut": (0.3, 0.0, 0.45)}
MOOD_SPEED = {"calm": 1.3, "normal": 1.0, "intense": 0.8}
BURST = 0.15  # Explosión: fin de la anticipación (estallido, destello, chispas y empujón a la vez)


def _ring_out(tt, diag):
    """Radio del anillo de salida de Onda: llega más allá de las esquinas en 0,75 s."""
    return tt / 0.75 * 0.95 * diag


def _ring_in(v, diag):
    """Radio del anillo de llegada de Onda (v 0..1)."""
    return v * 1.1 * diag


def next_setting(s):
    return SETTINGS[(SETTINGS.index(s) + 1) % len(SETTINGS)] if s in SETTINGS else SETTINGS[0]


def _clamp(v):
    return max(0.0, min(1.0, v))


def _smooth(a, b, x):
    t = _clamp((x - a) / (b - a))
    return t * t * (3 - 2 * t)


def _out_back(t):
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def _hash(i, salt):
    """Número 0..1 estable por estrella."""
    return (math.sin(i * 12.9898 + salt * 78.233) * 43758.5453) % 1.0


def _rot(dx, dy, a):
    c, s = math.cos(a), math.sin(a)
    return dx * c - dy * s, dx * s + dy * c


def params(style, seed, mood="normal", jitter=True):
    rnd = random.Random(seed)
    k = MOOD_SPEED.get(mood, 1.0) * (rnd.uniform(0.85, 1.15) if jitter else 1.0)
    return {"style": style, "k": k, "salt": rnd.random() * 100,
            "cx": rnd.uniform(-0.15, 0.15), "cy": rnd.uniform(-0.12, 0.12),  # punto de fuga / centro
            "rot": math.radians(rnd.uniform(-8, 8)), "dir": rnd.choice((-1, 1)), "turns": rnd.uniform(0.5, 1.25),
            "wind": math.radians(rnd.uniform(-20, 20)), "order": rnd.randrange(3),
            "curve": rnd.uniform(-0.1, 0.1), "streaks": rnd.randint(24, 40), "force": rnd.uniform(0.6, 1.2)}


def out_time(P):
    out = TIMES[P["style"]][0] + (0.25 if P["style"] == "rain" else 0.0)  # escalonado de la lluvia
    return out * P["k"]


def total(P, n=0):
    o, d, i = TIMES[P["style"]]
    extra = 0.04 * min(n, 20) if P["style"] == "rain" else 0.0
    return max(out_time(P), (d + i + extra) * P["k"])


def _center(P, w, h):
    return w * (0.5 + P["cx"]), h * (0.5 + P["cy"])


def out_state(P, t, x, y, i, n, w, h):
    """Estado de una estrella de la estrofa que se va."""
    style, k = P["style"], P["k"]
    o = TIMES[style][0] * k
    cx, cy = _center(P, w, h)
    dx, dy = x - cx, y - cy
    u = _clamp(t / o)
    if style == "travel":  # vuela hacia la cámara acelerando
        s = 1 / (1 - 0.6 * u ** 3)
        rx, ry = _rot(dx, dy, P["rot"] * u)
        # la palabra se va antes que la estrella: ampliada más de ×1,3 se vería borrosa
        return cx + rx * s, cy + ry * s, s, 1 - _smooth(0.2, 0.8, u), 1 - _smooth(0, 0.35, u), 0.0
    if style == "swirl":  # espiral hacia el centro
        f = (1 - u) ** 1.5
        rx, ry = _rot(dx, dy, P["dir"] * P["turns"] * 2 * math.pi * u * u)
        return cx + rx * f, cy + ry * f, 0.4 + 0.6 * f, 1 - _smooth(0.5, 1, u), 1 - _smooth(0, 0.3, u), 0.0
    if style == "explode":  # anticipación (se encoge un 12 %) y estallido
        tt = t / k
        d = math.hypot(dx, dy) or 1.0
        ux, uy = (dx / d, dy / d) if math.hypot(dx, dy) > 1 else (math.cos(i * 2.4), math.sin(i * 2.4))
        if tt < BURST:
            f = 1 - 0.12 * _smooth(0, BURST, tt)
            px, py = cx + dx * f, cy + dy * f
        else:
            speed = P["force"] * (0.6 + 0.6 * _hash(i, P["salt"])) * h
            dist = speed * (1 - math.exp(-4 * (tt - BURST))) / 4 / 0.25  # frenado exponencial
            px, py = cx + dx * 0.88 + ux * dist, cy + dy * 0.88 + uy * dist
        return px, py, 1.0, 1 - _smooth(BURST, BURST + 0.5, tt), 1 - _smooth(0, 0.15, tt), 0.0
    if style == "rain":  # caen con gravedad, escalonadas
        tt = t / k
        order = (x / w, 1 - x / w, _hash(i, P["salt"]))[P["order"]]
        fall = max(0.0, tt - 0.25 * order)
        drop = 0.5 * 2.2 * h * fall * fall
        a = 1 - _smooth(0.35, 0.9, fall)
        return x + drop * math.tan(P["wind"]), y + drop, 1.0, a, 1 - _smooth(0, 0.2, tt), min(0.15 * h, 2.2 * h * fall * 0.06)
    if style == "wave":  # un anillo empuja hacia fuera (llega hasta las esquinas)
        R = _ring_out(t / k, math.hypot(w, h))
        d = math.hypot(dx, dy) or 1.0
        hit = _smooth(d, d + 0.12 * math.hypot(w, h), R)
        return x + dx / d * 0.12 * h * hit, y + dy / d * 0.12 * h * hit, 1.0, 1 - hit, 1 - hit, 0.0
    # dust (se deshace en motas), reconstellate (las estrellas pasan a la nueva) y cut (fundido rápido)
    fade = {"dust": 0.35, "reconstellate": 0.35, "cut": 0.3}[style] * k
    return x, y, 1.0, 1 - _smooth(0, fade, t), 1 - _smooth(0, fade * 0.7, t), 0.0


def in_state(P, t, x, y, i, n, w, h, src=None):
    """Estado de una estrella de la estrofa que llega (x, y = su sitio final)."""
    style, k = P["style"], P["k"]
    _, delay, dur = TIMES[style]
    cx, cy = _center(P, w, h)
    dx, dy = x - cx, y - cy
    if style == "rain":
        delay += 0.04 * min(i, 20)
    v = _clamp((t / k - delay) / dur)
    if style == "travel":  # llega desde lejos
        e = 1 - (1 - v) ** 3
        s = 1 / (1 + 2.33 * (1 - e))
        rx, ry = _rot(dx, dy, -P["rot"] * (1 - e))
        return cx + rx * s, cy + ry * s, s, _smooth(0, 0.35, v), _smooth(0.35, 0.9, v), 0.0
    if style == "swirl":  # se despliega en espiral con un pequeño rebote (el radio crece antes que el giro)
        e = (1 - (1 - v) ** 3) * (1 + 0.08 * math.sin(math.pi * v))
        # al llegar gira menos que al irse: las estrellas lejanas del centro no dan saltos
        rx, ry = _rot(dx, dy, -P["dir"] * 0.6 * P["turns"] * 2 * math.pi * (1 - v) ** 2)
        return cx + rx * e, cy + ry * e, 0.4 + 0.6 * _clamp(e), _smooth(0, 0.3, v), _smooth(0.55, 0.95, v), 0.0
    if style == "explode":  # se reagrupa desde posiciones dispersas
        ang = _hash(i, P["salt"] + 1) * 2 * math.pi
        e = 1 - (1 - v) ** 4
        return (x + math.cos(ang) * 0.4 * h * (1 - e), y + math.sin(ang) * 0.4 * h * (1 - e), 1.0,
                _smooth(0, 0.3, v), _smooth(0.5, 0.95, v), 0.0)
    if style == "rain":  # cae desde arriba hasta su sitio
        e = 1 - (1 - v) ** 2
        top = -0.1 * h
        py = top + (y - top) * e
        return x - (y - py) * math.tan(P["wind"]), py, 1.0, _smooth(0, 0.15, v), _smooth(0.85, 1, v), (1 - e) * 0.1 * h
    if style == "dust":  # las motas se juntan y aparece la estrella (sin hueco vacío tras la salida)
        return x, y, 1.0, _smooth(0.35, 0.8, v), _smooth(0.5, 0.9, v), 0.0
    if style == "reconstellate":  # cada estrella viaja desde una de la estrofa anterior
        sx, sy = src if src else (cx, cy)
        e = v * v * (3 - 2 * v)
        ex, ey = x - sx, y - sy
        d = math.hypot(ex, ey) or 1.0
        bend = P["curve"] * h * math.sin(math.pi * e)
        return (sx + ex * e - ey / d * bend, sy + ey * e + ex / d * bend, 1.0,
                1.0 if src else _smooth(0, 0.3, v), _smooth(0.45, 0.8, v), 0.0)
    if style == "wave":  # aparecen cuando el anillo pasa por su radio
        diag = math.hypot(w, h)
        R = _ring_in(v, diag)
        d = math.hypot(dx, dy)
        g = _smooth(d - 0.05 * diag, d + 0.08 * diag, R)
        return x, y, 0.5 + 0.5 * _clamp(_out_back(g)) if g < 1 else 1.0, g, _smooth(d + 0.04 * diag, d + 0.2 * diag, R), 0.0
    return x, y, 1.0, _smooth(0.1, 0.4, t / k), _smooth(0.15, 0.45, t / k), 0.0  # cut


def push(P, t):
    """Empujón de cámara del fondo (0..~1,5) durante la transición."""
    tt = t / P["k"]
    style = P["style"]
    if style == "travel":
        return math.sin(math.pi * tt / 1.05) if 0 <= tt <= 1.05 else 0.0
    if style == "explode":
        return 1.5 * (1 - _clamp((tt - BURST) / 0.5)) if tt >= BURST else 0.0
    if style == "swirl":
        return 0.5 * math.sin(math.pi * tt / 1.25) if 0 <= tt <= 1.25 else 0.0
    return 0.0


def extras(P, t, old_pts, new_pts, w, h):
    """Efectos extra baratos: ("line", x1, y1, x2, y2, a), ("dot", x, y, r, a), ("ring", cx, cy, r, a), ("flash", a)."""
    style, k = P["style"], P["k"]
    tt = t / k
    cx, cy = _center(P, w, h)
    out = []
    if style == "travel" and 0 < tt < 1.05:  # estelas radiales desde el punto de fuga (que queda despejado)
        speed = math.sin(math.pi * tt / 1.05)
        grow = 1 + 0.5 * tt / 1.05
        for j in range(P["streaks"]):
            ang = _hash(j, P["salt"]) * 2 * math.pi
            r0 = (0.18 + 0.45 * _hash(j, P["salt"] + 3)) * h * grow
            r1 = r0 + 0.12 * h * speed * (0.5 + _hash(j, P["salt"] + 5))
            out.append(("line", cx + math.cos(ang) * r0, cy + math.sin(ang) * r0,
                        cx + math.cos(ang) * r1, cy + math.sin(ang) * r1, 0.3 * speed))
    elif style == "explode":
        if BURST <= tt < BURST + 0.18:  # destello corto y suave (se repite en estribillos y drops)
            out.append(("flash", 0.18 * (1 - (tt - BURST) / 0.18)))
        if BURST <= tt < BURST + 0.5:  # chispas
            age = (tt - BURST) / 0.5
            for j in range(30):
                ang = _hash(j, P["salt"] + 7) * 2 * math.pi
                dist = (0.1 + 0.5 * _hash(j, P["salt"] + 9)) * h * (1 - (1 - age) ** 2)
                out.append(("dot", cx + math.cos(ang) * dist, cy + math.sin(ang) * dist, 1.6, 1 - age))
    elif style == "dust":
        if tt < 0.9 and old_pts:  # la vieja se deshace en motas que suben (con empuje inicial)
            a = 1 - (1 - tt / 0.9) ** 2
            for i, (x, y) in enumerate(old_pts[:24]):
                for m in range(6):
                    jx = (_hash(i * 6 + m, P["salt"]) - 0.5) * 0.08 * h
                    out.append(("dot", x + jx * a * 2, y - (0.05 + 0.15 * _hash(i * 6 + m, P["salt"] + 2)) * h * a,
                                1.2, 0.8 * (1 - a)))
        v = _clamp(tt / 0.9)
        if new_pts and v < 1:  # y las nuevas se forman con motas que convergen
            e = 1 - (1 - v) ** 3
            for i, (x, y) in enumerate(new_pts[:24]):
                for m in range(6):
                    ox = (_hash(i * 6 + m, P["salt"] + 4) - 0.5) * 0.24 * h
                    oy = (_hash(i * 6 + m, P["salt"] + 6) - 0.5) * 0.24 * h
                    out.append(("dot", x + ox * (1 - e), y + oy * (1 - e), 1.2, 0.8 * _smooth(0, 0.3, v) * (1 - _smooth(0.8, 1, v))))
    elif style == "wave":  # los anillos coinciden con las estrellas que empujan / hacen aparecer
        diag = math.hypot(w, h)
        if 0 <= tt < 0.75:
            out.append(("ring", cx, cy, _ring_out(tt, diag), 0.45 * (1 - tt / 0.75)))
        v = (tt - 0.3) / 0.7
        if 0 <= v < 1:
            out.append(("ring", cx, cy, _ring_in(v, diag), 0.3 * (1 - v)))
    return out


def pick(setting, seed, mood, prev, special=False):
    """Estilo para este cambio de estrofa: fijo, aleatorio (sin repetir) o automático (según el ambiente)."""
    if setting in STYLES:
        return setting
    rnd = random.Random(seed)
    if setting == "auto":
        pool = IMPACT if special else GROUPS.get(mood, GROUPS["normal"])
    else:
        pool = STYLES
    choices = [s for s in pool if s != prev] or list(pool)
    return rnd.choice(choices)
