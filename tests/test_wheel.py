import math
import unittest

from brillomusical import wheel


class TestWheel(unittest.TestCase):
    def test_sectores_de_izquierda_a_derecha(self):
        r = (wheel.R_IN + wheel.R_OUT) / 2
        n = len(wheel.ITEMS)
        for i in range(n):
            a = math.pi - (i + 0.5) * math.pi / n  # centro del sector i (y hacia abajo)
            self.assertEqual(wheel.sector_at(r * math.cos(a), r * math.sin(a)), i)

    def test_fuera_de_la_rueda(self):
        self.assertIsNone(wheel.sector_at(0, 5))  # centro
        self.assertIsNone(wheel.sector_at(0, wheel.R_OUT + 1))
        self.assertIsNone(wheel.sector_at(0, -60))  # por encima
        self.assertEqual(wheel.sector_at(-60, 0), 0)  # borde izquierdo exacto

    def test_abre_al_quedarse_y_cierra_al_salir(self):
        w = wheel.Wheel()
        w.move(500, 20, 1000, 0.0)
        w.update(0.1)
        self.assertEqual(w.target, 0)
        w.update(0.5)
        self.assertEqual(w.target, 1)
        self.assertEqual(w.press(500 - 76, 30, 1000), "style")  # sector 0, a la izquierda
        w.move(500, 600, 1000, 1.0)
        w.update(1.4)
        self.assertEqual(w.target, 1)
        w.update(1.7)
        self.assertEqual(w.target, 0)
        for t in (1.8, 1.9, 2.0, 2.4):
            w.update(t)
        self.assertEqual(w.open, 0)
        self.assertFalse(w.busy(2.5))


if __name__ == "__main__":
    unittest.main()
