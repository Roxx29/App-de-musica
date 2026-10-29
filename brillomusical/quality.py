"""Calidad Automática / Alta / Ligera: mide lo que cuesta pintar la letra y baja la calidad si el equipo no llega (sin Qt)."""
import os

SETTINGS = ("auto", "high", "light")
NAMES = {"auto": "Automática", "high": "Alta", "light": "Ligera"}
PERIOD = 2.0  # segundos por medición
SLOW_MS = 10.0  # media por fotograma que baja a Ligera
SLOW_PERIODS = 2  # 4 s seguidos
# shortcut: Automática no vuelve a subir en la sesión (en Ligera no se puede medir lo que costaría Alta), ampliar si molesta


def next_setting(s):
    return SETTINGS[(SETTINGS.index(s) + 1) % len(SETTINGS)] if s in SETTINGS else SETTINGS[0]


class Governor:
    def __init__(self, setting="auto", cores=None):
        self.setting = setting if setting in SETTINGS else "auto"
        self.auto_light = (cores or os.cpu_count() or 4) <= 2  # equipo de 2 núcleos o menos: empieza en Ligera
        self.slow = self.n = 0
        self.ms, self.t0 = 0.0, None

    @property
    def light(self):
        return self.setting == "light" or (self.setting == "auto" and self.auto_light)

    def feed(self, ms, now):
        """Un fotograma pintado en `ms`. Devuelve True si Automática acaba de bajar a Ligera."""
        if self.setting != "auto" or self.auto_light:
            return False
        if self.t0 is None:
            self.t0 = now
        self.ms, self.n = self.ms + ms, self.n + 1
        if now - self.t0 < PERIOD:
            return False
        avg = self.ms / self.n if self.n >= 30 else None  # solo con animación continua
        self.ms, self.n, self.t0 = 0.0, 0, now
        self.slow = self.slow + 1 if avg is not None and avg > SLOW_MS else 0
        self.auto_light = self.slow >= SLOW_PERIODS
        return self.auto_light
