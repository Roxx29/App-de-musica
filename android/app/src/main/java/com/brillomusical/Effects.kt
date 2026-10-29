package com.brillomusical

import android.graphics.Color
import android.os.SystemClock
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Efectos del borde (port de effects.py y glow.py). Rellena una cinta de colores ARGB a lo largo
 * del perímetro: u = 0..1 desde arriba a la izquierda, en sentido horario. Sin objetos por fotograma.
 */
class Effects {
    var level = 0f; private set       // nivel global: 1 sonando, 0,5 en pausa, 0 anuncio/oculto
    var coreColor = 0; private set
    var coreAlpha = 0f; private set
    var hidden = false                // app delante a pantalla completa

    private var primary = NowPlaying.color
    private var from = primary; private var to = primary; private var colorT0 = -10_000L
    private var mode = "Respirar"; private var prev = mode; private var modeT0 = -10_000L
    private var autoLast = "Respirar"
    private var last = SystemClock.uptimeMillis()
    private var phase = 0f
    private var fade = 1f
    private var pulseN = -1L; private var pulseAt = -10_000L; private var hitSeen = Beat.hitAt
    private val waves = LongArray(6) { -10_000L }; private var wi = 0
    private val comT = LongArray(3) { -10_000L }; private val comU = FloatArray(3); private var ci = 0
    private val cols = IntArray(3)
    private val hsv = FloatArray(3); private val hsv2 = FloatArray(3)
    private var hue0 = 0f

    /** Llamar al cambiar NowPlaying: fundido de color de 800 ms desde el color visible. */
    fun song() {
        if (NowPlaying.color != to) { from = primary; to = NowPlaying.color; colorT0 = SystemClock.uptimeMillis() }
    }

    private fun target() = when {
        !Prefs.glowOn || (hidden && !NowPlaying.lyricsOpen) || NowPlaying.title.isEmpty() || NowPlaying.ad -> 0f
        NowPlaying.playing -> 1f
        else -> 0.5f
    }

    /** ¿Hacen falta más fotogramas? Sonando, o mientras termina un fundido. */
    fun animating(now: Long) = level != target() || now - colorT0 < 800 || now - modeT0 < 600 ||
        (NowPlaying.playing && level > 0f && mode != "Estático")

    fun slow() = mode == "Respirar" || mode == "Aurora" || mode == "Giratorio" || mode == "Arcoíris"

    fun frame(now: Long, w: Int, h: Int, px: IntArray) {
        val dt = (now - last).coerceIn(0, 100); last = now
        val e = Beat.energy()
        val tg = target() // 400 ms de 0 a 1 (anuncios, pausa, ocultar)
        level = if (level < tg) min(tg, level + dt / 400f) else max(tg, level - dt / 400f)

        val n = NowPlaying.positionMs() / Beat.PERIOD
        if (n != pulseN) {
            if (NowPlaying.playing) { pulseAt = now; if (n % 2 == 0L) { waves[wi] = now; wi = (wi + 1) % waves.size } }
            pulseN = n
        }
        if (Beat.hitAt != hitSeen) { // cambio de línea: cometa en Destello
            hitSeen = Beat.hitAt; comT[ci] = now; comU[ci] = Math.random().toFloat(); ci = (ci + 1) % 3
        }

        // modo con fundido de 600 ms (300 apagando + 300 encendiendo); si se interrumpe, sale desde donde está
        val want = resolve(Prefs.edge)
        if (want != mode) {
            val md = now - modeT0
            if (md >= 300) { prev = mode; modeT0 = now - ((1 - min(1f, (md - 300) / 300f)) * 300).toLong() }
            mode = want
        }
        val md = now - modeT0
        val m = if (md < 300) prev else mode
        fade = if (md < 300) 1 - md / 300f else min(1f, (md - 300) / 300f)

        primary = lerpHsv(from, to, ease(((now - colorT0) / 800f).coerceIn(0f, 1f)))
        cols[0] = primary
        Color.colorToHSV(primary, hsv); hue0 = hsv[0] / 360f
        for (i in 1..2) cols[i] = NowPlaying.palette.getOrNull(i) ?: run {
            hsv2[0] = (hsv[0] + (if (i == 1) 28.8f else 331.2f)) % 360f; hsv2[1] = hsv[1]; hsv2[2] = hsv[2] // tonos vecinos ±0,08
            Color.HSVToColor(hsv2)
        }

        // fase integrada: acelerar en un golpe no hace saltar el dibujo
        val boost = env(now - pulseAt, 50, 500)
        phase = (phase + dt / 1000f * (1 + 2 * boost) / (if (m == "Arcoíris") 12 else 10)) % 1f

        val t = now / 1000.0
        val uniform = when (m) {
            "Respirar" -> { val s = (0.5 - 0.5 * cos(2 * PI * t / 5)).toFloat(); val lo = 0.35f - 0.1f * e; lo + (0.8f + 0.05f * e - lo) * s }
            "Al ritmo" -> 0.35f + 0.2f * e + 0.5f * env(now - pulseAt, 60, 300)
            "Estático" -> 0.7f
            else -> -1f
        }
        if (uniform >= 0) px.fill(argb(uniform, 0.95f, cols[0]))
        else {
            val uc = (1.5f * w + h) / (2f * (w + h)) // centro de abajo: de ahí salen las ondas
            for (k in px.indices) px[k] = ribbon(m, (k + 0.5f) / px.size, t, e, now, uc)
        }
        coreColor = mix(cols[0], Color.WHITE, 0.35f)
        coreAlpha = min(1f, (0.45f + 0.25f * e + 0.4f * env(now - pulseAt, 30, 180)) * fade)
    }

