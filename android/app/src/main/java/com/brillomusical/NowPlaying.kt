package com.brillomusical

import android.graphics.Bitmap
import android.graphics.Color
import android.os.SystemClock

/** Estado de la canción actual, compartido entre el servicio y las pantallas (hilo principal). */
object NowPlaying {
    var title = ""
    var artist = ""
    var durationMs = 0L
    var art: Bitmap? = null
    var color = Color.rgb(120, 160, 255)
    var playing = false
    var palette: List<Int> = listOf(color)   // colores de la portada, el primero es el principal
    var ad = false
    var lines: List<Lyrics.Line> = emptyList()
    var lyricsState = LyricsState.NONE
    enum class LyricsState { NONE, LOADING, FOUND, NOT_FOUND, OFFLINE }

    /** Clave de la canción (desfase por canción, caché). */
    val key get() = "$title|$artist"

    private var posMs = 0L
    private var stamp = 0L
    private var speed = 1f
    private val listeners = mutableListOf<() -> Unit>()

    fun setPosition(pos: Long, updateTime: Long, playbackSpeed: Float) {
        // algunas sesiones no dan la hora de la actualización: se toma ahora
        posMs = pos; stamp = if (updateTime > 0) updateTime else SystemClock.elapsedRealtime(); speed = playbackSpeed
    }

    /** Posición para la letra: extrapolada + desfase manual de la canción. */
    fun lyricsPositionMs(): Long = positionMs() + Prefs.offset(key)

    /** Posición extrapolada desde la última actualización de la sesión. */
    fun positionMs(): Long =
        if (playing) posMs + ((SystemClock.elapsedRealtime() - stamp) * speed).toLong() else posMs

    fun listen(l: () -> Unit) { listeners += l }
    fun unlisten(l: () -> Unit) { listeners -= l }
    fun changed() = listeners.toList().forEach { it() }
}
