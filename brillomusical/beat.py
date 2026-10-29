"""Golpes y energía a partir del pico de audio (0..1) leído a ~60 Hz, y modo automático del borde (sin Qt)."""
import math
from collections import OrderedDict, deque

WINDOW = 60  # 1 s de muestras
SIGMA = 1.5
FLOOR = 0.02
REFRACTORY = 0.25
DECIDE_AFTER = 8.0  # segundos sonando antes de elegir modo
CACHE = 50


class BeatDetector:
    def __init__(self):
        self.win = deque(maxlen=WINDOW)
        self.prev = 0.0
        self.last = -1e9

    def feed(self, e, t):
        """True si `e` es un golpe: pico claro sobre la media del último segundo (independiente del volumen)."""
        hit = False
        if len(self.win) >= WINDOW // 2:
            mu = sum(self.win) / len(self.win)
            sd = math.sqrt(sum((x - mu) ** 2 for x in self.win) / len(self.win))
            hit = e > mu + SIGMA * sd and e > FLOOR and e > self.prev and t - self.last >= REFRACTORY
        if hit:
            self.last = t
        self.win.append(e)
        self.prev = e
        return hit


def classify(bps, cv, mean):
    if mean < 0.01:
        return "low"  # silencio
    if bps >= 1.5 and cv >= 0.25:
        return "high"
    if bps < 0.8 or cv < 0.12:
        return "low"
    return "mid"


class Envelope:
    """Energía continua 0..1: sigue el pico (sube en 50 ms, baja en 300 ms) y se normaliza con el máximo reciente."""
    RISE, FALL, PEAK_HALF_LIFE, FLOOR = 0.05, 0.3, 3.0, 0.02

    def __init__(self):
        self.env = self.peak = 0.0

    def feed(self, e, dt):
        k = min(1.0, dt / (self.RISE if e > self.env else self.FALL))
        self.env += (e - self.env) * k
        self.peak = max(e, self.peak * 0.5 ** (dt / self.PEAK_HALF_LIFE))
        return min(1.0, self.env / max(self.peak, self.FLOOR))


