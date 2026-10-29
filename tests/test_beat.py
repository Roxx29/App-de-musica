import random
import unittest

from brillomusical import beat

HZ = 60


def feed_signal(det, values):
    beats = 0
    for i, e in enumerate(values):
        beats += det.feed(e, i / HZ)
    return beats


def clicks(bpm, seconds, noise=0.02, seed=1):
    rnd = random.Random(seed)
    period = HZ * 60 / bpm
    out = []
    for i in range(int(seconds * HZ)):
        phase = (i % period) / period
        out.append((0.8 if phase < 2 / period else 0.15) + rnd.uniform(0, noise))
    return out


class TestBeatDetector(unittest.TestCase):
    def test_clics_a_120_bpm(self):
        n = feed_signal(beat.BeatDetector(), clicks(120, 10))
        self.assertTrue(18 <= n <= 21, n)  # 2 golpes/s (el primer segundo calienta la ventana)

    def test_silencio(self):
        self.assertEqual(feed_signal(beat.BeatDetector(), [0.0] * 600), 0)

    def test_tono_constante(self):
        self.assertEqual(feed_signal(beat.BeatDetector(), [0.5] * 600), 0)


class TestEnergy(unittest.TestCase):
    def test_clasifica(self):
        self.assertEqual(beat.classify(2.0, 0.4, 0.3), "high")
        self.assertEqual(beat.classify(1.0, 0.2, 0.3), "mid")
        self.assertEqual(beat.classify(0.5, 0.2, 0.3), "low")
        self.assertEqual(beat.classify(1.0, 0.05, 0.3), "low")
        self.assertEqual(beat.classify(0.0, 0.0, 0.0), "low")  # silencio

    def test_choose(self):
        self.assertEqual(beat.choose("high", 1), "beat")
        self.assertEqual(beat.choose("mid", 2), "spin")
        self.assertEqual(beat.choose("mid", 1), "breathe")
        self.assertEqual(beat.choose("low", 3), "aurora")
        self.assertEqual(beat.choose("low", 2), "breathe")
        self.assertEqual(beat.choose(None, 3), "breathe")


class TestChooseWarm(unittest.TestCase):
    def test_tabla_alta_energia(self):
        self.assertEqual(beat.choose("high", 1, warm=True), "fire")
        self.assertEqual(beat.choose("high", 3, warm=True), "fire")
        self.assertEqual(beat.choose("high", 1), "beat")
        self.assertEqual(beat.choose("high", 2), "waves")


class TestEnvelope(unittest.TestCase):
    def run_env(self, level):
        env = beat.Envelope()
        out = [env.feed(level, 1 / HZ) for _ in range(6)]
        out += [env.feed(0.0, 1 / HZ) for _ in range(36)]
        return out

    def test_sube_rapido_y_baja(self):
        out = self.run_env(0.5)
        self.assertGreater(out[5], 0.85)
        self.assertLess(out[-1], 0.2)

    def test_normaliza_el_volumen(self):
        for a, b in zip(self.run_env(0.5), self.run_env(0.25)):
            self.assertAlmostEqual(a, b, places=6)


def run_mood(mood, level, seconds, bps=0.0, t0=0.0):
    """Alimenta el Mood a 50 Hz con un nivel fijo y golpes regulares; devuelve el tiempo final."""
    t, next_beat = t0, t0
    for _ in range(int(seconds * 50)):
        t += 0.02
        hit = bps > 0 and t >= next_beat
        if hit:
            next_beat += 1 / bps  # sin acumular el redondeo de los pasos de 20 ms
        mood.feed(level, hit, 0.02)
    return t


class TestMood(unittest.TestCase):
    def test_tranquila_y_luego_intensa_con_histeresis(self):
        m = beat.Mood()
        m.start("a")
        t = run_mood(m, 0.1, 30)
        self.assertEqual(m.state, "calm")
        run_mood(m, 0.6, 1, bps=2.5, t0=t)  # un pico de 1 s no cambia nada
        self.assertEqual(m.state, "calm")
        run_mood(m, 0.6, 19, bps=2.5, t0=t + 1)  # puede pasar por "normal" (mínimo 8 s por estado)
        self.assertEqual(m.state, "intense")

    def test_drop(self):
        m = beat.Mood()
        m.start("a")
        t = run_mood(m, 0.5, 20, bps=2)
        t = run_mood(m, 0.08, 9, t0=t)  # calma (el nivel medio tarda unos segundos en bajar)
        m.pop_drop()
        run_mood(m, 0.7, 1.0, bps=2, t0=t)  # vuelve fuerte de golpe
        self.assertTrue(m.pop_drop())
        self.assertFalse(m.pop_drop())  # evento único

    def test_tempo(self):
        m = beat.Mood()
        m.start("a")
        run_mood(m, 0.4, 10, bps=2)
        self.assertAlmostEqual(m.bpm, 120, delta=4)
        m2 = beat.Mood()
        m2.start("b")
        import random
        rnd = random.Random(1)
        for _ in range(500):
            m2.feed(0.4, rnd.random() < 0.08, 0.02)
        self.assertIsNone(m2.bpm)

    def test_eleccion_por_ambiente(self):
        self.assertEqual(beat.choose_glow("intense", 1, True), "fire")
        self.assertEqual(beat.choose_glow("intense", 1, False), "beat")
        self.assertEqual(beat.choose_glow("normal", 2, False), "spin")
        self.assertEqual(beat.choose_glow("normal", 1, False), "waves")
        self.assertEqual(beat.choose_glow("calm", 3, False), "aurora")
        self.assertEqual(beat.choose_glow("calm", 1, False), "breathe")
        self.assertEqual(beat.choose_bg("calm", 5), "blur")
        self.assertEqual(beat.choose_bg("calm", 40), "kenburns")
        self.assertEqual(beat.choose_bg("normal", 0), "ambient")
        self.assertEqual(beat.choose_bg("intense", 0), "beat")
        self.assertEqual(beat.choose_bg("intense", 0, gap=True), "kenburns")


class TestAutoMode(unittest.TestCase):
    def test_decide_a_los_8s_y_no_cambia(self):
        auto = beat.AutoMode()
        auto.start("song")
        sig = clicks(120, 8.5)
        det = beat.BeatDetector()
        for i, e in enumerate(sig):
            auto.feed(e, det.feed(e, i / HZ), 1 / HZ, n_colors=1)
            if i < 7.9 * HZ:
                self.assertIsNone(auto.decided)
        self.assertEqual(auto.decided, "beat")
        for _ in range(600):
            auto.feed(0.0, False, 1 / HZ, n_colors=1)  # silencio después: no cambia
        self.assertEqual(auto.mode, "beat")

    def test_cache_por_cancion(self):
        auto = beat.AutoMode()
        auto.start("a")
        for _ in range(9 * HZ):
            auto.feed(0.0, False, 1 / HZ, n_colors=3)
        auto.start("b")
        self.assertIsNone(auto.decided)
        self.assertEqual(auto.mode, "aurora")  # mantiene el último modo mientras decide: sin parpadeo
        auto.start("a")
        self.assertEqual(auto.decided, "aurora")

    def test_manual_gana(self):
        self.assertEqual(beat.resolve("spin", "beat"), "spin")
        self.assertEqual(beat.resolve("auto", "beat"), "beat")


if __name__ == "__main__":
    unittest.main()
