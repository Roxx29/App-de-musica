import unittest

from brillomusical import history, ytm


def raw(title="Feather", pos=10.0, duration=200.0, paused=False, **kw):
    return {"title": title, "artist": "Nujabes", "album": "Modal Soul", "art": "https://x/a.jpg", "pos": pos,
            "duration": duration, "paused": paused, "rate": 1, "ad": False, "queue": [], **kw}


class TestYtm(unittest.TestCase):
    def test_parse(self):
        snap, prev = ytm.parse(raw(pos=0.5), None, 100.0)
        self.assertEqual((snap["title"], snap["artist"], snap["duration"], snap["playing"]),
                         ("Feather", "Nujabes", 200.0, True))
        self.assertEqual(snap["art_url"], "https://x/a.jpg")
        snap, prev = ytm.parse(raw(pos=30, paused=True), prev, 105.0)
        self.assertFalse(snap["playing"])
        self.assertEqual(ytm.parse(None, prev, 106.0), (None, prev))
        self.assertIsNone(ytm.parse(raw(title=""), prev, 106.0)[0])  # página cargando o sin sesión

    def test_duracion_vieja_al_cambiar(self):
        _, prev = ytm.parse(raw(pos=150), None, 100.0)
        snap, prev = ytm.parse(raw(title="Otra", pos=150), prev, 101.0)  # el <video> aún es el de antes
        self.assertEqual(snap["duration"], 0.0)
        snap, prev = ytm.parse(raw(title="Otra", pos=0.3, duration=180), prev, 101.5)
        self.assertEqual(snap["duration"], 180)

    def test_anuncio(self):
        self.assertTrue(ytm.parse(raw(ad=True), None, 0)[0]["ad"])

    def test_quien_manda(self):
        on, off, off2 = {"playing": True}, {"playing": False}, {"playing": False}
        self.assertEqual(ytm.choose(on, None), ("ext", on))
        self.assertEqual(ytm.choose(on, off), ("ext", on))  # solo suena el navegador
        self.assertEqual(ytm.choose(off, on), ("ytm", on))
        self.assertEqual(ytm.choose(on, on)[0], "ytm")
        self.assertEqual(ytm.choose(None, off)[0], "ytm")
        self.assertEqual(ytm.choose(off, off2, "ext"), ("ext", off))  # ninguna suena: sigue la que mandaba
        self.assertEqual(ytm.choose(off, off2, "ytm"), ("ytm", off2))

    def test_carrusel(self):
        before = [{"title": t} for t in ("c", "b", "a")]  # la más reciente primero
        queue = [{"title": q, "selected": q == "y"} for q in ("x", "y", "z1", "z2", "z3", "z4")]
        out = history.carousel(before, {"title": "now"}, queue, k=3)
        self.assertEqual([(k, it["title"]) for k, it, _ in out],
                         [("past", "a"), ("past", "b"), ("past", "c"), ("now", "now"),
                          ("next", "z1"), ("next", "z2"), ("next", "z3")])
        self.assertEqual(out[4][2], 2)  # índice real en la cola
        self.assertEqual([k for k, _, _ in history.carousel([], {"title": "n"}, [])], ["now"])
        self.assertEqual(history.carousel([], None, []), [])


if __name__ == "__main__":
    unittest.main()
