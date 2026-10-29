"""Carátula nítida en la ventana de letras: tarjeta en la esquina, compacta arriba o marca de agua.

Todo lo estático se dibuja una vez en un QPixmap (se rehace al cambiar de canción, portada,
tamaño o color); en cada fotograma solo se vuelca y se pinta la barra de progreso.
"""
import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPixmap, QRadialGradient

MODES = ("card", "top", "center", "hidden")
NAMES = {"card": "Tarjeta (abajo izquierda)", "top": "Arriba a la izquierda", "center": "Centro (marca de agua)",
         "hidden": "Oculta"}
SHADOW = 18
OUT_T, IN_DELAY, IN_T = 0.2, 0.12, 0.45  # cambio de canción en la tarjeta
ART_FADE = 1.5  # marca de agua
MARK_ALPHA = 0.20
HERO_DELAY, HERO_GO, HERO_BACK = 0.3, 0.9, 0.7  # carátula grande: espera, ida al centro, vuelta


# --- lógica pura ---
def next_mode(mode):
    return MODES[(MODES.index(mode) + 1) % len(MODES)] if mode in MODES else MODES[0]


def card_geometry(w, h):
    """Medidas de la tarjeta (px lógicos): carátula a, relleno, texto y posición abajo a la izquierda."""
    a = max(48.0, min(150.0, 0.14 * h))
    pad = 0.18 * a
    m = max(16.0, 0.035 * h)
    text_w = max(0.0, min(2.6 * a, 0.30 * w - a - 3 * pad))
    cw, ch = a + 3 * pad + text_w, a + 2 * pad
    return {"a": a, "pad": pad, "m": m, "text_w": text_w, "w": cw, "h": ch, "x": m, "y": h - m - ch}


def avoid_rect(mode, w, h):
    """Zona (normalizada) que la constelación no debe ocupar; solo depende del modo y del tamaño."""
    if mode != "card":
        return None
    g = card_geometry(w, h)
    # margen extra: la palabra se escribe al lado de su estrella y no debe montarse sobre la tarjeta
    return 0.0, max(0.0, g["y"] / h - 0.06), min(1.0, (g["x"] + g["w"]) / w + 0.06), 1.0


def hero_geometry(w, h, native):
    """Carátula grande (sin letra): (x, y, lado), centrada en horizontal y a 0,40·h; nunca > 2,5× la real."""
    side = min(0.42 * h, 0.32 * w, 2.5 * native)
    return w / 2 - side / 2, 0.40 * h - side / 2, side


def origin_rect(mode, w, h, native=1000):
    """Dónde está ahora la carátula según su posición (de ahí sale hacia el centro)."""
    if mode == "card":
        g = card_geometry(w, h)
        return g["x"] + g["pad"], g["y"] + g["pad"], g["a"]
    if mode == "top":
        return 16.0, 10.0, max(28.0, min(56.0, 0.05 * h))
    if mode == "center":
        side = 0.55 * h
        return (w - side) / 2, (h - side) / 2, side
    x, y, s = hero_geometry(w, h, native)  # oculta: aparece casi en su sitio
    return x + 0.05 * s, y + 0.05 * s, 0.9 * s


def arc_lerp(a, b, e, lift):
    """Interpola dos rectángulos (x, y, lado) subiendo en arco `lift` px a mitad de camino."""
    if e <= 0:
        return a
    x = a[0] + (b[0] - a[0]) * e
    y = a[1] + (b[1] - a[1]) * e - lift * math.sin(math.pi * e)
    return x, y, a[2] + (b[2] - a[2]) * e


def progress(pos, duration):
    return None if not duration else max(0.0, min(1.0, pos / duration))


def _out_cubic(t):
    return 1 - (1 - t) ** 3


def _bar(p, rect, prog, rgb):
    """Barra de progreso con extremos redondeados (misma en la tarjeta y en la carátula grande)."""
    r = rect.height() / 2
    track = QPainterPath()
    track.addRoundedRect(rect, r, r)
    p.fillPath(track, QColor(255, 255, 255, 46))
    if prog > 0:
        fill = QPainterPath()
        fill.addRoundedRect(QRectF(rect.x(), rect.y(), max(rect.height(), rect.width() * prog), rect.height()), r, r)
        p.fillPath(fill, QColor(*rgb, 230))


