package com.brillomusical

import android.content.Context
import android.content.SharedPreferences

/** Ajustes guardados. Mismos nombres de opciones que en la versión de PC. */
object Prefs {
    val EDGES = listOf("Automático", "Estático", "Respirar", "Al ritmo", "Giratorio", "Aurora", "Destello", "Fuego", "Ondas", "Arcoíris")
    val TRANSITIONS = listOf("Automática", "Aleatoria", "Viaje", "Remolino", "Explosión", "Lluvia de estrellas", "Polvo", "Reconstelar", "Onda")
    val BACKDROPS = listOf("Automático", "Sin portada", "Difuminado", "Ambiente en movimiento", "Ken Burns", "Al ritmo")
    val COVERS = listOf("Tarjeta", "Arriba", "Marca de agua", "Oculta")

    private lateinit var sp: SharedPreferences
    private val listeners = mutableListOf<() -> Unit>()

    fun init(ctx: Context) {
        if (!::sp.isInitialized) sp = ctx.applicationContext.getSharedPreferences("brillo", Context.MODE_PRIVATE)
    }

    var edge: String get() = sp.getString("edge", EDGES[0])!!; set(v) = put("edge", v)
    var transition: String get() = sp.getString("transition", TRANSITIONS[0])!!; set(v) = put("transition", v)
    var backdrop: String get() = sp.getString("backdrop", BACKDROPS[0])!!; set(v) = put("backdrop", v)
    var cover: String get() = sp.getString("cover", COVERS[0])!!; set(v) = put("cover", v)
    var glowOn: Boolean get() = sp.getBoolean("glow", true); set(v) { sp.edit().putBoolean("glow", v).apply(); changed() }
    var onboarded: Boolean get() = sp.getBoolean("onboarded", false); set(v) { sp.edit().putBoolean("onboarded", v).apply() }

    /** Desfase de la letra por canción, en ms (positivo = adelantar). */
    fun offset(key: String): Long = sp.getLong("off:$key", 0L)
    fun addOffset(key: String, deltaMs: Long): Long {
        val v = (offset(key) + deltaMs).coerceIn(-10_000, 10_000)
        sp.edit().putLong("off:$key", v).apply()
        return v
    }

    private fun put(k: String, v: String) { sp.edit().putString(k, v).apply(); changed() }
    fun listen(l: () -> Unit) { listeners += l }
    fun unlisten(l: () -> Unit) { listeners -= l }
    private fun changed() = listeners.toList().forEach { it() }
}
