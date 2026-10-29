package com.brillomusical

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.os.SystemClock
import android.text.Layout.Alignment
import android.text.StaticLayout
import android.text.TextPaint
import android.text.TextUtils
import android.util.TypedValue
import android.view.View
import kotlin.math.ceil
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * Letra en constelación (port de constellation.py): cada estrofa es una constelación, cada palabra una estrella
 * de 4 puntas con su texto. También dibuja la carátula (tarjeta, arriba, marca de agua, grande) y los avisos.
 * Sin objetos nuevos por fotograma: textos y portadas en Bitmap, creados solo cuando cambian.
 */
class ConstellationView(ctx: Context) : View(ctx) {
    var onWant: () -> Unit = {} // pide más fotogramas a la Activity

    /** Estrellas de una estrofa: destino (tx, ty), estado dibujado y base (copia del dibujado al empezar a irse). */
    private class Stars {
        var n = 0; var linked = 0; var grow = 1f
        var words: List<Layout.Word> = emptyList()
        val tx = FloatArray(MAX); val ty = FloatArray(MAX)
        val x = FloatArray(MAX); val y = FloatArray(MAX); val r = FloatArray(MAX); val sa = FloatArray(MAX)
        val la = FloatArray(MAX); val ls = FloatArray(MAX); val f = FloatArray(MAX); val trail = FloatArray(MAX)
        val br = FloatArray(MAX); val bsa = FloatArray(MAX); val bla = FloatArray(MAX); val bls = FloatArray(MAX); val bf = FloatArray(MAX)
        val kind = IntArray(MAX) // 0 futura, 1 cantada, 2 activa, 3 recién cantada (encogiendo)
        val act = arrayOfNulls<Bitmap>(MAX); val sung = arrayOfNulls<Bitmap>(MAX)
        fun snapshot() {
            x.copyInto(tx); y.copyInto(ty); r.copyInto(br); sa.copyInto(bsa); la.copyInto(bla); ls.copyInto(bls); f.copyInto(bf)
        }
    }

