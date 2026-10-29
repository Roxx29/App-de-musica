import unittest

from brillomusical import quality


def run(g, ms, secs, t0=0.0, fps=60):
    """Alimenta `secs` segundos de fotogramas de `ms`; devuelve (t final, ¿bajó alguna vez?)."""
    dropped, n = False, int(secs * fps)
    for i in range(1, n + 1):
        dropped |= g.feed(ms, t0 + i / fps)
    return t0 + n / fps, dropped


class TestGovernor(unittest.TestCase):
    def test_baja_tras_4_s_lentos_y_avisa(self):
        g = quality.Governor("auto", cores=8)
        t, dropped = run(g, 15, 3.5)
        self.assertFalse(g.light)
        t, dropped = run(g, 15, 2.5, t)
        self.assertTrue(g.light and dropped)

    def test_una_vez_en_ligera_se_queda(self):
        g = quality.Governor("auto", cores=8)
        t, _ = run(g, 15, 6)
        self.assertTrue(g.light)
        _, dropped = run(g, 1, 30, t)
        self.assertTrue(g.light)
        self.assertFalse(dropped)  # el aviso sale una sola vez

    def test_manual_manda(self):
        g = quality.Governor("high", cores=8)
        _, dropped = run(g, 30, 10)
        self.assertFalse(g.light or dropped)
        self.assertTrue(quality.Governor("light", cores=8).light)

    def test_sin_animacion_continua_no_cuenta(self):
        g = quality.Governor("auto", cores=8)
        run(g, 50, 20, fps=5)  # repintados sueltos (pausa)
        self.assertFalse(g.light)

    def test_equipo_de_2_nucleos_empieza_en_ligera(self):
        self.assertTrue(quality.Governor("auto", cores=2).light)
        self.assertEqual(quality.Governor("raro", cores=8).setting, "auto")
        self.assertEqual([quality.next_setting(s) for s in quality.SETTINGS], ["high", "light", "auto"])


if __name__ == "__main__":
    unittest.main()
