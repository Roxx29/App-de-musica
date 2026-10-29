package com.brillomusical

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.graphics.RadialGradient
import android.graphics.RenderEffect
import android.graphics.Shader
import android.os.Build
import android.os.SystemClock
import android.view.View
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/** Fondo de la letra: portada difuminada y oscurecida con viñeta, en varios modos (port de backdrop.py). */
class Backdrop(ctx: Context) : View(ctx) {
    private class Tex(val b: Bitmap, val soft: Bitmap, val dim: Float)

    var onWant: () -> Unit = {} // pide más fotogramas a la Activity
    private val born = SystemClock.uptimeMillis()
    private var src: Bitmap? = null // NowPlaying.art de la que sale la textura actual
    private var tex: Tex? = null
    private var prev: Tex? = null
    private var artAt = -10_000L
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG)
    private val vignette = Paint()
    // API 31+: difumina la vista; antes, textura de 32 px ampliada con filtro
    private val side = if (Build.VERSION.SDK_INT >= 31) 96 else 32

    init {
        if (Build.VERSION.SDK_INT >= 31) {
            val r = 24 * resources.displayMetrics.density
            setRenderEffect(RenderEffect.createBlurEffect(r, r, Shader.TileMode.CLAMP))
        }
    }

    private fun mode(): String = Prefs.backdrop.let {
        // shortcut: Automático = Ken Burns sonando / Difuminado en pausa; elegir por ambiente si llega a haber análisis real
        if (it == "Automático") (if (NowPlaying.playing) "Ken Burns" else "Difuminado") else it
    }

    /** ¿Necesita fotogramas? (modo animado sonando o fundido entre portadas). */
    fun wantsFrame() = (NowPlaying.playing && mode() in ANIMATED) || SystemClock.uptimeMillis() - artAt < FADE

    override fun onSizeChanged(w: Int, h: Int, ow: Int, oh: Int) {
        vignette.shader = RadialGradient(w / 2f, h / 2f, max(1f, hypot(w.toFloat(), h.toFloat()) / 2),
            intArrayOf(0, 0, 0xAA000000.toInt()), floatArrayOf(0f, 0.5f, 1f), Shader.TileMode.CLAMP)
    }

    override fun onDraw(c: Canvas) {
        c.drawColor(Color.BLACK)
        syncArt()
        val m = mode()
        if (m != "Sin portada") {
            val now = SystemClock.uptimeMillis()
            val f = ((now - artAt) / FADE.toFloat()).coerceIn(0f, 1f)
            val e = f * f * (3 - 2 * f)
            val t = (now - born) / 1000f
            val energy = if (m == "Al ritmo") Beat.energy() else 0f
            // la nueva se funde encima; si la nueva es "sin portada", la vieja se apaga
            prev?.let { drawTex(c, it, m, t, energy, if (tex != null) 1f else 1 - e) }
            tex?.let { drawTex(c, it, m, t, energy, if (prev != null) e else 1f) }
            if (f >= 1) prev = null
        }
        c.drawRect(0f, 0f, width.toFloat(), height.toFloat(), vignette)
        if (wantsFrame()) onWant()
    }

    private fun syncArt() {
        val a = NowPlaying.art
        if (a === src) return
        src = a
        val now = SystemClock.uptimeMillis()
        if (now - artAt >= FADE) prev = tex // durante otro fundido se conserva el origen: sin salto
        tex = a?.let { make(it) }
        artAt = now
    }

    /** Recorte cuadrado pequeño + versión con borde circular suave para las manchas del modo Ambiente. */
    private fun make(a: Bitmap): Tex {
        val sw = if (a.config == Bitmap.Config.HARDWARE) a.copy(Bitmap.Config.ARGB_8888, false) else a
        val s = min(sw.width, sw.height)
        val b = Bitmap.createScaledBitmap(Bitmap.createBitmap(sw, (sw.width - s) / 2, (sw.height - s) / 2, s, s), side, side, true)
        val px = Bitmap.createScaledBitmap(b, 1, 1, true).getPixel(0, 0)
        val lum = (0.299f * Color.red(px) + 0.587f * Color.green(px) + 0.114f * Color.blue(px)) / 255f
        val soft = b.copy(Bitmap.Config.ARGB_8888, true)
        Canvas(soft).drawRect(0f, 0f, side.toFloat(), side.toFloat(), Paint().apply {
            xfermode = PorterDuffXfermode(PorterDuff.Mode.DST_IN)
            shader = RadialGradient(side / 2f, side / 2f, side / 2f, intArrayOf(Color.BLACK, 0xA0000000.toInt(), 0),
                floatArrayOf(0f, 0.6f, 1f), Shader.TileMode.CLAMP)
        })
        // más oscuro cuanto más clara es la portada, para que la letra se lea
        return Tex(b, soft, (0.35f + 0.25f * lum).coerceIn(0.35f, 0.5f))
    }

    private fun drawTex(c: Canvas, x: Tex, m: String, t: Float, energy: Float, alpha: Float) {
        val w = width.toFloat(); val h = height.toFloat(); val n = side.toFloat()
        var zoom = 1f; var cx = 0.5f; var cy = 0.5f
        when (m) {
            "Ken Burns" -> { // lento y continuo, sin saltos al reiniciar
                zoom = 1.175f + 0.075f * sin(TAU * t / 40); cx = 0.5f + 0.5f * sin(TAU * t / 50); cy = 0.5f + 0.5f * sin(TAU * t / 70 + 1)
            }
            "Ambiente en movimiento" -> zoom = 1.3f
            "Al ritmo" -> zoom = 1.02f + 0.05f * energy
        }
        // parte de la textura que cubre la vista (en Float: sin saltos de píxel en 32 px)
        val aspect = w / h
        val sw = if (aspect >= 1) 1 / zoom else aspect / zoom
        val sh = if (aspect >= 1) 1 / (aspect * zoom) else 1 / zoom
        val k = w / (sw * n)
        paint.alpha = (alpha * 255).toInt()
        c.save()
        c.translate(-(1 - sw) * cx * n * k, -(1 - sh) * cy * n * k)
        c.scale(k, k)
        c.drawBitmap(x.b, 0f, 0f, paint)
        c.restore()
        if (m == "Ambiente en movimiento") for (j in 0..1) { // dos manchas que orbitan y giran
            val size = 1.1f * max(w, h)
            c.save()
            c.translate((0.35f + 0.3f * j + 0.28f * sin(TAU * t / (45 + 10 * j) + 2 * j)) * w,
                (0.5f + 0.25f * sin(TAU * t / (55 - 8 * j) + 1 + j)) * h)
            c.rotate(360 * t / (60 + 20 * j) * (if (j == 0) 1 else -1))
            c.scale(size / n, size / n)
            c.translate(-n / 2, -n / 2)
            paint.alpha = (alpha * 0.55f * 255).toInt()
            c.drawBitmap(x.soft, 0f, 0f, paint)
            c.restore()
        }
        val dim = if (m == "Al ritmo") x.dim - 0.12f * energy else x.dim
        c.drawColor(Color.argb((alpha * dim.coerceIn(0f, 1f) * 255).toInt(), 0, 0, 0))
    }

    private companion object {
        const val FADE = 1500L // fundido entre portadas
        val ANIMATED = setOf("Ambiente en movimiento", "Ken Burns", "Al ritmo")
        const val TAU = 6.2831855f
    }
}
