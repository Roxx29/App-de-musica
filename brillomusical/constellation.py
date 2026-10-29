"""Ventana de letras: cada estrofa es una constelación aleatoria que crece palabra a palabra.

Las formas costosas (fondo de estrellas, halo, nebulosa) se pintan una vez en QPixmap y se
reutilizan en cada fotograma; solo se anima lo que se mueve.
"""
import bisect
import ctypes
import math
import random
import time
import zlib
from collections import OrderedDict

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import backdrop, cover, layout, lyrics, media, transitions
from .color import FALLBACK

# tamaños en fracción de la altura de la ventana: (estrella, texto)
SIZE_CURRENT, SIZE_PREV, SIZE_REST = (0.045, 0.06), (0.025, 0.035), (0.012, 0.022)
REST_ALPHA, OLD_ALPHA, OLD_AFTER = 0.45, 0.25, 12  # las palabras con más de 12 de antigüedad, más tenues
DRAW_LINE = 0.35  # trazo de la línea hacia la palabra nueva
FLASH, SPARKS = 0.3, 0.5
BG_STARS, TWINKLERS = 120, 20
TOAST = 1.5  # avisos breves (desfase, modo de fondo)
SEARCHING = "Buscando letra…"
HELP = "B fondo · C carátula · T transición · ←/→ sincronizar · H atajos"


def _out_cubic(t):
    return 1 - (1 - t) ** 3


def _out_back(t):
    c = 1.70158
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def _star_path():
    path = QPainterPath()
    pts = [(0, -1), (0.2, -0.2), (1, 0), (0.2, 0.2), (0, 1), (-0.2, 0.2), (-1, 0), (-0.2, -0.2)]
    path.moveTo(*pts[0])
    for x, y in pts[1:]:
        path.lineTo(x, y)
    path.closeSubpath()
    return path


def _font_family():
    f = QFont("Segoe UI Variable Display")
    return f.family() if f.exactMatch() else "Segoe UI"


