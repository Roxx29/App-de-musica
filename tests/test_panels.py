import unittest

from brillomusical import history, panels


class TestPanels(unittest.TestCase):
    def test_botones(self):
        x, y, w, h = panels.pill_rect(720)
        self.assertGreaterEqual(y, 60)
        self.assertLessEqual(y + h, 720)
        names = [panels.BUTTONS[panels.button_at(x + w / 2, y + 6 + panels.BTN * (i + 0.5), 720)][0]
                 for i in range(len(panels.BUTTONS))]
        self.assertEqual(names, ["prev", "back", "play", "fwd", "next"])
        self.assertIsNone(panels.button_at(x + w + 5, y + 50, 720))
        self.assertIsNone(panels.button_at(x + 5, y - 5, 720))

    def test_carrusel_cabe_y_crece(self):
        for h in (270, 720, 1440):
            for focus, amount in ((None, 0.0), (0, 1.0), (3, 1.0), (6, 0.5)):
                lay = panels.strip_layout(7, focus, amount, h)
                top = lay[0][0] - lay[0][1] / 2
                bottom = lay[-1][0] + lay[-1][1] / 2
                self.assertGreaterEqual(top, panels.STRIP_TOP - 1e-6)
                self.assertLessEqual(bottom, h - panels.STRIP_BOTTOM + 1e-6)
        lay = panels.strip_layout(5, 2, 1.0, 1440)
        sizes = [s for _, s in lay]
        self.assertEqual(max(sizes), sizes[2])
        self.assertAlmostEqual(sizes[2], panels.BIG)
        self.assertEqual(panels.item_at(lay[2][0], lay), 2)
        self.assertIsNone(panels.item_at(5, lay))
        self.assertEqual(panels.strip_layout(0, None, 0, 720), [])

    def test_actual_en_el_medio(self):
        lay = panels.strip_layout(7, 3, 0.35, 900, center=3)
        self.assertAlmostEqual(lay[3][0], 450)
        lay = panels.strip_layout(4, 0, 0.35, 900, center=0)  # sin nada arriba: no se sale por arriba
        self.assertGreaterEqual(lay[0][0] - lay[0][1] / 2, panels.STRIP_TOP - 1e-6)

    def test_historial(self):
        hist = history.History(limit=3)
        for k in ("a", "b", "c", "b", "d"):
            hist.add(k, k.upper(), "x")
        self.assertEqual([it["key"] for it in hist.items], ["d", "b", "c"])  # sin repetir y con límite
        hist.set_thumb("b", "img")
        hist.add("b", "B", "x")
        self.assertEqual(hist.items[0]["thumb"], "img")  # conserva la miniatura
        self.assertEqual([it["key"] for it in hist.before()], ["d", "c"])
        self.assertEqual(history.search_url("Feather", "Nujabes"),
                         "https://music.youtube.com/search?q=Feather+Nujabes")


if __name__ == "__main__":
    unittest.main()
