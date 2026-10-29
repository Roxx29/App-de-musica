package com.brillomusical

import android.content.ComponentName
import android.graphics.Bitmap
import android.graphics.Color
import android.media.MediaMetadata
import android.media.session.MediaController
import android.media.session.MediaSessionManager
import android.media.session.PlaybackState
import android.os.Handler
import android.os.Looper
import android.service.notification.NotificationListenerService

/** Lee la sesión multimedia de YouTube Music y mantiene el brillo encendido. */
class MusicListener : NotificationListenerService() {
    private val main = Handler(Looper.getMainLooper())
    private var controller: MediaController? = null
    private var glow: GlowOverlay? = null
    private var lyricsKey = ""

    private val callback = object : MediaController.Callback() {
        override fun onMetadataChanged(m: MediaMetadata?) = update()
        override fun onPlaybackStateChanged(s: PlaybackState?) = update()
        override fun onSessionDestroyed() = attach(null)
    }

    private val sessions = MediaSessionManager.OnActiveSessionsChangedListener { attach(it) }

    override fun onListenerConnected() {
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
        glow?.hide(); glow = null
    }

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
        val art = m?.getBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART) ?: m?.getBitmap(MediaMetadata.METADATA_KEY_ART)
        if (art != null && art !== NowPlaying.art) { NowPlaying.art = art; NowPlaying.color = vivid(art) }
        glow?.show() // por si el permiso de brillo se concedió después
        loadLyrics()
        NowPlaying.changed()
    }

    private fun loadLyrics() {
        val key = "${NowPlaying.title}|${NowPlaying.artist}"
        if (key == lyricsKey || NowPlaying.title.isEmpty()) return
        lyricsKey = key
        NowPlaying.lines = emptyList()
        val (t, a, d) = Triple(NowPlaying.title, NowPlaying.artist, NowPlaying.durationMs)
        Thread {
            val lines = Lyrics.fetch(t, a, d)
            main.post { if (key == lyricsKey) { NowPlaying.lines = lines; NowPlaying.changed() } }
        }.start()
    }

    companion object {
        const val YT_MUSIC = "com.google.android.apps.youtube.music"

        /** Color más vivo de la portada (saturación × brillo), como en la versión de Windows. */
        fun vivid(b: Bitmap): Int {
            val small = Bitmap.createScaledBitmap(b, 16, 16, true)
            val hsv = FloatArray(3)
            var best = Color.rgb(120, 160, 255); var score = -1f
            for (x in 0 until 16) for (y in 0 until 16) {
                val p = small.getPixel(x, y)
                Color.colorToHSV(p, hsv)
                val sc = hsv[1] * hsv[2]
                if (sc > score) { score = sc; best = p }
            }
            Color.colorToHSV(best, hsv)
            hsv[2] = maxOf(hsv[2], 0.85f) // que brille aunque la portada sea oscura
            return Color.HSVToColor(hsv)
        }
    }
}
