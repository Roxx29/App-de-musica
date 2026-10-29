package com.brillomusical

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.Choreographer
import android.view.GestureDetector
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.widget.FrameLayout
import android.widget.ScrollView
import android.widget.TextView
import java.util.Locale
import kotlin.math.abs

/** Pantalla de letra a pantalla completa: fondo + constelación + carátula; gestos y panel de ajustes rápidos. */
class LyricsActivity : Activity() {
    private lateinit var bd: Backdrop
    private lateinit var stars: ConstellationView
    private lateinit var panel: ScrollView
    private lateinit var toast: TextView
    private var started = false
    private var posted = false
    private var bdAt = 0L

    // un solo bucle de fotogramas, vivo solo en primer plano y mientras alguna vista lo pida
    private val frame = Choreographer.FrameCallback { t ->
        posted = false
        stars.invalidate()
        if (bd.wantsFrame() && t - bdAt >= 30_000_000L) { bdAt = t; bd.invalidate() } // fondo a ~30 fps
        if (bd.wantsFrame()) want()
    }
    private val onChange: () -> Unit = { stars.invalidate(); bd.invalidate(); want() }

    private fun want() {
        if (started && !posted) { posted = true; Choreographer.getInstance().postFrameCallback(frame) }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate(s: Bundle?) {
        super.onCreate(s)
        Prefs.init(this)
        window.decorView.setBackgroundColor(Ui.BG)
        bd = Backdrop(this).apply { onWant = ::want }
        stars = ConstellationView(this).apply { onWant = ::want }
        toast = text("", Ui.Type.BODY, Ui.TEXT).apply {
            background = Ui.round(0x99000000.toInt(), dp(16).toFloat())
            setPadding(dp(16), dp(8), dp(16), dp(8))
            alpha = 0f
        }
        panel = ScrollView(this).apply { // con scroll: en horizontal puede no caber
            isVerticalScrollBarEnabled = false
            visibility = View.GONE
        }
        val detector = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: MotionEvent) = true
            override fun onSingleTapUp(e: MotionEvent): Boolean { togglePanel(); return true }
            override fun onFling(e1: MotionEvent?, e2: MotionEvent, vx: Float, vy: Float): Boolean {
                if (e1 == null) return false
                val dx = e2.x - e1.x
                if (abs(dx) < dp(48) || abs(dx) < 2 * abs(e2.y - e1.y)) return false
                shift(if (dx > 0) 100 else -100) // derecha adelanta la letra, izquierda la retrasa
                return true
            }
        })
        val root = FrameLayout(this).apply {
            val all = ViewGroup.LayoutParams.MATCH_PARENT
            addView(bd, all, all)
            addView(stars, all, all)
            addView(toast, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = dp(32) })
            addView(panel, FrameLayout.LayoutParams(all, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM).apply {
                setMargins(dp(12), dp(12), dp(12), dp(12))
            })
            setOnTouchListener { _, e -> detector.onTouchEvent(e) }
        }
        setContentView(root)
    }

    /** Ajustes rápidos; se rehace en onStart para reflejar lo cambiado en Ajustes. */
    private fun buildPanel() {
        panel.removeAllViews()
        panel.addView(card().apply {
            isClickable = true // los toques del panel no llegan a la pantalla de detrás
            fun row(name: String, options: List<String>, value: String, set: (String) -> Unit) {
                addView(text(name, Ui.Type.LABEL, Ui.TEXT3)); addView(segmented(options, value, set))
            }
            row("Fondo", Prefs.BACKDROPS, Prefs.backdrop) { Prefs.backdrop = it }
            row("Transición", Prefs.TRANSITIONS, Prefs.transition) { Prefs.transition = it }
            row("Carátula", Prefs.COVERS, Prefs.cover) { Prefs.cover = it }
            addView(button("Ajustes", primary = false) { startActivity(Intent(this@LyricsActivity, SettingsActivity::class.java)) })
        })
    }

    private fun togglePanel() {
        val show = panel.visibility != View.VISIBLE
        panel.animate().cancel()
        if (show) { panel.visibility = View.VISIBLE; panel.enter() }
        else panel.animate().alpha(0f).setDuration(Ui.FAST).withEndAction { panel.visibility = View.GONE }.start()
    }

    /** Desfase manual de la letra de esta canción, con aviso de 1 s. */
    private fun shift(ms: Long) {
        if (NowPlaying.title.isEmpty()) return
        val v = Prefs.addOffset(NowPlaying.key, ms)
        toast.text = String.format(Locale.forLanguageTag("es"), "%+.1f s", v / 1000f)
        toast.animate().cancel()
        toast.alpha = 1f
        toast.animate().alpha(0f).setStartDelay(1000).setDuration(Ui.FAST).start()
        onChange()
    }

    @Suppress("DEPRECATION")
    private fun immersive() {
        if (Build.VERSION.SDK_INT >= 30) {
            window.setDecorFitsSystemWindows(false)
            window.insetsController?.apply {
                hide(WindowInsets.Type.systemBars())
                systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_FULLSCREEN or
                View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) immersive() // las barras vuelven a esconderse tras asomarse
    }

    override fun onStart() {
        super.onStart()
        started = true
        immersive()
        buildPanel()
        NowPlaying.lyricsOpen = true
        NowPlaying.listen(onChange); Prefs.listen(onChange)
        NowPlaying.changed() // avisa al borde (y repinta esta pantalla)
    }

    override fun onStop() {
        super.onStop()
        started = false; posted = false
        Choreographer.getInstance().removeFrameCallback(frame)
        NowPlaying.unlisten(onChange); Prefs.unlisten(onChange)
        NowPlaying.lyricsOpen = false; NowPlaying.changed() // el borde vuelve a mirar si hay pantalla completa
    }
}
