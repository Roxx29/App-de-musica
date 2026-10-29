package com.brillomusical

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.tan
import kotlin.random.Random

/**
 * Transiciones entre estrofas (puro, port de transitions.py).
 * Estado de cada estrella en `o`: x, y, escala, opacidad de estrella, opacidad de texto, estela (px).
 */
object Transitions {
    val STYLES = listOf("Viaje", "Remolino", "Explosión", "Lluvia de estrellas", "Polvo", "Reconstelar", "Onda")
    const val CUT = "Corte" // saltos de varias estrofas: fundido rápido
    private val CALM = listOf("Reconstelar", "Polvo", "Remolino")
    private val NORMAL = listOf("Viaje", "Remolino", "Lluvia de estrellas")
    private val INTENSE = listOf("Explosión", "Onda", "Viaje")
    private const val RAIN = "Lluvia de estrellas"
    private const val BURST = 0.15f // Explosión: fin de la anticipación

    // (salida, retraso de la llegada, llegada) en segundos antes del factor k
    private val TIMES = mapOf(
        "Viaje" to floatArrayOf(0.7f, 0.15f, 0.9f), "Remolino" to floatArrayOf(0.8f, 0.25f, 1.0f),
        "Explosión" to floatArrayOf(0.65f, 0.2f, 0.7f), RAIN to floatArrayOf(0.9f, 0.1f, 0.8f),
        "Polvo" to floatArrayOf(0.9f, 0f, 0.9f), "Reconstelar" to floatArrayOf(0.35f, 0f, 1.1f),
        "Onda" to floatArrayOf(0.75f, 0.3f, 0.7f), CUT to floatArrayOf(0.3f, 0f, 0.45f))

    /** Variación de una transición (sale de una semilla por estrofa). */
    class P(val style: String, val k: Float, val salt: Float, val cx: Float, val cy: Float, val rot: Float, val dir: Float,
            val turns: Float, val wind: Float, val order: Int, val curve: Float, val force: Float)

    private fun mood(e: Float) = if (e < 0.45f) CALM else if (e < 0.7f) NORMAL else INTENSE

    /** Estilo para este cambio: fijo, aleatorio (sin repetir) o automático (según la energía). */
    fun pick(setting: String, seed: Long, energy: Float, prev: String?): String {
        if (setting in STYLES) return setting
        val pool = if (setting == "Aleatoria") STYLES else mood(energy)
        val choices = pool.filter { it != prev }.ifEmpty { pool }
        return choices[Random(seed).nextInt(choices.size)]
    }

    fun params(style: String, seed: Long, energy: Float): P {
        val r = Random(seed)
        fun u(a: Float, b: Float) = a + (b - a) * r.nextFloat()
        val speed = (if (energy < 0.45f) 1.3f else if (energy < 0.7f) 1f else 0.8f) * u(0.85f, 1.15f)
        val base = total(style, 1f, Layout.MAX_WORDS)
        // cambio de estrofa entre 0,8 y 1,2 s; el corte va aparte
        val k = if (style == CUT) 1f else (speed * base).coerceIn(0.8f, 1.2f) / base
        val rad = (PI / 180).toFloat()
        return P(style, k, r.nextFloat() * 100, u(-0.15f, 0.15f), u(-0.12f, 0.12f), u(-8f, 8f) * rad,
            if (r.nextBoolean()) 1f else -1f, u(0.5f, 1.25f), u(-20f, 20f) * rad, r.nextInt(3), u(-0.1f, 0.1f), u(0.6f, 1.2f))
    }

    private fun outTime(style: String, k: Float) = (TIMES.getValue(style)[0] + if (style == RAIN) 0.25f else 0f) * k
    private fun total(style: String, k: Float, n: Int): Float {
        val t = TIMES.getValue(style)
        val extra = if (style == RAIN) 0.04f * min(n, 20) else 0f
        return max(outTime(style, k), (t[1] + t[2] + extra) * k)
    }
    fun outTime(p: P) = outTime(p.style, p.k)
    fun total(p: P, n: Int) = total(p.style, p.k, n)

