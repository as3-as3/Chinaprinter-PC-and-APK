package com.mxw.printer

import android.annotation.SuppressLint
import android.bluetooth.*
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import java.util.ArrayDeque
import java.util.UUID

/**
 * BLE-Treiber für den MXW01 (2221-Protokoll), reverse-engineered aus FunPrint.
 * Kanäle: ae01 = Befehle, ae02 = Antworten (Notify), ae03 = Bitmap-Rohdaten.
 */
@SuppressLint("MissingPermission")
class BlePrinter(private val ctx: Context) {

    interface Listener {
        fun onStatus(msg: String)
        fun onConnected()
        fun onDisconnected()
        fun onPrintDone()
        fun onError(msg: String)
    }

    var listener: Listener? = null
    var density: Int = 98

    private val main = Handler(Looper.getMainLooper())
    private var gatt: BluetoothGatt? = null
    private var chWrite: BluetoothGattCharacteristic? = null   // ae01
    private var chData: BluetoothGattCharacteristic? = null    // ae03
    private var chNotify: BluetoothGattCharacteristic? = null  // ae02
    private var chunkSize = 180
    @Volatile private var connected = false
    private var scanner: android.bluetooth.le.BluetoothLeScanner? = null
    private var scanCb: ScanCallback? = null

    private val queue = ArrayDeque<Pair<BluetoothGattCharacteristic, ByteArray>>()

    companion object {
        private const val NAME = "MXW01"
        private val SERVICE = UUID.fromString("0000ae30-0000-1000-8000-00805f9b34fb")
        private val AE01 = UUID.fromString("0000ae01-0000-1000-8000-00805f9b34fb")
        private val AE02 = UUID.fromString("0000ae02-0000-1000-8000-00805f9b34fb")
        private val AE03 = UUID.fromString("0000ae03-0000-1000-8000-00805f9b34fb")
        private val CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

        private val CRC8 = intArrayOf(
            0,7,14,9,28,27,18,21,56,63,54,49,36,35,42,45,112,119,126,121,108,107,98,101,72,79,70,65,84,83,90,93,
            224,231,238,233,252,251,242,245,216,223,214,209,196,195,202,205,144,151,158,153,140,139,130,133,168,175,166,161,180,179,186,189,
            199,192,201,206,219,220,213,210,255,248,241,246,227,228,237,234,183,176,185,190,171,172,165,162,143,136,129,134,147,148,157,154,
            39,32,41,46,59,60,53,50,31,24,17,22,3,4,13,10,87,80,89,94,75,76,69,66,111,104,97,102,115,116,125,122,
            137,142,135,128,149,146,155,156,177,182,191,184,173,170,163,164,249,254,247,240,229,226,235,236,193,198,207,200,221,218,211,212,
            105,110,103,96,117,114,123,124,81,86,95,88,77,74,67,68,25,30,23,16,5,2,11,12,33,38,47,40,61,58,51,52,
            78,73,64,71,82,85,92,91,118,113,120,127,106,109,100,99,62,57,48,55,34,37,44,43,6,1,8,15,26,29,20,19,
            174,169,160,167,178,181,188,187,150,145,152,159,138,141,132,131,222,217,208,215,194,197,204,203,230,225,232,239,250,253,244,243)

        private fun crc8(data: ByteArray): Int {
            var t = 0
            for (b in data) t = CRC8[(t xor (b.toInt() and 0xFF)) and 0xFF]
            return t
        }
        /** Query-Befehl: 2221 CMD 00 LEN16 DATA crc8 FF */
        fun cmdQ(cmd: Int, data: ByteArray): ByteArray {
            val n = data.size
            return byteArrayOf(0x22, 0x21, cmd.toByte(), 0x00, (n and 0xFF).toByte(), ((n shr 8) and 0xFF).toByte()) +
                    data + byteArrayOf(crc8(data).toByte(), 0xFF.toByte())
        }
        /** Control-Befehl: 2221 CMD 00 LEN16 DATA 00 00 */
        fun cmdC(cmd: Int, data: ByteArray = ByteArray(0)): ByteArray {
            val n = data.size
            return byteArrayOf(0x22, 0x21, cmd.toByte(), 0x00, (n and 0xFF).toByte(), ((n shr 8) and 0xFF).toByte()) +
                    data + byteArrayOf(0x00, 0x00)
        }
    }

    private fun status(s: String) = main.post { listener?.onStatus(s) }
    private fun err(s: String) = main.post { listener?.onError(s) }

    val isConnected get() = connected

