import unittest

from brillomusical import backdrop


class TestRects(unittest.TestCase):
    def inside(self, r):
        x, y, w, h = r
        self.assertGreaterEqual(x, -1e-9)
        self.assertGreaterEqual(y, -1e-9)
        self.assertLessEqual(x + w, 1 + 1e-9)
        self.assertLessEqual(y + h, 1 + 1e-9)

    def test_cover_rect_rellena_sin_deformar(self):
        x, y, w, h = backdrop.cover_rect(16 / 9, 1.0)
        self.assertAlmostEqual(w, 1.0)
        self.assertAlmostEqual(h, 9 / 16)  # textura cuadrada en ventana 16:9: se recorta arriba y abajo
        self.inside((x, y, w, h))

    def test_cover_rect_con_zoom_y_centro_extremo_dentro(self):
        for cx, cy in ((0, 0), (1, 1), (0.5, 0.5), (0, 1)):
            self.inside(backdrop.cover_rect(16 / 9, 1.3, cx, cy))

    def test_kenburns_siempre_dentro(self):
        for i in range(400):
            zoom, cx, cy = backdrop.kenburns(i * 0.7)
            self.assertTrue(1.10 - 1e-9 <= zoom <= 1.25 + 1e-9)
            self.inside(backdrop.cover_rect(16 / 9, zoom, cx, cy))


class TestBlobs(unittest.TestCase):
    def test_deterministas_y_en_rango(self):
        a, b = backdrop.blobs(42), backdrop.blobs(42)
        self.assertEqual(a, b)
        self.assertNotEqual(a, backdrop.blobs(43))
        self.assertEqual(len(a), 4)
        for bl in a:
            for t in (0, 13.7, 500):
                x, y, ang = backdrop.blob_pos(bl, t)
                self.assertTrue(-0.1 <= x <= 1.1 and -0.1 <= y <= 1.1)


class TestMisc(unittest.TestCase):
    def test_dim_limitado(self):
        self.assertAlmostEqual(backdrop.dim_for(0.0), 0.30)
        self.assertAlmostEqual(backdrop.dim_for(1.0), 0.50)
        self.assertAlmostEqual(backdrop.dim_for(5.0), 0.50)
        self.assertLess(backdrop.dim_for(0.2), backdrop.dim_for(0.6))

    def test_ciclo_de_modos(self):
        seen = ["none"]
        for _ in range(len(backdrop.MODES)):
            seen.append(backdrop.next_mode(seen[-1]))
        self.assertEqual(seen[-1], "none")
        self.assertEqual(set(seen), set(backdrop.MODES))
        self.assertEqual(backdrop.next_mode("raro"), backdrop.MODES[0])


if __name__ == "__main__":
    unittest.main()
