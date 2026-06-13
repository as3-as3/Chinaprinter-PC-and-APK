# Compatible Printers / Kompatible Drucker

This app talks to thermal label printers that use the **"2221" BLE protocol**
(the protocol used by the *FunPrint* app, `com.fun.mxw`). It was reverse‑engineered
on, and is **confirmed working** with, the **MXW01**.

> ⚠️ Only the MXW01 is verified. Other models below are *likely* compatible because
> they belong to the same BLE protocol family, but they are **untested**.
> If you try one, please [open an issue](../../issues) with the result – the list
> will be updated.

---

## ✅ Confirmed working

| Model | BLE name | Notes |
|-------|----------|-------|
| **MXW01** | `MXW01-XXXX` (also shown as `YHK-XXXX`) | Fully tested: text, QR, barcode, label, banner, image, density, copies, frames |

Print width: **384 dots (48 bytes)**.

---

## 🟡 Likely compatible (untested – feedback welcome)

These share the same vendor / BLE family (`ae30` service, `2221` commands) in the
FunPrint app. Good chance they work as‑is:

- MXW009
- BQ02, BQ03, BQ17
- BH03

---

## ❌ Not compatible

Printers that use a **different protocol** will *not* work with this app, e.g.:

- The **5178** variant of the YHK/MXW family (similar but different framing)
- ESC/POS‑based models (many Phomemo M‑series, and the V5 / V7 / V8 series in FunPrint)
- Any non‑BLE / Bluetooth‑Classic‑only printer

These would need their own protocol implementation.

---

## 🔎 How to check if *your* printer is compatible

Your printer is compatible if **all** of these are true:

1. It connects over **Bluetooth Low Energy (BLE)**.
2. It exposes the GATT **service `0000ae30-0000-1000-8000-00805f9b34fb`** with:
   - `ae01` – write (commands)
   - `ae02` – notify (responses)
   - `ae03` – write (bitmap data)
3. It answers the handshake `2221A70000000000` on `ae01`
   (the printer replies with a `2221A7…` packet on `ae02`).
4. Its print width is **384 dots**.

Easiest practical test:

- Install a BLE scanner (e.g. **nRF Connect**) and check for the `ae30` service, **or**
- Just install this app, hit **Connect**, and try a small text print.

If it works (or doesn't), please report your **model + BLE name** in an issue so we
can grow this list. 🙏
