package com.brillomusical

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import kotlin.math.abs
import kotlin.math.roundToLong

/** Letras sincronizadas de LRCLIB (misma fuente y reglas que la versión de Windows). */
object Lyrics {
    /** words: inicio (ms) y texto de cada palabra; exactos con <mm:ss.xx>, si no estimados por longitud. */
    data class Line(val timeMs: Long, val text: String, val words: List<Pair<Long, String>> = emptyList())

    private const val API = "https://lrclib.net/api/"
    private const val MISS_TTL = 24 * 3600_000L // "sin letra" se vuelve a buscar al día siguiente
    private val TAG = Regex("""\[(\d+):(\d+(?:\.\d+)?)]""")
    private val WTAG = Regex("""<(\d+):(\d+(?:\.\d+)?)>\s*([^<]*)""")
    private val JUNK = Regex(
        """\s*[(\[][^)\]]*\b(official|video|audio|lyrics?|letra|visuali[sz]er|mv|hd|4k|remaster\w*)\b[^)\]]*[)\]]""",
        RegexOption.IGNORE_CASE)
    private val AD = Regex("""^(ad|anuncio|advertisement|publicidad)$|\b(anuncio|advertisement|publicidad)\b|\bad ·""",
        RegexOption.IGNORE_CASE)

    private fun ms(m: String, s: String) = m.toLong() * 60_000 + (s.toDouble() * 1000).roundToLong()

    fun parse(lrc: String): List<Line> {
        val raw = lrc.lines().flatMap { l ->
            val body = l.replace(TAG, "").trim()
            val tagged = WTAG.findAll(body).flatMap { m ->
                val t = ms(m.groupValues[1], m.groupValues[2])
                m.groupValues[3].split(Regex("\\s+")).filter { it.isNotEmpty() }.map { t to it } // etiqueta de cierre: sin palabras
            }.toList()
            val text = body.replace(Regex("<[^>]*>"), "").replace(Regex("\\s+"), " ").trim()
            // palabras antes de la primera etiqueta: empiezan con la línea
            val before = if (tagged.isEmpty()) emptyList() else body.substringBefore('<').split(Regex("\\s+")).filter { it.isNotEmpty() }
            TAG.findAll(l).map {
                val t = ms(it.groupValues[1], it.groupValues[2])
                Line(t, text, if (tagged.isEmpty()) emptyList() else before.map { w -> t to w } + tagged)
            }.toList()
        }.sortedBy { it.timeMs }
        return raw.mapIndexed { i, l -> if (l.words.isNotEmpty()) l else l.copy(words = estimate(l, raw.getOrNull(i + 1))) }
    }

    /** Reparto por longitud; una nota larga al final no retrasa las palabras (~0,5 s por palabra como mucho). */
    private fun estimate(l: Line, next: Line?): List<Pair<Long, String>> {
        val ws = l.text.split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (ws.isEmpty()) return emptyList()
        val end = next?.timeMs ?: (l.timeMs + 6000)
        val span = minOf(end - l.timeMs, 500L * ws.size + 500, 6000L).coerceAtLeast(0)
        val total = ws.sumOf { it.length + 2 }
        var acc = 0
        return ws.map { w -> (l.timeMs + span * acc / total to w).also { acc += w.length + 2 } }
    }

    fun wordTimes(lines: List<Line>, idx: Int): List<Long> = lines[idx].words.map { it.first }

    fun lineIndex(lines: List<Line>, posMs: Long): Int = lines.indexOfLast { it.timeMs <= posMs }

    /** Quita "(Official Video)" y similares; "Artista - Título" en el título se separa. */
    fun clean(title: String, artist: String): Pair<String, String> {
        var t = title.replace(JUNK, "").trim()
        var a = artist.trim().replace(Regex("""\s*-\s*Topic$|VEVO$"""), "").trim()
        if (" - " in t && (a.isEmpty() || t.lowercase().startsWith(a.lowercase() + " - "))) {
            val p = t.split(" - ", limit = 2); a = p[0].trim(); t = p[1].trim()
        }
        return t to a
    }

