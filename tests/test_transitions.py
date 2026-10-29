import math
import unittest

from brillomusical import transitions as tr

W, H = 1280, 720
PTS = [(200 + 80 * i, 150 + 37 * (i % 7)) for i in range(12)]


class TestStates(unittest.TestCase):
    def test_la_llegada_acaba_en_su_sitio(self):
        for style in tr.STYLES + ("cut",):
            P = tr.params(style, 42, "normal")
            end = tr.total(P, len(PTS))
            for i, (x, y) in enumerate(PTS):
                sx, sy, s, sa, la, _ = tr.in_state(P, end, x, y, i, len(PTS), W, H, src=(640, 360))
                self.assertAlmostEqual(sx, x, delta=0.5, msg=style)
                self.assertAlmostEqual(sy, y, delta=0.5, msg=style)
                self.assertAlmostEqual(s, 1.0, places=3, msg=style)
                self.assertAlmostEqual(sa, 1.0, places=3, msg=style)
                self.assertAlmostEqual(la, 1.0, places=3, msg=style)

    def test_la_salida_acaba_invisible(self):
        for style in tr.STYLES + ("cut",):
            P = tr.params(style, 7, "normal")
            end = tr.out_time(P)
            for i, (x, y) in enumerate(PTS):
                st = tr.out_state(P, end, x, y, i, len(PTS), W, H)
                self.assertLess(st[3], 0.02, style)

    def test_llegada_sin_saltos(self):
        for style in tr.STYLES:
            P = tr.params(style, 3, "normal")
            end = tr.total(P, len(PTS))
            for i, (x, y) in enumerate(PTS):
                prev = None
                t = 0.0
                while t <= end:
                    sx, sy = tr.in_state(P, t, x, y, i, len(PTS), W, H, src=(640, 360))[:2]
                    if prev and t > 0.05:
                        self.assertLess(math.hypot(sx - prev[0], sy - prev[1]), 0.08 * H, f"{style} t={t:.2f}")
                    prev = (sx, sy)
                    t += 1 / 50

    def test_opacidades_y_determinismo(self):
        for style in tr.STYLES:
            self.assertEqual(tr.params(style, 9, "calm"), tr.params(style, 9, "calm"))
            P = tr.params(style, 9, "intense")
            for t in (0, 0.1, 0.4, 0.8, 1.5):
                for st in (tr.out_state(P, t, 300, 200, 1, 5, W, H), tr.in_state(P, t, 300, 200, 1, 5, W, H)):
                    self.assertTrue(0 <= st[3] <= 1 and 0 <= st[4] <= 1, (style, t, st))

    def test_el_ambiente_cambia_la_duracion(self):
        calm = tr.params("travel", 1, "calm")["k"]
        intense = tr.params("travel", 1, "intense")["k"]
        self.assertGreater(calm, intense)


class TestPick(unittest.TestCase):
    def test_fijo(self):
        self.assertEqual(tr.pick("swirl", 1, "normal", "travel"), "swirl")

    def test_aleatoria_no_repite(self):
        for seed in range(100):
            self.assertNotEqual(tr.pick("random", seed, "normal", "rain"), "rain")
            self.assertIn(tr.pick("random", seed, "normal", "rain"), tr.STYLES)

    def test_automatica_por_ambiente(self):
        for mood, group in tr.GROUPS.items():
            for seed in range(30):
                s = tr.pick("auto", seed, mood, None)
                self.assertIn(s, group)
                self.assertNotEqual(tr.pick("auto", seed, mood, s), s)

    def test_drop_o_estribillo_fuerza_impacto(self):
        for seed in range(30):
            self.assertIn(tr.pick("auto", seed, "normal", None, special=True), ("explode", "wave"))


if __name__ == "__main__":
    unittest.main()