class Mood:
    """Ambiente de la canción en tiempo real: tranquila / normal / intensa, con histéresis, tempo y drops.

    Solo hay el pico de audio del navegador: se usa la energía relativa a la propia canción
    (no el volumen), la densidad de golpes, y el contexto (portada cálida, estribillo).
    """
    LOW, HIGH, MARGIN, HOLD, MIN_STATE = 0.35, 0.65, 0.08, 3.0, 8.0

    def __init__(self):
        self.warm, self.sat, self.chorus = False, 0.0, False
        self.start(None)

    def start(self, key):
        self.key = key
        self.e1 = self.e8 = None
        self.blocks, self.block_sum, self.block_n, self.block_t = [], 0.0, 0, 0.0
        self.beats = deque()
        self.t, self.since, self.hold, self.quiet = 0.0, 0.0, 0.0, 0.0
        self.state, self.drop, self.score = "normal", False, 0.5

    def set_context(self, warm=False, sat=0.0, chorus=False):
        self.warm, self.sat, self.chorus = warm, sat, chorus

    def _level(self):
        if len(self.blocks) >= 3:
            ref = sorted(self.blocks)[len(self.blocks) // 2]  # mediana: el "volumen normal" de esta canción
        else:
            ref = self.e8
        return self.e8 / ref if ref and ref > 1e-3 else 1.0

    def raw(self, m=None):
        m = self.score if m is None else m
        return "calm" if m < self.LOW else "intense" if m > self.HIGH else "normal"

    def feed(self, e, hit, dt):
        self.t += dt
        self.since += dt
        self.e1 = e if self.e1 is None else self.e1 + (e - self.e1) * min(1.0, dt / 0.5)
        self.e8 = e if self.e8 is None else self.e8 + (e - self.e8) * min(1.0, dt / 8.0)
        self.block_sum, self.block_n, self.block_t = self.block_sum + e, self.block_n + 1, self.block_t + dt
        if self.block_t >= 1.0:
            self.blocks = (self.blocks + [self.block_sum / self.block_n])[-600:]
            self.block_sum, self.block_n, self.block_t = 0.0, 0, 0.0
        if hit:
            self.beats.append(self.t)
        while self.beats and self.t - self.beats[0] > 8.0:
            self.beats.popleft()
        level = self._level()
        # drop: vuelve fuerte de golpe tras ≥ 4 s por debajo de lo normal
        if self.quiet >= 4.0 and self.e1 > 1.6 * self.e8:
            self.drop, self.quiet = True, 0.0
        self.quiet = self.quiet + dt if level < 0.7 else 0.0
        bps = len(self.beats) / max(1.0, min(8.0, self.t))
        cover = 0.6 * self.warm + 0.4 * self.sat
        # 2,5 golpes/s ya es "a tope": con /3 casi ninguna canción llegaba a intensa por la histéresis
        self.score = (0.5 * max(0.0, min(1.0, (level - 0.6) / 0.8)) + 0.25 * min(1.0, bps / 2.5)
                      + 0.15 * cover + 0.10 * self.chorus)
        m, s = self.score, self.state
        leaving = (m > self.LOW + self.MARGIN if s == "calm" else m < self.HIGH - self.MARGIN if s == "intense"
                   else m < self.LOW - self.MARGIN or m > self.HIGH + self.MARGIN)
        self.hold = self.hold + dt if leaving and self.raw() != s else 0.0
        if self.hold >= self.HOLD and self.since >= self.MIN_STATE:
            self.state, self.since, self.hold = self.raw(), 0.0, 0.0

    def pop_drop(self):
        d, self.drop = self.drop, False
        return d

    @property
    def bpm(self):
        """Tempo si los golpes son regulares (variación < 0,3); si no, None."""
        ts = list(self.beats)[-17:]
        iv = [b - a for a, b in zip(ts, ts[1:])]
        if len(iv) < 4:
            return None
        mean = sum(iv) / len(iv)
        sd = math.sqrt(sum((x - mean) ** 2 for x in iv) / len(iv))
        if mean <= 0 or sd / mean >= 0.3:
            return None
        bpm = 60 / sorted(iv)[len(iv) // 2]
        return bpm if 60 <= bpm <= 180 else None


def choose_glow(state, n_colors, warm):
    """Efecto del borde según el ambiente del momento."""
    if state == "calm":
        return "aurora" if n_colors >= 3 else "breathe"
    if state == "intense":
        return "fire" if warm else "beat"
    return "spin" if n_colors >= 2 else "waves"


def choose_bg(state, calm_secs, gap=False):
    """Fondo de la letra según el ambiente (en un instrumental, Ken Burns)."""
    if gap:
        return "kenburns"
    if state == "calm":
        return "kenburns" if calm_secs > 30 else "blur"
    return "beat" if state == "intense" else "ambient"


def choose(energy, n_colors, warm=False):
    if energy == "high":
        return "fire" if warm else "beat" if n_colors <= 1 else "waves"
    if energy == "mid":
        return "spin" if n_colors >= 2 else "breathe"
    if energy == "low":
        return "aurora" if n_colors >= 3 else "breathe"
    return "breathe"  # sin audio


def resolve(manual, auto_mode):
    return auto_mode if manual == "auto" else manual


class AutoMode:
    """Elige el modo una sola vez por canción (a los 8 s sonando) y lo recuerda."""

    def __init__(self):
        self.cache = OrderedDict()
        self.decided = self.last = None
        self.start(None)

    def start(self, key):
        self.last = self.decided or self.last  # mientras decide, sigue el modo anterior (sin parpadeo)
        self.key = key
        self.decided = self.cache.get(key)
        self.t = self.beats = self.n = self.sum = self.sumsq = 0

    @property
    def mode(self):
        return self.decided or self.last or "breathe"

    def feed(self, e, is_beat, dt, n_colors, warm=False):
        if self.decided or self.key is None:
            return
        self.t += dt
        self.beats += is_beat
        self.n += 1
        self.sum += e
        self.sumsq += e * e
        if self.t >= DECIDE_AFTER - 1e-9:
            mean = self.sum / self.n
            sd = math.sqrt(max(0.0, self.sumsq / self.n - mean * mean))
            self.decided = choose(classify(self.beats / self.t, sd / mean if mean else 0.0, mean), n_colors, warm)
            self.cache[self.key] = self.decided
            while len(self.cache) > CACHE:
                self.cache.popitem(last=False)
