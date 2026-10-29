"""Fondo de la ventana de letras: la portada difuminada con varios modos.

La textura (128×128, ya difuminada en el hilo de SMTC) se compone en un lienzo pequeño
(ventana/6), se amplía una vez con suavizado a una caché del tamaño de la ventana junto con
las estrellas de fondo, y cada fotograma solo vuelca esa caché.
"""
import math
import random
import time
import zlib

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QRadialGradient

from . import effects

MODES = ("auto", "none", "blur", "ambient", "kenburns", "beat")  # "auto" es una opción, no un dibujo
NAMES = {"auto": "Automático (según la música)", "none": "Sin portada", "blur": "Difuminado",
         "ambient": "Ambiente en movimiento", "kenburns": "Ken Burns", "beat": "Al ritmo"}
AUTO_FADE = 1.5  # los cambios automáticos se funden más despacio
ANIMATED = ("ambient", "kenburns")  # se recomponen a 25 fps
ART_FADE, MODE_FADE = 1.5, 0.5
DOWNSCALE = 6  # lienzo = ventana / 6: lo difuminado no pierde nada y ampliar es barato


# --- lógica pura ---
def cover_rect(aspect, zoom=1.0, cx=0.5, cy=0.5):
    """Rectángulo normalizado (x, y, w, h) de una textura cuadrada que cubre una ventana de ese aspecto."""
    if aspect >= 1:
        w, h = 1 / zoom, 1 / (aspect * zoom)
    else:
        w, h = aspect / zoom, 1 / zoom
    return (1 - w) * cx, (1 - h) * cy, w, h


def kenburns(t):
    """(zoom, cx, cy) lentos y continuos: sin saltos al reiniciar."""
    return (1.175 + 0.075 * math.sin(2 * math.pi * t / 40),
            0.5 + 0.5 * math.sin(2 * math.pi * t / 50),
            0.5 + 0.5 * math.sin(2 * math.pi * t / 70 + 1))


