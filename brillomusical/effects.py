"""Efectos del borde sin Qt: perímetro, partículas, ondas, fuego y envolventes de tiempo.

u es la posición en el perímetro (0..1), empezando arriba a la izquierda y en el sentido
de las agujas del reloj. depth es la distancia hacia dentro, en fracción del grosor del borde.
"""
import math
import random

MAX_SPARKS = 80
N_MOTES = 40
WAVE_TIME, WAVE_SIGMA, MAX_WAVES = 1.5, 0.04, 6


def perimeter_u(edge, a, w, h):
    """u del punto a (x en arriba/abajo, y en izquierda/derecha). edge: 0 arriba, 1 abajo, 2 izq., 3 der."""
    d = (a if edge == 0 else w + a if edge == 3 else w + h + (w - a) if edge == 1 else 2 * w + h + (h - a))
    return (d / (2 * (w + h))) % 1.0


def edge_point(u, w, h):
    """(x, y, nx, ny): punto del borde en u y la normal hacia dentro."""
    d = (u % 1.0) * 2 * (w + h)
    if d < w:
        return d, 0.0, 0.0, 1.0
    d -= w
    if d < h:
        return float(w), d, -1.0, 0.0
    d -= h
    if d < w:
        return w - d, float(h), 0.0, -1.0
    return 0.0, h - (d - w), 1.0, 0.0


def env(dt, rise, fall):
    """Envolvente de un golpe: sube lineal en `rise`, baja cuadrática en `fall`."""
    if dt < 0 or dt >= rise + fall:
        return 0.0
    if dt < rise:
        return dt / rise
    return (1 - (dt - rise) / fall) ** 2


def circ(a, b):
    d = abs(a - b) % 1.0
    return min(d, 1 - d)


class Particles:
    """Motas que recorren el borde y chispas que saltan hacia dentro con los golpes."""

    def __init__(self, seed):
        self.rnd = random.Random(seed)
        r = self.rnd
        self.motes = [{"u": r.random(), "speed": r.uniform(0.01, 0.04) * r.choice((-1, 1)),
                       "phase": r.uniform(0, 6.28), "freq": r.uniform(0.15, 0.45)} for _ in range(N_MOTES)]
        self.sparks = []

    def update(self, now, dt, energy):
        k = 0.4 + 1.6 * energy  # con más energía, más rápido
        for m in self.motes:
            m["u"] = (m["u"] + m["speed"] * k * dt) % 1.0
        self.sparks = [s for s in self.sparks if now - s["t0"] < s["life"]]

    def burst(self, now, n=10, life=(0.6, 0.6), centers=2):
        r = self.rnd
        cs = [r.random() for _ in range(centers)]
        for i in range(n):
            self.sparks.append({"u": (cs[i % centers] + r.gauss(0, 0.012)) % 1.0, "drift": r.uniform(-0.015, 0.015),
                                "depth": r.uniform(0.4, 1.0), "t0": now, "life": r.uniform(*life)})
        del self.sparks[:-MAX_SPARKS]

    def positions(self, now):
        """(u, depth, alfa, tipo) de cada partícula viva."""
        for m in self.motes:
            s = 0.5 + 0.5 * math.sin(m["phase"] + now * 2 * math.pi * m["freq"])
            yield m["u"], 0.6 * s, 0.35 + 0.4 * (1 - s), "mote"
        for s in self.sparks:
            t = min(1.0, max(0.0, (now - s["t0"]) / s["life"]))
            yield ((s["u"] + s["drift"] * t) % 1.0, s["depth"] * (1 - (1 - t) ** 2), 1 - t, "spark")


class Waves:
    """Pulsos que salen del centro de abajo hacia los dos lados y se encuentran arriba en 1,5 s."""

    def __init__(self):
        self.pulses = []

    def launch(self, now):
        self.pulses = (self.pulses + [now])[-MAX_WAVES:]

    def prune(self, now):
        self.pulses = [t for t in self.pulses if now - t < WAVE_TIME]

    def value(self, u, now, uc):
        total = 0.0
        for t0 in self.pulses:
            age = now - t0
            if 0 <= age < WAVE_TIME:
                d, amp = 0.5 * age / WAVE_TIME, 1 - age / WAVE_TIME
                for c in (uc + d, uc - d):
                    total += amp * math.exp(-circ(u, c) ** 2 / (2 * WAVE_SIGMA ** 2))
        return min(1.0, total)


_rnd = random.Random(9)
_NOISE = [_rnd.random() for _ in range(256)]


def noise(x):
    """Ruido 1D suave y periódico (256)."""
    i = math.floor(x)
    f = x - i
    a, b = _NOISE[i % 256], _NOISE[(i + 1) % 256]
    return a + (b - a) * f * f * (3 - 2 * f)


def fire(u, now):
    """Intensidad 0..1 de las llamas en u: dos ruidos que se desplazan y un parpadeo de ~10 Hz."""
    n = 0.6 * noise(u * 40 + now * 1.6) + 0.4 * noise(u * 97 - now * 3.3)
    flicker = 0.85 + 0.15 * math.sin(2 * math.pi * 10 * now + u * 60)
    return max(0.0, min(1.0, (n - 0.3) * 2.2)) * flicker  # contraste alto: lenguas de fuego y huecos
