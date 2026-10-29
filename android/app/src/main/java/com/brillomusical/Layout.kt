package com.brillomusical

import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin
import kotlin.random.Random

/** Constelación: estrofas y colocación sin solapes (funciones puras; la vista solo dibuja). */
object Layout {
    data class Word(val line: Int, val timeMs: Long, val text: String)

    /** stanza: índice de estrofa; activeWord: índice en words (-1 = aún no suena ninguna); activeLine: índice en lines. */
    data class Frame(val stanza: Int, val words: List<Word>, val activeWord: Int, val activeLine: Int)

    const val MAX_WORDS = 8
    private const val MAX_LINES = 4
    private const val GAP = 5000L // silencio que corta la estrofa

    /** Corte en línea vacía, hueco largo o más de 4 líneas; luego trozos de como mucho maxWords palabras. */
    fun stanzas(lines: List<Lyrics.Line>, maxWords: Int = MAX_WORDS): List<List<Word>> {
        val groups = mutableListOf<MutableList<Int>>()
        var cur = mutableListOf<Int>()
        for ((i, l) in lines.withIndex()) {
            if (l.words.isEmpty()) { if (cur.isNotEmpty()) groups += cur; cur = mutableListOf(); continue }
            if (cur.isNotEmpty()) {
                val p = lines[cur.last()]
                // la línea anterior ya acabó hace rato, o ya van 4 líneas
                if (l.timeMs - p.timeMs > GAP + 400L * p.words.size || cur.size >= MAX_LINES) { groups += cur; cur = mutableListOf() }
            }
            cur += i
        }
        if (cur.isNotEmpty()) groups += cur
        val out = mutableListOf<List<Word>>()
        for (g in groups) {
            var chunk = mutableListOf<Word>()
            for (i in g) {
                val ws = lines[i].words.map { Word(i, it.first, it.second) }
                if (chunk.isNotEmpty() && chunk.size + ws.size > maxWords) { out += chunk; chunk = mutableListOf() }
                if (ws.size <= maxWords) { chunk += ws; continue }
                val k = (ws.size + maxWords - 1) / maxWords // línea larga: partes iguales
                for (j in 0 until k) out += ws.subList(j * ws.size / k, (j + 1) * ws.size / k)
            }
            if (chunk.isNotEmpty()) out += chunk
        }
        return out
    }

    /** Qué se ve en posMs: la estrofa de la última palabra cantada (antes de empezar, la primera). null sin letra. */
    fun frame(lines: List<Lyrics.Line>, stanzas: List<List<Word>>, posMs: Long): Frame? {
        if (stanzas.isEmpty()) return null
        var s = 0; var w = -1
        for ((si, st) in stanzas.withIndex()) {
            if (st[0].timeMs > posMs) break
            s = si; w = st.indexOfLast { it.timeMs <= posMs }
        }
        return Frame(s, stanzas[s], w, Lyrics.lineIndex(lines, posMs))
    }

    /**
     * n puntos (x, y) en píxeles, cada uno cerca del anterior y a minDist o más de los demás.
     * avoidBottom: alto reservado abajo (carátula) donde no cae ninguno. Misma semilla = mismo resultado.
     */
    fun place(n: Int, seed: Long, width: Float, height: Float, minDist: Float, avoidBottom: Float = 0f): List<Pair<Float, Float>> {
        val rnd = Random(seed)
        val m = 0.08f * minOf(width, height)
        val x0 = m; val x1 = width - m; val y0 = m; val y1 = maxOf(y0 + 1, height - m - avoidBottom)
        val pts = mutableListOf<Pair<Float, Float>>()
        fun inside(p: Pair<Float, Float>) = p.first in x0..x1 && p.second in y0..y1
        fun free(p: Pair<Float, Float>) = pts.minOfOrNull { hypot(p.first - it.first, p.second - it.second) } ?: Float.MAX_VALUE
        fun anywhere() = x0 + rnd.nextFloat() * (x1 - x0) to y0 + rnd.nextFloat() * (y1 - y0)
        repeat(n) {
            var chosen: Pair<Float, Float>? = null
            if (pts.isEmpty()) chosen = anywhere()
            else repeat(30) {
                if (chosen != null) return@repeat
                val a = rnd.nextDouble(0.0, 2 * Math.PI); val r = minDist * (1f + 1.5f * rnd.nextFloat())
                val p = pts.last().first + r * cos(a).toFloat() to pts.last().second + r * sin(a).toFloat()
                if (inside(p) && free(p) >= minDist) chosen = p
            }
            // sin sitio cerca: el punto más libre de unos cuantos al azar
            pts += chosen ?: (0 until 60).map { anywhere() }.maxBy { free(it) }
        }
        return pts
    }
}
