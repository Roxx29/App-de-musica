import math
import unittest

from brillomusical import loco


class TestLoco(unittest.TestCase):
    def test_cuando_cambia(self):
        self.assertFalse(loco.decide("drop", "intense", 5, 7.9))  # nunca antes de 8 s
        self.assertTrue(loco.decide("drop", "calm", 0, 8.0))
        self.assertTrue(loco.decide("chorus", "calm", 0, 9))
        self.assertTrue(loco.decide("stanza", "intense", 1, 9))
        self.assertFalse(loco.decide("stanza", "normal", 1, 9))
        self.assertTrue(loco.decide("stanza", "normal", 2, 9))
        self.assertFalse(loco.decide("stanza", "calm", 2, 9))
        self.assertTrue(loco.decide("stanza", "calm", 3, 9))

    def test_estilo_y_transicion_sin_repetir(self):
        styles = ("constellation", "kinetic", "ribbon", "nyc")
        for seed in range(20):
            self.assertNotEqual(loco.next_style(styles, "nyc", seed), "nyc")
            self.assertEqual(loco.next_style(styles, "nyc", seed), loco.next_style(styles, "nyc", seed))
            for reason in ("drop", "chorus", "intense", "normal", "calm"):
                k = loco.pick(reason, "normal", "shock", seed)
                self.assertIn(k, loco.DURATION)
                self.assertNotEqual(k, "shock")
        self.assertEqual(loco.pick("drop", "normal", None, 0, light=True), "zoom")
        self.assertEqual(loco.duration("liquid", "calm"), 1.2)

    def test_formas_cubren_al_final_y_nada_al_principio(self):
        for th in (i * math.pi / 18 for i in range(36)):
            self.assertEqual(loco.iris(th, 0.0), 0.0)
            self.assertGreater(loco.iris(th, 1.0), 1.0)  # más que la semidiagonal: tapa toda la pantalla
            self.assertEqual(loco.blob(th, 0.0, 0.0), 0.0)
            self.assertGreater(loco.blob(th, 1.0, 3.0, 1.0, 1.0), 1.0)
        self.assertTrue(all(w == 1.0 for w in loco.blinds(0.0)))
        self.assertTrue(all(w == 0.0 for w in loco.blinds(1.0)))

    def test_cristal(self):
        tris = loco.shards(5)
        self.assertEqual(len(tris), 48)
        area = sum(abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2 for a, b, c in tris)
        self.assertAlmostEqual(area, 1.0, places=6)  # los trozos cubren la pantalla entera
        dx, dy, rot, sc, alpha = loco.shard_state(tris[0], 0, 0.0)
        self.assertEqual((dx, dy, rot, sc, alpha), (0.0, 0.0, 0.0, 1.0, 1.0))  # al principio, en su sitio
        self.assertEqual(loco.shard_state(tris[0], 0, 1.0)[4], 0.0)  # al final, desaparecido


if __name__ == "__main__":
    unittest.main()
