package com.brillomusical

import android.app.Activity
import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.os.Build
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.view.animation.DecelerateInterpolator
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import kotlin.math.abs

/** Estilo compartido: colores, tipos, tarjetas, botones y filas segmentadas. */
object Ui {
    const val BG = 0xFF0B0B0F.toInt()
    const val SURFACE = 0xFF16161D.toInt()
    const val TEXT = 0xEBFFFFFF.toInt()   // 92 %
    const val TEXT2 = 0x99FFFFFF.toInt()  // 60 %
    const val TEXT3 = 0x61FFFFFF.toInt()  // 38 %
    const val FAST = 200L
    const val SLOW = 400L

    /** Tamaño en sp y peso. LABEL va en mayúsculas con +0.08em. */
    enum class Type(val sp: Float, val weight: Int) { TITLE(32f, 600), HEAD(20f, 500), BODY(15f, 400), LABEL(12f, 500) }

    /** Acento a partir de la portada: saturación 0.55–0.75 y luminosidad ≥0.55 para leerse sobre BG. */
    fun accent(c: Int = NowPlaying.color): Int {
        val r = Color.red(c) / 255f; val g = Color.green(c) / 255f; val b = Color.blue(c) / 255f
        val max = maxOf(r, g, b); val min = minOf(r, g, b); val d = max - min
        var l = (max + min) / 2
        var h = when {
            d < 0.04f -> 225f // portada gris: azul por defecto
            max == r -> 60f * (((g - b) / d) % 6)
            max == g -> 60f * ((b - r) / d + 2)
            else -> 60f * ((r - g) / d + 4)
        }
        if (h < 0) h += 360f
        val s = (if (d == 0f) 0f else d / (1 - abs(2 * l - 1))).coerceIn(0.55f, 0.75f)
        l = l.coerceIn(0.55f, 0.8f) // tope 0.8: más arriba se vuelve blanco
        val cc = (1 - abs(2 * l - 1)) * s
        val x = cc * (1 - abs((h / 60f) % 2 - 1))
        val m = l - cc / 2
        val (r1, g1, b1) = when ((h / 60).toInt()) {
            0 -> Triple(cc, x, 0f); 1 -> Triple(x, cc, 0f); 2 -> Triple(0f, cc, x)
            3 -> Triple(0f, x, cc); 4 -> Triple(x, 0f, cc); else -> Triple(cc, 0f, x)
        }
        return Color.rgb(((r1 + m) * 255).toInt(), ((g1 + m) * 255).toInt(), ((b1 + m) * 255).toInt())
    }

    fun font(weight: Int): Typeface =
        if (Build.VERSION.SDK_INT >= 28) Typeface.create(Typeface.DEFAULT, weight, false)
        else Typeface.create(if (weight >= 500) "sans-serif-medium" else "sans-serif", Typeface.NORMAL)

    fun round(color: Int, radiusPx: Float) = GradientDrawable().apply { setColor(color); cornerRadius = radiusPx }
}

fun Context.dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

fun Context.text(s: CharSequence, type: Ui.Type = Ui.Type.BODY, color: Int = Ui.TEXT) = TextView(this).apply {
    text = if (type == Ui.Type.LABEL) s.toString().uppercase() else s
    setTextSize(TypedValue.COMPLEX_UNIT_SP, type.sp)
    typeface = Ui.font(type.weight)
    setTextColor(color)
    if (type == Ui.Type.LABEL) letterSpacing = 0.08f
    if (type == Ui.Type.TITLE) letterSpacing = -0.01f
    if (type == Ui.Type.BODY) setLineSpacing(0f, 1.35f)
}

/** Tarjeta: superficie #16161D, radio 20dp, relleno 20dp, 8dp entre hijos. */
fun Context.card() = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    background = Ui.round(Ui.SURFACE, dp(20).toFloat())
    setPadding(dp(20), dp(20), dp(20), dp(20))
    showDividers = LinearLayout.SHOW_DIVIDER_MIDDLE
    dividerDrawable = GradientDrawable().apply { setSize(0, dp(8)) }
}

/** Botón píldora de 52dp. Principal = acento con texto oscuro; secundario = superficie. */
fun Context.button(label: String, primary: Boolean = true, onClick: () -> Unit) = text(label, Ui.Type.HEAD, if (primary) Ui.BG else Ui.TEXT).apply {
    setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
    gravity = Gravity.CENTER
    minHeight = dp(52)
    setPadding(dp(24), 0, dp(24), 0)
    val bg = Ui.round(if (primary) Ui.accent() else Ui.SURFACE, dp(26).toFloat())
    background = RippleDrawable(ColorStateList.valueOf(0x33FFFFFF), bg, null)
    isClickable = true
    setOnClickListener { onClick() }
}

/** Fila segmentada con scroll horizontal; la opción elegida se rellena con el acento. */
fun Context.segmented(options: List<String>, selected: String, onPick: (String) -> Unit): View {
    val row = LinearLayout(this).apply { setPadding(dp(4), dp(4), dp(4), dp(4)); background = Ui.round(0x0FFFFFFF, dp(24).toFloat()) }
    fun paint(sel: String) {
        for (i in 0 until row.childCount) (row.getChildAt(i) as TextView).apply {
            val on = tag == sel
            setTextColor(if (on) Ui.BG else Ui.TEXT2)
            background = if (on) Ui.round(Ui.accent(), dp(20).toFloat()) else null
            isSelected = on
        }
    }
    options.forEach { o ->
        row.addView(text(o, Ui.Type.BODY).apply {
            tag = o
            typeface = Ui.font(500)
            gravity = Gravity.CENTER
            minHeight = dp(40)
            setPadding(dp(16), 0, dp(16), 0)
            setOnClickListener { paint(o); onPick(o) }
        })
    }
    paint(selected)
    return HorizontalScrollView(this).apply {
        isHorizontalScrollBarEnabled = false
        overScrollMode = View.OVER_SCROLL_NEVER
        addView(row)
        // que la opción elegida quede a la vista
        post { row.findViewWithTag<View>(selected)?.let { smoothScrollTo(it.left - dp(20), 0) } }
    }
}

/** Pone fondo #0B0B0F, barras oscuras y una columna con márgenes de 20dp; devuelve la columna. */
fun Activity.screen(scroll: Boolean = true): LinearLayout {
    window.statusBarColor = Ui.BG
    window.navigationBarColor = Ui.BG
    window.decorView.setBackgroundColor(Ui.BG)
    val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(24), dp(20), dp(32)) }
    // targetSdk 35 dibuja bajo las barras: sus insets se suman a los márgenes
    if (Build.VERSION.SDK_INT >= 30) col.setOnApplyWindowInsetsListener { v, ins ->
        val i = ins.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
        v.setPadding(dp(20) + i.left, dp(24) + i.top, dp(20) + i.right, dp(32) + i.bottom)
        ins
    }
    setContentView(if (scroll) ScrollView(this).apply { isFillViewport = true; addView(col) } else col)
    return col
}

/** Entrada suave: aparece y sube 16dp en 400 ms. */
fun View.enter() {
    alpha = 0f; translationY = context.dp(16).toFloat()
    animate().alpha(1f).translationY(0f).setDuration(Ui.SLOW).setInterpolator(DecelerateInterpolator(2f)).start()
}

/** LayoutParams de ancho completo con margen superior en dp. */
fun Context.full(top: Int = 0) = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(top) }