    private fun ribbon(m: String, u: Float, t: Double, e: Float, now: Long, uc: Float): Int = when (m) {
        "Giratorio" -> {
            val x = ((u + phase) % 1f) * 3; val i = x.toInt() % 3; val f = x - x.toInt()
            argb(0.7f, 0.95f, mix(cols[i], cols[(i + 1) % 3], f * f * (3 - 2 * f)))
        }
        "Arcoíris" -> {
            hsv2[0] = ((hue0 + u + phase) % 1f) * 360; hsv2[1] = 0.85f; hsv2[2] = 1f
            argb(0.7f, 0.95f, Color.HSVToColor(hsv2))
        }
        "Aurora" -> { // dos ondas lentas; el pulso las hace crecer
            val swell = 1 + 0.3f * env(now - pulseAt, 100, 800)
            val w1 = (0.5 + 0.5 * sin(2 * PI * (2 * u + t / 17))).toFloat()
            val w2 = (0.5 + 0.5 * sin(2 * PI * (3 * u - t / 13) + 1)).toFloat()
            argb((0.3f + 0.4f * (0.6f * w1 + 0.4f * w2)) * swell, 0.95f, mix(mix(cols[0], cols[1], w1), cols[2], w2 * 0.6f))
        }
        "Fuego" -> {
            val f = fire(u, t); val flare = env(now - pulseAt, 50, 250)
            val c0 = cols[0]
            val deep = mix(Color.rgb((Color.red(c0) * 0.45f).toInt(), (Color.green(c0) * 0.45f).toInt(), (Color.blue(c0) * 0.45f).toInt()), EMBER_DARK, 0.3f)
            argb(0.12f + 0.83f * f + 0.25f * flare, 0.7f, mix(deep, mix(c0, EMBER_HOT, 0.65f), f))
        }
        "Ondas" -> { val v = wave(u, now, uc); argb(0.3f + 0.2f * e + 0.6f * v, 0.95f, mix(cols[0], Color.WHITE, 0.4f * v)) }
        else -> { // Destello: cometa principal (una vuelta cada 3 s) + cometas en cada cambio de línea
            var k = max(0f, 1 - ((((t / 3) % 1.0).toFloat() - u).mod(1f)) / 0.2f).let { it * it }
            for (j in 0..2) {
                val age = now - comT[j]
                if (age < 1500) {
                    val head = (comU[j] + age / 3000f) % 1f
                    val q = max(0f, 1 - ((head - u).mod(1f)) / 0.2f)
                    k = max(k, (1 - age / 1500f) * q * q)
                }
            }
            argb(0.3f + 0.6f * k, 0.7f, mix(cols[0], Color.WHITE, 0.6f * k))
        }
    }

    /** Pulsos que salen del centro de abajo hacia los dos lados y se encuentran arriba en 1,5 s. */
    private fun wave(u: Float, now: Long, uc: Float): Float {
        var total = 0f
        for (t0 in waves) {
            val age = now - t0
            if (age in 0L until 1500L) {
                val d = 0.5f * age / 1500f; val amp = 1 - age / 1500f
                total += amp * (g(circ(u, uc + d)) + g(circ(u, uc - d)))
            }
        }
        return min(1f, total)
    }

