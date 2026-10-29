"""Pico de audio (0..1) de las sesiones del navegador, vía IAudioMeterInformation con ctypes puro.

Solo el navegador: así Discord o un juego no cuentan como golpes. Si no se encuentra su
sesión, se usa el medidor de toda la salida (`self.fallback = True`).
Llamar desde un único hilo (el de Qt).
"""
import ctypes
import os
import time
from ctypes import HRESULT, POINTER, byref, c_float, c_uint, c_void_p, wintypes

BROWSERS = ("opera.exe", "opera_gx.exe", "chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe", "firefox.exe")
REENUM = 3.0  # segundos entre búsquedas de sesiones nuevas


class GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]

    def __init__(self, s):
        super().__init__()
        ole32.CLSIDFromString(f"{{{s}}}", byref(self))


ole32 = ctypes.OleDLL("ole32")
kernel32 = ctypes.WinDLL("kernel32")
CLSID_MMDeviceEnumerator = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioSessionManager2 = GUID("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")
IID_IAudioSessionControl2 = GUID("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D")
IID_IAudioMeterInformation = GUID("C02216F6-8C67-4B5B-9D00-D008E73E0064")
CLSCTX_ALL = 0x17


def _call(ptr, index, *args, argtypes=()):
    """Llama al método `index` de la vtable de un puntero COM (lanza OSError si HRESULT falla)."""
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    return ctypes.WINFUNCTYPE(HRESULT, c_void_p, *argtypes)(vtbl[index])(ptr, *args)


def _release(ptr):
    if ptr:
        vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
        ctypes.WINFUNCTYPE(c_uint, c_void_p)(vtbl[2])(ptr)


def _qi(ptr, iid):
    out = c_void_p()
    _call(ptr, 0, byref(iid), byref(out), argtypes=(POINTER(GUID), POINTER(c_void_p)))
    return out


def _process_name(pid):
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(260), wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


class Meter:
    def __init__(self):
        ole32.CoInitializeEx.restype = ctypes.c_long  # S_FALSE / RPC_E_CHANGED_MODE no son errores aquí
        ole32.CoInitializeEx(None, 2)  # Qt ya inicializa COM en su hilo; esto no hace daño
        self.enum = c_void_p()
        ole32.CoCreateInstance(byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                               byref(IID_IMMDeviceEnumerator), byref(self.enum))
        self.meters = []
        self.fallback = False
        self.t_enum = 0.0

    def _clear(self):
        for m in self.meters:
            _release(m)
        self.meters = []

    def _enumerate(self):
        self._clear()
        self.t_enum = time.monotonic()
        device = manager = sessions = c_void_p()
        try:
            device = c_void_p()
            _call(self.enum, 4, 0, 1, byref(device), argtypes=(c_uint, c_uint, POINTER(c_void_p)))  # eRender, eMultimedia
            manager = c_void_p()
            _call(device, 3, byref(IID_IAudioSessionManager2), CLSCTX_ALL, None, byref(manager),
                  argtypes=(POINTER(GUID), c_uint, c_void_p, POINTER(c_void_p)))
            sessions = c_void_p()
            _call(manager, 5, byref(sessions), argtypes=(POINTER(c_void_p),))
            count = ctypes.c_int()
            _call(sessions, 3, byref(count), argtypes=(POINTER(ctypes.c_int),))
            for i in range(count.value):
                ctl = ctl2 = c_void_p()
                try:
                    ctl = c_void_p()
                    _call(sessions, 4, i, byref(ctl), argtypes=(ctypes.c_int, POINTER(c_void_p)))
                    ctl2 = _qi(ctl, IID_IAudioSessionControl2)
                    pid = wintypes.DWORD()
                    _call(ctl2, 14, byref(pid), argtypes=(POINTER(wintypes.DWORD),))
                    if _process_name(pid.value) in BROWSERS:
                        self.meters.append(_qi(ctl, IID_IAudioMeterInformation))
                except OSError:
                    pass  # sesión que desaparece mientras se enumera
                finally:
                    _release(ctl2)
                    _release(ctl)
            self.fallback = not self.meters
            if self.fallback:  # sin sesión del navegador: toda la salida
                m = c_void_p()
                _call(device, 3, byref(IID_IAudioMeterInformation), CLSCTX_ALL, None, byref(m),
                      argtypes=(POINTER(GUID), c_uint, c_void_p, POINTER(c_void_p)))
                self.meters.append(m)
        finally:
            _release(sessions)
            _release(manager)
            _release(device)

    def peak(self):
        """Pico actual 0..1. Lanza OSError si el dispositivo falla (se reintenta en la siguiente llamada)."""
        if not self.meters or time.monotonic() - self.t_enum > REENUM:
            self._enumerate()
        best = 0.0
        v = c_float()
        try:
            for m in self.meters:
                _call(m, 3, byref(v), argtypes=(POINTER(c_float),))
                best = max(best, v.value)
        except OSError:
            self._clear()
            raise
        return best

    def close(self):
        self._clear()
        _release(self.enum)
        self.enum = c_void_p()


if __name__ == "__main__":  # prueba manual: python -m brillomusical.audio
    meter = Meter()
    for _ in range(100):
        p = meter.peak()
        print(f"{'(salida general) ' if meter.fallback else ''}{p:5.3f} " + "#" * int(p * 60))
        time.sleep(0.05)
    meter.close()
