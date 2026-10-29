package com.brillomusical

import android.content.Context
import android.graphics.*
import android.os.Build
import android.provider.Settings
import android.view.Choreographer
import android.view.View
import android.view.WindowManager
import kotlin.math.sin

/** Brillo en los bordes sobre cualquier app. No recibe toques. */
class GlowOverlay(private val ctx: Context) {
    private val wm = ctx.getSystemService(WindowManager::class.java)
    private var view: GlowView? = null

    fun show() {
        if (view != null || !Settings.canDrawOverlays(ctx)) return
        val p = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        p.alpha = 0.8f // Android 12+ bloquea los toques bajo superposiciones más opacas
        if (Build.VERSION.SDK_INT >= 28)
            p.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        view = GlowView(ctx).also { wm.addView(it, p) }
    }

    fun hide() { view?.let { wm.removeView(it) }; view = null }

    private class GlowView(ctx: Context) : View(ctx), Choreographer.FrameCallback {
        private val paint = Paint()
        private val width = 28f * resources.displayMetrics.density
        private var running = false
        private val onChange = { invalidate(); tick() }

        override fun onAttachedToWindow() { super.onAttachedToWindow(); NowPlaying.listen(onChange); tick() }
        override fun onDetachedFromWindow() {
            super.onDetachedFromWindow(); NowPlaying.unlisten(onChange)
            Choreographer.getInstance().removeFrameCallback(this); running = false
        }

        // Solo anima mientras suena y la pantalla está encendida (ahorro de batería).
        private fun tick() {
            if (!running && NowPlaying.playing && isShown) { running = true; Choreographer.getInstance().postFrameCallback(this) }
        }

        override fun doFrame(t: Long) {
            running = false; invalidate(); tick()
        }

        override fun onDraw(c: Canvas) {
            if (NowPlaying.title.isEmpty()) return
            val breathe = if (NowPlaying.playing) 0.75f + 0.25f * sin(System.nanoTime() / 1e9 * 2.4).toFloat() else 0.5f
            val col = NowPlaying.color
            val solid = Color.argb((255 * breathe).toInt(), Color.red(col), Color.green(col), Color.blue(col))
            val w = this.width; val W = width(); val H = height()
            edge(c, 0f, 0f, 0f, w, solid, RectF(0f, 0f, W, w))
            edge(c, 0f, H, 0f, H - w, solid, RectF(0f, H - w, W, H))
            edge(c, 0f, 0f, w, 0f, solid, RectF(0f, 0f, w, H))
            edge(c, W, 0f, W - w, 0f, solid, RectF(W - w, 0f, W, H))
        }

        private fun width() = getWidth().toFloat()
        private fun height() = getHeight().toFloat()

        private fun edge(c: Canvas, x0: Float, y0: Float, x1: Float, y1: Float, col: Int, r: RectF) {
            paint.shader = LinearGradient(x0, y0, x1, y1, col, Color.TRANSPARENT, Shader.TileMode.CLAMP)
            c.drawRect(r, paint)
        }
    }
}
