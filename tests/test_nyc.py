import random
import unittest

from brillomusical import nyc


def words(rnd, n):
    return [(rnd.uniform(1.2, 6.0), rnd.uniform(0.1, 1.5), rnd.randint(1, 10)) for _ in range(n)]


class TestNyc(unittest.TestCase):
    def test_sin_solapes_y_determinista(self):
        rnd = random.Random(1)
        for seed in range(200):
            ws = words(rnd, rnd.randint(1, 14))
            rects = nyc.place(ws, seed)
            self.assertEqual(rects, nyc.place(ws, seed))
            self.assertEqual(len(rects), len(ws))
            for i, a in enumerate(rects):
                for b in rects[:i]:
                    sep = (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])
                    self.assertTrue(sep, (seed, a, b))
            self.assertFalse(rects[-1][4])  # la del zoom nunca va vertical

    def test_primera_con_alto_fijo(self):
        rects = nyc.place([(3.0, 0.5, 6), (2.0, 0.3, 4)], 7, first=1.4)
        self.assertEqual(rects[0][3], 1.4)

    def test_camara_continua_y_enlaza_con_la_siguiente(self):
        ws = words(random.Random(3), 6)
        rects = nyc.place(ws, 5)
        t_next = 14.0
        prev = None
        starts = [10.0, 10.1, 10.2, 10.6, 11.5, 12.0]  # palabras más rápidas que el movimiento de cámara
        for i in range(0, 5000):
            pos = 9.5 + i * 0.001
            cx, cy, sc, _ = nyc.camera(pos, starts, rects, t_next, 1600, 900)
            if prev:
                self.assertLess(abs(sc - prev[2]) / prev[2], 0.02)  # sin saltos de zoom entre muestras de 1 ms
                self.assertLess(abs(cx - prev[0]) + abs(cy - prev[1]), 0.2)  # un salto sería de varias unidades
            prev = (cx, cy, sc)
        end = nyc.camera(t_next - 1e-9, starts, rects, t_next, 1600, 900)
        nxt = nyc.frame(rects[-1:], 1600, 900)
        for a, b in zip(end[:3], nxt):
            self.assertAlmostEqual(a, b, places=3)  # al empezar la línea siguiente, el mismo plano
        self.assertLess(end[3], 0.01)  # las demás ya se han apagado

    def test_zoom_aunque_la_ultima_llegue_tarde(self):
        rects = nyc.place(words(random.Random(4), 4), 2)
        starts, t_next = [10.0, 10.2, 10.4, 10.9], 11.0  # la última, 0,1 s antes de la línea siguiente
        end = nyc.camera(t_next - 1e-9, starts, rects, t_next, 1600, 900)
        for a, b in zip(end[:3], nyc.frame(rects[-1:], 1600, 900)):
            self.assertAlmostEqual(a, b, places=3)

    def test_paso_entre_lineas_continuo(self):
        # al acabar una línea entra ×8 en la placa; la siguiente empieza en ×8 y sale: sin salto en la frontera
        self.assertAlmostEqual(nyc.dive(5.0, 2.0, 5.0), nyc.DIVE_MAX)
        self.assertAlmostEqual(nyc.dive(5.0, 5.0, 9.0), nyc.DIVE_MAX)
        self.assertAlmostEqual(nyc.dive(3.5, 2.0, 5.0), 1.0)
        prev = None
        for i in range(2000):
            pos = 4.0 + i * 0.001
            m = nyc.dive(pos, 2.0 if pos <= 5.0 else 5.0, 5.0 if pos <= 5.0 else 9.0)
            if prev:
                self.assertLess(abs(m - prev) / prev, 0.03)
            prev = m

    def test_tamanos_y_metro(self):
        self.assertLess(nyc.size(2, 1.0), nyc.size(6, 0.2))  # "me", "por": pequeñas
        self.assertEqual(nyc.mta((240, 240, 240)), (252, 204, 10))  # gris: amarillo taxi
        self.assertEqual(nyc.mta((10, 60, 200)), (0, 57, 166))
        self.assertEqual(nyc.mta((230, 30, 40)), (238, 53, 46))

    def test_fondos(self):
        self.assertEqual([nyc.next_bg(b) for b in nyc.BGS], ["cover", "city", "asphalt"])
        self.assertEqual(nyc.next_bg("raro"), "asphalt")


if __name__ == "__main__":
    unittest.main()
