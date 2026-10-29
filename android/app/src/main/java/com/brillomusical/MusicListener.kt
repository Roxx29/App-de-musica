package com.brillomusical

import android.content.ComponentName
import android.graphics.Bitmap
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.os.Handler
import android.os.Looper
import android.service.notification.NotificationListenerService
import java.io.File
import java.util.concurrent.Executors

/** Lee la sesión multimedia de YouTube Music y mantiene el brillo encendido. */
class MusicListener : NotificationListenerService() {
    private val main = Handler(Looper.getMainLooper())
    private val net = Executors.newSingleThreadExecutor() // un solo hilo de red: las búsquedas van en orden
    private var controller: MediaController? = null
    private var glow: GlowOverlay? = null
    @Volatile private var lyricsKey = ""
    private var artKey = ""
    private var album = ""
    private var wasPlaying = false
    private val retry = Runnable { if (NowPlaying.playing) retryLyrics() }

    private val callback = object : MediaController.Callback() {
        override fun onMetadataChanged(m: MediaMetadata?) = update()
        override fun onPlaybackStateChanged(s: PlaybackState?) = update()
        override fun onSessionDestroyed() = attach(null)
    }

    private val sessions = MediaSessionManager.OnActiveSessionsChangedListener { attach(it) }

    override fun onListenerConnected() {
        Prefs.init(this)
        val msm = getSystemService(MediaSessionManager::class.java)
        val me = ComponentName(this, MusicListener::class.java)
        msm.addOnActiveSessionsChangedListener(sessions, me)
        attach(msm.getActiveSessions(me))
        glow = GlowOverlay(this)
        update()
    }

    override fun onListenerDisconnected() {
        getSystemService(MediaSessionManager::class.java).removeOnActiveSessionsChangedListener(sessions)
        controller?.unregisterCallback(callback)
        main.removeCallbacks(retry)
        glow?.hide(); glow = null
    }

    override fun onDestroy() { net.shutdownNow(); super.onDestroy() }

    private fun attach(list: List<MediaController>?) {
        val c = list?.firstOrNull { it.packageName == YT_MUSIC }
        if (c?.sessionToken == controller?.sessionToken) return
        controller?.unregisterCallback(callback)
        controller = c
        c?.registerCallback(callback, main)
        update()
    }

