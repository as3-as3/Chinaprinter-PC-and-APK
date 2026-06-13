"""
MXW01 / YHK Thermal Label Printer - BLE Driver (2221-Protokoll)
================================================================
Reverse-engineered aus echtem btsnoop-Mitschnitt der FunPrint-App.

KANÄLE:
  ae01 (write-no-resp)  -> Befehle senden
  ae02 (notify)         -> Antworten/Status empfangen
  ae03 (write-no-resp)  -> rohe Bitmap-Daten

PAKET-FRAMING:
  Query-Befehle (a1,a2,b1):  2221 CMD 00 LEN_LO LEN_HI DATA crc8(DATA) FF
  Control-Befehle (a7,a9,ad): 2221 CMD 00 LEN_LO LEN_HI DATA 00 00

DRUCK-SEQUENZ:
  1. A7  2221a70000000000              (Handshake/Wake)
  2. B1  2221b10001000000ff            (Firmware-Version abfragen)
  3. A1  2221a10001000000ff            (Status abfragen)
  4. A2  2221a2 00 0100 [dichte] crc ff (Druckdichte/Energie setzen)
  5. A9  2221a9 00 0400 [H_lo H_hi 30 00] 00 00  (Print-Start, H=Zeilen, 48 B/Zeile)
  6. ROHE BITMAP -> ae03               (H*48 bytes, in MTU-Chunks)
  7. AD  2221ad000100000000            (Print-Ende/Ausführen)

DRUCKBREITE: 48 Bytes = 384 Dots
"""
import asyncio
from bleak import BleakScanner, BleakClient
from PIL import Image, ImageDraw, ImageFont
import qrcode
import barcode as _barcode
from barcode.writer import ImageWriter

# ─── GATT ────────────────────────────────────────────────────────────────────
TARGET_NAME = "MXW01"
ADDRESS     = "48:0F:57:27:63:C9"
CMD_UUID    = "0000ae01-0000-1000-8000-00805f9b34fb"   # Befehle
NOTIFY_UUID = "0000ae02-0000-1000-8000-00805f9b34fb"   # Antworten
DATA_UUID   = "0000ae03-0000-1000-8000-00805f9b34fb"   # Bitmap-Rohdaten

WIDTH_BYTES = 48          # 384 Dots
WIDTH_DOTS  = WIDTH_BYTES * 8
CHUNK       = 240         # Bulk-Chunk-Größe für ae03

# Druckdichte (A2-Befehl). Gültig 1-200; Presets:
DENSITY_LIGHT  = 70
DENSITY_MEDIUM = 98       # = 0x62 (Wert aus echtem Mitschnitt)
DENSITY_DARK   = 130
DENSITY        = DENSITY_MEDIUM

# ─── CRC8 (verifiziert gegen echte Befehle) ──────────────────────────────────
_CRC8 = [
    0,7,14,9,28,27,18,21,56,63,54,49,36,35,42,45,112,119,126,121,108,107,98,101,72,79,70,65,84,83,90,93,
    224,231,238,233,252,251,242,245,216,223,214,209,196,195,202,205,144,151,158,153,140,139,130,133,168,175,166,161,180,179,186,189,
    199,192,201,206,219,220,213,210,255,248,241,246,227,228,237,234,183,176,185,190,171,172,165,162,143,136,129,134,147,148,157,154,
    39,32,41,46,59,60,53,50,31,24,17,22,3,4,13,10,87,80,89,94,75,76,69,66,111,104,97,102,115,116,125,122,
    137,142,135,128,149,146,155,156,177,182,191,184,173,170,163,164,249,254,247,240,229,226,235,236,193,198,207,200,221,218,211,212,
    105,110,103,96,117,114,123,124,81,86,95,88,77,74,67,68,25,30,23,16,5,2,11,12,33,38,47,40,61,58,51,52,
    78,73,64,71,82,85,92,91,118,113,120,127,106,109,100,99,62,57,48,55,34,37,44,43,6,1,8,15,26,29,20,19,
    174,169,160,167,178,181,188,187,150,145,152,159,138,141,132,131,222,217,208,215,194,197,204,203,230,225,232,239,250,253,244,243,
]
def crc8(data: bytes) -> int:
    t = 0
    for b in data:
        t = _CRC8[(t ^ b) & 0xFF]
    return t

