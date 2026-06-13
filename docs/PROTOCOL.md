# MXW01 BLE Protocol (`2221`)

Reverse‑engineered from a btsnoop capture of the *FunPrint* app printing to an
**MXW01**. All command bytes below were verified byte‑for‑byte against the capture.

## GATT

Service `0000ae30-0000-1000-8000-00805f9b34fb`:

| Char | Properties | Use |
|------|-----------|-----|
| `ae01` | write‑without‑response | **commands** |
| `ae02` | notify | **responses / status** |
| `ae03` | write‑without‑response | **raw bitmap data** |

Request an MTU of ~247 and stream bitmap data to `ae03` in chunks (≤ MTU‑7).

## Packet framing

Two framings share the `22 21` prefix:

```
Query   commands (a1,a2,b1): 22 21 CMD 00 LEN_LO LEN_HI  DATA  CRC8(DATA)  FF
Control commands (a7,a9,ad): 22 21 CMD 00 LEN_LO LEN_HI  DATA  00 00
```

`LEN` is the little‑endian length of `DATA`. `CRC8` uses the polynomial table below.

## Print sequence

| Step | Bytes (example) | Meaning |
|------|-----------------|---------|
| 1 | `2221A70000000000` | A7 – handshake/wake (printer replies `2221A7…` auth token) |
| 2 | `2221B10001000000FF` | B1 – query firmware version |
| 3 | `2221A10001000000FF` | A1 – query status |
| 4 | `2221A2 00 0100 <density> <crc> FF` | A2 – set print density (1–200; `0x62`=98 default) |
| 5 | `2221A9 00 0400 <H_lo> <H_hi> 30 00 00 00` | A9 – **start print**; data = `[height_LE16][48_LE16]` |
| 6 | *(raw bitmap → `ae03`)* | `height × 48` bytes, streamed in MTU chunks |
| 7 | `2221AD000100000000` | AD – **end / execute print** |

Printer acknowledges A9 with `2221A90001000000` and signals completion with `2221AA…`.

## Bitmap format

- Width is fixed at **384 dots = 48 bytes** per row.
- 1 bit per pixel, **`1` = black**.
- **Bit order is LSB‑first**: pixel `x` → `byte[x/8] |= (1 << (x & 7))`.
  (MSB‑first produces a mirrored/ghosted image.)
- For photos, apply Floyd–Steinberg dithering before packing.

## CRC‑8 table

```
0,7,14,9,28,27,18,21,56,63,54,49,36,35,42,45, 112,119,126,121,108,107,98,101,72,79,70,65,84,83,90,93,
224,231,238,233,252,251,242,245,216,223,214,209,196,195,202,205, 144,151,158,153,140,139,130,133,168,175,166,161,180,179,186,189,
199,192,201,206,219,220,213,210,255,248,241,246,227,228,237,234, 183,176,185,190,171,172,165,162,143,136,129,134,147,148,157,154,
39,32,41,46,59,60,53,50,31,24,17,22,3,4,13,10, 87,80,89,94,75,76,69,66,111,104,97,102,115,116,125,122,
137,142,135,128,149,146,155,156,177,182,191,184,173,170,163,164, 249,254,247,240,229,226,235,236,193,198,207,200,221,218,211,212,
105,110,103,96,117,114,123,124,81,86,95,88,77,74,67,68, 25,30,23,16,5,2,11,12,33,38,47,40,61,58,51,52,
78,73,64,71,82,85,92,91,118,113,120,127,106,109,100,99, 62,57,48,55,34,37,44,43,6,1,8,15,26,29,20,19,
174,169,160,167,178,181,188,187,150,145,152,159,138,141,132,131, 222,217,208,215,194,197,204,203,230,225,232,239,250,253,244,243
```

```python
def crc8(data: bytes) -> int:
    t = 0
    for b in data:
        t = TABLE[(t ^ b) & 0xFF]
    return t
```

## Notes

- This is the **`2221`** variant. The same vendor also ships a **`5178`** variant
  (identical CRC table, different command prefix and a `D0`/`D1` start/stop pair).
- The handshake/version/status queries (A7/B1/A1) appear optional for printing but
  are sent for safety, mirroring the original app.
