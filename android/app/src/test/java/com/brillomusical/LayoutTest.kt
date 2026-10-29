package com.brillomusical

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.hypot

class LayoutTest {
    private fun line(t: Long, text: String) = Lyrics.parse("[00:00.00]$text").first().let {
        Lyrics.Line(t, text, it.words.map { w -> t + w.first to w.second })
    }

    @Test fun estrofas() {
        val lines = listOf(line(0, "a b"), line(1000, "c d"), Lyrics.Line(2000, ""), line(3000, "e"),
            line(20_000, "f"), line(21_000, "g"), line(22_000, "h"), line(23_000, "i"), line(24_000, "j"))
        val s = Layout.stanzas(lines)
        // corte en línea vacía, en hueco largo y a las 4 líneas
        assertEquals(listOf("a b c d", "e", "f g h i", "j"), s.map { st -> st.joinToString(" ") { it.text } })
    }

    @Test fun particion() {
        val lines = listOf(line(0, "1 2 3 4 5"), line(1000, "6 7 8 9"), line(2000, (1..12).joinToString(" ")))
        val s = Layout.stanzas(lines)
        assertEquals(listOf(5, 4, 6, 6), s.map { it.size })
        assertTrue(s.all { it.size <= Layout.MAX_WORDS })
    }

    @Test fun frame() {
        val lines = listOf(line(1000, "a b"), Lyrics.Line(2000, ""), line(10_000, "c"))
        val s = Layout.stanzas(lines)
        assertNull(Layout.frame(lines, emptyList(), 0))
        assertEquals(-1, Layout.frame(lines, s, 0)!!.activeWord)
        val f = Layout.frame(lines, s, 5000)!! // línea vacía: sigue la estrofa anterior
        assertEquals(0, f.stanza); assertEquals(1, f.activeWord); assertEquals(1, f.activeLine)
        assertEquals(1, Layout.frame(lines, s, 10_000)!!.stanza)
    }

    @Test fun colocacionSinSolapes() {
        for (seed in 0L until 20) {
            val p = Layout.place(8, seed, 1080f, 2000f, 180f, avoidBottom = 600f)
            assertEquals(8, p.size)
            assertTrue(p.all { it.first in 0f..1080f && it.second <= 2000f - 600f })
            for (i in p.indices) for (j in i + 1 until p.size)
                assertTrue(hypot(p[i].first - p[j].first, p[i].second - p[j].second) >= 180f)
            assertEquals(p, Layout.place(8, seed, 1080f, 2000f, 180f, avoidBottom = 600f))
        }
    }
}