    fun mainArtist(artist: String): String =
        artist.split(Regex(""",|&| feat\.? | ft\.? """, RegexOption.IGNORE_CASE))[0].trim()

    fun isAd(title: String, artist: String, album: String, durationMs: Long): Boolean =
        artist.isBlank() || AD.containsMatchIn(title) || (durationMs in 1 until 35_000 && album.isEmpty())

    /** syncedLyrics de la versión con duración más parecida (±3 s); sin duración, la primera. pares: (segundos, lrc). */
    fun pick(found: List<Pair<Double, String>>, durationSec: Double): String? {
        val ok = found.filter { it.second.isNotBlank() }
        if (durationSec <= 0) return ok.firstOrNull()?.second
        return ok.filter { abs(it.first - durationSec) <= 3 }.minByOrNull { abs(it.first - durationSec) }?.second
    }

    /**
     * Llamar fuera del hilo principal. null = sin red (no se cachea); vacía = no hay letra sincronizada.
     * cacheDir: carpeta de caché (p. ej. File(context.cacheDir, "lyrics")), o null para no cachear.
     */
    fun fetch(title: String, artist: String, album: String, durationMs: Long, cacheDir: File?): List<Line>? {
        val (t, a) = clean(title, artist)
        val sec = (durationMs + 500) / 1000
        // sin duración puede ser otra versión: no se guarda en caché
        val file = if (cacheDir != null && sec > 0) File(cacheDir, sha1("$a|$t|$sec".lowercase()) + ".lrc") else null
        if (file != null && file.exists()) {
            val lrc = try { file.readText() } catch (e: IOException) { null }
            if (lrc != null) {
                val lines = parse(lrc)
                if (lines.isNotEmpty()) return lines
                if (lrc.isEmpty() && System.currentTimeMillis() - file.lastModified() < MISS_TTL) return emptyList()
            } // archivo roto o fallo caducado: se busca otra vez
        }
        val lrc = try { query(t, a, album, sec) } catch (e: Exception) { return null }
        if (file != null) try {
            file.parentFile?.mkdirs()
            val tmp = File(file.path + ".tmp")
            tmp.writeText(lrc)
            tmp.renameTo(file)
        } catch (e: IOException) { } // sin caché no es grave
        return parse(lrc)
    }

    /** LRC encontrado o "" si no hay. Lanza excepción si falla la red o el servidor. */
    private fun query(title: String, artist: String, album: String, sec: Long): String {
        if (sec > 0) {
            val got = get("get", "track_name" to title, "artist_name" to artist, "album_name" to album, "duration" to "$sec")
            if (got != null) synced(JSONObject(got)).let { if (it.isNotBlank()) return it }
        }
        val arr = JSONArray(get("search", "track_name" to title, "artist_name" to mainArtist(artist)) ?: "[]")
        val found = (0 until arr.length()).map { arr.getJSONObject(it) }.map { it.optDouble("duration", 0.0) to synced(it) }
        return pick(found, sec.toDouble()) ?: ""
    }

    private fun synced(o: JSONObject) = if (o.isNull("syncedLyrics")) "" else o.optString("syncedLyrics", "")

    /** Cuerpo de la respuesta; null si 404. */
    private fun get(endpoint: String, vararg params: Pair<String, String>): String? {
        val q = params.joinToString("&") { "${it.first}=${URLEncoder.encode(it.second, "UTF-8")}" }
        val conn = URL("$API$endpoint?$q").openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 6000; conn.readTimeout = 6000
            conn.setRequestProperty("User-Agent", "BrilloMusical-Android/0.2")
            return when (conn.responseCode) {
                200 -> conn.inputStream.bufferedReader().use { it.readText() }
                404 -> null
                else -> throw IOException("LRCLIB ${conn.responseCode}")
            }
        } finally { conn.disconnect() }
    }

    private fun sha1(s: String) =
        MessageDigest.getInstance("SHA-1").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }
}