    private val dm = resources.displayMetrics
    private val d = dm.density
    private fun sp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, v, dm)
    private val pad = 12 * d // margen de los Bitmap de texto (sombra y halo)
    private val born = SystemClock.uptimeMillis()
    private var cur = Stars()
    private var old = Stars()
    private val o = FloatArray(6)
    private val rf = RectF()
    private val star = Path().apply {
        val p = floatArrayOf(0f, -1f, 0.2f, -0.2f, 1f, 0f, 0.2f, 0.2f, 0f, 1f, -0.2f, 0.2f, -1f, 0f, -0.2f, -0.2f)
        moveTo(p[0], p[1]); for (i in 2 until p.size step 2) lineTo(p[i], p[i + 1]); close()
    }
    private val starPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1.5f * d; strokeCap = Paint.Cap.ROUND }
    private val bmpPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)

    // letra y estrofa en pantalla
    private var lines: List<Lyrics.Line>? = null
    private var stanzas: List<List<Layout.Word>> = emptyList()
    private var shown = -1
    private var shownLines: List<Lyrics.Line>? = null
    private var shownTitle = ""; private var shownArtist = ""
    private var laidStanza = -2; private var laidW = 0f; private var laidH = 0f; private var laidCover = ""
    private var trans: Transitions.P? = null
    private var t0 = 0L
    private var prevStyle: String? = null

    // color, carátula y textos (se rehacen solo al cambiar)
    private var colorSrc = 0; private var accent = 0
    private var halo: Bitmap? = null
    private var artSrc: Bitmap? = null; private var artSide = 0
    private var smallArt: Bitmap? = null; private var bigArt: Bitmap? = null
    private var txTitle: String? = null; private var txArtist = ""; private var txW = 0f
    private var cardTitle: Bitmap? = null; private var cardArtist: Bitmap? = null
    private var heroTitle: Bitmap? = null; private var heroArtist: Bitmap? = null; private var footer: Bitmap? = null
    private var msgText: String? = null; private var msgW = 0f; private var msgBmp: Bitmap? = null
    private var heroP = 0f
    private var lastNow = 0L

    override fun onDraw(c: Canvas) {
        val now = SystemClock.uptimeMillis()
        val dt = if (lastNow == 0L) 0f else min(0.1f, (now - lastNow) / 1000f)
        lastNow = now
        val w = width.toFloat(); val h = height.toFloat()
        if (w <= 0 || h <= 0) return
        val np = NowPlaying
        syncColor(); syncTexts(w, h)
        val song = np.title.isNotEmpty() && !np.ad
        val ls = np.lines
        if (ls !== lines) { lines = ls; stanzas = Layout.stanzas(ls) }
        val pos = np.lyricsPositionMs()
        val frame = if (song && np.lyricsState == NowPlaying.LyricsState.FOUND) Layout.frame(ls, stanzas, pos) else null
        val gap = frame != null && instrumental(frame, pos)
        val noLyrics = song && (np.lyricsState == NowPlaying.LyricsState.NOT_FOUND ||
            (np.lyricsState == NowPlaying.LyricsState.FOUND && frame == null))
        val target = if (frame != null && !gap) frame.stanza else -1
        val heroWant = noLyrics || gap
        heroP = if (heroWant) min(1f, heroP + dt / 0.9f) else max(0f, heroP - dt / 0.7f)

        // cambio de estrofa, de letra o de canción: transición
        if (target != shown || ls !== shownLines || np.title != shownTitle || np.artist != shownArtist) {
            val jump = target >= 0 && shown >= 0 && ls === shownLines && (target < shown || target > shown + 1)
            startTransition(target, jump, now)
            shown = target; shownLines = ls; shownTitle = np.title; shownArtist = np.artist
        }
        if (frame != null && target >= 0 &&
            (target != laidStanza || w != laidW || h != laidH || Prefs.cover != laidCover)) lay(frame.words, target, w, h)

        if (song && Prefs.cover == "Marca de agua") art(c, bigArt, w / 2 - 0.275f * min(w, h), h / 2 - 0.275f * min(w, h), 0.55f * min(w, h), 0.2f * (1 - heroP))
        val age = (now - t0) / 1000f
        trans?.let { if (age > Transitions.total(it, cur.n) + 0.1f) { trans = null; old.n = 0 } }
        val tp = trans
        // la vieja sigue en old.n hasta el final: Reconstelar sale de sus posiciones
        if (tp != null && old.n > 0 && age < Transitions.outTime(tp)) { leave(tp, age, w, h); drawStars(c, old, true) }
        if (frame != null && target >= 0) { arrive(frame, pos, now, age, w, h); drawStars(c, cur, false) } else cur.n = 0

        val loading = song && (np.lyricsState == NowPlaying.LyricsState.LOADING || np.lyricsState == NowPlaying.LyricsState.NONE)
        when {
            np.title.isEmpty() -> message(c, "Pon algo en YouTube Music", w, h)
            np.ad -> {} // anuncio: sin letra
            np.lyricsState == NowPlaying.LyricsState.OFFLINE -> message(c, "Sin conexión. La letra vuelve cuando vuelva internet.", w, h)
            loading -> breathe(c, now, w, h)
        }
        if (song) {
            if (heroP > 0f) drawHero(c, w, h, np.lyricsState != NowPlaying.LyricsState.FOUND)
            drawCard(c, w, h, 1 - heroP)
        }
        val busy = trans != null || loading || heroP != (if (heroWant) 1f else 0f)
        if ((np.playing && !np.ad) || busy) onWant()
    }

    /** Instrumental largo: más de 8 s desde la última palabra y más de 4 s hasta la siguiente (o intro/final). */
    private fun instrumental(f: Layout.Frame, pos: Long): Boolean {
        val aw = f.activeWord
        val next = if (aw + 1 < f.words.size) f.words[aw + 1].timeMs else stanzas.getOrNull(f.stanza + 1)?.get(0)?.timeMs
        return (next == null || next - pos > 4000) && (aw < 0 || pos - f.words[aw].timeMs > 8000)
    }

    private fun startTransition(target: Int, jump: Boolean, now: Long) {
        // lo que está en pantalla se va desde donde está (también si llega otra estrofa a mitad de transición)
        if (cur.n > 0) { val t = old; old = cur; cur = t; old.snapshot() }
        else if (trans.let { it == null || (now - t0) / 1000f >= Transitions.outTime(it) }) old.n = 0 // ya se fue
        cur.n = 0; laidStanza = -2
        if (target < 0 && old.n == 0) { trans = null; return }
        val seed = (NowPlaying.title.hashCode() * 31L + target) * 31 + shown
        val e = Beat.energy()
        val style = if (jump) Transitions.CUT else Transitions.pick(Prefs.transition, seed, e, prevStyle)
        if (!jump) prevStyle = style
        trans = Transitions.params(style, seed, e)
        t0 = now
    }

    /** Posiciones de la estrofa k (misma semilla = mismas posiciones). */
    private fun lay(ws: List<Layout.Word>, k: Int, w: Float, h: Float) {
        val cover = Prefs.cover
        val top: Float; val bottom: Float
        if (h > w) { top = 0.2f * h; bottom = 0.75f * h } // vertical: franja 20–75 %
        else { // horizontal: toda la pantalla menos la carátula
            top = if (cover == "Arriba") M * d + CARD_H * d else 0f
            bottom = if (cover == "Tarjeta") h - M * d - CARD_H * d else h
        }
        val n = min(ws.size, MAX)
        // minDist ≈ ancho de una palabra típica
        val pts = Layout.place(n, "${NowPlaying.key}#$k".hashCode().toLong(), w, bottom - top, 84 * d)
        for (i in 0 until n) { cur.tx[i] = pts[i].first; cur.ty[i] = top + pts[i].second }
        cur.act.fill(null); cur.sung.fill(null)
        cur.words = ws; cur.n = n
        laidStanza = k; laidW = w; laidH = h; laidCover = cover
    }

    private fun arrive(fr: Layout.Frame, pos: Long, now: Long, age: Float, w: Float, h: Float) {
        val ws = fr.words; val aw = fr.activeWord; val tp = trans
        val t = (now - born) / 1000f
        val lineStart = lines?.getOrNull(fr.activeLine)?.timeMs
        for (i in 0 until cur.n) {
            var kind = if (i < aw) 1 else if (i == aw) 2 else 0
            var r: Float; var sa: Float; var la = 0f; var ls = 1f
            when (kind) {
                2 -> { // activa: aparece con un pequeño rebote
                    val a = ((pos - ws[i].timeMs) / 200f).coerceIn(0f, 1f)
                    r = 9 * d * (0.6f + 0.4f * outBack(a)); sa = 1f; la = a; ls = 0.85f + 0.15f * a
                }
                1 -> { // cantada: 18sp al 45 %; los primeros 200 ms encoge desde la activa
                    val a = ((pos - ws[i + 1].timeMs) / 200f).coerceIn(0f, 1f)
                    r = 5 * d; sa = 0.8f
                    if (a < 1f) { kind = 3; ls = 1 - (1 - 18f / 26f) * a; la = 1 - 0.55f * a } else la = 0.45f
                }
                else -> { r = 3.5f * d; sa = 0.25f } // futura: solo estrella
            }
            if (lineStart != null && ws[i].line == fr.activeLine) { // realce de 250 ms al empezar línea
                val q = 1 - ((pos - lineStart) / 250f).coerceIn(0f, 1f)
                r *= 1 + 0.4f * q; sa = min(1f, sa + 0.5f * q)
            }
            sa *= 0.85f + 0.15f * sin(t * (1.3f + 0.4f * (i % 3)) + i * 1.7f) // parpadeo leve
            cur.kind[i] = kind
            if (tp != null) {
                val src = min(i, old.n - 1)
                Transitions.inState(tp, age, cur.tx[i], cur.ty[i], i, w, h,
                    if (src >= 0) old.tx[src] else 0f, if (src >= 0) old.ty[src] else 0f, src >= 0, o)
                cur.x[i] = o[0]; cur.y[i] = o[1]; r *= o[2]; ls *= o[2]; cur.f[i] = o[3]; sa *= o[3]; la *= o[4]; cur.trail[i] = o[5]
            } else { cur.x[i] = cur.tx[i]; cur.y[i] = cur.ty[i]; cur.f[i] = 1f; cur.trail[i] = 0f }
            cur.r[i] = r; cur.sa[i] = sa; cur.la[i] = la; cur.ls[i] = ls
        }
        cur.linked = min(aw + 1, cur.n)
        cur.grow = if (aw >= 0) ((pos - ws[aw].timeMs) / 350f).coerceIn(0f, 1f) else 1f
    }

    private fun leave(tp: Transitions.P, age: Float, w: Float, h: Float) {
        for (i in 0 until old.n) {
            Transitions.outState(tp, age, old.tx[i], old.ty[i], i, w, h, o)
            old.x[i] = o[0]; old.y[i] = o[1]; old.r[i] = old.br[i] * o[2]; old.ls[i] = old.bls[i] * o[2]
            old.sa[i] = old.bsa[i] * o[3]; old.f[i] = old.bf[i] * o[3]; old.la[i] = old.bla[i] * o[4]; old.trail[i] = o[5]
        }
    }

    private fun drawStars(c: Canvas, s: Stars, leaving: Boolean) {
        if (s.linked > 1) { // líneas entre palabras cantadas, con ~12dp libres alrededor de cada palabra
            c.save()
            val g = 12 * d
            for (i in 0 until s.linked) {
                val e = s.r[i] + g
                c.clipOutRect(s.x[i] - e, s.y[i] - e, s.x[i] + e, s.y[i] + e)
                if (s.la[i] > 0.01f && label(s, i) != null) c.clipOutRect(rf) // el Bitmap ya lleva 12dp de margen
            }
            for (i in 1 until s.linked) {
                val x0 = s.x[i - 1]; val y0 = s.y[i - 1]; var x1 = s.x[i]; var y1 = s.y[i]
                if (i == s.linked - 1 && s.grow < 1f) { // la última se traza hacia la palabra nueva
                    val e = 1 - (1 - s.grow) * (1 - s.grow) * (1 - s.grow); x1 = x0 + (x1 - x0) * e; y1 = y0 + (y1 - y0) * e
                }
                var a = 0.6f * min(s.f[i - 1], s.f[i])
                if (leaving) { // al irse, una línea que se estira más del doble se apaga (no cruza la pantalla)
                    val base = hypot(s.tx[i] - s.tx[i - 1], s.ty[i] - s.ty[i - 1]) + 1
                    a *= (2 - hypot(x1 - x0, y1 - y0) / base).coerceIn(0f, 1f)
                }
                if (a > 0.01f) { linePaint.color = accent; linePaint.alpha = (a * 255).toInt(); c.drawLine(x0, y0, x1, y1, linePaint) }
            }
            c.restore()
        }
        for (i in 0 until s.n) {
            val sa = s.sa[i].coerceIn(0f, 1f); val x = s.x[i]; val y = s.y[i]; val r = s.r[i]
            if (sa > 0.01f) {
                if (s.trail[i] > 1f) { // estela (lluvia)
                    linePaint.color = accent; linePaint.alpha = (0.5f * sa * 255).toInt(); c.drawLine(x, y - s.trail[i], x, y, linePaint)
                }
                if (s.kind[i] == 2) halo?.let { // halo del acento en la palabra activa
                    bmpPaint.alpha = (0.7f * sa * 255).toInt(); rf.set(x - 3 * r, y - 3 * r, x + 3 * r, y + 3 * r); c.drawBitmap(it, null, rf, bmpPaint)
                }
                starPaint.color = if (s.kind[i] == 1 || s.kind[i] == 3) accent else Color.WHITE
                starPaint.alpha = (sa * 255).toInt()
                c.save(); c.translate(x, y); c.scale(r, r); c.drawPath(star, starPaint); c.restore()
            }
            if (s.la[i] > 0.01f) label(s, i)?.let { bmpPaint.alpha = (min(1f, s.la[i]) * 255).toInt(); c.drawBitmap(it, null, rf, bmpPaint) }
        }
    }

    /** Bitmap del texto de la estrella i (creado la primera vez que hace falta) y su sitio en rf. */
    private fun label(s: Stars, i: Int): Bitmap? {
        val word = s.words.getOrNull(i)?.text ?: return null
        val b = when (s.kind[i]) {
            2, 3 -> s.act[i] ?: textBitmap(word, sp(26f), 600, Color.WHITE, accent, 0.9f * width).also { s.act[i] = it }
            1 -> s.sung[i] ?: textBitmap(word, sp(18f), 400, Color.WHITE, 0, 0.9f * width).also { s.sung[i] = it }
            else -> return null
        }
        val sc = s.ls[i]; val bw = b.width * sc; val bh = b.height * sc; val p = pad * sc
        val lo = bw / 2 - p + 8 * d; val hi = width - lo // que no se salga por los lados
        val cx = if (lo <= hi) s.x[i].coerceIn(lo, hi) else width / 2f
        val gap = s.r[i] + 4 * d
        val top = if (i % 2 == 0) s.y[i] - gap - bh + p else s.y[i] + gap - p // alterna encima / debajo
        rf.set(cx - bw / 2, top, cx + bw / 2, top + bh)
        return b
    }

    /** Buscando letra: constelación que respira. */
    private fun breathe(c: Canvas, now: Long, w: Float, h: Float) {
        val b = 0.5f + 0.5f * sin((now - born) / 1000f * TAU / 2.4f)
        val top = if (h > w) 0.2f * h else 0.15f * h; val bh = if (h > w) 0.55f * h else 0.5f * h
        linePaint.color = accent; linePaint.alpha = (20 + 50 * b).toInt()
        for (i in 1 until BX.size) c.drawLine(BX[i - 1] * w, top + BY[i - 1] * bh, BX[i] * w, top + BY[i] * bh, linePaint)
        starPaint.color = Color.WHITE; starPaint.alpha = ((0.3f + 0.5f * b) * 255).toInt()
        val r = (4 + 2 * b) * d
        for (i in BX.indices) { c.save(); c.translate(BX[i] * w, top + BY[i] * bh); c.scale(r, r); c.drawPath(star, starPaint); c.restore() }
    }

    private fun message(c: Canvas, text: String, w: Float, h: Float) {
        if (text !== msgText || w != msgW) { msgText = text; msgW = w; msgBmp = textBitmap(text, sp(17f), 400, Ui.TEXT2, 0, 0.8f * w, 3) }
        msgBmp?.let { centered(c, it, w / 2, h / 2 - (it.height - 2 * pad) / 2, 1f) }
    }

    /** Carátula grande (sin letra o instrumental largo) con título, artista, barra y pie. */
    private fun drawHero(c: Canvas, w: Float, h: Float, footerOn: Boolean) {
        val e = heroP * heroP * (3 - 2 * heroP)
        val side = heroSide(w, h); val s = side * (0.9f + 0.1f * e); val cx = w / 2; val cy = 0.4f * h
        halo?.let { bmpPaint.alpha = (0.35f * e * 255).toInt(); rf.set(cx - 0.8f * s, cy - 0.8f * s, cx + 0.8f * s, cy + 0.8f * s); c.drawBitmap(it, null, rf, bmpPaint) }
        art(c, bigArt, cx - s / 2, cy - s / 2, s, e)
        var y = cy + side / 2 + 16 * d
        heroTitle?.let { centered(c, it, cx, y, e); y += it.height - 2 * pad + 4 * d }
        heroArtist?.let { centered(c, it, cx, y, e); y += it.height - 2 * pad + 14 * d }
        bar(c, cx - side / 2, y, cx + side / 2, e)
        if (footerOn) footer?.let { centered(c, it, cx, h - 24 * d - (it.height - 2 * pad), e) }
    }

    /** Tarjeta abajo o arriba: carátula, título, artista y barra de progreso. */
    private fun drawCard(c: Canvas, w: Float, h: Float, alpha: Float) {
        val mode = Prefs.cover
        if (alpha <= 0.01f || (mode != "Tarjeta" && mode != "Arriba")) return
        val cw = cardW(w); val ch = CARD_H * d; val x = (w - cw) / 2
        val y = if (mode == "Arriba") M * d else h - M * d - ch
        fill.color = Ui.SURFACE; fill.alpha = (0.72f * alpha * 255).toInt()
        c.drawRoundRect(x, y, x + cw, y + ch, 20 * d, 20 * d, fill)
        art(c, smallArt, x + 12 * d, y + 12 * d, ART * d, alpha)
        val tx = x + (24 + ART) * d
        bmpPaint.alpha = (alpha * 255).toInt()
        cardTitle?.let { c.drawBitmap(it, tx - pad, y + 12 * d - pad, bmpPaint) }
        cardArtist?.let { c.drawBitmap(it, tx - pad, y + 35 * d - pad, bmpPaint) }
        bar(c, tx, y + ch - 17 * d, x + cw - 16 * d, alpha)
    }

    private fun bar(c: Canvas, x0: Float, y: Float, x1: Float, alpha: Float) {
        val dur = NowPlaying.durationMs
        if (dur <= 0 || x1 <= x0) return
        val prog = (NowPlaying.positionMs().toFloat() / dur).coerceIn(0f, 1f)
        val bh = 3 * d
        fill.color = Color.WHITE; fill.alpha = (0.18f * alpha * 255).toInt()
        c.drawRoundRect(x0, y, x1, y + bh, bh / 2, bh / 2, fill)
        fill.color = accent; fill.alpha = (0.9f * alpha * 255).toInt()
        c.drawRoundRect(x0, y, x0 + max(bh, (x1 - x0) * prog), y + bh, bh / 2, bh / 2, fill)
    }

    private fun art(c: Canvas, b: Bitmap?, x: Float, y: Float, s: Float, alpha: Float) {
        if (alpha <= 0.01f) return
        rf.set(x, y, x + s, y + s)
        if (b != null) { bmpPaint.alpha = (alpha * 255).toInt(); c.drawBitmap(b, null, rf, bmpPaint) }
        else { fill.color = accent; fill.alpha = (0.25f * alpha * 255).toInt(); c.drawRoundRect(rf, 0.06f * s, 0.06f * s, fill) }
    }

    private fun centered(c: Canvas, b: Bitmap, cx: Float, top: Float, alpha: Float) {
        bmpPaint.alpha = (alpha * 255).toInt()
        c.drawBitmap(b, cx - b.width / 2f, top - pad, bmpPaint)
    }

    private fun cardW(w: Float) = min(w - 2 * M * d, 420 * d)
    private fun heroSide(w: Float, h: Float) = min(0.42f * h, 0.62f * w)

    private fun syncColor() {
        if (NowPlaying.color == colorSrc && halo != null) return
        colorSrc = NowPlaying.color; accent = Ui.accent(colorSrc)
        val n = 64f
        halo = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888).also {
            Canvas(it).drawRect(0f, 0f, n, n, Paint().apply {
                shader = RadialGradient(n / 2, n / 2, n / 2, intArrayOf(accent, accent and 0x6EFFFFFF, accent and 0xFFFFFF),
                    floatArrayOf(0f, 0.45f, 1f), Shader.TileMode.CLAMP)
            })
        }
        cur.act.fill(null) // el halo del texto activo lleva el acento
    }

    private fun syncTexts(w: Float, h: Float) {
        val np = NowPlaying
        if (np.title != txTitle || np.artist != txArtist || w != txW) {
            txTitle = np.title; txArtist = np.artist; txW = w
            val cw = cardW(w) - (40 + ART) * d
            cardTitle = textBitmap(np.title, sp(16f), 600, Ui.TEXT, 0, cw)
            cardArtist = textBitmap(np.artist, sp(13f), 400, Ui.TEXT2, 0, cw)
            heroTitle = textBitmap(np.title, sp(22f), 600, Ui.TEXT, 0, 0.8f * w, 2)
            heroArtist = textBitmap(np.artist, sp(15f), 400, Ui.TEXT2, 0, 0.8f * w)
            footer = textBitmap("Esta canción va sin letra. Disfruta la luz.", sp(13f), 400, Ui.TEXT3, 0, 0.9f * w, 2)
        }
        val side = heroSide(w, h).toInt().coerceAtLeast(1)
        if (np.art !== artSrc || side != artSide) {
            artSrc = np.art; artSide = side
            smallArt = np.art?.let { rounded(it, (ART * d).toInt(), 10 * d) }
            bigArt = np.art?.let { rounded(it, side, 0.06f * side) }
        }
    }

    /** Recorte cuadrado con esquinas redondeadas. */
    private fun rounded(a: Bitmap, side: Int, radius: Float): Bitmap {
        val src = if (a.config == Bitmap.Config.HARDWARE) a.copy(Bitmap.Config.ARGB_8888, false) else a
        val s = min(src.width, src.height).toFloat()
        val sh = BitmapShader(src, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP).apply {
            setLocalMatrix(Matrix().apply { setScale(side / s, side / s); preTranslate(-(src.width - s) / 2, -(src.height - s) / 2) })
        }
        return Bitmap.createBitmap(side, side, Bitmap.Config.ARGB_8888).also {
            Canvas(it).drawRoundRect(0f, 0f, side.toFloat(), side.toFloat(), radius, radius,
                Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG).apply { shader = sh })
        }
    }

    /** Texto horneado en un Bitmap (con sombra y, si glow ≠ 0, halo de ese color); margen `pad` alrededor. */
    private fun textBitmap(s: String, px: Float, weight: Int, color: Int, glow: Int, maxW: Float, maxLines: Int = 1): Bitmap {
        val tp = TextPaint(Paint.ANTI_ALIAS_FLAG).apply { textSize = px; typeface = Ui.font(weight); this.color = color }
        val tw = min(ceil(tp.measureText(s)).toInt(), maxW.toInt()).coerceAtLeast(1)
        val sl = StaticLayout.Builder.obtain(s, 0, s.length, tp, tw).setAlignment(Alignment.ALIGN_CENTER)
            .setMaxLines(maxLines).setEllipsize(TextUtils.TruncateAt.END).setIncludePad(false).build()
        val p = pad.toInt()
        val b = Bitmap.createBitmap(tw + 2 * p, max(1, sl.height) + 2 * p, Bitmap.Config.ARGB_8888)
        val c = Canvas(b)
        c.translate(p.toFloat(), p.toFloat())
        tp.setShadowLayer(3 * d, 0f, d, 0x80000000.toInt()) // sombra para portadas claras
        sl.draw(c)
        if (glow != 0) { tp.setShadowLayer(10 * d, 0f, 0f, glow); sl.draw(c) }
        return b
    }

    private fun outBack(t: Float): Float { val k = 1.70158f; val u = t - 1; return 1 + (k + 1) * u * u * u + k * u * u }

    private companion object {
        const val MAX = Layout.MAX_WORDS
        const val M = 16f // margen de la tarjeta (dp)
        const val CARD_H = 80f
        const val ART = 56f
        const val TAU = 6.2831855f
        val BX = floatArrayOf(0.22f, 0.38f, 0.52f, 0.66f, 0.78f)
        val BY = floatArrayOf(0.55f, 0.3f, 0.6f, 0.35f, 0.65f)
    }
}
