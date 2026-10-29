package com.brillomusical

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.*
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import android.provider.Settings
import android.view.Choreographer
import android.view.RoundedCorner
import android.view.View
import android.view.WindowInsets
import android.view.WindowManager
import kotlin.math.max
import kotlin.math.min

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
        val v = GlowView(ctx)
        try { wm.addView(v, p); view = v } catch (e: Exception) {} // permiso retirado o servicio parado
    }

    fun hide() { view?.let { try { wm.removeView(it) } catch (e: Exception) {} }; view = null }

    /**
     * Una máscara ALPHA_8 con el halo (esquinas redondeadas y notch incluidos) se calcula al cambiar
     * tamaño/insets; cada fotograma solo se rellena una cinta de 128 colores que la tiñe por las 4 franjas.
     */
    private class GlowView(ctx: Context) : View(ctx), Choreographer.FrameCallback {
        private val fx = Effects()
        private val px = IntArray(128)
        private val ribbon = Bitmap.createBitmap(px.size, 1, Bitmap.Config.ARGB_8888)
        private val shaders = Array(4) { BitmapShader(ribbon, Shader.TileMode.REPEAT, Shader.TileMode.REPEAT) }
        private val bands = Array(4) { Rect() } // arriba, derecha, abajo, izquierda
        private var mask: Bitmap? = null
        private var built: List<Any?>? = null // tamaño y cutout de la máscara actual
        private val paint = Paint(Paint.FILTER_BITMAP_FLAG)
        private val core = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.5f * resources.displayMetrics.density }
        private val outline = Path()
        private val thick = 16f * resources.displayMetrics.density
        private var running = false
        private var odd = false
        private var screenOn = ctx.getSystemService(PowerManager::class.java).isInteractive
        private val onChange = { fx.song(); refresh() }
        private val onPrefs = { refresh() }
        private val screen = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) { screenOn = i.action == Intent.ACTION_SCREEN_ON; refresh() }
        }

        override fun onAttachedToWindow() {
            super.onAttachedToWindow()
            NowPlaying.listen(onChange); Prefs.listen(onPrefs)
            context.registerReceiver(screen, IntentFilter(Intent.ACTION_SCREEN_OFF).apply { addAction(Intent.ACTION_SCREEN_ON) })
            refresh()
        }

        override fun onDetachedFromWindow() {
            super.onDetachedFromWindow()
            NowPlaying.unlisten(onChange); Prefs.unlisten(onPrefs)
            try { context.unregisterReceiver(screen) } catch (e: Exception) {}
            Choreographer.getInstance().removeFrameCallback(this); running = false
        }

        override fun onSizeChanged(w: Int, h: Int, ow: Int, oh: Int) { post { build() } } // tras los insets nuevos

        override fun onApplyWindowInsets(insets: WindowInsets): WindowInsets {
            // app delante a pantalla completa = barra de estado oculta
            if (Build.VERSION.SDK_INT >= 30) fx.hidden = insets.getInsetsIgnoringVisibility(WindowInsets.Type.statusBars()).top > 0 &&
                !insets.isVisible(WindowInsets.Type.statusBars()) // sin barra de estado (p. ej. horizontal) no cuenta
            post { build(); refresh() } // rootWindowInsets ya actualizado
            return insets
        }

        private fun refresh() { step(); tick() }

        private fun step() {
            if (width == 0) return
            fx.frame(SystemClock.uptimeMillis(), width, height, px)
            ribbon.setPixels(px, 0, px.size, 0, 0, px.size, 1)
            invalidate()
        }

        // Fotogramas solo con pantalla encendida y mientras haya animación (sonando o terminando un fundido).
        private fun tick() {
            if (!running && screenOn && isAttachedToWindow && fx.animating(SystemClock.uptimeMillis())) {
                running = true; Choreographer.getInstance().postFrameCallback(this)
            }
        }

        override fun doFrame(t: Long) {
            running = false
            odd = !odd
            if (!fx.slow() || odd) step() // efectos lentos a 30 fps
            tick()
        }

        override fun onDraw(c: Canvas) {
            val m = mask ?: return
            if (fx.level <= 0.01f) return
            paint.alpha = (255 * fx.level).toInt()
            // máscara ALPHA_8: el shader de la cinta pone el color
            for (i in 0..3) { paint.shader = shaders[i]; c.drawBitmap(m, bands[i], bands[i], paint) }
            core.color = fx.coreColor
            core.alpha = (255 * fx.coreAlpha * fx.level).toInt()
            c.drawPath(outline, core)
        }

        /** Recalcula máscara, contorno, franjas y shaders (tamaño, rotación, insets). */
        private fun build() {
            val w = width; val h = height
            if (w == 0 || h == 0) return
            val ins = rootWindowInsets
            val key = listOf(w, h, if (Build.VERSION.SDK_INT >= 28) ins?.displayCutout else null)
            if (key == built) return // mismo tamaño y cutout: la máscara vale
            built = key
            val r = FloatArray(8)
            if (Build.VERSION.SDK_INT >= 31 && ins != null)
                intArrayOf(RoundedCorner.POSITION_TOP_LEFT, RoundedCorner.POSITION_TOP_RIGHT,
                    RoundedCorner.POSITION_BOTTOM_RIGHT, RoundedCorner.POSITION_BOTTOM_LEFT).forEachIndexed { i, pos ->
                    val v = ins.getRoundedCorner(pos)?.radius?.toFloat() ?: 0f
                    r[2 * i] = v; r[2 * i + 1] = v
                }
            outline.reset()
            outline.addRoundRect(0f, 0f, w.toFloat(), h.toFloat(), r, Path.Direction.CW)
            val screenPath = Path(outline)
            var deep = 0
            if (Build.VERSION.SDK_INT >= 28) ins?.displayCutout?.let { cut ->
                val cp = if (Build.VERSION.SDK_INT >= 31) cut.cutoutPath else null
                if (cp != null) outline.addPath(cp) else cut.boundingRects.forEach { outline.addRect(RectF(it), Path.Direction.CW) }
                cut.boundingRects.forEach { deep = max(deep, minOf(it.bottom, h - it.top, it.right, w - it.left)) }
            }

            // halo: trazo del contorno difuminado (núcleo de color pegado al borde + cola suave hasta ~16 dp)
            val m = Bitmap.createBitmap(w, h, Bitmap.Config.ALPHA_8)
            val c = Canvas(m)
            c.clipPath(screenPath)
            val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
            p.strokeWidth = thick * 0.6f; p.maskFilter = BlurMaskFilter(thick * 0.6f, BlurMaskFilter.Blur.NORMAL); c.drawPath(outline, p)
            p.strokeWidth = thick * 0.3f; p.maskFilter = BlurMaskFilter(thick * 0.2f, BlurMaskFilter.Blur.NORMAL); c.drawPath(outline, p)
            mask = m // sin recycle(): el RenderThread puede seguir usando la anterior

            val b = max(max(2 * thick, r.max() + thick), deep + thick).toInt().coerceAtMost(min(w, h) / 2)
            bands[0].set(0, 0, w, b); bands[1].set(w - b, b, w, h - b)
            bands[2].set(0, h - b, w, h); bands[3].set(0, b, b, h - b)

            // cinta (x = u·128) → pantalla, por franja: arriba →, derecha ↓, abajo ←, izquierda ↑
            val s = 2f * (w + h) / px.size
            val mx = Matrix()
            val vals = arrayOf(
                floatArrayOf(s, 0f, 0f, 0f, 1f, 0f),
                floatArrayOf(0f, 1f, 0f, s, 0f, -w.toFloat()),
                floatArrayOf(-s, 0f, 2f * w + h, 0f, 1f, 0f),
                floatArrayOf(0f, 1f, 0f, -s, 0f, 2f * (w + h)))
            for (i in 0..3) { mx.setValues(vals[i] + floatArrayOf(0f, 0f, 1f)); shaders[i].setLocalMatrix(mx) }
            invalidate()
        }
    }
}
