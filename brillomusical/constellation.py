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

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontInfo, QFontMetricsF, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import backdrop, cover, effects, history, kinetic, layout, lyrics, media, panels, quality, ribbon, transitions, wheel
from .color import FALLBACK

# tamaños en fracción de la altura de la ventana: (estrella, texto)
SIZE_CURRENT, SIZE_PREV, SIZE_REST = (0.045, 0.06), (0.025, 0.035), (0.012, 0.022)
REST_ALPHA, OLD_ALPHA, OLD_AFTER = 0.45, 0.25, 12  # las palabras con más de 12 de antigüedad, más tenues
DRAW_LINE = 0.35  # trazo de la línea hacia la palabra nueva
FLASH, SPARKS = 0.3, 0.5
BG_STARS, TWINKLERS = 120, 20
TOAST = 1.5  # avisos breves (desfase, modo de fondo)
SEARCHING = "Buscando letra…"
HELP = "Espacio play/pausa · N/P siguiente/anterior · Mayús+←/→ ±10 s · M menú · F pantalla completa · L estilo · B fondo · C carátula · T transición · ←/→ sincronizar · H atajos"
FIRST_TIP = "Acerca el ratón a los bordes: menú arriba, controles a la izquierda, canciones a la derecha"
CURSOR_HIDE = 2500  # ms quieto en pantalla completa antes de ocultar el cursor
KIN_SIZE, KIN_Y, KIN_W = 0.075, 0.46, 0.82  # Latido: letra (·alto), centro vertical y anchura máxima (·ancho)


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
    control = Signal(str)  # play / next / prev / back / fwd hacia YouTube Music
    style_changed = Signal(str)  # L: Automático / Constelación / Latido / Cinta
    quality_changed = Signal(str)

    def __init__(self, settings, frames, governor):
        super().__init__()
        self.settings = settings
        self.frames = frames
        self.quality = governor
        self.style_setting = settings.value("lyrics_style", "constellation")  # lo elegido (puede ser "auto")
        if self.style_setting not in kinetic.SETTINGS:
            self.style_setting = "constellation"
        self.style = self.style_setting if self.style_setting != "auto" else "constellation"  # lo que se pinta
        self.kin = {}  # Latido: (efecto, fuente) elegidos al aparecer cada línea
        self.glyphs, self.rib, self.rib_track = {}, None, None  # Cinta: letras sueltas, texto y curva en caché
        self.beat_t = -1e9
        self.wheel = wheel.Wheel()
        self.panels = panels.Panels()
        self.history = history.History()
        self.wheel_on = self.skip = False
        self.setMouseTracking(True)
        self.cursor_timer = QTimer(self, singleShot=True, interval=CURSOR_HIDE, timeout=self._hide_cursor)
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
                self.history.add(key, snap["title"], snap["artist"])
            self.cover.set_track(key, snap["title"], snap["artist"], snap["album"])
            if self.hd_key != key and snap.get("art_id"):  # solo convierte si cambió la portada
                if snap.get("backdrop"):
                    self.backdrop.set_art(snap["art_id"], *snap["backdrop"])
                if snap.get("cover"):
                    self.cover.set_art(snap["art_id"], *snap["cover"])
                    self._thumb(key)
        self._update_timer()
        self.update()

    def set_lyrics(self, status, lines):
        self.status, self.lines = status, lines
        self.times = [t for t, _ in lines]
        self.groups = layout.stanzas(lines)
        self.chorus = layout.chorus(lines, self.groups)  # estribillos: transición de impacto en Automática
        self.gaps = layout.gaps(lines)  # instrumentales largos: carátula grande
        self.stanza_cache.clear()
        self.kin.clear()
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
        self._thumb(key)
        self.update()

    def _thumb(self, key):
        """Miniatura de la portada actual para "Sonó antes" (pequeña: no guarda la de 1000 px)."""
        if self.cover.img is not None:
            self.history.set_thumb(key, self.cover.img.scaled(192, 192, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))

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
                and (self.backdrop.setting in ("beat", "auto") or self.trans_setting == "auto"
                     or self.style != "constellation"))

    def set_energy(self, e):
        self.backdrop.energy = e

    def beat(self):
        self.backdrop.beat()
        self.beat_t = time.monotonic()

    def set_style(self, setting, show=False):
        if setting in kinetic.SETTINGS:
            self.style_setting = setting
            self.settings.setValue("lyrics_style", setting)
            if setting != "auto":  # en Automático sigue el que hay hasta que llegue el género
                self._apply_style(setting)
            if show:
                self.toast(f"Estilo: {kinetic.SETTING_NAMES[setting]}")

    def set_auto_style(self, style, genre):
        """Estilo que pide el género de la canción (solo con la opción Automático)."""
        style = style or "constellation"  # género desconocido o sin género: el principal
        if self.style_setting == "auto" and style != self.style:
            self._apply_style(style)
            self.toast(f"{kinetic.STYLE_NAMES[style]} · {genre}" if genre else f"Estilo: {kinetic.STYLE_NAMES[style]}")

    def _apply_style(self, style):
        self.style = style
        # al volver a Constelación no hay transición desde una estrofa vieja
        self.shown, self.last_items, self.old_items, self.leaving_now = None, [], [], []
        self.update()

    def set_quality(self, setting, show=False):
        if setting in quality.SETTINGS:
            self.quality.setting = setting
            self.settings.setValue("quality", setting)
            if show:
                self.toast(f"Calidad: {quality.NAMES[setting]}")

    def toggle_fullscreen(self):
        if not self.isFullScreen():
            self.normal_geo = self.saveGeometry()  # la que se guarda al cerrar: no arranca a pantalla completa
        self.setWindowState(self.windowState() ^ Qt.WindowFullScreen)  # vuelve a normal o maximizada
        if self.isFullScreen():
            self.toast("Esc o F11 para salir de pantalla completa", 2.5)
            self.cursor_timer.start()
        else:
            self.unsetCursor()

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
        if self.animating or self.wheel_on:
            self.skip = self.quality.light and not self.skip  # Ligera: uno de cada dos (30 fps)
            if not self.skip:
                self.update()

    def _wheel_frames(self):
        now = time.monotonic()
        on = self.wheel.busy(now) or self.panels.busy(now)  # rueda y paneles: fotogramas solo mientras se animan
        if on != self.wheel_on:
            self.wheel_on = on
            self.frames.want("wheel", on)

    def cycle(self, action):
        """Siguiente opción de una acción (teclas y rueda); avisa a la bandeja para marcarla."""
        if action == "bg":
            self.set_bg(backdrop.next_mode(self.backdrop.setting), show=True)
            self.bg_changed.emit(self.backdrop.setting)
        elif action == "transition":
            self.set_transition(transitions.next_setting(self.trans_setting), show=True)
            self.transition_changed.emit(self.trans_setting)
        elif action == "cover":
            self.set_cover(cover.next_mode(self.cover.mode), show=True)
            self.cover_changed.emit(self.cover.mode)
        elif action == "style":
            self.set_style(kinetic.next_style(self.style_setting), show=True)
            self.style_changed.emit(self.style_setting)
        elif action == "quality":
            self.set_quality(quality.next_setting(self.quality.setting), show=True)
            self.quality_changed.emit(self.quality.setting)
        elif action == "fullscreen":
            self.toggle_fullscreen()

    def wheel_value(self, action):
        style = kinetic.STYLE_NAMES[self.style]
        return {"style": f"Automático · {style}" if self.style_setting == "auto" else style, "transition": transitions.SETTING_NAMES[self.trans_setting],
                "bg": backdrop.NAMES[self.backdrop.setting], "cover": cover.NAMES[self.cover.mode],
                "quality": quality.NAMES[self.quality.setting],
                "fullscreen": "salir" if self.isFullScreen() else "activar"}[action]

    KEYS = {Qt.Key_B: "bg", Qt.Key_T: "transition", Qt.Key_C: "cover", Qt.Key_L: "style",
            Qt.Key_F: "fullscreen", Qt.Key_F11: "fullscreen"}

    CONTROLS = {Qt.Key_Space: "play", Qt.Key_N: "next", Qt.Key_P: "prev"}

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Left, Qt.Key_Right) and e.modifiers() & Qt.ShiftModifier:
            self.control.emit("fwd" if e.key() == Qt.Key_Right else "back")
        elif e.key() in self.CONTROLS and e.isAutoRepeat():
            pass  # mantener Espacio o N no alterna ni salta sin parar
        elif e.key() in self.CONTROLS:
            self.control.emit(self.CONTROLS[e.key()])
        elif e.key() in (Qt.Key_Left, Qt.Key_Right):
            self.offset_step.emit(0.1 if e.key() == Qt.Key_Right else -0.1)
        elif e.key() in self.KEYS:
            self.cycle(self.KEYS[e.key()])
        elif e.key() == Qt.Key_H:
            self.toast(HELP, 6)
        elif e.key() == Qt.Key_M:
            self.wheel.toggle()  # abierta con tecla: no se cierra sola hasta que el ratón pase y se vaya
            self._wheel_frames()
            self.update()
        elif e.key() == Qt.Key_Escape:
            if self.wheel.target:
                self.wheel.toggle(False)
                self._wheel_frames()
            elif self.isFullScreen():
                self.toggle_fullscreen()
        else:
            super().keyPressEvent(e)

    # --- ratón: rueda, doble clic y cursor en pantalla completa ---
    def mouseMoveEvent(self, e):
        x, y, now = e.position().x(), e.position().y(), time.monotonic()
        pn = self.panels
        before = (self.wheel.near, self.wheel.hover, pn.near_l, pn.near_r, pn.btn, pn.item)
        self.wheel.move(x, y, self.width(), now)
        pn.move(x, y, self.width(), self.height(), now, block=bool(self.wheel.target))
        self._wheel_frames()
        if self.isFullScreen():
            self.unsetCursor()
            self.cursor_timer.start()
        if (self.wheel.near, self.wheel.hover, pn.near_l, pn.near_r, pn.btn, pn.item) != before and not self.animating:
            self.update()  # sonando ya repinta el reloj

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            x, y = e.position().x(), e.position().y()
            action = self.wheel.press(x, y, self.width())
            hit = None if action else self.panels.press(x, y, self.width(), self.height(), time.monotonic())
            if action and action != "toggle":
                self.cycle(action)
            elif hit and hit[0] == "control":
                self.control.emit(hit[1])
            elif hit:  # "Sonó antes": esa canción en YouTube Music, en el navegador
                it = self.history.before()[hit[1]]
                QDesktopServices.openUrl(QUrl(history.search_url(it["title"], it["artist"])))
            self._wheel_frames()
            self.update()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        x, y = e.position().x(), e.position().y()
        if e.button() != Qt.LeftButton:
            return
        if self.panels.hit(x, y, self.width(), self.height()):
            self.mousePressEvent(e)  # dos clics rápidos en "siguiente" o "+10 s" cuentan dos veces
        elif not self.wheel.hit(x, y, self.width()):
            self.toggle_fullscreen()

    def leaveEvent(self, e):
        now = time.monotonic()
        self.wheel.move(-1e4, -1e4, self.width(), now)
        self.panels.move(self.width() / 2, -1e4, self.width(), self.height(), now)
        self._wheel_frames()
        super().leaveEvent(e)

    def _hide_cursor(self):
        if self.isFullScreen() and not self.wheel.target and not self.panels.left and not self.panels.right:
            self.setCursor(Qt.BlankCursor)

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
            self.toast(FIRST_TIP, 6)  # corto: el de atajos taparía el botón de la rueda
            self.wheel.hint_until = self.panels.hint_until = time.monotonic() + 4  # que se vea dónde está todo
            self._wheel_frames()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._update_timer()
        self.wheel.reset()  # oculta no se pinta: una animación a medias pediría fotogramas para siempre
        self.panels.reset()
        self._wheel_frames()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange:  # minimizar / restaurar
            self._update_timer()
            if self.isMinimized():
                self.wheel.reset()
                self.panels.reset()
                self._wheel_frames()
            if not self.isFullScreen():  # salió por la bandeja, Win+↓…: el cursor vuelve
                self.cursor_timer.stop()
                self.unsetCursor()

    def resizeEvent(self, e):
        self.bg = self.nebula = None
        self.glyphs.clear()
        self.labels.clear()  # los tamaños de letra dependen de la altura
        self.stanza_cache.clear()  # y la esquina reservada para la tarjeta
        super().resizeEvent(e)

    def closeEvent(self, e):
        self.settings.setValue("lyrics_geometry", self.normal_geo if self.isFullScreen() else self.saveGeometry())
        super().closeEvent(e)

    # --- cachés ---
    def _font(self, px, bold=False, kind=""):
        """kind: "" normal, "light" fina, "heavy" Bahnschrift gruesa (Latido intenso)."""
        key = (round(px), bold, kind)
        if key not in self.fonts:
            f = QFont(self.family)
            if kind == "heavy":
                f = QFont("Bahnschrift")  # Windows 10 1709+; si falta, la de siempre
                if not f.exactMatch():
                    f = QFont(self.family)
            elif kind == "condensed":  # Cinta: palo seco estrecho y grueso, como el del vídeo de referencia
                f = QFont("Bahnschrift Condensed")
                if "Bahnschrift" not in QFontInfo(f).family():
                    f = QFont("Bahnschrift")
                    f.setStretch(QFont.Condensed)
                if "Bahnschrift" not in QFontInfo(f).family():
                    f = QFont("Impact")  # en todos los Windows
            f.setPixelSize(max(8, key[0]))
            f.setWeight({"light": QFont.Light, "heavy": QFont.Bold, "condensed": QFont.Bold}.get(kind, QFont.DemiBold if bold else QFont.Normal))
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
        t0 = time.perf_counter()
        now = time.monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)  # halo, nebulosa y etiquetas escaladas o en posición decimal
        self._paint(p, now)
        w = self.width()
        if now - self.toast_t < self.toast_secs and self.wheel.open == 0:  # aviso (con la rueda, su etiqueta) en una pastilla oscura (legible sobre portadas claras)
            pm = self._text_pixmap(self.toast_text, 13, False, (255, 255, 255), False)
            tw, th = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
            pill = QRectF(w - tw - 16 - 12, 16 - 6, tw + 24, th + 12)
            p.setOpacity(0.75 * min(1.0, 3 * (1 - (now - self.toast_t) / self.toast_secs)))
            path = QPainterPath()
            path.addRoundedRect(pill, 8, 8)
            p.fillPath(path, QColor(0, 0, 0, 90 if self.style != "ribbon" else 200))
            p.drawPixmap(QPointF(pill.x() + 12, pill.y() + 6), pm)
            p.setOpacity(1.0)
        snap = self.snap
        self.panels.draw(p, self.width(), self.height(), now, {
            "playing": bool(snap) and snap["playing"], "rgb": self.rgb, "paper": self.style == "ribbon",
            "style": self.style, "items": self.history.before(), "thumb": lambda it, side: it["thumb"],
            "label": lambda t, px, bold: self._text_pixmap(t, px, bold, (255, 255, 255), False),
            "beat": effects.env(now - self.beat_t, 0.04, 0.22), "light": self.quality.light})
        if self.wheel.open > 0:  # la letra se apaga un poco bajo la rueda abierta
            p.fillRect(self.rect(), QColor(0, 0, 0, round(110 * self.wheel.open)))
        self.wheel.draw(p, self.width(), self.rgb, self.wheel_value,
                        lambda t: self._text_pixmap(t, 13, True, (255, 255, 255), False), now)
        p.end()
        self._wheel_frames()
        if self.animating and self.quality.feed((time.perf_counter() - t0) * 1000, now):
            self.toast("Calidad ligera para ir más fluido", 3)
            self.quality_changed.emit(self.quality.setting)

    def _paint(self, p, now):
        w, h = self.width(), self.height()
        light = self.quality.light
        if self.style == "ribbon":
            return self._ribbon(p, now, w, h)
        if self.bg is None:
            self._build_bg()
        age = now - self.trans_t0  # tiempo desde el último cambio de estrofa
        push = transitions.push(self.trans_P, age) if self.trans_P and not light else 0.0  # Ligera: sin ampliar el fondo
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
        if not light:  # Ligera: sin estrellas que titilan ni nebulosa
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
        if not snap:
            return self._message(p, "Pon algo en YouTube Music ♪")
        if snap["ad"]:
            return self._message(p, "Anuncio · la música vuelve enseguida")
        if self.style == "kinetic" and self.lines:
            return self._kinetic(p, pos, now, w, h, gap, hero)
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

    def _glyph(self, ch, px, rgb):
        """Una letra de la Cinta, sin sombra, en caché (se transforma una a una cada fotograma)."""
        key = (ch, round(px), rgb, self.devicePixelRatioF())  # otra pantalla con otra escala: nítidas
        pm = self.glyphs.get(key)
        if pm is None:
            if len(self.glyphs) > 400:
                self.glyphs.clear()
            font = self._font(px, True, "condensed")
            fm = QFontMetricsF(font)
            dpr = self.devicePixelRatioF()
            pm = QPixmap(math.ceil((fm.horizontalAdvance(ch) + 4) * dpr), math.ceil((fm.height() + 4) * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.TextAntialiasing)
            q.setFont(font)
            q.setPen(QColor(*rgb))
            q.drawText(QPointF(2, 2 + fm.ascent()), ch)
            q.end()
            self.glyphs[key] = pm
        return pm

    def _ribbon_text(self, px, fm, title):
        """(tiempos, letras por palabra, anchos, desplazamientos, paso) del texto de la Cinta; una vez por canción y tamaño."""
        snap = self.snap
        key = (round(px), title)
        if self.rib and self.rib[0] == key and self.rib[2] is self.lines:
            return self.rib[1]
        words = [(t, x.upper()) for i, (_, text) in enumerate(self.lines)
                 for t, x in zip(lyrics.word_times(self.lines, i), lyrics.words(text))]
        step = ribbon.WORD_STEP
        if not words:  # sin letra: el título repetido, avanzando sin parar (como en el vídeo)
            words = [(k * 2.5, title) for k in range(int((snap["duration"] or 600) / 2.5) + 3)]
            step = None
        elif words[0][0] > 0:
            words.insert(0, (0.0, title))  # antes de la primera línea pasa el título
        space = (0.12 if step else 0.05) * px  # casi pegadas, como en el vídeo
        times, lets, widths, offs, m = [], [], [], [], 0.0
        for t, x in words:
            adv = [fm.horizontalAdvance(x[:j]) for j in range(len(x) + 1)]
            times.append(t)
            lets.append([(ch, adv[j], adv[j + 1] - adv[j]) for j, ch in enumerate(x)])
            widths.append(adv[-1])
            offs.append(m)
            m += adv[-1] + space
        self.rib = (key, (times, lets, widths, offs, step), self.lines)
        return self.rib[1]

    def _ribbon(self, p, now, w, h):
        """Cinta: papel claro, la letra recorriendo una cinta en S que se retuerce, y el rótulo del título al empezar."""
        p.fillRect(self.rect(), QColor(*ribbon.PAPER))
        snap = self.snap
        if not snap:
            return self._message(p, "Pon algo en YouTube Music ♪", rgb=ribbon.INK)
        if snap["ad"]:
            return self._message(p, "Anuncio · la música vuelve enseguida", rgb=ribbon.INK)
        pos, light = self.position(), self.quality.light
        px = (0.18 if light else 0.16) * h  # Ligera: letra más grande, menos letras que mover
        font = self._font(px, True, "condensed")
        fm = QFontMetricsF(font)
        title = snap["title"].upper()
        times, lets, widths, offs, step = self._ribbon_text(px, fm, title)
        if not self.rib_track or self.rib_track[0] != (w, h):
            self.rib_track = ((w, h), ribbon.track(w, h))
        tr = self.rib_track[1]
        length = tr[0][-1]
        anchor = ribbon.ANCHOR * length
        m_now = ribbon.scroll(pos, times, offs, widths, step)
        cur = bisect.bisect_right(times, pos) - 1
        acc = QColor(*self.rgb)  # acento: la portada oscurecida hasta que se lea sobre el papel
        acc.setHslF(acc.hslHueF(), max(0.5, acc.hslSaturationF()), min(0.42, acc.lightnessF()))
        accent = (acc.red(), acc.green(), acc.blue())
        beat = 0.0 if light else effects.env(now - self.beat_t, 0.04, 0.22)
        self._speakers(p, w, h, now, beat)
        p.setRenderHint(QPainter.SmoothPixmapTransform, not light)
        # la cinta aparece cuando se va el rótulo (si se entra a mitad de canción, ya está)
        fade = min(1.0, max(0.0, (pos - ribbon.CARD_END) / 0.4)) if pos < ribbon.CARD_END + 0.4 else 1.0
        p.setOpacity(fade)
        lo, hi = m_now - anchor, (m_now + length - anchor) if fade > 0 else -1e18  # bajo el rótulo, nada
        for i in range(max(0, bisect.bisect_right(offs, lo) - 1), len(offs)):
            if offs[i] > hi:
                break
            for ch, dx, adv in lets[i]:
                a = ribbon.at(tr, anchor + offs[i] + dx + adv / 2 - m_now)
                if a is None or ch == " ":
                    continue
                x, y, ang, u = a
                c = math.cos(ribbon.twist(u, 0.0 if light else now, beat))
                if abs(c) < 0.08 or (c < 0 and light):  # de canto no se ve; en Ligera, sin reverso
                    continue
                pm = self._glyph(ch, px, (accent if i == cur else ribbon.INK) if c > 0 else ribbon.BACK)
                dpr = pm.devicePixelRatio()
                p.save()
                p.translate(x, y)
                p.shear(0, max(-1.2, min(1.2, math.tan(ang))))  # se inclina con la curva, trazos verticales
                p.scale(1, c)  # media vuelta: escala negativa = reverso en espejo
                p.drawPixmap(QPointF(-pm.width() / dpr / 2, -pm.height() / dpr / 2), pm)
                p.restore()
        p.setOpacity(1.0)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self._tide(p, w, h, 0.0 if light and not self.animating else now, beat, 24 if light else 64)
        gap = next(((a, b) for a, b in self.gaps if a <= pos <= b), None)
        if gap and gap[1] - gap[0] >= 4:  # instrumental: las flechas cruzan por el centro
            k = min(1.0, (pos - gap[0]) / 0.9, (gap[1] - pos) / 0.9)
            self._chevrons(p, w, 0.40 * h, 0.2 * h, pos, 0.0, 0.9 * max(0.0, k))
        if not self.lines and self.status:
            self._message(p, self.status, y=0.86, alpha=0.5, size=0.022 * h, rgb=ribbon.INK)
        self._ribbon_card(p, pos, w, h, title, snap["artist"])

    def _chevrons(self, p, w, y, bh, pos, shift, alpha=1.0):
        """Franja de flechas ››› de alto bh que avanza una flecha cada 0,4 s."""
        gap, thick = 0.9 * bh, 0.45 * bh
        chev = QPainterPath()
        chev.addPolygon([QPointF(0, 0), QPointF(thick, 0), QPointF(thick + bh / 2, bh / 2), QPointF(thick, bh),
                         QPointF(0, bh), QPointF(bh / 2, bh / 2)])
        p.setOpacity(alpha)
        x = shift + (pos / 0.4 * gap) % gap - gap
        while x < w:
            p.fillPath(chev.translated(x, y), QColor(*ribbon.INK))
            x += gap
        p.setOpacity(1.0)

    def _speakers(self, p, w, h, now, beat):
        """Los dos aros del altavoz del vídeo: laten con el golpe y sueltan una onda fina."""
        age = now - self.beat_t
        p.setOpacity(1 - 0.7 * max(self.panels.left, self.panels.right))  # no compiten con los paneles
        for cx, cy in ((0.12 * w, 0.22 * h), (0.80 * w, 0.76 * h)):
            r = 0.085 * h
            thick = 0.035 * h * (1 + 0.08 * beat)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(*ribbon.INK), thick))
            p.drawEllipse(QPointF(cx, cy), r, r)
            if age < 0.7 and not self.quality.light:
                t = age / 0.7
                p.setPen(QPen(QColor(*ribbon.INK, round(160 * (1 - t))), 1.5))
                rr = r + thick / 2 + 0.06 * h * (1 - (1 - t) ** 2)
                p.drawEllipse(QPointF(cx, cy), rr, rr)
        p.setOpacity(1.0)

    def _tide(self, p, w, h, now, beat, n):
        """Marea de tinta abajo (el agua del vídeo): dos ondas sumadas que crecen con el golpe."""
        amp = 0.012 * h * (1 + 1.5 * beat)
        path = QPainterPath(QPointF(0, h))
        for i in range(n + 1):
            x = w * i / n
            y = 0.95 * h + amp * (math.sin(x / w * 7 + now * 1.3) + 0.6 * math.sin(x / w * 13 - now * 0.9))
            path.lineTo(x, y)
        path.lineTo(w, h)
        path.closeSubpath()
        p.fillPath(path, QColor(*ribbon.INK))

    def _ribbon_card(self, p, pos, w, h, title, artist):
        """Rótulo al empezar la canción: flechas que cruzan arriba, barra y título letra a letra."""
        c = ribbon.card(pos)
        if c is None:
            return
        arrows, bar, frac, out = c
        ink = QColor(*ribbon.INK)
        # franja de chevrones ››› arriba, entrando por la izquierda y saliendo por la derecha
        self._chevrons(p, w, -0.04 * h, 0.28 * h, pos, -w * (1 - arrows) + w * 1.1 * out)
        # título: barra vertical y como mucho 2 filas que se escriben letra a letra
        px = 0.10 * h
        font = self._font(px, True, "condensed")
        fm = QFontMetricsF(font)
        words = title.split()
        if not words:
            return
        rows = [" ".join(words[i] for i in r)
                for r in kinetic.wrap([fm.horizontalAdvance(x) for x in words], fm.horizontalAdvance(" "), 0.8 * w)][:2]
        lh = px * 1.0
        x0, top = 0.06 * w, 0.62 * h - len(rows) * lh
        p.fillRect(QRectF(x0, top, max(2.0, 0.004 * h), bar * (len(rows) * lh + 0.05 * h)), ink)
        shown = frac * sum(len(r) for r in rows)
        p.setFont(font)
        p.setPen(ink)
        tx = x0 + 0.012 * w
        for r, row in enumerate(rows):
            n = max(0.0, min(len(row), shown))
            shown -= len(row)
            vis = fm.horizontalAdvance(row[:math.ceil(n)]) * (1 - out)  # salida: se borra de derecha a izquierda
            if vis <= 0:
                continue
            p.save()
            p.setClipRect(QRectF(tx, top + r * lh - 0.2 * px, vis, lh + 0.4 * px))
            p.drawText(QPointF(tx, top + r * lh + fm.ascent() * 0.85), row)
            p.restore()
        if artist:
            p.setOpacity(0.6 * bar * (1 - out))
            p.setFont(self._font(0.03 * h, False))
            p.drawText(QPointF(tx, top + len(rows) * lh + 0.045 * h), artist)
            p.setOpacity(1.0)

    def _kinetic(self, p, pos, now, w, h, gap, hero):
        """Latido: la línea que suena, grande y centrada; la anterior arriba y la siguiente abajo, tenues."""
        idx = self.line_index(pos)
        words = lyrics.words(self.lines[idx][1]) if idx >= 0 else []
        if gap or not words:
            if not hero:
                self._message(p, "♪")
            return
        start = self.lines[idx][0]
        if idx not in self.kin:  # efecto y fuente fijos por línea: un cambio de ambiente no la hace saltar
            seed = zlib.crc32(f"{self.snap['title']}|{idx}".encode())
            self.kin[idx] = (kinetic.pick(seed, self.mood), {"calm": "light", "intense": "heavy"}.get(self.mood, ""))
        effect, kind = self.kin[idx]
        if kind == "heavy":
            words = [x.upper() for x in words]
        times = lyrics.word_times(self.lines, idx)
        end = self.lines[idx + 1][0] if idx + 1 < len(self.lines) else start + 6
        light = self.quality.light
        tint = tuple(round(c + (255 - c) * 0.55) for c in self.rgb)  # pastel: acompaña sin competir con la actual
        fit = (idx, w, h)
        px = self.kin.get(fit) or KIN_SIZE * h
        for _ in range(5):  # como mucho 2 filas: si no caben, letra más pequeña (se calcula una vez por línea)
            pms = [self._text_pixmap(x, px, True, (255, 255, 255), False, kind) for x in words]
            dpr = pms[0].devicePixelRatio()
            widths = [pm.width() / dpr - 8 for pm in pms]  # sin el margen de 4 px de cada lado
            space = 0.28 * px
            rows = kinetic.wrap(widths, space, KIN_W * w)
            if fit in self.kin or len(rows) <= 2 or px < 0.035 * h:
                break
            px *= 0.85
        self.kin[fit] = px
        lh = px * 1.3
        top = KIN_Y * h - lh * len(rows) / 2
        energy, beat = self.backdrop.energy, effects.env(now - self.beat_t, 0.04, 0.18)
        line_age = pos - start
        for r, row in enumerate(rows):
            x = (w - sum(widths[i] for i in row) - space * (len(row) - 1)) / 2
            for i in row:
                we = times[i + 1] if i + 1 < len(times) else end
                tw = pos - times[i]
                dy, scale, alpha, fill = kinetic.word_state(effect, i, tw, min(we - times[i], 1.5), line_age,
                                                            energy, beat, now)
                sung = pos >= we and fill is None
                if sung:
                    pm = self._text_pixmap(words[i], px, True, tint, False, kind)
                elif tw >= 0 and not light:  # la que suena, con halo del color de la portada
                    pm = self._text_pixmap(words[i], px, True, (255, 255, 255), True, kind)
                else:
                    pm = pms[i]
                pw, ph = pm.width() / dpr * scale, pm.height() / dpr * scale
                cx, cy = x + widths[i] / 2, top + r * lh + lh / 2 + dy * px
                target = QRectF(cx - pw / 2, cy - ph / 2, pw, ph)
                p.setOpacity(min(1.0, alpha * (kinetic.PENDING_ALPHA if fill is not None else 1.0)))
                p.drawPixmap(target, pm, QRectF(pm.rect()))
                if fill:  # barrido: la parte ya cantada encima, a plena luz
                    p.save()
                    p.setClipRect(QRectF(target.x(), target.y(), (4 + widths[i] * fill) * scale, ph))
                    p.setOpacity(min(1.0, alpha))
                    p.drawPixmap(target, pm, QRectF(pm.rect()))
                    p.restore()
                x += widths[i] + space
        # contexto: la línea anterior arriba y la siguiente abajo
        k = min(1.0, max(0.0, line_age / kinetic.LINE_IN))
        small = max(11.0, 0.032 * h)
        for j, alpha, above in ((idx - 1, 0.22, True), (idx + 1, 0.35, False)):
            ctx = " ".join(lyrics.words(self.lines[j][1])) if 0 <= j < len(self.lines) else ""
            if not ctx:
                continue
            pm = self._text_pixmap(ctx, small, False, (255, 255, 255), False)
            pw, ph = pm.width() / dpr, pm.height() / dpr
            f = min(1.0, 0.9 * w / pw)
            y = top - ph * f - 0.3 * small if above else top + lh * len(rows) + 0.3 * small
            p.setOpacity(alpha * k)
            p.drawPixmap(QRectF((w - pw * f) / 2, y, pw * f, ph * f), pm, QRectF(pm.rect()))
        p.setOpacity(1.0)

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
                if not self.quality.light:
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

    def _text_pixmap(self, text, px, bold, rgb, glow, kind=""):
        """Texto dibujado una vez en una imagen: se mueve con precisión subpíxel sin vibrar."""
        key = (text, round(px), bold, rgb, glow, kind)
        pm = self.labels.get(key)
        if pm is None:
            font = self._font(px, bold, kind)
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
