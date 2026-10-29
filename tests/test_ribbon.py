import math
import unittest

from brillomusical import ribbon


class TestRibbon(unittest.TestCase):
    def test_curva_continua_y_dentro(self):
        tr = ribbon.track(1600, 900)
        length = tr[0][-1]
        self.assertGreater(length, 1600)
        prev = None
        for k in range(101):
            x, y, ang, u = ribbon.at(tr, length * k / 100)
            self.assertTrue(all(math.isfinite(v) for v in (x, y, ang)))
            self.assertAlmostEqual(u, k / 100, places=6)
            if prev:
                self.assertLess(math.hypot(x - prev[0], y - prev[1]), length / 50)  # sin saltos
            prev = (x, y)
        self.assertIsNone(ribbon.at(tr, -1))
        self.assertIsNone(ribbon.at(tr, length + 1))

    def test_final_de_reves(self):
        self.assertLess(math.cos(ribbon.twist(1.0)), -0.5)  # al final se ve el reverso
        self.assertGreater(math.cos(ribbon.twist(0.45)), -1.1)

    def test_scroll_monotono_y_estable(self):
        times, offs, widths = [0.0, 1.0, 5.0], [0.0, 100.0, 180.0], [90.0, 70.0, 60.0]
        vals = [ribbon.scroll(t / 10, times, offs, widths) for t in range(0, 80)]
        self.assertEqual(vals, sorted(vals))
        self.assertEqual(ribbon.scroll(2.0, times, offs, widths), 180.0)  # pasó la palabra y espera
        self.assertEqual(ribbon.scroll(2.0, times, offs, widths), ribbon.scroll(2.0, times, offs, widths))
        self.assertAlmostEqual(ribbon.scroll(2.5, times, offs, widths, None), 100 + 80 * 1.5 / 4)  # velocidad constante
        self.assertEqual(ribbon.scroll(-1, times, offs, widths), 0.0)
        self.assertEqual(ribbon.scroll(700, times, offs, widths, None), 240.0)  # más allá del final, sin error

    def test_rotulo(self):
        self.assertIsNone(ribbon.card(-0.1))
        self.assertIsNone(ribbon.card(ribbon.CARD_END))
        a = ribbon.card(0.0)
        b = ribbon.card(2.0)
        self.assertEqual(a[2], 0.0)
        self.assertEqual(b[:3], (1.0, 1.0, 1.0))
        self.assertGreater(ribbon.card(3.3)[3], 0.5)  # saliendo


if __name__ == "__main__":
    unittest.main()
