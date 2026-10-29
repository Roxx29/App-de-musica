package com.brillomusical

import android.app.Activity
import android.graphics.Color
import android.graphics.RenderEffect
import android.graphics.Shader
import android.os.Build
import android.os.Bundle
import android.widget.FrameLayout
import android.widget.ImageView

/** Pantalla de letra: portada difuminada de fondo + constelación. */
class LyricsActivity : Activity() {
    private lateinit var bg: ImageView
    private val onChange = { bg.setImageBitmap(NowPlaying.art) }

    override fun onCreate(s: Bundle?) {
        super.onCreate(s)
        window.decorView.setBackgroundColor(Color.BLACK)
        bg = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            alpha = 0.45f
            if (Build.VERSION.SDK_INT >= 31) setRenderEffect(RenderEffect.createBlurEffect(40f, 40f, Shader.TileMode.CLAMP))
        }
        setContentView(FrameLayout(this).apply { addView(bg); addView(ConstellationView(this@LyricsActivity)) })
    }

    override fun onStart() { super.onStart(); NowPlaying.listen(onChange); onChange() }
    override fun onStop() { super.onStop(); NowPlaying.unlisten(onChange) }
}
