package com.brillomusical

import org.junit.Assert.assertEquals
import org.junit.Test

class LyricsTest {
    @Test fun parse() {
        val l = Lyrics.parse("[00:01.50]Hola <00:02.00>mundo\n[01:00.00][00:00.20]Coro")
        assertEquals(listOf(200L, 1500L, 60000L), l.map { it.timeMs })
        assertEquals("Hola mundo", l[1].text)
        assertEquals(1, Lyrics.lineIndex(l, 1600))
        assertEquals(-1, Lyrics.lineIndex(l, 100))
    }
}