    private fun clamp(v: Float) = v.coerceIn(0f, 1f)
    private fun smooth(a: Float, b: Float, x: Float): Float { val t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t) }
    private fun outBack(t: Float): Float { val c = 1.70158f; val u = t - 1; return 1 + (c + 1) * u * u * u + c * u * u }
    /** 0..1 estable por estrella (en Double: en Float el seno de números grandes pierde precisión). */
    private fun hash(i: Int, salt: Float): Float { val v = sin(i * 12.9898 + salt * 78.233) * 43758.5453; return (((v % 1.0) + 1.0) % 1.0).toFloat() }
    private fun set(o: FloatArray, x: Float, y: Float, s: Float, sa: Float, la: Float, tr: Float) {
        o[0] = x; o[1] = y; o[2] = s; o[3] = sa; o[4] = la; o[5] = tr
    }

    /** Estrella de la estrofa que se va. */
    fun outState(p: P, t: Float, x: Float, y: Float, i: Int, w: Float, h: Float, o: FloatArray) {
        val k = p.k
        val u = clamp(t / (TIMES.getValue(p.style)[0] * k))
        val cx = w * (0.5f + p.cx); val cy = h * (0.5f + p.cy)
        val dx = x - cx; val dy = y - cy
        when (p.style) {
            "Viaje" -> { // vuela hacia la cámara acelerando; la palabra se va antes que la estrella
                val s = 1 / (1 - 0.6f * u * u * u); val a = p.rot * u
                set(o, cx + (dx * cos(a) - dy * sin(a)) * s, cy + (dx * sin(a) + dy * cos(a)) * s, s,
                    1 - smooth(0.2f, 0.8f, u), 1 - smooth(0f, 0.35f, u), 0f)
            }
            "Remolino" -> { // espiral hacia el centro
                val f = (1 - u).let { it * kotlin.math.sqrt(it) }; val a = p.dir * p.turns * 2 * PI.toFloat() * u * u
                set(o, cx + (dx * cos(a) - dy * sin(a)) * f, cy + (dx * sin(a) + dy * cos(a)) * f, 0.4f + 0.6f * f,
                    1 - smooth(0.5f, 1f, u), 1 - smooth(0f, 0.3f, u), 0f)
            }
            "Explosión" -> { // se encoge un 12 % y estalla con frenado
                val tt = t / k; val d = hypot(dx, dy)
                val ux = if (d > 1) dx / d else cos(i * 2.4f); val uy = if (d > 1) dy / d else sin(i * 2.4f)
                if (tt < BURST) { val f = 1 - 0.12f * smooth(0f, BURST, tt); o[0] = cx + dx * f; o[1] = cy + dy * f }
                else {
                    val dist = p.force * (0.6f + 0.6f * hash(i, p.salt)) * h * (1 - exp(-4 * (tt - BURST)))
                    o[0] = cx + dx * 0.88f + ux * dist; o[1] = cy + dy * 0.88f + uy * dist
                }
                o[2] = 1f; o[3] = 1 - smooth(BURST, BURST + 0.5f, tt); o[4] = 1 - smooth(0f, 0.15f, tt); o[5] = 0f
            }
            RAIN -> { // caen con gravedad, escalonadas
                val tt = t / k
                val order = when (p.order) { 0 -> x / w; 1 -> 1 - x / w; else -> hash(i, p.salt) }
                val fall = max(0f, tt - 0.25f * order)
                val drop = 1.1f * h * fall * fall
                set(o, x + drop * tan(p.wind), y + drop, 1f, 1 - smooth(0.35f, 0.9f, fall), 1 - smooth(0f, 0.2f, tt),
                    min(0.15f * h, 0.132f * h * fall))
            }
            "Onda" -> { // un anillo empuja hacia fuera
                val diag = hypot(w, h); val r = t / k / 0.75f * 0.95f * diag
                val d = hypot(dx, dy).let { if (it == 0f) 1f else it }
                val hit = smooth(d, d + 0.12f * diag, r)
                set(o, x + dx / d * 0.12f * h * hit, y + dy / d * 0.12f * h * hit, 1f, 1 - hit, 1 - hit, 0f)
            }
            else -> { // Polvo, Reconstelar y Corte: fundido
                val fade = (if (p.style == CUT) 0.3f else 0.35f) * k
                set(o, x, y, 1f, 1 - smooth(0f, fade, t), 1 - smooth(0f, fade * 0.7f, t), 0f)
            }
        }
    }

    /** Estrella de la estrofa que llega (x, y = su sitio final; sx, sy = estrella de origen para Reconstelar). */
    fun inState(p: P, t: Float, x: Float, y: Float, i: Int, w: Float, h: Float, sx: Float, sy: Float, hasSrc: Boolean, o: FloatArray) {
        val k = p.k
        val tm = TIMES.getValue(p.style)
        val delay = tm[1] + if (p.style == RAIN) 0.04f * min(i, 20) else 0f
        val v = clamp((t / k - delay) / tm[2])
        val cx = w * (0.5f + p.cx); val cy = h * (0.5f + p.cy)
        val dx = x - cx; val dy = y - cy
        when (p.style) {
            "Viaje" -> { // llega desde lejos
                val e = 1 - (1 - v) * (1 - v) * (1 - v); val s = 1 / (1 + 2.33f * (1 - e)); val a = -p.rot * (1 - e)
                set(o, cx + (dx * cos(a) - dy * sin(a)) * s, cy + (dx * sin(a) + dy * cos(a)) * s, s,
                    smooth(0f, 0.35f, v), smooth(0.35f, 0.9f, v), 0f)
            }
            "Remolino" -> { // se despliega en espiral con un pequeño rebote
                val e = (1 - (1 - v) * (1 - v) * (1 - v)) * (1 + 0.08f * sin(PI.toFloat() * v))
                val a = -p.dir * 0.6f * p.turns * 2 * PI.toFloat() * (1 - v) * (1 - v)
                set(o, cx + (dx * cos(a) - dy * sin(a)) * e, cy + (dx * sin(a) + dy * cos(a)) * e, 0.4f + 0.6f * clamp(e),
                    smooth(0f, 0.3f, v), smooth(0.55f, 0.95f, v), 0f)
            }
            "Explosión" -> { // se reagrupa desde posiciones dispersas
                val ang = hash(i, p.salt + 1) * 2 * PI.toFloat(); val e = 1 - (1 - v) * (1 - v) * (1 - v) * (1 - v)
                set(o, x + cos(ang) * 0.4f * h * (1 - e), y + sin(ang) * 0.4f * h * (1 - e), 1f,
                    smooth(0f, 0.3f, v), smooth(0.5f, 0.95f, v), 0f)
            }
            RAIN -> { // cae desde arriba hasta su sitio
                val e = 1 - (1 - v) * (1 - v); val top = -0.1f * h; val py = top + (y - top) * e
                set(o, x - (y - py) * tan(p.wind), py, 1f, smooth(0f, 0.15f, v), smooth(0.85f, 1f, v), (1 - e) * 0.1f * h)
            }
            "Polvo" -> set(o, x, y, 1f, smooth(0.35f, 0.8f, v), smooth(0.5f, 0.9f, v), 0f)
            "Reconstelar" -> { // cada estrella viaja desde una de la estrofa anterior, en curva
                val ox = if (hasSrc) sx else cx; val oy = if (hasSrc) sy else cy
                val e = v * v * (3 - 2 * v); val ex = x - ox; val ey = y - oy
                val d = hypot(ex, ey).let { if (it == 0f) 1f else it }
                val bend = p.curve * h * sin(PI.toFloat() * e)
                set(o, ox + ex * e - ey / d * bend, oy + ey * e + ex / d * bend, 1f,
                    if (hasSrc) 1f else smooth(0f, 0.3f, v), smooth(0.45f, 0.8f, v), 0f)
            }
            "Onda" -> { // aparecen cuando el anillo pasa por su radio
                val diag = hypot(w, h); val r = v * 1.1f * diag; val d = hypot(dx, dy)
                val g = smooth(d - 0.05f * diag, d + 0.08f * diag, r)
                set(o, x, y, if (g < 1) 0.5f + 0.5f * clamp(outBack(g)) else 1f, g, smooth(d + 0.04f * diag, d + 0.2f * diag, r), 0f)
            }
            else -> set(o, x, y, 1f, smooth(0.1f, 0.4f, t / k), smooth(0.15f, 0.45f, t / k), 0f) // corte
        }
    }
}