def blobs(seed, n=4):
    """Manchas del modo Ambiente: un cuadrante de la portada cada una, con órbita y giro propios."""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        out.append({"quad": i % 4, "bx": 0.35 + 0.3 * (i % 2), "by": 0.35 + 0.3 * (i // 2 % 2),
                    "size": rnd.uniform(0.9, 1.4), "px": rnd.uniform(35, 70), "py": rnd.uniform(35, 70),
                    "ph1": rnd.uniform(0, 6.28), "ph2": rnd.uniform(0, 6.28),
                    "rot": rnd.uniform(45, 90) * (1 if i % 2 else -1)})
    return out


def blob_pos(b, t):
    """(x, y) normalizados y ángulo en grados de una mancha en el instante t."""
    return (b["bx"] + 0.28 * math.sin(2 * math.pi * t / b["px"] + b["ph1"]),
            b["by"] + 0.25 * math.sin(2 * math.pi * t / b["py"] + b["ph2"]),
            360 * t / b["rot"])


def dim_for(lum):
    """Cuánto oscurecer: más cuanto más clara es la portada, para que las letras se lean."""
    return min(0.50, max(0.30, 0.30 + 0.25 * lum))


def next_mode(mode):
    return MODES[(MODES.index(mode) + 1) % len(MODES)] if mode in MODES else MODES[0]


# --- Qt ---
class Backdrop:
    def __init__(self, mode="auto"):
        self.setting = mode if mode in MODES else "auto"  # lo elegido (puede ser "auto")
        self.auto_mode = "blur"  # lo último que decidió el ambiente
        self.mode = self.auto_mode if self.setting == "auto" else self.setting  # lo que se dibuja
        self.mode_fade = MODE_FADE
        self.tex = self.prev_tex = None  # (QImage, lum, manchas)
        self.art_id = None
        self.art_t0 = self.mode_t0 = -1e9
        self.prev_cache = None  # caché del modo anterior, para el fundido
        self.cache = None
        self.cache_key = None
        self.stars = None  # QPixmap transparente con las estrellas de fondo
        self.size = (0, 0)
        self.vignette = None
        self.last_compose = -1e9
        self.energy, self.beat_t = 0.0, -1e9

    def set_art(self, art_id, data, lum):
        if art_id == self.art_id or not data:
            return
        side = int(round(math.sqrt(len(data) / 3)))
        img = QImage(data, side, side, side * 3, QImage.Format_RGB888).copy()  # copy: no depende de los bytes
        if time.monotonic() - self.art_t0 >= ART_FADE:  # durante otro fundido se conserva el origen: sin salto
            self.prev_tex = self.tex
        self.tex = (img, lum, self._blob_images(img), blobs(zlib.crc32(art_id.encode())))
        self.art_id, self.art_t0 = art_id, time.monotonic()
        self.cache_key = None

    def set_mode(self, mode):
        """Opción elegida por el usuario (un modo o "auto")."""
        if mode not in MODES:
            return
        self.setting = mode
        # al volver a "auto" se aplica en seguida lo último que decidió el ambiente
        self._apply(self.auto_mode if mode == "auto" else mode, MODE_FADE)

    def set_auto(self, mode):
        """Modo que decide el ambiente de la canción; solo se ve si la opción es "auto"."""
        self.auto_mode = mode
        if self.setting == "auto":
            self._apply(mode, AUTO_FADE)

    def _apply(self, mode, fade):
        if mode in MODES and mode != "auto" and mode != self.mode:
            self.mode_fade = fade
            prev = self.cache.copy() if self.cache is not None else None  # copia: la caché se reutiliza
            if prev is not None and self.mode == "beat":
                q = QPainter(prev)  # Al ritmo se compone más claro: aplicarle su capa oscura (sin destello)
                q.fillRect(prev.rect(), QColor(0, 0, 0, 51))
                q.end()
            self.prev_cache, self.mode, self.mode_t0 = prev, mode, time.monotonic()
            self.cache_key = None

    def set_stars(self, pixmap):
        self.stars, self.cache_key = pixmap, None

    def beat(self):
        self.beat_t = time.monotonic()

    def _blob_images(self, img):
        """Los 4 cuadrantes de la portada con borde circular suave (se precalculan una vez)."""
        half = img.width() // 2
        out = []
        for q in range(4):
            part = img.copy((q % 2) * half, (q // 2) * half, half, half).convertToFormat(QImage.Format_ARGB32_Premultiplied)
            p = QPainter(part)
            p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
            g = QRadialGradient(QPointF(half / 2, half / 2), half / 2)
            g.setColorAt(0, QColor(0, 0, 0, 255))
            g.setColorAt(0.6, QColor(0, 0, 0, 160))
            g.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(part.rect(), g)
            p.end()
            out.append(part)
        return out

    def draw(self, p, w, h, push=0.0, live=True):
        """Vuelca el fondo (portada + estrellas) en el painter.

        push: empujón de cámara del viaje 0..1. live: la ventana está animando; si no (pausa),
        los modos animados se quedan quietos en vez de avanzar a saltos con cada repintado suelto.
        """
        now = time.monotonic()
        if (w, h) != self.size:
            self.size, self.cache_key, self.vignette = (w, h), None, None
        art_fading = now - self.art_t0 < ART_FADE
        beat_env = effects.env(now - self.beat_t, 0.06, 0.35) if self.mode == "beat" else 0.0
        if self.mode in ANIMATED and self.tex is not None:
            stale = live and now - self.last_compose >= 0.04  # 25 fps
            key = self.cache_key if not stale and not art_fading else (self.mode, now)
        else:
            key = (self.mode, art_fading and int(now * 25))  # fundido de portada también a 25 fps
        if key != self.cache_key or self.cache is None:
            self._compose(w, h, now, beat_env)
            self.cache_key, self.last_compose = key, now
        scale = 1 + 0.04 * push
        if self.mode == "beat":
            scale *= 1 + 0.025 * beat_env + 0.01 * self.energy
        target = QRectF(w * (1 - scale) / 2, h * (1 - scale) / 2, w * scale, h * scale)
        p.drawPixmap(target, self.cache, QRectF(self.cache.rect()))
        if self.mode == "beat" and self.tex is not None:
            # compuesto 0,2 más claro; esta capa lo oscurece y el golpe la aclara (sin recomponer cada fotograma)
            p.fillRect(QRectF(0, 0, w, h), QColor(0, 0, 0, round(255 * max(0.0, 0.2 - 0.15 * beat_env - 0.05 * self.energy))))
        mf = now - self.mode_t0
        if mf < self.mode_fade and self.prev_cache is not None:  # el modo anterior se desvanece encima
            p.setOpacity(1 - mf / self.mode_fade)
            p.drawPixmap(QRectF(0, 0, w, h), self.prev_cache, QRectF(self.prev_cache.rect()))
            p.setOpacity(1.0)
        elif self.prev_cache is not None:
            self.prev_cache = None  # libera el pixmap del tamaño de la ventana

    def _compose(self, w, h, now, beat_env):
        if self.mode in ANIMATED:  # se recomponen 25 veces por segundo: lienzo pequeño
            ds = DOWNSCALE + 2 if w > 1280 else DOWNSCALE
            cw, ch = max(16, w // ds), max(9, h // ds)
        else:  # quietos: se componen pocas veces, lienzo grande para que la portada HD se vea nítida
            cw = max(16, min(640, w // 3))
            ch = max(9, round(cw * h / w))
        canvas = QImage(cw, ch, QImage.Format_RGB32)
        canvas.fill(Qt.black)
        if self.mode != "none" and self.tex is not None:
            q = QPainter(canvas)
            q.setRenderHint(QPainter.SmoothPixmapTransform)
            q.setRenderHint(QPainter.Antialiasing)
            t_art = min(1.0, (now - self.art_t0) / ART_FADE)
            fade = t_art * t_art * (3 - 2 * t_art)
            if self.prev_tex is not None and fade < 1:
                self._paint_tex(q, self.prev_tex, cw, ch, now, 1.0, beat_env)
            self._paint_tex(q, self.tex, cw, ch, now, fade if self.prev_tex is not None else 1.0, beat_env)
            q.setOpacity(1.0)
            q.drawImage(0, 0, self._vignette(cw, ch))
            q.end()
        pm = self.cache if self.cache is not None and self.cache.size().toTuple() == (w, h) else QPixmap(w, h)
        p = QPainter(pm)  # reutilizar evita reservar 8 MB (1080p) 25 veces por segundo
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(QRectF(0, 0, w, h), canvas, QRectF(canvas.rect()))
        if self.stars is not None:
            p.drawPixmap(0, 0, self.stars)
        p.end()
        self.cache = pm

    def _paint_tex(self, q, tex, cw, ch, now, opacity, beat_env):
        img, lum, parts, bl = tex
        aspect = cw / ch
        zoom, cx, cy = (kenburns(now) if self.mode == "kenburns" else
                        (1.3, 0.5, 0.5) if self.mode == "ambient" else (1.0, 0.5, 0.5))
        x, y, sw, sh = cover_rect(aspect, zoom, cx, cy)
        n = img.width()
        q.setOpacity(opacity)
        q.drawImage(QRectF(0, 0, cw, ch), img, QRectF(x * n, y * n, sw * n, sh * n))
        if self.mode == "ambient":
            q.setOpacity(0.65 * opacity)
            for b in bl:
                bx, by, ang = blob_pos(b, now)
                size = b["size"] * ch
                q.save()
                q.translate(bx * cw, by * ch)
                q.rotate(ang)
                q.drawImage(QRectF(-size / 2, -size / 2, size, size), parts[b["quad"]])
                q.restore()
        dim = dim_for(lum) - (0.2 if self.mode == "beat" else 0.0)
        q.setOpacity(opacity)
        q.fillRect(0, 0, cw, ch, QColor(0, 0, 0, round(255 * max(0.0, min(1.0, dim)))))

    def _vignette(self, cw, ch):
        if self.vignette is None or self.vignette.size().toTuple() != (cw, ch):
            v = QImage(cw, ch, QImage.Format_ARGB32_Premultiplied)
            v.fill(Qt.transparent)
            p = QPainter(v)
            r = math.hypot(cw, ch) / 2
            g = QRadialGradient(QPointF(cw / 2, ch / 2), r)
            g.setColorAt(0.5, QColor(0, 0, 0, 0))
            g.setColorAt(1, QColor(0, 0, 0, 170))
            p.fillRect(v.rect(), g)
            p.end()
            self.vignette = v
        return self.vignette
