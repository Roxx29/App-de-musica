"""Paneles laterales de la ventana de la letra, pintados dentro de ella como la rueda.

Izquierda: controles de YouTube Music (anterior, −10 s, play/pausa, +10 s, siguiente).
Derecha: "Sonó antes", carrusel vertical; la canción bajo el ratón crece y se ve según el estilo:
galaxia (Constelación), vinilo girando (Cinta) o altavoz con ondas (Latido).
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QConicalGradient, QFont, QPainterPath, QPen, QRadialGradient

# (acción, icono Segoe MDL2, icono alternativo cuando suena)
BUTTONS = (("prev", "", None), ("back", "", None), ("play", "", ""),
           ("fwd", "", None), ("next", "", None))
EDGE_L, EDGE_R = 88.0, 120.0  # px desde el borde que muestran cada panel
PILL_X, PILL_W, BTN = 16.0, 56.0, 44.0
STRIP_R, THUMB, BIG, GAP = 16.0, 56.0, 160.0, 12.0
STRIP_TOP, STRIP_BOTTOM = 64.0, 24.0  # debajo de los avisos
MAX_ITEMS = 7
SHOW_T, HOVER_T, LINGER = 0.18, 0.22, 0.6
HOME = 0.35  # la que suena, sin ratón encima: algo más grande que las demás
RPM = 200.0  # 33⅓ rpm en grados por segundo


def _approach(v, target, dt, secs):
    step = dt / secs
    return min(target, v + step) if v < target else max(target, v - step)


def _ease(t):
    return 1 - (1 - t) ** 3


# --- geometría pura ---
def pill_rect(h):
    """(x, y, ancho, alto) de la pastilla de controles, centrada en el 42 % del alto."""
    ph = len(BUTTONS) * BTN + 12
    y = max(60.0, min(h - ph - 16, 0.42 * h - ph / 2))
    return PILL_X, y, PILL_W, ph


def button_at(x, y, h):
    px, py, pw, ph = pill_rect(h)
    if not (px <= x <= px + pw and py + 6 <= y < py + ph - 6):
        return None
    return min(len(BUTTONS) - 1, int((y - py - 6) // BTN))


def strip_layout(n, focus, amount, h, center=None):
    """[(y del centro, lado)] de n miniaturas; `focus` (índice, puede ser decimal) crece con `amount` 0..1.

    center: índice que se coloca a media altura (la canción que suena), sin salirse de la ventana.
    """
    if n <= 0:
        return []
    # lupa: caída gaussiana (σ = 0,6 → la vecina ~80 px)
    sizes = [THUMB + (BIG - THUMB) * amount * (math.exp(-((i - focus) ** 2) / 0.72) if focus is not None else 0)
             for i in range(n)]
    avail = h - STRIP_TOP - STRIP_BOTTOM
    total = sum(sizes) + GAP * (n - 1)
    k = min(1.0, avail / total) if total > 0 else 1.0  # si no caben, todas un poco más pequeñas
    out, y = [], STRIP_TOP
    for s in sizes:
        out.append((y + s * k / 2, s * k))
        y += s * k + GAP * k
    if center is not None and 0 <= center < n:
        top, bottom = out[0][0] - out[0][1] / 2, out[-1][0] + out[-1][1] / 2
        shift = max(STRIP_TOP - top, min(h - STRIP_BOTTOM - bottom, h / 2 - out[center][0]))
        out = [(cy + shift, s) for cy, s in out]
    return out


def item_at(y, layout):
    for i, (cy, s) in enumerate(layout):
        if abs(y - cy) <= s / 2 + GAP / 2:
            return i
    return None


class Panels:
    def __init__(self):
        self.reset()

    def reset(self):
        self.left = self.right = 0.0  # visibilidad 0..1
        self.near_l = self.near_r = False
        self.leave_l = self.leave_r = None
        self.btn = None
        self.press_t, self.press_btn = -1e9, None
        self.item = None  # índice bajo el ratón en el carrusel
        self.focus, self.amount = None, 0.0  # lupa animada
        self.home = None  # índice de la que suena
        self.n = 0
        self.layout = []
        self.last = None
        self.hint_until = 0.0
        self.animate = True

    # --- ratón ---
    def move(self, x, y, w, h, now, block=False):
        near_l = not block and x < EDGE_L or (self.left > 0.5 and x < PILL_X + PILL_W + 24)
        near_r = not block and x > w - EDGE_R or (self.right > 0.5 and x > w - STRIP_R - BIG - 24)
        if self.near_l and not near_l:
            self.leave_l = now
        if self.near_r and not near_r:
            self.leave_r = now
        self.near_l, self.near_r = near_l, near_r
        self.btn = button_at(x, y, h) if self.left > 0.5 else None
        self.item = item_at(y, self.layout) if self.right > 0.5 and x > w - STRIP_R - BIG - 8 else None

    def press(self, x, y, w, h, now):
        """('control', acción) / ('song', índice) / None."""
        b = button_at(x, y, h) if self.left > 0.5 else None
        if b is not None:
            self.press_t, self.press_btn = now, b
            return "control", BUTTONS[b][0]
        if self.right > 0.5 and x > w - STRIP_R - BIG - 8:
            i = item_at(y, self.layout)
            if i is not None:
                return "song", i
        return None

    def hit(self, x, y, w, h):
        return (self.left > 0.5 and button_at(x, y, h) is not None) or (
            self.right > 0.5 and x > w - STRIP_R - BIG - 8 and item_at(y, self.layout) is not None)

    def busy(self, now):
        want_l = 1.0 if self.near_l or now < self.hint_until else 0.0
        want_r = 1.0 if (self.near_r or now < self.hint_until) and self.n else 0.0
        return (self.left != want_l or self.right != want_r or now < self.hint_until or now - self.press_t < 0.25
                or (self.item is not None and self.right > 0 and self.animate)  # la ampliada se anima (no en Ligera)
                or abs(self.amount - (1.0 if self.item is not None else HOME if self.home is not None else 0.0)) > 1e-3
                or (not self.near_l and self.leave_l is not None and self.left > 0)
                or (not self.near_r and self.leave_r is not None and self.right > 0))

    def update(self, now, h, n, home=None):
        """home: la que suena; sin ratón encima queda algo más grande (la lupa vuelve a ella)."""
        dt = 0.0 if self.last is None else min(0.1, now - self.last)
        self.last, self.n = now, n
        hint = now < self.hint_until
        stay_l = self.near_l or hint or (self.leave_l is not None and now - self.leave_l < LINGER and self.left > 0)
        stay_r = (self.near_r or hint or (self.leave_r is not None and now - self.leave_r < LINGER
                                          and self.right > 0)) and n > 0
        self.left = _approach(self.left, 1.0 if stay_l else 0.0, dt, SHOW_T)
        self.right = _approach(self.right, 1.0 if stay_r else 0.0, dt, SHOW_T)
        if self.item is not None and self.item >= n:
            self.item = None
        target = self.item if self.item is not None else home
        if target is not None:
            self.focus = target if self.focus is None else self.focus + (target - self.focus) * min(1.0, dt / 0.09)
        self.amount = _approach(self.amount, 1.0 if self.item is not None else HOME if home is not None else 0.0,
                                dt, HOVER_T)
        if self.amount == 0:
            self.focus = None
        self.layout = strip_layout(min(n, MAX_ITEMS), self.focus, _ease(self.amount), h, home)

    # --- dibujo ---
    def draw(self, p, w, h, now, ctx):
        """ctx: dict con playing, rgb, paper (tema claro), style, items, thumb(it, lado), label(texto, px, bold),
        beat (envolvente 0..1), light (calidad Ligera)."""
        self.animate = not ctx["light"]
        self.home = next((i for i, it in enumerate(ctx["items"]) if it.get("kind") == "now"), None)
        self.update(now, h, min(len(ctx["items"]), MAX_ITEMS), self.home)
        if self.left > 0:
            self._controls(p, h, now, ctx)
        if self.right > 0 and self.layout:
            self._strip(p, w, now, ctx)

    def _controls(self, p, h, now, ctx):
        e = _ease(self.left)
        x, y, pw, ph = pill_rect(h)
        p.save()
        p.setOpacity(e)
        p.translate(-12 * (1 - e), 0)
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, pw, ph), pw / 2, pw / 2)
        if ctx["paper"]:  # Cinta: "hardware" negro sobre el papel
            p.fillPath(path, QColor(20, 20, 20, 235))
        else:
            p.fillPath(path, QColor(10, 10, 14, 153))
            p.setPen(QPen(QColor(255, 255, 255, 41), 1))
            p.drawPath(path)
        hl = QColor(*ctx["rgb"])
        hl.setHslF(hl.hslHueF(), hl.hslSaturationF(), max(0.45, min(0.55 if ctx["paper"] else 0.68, hl.lightnessF())),
                   0.9)
        icon = QColor(230, 226, 216) if ctx["paper"] else QColor(255, 255, 255, 235)
        for i, (action, glyph, alt) in enumerate(BUTTONS):
            cx, cy = x + pw / 2, y + 6 + BTN * (i + 0.5)
            s = 1.0
            if self.press_btn == i and now - self.press_t < 0.25:  # pulsado: 0,92 y vuelve
                t = (now - self.press_t) / 0.25
                s = 0.92 + 0.08 * min(1.0, t * 2) if t < 0.5 else 1.0
            r = BTN / 2 - 4
            if action == "play":
                p.setPen(Qt.NoPen)
                p.setBrush(hl)
                p.drawEllipse(QPointF(cx, cy), r * s, r * s)
            elif self.btn == i:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 26))
                p.drawEllipse(QPointF(cx, cy), r, r)
            p.setPen(icon if action != "play" else QColor(255, 255, 255))
            p.setFont(_icon_font(round((20 if action == "play" else 16) * s)))
            p.drawText(QRectF(cx - 16, cy - 16, 32, 32), Qt.AlignCenter, alt if alt and ctx["playing"] else glyph)
        p.restore()

    def _strip(self, p, w, now, ctx):
        e = _ease(self.right)
        p.save()
        p.setOpacity(e)
        p.translate(12 * (1 - e), 0)
        hovered = None
        for i, (cy, s) in enumerate(self.layout):
            it = ctx["items"][i]
            rect = QRectF(w - STRIP_R - s, cy - s / 2, s, s)
            if i == self.item and s > THUMB + 20:
                hovered = (it, rect)
                continue
            if it.get("kind") == "past":  # lo ya escuchado, más tenue
                p.setOpacity(e * 0.55)
            self._thumb(p, it, rect, ctx)
            p.setOpacity(e)
            if it.get("kind") == "now":  # aro del color de la portada: "suena ahora"
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(*ctx["rgb"]), 2))
                p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 0.06 * s + 3, 0.06 * s + 3)
        if hovered:  # la ampliada encima de las demás, con su vista según el estilo
            it, rect = hovered
            f = max(0.0, min(1.0, (rect.width() - THUMB) / (BIG - THUMB)))
            {"ribbon": self._vinyl, "kinetic": self._speaker}.get(ctx["style"], self._galaxy)(p, it, rect, f, now, ctx)
            self._label(p, it, rect, ctx)
        p.restore()

    def _thumb(self, p, it, rect, ctx, circle=False):
        path = QPainterPath()
        if circle:
            path.addEllipse(rect)
        else:
            rad = 0.06 * rect.width()
            path.addRoundedRect(rect, rad, rad)
        img = ctx["thumb"](it, rect.width())
        if img is None:
            p.fillPath(path, QColor(40, 40, 46) if not ctx["paper"] else QColor(20, 20, 20))
            return
        p.save()
        p.setClipPath(path)
        p.drawImage(rect, img)
        p.restore()

    def _label(self, p, it, rect, ctx):
        title = ctx["label"](it["title"], 14, True)
        tag = {"now": "Suena ahora · ", "next": "Sigue · "}.get(it.get("kind"), "")
        artist = ctx["label"](tag + it["artist"], 12, False)
        dpr = title.devicePixelRatio()
        tw = max(title.width(), artist.width()) / dpr
        th = (title.height() + artist.height()) / dpr
        x = rect.x() - 12 - tw - 20
        if ctx["style"] == "ribbon":
            x -= 0.4 * rect.width()  # el vinilo sale por la izquierda
        pill = QRectF(x, rect.center().y() - th / 2 - 6, tw + 20, th + 12)
        path = QPainterPath()
        path.addRoundedRect(pill, 8, 8)
        if ctx["paper"]:
            p.fillPath(path, QColor(20, 20, 20, 235))
        else:
            p.fillPath(path, QColor(10, 10, 14, 220))
            p.setPen(QPen(QColor(255, 255, 255, 26), 1))
            p.drawPath(path)
        p.drawPixmap(QPointF(pill.x() + 10, pill.y() + 6), title)
        p.setOpacity(p.opacity() * 0.6)
        p.drawPixmap(QPointF(pill.x() + 10, pill.y() + 6 + title.height() / dpr), artist)
        p.setOpacity(p.opacity() / 0.6)

    def _galaxy(self, p, it, rect, f, now, ctx):
        """Constelación: la portada como núcleo de una galaxia de dos brazos en espiral."""
        c, s = rect.center(), rect.width()
        rgb = ctx["rgb"]
        t = 0.0 if ctx["light"] else now
        g = QRadialGradient(c, 0.7 * s)
        g.setColorAt(0, QColor(*rgb, round(110 * f)))
        g.setColorAt(0.5, QColor(*rgb, round(40 * f)))
        g.setColorAt(1, QColor(*rgb, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, 0.7 * s, 0.7 * s)
        n = 16 if ctx["light"] else 28
        for arm in range(2):
            for k in range(n):
                a = k / n * 2.6 * math.pi + arm * math.pi + t * 0.15 * 2 * math.pi
                r = 0.22 * s * math.exp(0.3 * k / n * 2.6)  # espiral logarítmica
                pt = QPointF(c.x() + r * math.cos(a), c.y() + 0.75 * r * math.sin(a))
                tw = 0.6 + 0.4 * math.sin(t * 3 + k * 1.7)
                p.setBrush(QColor(255, 255, 255, round(255 * f * (0.9 - 0.6 * k / n) * tw)))
                d = 2.5 - 1.5 * k / n
                p.drawEllipse(pt, d, d)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, round(77 * f)), 1))
        p.drawEllipse(c, 0.62 * s, 0.62 * s * 0.35)
        core = 0.6 * s * (1 + 0.04 * ctx["beat"])
        self._thumb(p, it, QRectF(c.x() - core / 2, c.y() - core / 2, core, core), ctx, circle=True)

    def _vinyl(self, p, it, rect, f, now, ctx):
        """Cinta: la portada es la funda y de ella sale un vinilo que gira a 33⅓ rpm."""
        s = rect.width()
        r = 0.48 * s
        c = QPointF(rect.center().x() - 0.4 * s * f, rect.center().y())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(16, 16, 16))
        p.drawEllipse(c, r, r)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        for k in range(6):
            rr = r * (0.48 + 0.47 * k / 5)
            p.drawEllipse(c, rr, rr)
        if not ctx["light"]:  # reflejo fijo: la luz no gira con el disco
            shine = QConicalGradient(c, 45)
            for a, alpha in ((0, 28), (0.12, 0), (0.5, 28), (0.62, 0), (1, 28)):
                shine.setColorAt(a, QColor(255, 255, 255, alpha))
            p.setPen(Qt.NoPen)
            p.setBrush(shine)
            p.drawEllipse(c, r, r)
        label = 0.36 * r * 2
        p.save()
        p.translate(c)
        p.rotate(0 if ctx["light"] or not ctx["playing"] else (now * RPM) % 360)
        self._thumb(p, it, QRectF(-label / 2, -label / 2, label, label), ctx, circle=True)
        p.restore()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(230, 226, 216))
        p.drawEllipse(c, 2, 2)
        # brazo del tocadiscos: arriba a la izquierda, baja sobre el disco al salir
        pivot = QPointF(c.x() - 0.85 * r, c.y() - 0.85 * r)
        p.setPen(QPen(QColor(180, 176, 168), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(pivot, QPointF(c.x() - 0.30 * r, c.y() + 0.15 * r) * f + pivot * (1 - f))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(180, 176, 168))
        p.drawEllipse(pivot, 5, 5)
        self._thumb(p, it, rect, ctx)  # funda encima

    def _speaker(self, p, it, rect, f, now, ctx):
        """Latido: la portada late como un altavoz y suelta ondas con cada golpe."""
        c, s = rect.center(), rect.width()
        rgb = ctx["rgb"]
        p.setBrush(Qt.NoBrush)
        rings = 1 if ctx["light"] else 3
        for k in range(rings):
            t = ((now * 1.25 + k / rings) % 1.0) if not ctx["light"] else 0.5
            grow = s / 2 + 36 * (1 - (1 - t) ** 2) + 8 * ctx["beat"]
            p.setPen(QPen(QColor(*rgb, round(120 * (1 - t) * f)), 1.5))
            p.drawRoundedRect(QRectF(c.x() - grow, c.y() - grow, 2 * grow, 2 * grow), 0.06 * s, 0.06 * s)
        k = 1 + 0.04 * ctx["beat"]
        self._thumb(p, it, QRectF(c.x() - s * k / 2, c.y() - s * k / 2, s * k, s * k), ctx)


_fonts = {}


def _icon_font(px):
    if px not in _fonts:
        font = QFont("Segoe MDL2 Assets")
        font.setPixelSize(max(6, px))
        _fonts[px] = font
    return _fonts[px]