    private fun update() {
        val c = controller
        val m = c?.metadata
        val s = c?.playbackState
        NowPlaying.playing = s?.state == PlaybackState.STATE_PLAYING
        if (s != null) NowPlaying.setPosition(s.position, s.lastPositionUpdateTime, s.playbackSpeed)
        NowPlaying.title = m?.getString(MediaMetadata.METADATA_KEY_TITLE).orEmpty()
        NowPlaying.artist = m?.getString(MediaMetadata.METADATA_KEY_ARTIST).orEmpty()
        NowPlaying.durationMs = m?.getLong(MediaMetadata.METADATA_KEY_DURATION) ?: 0L
        val album = m?.getString(MediaMetadata.METADATA_KEY_ALBUM).orEmpty()
        NowPlaying.ad = NowPlaying.title.isNotEmpty() && Lyrics.isAd(NowPlaying.title, NowPlaying.artist, album, NowPlaying.durationMs)
        updateArt(m?.getBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART) ?: m?.getBitmap(MediaMetadata.METADATA_KEY_ART))
        glow?.show() // por si el permiso de brillo se concedió después
        loadLyrics(album)
        // al volver a sonar sin red, se reintenta enseguida
        if (NowPlaying.playing && !wasPlaying && NowPlaying.lyricsState == NowPlaying.LyricsState.OFFLINE) retryLyrics()
        wasPlaying = NowPlaying.playing
        NowPlaying.changed()
    }

    /** Recalcula colores solo con canción nueva o portada de otro tamaño (cada evento trae un Bitmap nuevo). */
    private fun updateArt(art: Bitmap?) {
        val key = NowPlaying.key
        if (art == null) {
            if (key != artKey) { artKey = key; NowPlaying.art = null; NowPlaying.color = DEFAULT; NowPlaying.palette = listOf(DEFAULT) }
            return
        }
        if (key == artKey && art.width == NowPlaying.art?.width) return
        artKey = key
        NowPlaying.art = art
        val small = Bitmap.createScaledBitmap(art, 24, 24, true)
        val px = IntArray(24 * 24).also { small.getPixels(it, 0, 24, 0, 0, 24, 24) }
        NowPlaying.palette = palette(px)
        NowPlaying.color = NowPlaying.palette[0]
    }

    private fun loadLyrics(album: String) {
        val key = NowPlaying.key
        if (key == lyricsKey) return
        lyricsKey = key
        this.album = album
        main.removeCallbacks(retry)
        NowPlaying.lines = emptyList()
        NowPlaying.lyricsState = NowPlaying.LyricsState.NONE
        if (NowPlaying.title.isEmpty() || NowPlaying.ad) return
        fetch()
    }

    private fun retryLyrics() {
        if (NowPlaying.lyricsState != NowPlaying.LyricsState.OFFLINE || lyricsKey != NowPlaying.key) return
        main.removeCallbacks(retry)
        fetch()
    }

    private fun fetch() {
        val key = lyricsKey
        val (t, a, d) = Triple(NowPlaying.title, NowPlaying.artist, NowPlaying.durationMs)
        val al = album
        val dir = File(cacheDir, "lyrics")
        NowPlaying.lyricsState = NowPlaying.LyricsState.LOADING
        net.execute {
            if (key != lyricsKey) return@execute // ya cambió de canción mientras esperaba
            val lines = Lyrics.fetch(t, a, al, d, dir)
            main.post {
                if (key != lyricsKey) return@post
                NowPlaying.lines = lines.orEmpty()
                NowPlaying.lyricsState = when {
                    lines == null -> NowPlaying.LyricsState.OFFLINE
                    lines.isEmpty() -> NowPlaying.LyricsState.NOT_FOUND
                    else -> NowPlaying.LyricsState.FOUND
                }
                if (lines == null) main.postDelayed(retry, RETRY_MS)
                NowPlaying.changed()
            }
        }
    }

    companion object {
        const val YT_MUSIC = "com.google.android.apps.youtube.music"
        const val RETRY_MS = 15_000L
        val DEFAULT = argb(120, 160, 255)
        private val FALLBACK = argb(255, 179, 71) // ámbar si la portada es gris/negra/blanca

        private fun argb(r: Int, g: Int, b: Int) = (0xFF shl 24) or (r shl 16) or (g shl 8) or b

        /**
         * Hasta 4 colores vivos de tonos distintos (>60°), el dominante primero, como color.py de PC.
         * Puro (píxeles ARGB) para poder probarlo sin Android.
         */
        fun palette(pixels: IntArray): List<Int> {
            // por cada tramo de 30° de tono: peso (cantidad × saturación) y medias de h, s, v
            val w = DoubleArray(12); val hs = DoubleArray(12); val ss = DoubleArray(12); val vs = DoubleArray(12)
            for (p in pixels) {
                val r = (p shr 16 and 255) / 255.0; val g = (p shr 8 and 255) / 255.0; val b = (p and 255) / 255.0
                val max = maxOf(r, g, b); val d = max - minOf(r, g, b)
                val s = if (max > 0) d / max else 0.0
                if (max < 0.15 || s < 0.2) continue // casi negro o gris (incluye casi blanco)
                val h = 60 * when (max) { r -> ((g - b) / d).mod(6.0); g -> (b - r) / d + 2; else -> (r - g) / d + 4 }
                val i = (h / 30).toInt().coerceIn(0, 11)
                w[i] += s; hs[i] += h * s; ss[i] += s * s; vs[i] += max * s
            }
            val chosen = mutableListOf<Double>()
            val out = mutableListOf<Int>()
            for (i in (0 until 12).sortedByDescending { w[it] }) {
                if (w[i] <= 0 || out.size == 4) break
                val h = hs[i] / w[i]
                if (chosen.any { minOf(Math.abs(h - it), 360 - Math.abs(h - it)) <= 60 }) continue
                chosen += h
                out += tune(h, ss[i] / w[i], vs[i] / w[i])
            }
            return out.ifEmpty { listOf(FALLBACK) }
        }

        /** Saturación mínima 0,55 y luminosidad (HSL) entre 0,5 y 0,7 para que brille sin quemarse. */
        private fun tune(h: Double, sv: Double, v: Double): Int {
            val l0 = v * (1 - sv / 2)
            val sl0 = if (l0 <= 0 || l0 >= 1) 0.0 else (v - l0) / minOf(l0, 1 - l0)
            val l = l0.coerceIn(0.5, 0.7); val s = maxOf(sl0, 0.55).coerceAtMost(1.0)
            val c = (1 - Math.abs(2 * l - 1)) * s
            val x = c * (1 - Math.abs((h / 60).mod(2.0) - 1))
            val (r, g, b) = when ((h / 60).toInt().coerceIn(0, 5)) {
                0 -> Triple(c, x, 0.0); 1 -> Triple(x, c, 0.0); 2 -> Triple(0.0, c, x)
                3 -> Triple(0.0, x, c); 4 -> Triple(x, 0.0, c); else -> Triple(c, 0.0, x)
            }
            val m = l - c / 2
            fun ch(v: Double) = ((v + m) * 255).toInt().coerceIn(0, 255)
            return argb(ch(r), ch(g), ch(b))
        }
    }
}