# --- Qt ---
class Cover:
    def __init__(self, mode, family):
        self.mode = mode if mode in MODES else "card"
        self.family = family
        self.img = self.prev_img = None
        self.art_id = None
        self.art_t0 = -1e9
        self.key, self.title, self.artist = None, "", ""
        self.track_t0 = -1e9
        self.front = None  # (clave, pixmap, x, y) de la tarjeta/compacta actual
        self.old_front = None  # la de la canción anterior, mientras sale
        self.marks = {}  # marca de agua escalada por (art_id, lado)
        self.album = ""
        # carátula grande (sin letra / instrumental): progreso 0 (en su sitio) → 1 (en el centro)
        self.hero_on, self.hero_scale, self.hero_t0, self.hero_from = False, 1.0, -1e9, 0.0
        self.hero_cache = {}  # pixmaps de portada, halo y textos de la carátula grande

    def set_mode(self, mode):
        if mode in MODES:
            self.mode, self.front, self.old_front = mode, None, None

    def set_art(self, art_id, data, side):
        if art_id == self.art_id or not data:
            return
        self.prev_img = self.img
        self.img = QImage(data, side, side, side * 3, QImage.Format_RGB888).copy()
        self.art_id, self.art_t0 = art_id, time.monotonic()

    def set_track(self, key, title, artist, album=""):
        if key != self.key:
            if self.front is not None:
                self.old_front = self.front
            same_album = bool(album) and self.key is not None and album == self.key[2]
            self.key, self.title, self.artist, self.album = key, title, artist, album
            self.track_t0, self.front = time.monotonic(), None
            if not same_album:  # mismo álbum: Windows repite la portada y no llega otra; se conserva
                self.img = self.prev_img = None  # la portada nueva llega después
                self.art_id = None

    def avoid(self, w, h):
        return avoid_rect(self.mode, w, h)

    # --- carátula grande: sin letra (×1, con textos) o instrumental largo (×0,7, sin textos) ---
    def set_hero(self, on, scale=1.0):
        if on == self.hero_on and (not on or scale == self.hero_scale):
            return
        now = time.monotonic()
        self.hero_from = self.hero_progress(now)  # sin saltos si cambia a mitad
        self.hero_on, self.hero_t0 = on, now
        if on:
            self.hero_scale = scale
        else:
            self.track_t0 = now + HERO_BACK - IN_DELAY  # la tarjeta vuelve a entrar cuando llega a su sitio
            self.old_front = None

    def hero_progress(self, now=None):
        now = time.monotonic() if now is None else now
        age = now - self.hero_t0
        if self.hero_on:  # arranca con decisión y se posa suave
            t = max(0.0, min(1.0, (age - HERO_DELAY) / HERO_GO))
            e = 1 - (1 - t) ** 3
            return self.hero_from + (1 - self.hero_from) * e
        t = max(0.0, min(1.0, age / HERO_BACK))
        return self.hero_from * (1 - t * t * (3 - 2 * t))

    def hero_busy(self):
        """¿Hay animación de la carátula grande en marcha (o visible, que respira)?"""
        return self.hero_progress() > 0

    def draw_hero(self, p, w, h, rgb, prog, energy, dpr, native):
        """Dibuja la carátula grande; devuelve True si se ve (la tarjeta normal no se dibuja)."""
        now = time.monotonic()
        e = self.hero_progress(now)
        if e <= 0 or self.key is None:
            return False
        tx, ty, ts = hero_geometry(w, h, native)
        k = self.hero_scale
        target = (tx + ts * (1 - k) / 2, ty + ts * (1 - k) / 2, ts * k)
        x, y, s = arc_lerp(origin_rect(self.mode, w, h, native), target, e, 0.1 * h)
        fade = e if self.mode in ("hidden", "center") else min(1.0, e * 4)
        cx, cy = x + s / 2, y + s / 2
        # halo del color de la portada que respira con la música
        halo = self._hero_halo(rgb)
        hs = 1.6 * s * (1 + 0.015 * energy)
        p.setOpacity(0.35 * e)
        p.drawPixmap(QRectF(cx - hs / 2, cy - hs / 2, hs, hs), halo, QRectF(halo.rect()))
        # sombra en capas y portada con esquinas redondeadas
        radius = 0.06 * s
        for grow, alpha in ((28, 0.06), (16, 0.09), (6, 0.14)):  # sombra hacia abajo y los lados (no un marco)
            path = QPainterPath()
            path.addRoundedRect(QRectF(x - grow, y + 0.04 * s, s + 2 * grow, s + 1.5 * grow), radius + grow, radius + grow)
            p.setOpacity(alpha * e)
            p.fillPath(path, QColor(0, 0, 0))
        p.setOpacity(fade)
        art = self._hero_art(round(target[2] * dpr), dpr, rgb)
        p.drawPixmap(QRectF(x, y, s, s), art, QRectF(art.rect()))
        if k >= 1 and self.hero_on:  # textos: subiendo, cuando la portada ya ha llegado
            ta = max(0.0, min(1.0, (now - self.hero_t0 - 0.95) / 0.45))
        else:
            ta = e if k >= 1 else 0.0
        if ta > 0:
            text = self._hero_text(w, h, rgb, dpr)
            tw, th = text.width() / dpr, text.height() / dpr
            p.setOpacity(ta)
            rise = 16 * (1 - ta) ** 2
            p.drawPixmap(QRectF(w / 2 - tw / 2, ty + ts + 0.03 * h + rise, tw, th), text, QRectF(text.rect()))
            if prog is not None:  # del ancho de la carátula y subiendo con los textos
                bh = max(3.0, 0.005 * h)
                by = ty + ts + 0.03 * h + rise + th + 0.03 * h
                _bar(p, QRectF(w / 2 - ts / 2, by, ts, bh), prog, rgb)
        p.setOpacity(1.0)
        return True

    def _hero_art(self, n, dpr, rgb):
        key = ("art", self.art_id, n)
        pm = self.hero_cache.get(key)
        if pm is None:
            n = max(1, n)
            pm = QPixmap(n, n)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing)
            q.setRenderHint(QPainter.SmoothPixmapTransform)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, n, n), 0.06 * n, 0.06 * n)
            if self.img is None:
                q.fillPath(path, QColor(*rgb, 64))
            else:
                q.setClipPath(path)
                q.drawImage(QRectF(0, 0, n, n), self.img)
            q.end()
            self.hero_cache = {kk: v for kk, v in self.hero_cache.items() if kk[0] != "art"}
            self.hero_cache[key] = pm
        return pm

    def _hero_halo(self, rgb):
        key = ("halo", tuple(rgb))
        pm = self.hero_cache.get(key)
        if pm is None:
            pm = QPixmap(256, 256)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            g = QRadialGradient(QPointF(128, 128), 128)
            g.setColorAt(0, QColor(*rgb, 255))
            g.setColorAt(0.45, QColor(*rgb, 110))
            g.setColorAt(1, QColor(*rgb, 0))
            q.fillRect(pm.rect(), g)
            q.end()
            self.hero_cache = {kk: v for kk, v in self.hero_cache.items() if kk[0] != "halo"}
            self.hero_cache[key] = pm
        return pm

    def _hero_text(self, w, h, rgb, dpr):
        """Título, artista y álbum centrados (jerarquía: grande / medio / pequeño)."""
        key = ("text", self.key, w, h, dpr)
        pm = self.hero_cache.get(key)
        if pm is None:
            lines = [(self.title, self._font(0.045 * h, True), QColor(255, 255, 255, 245)),
                     (self.artist, self._font(0.028 * h), QColor(255, 255, 255, 178))]
            if self.album and self.album != self.title:
                lines.append((self.album, self._font(0.022 * h), QColor(255, 255, 255, 128)))
            maxw = 0.8 * w
            widths = [min(QFontMetricsF(f).horizontalAdvance(t) + 6, maxw) for t, f, _ in lines]
            heights = [QFontMetricsF(f).height() for _, f, _ in lines]
            tw, th = max(widths), sum(heights) + 0.008 * h * (len(lines) - 1)
            pm, q = self._canvas(tw, th, dpr)
            yy = 0.0
            for (t, f, c), lw, lh in zip(lines, widths, heights):
                self._text(q, (tw - lw) / 2 + 3, yy + QFontMetricsF(f).ascent(), t, f, lw, c)
                yy += lh + 0.008 * h
            q.end()
            self.hero_cache = {kk: v for kk, v in self.hero_cache.items() if kk[0] != "text"}
            self.hero_cache[key] = pm
        return pm

    def _font(self, px, bold=False):
        f = QFont(self.family)
        f.setPixelSize(max(8, round(px)))
        f.setWeight(QFont.DemiBold if bold else QFont.Normal)
        return f

    # --- marca de agua (detrás de las estrellas) ---
    def draw_watermark(self, p, w, h, push=0.0, dpr=1.0, fade=1.0):
        if self.mode != "center" or self.img is None or fade <= 0:
            return
        base = 0.55 * h
        side = base * (1 + 0.04 * push)  # el empujón del viaje lo aplica drawPixmap: la caché no cambia
        rect = QRectF((w - side) / 2, (h - side) / 2, side, side)
        n = max(1, round(base * dpr))
        cross = min(1.0, (time.monotonic() - self.art_t0) / ART_FADE)  # fundido entre portadas
        alpha = MARK_ALPHA * fade
        if self.prev_img is not None and cross < 1:
            self._mark(p, self.prev_img, "prev", n, dpr, rect, alpha * (1 - cross))
        self._mark(p, self.img, "cur", n, dpr, rect, alpha * (cross if self.prev_img is not None else 1.0))

    def _mark(self, p, img, slot, n, dpr, rect, opacity):
        """Una entrada por imagen (actual / anterior); se rehace solo si cambia el tamaño o la portada."""
        cached = self.marks.get(slot)
        if cached is None or cached[0] is not img or cached[1] != n:
            pm = QPixmap(n, n)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing)
            q.setRenderHint(QPainter.SmoothPixmapTransform)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, n, n), 0.04 * n, 0.04 * n)
            q.setClipPath(path)
            q.drawImage(QRectF(0, 0, n, n), img)
            q.end()
            pm.setDevicePixelRatio(dpr)
            cached = self.marks[slot] = (img, n, pm)
        pm = cached[2]
        p.setOpacity(opacity)
        p.drawPixmap(rect, pm, QRectF(pm.rect()))
        p.setOpacity(1.0)

    # --- tarjeta / compacta (delante del fondo, detrás de las estrellas) ---
    def draw_front(self, p, w, h, rgb, prog, dpr):
        if self.mode not in ("card", "top") or self.key is None:
            return
        key = (self.mode, self.key, self.art_id, w, h, tuple(rgb), dpr)
        if self.front is None or self.front[0] != key:
            pm, x, y = self._build_card(w, h, rgb, dpr) if self.mode == "card" else self._build_top(w, h, dpr)
            self.front = (key, pm, x, y)
        age = time.monotonic() - self.track_t0
        g = card_geometry(w, h)
        dist = g["h"] if self.mode == "card" else 20
        if self.old_front is not None and age < OUT_T:  # la anterior baja y se desvanece
            _, pm, x, y = self.old_front
            p.setOpacity(1 - age / OUT_T)
            p.drawPixmap(QRectF(x, y + 0.15 * dist * age / OUT_T, pm.width() / dpr, pm.height() / dpr), pm,
                         QRectF(pm.rect()))
        elif self.old_front is not None:
            self.old_front = None
        e = _out_cubic(min(1.0, max(0.0, (age - IN_DELAY) / IN_T)))  # la nueva sube y aparece
        _, pm, x, y = self.front
        dy = 0.3 * dist * (1 - e)
        p.setOpacity(e)
        p.drawPixmap(QRectF(x, y + dy, pm.width() / dpr, pm.height() / dpr), pm, QRectF(pm.rect()))
        if self.mode == "card" and prog is not None and e > 0:  # barra de progreso: lo único que cambia siempre
            bar = max(3.0, 0.03 * g["a"])
            bx = g["x"] + 2 * g["pad"] + g["a"]
            by = g["y"] + g["pad"] + g["a"] - bar + dy
            _bar(p, QRectF(bx, by, g["text_w"], bar), prog, rgb)
        p.setOpacity(1.0)

    def _canvas(self, w, h, dpr):
        pm = QPixmap(max(1, round(w * dpr)), max(1, round(h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing)
        q.setRenderHint(QPainter.SmoothPixmapTransform)
        q.setRenderHint(QPainter.TextAntialiasing)
        return pm, q

    def _art(self, q, rect, radius, rgb):
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        if self.img is None:  # mientras llega la portada
            q.fillPath(path, QColor(*rgb, 64))
            return
        q.save()
        q.setClipPath(path)
        q.drawImage(rect, self.img)
        q.restore()

    def _text(self, q, x, y, text, font, width, color):
        fm = QFontMetricsF(font)
        text = fm.elidedText(text, Qt.ElideRight, width)
        q.setFont(font)
        q.setPen(QColor(0, 0, 0, 110))  # sombra para fondos claros
        q.drawText(x, y + 1.5, text)
        q.setPen(color)
        q.drawText(x, y, text)

    def _build_card(self, w, h, rgb, dpr):
        g = card_geometry(w, h)
        a, pad, s = g["a"], g["pad"], SHADOW
        pm, q = self._canvas(g["w"] + 2 * s, g["h"] + 2 * s, dpr)
        radius = 0.14 * a
        for grow, alpha in ((12, 20), (7, 30), (3, 40)):  # sombra suave en capas
            path = QPainterPath()
            path.addRoundedRect(QRectF(s - grow, s - grow + 4, g["w"] + 2 * grow, g["h"] + 2 * grow),
                                radius + grow, radius + grow)
            q.fillPath(path, QColor(0, 0, 0, alpha))
        card = QPainterPath()
        card.addRoundedRect(QRectF(s, s, g["w"], g["h"]), radius, radius)
        q.fillPath(card, QColor(10, 10, 14, 140))
        q.fillPath(card, QColor(*rgb, 26))  # velo del color de la portada
        q.setPen(QColor(255, 255, 255, 20))
        q.drawPath(card)
        self._art(q, QRectF(s + pad, s + pad, a, a), 0.10 * a, rgb)  # esquinas concéntricas con la tarjeta
        if g["text_w"] > 8:
            tx = s + 2 * pad + a
            title_f, artist_f = self._font(0.20 * a, True), self._font(0.155 * a)
            ty = s + pad + 0.06 * a + QFontMetricsF(title_f).ascent()
            self._text(q, tx, ty, self.title, title_f, g["text_w"], QColor(255, 255, 255, 245))
            self._text(q, tx, ty + 0.27 * a, self.artist, artist_f, g["text_w"], QColor(255, 255, 255, 178))
        q.end()
        return pm, g["x"] - s, g["y"] - s

    def _build_top(self, w, h, dpr):
        side = max(28.0, min(56.0, 0.05 * h))
        font = self._font(max(12.0, min(18.0, 0.022 * h)))
        text = f"{self.title} · {self.artist}"
        tw = min(QFontMetricsF(font).horizontalAdvance(text) + 4, 0.6 * w)
        pm, q = self._canvas(side + 10 + tw, side + 4, dpr)
        self._art(q, QRectF(0, 0, side, side), 0.15 * side, (255, 255, 255))
        fm = QFontMetricsF(font)
        self._text(q, side + 10, (side + fm.ascent() - fm.descent()) / 2, text, font, tw, QColor(255, 255, 255, 191))
        q.end()
        return pm, 16, 10
