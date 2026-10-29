package com.brillomusical

import android.content.Context
import android.graphics.*
import android.view.Choreographer
import android.view.View
import kotlin.random.Random

/** Letra en constelación: cada palabra es una estrella; se encienden y se unen mientras se cantan. */
class ConstellationView(ctx: Context) : View(ctx), Choreographer.FrameCallback {
    private val d = resources.displayMetrics.density
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 22 * d; setShadowLayer(6 * d, 0f, 0f, Color.BLACK) }
    private val star = Paint(Paint.ANTI_ALIAS_FLAG)
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeWidth = 1.5f * d }
    private var shown = -2
    private var points: List<PointF> = emptyList()

    override fun onAttachedToWindow() { super.onAttachedToWindow(); Choreographer.getInstance().postFrameCallback(this) }
    override fun onDetachedFromWindow() { super.onDetachedFromWindow(); Choreographer.getInstance().removeFrameCallback(this) }
    override fun doFrame(t: Long) { invalidate(); Choreographer.getInstance().postFrameCallback(this) }

    override fun onDraw(c: Canvas) {
        val lines = NowPlaying.lines
        val col = NowPlaying.color
        if (lines.isEmpty()) {
            text.color = Color.WHITE; text.textAlign = Paint.Align.CENTER
            val msg = if (NowPlaying.title.isEmpty()) "Pon una canción en YouTube Music" else NowPlaying.title
            c.drawText(msg, width / 2f, height / 2f, text); return
        }
        val pos = NowPlaying.positionMs()
        val i = Lyrics.lineIndex(lines, pos).coerceAtLeast(0)
        val words = lines[i].text.split(' ').filter { it.isNotBlank() }
        if (i != shown) { shown = i; points = place(words.size, i) }
        val end = lines.getOrNull(i + 1)?.timeMs ?: (lines[i].timeMs + 4000)
        // shortcut: tiempo por palabra repartido a partes iguales; usar etiquetas <mm:ss> cuando LRCLIB las traiga
        val frac = ((pos - lines[i].timeMs).toFloat() / (end - lines[i].timeMs).coerceAtLeast(1)).coerceIn(0f, 1f)
        val lit = (frac * words.size).toInt().coerceAtMost(words.size)
        line.color = Color.argb(150, Color.red(col), Color.green(col), Color.blue(col))
        for (k in 1 until lit) c.drawLine(points[k - 1].x, points[k - 1].y, points[k].x, points[k].y, line)
        text.textAlign = Paint.Align.CENTER
        words.forEachIndexed { k, w ->
            val on = k < lit
            star.color = if (on) Color.WHITE else Color.argb(110, 255, 255, 255)
            c.drawCircle(points[k].x, points[k].y, (if (on) 4f else 2.5f) * d, star)
            text.color = if (on) col else Color.argb(140, 255, 255, 255)
            c.drawText(w, points[k].x, points[k].y - 10 * d, text)
        }
    }

    /** Colocación aleatoria con semilla por línea, evitando palabras encimadas. */
    private fun place(n: Int, seed: Int): List<PointF> {
        val r = Random(seed * 7919 + NowPlaying.title.hashCode())
        val out = mutableListOf<PointF>(); val m = 48 * d; val gap = 70 * d
        repeat(n) {
            var p = PointF(); var tries = 0
            do { p = PointF(m + r.nextFloat() * (width - 2 * m), m * 2 + r.nextFloat() * (height - 4 * m)); tries++ }
            while (tries < 40 && out.any { o -> Math.hypot((o.x - p.x).toDouble(), (o.y - p.y).toDouble()) < gap })
            out += p
        }
        return out
    }
}
