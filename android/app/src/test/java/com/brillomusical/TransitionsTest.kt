package com.brillomusical

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TransitionsTest {
    @Test fun llegaASuSitio() {
        val o = FloatArray(6)
        for (style in Transitions.STYLES + Transitions.CUT) for (e in listOf(0.2f, 0.6f, 0.9f)) {
            val p = Transitions.params(style, 7L, e)
            val tot = Transitions.total(p, 8)
            if (style != Transitions.CUT) assertTrue("$style $tot", tot in 0.79f..1.21f)
            for (i in 0 until 8) {
                Transitions.inState(p, tot, 300f + 40 * i, 500f, i, 1080f, 1920f, 100f, 100f, true, o)
                assertEquals(style, 300f + 40 * i, o[0], 1f); assertEquals(style, 500f, o[1], 1f)
                assertEquals(style, 1f, o[3], 0.01f); assertEquals(style, 1f, o[4], 0.01f)
            }
            Transitions.outState(p, Transitions.outTime(p), 300f, 500f, 0, 1080f, 1920f, o)
            assertTrue(style, o[4] < 0.01f) // el texto ya se fue
        }
    }

    @Test fun eleccion() {
        assertEquals("Onda", Transitions.pick("Onda", 1, 0.5f, null))
        assertTrue(Transitions.pick("Aleatoria", 1, 0.5f, "Viaje") != "Viaje")
        assertTrue(Transitions.pick("Automática", 1, 0.9f, null) in listOf("Explosión", "Onda", "Viaje"))
    }
}
