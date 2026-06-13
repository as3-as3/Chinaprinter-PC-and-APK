package com.mxw.printer

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import android.widget.AdapterView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.mxw.printer.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity(), BlePrinter.Listener {

    private lateinit var b: ActivityMainBinding
    private lateinit var printer: BlePrinter
    private var pickedBitmap: Bitmap? = null

    private val modes = listOf("Text", "QR-Code", "Barcode", "Etikett", "Banner", "Bild")

    private val pickImage = registerForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            try {
                contentResolver.openInputStream(uri).use { pickedBitmap = BitmapFactory.decodeStream(it) }
                b.txtImgPath.text = uri.lastPathSegment ?: "Bild gewählt"
                updatePreview()
            } catch (e: Exception) { toast("Bild-Fehler: ${e.message}") }
        }
    }

    private val reqPerms = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { res ->
        if (res.values.all { it }) printer.connect()
        else toast("Bluetooth-Berechtigung nötig.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)

        printer = BlePrinter(this).also { it.listener = this }

        b.spMode.adapter = spinnerAdapter(modes)
        b.spBcType.adapter = spinnerAdapter(Render.BARCODE_TYPES)
        b.spFrame.adapter = spinnerAdapter(Render.FRAME_STYLES)

        b.spMode.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) { showGroup(pos); updatePreview() }
            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
        val rerender = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) { updatePreview() }
            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
        b.spBcType.onItemSelectedListener = rerender
        b.spFrame.onItemSelectedListener = rerender

        b.sbDensity.setOnSeekBarChangeListener(simpleSeek { b.txtDensity.text = "Dichte: ${b.sbDensity.progress.coerceAtLeast(1)}" })
        b.sbFont.setOnSeekBarChangeListener(simpleSeek { updatePreview() })
        b.rbDown.setOnClickListener { updatePreview() }
        b.rbUp.setOnClickListener { updatePreview() }
        b.cbDither.setOnClickListener { updatePreview() }

        b.btnPickImage.setOnClickListener { pickImage.launch("image/*") }
        b.btnPreview.setOnClickListener { updatePreview() }
        b.btnConnect.setOnClickListener { toggleConnect() }
        b.btnPrint.setOnClickListener { doPrint() }

        showGroup(0)
        b.root.post { updatePreview() }
    }

    // ── UI-Helfer ────────────────────────────────────────────────────────────
    private fun spinnerAdapter(items: List<String>) =
        ArrayAdapter(this, R.layout.spinner_item, items).also { it.setDropDownViewResource(R.layout.spinner_item) }

    private fun showGroup(mode: Int) {
        b.grpText.visibility = if (mode == 0) View.VISIBLE else View.GONE
        b.grpQr.visibility = if (mode == 1) View.VISIBLE else View.GONE
        b.grpBarcode.visibility = if (mode == 2) View.VISIBLE else View.GONE
        b.grpLabel.visibility = if (mode == 3) View.VISIBLE else View.GONE
        b.grpBanner.visibility = if (mode == 4) View.VISIBLE else View.GONE
        b.grpImage.visibility = if (mode == 5) View.VISIBLE else View.GONE
    }

    private fun simpleSeek(onChange: () -> Unit) = object : android.widget.SeekBar.OnSeekBarChangeListener {
        override fun onProgressChanged(s: android.widget.SeekBar?, p: Int, fromUser: Boolean) { onChange() }
        override fun onStartTrackingTouch(s: android.widget.SeekBar?) {}
        override fun onStopTrackingTouch(s: android.widget.SeekBar?) {}
    }

    private fun toast(m: String) = android.widget.Toast.makeText(this, m, android.widget.Toast.LENGTH_SHORT).show()

    // ── Bild-Erzeugung ───────────────────────────────────────────────────────
    private fun buildSource(): Bitmap? = try {
        when (b.spMode.selectedItemPosition) {
            0 -> Render.text(b.etText.text.toString(), b.sbFont.progress.coerceAtLeast(14).toFloat())
            1 -> Render.qr(b.etQrData.text.toString(), b.etQrLabel.text.toString().ifBlank { null })
            2 -> Render.barcode(b.etBcData.text.toString(), b.spBcType.selectedItem as String)
            3 -> Render.label(b.etLblTitle.text.toString(), b.etLblSub.text.toString(),
                              b.etLblQr.text.toString().ifBlank { null })
            4 -> Render.banner(b.etBanner.text.toString(), b.rbUp.isChecked)
            5 -> pickedBitmap
            else -> null
        }
    } catch (e: Exception) { toast("Fehler: ${e.message}"); null }

    private fun buildFinal(): Bitmap? {
        val src = buildSource() ?: return null
        val style = b.spFrame.selectedItem as String
        return if (b.spMode.selectedItemPosition != 4 && style != "kein") Render.frame(src, style) else src
    }

    private fun isImageDither() = b.spMode.selectedItemPosition == 5 && b.cbDither.isChecked

    private fun updatePreview() {
        val img = buildFinal() ?: run { b.imgPreview.setImageBitmap(null); return }
        val (raster, h) = Render.toRaster(img, isImageDither())
        b.imgPreview.setImageBitmap(Render.rasterToBitmap(raster, h))
    }

    // ── Verbindung & Druck ─────────────────────────────────────────────────
    private fun neededPerms(): Array<String> =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
        else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)

    private fun toggleConnect() {
        if (printer.isConnected) { printer.disconnect(); return }
        val missing = neededPerms().any { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (missing) reqPerms.launch(neededPerms()) else printer.connect()
    }

    private fun doPrint() {
        if (!printer.isConnected) { toast("Bitte zuerst verbinden."); return }
        val img = buildFinal() ?: run { toast("Nichts zu drucken."); return }
        val copies = b.etCopies.text.toString().toIntOrNull()?.coerceIn(1, 99) ?: 1
        printer.density = b.sbDensity.progress.coerceIn(1, 200)
        val (raster, h) = Render.toRaster(img, isImageDither())
        printer.print(raster, h, copies)
    }

    // ── BlePrinter.Listener ──────────────────────────────────────────────────
    override fun onStatus(msg: String) { b.txtStatus.text = msg }
    override fun onConnected() {
        b.txtStatus.text = "verbunden"
        b.txtStatus.setTextColor(ContextCompat.getColor(this, R.color.ok))
        b.btnConnect.text = "Trennen"
    }
    override fun onDisconnected() {
        b.txtStatus.text = "getrennt"
        b.txtStatus.setTextColor(ContextCompat.getColor(this, R.color.err))
        b.btnConnect.text = "Verbinden"
    }
    override fun onPrintDone() { toast("Druck fertig ✓"); b.txtStatus.text = "Bereit." }
    override fun onError(msg: String) {
        b.txtStatus.text = msg
        b.txtStatus.setTextColor(ContextCompat.getColor(this, R.color.err))
    }

    override fun onDestroy() { super.onDestroy(); printer.disconnect() }
}
