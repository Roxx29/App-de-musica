"""Menú de rueda arriba en el centro de la ventana de la letra: un abanico de 180° que se despliega hacia abajo.

Al acercar el ratón aparece un botón; con clic o quedándose 0,35 s encima, los sectores salen
escalonados con rebote. Se pinta dentro de la ventana (sin widgets) y solo pide fotogramas
mientras se anima.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen

# (acción, icono de Segoe MDL2 Assets, nombre)
ITEMS = (("style", "", "Estilo"), ("transition", "", "Transición"), ("bg", "", "Fondo"),
         ("cover", "", "Carátula"), ("quality", "", "Calidad"), ("fullscreen", "", "Pantalla completa"))
CY, BUTTON = 30.0, 16.0  # centro (px desde arriba) y radio del botón
R_IN, R_OUT = 40.0, 112.0
ZONE_W, ZONE_H = 130.0, 90.0  # media anchura y altura de la zona que muestra el botón
DWELL, LINGER = 0.35, 0.6  # quedarse encima abre; al salir se cierra tras 0,6 s
OPEN_T, CLOSE_T, STAGGER, ITEM_T = 0.37, 0.16, 0.03, 0.22
HOVER_T, BUTTON_T = 0.12, 0.16
GAP = math.radians(1.5)  # media separación entre sectores


def sector_at(dx, dy, n=len(ITEMS), r_in=R_IN, r_out=R_OUT):
    """Sector bajo (dx, dy) relativo al centro (y hacia abajo), de izquierda a derecha; None fuera."""
    r = math.hypot(dx, dy)
    if dy < 0 or not r_in <= r <= r_out:
        return None
    return min(n - 1, int((math.pi - math.atan2(dy, dx)) / (math.pi / n)))


def _approach(v, target, dt, secs):
    step = dt / secs
    return min(target, v + step) if v < target else max(target, v - step)


def _out_back(t, c=1.4):
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


class Wheel:
    def __init__(self):
        self.near = False  # ratón en la zona
        self.button = 0.0  # visibilidad del botón 0..1
        self.open = 0.0  # 0 cerrada … 1 abierta (cerrando se recorre al revés, sin rebote)
        self.target = 0.0
        self.hover = None
        self.hovers = [0.0] * len(ITEMS)
        self.enter_t = self.leave_t = None
        self.hint_until = 0.0  # primera vez: el botón se ve unos segundos aunque no se acerque el ratón
        self.last = None

    # --- ratón (px lógicos de la ventana) ---
    def move(self, x, y, w, now):
        dx, dy = x - w / 2, y - CY
        near = (abs(dx) < ZONE_W and y < ZONE_H) or (self.target and math.hypot(dx, dy) < R_OUT + 24)
        if near and not self.near:
            self.enter_t = now
        if not near and self.near:
            self.leave_t = now
        self.near = near
        self.hover = sector_at(dx, dy) if self.target else None

    def hit(self, x, y, w):
        """¿Cae (x, y) en el botón o en la rueda abierta? (sin cambiar nada)."""
        r = math.hypot(x - w / 2, y - CY)
        return r <= BUTTON + 6 or bool(self.target and r <= R_OUT)

    def reset(self):
        """Ventana oculta: todo cerrado al momento (sin animaciones que pidan fotogramas)."""
        self.__init__()

    def press(self, x, y, w):
        """Clic: 'toggle' en el botón, la acción del sector, o None si no es de la rueda."""
        dx, dy = x - w / 2, y - CY
        if math.hypot(dx, dy) <= BUTTON + 6:
            self.toggle()
            return "toggle"
        if self.target:
            i = sector_at(dx, dy)
            return ITEMS[i][0] if i is not None else None
        return None

    def toggle(self, on=None):
        self.target = float(not self.target if on is None else on)
        self.enter_t = self.leave_t = None

    def busy(self, now):
        show = 1.0 if self.near or self.target or now < self.hint_until else 0.0
        return (now < self.hint_until or self.button != show or self.open != self.target
                or any(0 < v < 1 for v in self.hovers) or (self.hover is not None and self.hovers[self.hover] < 1)
                or (self.near and not self.target and self.enter_t is not None)  # esperando para abrir
                or (self.target and not self.near and self.leave_t is not None))  # esperando para cerrar

    def update(self, now):
        dt = 0.0 if self.last is None else min(0.1, now - self.last)
        self.last = now
        if self.near and not self.target and self.enter_t is not None and now - self.enter_t >= DWELL:
            self.toggle(True)
        if self.target and not self.near and self.leave_t is not None and now - self.leave_t >= LINGER:
            self.toggle(False)
        show = self.near or self.target or now < self.hint_until
        self.button = _approach(self.button, 1.0 if show else 0.0, dt, BUTTON_T)
        self.open = _approach(self.open, self.target, dt, OPEN_T if self.target else CLOSE_T)
        for i in range(len(ITEMS)):
            self.hovers[i] = _approach(self.hovers[i], 1.0 if i == self.hover else 0.0, dt, HOVER_T)

    # --- dibujo ---
    def draw(self, p, w, rgb, value, label_pixmap, now):
        """value(acción) → texto del valor actual; label_pixmap(texto) → QPixmap con sombra."""
        self.update(now)
        if self.button <= 0 and self.open <= 0:
            return
        c = QPointF(w / 2, CY)
        p.save()
        if self.open > 0:
            self._fan(p, c, rgb)
            if self.hover is not None and self.open > 0.6:
                key, _, name = ITEMS[self.hover]
                pm = label_pixmap(f"{name} · {value(key)}")
                dpr = pm.devicePixelRatio()
                pw, ph = pm.width() / dpr, pm.height() / dpr
                pill = QRectF(c.x() - pw / 2 - 10, CY + R_OUT + 12, pw + 20, ph + 8)
                path = QPainterPath()
                path.addRoundedRect(pill, ph / 2 + 4, ph / 2 + 4)
                p.setOpacity(min(1.0, (self.open - 0.6) / 0.4))
                p.fillPath(path, QColor(0, 0, 0, 120))
                p.drawPixmap(QPointF(pill.x() + 10, pill.y() + 4), pm)
        # botón: baja 8 px al aparecer, con un latido suave mientras es pista
        b = 1 - (1 - self.button) ** 3
        pulse = 1 + 0.04 * math.sin(now * 4) if now < self.hint_until and not self.near else 1.0
        p.setOpacity(b)
        p.translate(0, -8 * (1 - b))
        p.setPen(QPen(QColor(255, 255, 255, 41), 1))
        p.setBrush(QColor(10, 10, 14, 153))
        p.drawEllipse(c, BUTTON * pulse, BUTTON * pulse)
        p.setPen(QColor(*rgb).lighter(130) if self.target else QColor(255, 255, 255, 220))
        p.setFont(self._icon_font(13))
        p.drawText(QRectF(c.x() - BUTTON, c.y() - BUTTON, 2 * BUTTON, 2 * BUTTON), Qt.AlignCenter,
                   "" if self.target else "")  # Cerrar / Más
        p.restore()

    def _fan(self, p, c, rgb):
        n = len(ITEMS)
        span = math.pi / n
        t_open = self.open * OPEN_T
        hl = QColor(*rgb)
        hl.setHslF(hl.hslHueF(), hl.hslSaturationF(), max(0.55, min(0.68, hl.lightnessF())), 0.6)
        dark_icon = hl.lightnessF() > 0.6 and (0.3 * hl.redF() + 0.59 * hl.greenF() + 0.11 * hl.blueF()) > 0.55
        for i, (_, icon, _) in enumerate(ITEMS):
            # sale del centro en orden de izquierda a derecha; cerrando, todos a la vez (sin rebote)
            local = max(0.0, min(1.0, (t_open - STAGGER * i) / ITEM_T)) if self.target else self.open
            if local <= 0:
                continue
            e = _out_back(local) if self.target else 1 - (1 - local) ** 2  # cierre: frena al final, sin rebote
            hv = self.hovers[i]
            scale = (0.6 + 0.4 * e) * (1 + 0.04 * hv)
            # ángulos en Qt (y abajo): de 180° (izquierda) a 0° (derecha) pasando por abajo
            a1, a0 = math.pi - span * i - GAP, math.pi - span * (i + 1) + GAP
            rot = math.radians(-10 * (1 - e))
            path = QPainterPath()
            r_in, r_out = R_IN * scale, R_OUT * scale
            path.arcMoveTo(QRectF(c.x() - r_out, c.y() - r_out, 2 * r_out, 2 * r_out), -math.degrees(a0 + rot))
            path.arcTo(QRectF(c.x() - r_out, c.y() - r_out, 2 * r_out, 2 * r_out), -math.degrees(a0 + rot),
                       -math.degrees(a1 - a0))
            path.arcTo(QRectF(c.x() - r_in, c.y() - r_in, 2 * r_in, 2 * r_in), -math.degrees(a1 + rot),
                       math.degrees(a1 - a0))
            path.closeSubpath()
            p.setOpacity(min(1.0, local * 1.5))
            p.setPen(QPen(QColor(255, 255, 255, round(30 + 60 * hv)), 1))
            base = QColor(12, 12, 16, 158)
            p.setBrush(QColor.fromRgbF(base.redF() + (hl.redF() - base.redF()) * hv,
                                       base.greenF() + (hl.greenF() - base.greenF()) * hv,
                                       base.blueF() + (hl.blueF() - base.blueF()) * hv,
                                       base.alphaF() + (hl.alphaF() - base.alphaF()) * hv))
            p.drawPath(path)
            mid = (a0 + a1) / 2 + rot
            rm = (r_in + r_out) / 2
            ic = QPointF(c.x() + rm * math.cos(mid), c.y() + rm * math.sin(mid))
            p.setPen(QColor(20, 20, 24) if dark_icon and hv > 0.5 else QColor(255, 255, 255, 235))
            p.setFont(self._icon_font(round(18 * scale)))
            p.drawText(QRectF(ic.x() - 16, ic.y() - 16, 32, 32), Qt.AlignCenter, icon)
        p.setOpacity(1.0)

    _fonts = {}

    def _icon_font(self, px):
        if px not in self._fonts:
            f = QFont("Segoe MDL2 Assets")  # iconos de Windows 10/11, sin archivos extra
            f.setPixelSize(max(6, px))
            self._fonts[px] = f
        return self._fonts[px]