    // ── Scan + Verbindung ───────────────────────────────────────────────────
    fun connect() {
        val mgr = ctx.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = mgr.adapter
        if (adapter == null || !adapter.isEnabled) { err("Bluetooth ist aus."); return }
        scanner = adapter.bluetoothLeScanner
        status("Suche MXW01…")
        val cb = object : ScanCallback() {
            override fun onScanResult(type: Int, result: ScanResult) {
                val dev = result.device
                if (dev.name == NAME || result.scanRecord?.deviceName == NAME) {
                    scanner?.stopScan(this)
                    status("Gefunden, verbinde…")
                    gatt = dev.connectGatt(ctx, false, gattCb, BluetoothDevice.TRANSPORT_LE)
                }
            }
            override fun onScanFailed(errorCode: Int) { err("Scan fehlgeschlagen ($errorCode)") }
        }
        scanCb = cb
        scanner?.startScan(null, ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build(), cb)
        // Timeout
        main.postDelayed({
            if (!connected) { scanner?.stopScan(cb); if (gatt == null) err("MXW01 nicht gefunden. Eingeschaltet?") }
        }, 12000)
    }

    fun disconnect() {
        try { gatt?.disconnect(); gatt?.close() } catch (_: Exception) {}
        gatt = null; connected = false
        main.post { listener?.onDisconnected() }
    }

    private val gattCb = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, st: Int, newState: Int) {
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                status("Verbunden, suche Dienste…")
                g.discoverServices()
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                connected = false
                main.post { listener?.onDisconnected() }
            }
        }

        override fun onServicesDiscovered(g: BluetoothGatt, st: Int) {
            val svc = g.getService(SERVICE)
            if (svc == null) { err("Drucker-Dienst nicht gefunden."); return }
            chWrite = svc.getCharacteristic(AE01)
            chData = svc.getCharacteristic(AE03)
            chNotify = svc.getCharacteristic(AE02)
            if (chWrite == null || chData == null || chNotify == null) { err("Kanäle fehlen."); return }
            g.requestMtu(247)
        }

        override fun onMtuChanged(g: BluetoothGatt, mtu: Int, st: Int) {
            chunkSize = (mtu - 7).coerceIn(20, 240)
            // Notify aktivieren
            val ch = chNotify!!
            g.setCharacteristicNotification(ch, true)
            val d = ch.getDescriptor(CCCD)
            if (d != null) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    g.writeDescriptor(d, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                } else {
                    @Suppress("DEPRECATION") run {
                        d.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                        @Suppress("DEPRECATION") g.writeDescriptor(d)
                    }
                }
            } else { ready() }
        }

        override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, st: Int) {
            ready()
        }

        override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, st: Int) {
            // Nächsten Eintrag der Warteschlange senden
            synchronized(queue) {
                if (queue.isNotEmpty()) queue.poll()
                if (queue.isEmpty()) { main.post { listener?.onPrintDone() } }
                else drainLocked()
            }
        }

        @Deprecated("Deprecated in Java")
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
            // Antworten des Druckers (Status/Flow) — derzeit nur ignoriert/loggen
        }
    }

    private fun ready() {
        connected = true
        main.post { listener?.onConnected() }
        status("Bereit.")
    }

    // ── Drucken ───────────────────────────────────────────────────────────
    fun print(raster: ByteArray, height: Int, copies: Int) {
        val w = chWrite; val d = chData
        if (!connected || w == null || d == null) { err("Nicht verbunden."); return }
        val h = height
        val a9 = cmdC(0xA9, byteArrayOf(
            (h and 0xFF).toByte(), ((h shr 8) and 0xFF).toByte(),
            (Render.WIDTH_BYTES and 0xFF).toByte(), 0x00))
        synchronized(queue) {
            queue.clear()
            repeat(copies.coerceAtLeast(1)) {
                queue.add(w to cmdC(0xA7))
                queue.add(w to cmdQ(0xB1, byteArrayOf(0)))
                queue.add(w to cmdQ(0xA1, byteArrayOf(0)))
                queue.add(w to cmdQ(0xA2, byteArrayOf(density.coerceIn(1, 200).toByte())))
                queue.add(w to a9)
                var i = 0
                while (i < raster.size) {
                    val end = minOf(i + chunkSize, raster.size)
                    queue.add(d to raster.copyOfRange(i, end))
                    i = end
                }
                queue.add(w to cmdC(0xAD, byteArrayOf(0)))
            }
            status("Drucke…")
            drainLocked()
        }
    }

    private fun drainLocked() {
        val head = queue.peek() ?: return
        doWrite(head.first, head.second)
    }

    private fun doWrite(ch: BluetoothGattCharacteristic, data: ByteArray) {
        val g = gatt ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            g.writeCharacteristic(ch, data, BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE)
        } else {
            @Suppress("DEPRECATION") run {
                ch.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
                ch.value = data
                @Suppress("DEPRECATION") g.writeCharacteristic(ch)
            }
        }
    }
}
