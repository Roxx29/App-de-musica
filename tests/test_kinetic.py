import math
import unittest

from brillomusical import kinetic


class TestKinetic(unittest.TestCase):
    def test_wrap(self):
        self.assertEqual(kinetic.wrap([10, 10, 10], 2, 22), [[0, 1], [2]])
        self.assertEqual(kinetic.wrap([50, 10], 2, 22), [[0], [1]])  # palabra larga sola
        self.assertEqual(kinetic.wrap([], 2, 22), [])

    def test_efectos_terminan_en_su_sitio_y_sin_nan(self):
        for group in kinetic.EFFECTS.values():
            for eff in group:
                for e in (0.0, 1.0):
                    for tw in (-1.0, 0.0, 0.05, 0.3, 5.0):
                        dy, s, a, fill = kinetic.word_state(eff, 3, tw, 0.5, 0.1, e, 1.0, 12.3)
                        self.assertTrue(all(math.isfinite(v) for v in (dy, s, a)), eff)
                        self.assertTrue(0 <= a <= 1)
                dy, s, a, fill = kinetic.word_state(eff, 3, 5.0, 0.5, 6.0, 0.0, 0.0, 0.0)
                if eff != "wave":  # el vaivén oscila; los demás acaban quietos y visibles
                    self.assertAlmostEqual(dy, 0, places=6)
                self.assertAlmostEqual(s, 1)
                self.assertAlmostEqual(a, 1)
                self.assertIn(fill, (None, 1.0))

    def test_pendientes_tenues(self):
        _, _, a, _ = kinetic.word_state("pop", 0, -1.0, 0.5, 2.0)
        self.assertAlmostEqual(a, kinetic.PENDING_ALPHA)

    def test_eleccion(self):
        self.assertIn(kinetic.pick(7, "calm"), kinetic.EFFECTS["calm"])
        self.assertIn(kinetic.pick(7, "raro"), kinetic.EFFECTS["normal"])
        self.assertEqual(kinetic.next_style("constellation"), "kinetic")
        self.assertEqual(kinetic.next_style("kinetic"), "ribbon")
        self.assertEqual(kinetic.next_style("ribbon"), "nyc")
        self.assertEqual(kinetic.next_style("nyc"), "loco")
        self.assertEqual(kinetic.next_style("loco"), "auto")
        self.assertEqual(kinetic.next_style("auto"), "constellation")

    def test_estilo_por_genero(self):
        for genre, style in (("Hip-Hop/Rap", "nyc"), ("R&B/Soul", "ribbon"), ("Pop Latino", "kinetic"),
                             ("K-Pop", "kinetic"), ("Dance", "kinetic"), ("Classical", "constellation"),
                             ("Singer/Songwriter", "constellation"), ("ALTERNATIVE", "ribbon")):
            self.assertEqual(kinetic.style_for(genre), style, genre)
        self.assertIsNone(kinetic.style_for(None))
        self.assertIsNone(kinetic.style_for(""))
        self.assertIsNone(kinetic.style_for("Comedy"))


if __name__ == "__main__":
    unittest.main()
