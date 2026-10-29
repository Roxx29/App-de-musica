package com.brillomusical

import android.os.SystemClock

/** Ritmo simulado (sin micrófono): pulso a 120 BPM anclado a la posición + golpe en cada cambio de línea. */
object Beat {
    const val PERIOD = 500L // 120 BPM
    private var line = -1
    /** uptime del último cambio de línea de la letra. */
    var hitAt = -10_000L; private set

    /** Energía 0..1. Llamar a menudo (cada fotograma): detecta también los cambios de línea. */
    fun energy(): Float {
        val now = SystemClock.uptimeMillis()
        val i = Lyrics.lineIndex(NowPlaying.lines, NowPlaying.lyricsPositionMs())
        if (i != line) { if (i >= 0) hitAt = now; line = i }
        if (!NowPlaying.playing) return 0.3f
        val p = 1f - NowPlaying.positionMs().mod(PERIOD) / PERIOD.toFloat() // 1 justo en el pulso
        return (0.3f + 0.4f * p * p + 0.3f * Effects.env(now - hitAt, 60, 400)).coerceIn(0f, 1f)
    }
}
