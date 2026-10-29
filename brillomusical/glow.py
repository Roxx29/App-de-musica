"""Brillo en los bordes del monitor principal: 4 franjas transparentes que no reciben clics.

Capas por franja, en cada fotograma:
1. Relleno con el color o la cinta de colores del modo, recortado con la máscara del halo
   (precalculada: caída larga y suave).
2. Núcleo: línea fina casi blanca pegada al borde.
3. Partículas (motas, chispas, brasas) con un sprite precalculado y mezcla aditiva.
El ritmo llega como energía continua (`set_energy`) y golpes (`beat`).
"""
import colorsys
import ctypes
import logging
import math
import time
from ctypes import wintypes

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import effects

THICK = 60  # px lógicos
CORE = 3  # núcleo brillante
FADE = 1.2  # transición de color (s)
MODE_FADE = 1.0  # cambio de modo: 0,5 s apagando + 0,5 s encendiendo
PARTICLE_FADE = 1.0  # en pausa las partículas se apagan en 1 s
MAX_ALPHA = 0.95
RIBBON_STOPS = 48
SLOW_MS = 8.0  # si pintar el borde cuesta más de esto de media, se baja a 30 fps
GAMES = (2, 3)  # SHQueryUserNotificationState: app a pantalla completa / Direct3D a pantalla completa
MODES = ("static", "breathe", "beat", "spin", "aurora", "flash", "fire", "waves", "rainbow")
RIBBON = ("spin", "aurora", "flash", "fire", "waves", "rainbow")

log = logging.getLogger(__name__)
user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x20, 0x80000, 0x80, 0x8000000
HWND_TOPMOST = wintypes.HWND(-1)
SWP_FLAGS = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]


def fullscreen_app():
    state = ctypes.c_int(0)
    return ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0 and state.value in GAMES


def _ease(t):  # easeInOutCubic
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def _mix(a, b, f):
    return tuple(x + (y - x) * f for x, y in zip(a, b))


def _falloff(t):
    """Opacidad del halo a distancia t (0 borde, 1 interior): mucho color cerca y cola larga."""
    return 0.6 * (1 - t) ** 4 + 0.4 * (1 - t) ** 1.5


def _stops(grad, reverse=False):
    for i in range(13):
        t = i / 12
        grad.setColorAt(1 - t if reverse else t, QColor(255, 255, 255, round(255 * _falloff(t))))


class Strip(QWidget):
    def __init__(self, glow, edge):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.glow, self.edge = glow, edge  # edge: 0 arriba, 1 abajo, 2 izquierda, 3 derecha
        self.mask = QPixmap()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def showEvent(self, e):
        hwnd = int(self.winId())
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE,
                                 style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        super().showEvent(e)

    def build_mask(self, screen, dpr):
        pm = QPixmap(self.size() * dpr)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.translate(-self.x() + screen.x(), -self.y() + screen.y())
        w, ht, t = screen.width(), screen.height(), THICK
        for x0, y0, x1, y1, rect in ((0, 0, 0, t, QRect(t, 0, w - 2 * t, t)),
                                     (0, ht, 0, ht - t, QRect(t, ht - t, w - 2 * t, t)),
                                     (0, 0, t, 0, QRect(0, t, t, ht - 2 * t)),
                                     (w, 0, w - t, 0, QRect(w - t, t, t, ht - 2 * t))):
            g = QLinearGradient(x0, y0, x1, y1)
            _stops(g)
            p.fillRect(rect, g)
        for cx, cy in ((t, t), (w - t, t), (t, ht - t), (w - t, ht - t)):
            g = QRadialGradient(QPointF(cx, cy), t)  # esquinas redondeadas por dentro
            _stops(g, reverse=True)
            p.fillRect(QRect(cx - t if cx == t else cx, cy - t if cy == t else cy, t, t), g)
        p.end()
        self.mask = pm

    def core_rects(self):
        """Rectángulos del núcleo en coordenadas de la franja (incluye las esquinas en arriba/abajo)."""
        w, h = self.width(), self.height()
        if self.edge == 0:
            return [QRectF(0, 0, w, CORE), QRectF(0, 0, CORE, h), QRectF(w - CORE, 0, CORE, h)]
        if self.edge == 1:
            return [QRectF(0, h - CORE, w, CORE), QRectF(0, 0, CORE, h), QRectF(w - CORE, 0, CORE, h)]
        return [QRectF(0 if self.edge == 2 else w - CORE, 0, CORE, h)]

    def paintEvent(self, e):
        t0 = time.perf_counter()
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        opacity = self.glow.fill(self, p)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawPixmap(0, 0, self.mask)
        # la opacidad va aparte: con setOpacity Qt mezclaría con el fondo y el halo nunca llegaría a 0
        p.fillRect(self.rect(), QColor(0, 0, 0, round(255 * max(0.0, min(1.0, opacity)))))
        p.setCompositionMode(QPainter.CompositionMode_Plus)  # luz que se suma
        self.glow.overlay(self, p)
        p.end()
        self.glow.paint_ms += (time.perf_counter() - t0) * 1000


