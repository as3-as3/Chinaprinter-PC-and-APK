# MXW01 Printer — bloat‑free driver & apps

A tiny, **privacy‑respecting** alternative to the stock *FunPrint* app for the
**MXW01** mini thermal label printer.

The original app is ~185 MB and bundles **four ad/tracking networks** (ByteDance/Pangle,
TikTok, Google Ads, Facebook) plus cloud OCR and analytics. This project talks to the
printer **directly over Bluetooth** — no servers, no tracking, no ads, no cloud.

| | Stock FunPrint | This project |
|---|---|---|
| Size (Android) | ~185 MB | **5.9 MB** |
| Servers contacted | dozens (see [docs](docs/funprint_server_analyse.txt)) | **none** |
| Ads / trackers | 4 networks | **none** |
| Works offline | partly | **fully** |

> Reverse‑engineered from the BLE traffic of the original app. Not affiliated with
> the manufacturer. See [disclaimer](#disclaimer).

---

## What's included

- **`android/`** — native Kotlin app (minSdk 26 / Android 8+), no bloat
- **`pc/`** — Python program for Windows/Linux/macOS (GUI + command line)
- **`releases/`** — ready‑to‑use downloads:
  - `MXW01-Drucker.apk` — install on your phone
  - `MXW01-Drucker-Portable.zip` — standalone Windows program (no Python needed)
- **`docs/`** — protocol documentation & the server/tracking analysis of the original app

## Features (both apps)

- **Text** (multi‑line, adjustable font size)
- **QR codes** (with optional caption)
- **Barcodes** (Code128, EAN‑13, EAN‑8, Code39, UPC‑A, ITF)
- **Labels** (title + subtitle + optional QR)
- **Banner** (large text printed lengthwise)
- **Images / photos** (with Floyd–Steinberg dithering)
- **Adjustable density**, **copies**, **decorative frames**
- Live preview that shows the exact print result

## Compatibility

Confirmed on the **MXW01**. Other models of the same BLE family are likely compatible
but untested — see **[COMPATIBILITY.md](COMPATIBILITY.md)**.

---

## Install & use

### 📱 Android
1. Download `releases/MXW01-Drucker.apk` to your phone.
2. Tap it, allow "install from unknown sources" (normal for sideloaded apps).
3. Turn the printer on, tap **Connect**, allow the Bluetooth permission, print.

> Make sure the official FunPrint app is **disconnected** — it holds the BLE link.

### 🖥️ Windows (no install)
1. Download `releases/MXW01-Drucker-Portable.zip`, extract it.
2. Run `MXW01 Drucker.exe` (SmartScreen → *More info* → *Run anyway*).

### 🐍 PC from source (Windows / Linux / macOS)
```bash
cd pc
pip install -r requirements.txt
python gui.py                      # graphical UI
# or command line:
python mxw_printer.py text "Hello\nWorld"
python mxw_printer.py qr "https://example.com" "example.com"
python mxw_printer.py barcode "4006381333931" ean13
python mxw_printer.py banner "PARTY"
python mxw_printer.py image photo.png
#   options: --copies N  --density 1..200  --frame rund  --nodither
```

---

## Build from source

### Android (APK)
```bash
cd android
./gradlew assembleDebug          # Windows: gradlew.bat assembleDebug
# -> app/build/outputs/apk/debug/app-debug.apk
```
Requires a JDK 17+ and the Android SDK (set `sdk.dir` in `local.properties`,
or just open the folder in Android Studio).

### Windows .exe
```bash
cd pc
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --windowed --name "MXW01 Drucker" --icon icon.ico ^
  --collect-all bleak --collect-all barcode --collect-data qrcode ^
  --hidden-import PIL._tkinter_finder gui.py
```

---

## How it works

The MXW01 uses a custom BLE protocol (`2221` framing). Commands go to characteristic
`ae01`, responses arrive on `ae02`, and the raw bitmap is streamed to `ae03`.
Full details in **[docs/PROTOCOL.md](docs/PROTOCOL.md)**.

## Privacy

This software contacts **no servers whatsoever** — it only speaks Bluetooth to the
printer. For comparison, the analysis of what the original app reached out to is in
[docs/funprint_server_analyse.txt](docs/funprint_server_analyse.txt).

---

## Disclaimer & No Liability

This is an independent **interoperability** project, created by reverse‑engineering
the Bluetooth communication of a device the author owns. It is **not affiliated with,
endorsed by, or supported by** the printer's manufacturer or the FunPrint app.
Trademarks belong to their respective owners.

**The software and all downloadable files (APK, EXE, ZIP) are provided "AS IS",
without any warranty of any kind. You use them entirely at your own risk. To the
maximum extent permitted by law, the author accepts NO LIABILITY for any damage of
any kind — including but not limited to damage to your device, printer, or data, or
any direct, indirect, incidental or consequential loss — arising from the use of, or
inability to use, this code or the downloaded files.**

See **[DISCLAIMER.md](DISCLAIMER.md)** for the full text (English & Deutsch).

## License

[GPLv3](LICENSE) © 2026 **as3-as3**. The GPLv3 itself also disclaims warranty (sections 15–16).
