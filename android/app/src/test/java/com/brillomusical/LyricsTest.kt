package com.brillomusical

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LyricsTest {
    @Test fun parse() {
        val l = Lyrics.parse("[00:01.50]Hola <00:02.00>mundo\n[01:00.00][00:00.20]Coro")
        assertEquals(listOf(200L, 1500L, 60000L), l.map { it.timeMs })
        assertEquals("Hola mundo", l[1].text)
        assertEquals(listOf(1500L to "Hola", 2000L to "mundo"), l[1].words)
        assertEquals(1, Lyrics.lineIndex(l, 1600))
        assertEquals(-1, Lyrics.lineIndex(l, 100))
    }

    @Test fun palabrasConEtiquetas() {
        val l = Lyrics.parse("[00:10.00]<00:10.00>Uno <00:10.50>dos<00:11.00> tres <00:12.00>")
        assertEquals("Uno dos tres", l[0].text)
        assertEquals(listOf(10000L, 10500L, 11000L), Lyrics.wordTimes(l, 0))
    }

    @Test fun palabrasEstimadas() {
        val l = Lyrics.parse("[00:00.00]aa bbbb\n[00:10.00]fin\n[00:20.00]")
        // 2 palabras: como mucho 1,5 s; pesos 4 y 6
        assertEquals(listOf(0L, 600L), Lyrics.wordTimes(l, 0))
        assertEquals(listOf(10000L), Lyrics.wordTimes(l, 1))
        assertTrue(l[2].words.isEmpty())
    }

    @Test fun clean() {
        assertEquals("Song" to "Band", Lyrics.clean("Song (Official Video)", "Band - Topic"))
        assertEquals("Song" to "Band", Lyrics.clean("Band - Song [Lyrics]", ""))
        assertEquals("A - B" to "Other", Lyrics.clean("A - B", "Other"))
        assertEquals("Ana", Lyrics.mainArtist("Ana feat. Luis, Pepe"))
    }

    @Test fun isAd() {
        assertTrue(Lyrics.isAd("Anuncio", "Google", "", 0))
        assertTrue(Lyrics.isAd("Algo", "", "Álbum", 200_000))
        assertTrue(Lyrics.isAd("Algo", "Marca", "", 20_000))
        assertFalse(Lyrics.isAd("Algo", "Marca", "Disco", 20_000))
        assertFalse(Lyrics.isAd("Bad Romance", "Lady Gaga", "", 290_000))
    }

    @Test fun eligePorDuracion() {
        val found = listOf(180.0 to "a", 203.0 to "b", 200.5 to "c", 201.0 to "")
        assertEquals("c", Lyrics.pick(found, 200.0))
        assertNull(Lyrics.pick(found, 300.0))
        assertEquals("a", Lyrics.pick(found, 0.0))
    }

    @Test fun paleta() {
        val red = (0xFF shl 24) or (200 shl 16); val gray = 0xFF808080.toInt(); val blue = 0xFF0000C8.toInt()
        val p = MusicListener.palette(IntArray(50) { red } + IntArray(80) { gray } + IntArray(20) { blue })
        assertEquals(2, p.size)
        assertTrue((p[0] shr 16 and 255) > 200 && (p[0] and 255) < 80) // rojo primero
        assertEquals(1, MusicListener.palette(IntArray(10) { gray }).size) // gris: color de reserva
    }
}
