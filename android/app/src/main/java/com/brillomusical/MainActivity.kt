package com.brillomusical

import android.app.Activity
import android.content.ComponentName
import android.content.Intent
import android.content.res.ColorStateList
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewOutlineProvider
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.Switch
import android.widget.TextView

/** Bienvenida por pasos (primera vez) e inicio. */
class MainActivity : Activity() {
    private var step = 0 // 0 bienvenida, 1 música, 2 brillo, 3 batería
    private var art: ImageView? = null
    private var nowTitle: TextView? = null
    private var artist: TextView? = null
    private val onNow = { showNow() }

    private val hasMusic get() = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
        ?.contains(ComponentName(this, MusicListener::class.java).flattenToString()) == true
    private val hasOverlay get() = Settings.canDrawOverlays(this)
    private val hasBattery get() = getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)

    override fun onCreate(s: Bundle?) {
        super.onCreate(s)
        Prefs.init(this)
        step = s?.getInt("step") ?: 0
    }

    override fun onSaveInstanceState(out: Bundle) { super.onSaveInstanceState(out); out.putInt("step", step) }

    // El estado de los permisos se comprueba al volver de Ajustes
    override fun onResume() { super.onResume(); if (Prefs.onboarded) home() else onboarding(false) }
    override fun onStart() { super.onStart(); NowPlaying.listen(onNow) }
    override fun onStop() { super.onStop(); NowPlaying.unlisten(onNow) }

    private fun openMusic() = open(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
    private fun openOverlay() = open(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
    private fun openBattery() = open(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
    private fun openAppInfo() = open(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))

    /** Algunos fabricantes no tienen esa pantalla: se abre Info de la app. */
    private fun open(i: Intent) {
        try { startActivity(i) } catch (e: Exception) {
            try { startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName"))) } catch (e: Exception) {}
        }
    }

    // Android 13+ bloquea este permiso en apps instaladas a mano
    private val restricted = if (Build.VERSION.SDK_INT >= 33)
        "¿Aparece «Ajuste restringido»? Abre Info de la app, toca ⋮ y elige «Permitir ajustes restringidos»." else null

    private fun go(next: Int) {
        if (next > 3 || (next == 3 && hasBattery)) { Prefs.onboarded = true; home(); return }
        step = next; onboarding(true)
    }

    private fun onboarding(animate: Boolean) {
        val col = screen(scroll = true)
        // Puntos de progreso de los 3 pasos (la bienvenida no cuenta)
        val dots = LinearLayout(this).apply { gravity = Gravity.CENTER; minimumHeight = dp(24) }
        if (step > 0) for (i in 1..3) dots.addView(View(this).apply {
            background = Ui.round(if (i == step) Ui.accent() else Ui.TEXT3, dp(4).toFloat())
            layoutParams = LinearLayout.LayoutParams(dp(if (i == step) 24 else 8), dp(8)).apply { marginStart = dp(4); marginEnd = dp(4) }
        })
        col.addView(dots)

        val body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_VERTICAL }
        col.addView(body, LinearLayout.LayoutParams(-1, 0, 1f))
        val actions = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(actions)

        fun write(t: String, msg: String, hint: String? = null, ok: String? = null) {
            body.addView(text(t, Ui.Type.TITLE))
            body.addView(text(msg, Ui.Type.BODY, Ui.TEXT2), full(16))
            if (ok != null) body.addView(text(ok, Ui.Type.HEAD, Ui.accent()), full(24))
            else if (hint != null) body.addView(text(hint, Ui.Type.BODY, Ui.TEXT3), full(16))
        }
        fun act(label: String, primary: Boolean = true, f: () -> Unit) = actions.addView(button(label, primary, f), full(if (actions.childCount > 0) 8 else 0))

        when (step) {
            0 -> {
                body.addView(ImageView(this).apply { setImageResource(R.drawable.ic_star) }, LinearLayout.LayoutParams(dp(96), dp(96)).apply { bottomMargin = dp(32) })
                write("BrilloMusical", "Tu música, en la luz de tu pantalla.")
                act("Empezar") { go(1) }
            }
            1 -> {
                write("Ver qué suena", "Leemos el título y la portada de lo que suena en YouTube Music para buscar la letra por título. No guardamos nada fuera de tu teléfono.",
                    "Busca BrilloMusical y actívalo." + (restricted?.let { "\n\n$it" } ?: ""), if (hasMusic) "Listo, ya te escucho." else null)
                if (hasMusic) act("Seguir") { go(2) } else {
                    act("Activar") { openMusic() }
                    if (restricted != null) act("Abrir Info de la app", false) { openAppInfo() }
                    act("Ahora no", false) { go(2) }
                }
            }
            2 -> {
                write("Brillo sobre tus apps", "Dibuja un borde de luz encima de lo que uses. Puedes apagarlo cuando quieras.",
                    null, if (hasOverlay) "Listo, que brille." else null)
                if (hasOverlay) act("Seguir") { go(3) } else { act("Activar") { openOverlay() }; act("Ahora no", false) { go(3) } }
            }
            else -> {
                if (hasBattery) { go(4); return }
                write("Que no se apague", "Algunos teléfonos cierran apps en segundo plano. Quita la optimización para que el brillo no se apague.")
                act("Quitar optimización") { openBattery() }
                act("Ahora no", false) { go(4) }
            }
        }
        if (animate) body.enter()
    }

    private fun home() {
        val col = screen()
        col.addView(text("BrilloMusical", Ui.Type.TITLE))

        // Sonando ahora
        val now = card()
        now.addView(text("Sonando ahora", Ui.Type.LABEL, Ui.TEXT3))
        val row = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        art = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            background = Ui.round(0x14FFFFFF, dp(12).toFloat())
            outlineProvider = ViewOutlineProvider.BACKGROUND
            clipToOutline = true
        }
        row.addView(art, LinearLayout.LayoutParams(dp(64), dp(64)))
        val names = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), 0, 0, 0) }
        nowTitle = text("", Ui.Type.HEAD).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END }
        artist = text("", Ui.Type.BODY, Ui.TEXT2).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END }
        names.addView(nowTitle); names.addView(artist)
        row.addView(names, LinearLayout.LayoutParams(0, -2, 1f))
        now.addView(row)
        col.addView(now, full(24))

        // Interruptor del brillo (fila de 56dp)
        val glow = card().apply { setPadding(dp(20), 0, dp(12), 0) }
        glow.addView(Switch(this).apply {
            text = "Brillo"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f); typeface = Ui.font(500); setTextColor(Ui.TEXT)
            minHeight = dp(56)
            isChecked = Prefs.glowOn
            val a = Ui.accent()
            thumbTintList = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()), intArrayOf(a, 0xFFBDBDC4.toInt()))
            trackTintList = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()), intArrayOf(a and 0x66FFFFFF, 0x33FFFFFF))
            setOnCheckedChangeListener { _, on -> Prefs.glowOn = on }
        })
        col.addView(glow, full(12))

        // Permisos que faltan
        if (!hasMusic) col.addView(fix("Ver qué suena", "Sin este permiso no sabemos qué suena.") { openMusic() }.apply {
            restricted?.let { addView(text(it, Ui.Type.BODY, Ui.TEXT3)); addView(button("Abrir Info de la app", false) { openAppInfo() }, full(8)) }
        }, full(12))
        if (!hasOverlay) col.addView(fix("Brillo sobre tus apps", "Sin este permiso el borde de luz no se ve.") { openOverlay() }, full(12))

        col.addView(View(this), LinearLayout.LayoutParams(1, 0, 1f)) // empuja los botones abajo
        col.addView(button("Ver la letra") { open(Intent(this, LyricsActivity::class.java)) }, full(24))
        col.addView(button("Ajustes", false) { open(Intent(this, SettingsActivity::class.java)) }, full(8))
        showNow()
    }

    private fun fix(t: String, msg: String, f: () -> Unit) = card().apply {
        addView(text(t, Ui.Type.HEAD))
        addView(text(msg, Ui.Type.BODY, Ui.TEXT2))
        addView(button("Activar", true, f), full(8))
    }

    private fun showNow() {
        val t = nowTitle ?: return
        val has = NowPlaying.title.isNotEmpty()
        t.text = if (has) NowPlaying.title else "Pon algo en YouTube Music"
        artist?.text = NowPlaying.artist
        artist?.visibility = if (has && NowPlaying.artist.isNotEmpty()) View.VISIBLE else View.GONE
        art?.setImageBitmap(if (has) NowPlaying.art else null)
    }
}
