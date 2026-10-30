"""Latido: letra en tipografía cinética, una línea grande que se mueve con la música (sin Qt).

Todo sale de la posición de la canción (tiempo desde la palabra y desde la línea): pausa,
saltos y desfase no dan tirones. Los desplazamientos van en "em" (fracción del tamaño de letra).
"""
import math

STYLES = ("constellation", "kinetic", "ribbon", "nyc")  # "ribbon" con ribbon.py, "nyc" con nyc.py
STYLE_NAMES = {"constellation": "Constelación", "kinetic": "Latido", "ribbon": "Cinta", "nyc": "Nueva York"}
# dos efectos por ambiente; cada línea elige uno con su semilla
EFFECTS = {"calm": ("rise", "sweep"), "normal": ("pop", "wave"), "intense": ("zoom", "fall")}
LINE_IN = 0.25  # entrada de la línea
PENDING_ALPHA = 0.45


SETTINGS = ("auto",) + STYLES  # "auto": el estilo lo decide el género de la canción
SETTING_NAMES = {"auto": "Automático (según el género)", **STYLE_NAMES}
# géneros de iTunes (tienda de EE. UU., en inglés) → estilo; en orden: "hip-hop" antes que "pop"
GENRES = (("nyc", ("hip-hop", "rap")),
          ("ribbon", ("r&b", "soul", "jazz", "alternative", "indie", "lo-fi", "funk", "blues")),
          ("kinetic", ("electronic", "dance", "house", "edm", "pop", "latin", "urbano", "reggaeton", "rock", "metal",
                       "punk")),
          ("constellation", ("classical", "ambient", "acoustic", "singer/songwriter", "soundtrack", "new age",
                             "country", "folk", "regional", "christian", "easy listening", "vocal")))


def next_style(s):
    return SETTINGS[(SETTINGS.index(s) + 1) % len(SETTINGS)] if s in SETTINGS else SETTINGS[0]


def style_for(genre):
    """Estilo para un género de iTunes; None si no hay género o no se reconoce."""
    g = (genre or "").lower()
    return next((style for style, words in GENRES if any(w in g for w in words)), None) if g else None


def pick(seed, mood):
    group = EFFECTS.get(mood, EFFECTS["normal"])
    return group[seed % len(group)]


def wrap(widths, space, max_w):
    """Reparte palabras en filas que no pasen de max_w; [[índices], …]. Una palabra larga va sola."""
    rows, row, x = [], [], 0.0
    for i, w in enumerate(widths):
        need = w if not row else x + space + w
        if row and need > max_w:
            rows.append(row)
            row, need = [], w
        row.append(i)
        x = need
    if row:
        rows.append(row)
    return rows


def _clamp(v):
    return max(0.0, min(1.0, v))


def _out_cubic(t):
    return 1 - (1 - t) ** 3


def _out_back(t, c=1.70158):
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def word_state(effect, i, tw, dur, line_age, energy=0.0, beat=0.0, now=0.0):
    """(dy en em, escala, opacidad, relleno) de la palabra i.

    tw: segundos desde que empieza la palabra (negativo = aún no cantada). dur: lo que dura.
    relleno: 0..1 del barrido (solo "sweep"; None en los demás).
    """
    k = _clamp(line_age / LINE_IN)  # la línea entra subiendo y apareciendo
    dy, scale = 0.35 * (1 - _out_cubic(k)), 1.0
    alpha = k * (1.0 if tw >= 0 else PENDING_ALPHA)
    fill = None
    a = _clamp(tw / 0.4) if tw >= 0 else 0.0
    if effect == "rise":  # las pendientes esperan un poco más abajo y suben al cantarse
        dy += 0.15 * (1 - _out_cubic(a))
    elif effect == "sweep":  # karaoke: se rellena de izquierda a derecha durante la palabra
        fill = _clamp(tw / max(dur, 0.15)) if tw >= 0 else 0.0
        alpha = k
    elif effect == "pop" and tw >= 0:  # golpe al empezar: 1,25 → 1
        scale = 1 + 0.25 * (1 - _out_cubic(_clamp(tw / 0.24)))
    elif effect == "wave":  # vaivén suave de toda la línea; más amplio con más energía
        dy -= (0.03 + 0.08 * energy) * math.sin(2 * math.pi * 0.5 * now - 0.6 * i)
    elif effect == "zoom" and tw >= 0:  # impacto: 1,5 → 1 muy rápido
        z = _clamp(tw / 0.2)
        scale, alpha = 1 + 0.5 * (1 - z) ** 3, alpha * _clamp(tw / 0.06)
    elif effect == "fall":  # cascada: cada palabra cae a su sitio, escalonadas
        f = _clamp((line_age - 0.04 * i) / 0.35)
        dy -= 0.6 * (1 - _out_back(f))
        alpha *= _clamp(f * 3)
    if tw >= 0 and tw < dur + 0.1:  # la palabra que suena late con los golpes
        scale *= 1 + 0.08 * beat * (0.5 + energy)
    return dy, scale, alpha, fill
