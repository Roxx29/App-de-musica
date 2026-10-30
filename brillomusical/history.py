"""Sonó antes: las canciones que han sonado mientras la app está abierta (sin Qt, sin disco)."""
import urllib.parse

LIMIT = 30


class History:
    def __init__(self, limit=LIMIT):
        self.items = []  # la más reciente primero: {"key", "title", "artist", "thumb"}
        self.limit = limit

    def add(self, key, title, artist):
        """Canción que empieza: si ya estaba, sube arriba (sin repetirse) y conserva su miniatura."""
        old = next((it for it in self.items if it["key"] == key), None)
        if old:
            self.items.remove(old)
        self.items.insert(0, old or {"key": key, "title": title, "artist": artist, "thumb": None})
        del self.items[self.limit:]

    def set_thumb(self, key, thumb):
        for it in self.items:
            if it["key"] == key:
                it["thumb"] = thumb

    def before(self):
        """Las anteriores a la que suena."""
        return self.items[1:]


def search_url(title, artist):
    return "https://music.youtube.com/search?" + urllib.parse.urlencode({"q": f"{title} {artist}".strip()})


def carousel(before, current, queue, k=3):
    """Carrusel con la que suena en el medio: [(tipo, canción, índice en la cola)].

    Arriba las k últimas escuchadas (la más antigua primero), luego la actual y abajo las k siguientes
    de la cola de YouTube Music (solo con YouTube Music integrado).
    """
    out = [("past", it, None) for it in reversed(before[:k])]
    if current:
        out.append(("now", current, None))
    sel = next((i for i, q in enumerate(queue) if q.get("selected")), -1)
    out += [("next", q, i) for i, q in enumerate(queue) if i > sel][:k]
    return out
