import unittest

from brillomusical import effects


class TestPerimeter(unittest.TestCase):
    def test_ida_y_vuelta(self):
        w, h = 1920, 1080
        for edge, a in ((0, 100), (3, 500), (1, 300), (2, 700)):
            u = effects.perimeter_u(edge, a, w, h)
            self.assertTrue(0 <= u < 1)
            x, y, nx, ny = effects.edge_point(u, w, h)
            self.assertAlmostEqual(effects.perimeter_u(edge, x if edge < 2 else y, w, h), u, places=6)


class TestParticles(unittest.TestCase):
    def test_determinista(self):
        a, b = effects.Particles(5), effects.Particles(5)
        self.assertEqual([m["u"] for m in a.motes], [m["u"] for m in b.motes])

    def test_rangos(self):
        p = effects.Particles(1)
        now = 0.0
        for _ in range(600):
            now += 1 / 60
            p.update(now, 1 / 60, energy=1.0)
            for u, depth, alpha, kind in p.positions(now):
                self.assertTrue(0 <= u < 1)
                self.assertTrue(0 <= depth <= 1.0)
                self.assertTrue(0 <= alpha <= 1)

    def test_tope_y_vida_de_chispas(self):
        p = effects.Particles(2)
        for _ in range(20):
            p.burst(0.0, 10)
        self.assertLessEqual(len(p.sparks), effects.MAX_SPARKS)
        p.update(0.61, 0.61, energy=0.0)
        self.assertEqual(p.sparks, [])


class TestWaves(unittest.TestCase):
    def test_pulso_da_la_vuelta_en_1_5s(self):
        wv = effects.Waves()
        wv.launch(0.0)
        uc = 0.5
        self.assertGreater(wv.value(uc + 0.25, 0.75, uc), 0.3)
        self.assertLess(wv.value(uc, 0.75, uc), 0.05)
        wv.prune(1.6)
        self.assertEqual(wv.value(uc + 0.25, 1.6, uc), 0.0)

    def test_maximo_6(self):
        wv = effects.Waves()
        for i in range(10):
            wv.launch(i * 0.01)
        self.assertEqual(len(wv.pulses), 6)


class TestFire(unittest.TestCase):
    def test_hay_llamas_y_huecos(self):
        vals = [effects.fire(i / 200, 0.0) for i in range(200)]
        self.assertGreater(max(vals) - min(vals), 0.5)


class TestEnv(unittest.TestCase):
    def test_subida_y_bajada(self):
        self.assertEqual(effects.env(0.0, 0.05, 0.3), 0.0)
        self.assertAlmostEqual(effects.env(0.05, 0.05, 0.3), 1.0)
        self.assertEqual(effects.env(0.36, 0.05, 0.3), 0.0)
        self.assertEqual(effects.env(-1, 0.05, 0.3), 0.0)


if __name__ == "__main__":
    unittest.main()
