package com.mxw.printer

import android.graphics.*
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.MultiFormatWriter
import com.google.zxing.qrcode.QRCodeWriter
import kotlin.math.max
import kotlin.math.roundToInt

/** Bitmap-Erzeugung für den MXW01 (384 Dots breit). */
object Render {
    const val WIDTH_DOTS = 384
    const val WIDTH_BYTES = 48

    val FRAME_STYLES = listOf("kein", "solid", "doppelt", "gestrichelt", "gepunktet", "rund", "zierrahmen")
    val BARCODE_TYPES = listOf("code128", "ean13", "ean8", "code39", "upca", "itf")

    // ── Text ──────────────────────────────────────────────────────────────
    fun text(content: String, fontSize: Float, bold: Boolean = false): Bitmap {
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.BLACK
            textSize = fontSize
            typeface = Typeface.create(Typeface.SANS_SERIF, if (bold) Typeface.BOLD else Typeface.NORMAL)
        }
        val lines = if (content.isEmpty()) listOf(" ") else content.split("\n")
        val fm = paint.fontMetrics
        val lineH = fm.descent - fm.ascent + 6f
        val h = (lineH * lines.size + 16f).toInt().coerceAtLeast(32)
        val bmp = Bitmap.createBitmap(WIDTH_DOTS, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp); c.drawColor(Color.WHITE)
        var y = 8f - fm.ascent
        for (ln in lines) { c.drawText(ln, 8f, y, paint); y += lineH }
        return bmp
    }

    // ── QR ────────────────────────────────────────────────────────────────
    fun qr(data: String, label: String?): Bitmap {
        val target = 256
        val hints = mapOf(EncodeHintType.MARGIN to 1)
        val m = QRCodeWriter().encode(data.ifEmpty { " " }, BarcodeFormat.QR_CODE, target, target, hints)
        val qr = Bitmap.createBitmap(target, target, Bitmap.Config.ARGB_8888)
        for (y in 0 until target) for (x in 0 until target)
            qr.setPixel(x, y, if (m[x, y]) Color.BLACK else Color.WHITE)
        val extra = if (label.isNullOrEmpty()) null else text(label, 24f)
        val h = target + (extra?.height ?: 0)
        val out = Bitmap.createBitmap(WIDTH_DOTS, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(out); c.drawColor(Color.WHITE)
        c.drawBitmap(qr, ((WIDTH_DOTS - target) / 2).toFloat(), 0f, null)
        if (extra != null) c.drawBitmap(extra, 0f, target.toFloat(), null)
        return out
    }

    // ── Barcode ───────────────────────────────────────────────────────────
    fun barcode(data: String, type: String): Bitmap {
        val fmt = when (type) {
            "ean13" -> BarcodeFormat.EAN_13
            "ean8" -> BarcodeFormat.EAN_8
            "code39" -> BarcodeFormat.CODE_39
            "upca" -> BarcodeFormat.UPC_A
            "itf" -> BarcodeFormat.ITF
            else -> BarcodeFormat.CODE_128
        }
        val bw = WIDTH_DOTS - 40
        val bh = 150
        val hints = mapOf(EncodeHintType.MARGIN to 4)
        val m = MultiFormatWriter().encode(data, fmt, bw, bh, hints)
        val mw = m.width; val mh = m.height
        val bars = Bitmap.createBitmap(mw, mh, Bitmap.Config.ARGB_8888)
        for (y in 0 until mh) for (x in 0 until mw)
            bars.setPixel(x, y, if (m[x, y]) Color.BLACK else Color.WHITE)
        // Klartext darunter
        val txt = text(data, 30f)
        val gap = 8
        val out = Bitmap.createBitmap(WIDTH_DOTS, mh + gap + txt.height, Bitmap.Config.ARGB_8888)
        val c = Canvas(out); c.drawColor(Color.WHITE)
        c.drawBitmap(bars, ((WIDTH_DOTS - mw) / 2).toFloat(), 0f, null)
        // Klartext zentrieren
        val tp = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; textSize = 30f }
        val tw = tp.measureText(data)
        c.drawText(data, (WIDTH_DOTS - tw) / 2, (mh + gap - tp.fontMetrics.ascent), tp)
        return out
    }

    // ── Etikett ───────────────────────────────────────────────────────────
    fun label(title: String, subtitle: String, qrData: String?): Bitmap {
        val titleBmp = text(title, 40f, bold = true)
        val subBmp = if (subtitle.isEmpty()) null else text(subtitle, 26f)
        var totalH = titleBmp.height + (subBmp?.height ?: 0) + 12
        if (!qrData.isNullOrEmpty()) totalH = max(totalH, 160)
        val out = Bitmap.createBitmap(WIDTH_DOTS, totalH, Bitmap.Config.ARGB_8888)
        val c = Canvas(out); c.drawColor(Color.WHITE)
        var y = 0
        c.drawBitmap(titleBmp, 4f, y.toFloat(), null); y += titleBmp.height + 6
        if (subBmp != null) { c.drawBitmap(subBmp, 4f, y.toFloat(), null) }
        if (!qrData.isNullOrEmpty()) {
            val hints = mapOf(EncodeHintType.MARGIN to 1)
            val m = QRCodeWriter().encode(qrData, BarcodeFormat.QR_CODE, 150, 150, hints)
            val q = Bitmap.createBitmap(150, 150, Bitmap.Config.ARGB_8888)
            for (yy in 0 until 150) for (xx in 0 until 150)
                q.setPixel(xx, yy, if (m[xx, yy]) Color.BLACK else Color.WHITE)
            c.drawBitmap(q, (WIDTH_DOTS - 158).toFloat(), 4f, null)
        }
        return out
    }

    // ── Banner (großer Text, 90° gedreht) ──────────────────────────────────
    fun banner(content: String, directionUp: Boolean): Bitmap {
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.BLACK; textSize = 300f
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        }
        val txt = content.ifEmpty { "BANNER" }
        val bounds = Rect(); paint.getTextBounds(txt, 0, txt.length, bounds)
        val pad = 30
        val fm = paint.fontMetrics
        val hw = bounds.width() + 2 * pad
        val hh = (fm.descent - fm.ascent).toInt() + 2 * pad
        val horiz = Bitmap.createBitmap(hw.coerceAtLeast(1), hh.coerceAtLeast(1), Bitmap.Config.ARGB_8888)
        val hc = Canvas(horiz); hc.drawColor(Color.WHITE)
        hc.drawText(txt, (pad - bounds.left).toFloat(), (pad - fm.ascent), paint)
        // 90° drehen
        val mtx = Matrix(); mtx.postRotate(if (directionUp) -90f else 90f)
        val rot = Bitmap.createBitmap(horiz, 0, 0, horiz.width, horiz.height, mtx, true)
        // auf Druckbreite skalieren
        val nh = max(1, (rot.height.toDouble() * WIDTH_DOTS / rot.width).roundToInt())
        return Bitmap.createScaledBitmap(rot, WIDTH_DOTS, nh, true)
    }

    // ── Zierrahmen ──────────────────────────────────────────────────────────
    fun frame(src: Bitmap, fstyle: String): Bitmap {
        if (fstyle == "kein" || fstyle.isEmpty()) return src
        val pad = 18
        val innerW = WIDTH_DOTS - 2 * pad - 12
        val scaled = if (src.width != innerW) {
            val nh = max(1, (src.height.toDouble() * innerW / src.width).roundToInt())
            Bitmap.createScaledBitmap(src, innerW, nh, true)
        } else src
        val h = scaled.height + 2 * pad + 12
        val out = Bitmap.createBitmap(WIDTH_DOTS, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(out); c.drawColor(Color.WHITE)
        c.drawBitmap(scaled, (pad + 6).toFloat(), (pad + 6).toFloat(), null)
        val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK; style = Paint.Style.STROKE; strokeWidth = 3f }
        val m = 5f
        val l = m; val t = m; val r = WIDTH_DOTS - 1 - m; val b = h - 1 - m
        when (fstyle) {
            "solid" -> c.drawRect(l, t, r, b, p)
            "doppelt" -> { c.drawRect(l, t, r, b, p); c.drawRect(l + 6, t + 6, r - 6, b - 6, p) }
            "rund" -> c.drawRoundRect(l, t, r, b, 22f, 22f, p)
            "gestrichelt" -> {
                p.pathEffect = DashPathEffect(floatArrayOf(14f, 9f), 0f)
                c.drawRect(l, t, r, b, p)
            }
            "gepunktet" -> {
                val pf = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK }
                var x = l; while (x <= r) { c.drawCircle(x, t, 3f, pf); c.drawCircle(x, b, 3f, pf); x += 11 }
                var y = t; while (y <= b) { c.drawCircle(l, y, 3f, pf); c.drawCircle(r, y, 3f, pf); y += 11 }
            }
            "zierrahmen" -> {
                p.strokeWidth = 2f
                c.drawRoundRect(l, t, r, b, 20f, 20f, p)
                val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.BLACK }
                for (cx in floatArrayOf(l, r)) for (cy in floatArrayOf(t, b)) {
                    c.drawCircle(cx, cy, 7f, fill)
                    c.drawCircle(cx, cy, 13f, p)
                }
            }
        }
        return out
    }

    // ── Rohdaten -> Bitmap (für exakte Vorschau) ────────────────────────────
    fun rasterToBitmap(raster: ByteArray, height: Int): Bitmap {
        val bmp = Bitmap.createBitmap(WIDTH_DOTS, height.coerceAtLeast(1), Bitmap.Config.ARGB_8888)
        val px = IntArray(WIDTH_DOTS * height)
        for (y in 0 until height) for (x in 0 until WIDTH_DOTS) {
            val bit = (raster[y * WIDTH_BYTES + (x ushr 3)].toInt() shr (x and 7)) and 1
            px[y * WIDTH_DOTS + x] = if (bit == 1) Color.BLACK else Color.WHITE
        }
        bmp.setPixels(px, 0, WIDTH_DOTS, 0, 0, WIDTH_DOTS, height)
        return bmp
    }

    // ── Bitmap -> rohe Druckdaten (LSB-first, 1=schwarz) ────────────────────
    fun toRaster(src: Bitmap, dither: Boolean): Pair<ByteArray, Int> {
        var bmp = src
        if (bmp.width != WIDTH_DOTS) {
            val nh = max(1, (bmp.height.toDouble() * WIDTH_DOTS / bmp.width).roundToInt())
            bmp = Bitmap.createScaledBitmap(bmp, WIDTH_DOTS, nh, true)
        }
        val w = WIDTH_DOTS; val h = bmp.height
        val pixels = IntArray(w * h); bmp.getPixels(pixels, 0, w, 0, 0, w, h)
        val gray = IntArray(w * h)
        for (i in pixels.indices) {
            val p = pixels[i]
            val a = (p ushr 24) and 0xFF
            var r = (p ushr 16) and 0xFF; var g = (p ushr 8) and 0xFF; var bl = p and 0xFF
            if (a < 255) { val af = a / 255f; r = (r * af + 255 * (1 - af)).toInt(); g = (g * af + 255 * (1 - af)).toInt(); bl = (bl * af + 255 * (1 - af)).toInt() }
            gray[i] = (0.299 * r + 0.587 * g + 0.114 * bl).toInt()
        }
        val out = ByteArray(WIDTH_BYTES * h)
        fun setBit(x: Int, y: Int) {
            val idx = y * WIDTH_BYTES + (x ushr 3)
            out[idx] = (out[idx].toInt() or (1 shl (x and 7))).toByte()
        }
        if (dither) {
            for (y in 0 until h) for (x in 0 until w) {
                val idx = y * w + x
                val old = gray[idx].coerceIn(0, 255)
                val nv = if (old < 128) 0 else 255
                val err = old - nv
                if (nv == 0) setBit(x, y)
                if (x + 1 < w) gray[idx + 1] += err * 7 / 16
                if (y + 1 < h) {
                    if (x > 0) gray[idx + w - 1] += err * 3 / 16
                    gray[idx + w] += err * 5 / 16
                    if (x + 1 < w) gray[idx + w + 1] += err * 1 / 16
                }
            }
        } else {
            for (y in 0 until h) for (x in 0 until w)
                if (gray[y * w + x] < 128) setBit(x, y)
        }
        return Pair(out, h)
    }
}
