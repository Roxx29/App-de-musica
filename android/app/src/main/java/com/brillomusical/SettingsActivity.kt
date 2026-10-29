package com.brillomusical

import android.app.Activity
import android.os.Bundle

/** Ajustes: una tarjeta por grupo con su fila segmentada. */
class SettingsActivity : Activity() {
    override fun onCreate(s: Bundle?) {
        super.onCreate(s)
        Prefs.init(this)
        val col = screen()
        col.addView(text("Ajustes", Ui.Type.TITLE))
        fun group(name: String, options: List<String>, value: String, set: (String) -> Unit) =
            col.addView(card().apply {
                addView(text(name, Ui.Type.LABEL, Ui.TEXT3))
                addView(segmented(options, value, set))
            }, full(if (col.childCount == 1) 24 else 12))
        group("Borde", Prefs.EDGES, Prefs.edge) { Prefs.edge = it }
        group("Transición", Prefs.TRANSITIONS, Prefs.transition) { Prefs.transition = it }
        group("Fondo", Prefs.BACKDROPS, Prefs.backdrop) { Prefs.backdrop = it }
        group("Carátula", Prefs.COVERS, Prefs.cover) { Prefs.cover = it }
        col.addView(text("Desliza a los lados en la letra para adelantar o retrasar 0,1 s.", Ui.Type.BODY, Ui.TEXT3), full(24))
    }
}