    private fun g(d: Float) = exp(-d * d / (2 * 0.04f * 0.04f))
    private fun circ(a: Float, b: Float): Float { val d = (a - b).mod(1f); return min(d, 1 - d) }

    private fun argb(a: Float, cap: Float, c: Int) = ((a.coerceIn(0f, cap) * fade * 255).toInt() shl 24) or (c and 0xFFFFFF)

    private fun lerpHsv(a: Int, b: Int, f: Float): Int {
        if (f >= 1f) return b
        Color.colorToHSV(a, hsv); Color.colorToHSV(b, hsv2)
        val dh = ((hsv2[0] - hsv[0] + 540f) % 360f) - 180f // camino de tono más corto
        hsv[0] = (hsv[0] + dh * f + 360f) % 360f
        hsv[1] += (hsv2[1] - hsv[1]) * f; hsv[2] += (hsv2[2] - hsv[2]) * f
        return Color.HSVToColor(hsv)
    }

    /** Automático (idea de AutoMode de beat.py): una elección por canción según la densidad de la letra y la portada. */
    private fun resolve(edge: String): String {
        if (edge != "Automático") return edge
        if (NowPlaying.lyricsState == NowPlaying.LyricsState.LOADING) return autoLast // sin parpadeo mientras carga
        val lines = NowPlaying.lines
        val dur = if (NowPlaying.durationMs > 0) NowPlaying.durationMs else lines.lastOrNull()?.timeMs ?: 0L
        val perMin = if (dur > 0) lines.size * 60_000f / dur else 0f
        Color.colorToHSV(to, hsv2)
        val warm = hsv2[1] > 0.4f && (hsv2[0] < 50f || hsv2[0] > 330f)
        val nc = NowPlaying.palette.size
        autoLast = when {
            lines.isEmpty() -> if (nc >= 2) "Giratorio" else "Respirar"
            perMin >= 28 -> if (warm) "Fuego" else if (nc <= 1) "Al ritmo" else "Ondas"
            perMin >= 16 -> if (nc >= 2) "Giratorio" else "Respirar"
            else -> if (nc >= 3) "Aurora" else "Respirar"
        }
        return autoLast
    }

    companion object {
        private val EMBER_DARK = Color.rgb(128, 13, 0)
        private val EMBER_HOT = Color.rgb(255, 235, 166)
        private val NOISE = java.util.Random(9).let { r -> FloatArray(256) { r.nextFloat() } }

        /** Envolvente de un golpe: sube lineal en `rise` ms, baja cuadrática en `fall` ms. */
        fun env(dt: Long, rise: Int, fall: Int): Float = when {
            dt < 0 || dt >= rise + fall -> 0f
            dt < rise -> dt / rise.toFloat()
            else -> (1 - (dt - rise) / fall.toFloat()).let { it * it }
        }

        fun ease(t: Float) = if (t < 0.5f) 4 * t * t * t else 1 - (-2 * t + 2).let { it * it * it } / 2

        fun mix(a: Int, b: Int, f: Float) = Color.rgb(
            (Color.red(a) + (Color.red(b) - Color.red(a)) * f).toInt(),
            (Color.green(a) + (Color.green(b) - Color.green(a)) * f).toInt(),
            (Color.blue(a) + (Color.blue(b) - Color.blue(a)) * f).toInt())

        /** Ruido 1D suave y periódico (256). */
        private fun noise(x: Double): Float {
            val i = floor(x); val f = (x - i).toFloat(); val k = Math.floorMod(i.toLong(), 256L).toInt()
            val a = NOISE[k]; val b = NOISE[(k + 1) % 256]
            return a + (b - a) * f * f * (3 - 2 * f)
        }

        /** Llamas en u: dos ruidos que se desplazan y un parpadeo de ~10 Hz. */
        private fun fire(u: Float, t: Double): Float {
            val n = 0.6f * noise(u * 40.0 + t * 1.6) + 0.4f * noise(u * 97.0 - t * 3.3)
            val flicker = (0.85 + 0.15 * sin(2 * PI * 10 * t + u * 60)).toFloat()
            return ((n - 0.3f) * 2.2f).coerceIn(0f, 1f) * flicker
        }
    }
}
