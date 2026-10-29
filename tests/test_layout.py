import math
import unittest

from brillomusical import layout


def lrc(*items):
    return list(items)


class TestStanzas(unittest.TestCase):
    def test_corta_en_linea_vacia(self):
        lines = lrc((0, "a b"), (2, "c d"), (4, ""), (5, "e f"))
        self.assertEqual(layout.stanzas(lines), [[0, 1], [3]])

    def test_corta_en_hueco_largo(self):
        lines = lrc((0, "a"), (2, "b"), (20, "c"))
        self.assertEqual(layout.stanzas(lines), [[0, 1], [2]])

    def test_maximo_4_lineas_repartidas(self):
        lines = [(i * 2.0, "x y") for i in range(6)]
        self.assertEqual(layout.stanzas(lines), [[0, 1, 2], [3, 4, 5]])

    def test_sin_letra_y_una_linea(self):
        self.assertEqual(layout.stanzas([]), [])
        self.assertEqual(layout.stanzas([(1, "hola")]), [[0]])

    def test_stanza_of(self):
        st = [[0, 1], [3]]
        self.assertEqual(layout.stanza_of(st, 1), 0)
        self.assertEqual(layout.stanza_of(st, 2), 0)  # línea vacía: sigue la estrofa anterior
        self.assertEqual(layout.stanza_of(st, 3), 1)
        self.assertIsNone(layout.stanza_of(st, -1))


class TestPlace(unittest.TestCase):
    def test_determinista_y_distinta_con_otra_semilla(self):
        self.assertEqual(layout.place(20, 7), layout.place(20, 7))
        self.assertNotEqual(layout.place(20, 7), layout.place(20, 8))

    def test_dentro_de_margenes(self):
        for x, y in layout.place(30, 3):
            self.assertTrue(layout.MARGIN <= x <= 1 - layout.MARGIN)
            self.assertTrue(layout.MARGIN <= y <= 1 - layout.MARGIN)

    def test_sin_solapes(self):
        pts = layout.place(24, 11)
        a = layout.ASPECT
        for i, (x1, y1) in enumerate(pts):
            for x2, y2 in pts[:i]:
                self.assertGreaterEqual(math.hypot((x1 - x2) * a, y1 - y2), layout.MIN_DIST - 1e-9)

    def test_evita_la_zona_reservada(self):
        avoid = (0.0, 0.7, 0.4, 1.0)  # esquina inferior izquierda (tarjeta)
        for seed in range(200):
            pts = layout.place(24, seed, avoid)
            self.assertEqual(len(pts), 24)
            for x, y in pts:
                self.assertFalse(avoid[0] <= x <= avoid[2] and avoid[1] <= y <= avoid[3], (seed, x, y))
        self.assertEqual(layout.place(10, 3, avoid), layout.place(10, 3, avoid))

    def test_visible_tope(self):
        self.assertEqual(layout.visible(range(40), 30), list(range(7, 31)))
        self.assertEqual(layout.visible(range(5), 2), [0, 1, 2])


class TestSongShape(unittest.TestCase):
    lines = [(0, "verso uno aqui"), (3, "sigue el verso"), (6, ""),
             (8, "este es el coro"), (10, "canta el coro"), (12, ""),
             (14, "otro verso distinto"), (17, ""),
             (19, "este es el coro"), (21, "canta el coro")]

    def test_estribillos(self):
        groups = layout.stanzas(self.lines)
        self.assertEqual(layout.chorus(self.lines, groups), {1, 3})

    def test_huecos_instrumentales(self):
        lines = [(20.0, "empieza tarde"), (23.0, "otra"), (45.0, "tras el solo"), (47.0, "")]
        gaps = layout.gaps(lines, 12)
        self.assertEqual(len(gaps), 2)
        self.assertAlmostEqual(gaps[0][0], 2.0)  # intro
        self.assertAlmostEqual(gaps[0][1], 18.5)
        self.assertTrue(23 < gaps[1][0] < 30 and abs(gaps[1][1] - 43.5) < 1e-9)
        self.assertEqual(layout.gaps([(1, "a"), (3, "b")], 12), [])


if __name__ == "__main__":
    unittest.main()