def cmd_q(cmd: int, data: bytes) -> bytes:
    """Query-Befehl: 2221 CMD 00 LEN16 DATA crc8 FF"""
    n = len(data)
    return bytes([0x22, 0x21, cmd, 0x00, n & 0xFF, (n >> 8) & 0xFF]) + data + bytes([crc8(data), 0xFF])

def cmd_c(cmd: int, data: bytes = b"") -> bytes:
    """Control-Befehl: 2221 CMD 00 LEN16 DATA 00 00"""
    n = len(data)
    return bytes([0x22, 0x21, cmd, 0x00, n & 0xFF, (n >> 8) & 0xFF]) + data + bytes([0x00, 0x00])

# Vorgefertigte Befehle
C_A7  = cmd_c(0xA7)                     # 2221a70000000000
C_B1  = cmd_q(0xB1, b'\x00')           # 2221b10001000000ff
C_A1  = cmd_q(0xA1, b'\x00')           # 2221a10001000000ff
C_A2  = cmd_q(0xA2, bytes([DENSITY]))  # 2221a2 00 0100 62 29 ff
C_AD  = cmd_c(0xAD, b'\x00')           # 2221ad000100000000

def c_a2(density: int) -> bytes:
    """Druckdichte-Befehl (1-200)."""
    d = max(1, min(200, int(density)))
    return cmd_q(0xA2, bytes([d]))

def c_a9(height: int) -> bytes:
    """Print-Start: data = [height_LE16][WIDTH_BYTES_LE16]"""
    data = bytes([height & 0xFF, (height >> 8) & 0xFF, WIDTH_BYTES & 0xFF, (WIDTH_BYTES >> 8) & 0xFF])
    return cmd_c(0xA9, data)

# ─── Bild -> Bitmap ──────────────────────────────────────────────────────────
def img_to_raster(img: Image.Image, threshold: int = 128, dither: bool = False) -> tuple[bytes, int]:
    """PIL-Image -> rohe Bitmap (LSB=links, 1=schwarz). Gibt (bytes, height).
    dither=True: Floyd-Steinberg-Fehlerdiffusion (ideal für Fotos/Farbbilder).
    dither=False: harter Schwellwert (ideal für Text/QR/Barcode/Strichgrafik)."""
    img = img.convert("L")
    w, h = img.size
    # Auf Druckbreite skalieren falls nötig
    if w != WIDTH_DOTS:
        new_h = max(1, round(h * WIDTH_DOTS / w))
        img = img.resize((WIDTH_DOTS, new_h), Image.LANCZOS)
        w, h = img.size
    if dither:
        # convert("1") nutzt Floyd-Steinberg; 0=schwarz, 255=weiß
        bw = img.convert("1", dither=Image.FLOYDSTEINBERG)
        px = bw.load()
        out = bytearray(WIDTH_BYTES * h)
        for y in range(h):
            base = y * WIDTH_BYTES
            for x in range(WIDTH_DOTS):
                if px[x, y] == 0:
                    out[base + (x >> 3)] |= (0x01 << (x & 7))
        return bytes(out), h
    px = img.load()
    out = bytearray(WIDTH_BYTES * h)
    for y in range(h):
        base = y * WIDTH_BYTES
        for x in range(WIDTH_DOTS):
            if px[x, y] < threshold:
                # Drucker liest LSB-first: Bit 0 = linkes Pixel
                out[base + (x >> 3)] |= (0x01 << (x & 7))
    return bytes(out), h

