package com.brillomusical

import android.app.Activity
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Inicio: pide los dos permisos y abre la letra. */
class MainActivity : Activity() {
    private lateinit var music: Button
    private lateinit var overlay: Button

    override fun onCreate(s: Bundle?) {
        super.onCreate(s)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setPadding(48, 48, 48, 48) }
        box.addView(TextView(this).apply { text = "Tu música, en la luz de tu pantalla."; textSize = 20f; gravity = Gravity.CENTER })
        music = Button(this).apply { setOnClickListener { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) } }
        overlay = Button(this).apply {
            setOnClickListener { startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName"))) }
        }
        box.addView(music); box.addView(overlay)
        box.addView(Button(this).apply { text = "Ver la letra"; setOnClickListener { startActivity(Intent(this@MainActivity, LyricsActivity::class.java)) } })
        setContentView(box)
    }

    override fun onResume() {
        super.onResume()
        val me = ComponentName(this, MusicListener::class.java).flattenToString()
        val hasMusic = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")?.contains(me) == true
        music.text = if (hasMusic) "✓ Acceso a la música" else "1. Permitir leer lo que suena"
        overlay.text = if (Settings.canDrawOverlays(this)) "✓ Brillo en pantalla" else "2. Permitir el brillo sobre otras apps"
    }
}