class Glow:
    def __init__(self, frames):
        self.frames = frames
        self.enabled = True
        self._scr = None
        self.screen = QRect()
        self.strips = [Strip(self, i) for i in range(4)]
        self.cur = (*colorsys.rgb_to_hsv(1, 0.7, 0.28), 0.0)  # (h, s, v, nivel)
        self.start = self.target = self.cur
        self.t0 = -1e9
        self.palette = []
        self.mode = self.prev_mode = "breathe"
        self.mode_t0 = -1e9
        self.beat_t = self.pulse_t = -1e9
        self.energy = 0.0
        self.spin_phase = 0.0
        self.last_t = time.monotonic()
        self.particles = effects.Particles(7)
        self.parts = []  # (x, y, alfa, tipo) en coordenadas de pantalla, calculadas una vez por fotograma
        self.part_fade = 0.0
        self.waves = effects.Waves()
        self.comets = []  # cometas extra del modo Destello: (t0, u0)
        self.sprites = {}
        self.ticking = False
        self.paint_ms, self.frames_n, self.stat_t, self.half, self.skip = 0.0, 0, time.monotonic(), False, False
        self.slow_periods = 0
        frames.tick.connect(self._on_tick)
        self.watch = QTimer(interval=2000, timeout=self._watch)  # topmost + pantalla completa
        self.watch.start()
        QGuiApplication.instance().primaryScreenChanged.connect(lambda _: self._layout())
        self._layout()

    # --- API ---
    def set_target(self, rgb, level):
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        target = (h, s, v, level)
        if all(abs(a - b) < 1e-3 for a, b in zip(target, self.target)):
            return
        self.start, self.target, self.t0 = self.cur, target, time.monotonic()
        self._apply_visibility()

    def set_palette(self, pal):
        self.palette = list(pal or [])

    def set_mode(self, mode):
        if mode != self.mode and mode in MODES:
            self.prev_mode, self.mode, self.mode_t0 = self.mode, mode, time.monotonic()
            self._apply_visibility()

    def set_enabled(self, on):
        self.enabled = on
        self._apply_visibility()

    def set_energy(self, e):
        self.energy = e

    def visible(self):
        return self.strips[0].isVisible()

    def beat(self):
        """Golpe de la música: cada modo reacciona a su manera."""
        now = time.monotonic()
        self.beat_t = now
        mode = self.mode
        if mode == "fire":
            self.particles.burst(now, 12, life=(0.8, 1.4), centers=3)  # brasas
        elif mode == "waves":
            self.waves.launch(now)
        elif mode == "flash":
            self.comets = [c for c in self.comets if now - c[0] < 1.5][-2:] + [(now, self.particles.rnd.random())]
        elif mode in ("static", "beat", "rainbow"):
            self.particles.burst(now, 10)
        elif mode == "breathe":
            self.particles.burst(now, 4, centers=1)

    def pulse(self):
        if self.mode != "beat":
            self.pulse_t = time.monotonic()
            self._apply_visibility()

    # --- geometría y visibilidad ---
    def _layout(self):
        scr = QGuiApplication.primaryScreen()
        if scr is not self._scr:  # resolución/escala/orientación del monitor principal
            if self._scr is not None:
                try:
                    self._scr.geometryChanged.disconnect(self._layout)
                except (RuntimeError, TypeError):
                    pass  # pantalla ya destruida
            scr.geometryChanged.connect(self._layout)
            self._scr = scr
        g = scr.geometry()  # geometría completa: también cubre la barra de tareas
        self.screen = g
        t = THICK
        rects = [QRect(g.x(), g.y(), g.width(), t), QRect(g.x(), g.bottom() - t + 1, g.width(), t),
                 QRect(g.x(), g.y() + t, t, g.height() - 2 * t), QRect(g.right() - t + 1, g.y() + t, t, g.height() - 2 * t)]
        for s, r in zip(self.strips, rects):
            s.setGeometry(r)
            s.build_mask(g, scr.devicePixelRatio())
        self._apply_visibility()

    def _playing(self):
        return self.target[3] >= 1

    def _busy(self, now):
        """¿Hace falta seguir animando? Sonando siempre (partículas); en pausa solo hasta que todo se calme."""
        return (self._playing() or now - self.t0 < FADE or now - self.mode_t0 < MODE_FADE
                or now - self.pulse_t < 0.4 or now - self.beat_t < 0.5 or self.part_fade > 0)

    def _want(self, on):
        if on != self.ticking:
            self.ticking = on
            self.frames.want("glow", on)

    def _apply_visibility(self):
        now = time.monotonic()
        show = self.enabled and (self.target[3] > 0 or now - self.t0 < FADE) and not fullscreen_app()
        for s in self.strips:
            if show and not s.isVisible():
                s.show()
            elif not show and s.isVisible():
                s.hide()
        if show and self._busy(now):
            self._want(True)
        else:
            self._want(False)  # oculto (p. ej. juego a pantalla completa) o quieto: sin fotogramas
            if show:
                self._tick()  # último fotograma estable

    def _on_tick(self):
        if not self.ticking:
            return
        self.skip = self.half and not self.skip  # modo lento: uno de cada dos
        if not self.skip:
            self._tick()

    def _tick(self):
        now = time.monotonic()
        dt, self.last_t = min(0.1, now - self.last_t), now
        t = min(1.0, (now - self.t0) / FADE)
        e = _ease(t)
        (h0, s0, v0, l0), (h1, s1, v1, l1) = self.start, self.target
        dh = (h1 - h0 + 0.5) % 1.0 - 0.5  # camino de tono más corto
        self.cur = ((h0 + dh * e) % 1.0, s0 + (s1 - s0) * e, v0 + (v1 - v0) * e, l0 + (l1 - l0) * e)
        # fase integrada: acelerar en un golpe no hace saltar el dibujo
        boost = effects.env(now - self.beat_t, 0.05, 0.5)
        self.spin_phase = (self.spin_phase + dt * (1 + 2 * boost) / (12 if self.mode == "rainbow" else 10)) % 1.0
        self.part_fade = max(0.0, min(1.0, self.part_fade + (dt if self._playing() else -dt) / PARTICLE_FADE))
        self.particles.update(now, dt, self.energy)
        self.waves.prune(now)
        self._place_particles(now)
        self._stats(now)
        if not self._busy(now):
            self._want(False)
            if self.target[3] == 0:
                self._apply_visibility()
        for s in self.strips:
            s.update()

    def _stats(self, now):
        self.frames_n += 1
        if now - self.stat_t >= 2.0:
            if self.frames_n >= 30:  # solo con animación continua; en pausa un repintado suelto no cuenta
                avg = self.paint_ms / self.frames_n
                self.slow_periods = self.slow_periods + 1 if avg > SLOW_MS else 0
                if self.slow_periods >= 2 and not self.half:
                    log.warning("Borde lento (%.1f ms por fotograma): baja a 30 fps", avg)
                    self.half = True
                elif self.half and avg < SLOW_MS / 2:
                    self.half = False  # el equipo ya va desahogado: vuelve a fps completos
            self.paint_ms, self.frames_n, self.stat_t = 0.0, 0, now

    def _watch(self):
        self._apply_visibility()
        for s in self.strips:
            if s.isVisible():
                user32.SetWindowPos(int(s.winId()), HWND_TOPMOST, 0, 0, 0, 0, SWP_FLAGS)

    # --- dibujo ---
    def _colors(self):
        """Primario (con su transición) + paleta; si la portada da un solo color, tonos vecinos."""
        h, s, v, _ = self.cur
        base = colorsys.hsv_to_rgb(h, s, v)
        rest = [tuple(c / 255 for c in rgb) for rgb in self.palette[1:3]]
        while len(rest) < 2:
            rest.append(colorsys.hsv_to_rgb((h + (0.08 if not rest else -0.08)) % 1.0, s, v))
        return [base] + rest

    def _mode_and_fade(self, now):
        dt = now - self.mode_t0
        return (self.prev_mode, 1 - dt / 0.5) if dt < 0.5 else (self.mode, min(1.0, (dt - 0.5) / 0.5))

    def _extra(self, mode, now):
        """Luz extra común: pulso de cambio de línea + golpe suave en el halo (todos los modos)."""
        pp = now - self.pulse_t
        extra = 0.25 * (1 - pp / 0.4) ** 3 if pp < 0.4 and mode != "beat" else 0.0
        if mode != "beat":
            extra += 0.15 * effects.env(now - self.beat_t, 0.08, 0.4)
        return extra

    def _ribbon(self, mode, u, now, cols):
        """(rgb 0..1, alfa) en la posición u (0..1) del perímetro."""
        if mode == "spin":
            x = ((u + self.spin_phase) % 1.0) * len(cols)
            i, f = int(x), x - int(x)
            return _mix(cols[i], cols[(i + 1) % len(cols)], f * f * (3 - 2 * f)), 0.7
        if mode == "rainbow":
            h = (colorsys.rgb_to_hsv(*cols[0])[0] + u + self.spin_phase) % 1.0
            return colorsys.hsv_to_rgb(h, 0.85, 1.0), 0.7
        if mode == "aurora":  # dos ondas lentas; un golpe las hace crecer
            swell = 1 + 0.3 * effects.env(now - self.beat_t, 0.1, 0.8)
            w1 = 0.5 + 0.5 * math.sin(2 * math.pi * (2 * u + now / 17))
            w2 = 0.5 + 0.5 * math.sin(2 * math.pi * (3 * u - now / 13) + 1)
            return (_mix(_mix(cols[0], cols[1], w1), cols[2], w2 * 0.6),
                    (0.3 + 0.4 * (0.6 * w1 + 0.4 * w2)) * swell)
        if mode == "fire":
            f = effects.fire(u, now)
            flare = effects.env(now - self.beat_t, 0.05, 0.25)
            deep = _mix(tuple(c * 0.45 for c in cols[0]), (0.5, 0.05, 0.0), 0.3)  # brasa oscura
            ember = _mix(deep, _mix(cols[0], (1.0, 0.92, 0.65), 0.65), f)
            return ember, 0.12 + 0.83 * f + 0.25 * flare
        if mode == "waves":
            uc = effects.perimeter_u(1, self.screen.width() / 2, self.screen.width(), self.screen.height())
            v = self.waves.value(u, now, uc)
            return _mix(cols[0], (1, 1, 1), 0.4 * v), 0.3 + 0.2 * self.energy + 0.6 * v
        # flash: cometa principal (una vuelta cada 3 s) + cometas lanzados por los golpes
        k = max(0.0, 1 - (((now / 3) % 1.0 - u) % 1.0) / 0.2) ** 2
        for t0, u0 in self.comets:
            age = now - t0
            if age < 1.5:
                head = (u0 + age / 3) % 1.0
                k = max(k, (1 - age / 1.5) * max(0.0, 1 - ((head - u) % 1.0) / 0.2) ** 2)
        return _mix(cols[0], (1, 1, 1), 0.6 * k), 0.3 + 0.6 * k

    def _alpha(self, mode, now):
        if mode == "breathe":  # seno de 5 s; la energía amplía la oscilación
            s = 0.5 - 0.5 * math.cos(2 * math.pi * now / 5)
            lo, hi = 0.35 - 0.1 * self.energy, 0.8 + 0.05 * self.energy
            return lo + (hi - lo) * s
        if mode == "beat":
            return 0.35 + 0.2 * self.energy + 0.5 * effects.env(now - self.beat_t, 0.06, 0.3)
        return 0.6 + 0.2 * self.energy  # static

    def fill(self, strip, p):
        """Rellena la franja con el color del modo y devuelve la opacidad con la que aplicar la máscara."""
        now = time.monotonic()
        mode, fade = self._mode_and_fade(now)
        level = self.cur[3] * fade
        extra = self._extra(mode, now)
        cols = self._colors()
        rect = strip.rect()
        if mode not in RIBBON:
            p.fillRect(rect, QColor.fromRgbF(*cols[0]))
            return min(MAX_ALPHA, self._alpha(mode, now) + extra) * level
        # cinta a lo largo del eje largo de la franja, con la posición en el perímetro
        w, h = self.screen.width(), self.screen.height()
        x0, y0 = strip.x() - self.screen.x(), strip.y() - self.screen.y()
        horizontal = strip.edge < 2
        length = rect.width() if horizontal else rect.height()
        g = QLinearGradient(0, 0, length, 0) if horizontal else QLinearGradient(0, 0, 0, length)
        for k in range(RIBBON_STOPS + 1):
            f = k / RIBBON_STOPS
            u = effects.perimeter_u(strip.edge, (x0 if horizontal else y0) + f * length, w, h)
            rgb, alpha = self._ribbon(mode, u, now, cols)
            g.setColorAt(f, QColor.fromRgbF(*rgb, max(0.0, min(MAX_ALPHA, alpha + extra))))
        p.fillRect(rect, g)
        return level

    def overlay(self, strip, p):
        """Núcleo brillante + partículas (mezcla aditiva)."""
        now = time.monotonic()
        mode, fade = self._mode_and_fade(now)
        level = self.cur[3] * fade
        if level <= 0.01:
            return
        cols = self._colors()
        flash = effects.env(now - self.beat_t, 0.03, 0.18)
        core_a = min(1.0, (0.45 + 0.25 * self.energy + 0.4 * flash + self._extra(mode, now)) * level)
        core = QColor.fromRgbF(*_mix(cols[0], (1, 1, 1), 0.35), core_a)
        for r in strip.core_rects():
            p.fillRect(r, core)
        if not self.parts:
            return
        ox, oy = strip.x() - self.screen.x(), strip.y() - self.screen.y()
        sw, sh = strip.width(), strip.height()
        for x, y, alpha, kind, ci in self.parts:
            lx, ly = x - ox, y - oy
            if -8 <= lx <= sw + 8 and -8 <= ly <= sh + 8:
                size = 4.5 if kind == "mote" else 6
                rgb = (1.0, 0.75, 0.35) if mode == "fire" else cols[ci % 3]  # en Fuego, todo son brasas
                p.setOpacity(min(1.0, alpha * level))
                p.drawPixmap(QRectF(lx - size, ly - size, 2 * size, 2 * size), self._sprite(rgb), QRectF(0, 0, 32, 32))
        p.setOpacity(1.0)

    def _place_particles(self, now):
        if self.part_fade <= 0:
            self.parts = []
            return
        w, h = self.screen.width(), self.screen.height()
        out = []
        for i, (u, depth, alpha, kind) in enumerate(self.particles.positions(now)):
            x, y, nx, ny = effects.edge_point(u, w, h)
            d = depth * THICK
            out.append((x + nx * d, y + ny * d, alpha * self.part_fade * (0.6 + 0.4 * self.energy), kind, i))
        self.parts = out

    def _sprite(self, rgb):
        key = tuple(round(c * 20) for c in rgb)  # pocos colores distintos en caché
        pm = self.sprites.get(key)
        if pm is None:
            if len(self.sprites) > 64:  # las transiciones de color pasan por muchos tonos intermedios
                self.sprites.clear()
            pm = QPixmap(32, 32)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            g = QRadialGradient(QPointF(16, 16), 16)
            g.setColorAt(0, QColor(255, 255, 255, 255))
            g.setColorAt(0.25, QColor.fromRgbF(*rgb, 0.9))
            g.setColorAt(1, QColor.fromRgbF(*rgb, 0.0))
            q.fillRect(pm.rect(), g)
            q.end()
            self.sprites[key] = pm
        return pm