class LyricsWindow(QWidget):
    offset_step = Signal(float)  # ← / → : mover la letra ±0,1 s
    bg_changed = Signal(str)  # B: siguiente modo de fondo
    cover_changed = Signal(str)  # C: siguiente posición de la carátula
    transition_changed = Signal(str)  # T: siguiente transición

    def __init__(self, settings, frames):
        super().__init__()
        self.settings = settings
        self.frames = frames
        self.clock = lyrics.Clock()
        self.offset = 0.0
        self.toast_text, self.toast_t, self.toast_secs = "", -1e9, TOAST
        self.backdrop = backdrop.Backdrop(settings.value("lyrics_bg", "auto"))
        # transiciones: opción elegida, estilo en curso y contexto musical para la Automática
        self.trans_setting = settings.value("lyrics_transition", "auto")
        if self.trans_setting not in transitions.SETTINGS:
            self.trans_setting = "auto"
        self.trans_P, self.prev_style = None, None
        self.mood, self.drop_t = "normal", -1e9
        self.chorus, self.gaps = set(), []
        self.times = []
        self.labels = OrderedDict()  # caché LRU de etiquetas ya dibujadas
        self.rands = {}
        self.setWindowTitle("BrilloMusical · Letras")
        self.setMinimumSize(480, 270)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.family = _font_family()
        self.fonts = {}
        self.cover = cover.Cover(settings.value("lyrics_cover", "card"), self.family)
        self.hd_key = None  # canción cuya portada grande (iTunes) ya está puesta: la de Windows no la pisa
        self.snap = None
        self.lines, self.groups = [], []
        self.status = "Esperando música…"
        self.rgb = FALLBACK
        self.star = _star_path()
        self.halo = self.nebula = self.bg = None
        self.twinklers = []
        self.stanza_cache = {}
        self.shown = None  # estrofa en pantalla
        self.trans_t0 = -1e9
        self.old_items, self.last_items, self.leaving_now = [], [], []
        self.animating = False
        frames.tick.connect(self._on_tick)  # 60 fps sincronizados con la pantalla, solo si hace falta
        # al final: restaurar una ventana maximizada lanza changeEvent, que ya necesita el estado de arriba
        geo = settings.value("lyrics_geometry")
        if geo is None or not self.restoreGeometry(geo):
            self.resize(960, 540)

    # --- estado que llega desde main ---
    def set_snapshot(self, snap):
        self.snap = snap
        if snap and snap["color"] and tuple(snap["color"]) != tuple(self.rgb):
            self.rgb = tuple(snap["color"])
            self.halo = self.nebula = None  # se regeneran con el color nuevo
            self.labels.clear()
        if snap and not snap["ad"]:
            key = (snap["title"], snap["artist"], snap["album"])
            if key != self.cover.key:
                self.hd_key = None  # canción nueva: hasta que llegue su portada grande vale la de Windows
            self.cover.set_track(key, snap["title"], snap["artist"], snap["album"])
            if self.hd_key != key and snap.get("art_id"):  # solo convierte si cambió la portada
                if snap.get("backdrop"):
                    self.backdrop.set_art(snap["art_id"], *snap["backdrop"])
                if snap.get("cover"):
                    self.cover.set_art(snap["art_id"], *snap["cover"])
        self._update_timer()
        self.update()

    def set_lyrics(self, status, lines):
        self.status, self.lines = status, lines
        self.times = [t for t, _ in lines]
        self.groups = layout.stanzas(lines)
        self.chorus = layout.chorus(lines, self.groups)  # estribillos: transición de impacto en Automática
        self.gaps = layout.gaps(lines)  # instrumentales largos: carátula grande
        self.stanza_cache.clear()
        # la última estrofa de la canción anterior termina de irse (no desaparece de golpe)
        self.old_items = [dict(it) for it in self.last_items] if self.last_items else self.leaving_now
        self.shown, self.last_items, self.trans_t0 = None, [], time.monotonic()
        self._update_timer()
        self.update()

    def set_offset(self, seconds, show=False):
        self.offset = seconds
        if show:
            self.toast(f"Letra {seconds:+.2f} s".replace(".", ","))

    def toast(self, text, secs=TOAST):
        """Aviso breve arriba a la derecha."""
        self.toast_text, self.toast_t, self.toast_secs = text, time.monotonic(), secs
        self.update()
        QTimer.singleShot(int(secs * 1000) + 100, self.update)

    def set_bg(self, mode, show=False):
        self.backdrop.set_mode(mode)
        self.settings.setValue("lyrics_bg", self.backdrop.setting)
        if show:
            self.toast(f"Fondo: {backdrop.NAMES[self.backdrop.setting]}")
        self.update()

    def bg_mode(self):
        return self.backdrop.setting

    def set_auto_bg(self, mode):
        """Fondo que decide el ambiente (solo cuenta con la opción Automático)."""
        self.backdrop.set_auto(mode)

    def set_transition(self, setting, show=False):
        if setting in transitions.SETTINGS:
            self.trans_setting = setting
            self.settings.setValue("lyrics_transition", setting)
            if show:
                self.toast(f"Transición: {transitions.SETTING_NAMES[setting]}")

    def set_mood(self, mood):
        self.mood = mood

    def set_drop(self):
        self.drop_t = time.monotonic()

    def in_gap(self):
        """¿Está sonando un instrumental largo? (para el fondo automático)."""
        if not self.snap or not self.gaps:
            return False
        pos = self.position()
        return any(a <= pos <= b for a, b in self.gaps)

    def set_hd_art(self, key, art_id, backdrop_data, cover_data):
        """Portada grande (iTunes) de la canción `key`; se ignora si ya suena otra (un anuncio no cuenta)."""
        if key != self.cover.key:
            return
        self.hd_key = key
        self.backdrop.set_art(art_id, *backdrop_data)
        self.cover.set_art(art_id, *cover_data)
        self.update()

    def set_cover(self, mode, show=False):
        self.cover.set_mode(mode)
        self.settings.setValue("lyrics_cover", self.cover.mode)
        self.stanza_cache.clear()  # la esquina reservada cambia
        if show:
            self.toast(f"Carátula: {cover.NAMES[self.cover.mode]}")
        self.update()

    def cover_mode(self):
        return self.cover.mode

    def wants_audio(self):
        """El fondo Al ritmo y los automáticos necesitan el medidor aunque el borde esté apagado."""
        return (self.isVisible() and not self.isMinimized()
                and (self.backdrop.setting in ("beat", "auto") or self.trans_setting == "auto"))

    def set_energy(self, e):
        self.backdrop.energy = e

    def beat(self):
        self.backdrop.beat()

    def position(self):
        """Posición de la canción para la letra: reloj suavizado + desfase manual."""
        snap = self.snap
        if not snap:
            return 0.0
        key = (snap["title"], snap["artist"], snap["album"])
        return self.clock.get(media.position(snap), snap["playing"], time.monotonic(), key) + self.offset

    def line_index(self, pos):
        return bisect.bisect_right(self.times, pos) - 1

    def _update_timer(self):
        playing = bool(self.snap) and self.snap["playing"] and not self.snap["ad"]
        run = self.isVisible() and not self.isMinimized() and playing
        if run != self.animating:
            self.animating = run
            self.frames.want("lyrics", run)

    def _on_tick(self):
        if self.animating:
            self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Left, Qt.Key_Right):
            self.offset_step.emit(0.1 if e.key() == Qt.Key_Right else -0.1)
        elif e.key() == Qt.Key_B:
            self.set_bg(backdrop.next_mode(self.backdrop.setting), show=True)
            self.bg_changed.emit(self.backdrop.setting)
        elif e.key() == Qt.Key_T:
            self.set_transition(transitions.next_setting(self.trans_setting), show=True)
            self.transition_changed.emit(self.trans_setting)
        elif e.key() == Qt.Key_H:
            self.toast(HELP, 6)
        elif e.key() == Qt.Key_C:
            self.set_cover(cover.next_mode(self.cover.mode), show=True)
            self.cover_changed.emit(self.cover.mode)
        else:
            super().keyPressEvent(e)

    # --- ventana ---
    def showEvent(self, e):
        try:  # barra de título oscura (Windows 10 2004+ / 11)
            on = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(on), 4)
        except OSError:
            pass
        self.shown, self.last_items, self.old_items = None, [], []  # sin transición de una estrofa vieja
        super().showEvent(e)
        self._update_timer()
        if not self.settings.value("help_shown", False, type=bool):  # la primera vez: los atajos
            self.settings.setValue("help_shown", True)
            self.toast(HELP, 6)

    def hideEvent(self, e):
        super().hideEvent(e)
        self._update_timer()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange:  # minimizar / restaurar
            self._update_timer()

    def resizeEvent(self, e):
        self.bg = self.nebula = None
        self.labels.clear()  # los tamaños de letra dependen de la altura
        self.stanza_cache.clear()  # y la esquina reservada para la tarjeta
        super().resizeEvent(e)

    def closeEvent(self, e):
        self.settings.setValue("lyrics_geometry", self.saveGeometry())
        super().closeEvent(e)

    # --- cachés ---
    def _font(self, px, bold=False):
        key = (round(px), bold)
        if key not in self.fonts:
            f = QFont(self.family)
            f.setPixelSize(max(8, key[0]))
            f.setWeight(QFont.DemiBold if bold else QFont.Normal)
            self.fonts[key] = f
        return self.fonts[key]

    def _color(self, alpha, rgb=None):
        return QColor(*(rgb or self.rgb), max(0, min(255, round(255 * alpha))))

    def _build_bg(self):
        """Estrellas de fondo en una capa transparente: el fondo (portada o negro) las hornea en su caché."""
        w, h = self.width(), self.height()
        rnd = random.Random(42)
        pm = QPixmap(self.size())
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        for _ in range(BG_STARS):
            p.setBrush(QColor(255, 255, 255, rnd.randint(30, 120)))
            r = rnd.uniform(0.4, 1.2)
            p.drawEllipse(QPointF(rnd.uniform(0, w), rnd.uniform(0, h)), r, r)
        p.end()
        self.bg = pm
        self.backdrop.set_stars(pm)
        self.twinklers = [(rnd.random(), rnd.random(), rnd.uniform(2, 5), rnd.uniform(0, 6.28), rnd.uniform(0.8, 1.6))
                          for _ in range(TWINKLERS)]

    def _build_halo(self):
        pm = QPixmap(128, 128)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        g = QRadialGradient(QPointF(64, 64), 64)
        g.setColorAt(0, self._color(0.9))
        g.setColorAt(0.25, self._color(0.35))
        g.setColorAt(1, self._color(0))
        p.fillRect(pm.rect(), g)
        p.end()
        self.halo = pm

    def _build_nebula(self):
        w, h = self.width(), self.height()
        pm = QPixmap(max(1, w // 4), max(1, h // 4))  # pequeña y ampliada: suave y barata
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        g = QRadialGradient(QPointF(pm.width() * 0.5, pm.height() * 0.55), max(pm.width(), pm.height()) * 0.6)
        g.setColorAt(0, self._color(1))
        g.setColorAt(1, self._color(0))
        p.fillRect(pm.rect(), g)
        p.end()
        self.nebula = pm

    def _stanza(self, k):
        """(palabras [(texto, inicio)], puntos 0..1) de la estrofa k, calculado una vez."""
        if k not in self.stanza_cache:
            words = []
            for li in self.groups[k]:
                words += zip(lyrics.words(self.lines[li][1]), lyrics.word_times(self.lines, li))
            seed = zlib.crc32(f"{self.snap['title'] if self.snap else ''}|{k}".encode())
            avoid = self.cover.avoid(self.width(), self.height())  # sin estrellas bajo la tarjeta
            self.stanza_cache[k] = (words, layout.place(len(words), seed, avoid))
        return self.stanza_cache[k]

    # --- dibujo ---
    def paintEvent(self, e):
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)  # halo, nebulosa y etiquetas escaladas o en posición decimal
        w, h = self.width(), self.height()
        if self.bg is None:
            self._build_bg()
        age = now - self.trans_t0  # tiempo desde el último cambio de estrofa
        push = transitions.push(self.trans_P, age) if self.trans_P else 0.0
        self.backdrop.draw(p, w, h, push=push, live=self.animating)
        snap = self.snap
        pos = self.position() if snap else 0.0
        playing_song = bool(snap) and not snap["ad"]
        # carátula grande: sin letra (estado final, no mientras se busca) o instrumental largo
        # entre dos canciones sin letra la carátula no va y vuelve mientras se busca la siguiente
        no_lyrics = (playing_song and not self.lines and self.status != ""
                     and (self.status != SEARCHING or self.cover.hero_on))
        gap = playing_song and bool(self.lines) and any(a <= pos <= b for a, b in self.gaps)
        self.cover.set_hero(no_lyrics or gap, 1.0 if no_lyrics else 0.7)
        if self.cover.mode == "center":  # se apaga a la vez que llega la carátula grande (sin parpadeo)
            self.cover.draw_watermark(p, w, h, push, self.devicePixelRatioF(), 1 - self.cover.hero_progress())
        self._background(p, now, w, h)
        prog = cover.progress(pos - self.offset, snap["duration"]) if snap else None
        native = 1000 if self.hd_key and self.hd_key == self.cover.key else 120
        hero = playing_song and self.cover.draw_hero(p, w, h, self.rgb, prog, self.backdrop.energy,
                                                     self.devicePixelRatioF(), native)
        if playing_song and not hero and self.cover.mode in ("card", "top"):
            self.cover.draw_front(p, w, h, self.rgb, prog, self.devicePixelRatioF())
        elif snap and not hero:
            p.setOpacity(0.4)
            p.drawPixmap(QPointF(16, 10), self._text_pixmap(f"{snap['title']} · {snap['artist']}", 13, False,
                                                             (255, 255, 255), False))
            p.setOpacity(1.0)
        if now - self.toast_t < self.toast_secs:  # aviso en una pastilla oscura (legible sobre portadas claras)
            pm = self._text_pixmap(self.toast_text, 13, False, (255, 255, 255), False)
            tw, th = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
            pill = QRectF(w - tw - 16 - 12, 16 - 6, tw + 24, th + 12)
            p.setOpacity(0.75 * min(1.0, 3 * (1 - (now - self.toast_t) / self.toast_secs)))
            path = QPainterPath()
            path.addRoundedRect(pill, 8, 8)
            p.fillPath(path, QColor(0, 0, 0, 90))
            p.drawPixmap(QPointF(pill.x() + 12, pill.y() + 6), pm)
            p.setOpacity(1.0)
        if not snap:
            return self._message(p, "Pon algo en YouTube Music ♪")
        if snap["ad"]:
            return self._message(p, "Anuncio · la música vuelve enseguida")
        if not self.lines:
            self._leaving(p, self.trans_P, age)  # la última estrofa termina de irse
            if hero:  # pie discreto del grupo carátula + textos + barra
                return self._message(p, self.status, y=0.86, alpha=0.45, size=0.020 * h, rgb=(255, 255, 255))
            return self._message(p, self.status)

        # tras un instrumental (hasta la siguiente línea) no vuelve la estrofa de antes
        after_gap = any(b < pos < b + 1.6 for _, b in self.gaps)
        k = None if gap or after_gap else layout.stanza_of(self.groups, self.line_index(pos))
        if k != self.shown:  # cambio de estrofa (o salto, o instrumental): transición
            self._start_transition(k, now)
            age = 0.0
        P = self.trans_P
        old_pts = self._leaving(p, P, age)
        if k is None:
            self.last_items = []
            self._extras(p, P, age, old_pts, [])
            if not hero:
                self._message(p, "♪")
            return

        words, pts = self._stanza(k)
        cur = max(0, sum(1 for _, s in words if s <= pos) - 1)
        vis = layout.visible(range(len(words)), cur)
        items = []
        for i in vis:
            rank = cur - i  # palabras desde la actual (no confundir con `age` de la transición)
            size, alpha = ((SIZE_CURRENT, 1.0) if rank == 0 else (SIZE_PREV, 0.85) if rank == 1
                           else (SIZE_REST, OLD_ALPHA if rank > OLD_AFTER else REST_ALPHA))
            it = self._item(pts[i], words[i][0], size, alpha, now, i, current=rank == 0)
            # estado en pantalla según la transición de llegada (se guarda: si cambia a mitad, sin saltos)
            if P is not None:
                src = old_pts[i] if i < len(old_pts) else (old_pts[-1] if old_pts else None)
                st = transitions.in_state(P, age, it["x"], it["y"], i, len(words), w, h, src)
            else:
                st = (it["x"], it["y"], 1.0, 1.0, 1.0, 0.0)
            it["dx"], it["dy"], it["s"], it["sa"], it["la"], it["trail"] = st
            items.append(it)
        self.last_items = items
        self._extras(p, P, age, old_pts, [(it["x"], it["y"]) for it in items])
        start = words[cur][1]
        self._draw(p, items, (pos - start, start))

    def _start_transition(self, k, now):
        """Elige estilo y variación para el cambio de estrofa; la vieja guarda su estado real en pantalla."""
        prev, self.shown = self.shown, k
        seed = zlib.crc32(f"{self.snap['title'] if self.snap else ''}|{k}|{prev}".encode())
        jump = prev is not None and k is not None and (k < prev or k > prev + 1)  # salto atrás o de varias
        special = now - self.drop_t < 2.0 or (k in self.chorus and prev not in self.chorus)
        style = "cut" if jump else transitions.pick(self.trans_setting, seed, self.mood, self.prev_style, special)
        self.trans_P = transitions.params(style, seed, self.mood)
        self.prev_style = style if style != "cut" else self.prev_style
        # sin estrofa en pantalla (p. ej. tras cambiar de canción), sigue desde lo que se está yendo
        self.old_items = [dict(it) for it in self.last_items] if self.last_items else self.leaving_now
        self.trans_t0 = now

    def _background(self, p, now, w, h):
        p.setPen(Qt.NoPen)
        for x, y, period, phase, r in self.twinklers:
            a = 0.25 + 0.55 * (0.5 + 0.5 * math.sin(2 * math.pi * now / period + phase))
            p.setBrush(QColor(255, 255, 255, round(255 * a)))
            p.drawEllipse(QPointF(x * w, y * h), r, r)
        if self.nebula is None:
            self._build_nebula()
        p.setOpacity(0.08 + 0.07 * (0.5 + 0.5 * math.sin(2 * math.pi * now / 10)))
        p.drawPixmap(QRectF(0, 0, w, h), self.nebula, QRectF(self.nebula.rect()))
        p.setOpacity(1.0)

    def _rand(self, seed, n):
        """n números aleatorios fijos para una semilla (calculados una vez, no en cada fotograma)."""
        if seed not in self.rands:
            rnd = random.Random(seed)
            self.rands[seed] = [rnd.random() for _ in range(n)]
        return self.rands[seed]

    def _item(self, pt, word, size, alpha, now, i, current=False):
        """Estrella con su posición en pantalla (flota ±3 px) y su titileo."""
        r = self._rand(i * 7919, 5)
        w, h = self.width(), self.height()
        drift = 6 + 3 * r[0]
        x = pt[0] * w + 3 * math.sin(2 * math.pi * now / drift + 6.28 * r[1])
        y = pt[1] * h + 3 * math.cos(2 * math.pi * now / (drift + 1) + 6.28 * r[2])
        tw = 0.85 + 0.15 * math.sin(2 * math.pi * now / (2 + 3 * r[3]) + 6.28 * r[4])
        return {"x": x, "y": y, "word": word, "r": size[0] * h, "font": size[1] * h, "alpha": alpha,
                "tw": tw, "current": current, "seed": i}

    def _draw(self, p, items, timing):
        """Dibuja la constelación con el estado en pantalla de cada estrella (dx, dy, s, sa, la, trail)."""
        if not items:
            return
        if self.halo is None:
            self._build_halo()
        # líneas: la última se traza hacia la palabra nueva
        grow = _out_cubic(min(1.0, timing[0] / DRAW_LINE)) if timing else 1.0
        for n, (a, b) in enumerate(zip(items, items[1:])):
            last = n == len(items) - 2
            pa, pb = QPointF(a["dx"], a["dy"]), QPointF(b["dx"], b["dy"])
            if last and grow < 1:
                pb = pa + (pb - pa) * grow
            fade = min(a["sa"], b["sa"])
            if "ox" in a:  # al salir, una línea que se estira más del doble se apaga (no cruza la pantalla)
                base = math.hypot(a["ox"] - b["ox"], a["oy"] - b["oy"]) + 1
                fade *= max(0.0, min(1.0, 2 - math.hypot(pa.x() - pb.x(), pa.y() - pb.y()) / base))
            if fade > 0.01:
                p.setPen(QPen(self._color((0.6 if last and grow < 1 else 0.35) * fade), 1))
                p.drawLine(pa, pb)
        for it in items:
            f = it["sa"]
            if f <= 0.01 and it["la"] <= 0.01:
                continue
            pt, r = QPointF(it["dx"], it["dy"]), it["r"] * it["s"]
            if it["trail"] > 1:  # estela (lluvia)
                p.setPen(QPen(self._color(0.5 * f), 1.2))
                p.drawLine(QPointF(pt.x(), pt.y() - it["trail"]), pt)
            if it["current"] and timing:
                t = min(1.0, timing[0] / FLASH)
                r *= 0.6 + 0.4 * _out_back(t)  # destello: 0,6 → 1,15 → 1
                self._sparks(p, pt, it["r"] * it["s"], timing[0], it["seed"], f)
            a = it["alpha"] * it["tw"] * f
            p.setOpacity(min(1.0, a))
            p.drawPixmap(QRectF(pt.x() - r * 3, pt.y() - r * 3, r * 6, r * 6), self.halo, QRectF(self.halo.rect()))
            p.setOpacity(1.0)
            p.save()
            p.translate(pt)
            p.scale(r, r)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, round(255 * min(1.0, a))) if it["current"] else self._color(min(1.0, a + 0.2)))
            p.drawPath(self.star)
            p.restore()
            if it["la"] > 0.01:
                self._label(p, pt, it, r, it["la"], it["s"])

    def _text_pixmap(self, text, px, bold, rgb, glow):
        """Texto dibujado una vez en una imagen: se mueve con precisión subpíxel sin vibrar."""
        key = (text, round(px), bold, rgb, glow)
        pm = self.labels.get(key)
        if pm is None:
            font = self._font(px, bold)
            fm = QFontMetricsF(font)
            pad = 4
            dpr = self.devicePixelRatioF()
            pm = QPixmap(round((fm.horizontalAdvance(text) + 2 * pad) * dpr), round((fm.height() + 2 * pad) * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.TextAntialiasing)
            q.setFont(font)
            base = QPointF(pad, pad + fm.ascent())
            # sombra horneada (gratis por fotograma): contorno fino + sombra abajo, para fondos claros
            q.setPen(QColor(0, 0, 0, 90))
            for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
                q.drawText(base + QPointF(dx, dy), text)
            q.setPen(QColor(0, 0, 0, 120))
            q.drawText(base + QPointF(0, 2), text)
            if glow:  # halo del color de la portada alrededor del texto
                q.setPen(self._color(0.3))
                for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                    q.drawText(base + QPointF(dx, dy), text)
            q.setPen(QColor(*rgb))
            q.drawText(base, text)
            q.end()
            self.labels[key] = pm
            if len(self.labels) > 200:
                self.labels.popitem(last=False)
        else:
            self.labels.move_to_end(key)
        return pm

    def _label(self, p, pt, it, r, fade, scale=1.0):
        current = it["current"]
        # las no actuales: color de la portada aclarado un 25 % para no perderse sobre un fondo del mismo tono
        rgb = (255, 255, 255) if current else tuple(round(c + (255 - c) * 0.25) for c in self.rgb)
        pm = self._text_pixmap(it["word"], it["font"], current, rgb, current)
        dpr = pm.devicePixelRatio()
        pw, ph = pm.width() / dpr * scale, pm.height() / dpr * scale  # escala con el viaje (suavizada)
        below = it["seed"] % 2 == 1
        y = pt.y() + r - 2 if below else pt.y() - r + 2 - ph
        p.setOpacity(min(1.0, it["alpha"] * fade))
        p.drawPixmap(QRectF(pt.x() - pw / 2, y, pw, ph), pm, QRectF(pm.rect()))
        p.setOpacity(1.0)

    def _sparks(self, p, pt, r, age, seed, fade):
        t = age / SPARKS
        if not 0 <= t < 1:
            return
        rs = self._rand(seed * 31 + 7, 17)
        p.setPen(Qt.NoPen)
        p.setBrush(self._color((1 - t) * fade, (255, 255, 255)))
        for k in range(6 + int(rs[16] * 3)):
            ang = rs[k] * 2 * math.pi
            d = r * (1.2 + 3.5 * _out_cubic(t)) * (0.7 + 0.5 * rs[k + 8 if k + 8 < 16 else k])
            p.drawEllipse(QPointF(pt.x() + d * math.cos(ang), pt.y() + d * math.sin(ang)), 1.6, 1.6)

    def _leaving(self, p, P, age):
        """Estrofa anterior según el estilo de la transición; devuelve dónde estaban sus estrellas."""
        old = self.old_items
        pts = [(it["dx"], it["dy"]) for it in old]
        if not old or P is None or age >= transitions.out_time(P):
            self.leaving_now = []
            return pts
        w, h = self.width(), self.height()
        moved = []
        for i, it in enumerate(old):
            x, y, s, sa, la, trail = transitions.out_state(P, age, it["dx"], it["dy"], i, len(old), w, h)
            m = dict(it)  # parte del estado real que tenía en pantalla (sin saltos si cambió a mitad)
            m.update(dx=x, dy=y, s=it["s"] * s, sa=it["sa"] * sa, la=it["la"] * la, trail=trail, current=False,
                     ox=it["dx"], oy=it["dy"])
            moved.append(m)
        self._draw(p, moved, None)
        self.leaving_now = moved  # su estado real ahora, por si empieza otra transición a mitad
        return pts

    def _extras(self, p, P, age, old_pts, new_pts):
        """Efectos propios de cada transición: estelas, chispas, motas, anillos, destello."""
        if P is None or age > transitions.total(P, len(new_pts)) + 0.1:
            return
        w, h = self.width(), self.height()
        tint = tuple(round(0.7 * 255 + 0.3 * v) for v in self.rgb)
        p.setPen(Qt.NoPen)
        for prim in transitions.extras(P, age, old_pts, new_pts, w, h):
            kind = prim[0]
            if kind == "line":
                p.setPen(QPen(self._color(prim[5], tint), 1.2))
                p.drawLine(QPointF(prim[1], prim[2]), QPointF(prim[3], prim[4]))
                p.setPen(Qt.NoPen)
            elif kind == "dot":
                p.setBrush(self._color(prim[4], tint))
                p.drawEllipse(QPointF(prim[1], prim[2]), prim[3], prim[3])
            elif kind == "ring":  # brillo ancho y suave + trazo fino
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(self._color(prim[4] * 0.25, tint), 7.0))
                p.drawEllipse(QPointF(prim[1], prim[2]), prim[3], prim[3])
                p.setPen(QPen(self._color(prim[4], tint), 2.0))
                p.drawEllipse(QPointF(prim[1], prim[2]), prim[3], prim[3])
                p.setPen(Qt.NoPen)
            elif kind == "flash":
                p.fillRect(self.rect(), self._color(prim[1], tint))

    def _message(self, p, text, y=0.5, alpha=0.6, size=None, rgb=None):
        size = size or max(14, min(32, self.height() * 0.035))
        pm = self._text_pixmap(text, max(11, size), False, rgb or self.rgb, False)
        dpr = pm.devicePixelRatio()
        pw, ph = pm.width() / dpr, pm.height() / dpr
        p.setOpacity(alpha)
        p.drawPixmap(QRectF((self.width() - pw) / 2, self.height() * y - ph / 2, pw, ph), pm, QRectF(pm.rect()))
        p.setOpacity(1.0)
