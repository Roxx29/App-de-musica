package com.brillomusical

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** Letras sincronizadas de LRCLIB (misma fuente que la versión de Windows). */
object Lyrics {
    data class Line(val timeMs: Long, val text: String)

    private val TAG = Regex("""\[(\d+):(\d+(?:\.\d+)?)]""")

    fun parse(lrc: String): List<Line> = lrc.lines().flatMap { raw ->
        val tags = TAG.findAll(raw).toList()
        val text = raw.replace(TAG, "").replace(Regex("<[^>]*>"), "").trim()
        tags.map { Line((it.groupValues[1].toLong() * 60_000 + it.groupValues[2].toDouble() * 1000).toLong(), text) }
    }.sortedBy { it.timeMs }

    fun lineIndex(lines: List<Line>, posMs: Long): Int = lines.indexOfLast { it.timeMs <= posMs }

    /** Llamar fuera del hilo principal. Devuelve lista vacía si no hay letra o falla la red. */
    fun fetch(title: String, artist: String, durationMs: Long): List<Line> = try {
        fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
        var q = "track_name=${enc(title)}&artist_name=${enc(artist)}"
        if (durationMs > 0) q += "&duration=${durationMs / 1000}"
        val conn = URL("https://lrclib.net/api/get?$q").openConnection() as HttpURLConnection
        conn.connectTimeout = 8000; conn.readTimeout = 8000
        conn.setRequestProperty("User-Agent", "BrilloMusical-Android/0.1")
        if (conn.responseCode != 200) emptyList()
        else parse(JSONObject(conn.inputStream.bufferedReader().readText()).optString("syncedLyrics", ""))
    } catch (e: Exception) { emptyList() }
}