def text_to_image(text: str, font_size: int = 32) -> Image.Image:
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    dummy = Image.new("L", (WIDTH_DOTS, 1000), 255)
    bbox = ImageDraw.Draw(dummy).multiline_textbbox((0, 0), text, font=font, spacing=6)
    h = bbox[3] - bbox[1] + 24
    img = Image.new("L", (WIDTH_DOTS, max(h, 32)), 255)
    ImageDraw.Draw(img).multiline_text((8, 8), text, font=font, fill=0, spacing=6)
    return img

def qr_to_image(data: str, target_dots: int = 256, label: str | None = None) -> Image.Image:
    """QR-Code mittig auf Druckbreite, optional mit Text-Label darunter."""
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data); qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("L")
    # auf ganzzahliges Vielfaches skalieren (scharfe Module), zentriert
    target = min(target_dots, WIDTH_DOTS)
    qr_img = qr_img.resize((target, target), Image.NEAREST)
    extra = 0
    lbl_img = None
    if label:
        lbl_img = text_to_image(label, font_size=24)
        extra = lbl_img.size[1]
    canvas = Image.new("L", (WIDTH_DOTS, target + extra), 255)
    canvas.paste(qr_img, ((WIDTH_DOTS - target) // 2, 0))
    if lbl_img:
        canvas.paste(lbl_img, (0, target))
    return canvas


def label_to_image(title: str, subtitle: str = "", qr_data: str | None = None) -> Image.Image:
    """Etikett: Titel (groß), Untertitel, optional QR rechts."""
    title_img = text_to_image(title, font_size=40)
    parts = [title_img]
    if subtitle:
        parts.append(text_to_image(subtitle, font_size=26))
    total_h = sum(p.size[1] for p in parts) + 12
    if qr_data:
        total_h = max(total_h, 160)
    canvas = Image.new("L", (WIDTH_DOTS, total_h), 255)
    y = 0
    text_w = WIDTH_DOTS - (170 if qr_data else 0)
    for p in parts:
        crop = p.crop((0, 0, min(text_w, p.size[0]), p.size[1]))
        canvas.paste(crop, (4, y)); y += p.size[1] + 6
    if qr_data:
        qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(qr_data); qr.make(fit=True)
        q = qr.make_image(fill_color="black", back_color="white").convert("L").resize((150, 150), Image.NEAREST)
        canvas.paste(q, (WIDTH_DOTS - 158, 4))
    return canvas


# Unterstützte Barcode-Typen (Auswahl der gängigsten)
BARCODE_TYPES = ["code128", "code39", "ean13", "ean8", "upca", "isbn13", "itf"]

def barcode_to_image(data: str, kind: str = "code128", show_text: bool = True) -> Image.Image:
    """Strichcode (EAN13, Code128, …) mittig auf Druckbreite.
    Balken werden OHNE eingebauten Text gerendert; die Klartext-Nummer
    wird separat mit klarem Abstand darunter gesetzt (keine Überlappung)."""
    bc = _barcode.get(kind, data, writer=ImageWriter())
    # Nur die Balken rendern (write_text=False)
    img = bc.render({
        "module_height": 16.0,
        "module_width": 0.3,
        "quiet_zone": 2.0,
        "write_text": False,
    }).convert("L")
    # auf max. Druckbreite einpassen, zentriert
    w, h = img.size
    if w > WIDTH_DOTS:
        h = round(h * WIDTH_DOTS / w); w = WIDTH_DOTS
        img = img.resize((w, h), Image.LANCZOS)
    bars = Image.new("L", (WIDTH_DOTS, h), 255)
    bars.paste(img, ((WIDTH_DOTS - w) // 2, 0))
    if not show_text:
        return bars
    # Klartext darunter (zentriert, mit Abstand)
    full_code = bc.get_fullcode()           # inkl. berechneter Prüfziffer
    try:
        font = ImageFont.truetype("consola.ttf", 30)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 30)
        except Exception:
            font = ImageFont.load_default()
    gap = 8
    txt_h = 40
    canvas = Image.new("L", (WIDTH_DOTS, h + gap + txt_h), 255)
    canvas.paste(bars, (0, 0))
    draw = ImageDraw.Draw(canvas)
    tb = draw.textbbox((0, 0), full_code, font=font)
    tw = tb[2] - tb[0]
    draw.text(((WIDTH_DOTS - tw) // 2, h + gap), full_code, font=font, fill=0)
    return canvas


# ─── Banner (großer Text, 90° gedreht = langer Streifen) ─────────────────────
def banner_to_image(text: str, bold: bool = True, direction: str = "down") -> Image.Image:
    """Großer Text als langer Streifen entlang der Papierlänge (Banner-Modus).
    Die Buchstaben werden so groß wie die Druckbreite (384 Dots).
    direction: 'down' = liest von oben nach unten, 'up' = unten nach oben."""
    font = None
    for name in (("arialbd.ttf", "calibrib.ttf") if bold else ("arial.ttf", "calibri.ttf")):
        try:
            font = ImageFont.truetype(name, 320); break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    # horizontal rendern, eng zugeschnitten
    dummy = Image.new("L", (10, 10), 255)
    bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad = 30
    horiz = Image.new("L", (tw + 2 * pad, th + 2 * pad), 255)
    ImageDraw.Draw(horiz).text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=0)
    # 90° drehen -> hoher, schmaler Streifen
    rot = horiz.rotate(90 if direction == "up" else -90, expand=True)
    # auf Druckbreite skalieren
    w, h = rot.size
    nh = max(1, round(h * WIDTH_DOTS / w))
    return rot.resize((WIDTH_DOTS, nh), Image.LANCZOS)


# ─── Zierrahmen (auf beliebigen Inhalt anwendbar) ────────────────────────────
FRAME_STYLES = ["kein", "solid", "doppelt", "gestrichelt", "gepunktet", "rund", "zierrahmen"]

def _dashed_rect(draw, box, dash=14, gap=9, width=3):
    x0, y0, x1, y1 = box
    def seg(a, b, horiz, fixed):
        p = a
        while p < b:
            q = min(p + dash, b)
            if horiz: draw.line([p, fixed, q, fixed], fill=0, width=width)
            else:     draw.line([fixed, p, fixed, q], fill=0, width=width)
            p = q + gap
    seg(x0, x1, True, y0); seg(x0, x1, True, y1)
    seg(y0, y1, False, x0); seg(y0, y1, False, x1)

def _dotted_rect(draw, box, step=11, r=3):
    x0, y0, x1, y1 = box
    def dot(x, y): draw.ellipse([x-r, y-r, x+r, y+r], fill=0)
    x = x0
    while x <= x1: dot(x, y0); dot(x, y1); x += step
    y = y0
    while y <= y1: dot(x0, y); dot(x1, y); y += step

def frame_image(img: Image.Image, style: str = "solid", pad: int = 18) -> Image.Image:
    """Umrahmt einen Inhalt mit einem Zierrahmen. style aus FRAME_STYLES."""
    if not style or style == "kein":
        return img
    img = img.convert("L")
    inner_w = WIDTH_DOTS - 2 * pad - 12
    if img.size[0] != inner_w:
        nh = max(1, round(img.size[1] * inner_w / img.size[0]))
        img = img.resize((inner_w, nh), Image.LANCZOS)
    cw, ch = img.size
    H = ch + 2 * pad + 12
    canvas = Image.new("L", (WIDTH_DOTS, H), 255)
    canvas.paste(img, (pad + 6, pad + 6))
    draw = ImageDraw.Draw(canvas)
    m = 5
    box = [m, m, WIDTH_DOTS - 1 - m, H - 1 - m]
    t = 3
    if style == "solid":
        draw.rectangle(box, outline=0, width=t)
    elif style == "doppelt":
        draw.rectangle(box, outline=0, width=2)
        draw.rectangle([box[0]+6, box[1]+6, box[2]-6, box[3]-6], outline=0, width=2)
    elif style == "rund":
        draw.rounded_rectangle(box, radius=22, outline=0, width=t)
    elif style == "gestrichelt":
        _dashed_rect(draw, box, width=t)
    elif style == "gepunktet":
        _dotted_rect(draw, box)
    elif style == "zierrahmen":
        draw.rounded_rectangle(box, radius=20, outline=0, width=2)
        for cx, cy in [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])]:
            draw.ellipse([cx-7, cy-7, cx+7, cy+7], fill=0)
            draw.ellipse([cx-13, cy-13, cx+13, cy+13], outline=0, width=2)
    return canvas

# ─── Drucker ─────────────────────────────────────────────────────────────────
class MXWPrinter:
    def __init__(self, density: int = DENSITY):
        self.client: BleakClient | None = None
        self.density = density           # einstellbare Druckdichte (1-200)
        self._flow = asyncio.Event(); self._flow.set()
        self._last_status = None

    def _on_notify(self, _, data: bytearray):
        h = bytes(data).hex()
        print(f"  [<- Drucker] {h}")
        # Flow-Control (2221ae01...)
        if h.startswith("2221ae0101001070") or h.endswith("1070ff"):
            self._flow.clear()
        elif h.startswith("2221ae0101000000") or h.endswith("0000ff"):
            self._flow.set()
        if h.startswith("2221a1"):
            self._last_status = h

    async def connect(self, address: str = ADDRESS) -> bool:
        print(f"Scanne nach {TARGET_NAME}...")
        found = None
        def cb(d, a):
            nonlocal found
            if d.address == address or (d.name and TARGET_NAME in d.name):
                found = d.address
        sc = BleakScanner(detection_callback=cb)
        await sc.start(); await asyncio.sleep(6); await sc.stop()
        if not found:
            print("Drucker nicht gefunden! FunPrint getrennt?"); return False

        print(f"Verbinde mit {found}...")
        self.client = BleakClient(found, timeout=20.0)
        await self.client.connect()
        print(f"Verbunden! MTU={self.client.mtu_size}")
        await self.client.start_notify(NOTIFY_UUID, self._on_notify)
        await asyncio.sleep(0.3)
        return True

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            print("Getrennt.")

    async def _cmd(self, data: bytes, wait: float = 0.25):
        await self.client.write_gatt_char(CMD_UUID, data, response=False)
        await asyncio.sleep(wait)

    async def _print_one(self, raster: bytes, height: int):
        """Eine einzelne Bitmap drucken (komplette A7..AD-Sequenz)."""
        await self._cmd(C_A7)
        await self._cmd(C_B1)
        await self._cmd(C_A1)
        await self._cmd(c_a2(self.density))          # einstellbare Dichte
        await self._cmd(c_a9(height), wait=0.4)       # Print-Start
        for i in range(0, len(raster), CHUNK):
            await self._flow.wait()
            await self.client.write_gatt_char(DATA_UUID, raster[i:i+CHUNK], response=False)
            if (i // CHUNK) % 8 == 7:
                await asyncio.sleep(0.02)
        await asyncio.sleep(0.2)
        await self._cmd(C_AD, wait=0.5)               # Print-Ende
        await asyncio.sleep(1.2)

    async def print_image(self, img: Image.Image, copies: int = 1, dither: bool = False):
        raster, height = img_to_raster(img, dither=dither)
        mode = "Dithering" if dither else "Schwellwert"
        print(f"Bild: {WIDTH_DOTS}x{height} Dots, {len(raster)} Bytes, {copies}x, Dichte={self.density}, {mode}")
        for n in range(copies):
            if copies > 1:
                print(f"  Kopie {n+1}/{copies}...")
            await self._print_one(raster, height)
        print("Fertig.")

    async def print_batch(self, images: list[Image.Image]):
        """Mehrere verschiedene Etiketten am Stück drucken."""
        print(f"Stapeldruck: {len(images)} Etiketten...")
        for idx, img in enumerate(images):
            print(f"  Etikett {idx+1}/{len(images)}...")
            raster, height = img_to_raster(img)
            await self._print_one(raster, height)
        print("Stapeldruck fertig.")

    async def print_text(self, text: str, font_size: int = 32, copies: int = 1):
        await self.print_image(text_to_image(text, font_size), copies)

    async def print_qr(self, data: str, label: str | None = None, copies: int = 1):
        await self.print_image(qr_to_image(data, label=label), copies)

    async def print_label(self, title: str, subtitle: str = "", qr_data: str | None = None, copies: int = 1):
        await self.print_image(label_to_image(title, subtitle, qr_data), copies)

    async def print_barcode(self, data: str, kind: str = "code128", copies: int = 1):
        await self.print_image(barcode_to_image(data, kind), copies)

    async def print_banner(self, text: str, copies: int = 1, direction: str = "down"):
        await self.print_image(banner_to_image(text, direction=direction), copies)

    async def print_file(self, path: str, copies: int = 1, dither: bool = True):
        await self.print_image(Image.open(path), copies, dither=dither)

# ─── CLI ─────────────────────────────────────────────────────────────────────
def _print_usage():
    print("""MXW01 Drucker — Verwendung:
  python mxw_printer.py text "Zeile1\\nZeile2"        Text drucken
  python mxw_printer.py qr   "https://..." [Label]    QR-Code drucken
  python mxw_printer.py label "Titel" "Untertitel" [QR-Daten]
  python mxw_printer.py barcode "ABC123" [typ]        Barcode (code128/ean13/...)
  python mxw_printer.py banner "TEXT"                 Banner (großer Text, längs)
  python mxw_printer.py image pfad\\zum\\bild.png       Bilddatei drucken
  python mxw_printer.py test                          Test-Ausdruck

Optionen (überall anhängbar):
  --copies N        N Kopien (Stapeldruck)
  --density N        Druckdichte 1-200 (Standard 98; heller=niedriger, dunkler=höher)
  --frame STIL       Zierrahmen: solid, doppelt, gestrichelt, gepunktet, rund, zierrahmen
  --nodither         Bilder ohne Dithering (harter S/W-Schnitt)

Barcode-Typen: code128, code39, ean13, ean8, upca, isbn13, itf
""")

async def main():
    import sys
    args = sys.argv[1:]

    # Optionen herausfiltern
    copies, density, dither, frame = 1, DENSITY, True, "kein"
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--copies" and i + 1 < len(args):
            copies = int(args[i+1]); i += 2
        elif args[i] == "--density" and i + 1 < len(args):
            density = int(args[i+1]); i += 2
        elif args[i] == "--frame" and i + 1 < len(args):
            frame = args[i+1]; i += 2
        elif args[i] == "--nodither":
            dither = False; i += 1
        else:
            rest.append(args[i]); i += 1
    args = rest
    mode = args[0].lower() if args else "test"

    if mode in ("help", "-h", "--help"):
        _print_usage(); return

    # Bild je nach Modus erzeugen
    use_dither = False
    if mode == "text":
        img = text_to_image(args[1].replace("\\n", "\n") if len(args) > 1 else "Test")
    elif mode == "qr":
        img = qr_to_image(args[1], label=args[2] if len(args) > 2 else None)
    elif mode == "label":
        img = label_to_image(args[1] if len(args) > 1 else "Label",
                             args[2] if len(args) > 2 else "",
                             args[3] if len(args) > 3 else None)
    elif mode == "barcode":
        img = barcode_to_image(args[1], args[2] if len(args) > 2 else "code128")
    elif mode == "banner":
        img = banner_to_image(args[1] if len(args) > 1 else "BANNER")
    elif mode == "image":
        img = Image.open(args[1]); use_dither = dither
    else:  # test
        img = text_to_image("MXW01\nHallo Welt!\n2026")

    if frame and frame != "kein":
        img = frame_image(img, frame)

    p = MXWPrinter(density=density)
    if not await p.connect():
        return
    try:
        await p.print_image(img, copies=copies, dither=use_dither)
    finally:
        await p.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
