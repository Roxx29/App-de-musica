import unittest

from brillomusical import artwork, cover


class TestCoverLogic(unittest.TestCase):
    def test_ciclo_de_posiciones(self):
        self.assertEqual([cover.next_mode(m) for m in cover.MODES], ["top", "center", "hidden", "card"])
        self.assertEqual(cover.next_mode("raro"), "card")

    def test_tarjeta_dentro_de_la_ventana(self):
        for w, h in ((480, 270), (1280, 720), (2560, 1440)):
            g = cover.card_geometry(w, h)
            self.assertTrue(48 <= g["a"] <= 150)
            self.assertGreaterEqual(g["text_w"], 0)
            self.assertGreaterEqual(g["x"], 16)
            self.assertLessEqual(g["x"] + g["w"], w)
            self.assertLessEqual(g["y"] + g["h"], h - 16 + 1e-9)
            self.assertGreaterEqual(g["y"], 0)

    def test_zona_reservada_contiene_la_tarjeta(self):
        w, h = 1280, 720
        g = cover.card_geometry(w, h)
        x0, y0, x1, y1 = cover.avoid_rect("card", w, h)
        self.assertLessEqual(x0, g["x"] / w)
        self.assertLessEqual(y0, g["y"] / h)
        self.assertGreaterEqual(x1, (g["x"] + g["w"]) / w)
        self.assertGreaterEqual(y1, (g["y"] + g["h"]) / h)
        for mode in ("top", "center", "hidden"):
            self.assertIsNone(cover.avoid_rect(mode, w, h))

    def test_progreso(self):
        self.assertIsNone(cover.progress(10, 0))
        self.assertEqual(cover.progress(-5, 100), 0.0)
        self.assertEqual(cover.progress(500, 100), 1.0)
        self.assertAlmostEqual(cover.progress(25, 100), 0.25)


class TestHero(unittest.TestCase):
    def test_tamano_limitado(self):
        x, y, s = cover.hero_geometry(1280, 720, 1000)
        self.assertAlmostEqual(s, min(0.42 * 720, 0.32 * 1280))
        self.assertAlmostEqual(x + s / 2, 640)
        self.assertAlmostEqual(y + s / 2, 0.40 * 720)
        self.assertAlmostEqual(cover.hero_geometry(1280, 720, 100)[2], 250)  # nunca más de 2,5× la portada real

    def test_origen_por_posicion(self):
        w, h = 1280, 720
        g = cover.card_geometry(w, h)
        x, y, s = cover.origin_rect("card", w, h)
        self.assertAlmostEqual(x, g["x"] + g["pad"])
        self.assertAlmostEqual(s, g["a"])
        self.assertAlmostEqual(cover.origin_rect("center", w, h)[2], 0.55 * h)
        hx, hy, hs = cover.hero_geometry(w, h, 1000)
        self.assertAlmostEqual(cover.origin_rect("hidden", w, h, 1000)[2], 0.9 * hs)

    def test_arco(self):
        a, b = (100, 600, 80), (500, 200, 300)
        self.assertEqual(cover.arc_lerp(a, b, 0.0, 50), a)
        self.assertEqual(cover.arc_lerp(b, a, 0.0, 50), b)
        x, y, s = cover.arc_lerp(a, b, 1.0, 50)
        self.assertAlmostEqual(x, 500)
        self.assertAlmostEqual(y, 200)
        mid = cover.arc_lerp(a, b, 0.5, 50)
        self.assertLess(mid[1], (600 + 200) / 2)  # sube en arco


class TestArtwork(unittest.TestCase):
    results = [
        {"trackName": "Otra canción", "artistName": "Bizarrap", "artworkUrl100": "https://x/a/100x100bb.jpg"},
        {"trackName": "Toy en el Mic", "artistName": "Bizarrap & Milo j", "artworkUrl100": "https://x/b/100x100bb.jpg"},
    ]

    def test_elige_la_que_coincide(self):
        self.assertEqual(artwork.pick(self.results, "Toy en el Mic", "Bizarrap y Milo j"), "https://x/b/1000x1000bb.jpg")

    def test_sin_coincidencia_no_inventa(self):
        self.assertIsNone(artwork.pick(self.results, "Feather", "Sabrina Carpenter"))
        self.assertIsNone(artwork.pick([], "Feather", "Sabrina Carpenter"))

    def test_ignora_parentesis_y_mayusculas(self):
        res = [{"trackName": "Feather (Sped Up)", "artistName": "Sabrina Carpenter",
                "artworkUrl100": "https://u/100x100bb.png"}]
        self.assertEqual(artwork.pick(res, "FEATHER", "sabrina carpenter"), "https://u/1000x1000bb.png")

    def test_itunes_pide_1000(self):
        self.assertTrue(artwork.pick(self.results, "Toy en el Mic", "Bizarrap y Milo j").endswith("1000x1000bb.jpg"))

    def test_deezer_coincide_y_duracion(self):
        data = [{"title": "Otra", "duration": 180, "artist": {"name": "Queen"},
                 "album": {"cover_xl": "https://cdn-images.dzcdn.net/images/cover/a/1000x1000.jpg"}},
                {"title": "Bohemian Rhapsody (Remastered 2011)", "duration": 355, "artist": {"name": "Queen"},
                 "album": {"cover_xl": "https://cdn-images.dzcdn.net/images/cover/b/1000x1000.jpg"}}]
        self.assertEqual(artwork.pick_deezer(data, "Bohemian Rhapsody", "Queen", 354),
                         "https://cdn-images.dzcdn.net/images/cover/b/1000x1000.jpg")
        self.assertIsNone(artwork.pick_deezer(data, "Bohemian Rhapsody", "Queen", 200))  # otra versión
        self.assertEqual(artwork.pick_deezer(data, "Bohemian Rhapsody", "Queen", 0)[-14:], "b/1000x1000.jpg"[-14:])

    def test_deezer_rechaza_otro_host(self):
        data = [{"title": "Feather", "duration": 185, "artist": {"name": "Sabrina Carpenter"},
                 "album": {"cover_xl": "https://malo.example.com/x.jpg"}}]
        self.assertIsNone(artwork.pick_deezer(data, "Feather", "Sabrina Carpenter", 185))

    def test_rechaza_urls_que_no_son_https(self):
        res = [{"trackName": "Feather", "artistName": "Sabrina Carpenter", "artworkUrl100": "file:///C:/x/100x100bb.png"}]
        self.assertIsNone(artwork.pick(res, "Feather", "Sabrina Carpenter"))


if __name__ == "__main__":
    unittest.main()
