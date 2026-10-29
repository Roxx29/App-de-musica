"""Reloj de fotogramas sincronizado con la pantalla (vsync) para el borde y la ventana de letras.

Un hilo espera al refresco con DwmFlush() y emite `tick` (máx. 60/s) al hilo de Qt. Así cada
fotograma llega en su momento, sin los 31/47 ms alternos de un QTimer de Windows.
Si nadie lo necesita, el hilo duerme en un Event (cero despertares en pausa).
"""
import ctypes
import logging
import threading
import time

from PySide6.QtCore import QObject, Signal

MIN_FRAME = 1 / 75  # 60 Hz: todos los refrescos; 120/144 Hz: uno de cada dos (60-72 fps)
FALLBACK = 1 / 60

log = logging.getLogger(__name__)


class FrameClock(QObject):
    tick = Signal()

    def __init__(self):
        super().__init__()
        self._users = set()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._pending = False  # si la interfaz va lenta no se acumulan ticks
        self._lock = threading.Lock()
        self.tick.connect(self._delivered)
        try:
            self._flush = ctypes.windll.dwmapi.DwmFlush
        except (OSError, AttributeError):
            self._flush = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="vsync")
        self._thread.start()

    def want(self, name, on):
        """Cada consumidor ('glow', 'lyrics'…) pide o suelta los ticks."""
        with self._lock:
            (self._users.add if on else self._users.discard)(name)
            active = bool(self._users)
        (self._wake.set if active else self._wake.clear)()

    def stop(self):
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=1)

    def _delivered(self):
        self._pending = False

    def _run(self):
        last = 0.0
        fast = 0  # retornos instantáneos seguidos de DwmFlush
        while not self._stop.is_set():
            self._wake.wait()
            if self._stop.is_set():
                break
            t0 = time.perf_counter()
            ok = False
            if self._flush:
                try:
                    ok = self._flush() == 0
                except OSError:
                    ok = False
            fast = fast + 1 if not ok or time.perf_counter() - t0 < 0.002 else 0
            if fast >= 3:
                # DwmFlush no espera (sesión bloqueada, escritorio remoto…): no girar en vacío.
                # Uno suelto es normal (el hilo llegó tarde al refresco) y no debe costar un fotograma
                time.sleep(max(0.0, FALLBACK - (time.perf_counter() - t0)))
            now = time.perf_counter()
            # margen de 1 ms: a 144 Hz dos refrescos (13,9 ms) pasan; a 100 Hz uno retrasado (~11 ms) no
            if now - last < MIN_FRAME - 0.001 or self._pending:
                continue
            last = now
            self._pending = True
            try:
                self.tick.emit()
            except RuntimeError:
                break  # la app se cerró sin llamar a stop()
