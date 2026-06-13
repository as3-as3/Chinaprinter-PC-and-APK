#!/usr/bin/env python3
"""
MXW01 Mini-Label-Drucker — GUI (Tkinter)
Nutzt den funktionierenden 2221-BLE-Treiber aus mxw_printer.py.
Tabs: Text · QR-Code · Etikett · Bild — mit Live-Vorschau.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import asyncio
import threading
from PIL import Image, ImageTk

import mxw_printer as mx
from mxw_printer import (MXWPrinter, text_to_image, qr_to_image, label_to_image,
                        barcode_to_image, BARCODE_TYPES, banner_to_image,
                        frame_image, FRAME_STYLES)


class PrinterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MXW01 — Druckersteuerung")
        self.geometry("560x780")
        self.configure(bg="#1E1E2E")

        self.printer: MXWPrinter | None = None
        self.connected = False
        self._preview_img = None
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

        self._build_ui()

    # ── async-Helfer ─────────────────────────────────────────────────────────
    def _run(self, coro, on_done=None):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        def _cb(f):
            err = f.exception()
            if err:
                self.after(0, lambda: self._log(f"Fehler: {err}"))
            elif on_done:
                self.after(0, on_done)
        fut.add_done_callback(_cb)

    def _log(self, msg):
        self.status.config(text=msg)

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        st = ttk.Style(self); st.theme_use("clam")
        bg, fg, acc = "#1E1E2E", "#CDD6F4", "#89B4FA"
        st.configure("TFrame", background=bg)
        st.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        st.configure("TButton", background="#313244", foreground=fg, font=("Segoe UI", 10), padding=6)
        st.configure("TNotebook", background=bg, borderwidth=0)
        st.configure("TNotebook.Tab", background="#313244", foreground=fg, padding=(14, 6))
        st.map("TNotebook.Tab", background=[("selected", acc)], foreground=[("selected", "#1E1E2E")])
        st.configure("Accent.TButton", background=acc, foreground="#1E1E2E", font=("Segoe UI", 11, "bold"))

        # Kopf: Verbindung
        top = ttk.Frame(self); top.pack(fill="x", padx=14, pady=10)
        self.btn_conn = ttk.Button(top, text="🔗 Verbinden", command=self._toggle_conn, style="Accent.TButton")
        self.btn_conn.pack(side="left")
        self.conn_lbl = ttk.Label(top, text="● getrennt", foreground="#F38BA8")
        self.conn_lbl.pack(side="left", padx=12)

        # Tabs
        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=14)

        # Text
        f1 = ttk.Frame(nb); nb.add(f1, text="Text")
        ttk.Label(f1, text="Text (mehrzeilig):").pack(anchor="w", pady=(10, 2))
        self.txt = tk.Text(f1, height=5, bg="#313244", fg=fg, insertbackground=fg, font=("Segoe UI", 11))
        self.txt.pack(fill="x"); self.txt.insert("1.0", "MXW01\nHallo Welt!\n2026")
        ttk.Label(f1, text="Schriftgröße:").pack(anchor="w", pady=(8, 2))
        self.fsize = tk.IntVar(value=32)
        ttk.Scale(f1, from_=18, to=64, variable=self.fsize, command=lambda e: self._preview()).pack(fill="x")
        ttk.Button(f1, text="Vorschau", command=self._preview).pack(pady=8)

        # QR
        f2 = ttk.Frame(nb); nb.add(f2, text="QR-Code")
        ttk.Label(f2, text="QR-Inhalt (URL/Text):").pack(anchor="w", pady=(10, 2))
        self.qr_data = tk.Entry(f2, bg="#313244", fg=fg, insertbackground=fg, font=("Segoe UI", 11))
        self.qr_data.pack(fill="x"); self.qr_data.insert(0, "https://example.com")
        ttk.Label(f2, text="Label darunter (optional):").pack(anchor="w", pady=(8, 2))
        self.qr_label = tk.Entry(f2, bg="#313244", fg=fg, insertbackground=fg, font=("Segoe UI", 11))
        self.qr_label.pack(fill="x")
        ttk.Button(f2, text="Vorschau", command=self._preview).pack(pady=8)

        # Etikett
        f3 = ttk.Frame(nb); nb.add(f3, text="Etikett")
        ttk.Label(f3, text="Titel:").pack(anchor="w", pady=(10, 2))
        self.lbl_title = tk.Entry(f3, bg="#313244", fg=fg, insertbackground=fg, font=("Segoe UI", 11))
        self.lbl_title.pack(fill="x"); self.lbl_title.insert(0, "Kaffee")
        ttk.Label(f3, text="Untertitel:").pack(anchor="w", pady=(8, 2))
        self.lbl_sub = tk.Entry(f3, bg="#313244", fg=fg, insertbackground=fg, font=("Segoe UI", 11))
        self.lbl_sub.pack(fill="x"); self.lbl_sub.insert(0, "MHD 2026-12-31")
        ttk.Label(f3, text="QR-Daten rechts (optional):").pack(anchor="w", pady=(8, 2))
        self.lbl_qr = tk.Entry(f3, bg="#313244", fg=fg, insertbackground=fg, font=("Segoe UI", 11))
        self.lbl_qr.pack(fill="x")
        ttk.Button(f3, text="Vorschau", command=self._preview).pack(pady=8)

        # Barcode
        f5 = ttk.Frame(nb); nb.add(f5, text="Barcode")
        ttk.Label(f5, text="Barcode-Inhalt:").pack(anchor="w", pady=(10, 2))
        self.bc_data = tk.Entry(f5, bg="#313244", fg=fg, insertbackground=fg, font=("Segoe UI", 11))
        self.bc_data.pack(fill="x"); self.bc_data.insert(0, "ABC-12345")
        ttk.Label(f5, text="Typ:").pack(anchor="w", pady=(8, 2))
        self.bc_type = tk.StringVar(value="code128")
        ttk.Combobox(f5, textvariable=self.bc_type, values=BARCODE_TYPES, state="readonly").pack(fill="x")
        ttk.Label(f5, text="(ean13=13 Ziffern, ean8=8 Ziffern, upca=12 Ziffern)",
                  foreground="#9399B2").pack(anchor="w", pady=(4, 0))
        ttk.Button(f5, text="Vorschau", command=self._preview).pack(pady=8)

        # Banner
        f6 = ttk.Frame(nb); nb.add(f6, text="Banner")
        ttk.Label(f6, text="Banner-Text (groß, längs gedruckt):").pack(anchor="w", pady=(10, 2))
        self.bn_text = tk.Entry(f6, bg="#313244", fg=fg, insertbackground=fg, font=("Segoe UI", 11))
        self.bn_text.pack(fill="x"); self.bn_text.insert(0, "PARTY")
        ttk.Label(f6, text="Leserichtung:").pack(anchor="w", pady=(8, 2))
        self.bn_dir = tk.StringVar(value="down")
        rowd = ttk.Frame(f6); rowd.pack(anchor="w")
        ttk.Radiobutton(rowd, text="oben → unten", variable=self.bn_dir, value="down",
                        command=self._preview).pack(side="left")
        ttk.Radiobutton(rowd, text="unten → oben", variable=self.bn_dir, value="up",
                        command=self._preview).pack(side="left", padx=12)
        ttk.Button(f6, text="Vorschau", command=self._preview).pack(pady=8)

        # Bild
        f4 = ttk.Frame(nb); nb.add(f4, text="Bild")
        self.img_path = tk.StringVar(value="(keine Datei)")
        ttk.Button(f4, text="📁 Bilddatei wählen…", command=self._pick_image).pack(pady=10)
        ttk.Label(f4, textvariable=self.img_path, wraplength=480).pack()
        self.dither = tk.BooleanVar(value=True)
        ttk.Checkbutton(f4, text="Foto-Modus (Dithering – für Farbbilder/Fotos)",
                        variable=self.dither, command=self._preview).pack(pady=10)

        self.tabs = nb
        nb.bind("<<NotebookTabChanged>>", lambda e: self._preview())

        # Vorschau
        ttk.Label(self, text="Vorschau (384 Dots breit):").pack(anchor="w", padx=14, pady=(6, 2))
        self.canvas = tk.Label(self, bg="white"); self.canvas.pack(padx=14)

        # Dichte + Kopien
        opt = ttk.Frame(self); opt.pack(fill="x", padx=14, pady=(10, 0))
        ttk.Label(opt, text="Dichte:").grid(row=0, column=0, sticky="w")
        self.density = tk.IntVar(value=mx.DENSITY)
        self.dens_lbl = ttk.Label(opt, text=str(mx.DENSITY), width=4)
        ttk.Scale(opt, from_=40, to=160, variable=self.density,
                  command=lambda e: self.dens_lbl.config(text=str(self.density.get()))
                  ).grid(row=0, column=1, sticky="ew", padx=6)
        self.dens_lbl.grid(row=0, column=2)
        ttk.Label(opt, text="Kopien:").grid(row=0, column=3, sticky="w", padx=(14, 4))
        self.copies = tk.IntVar(value=1)
        ttk.Spinbox(opt, from_=1, to=99, textvariable=self.copies, width=5).grid(row=0, column=4)
        opt.columnconfigure(1, weight=1)
        # Rahmen-Auswahl (gilt für alle außer Banner)
        ttk.Label(opt, text="Rahmen:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.frame_style = tk.StringVar(value="kein")
        fb = ttk.Combobox(opt, textvariable=self.frame_style, values=FRAME_STYLES,
                          state="readonly", width=14)
        fb.grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))
        fb.bind("<<ComboboxSelected>>", lambda e: self._preview())

        # Drucken
        ttk.Button(self, text="🖨  DRUCKEN", command=self._do_print, style="Accent.TButton").pack(fill="x", padx=14, pady=12)
        self.status = ttk.Label(self, text="Bereit. Drucker einschalten & verbinden.", foreground="#A6E3A1")
        self.status.pack(padx=14, pady=(0, 10))

        self.after(200, self._preview)

    # ── Bild-Erzeugung je Tab ────────────────────────────────────────────────
    def _current_image(self) -> Image.Image | None:
        tab = self.tabs.tab(self.tabs.select(), "text")
        if tab == "Text":
            return text_to_image(self.txt.get("1.0", "end").strip(), self.fsize.get())
        if tab == "QR-Code":
            lbl = self.qr_label.get().strip() or None
            return qr_to_image(self.qr_data.get().strip() or " ", label=lbl)
        if tab == "Etikett":
            return label_to_image(self.lbl_title.get().strip(), self.lbl_sub.get().strip(),
                                  self.lbl_qr.get().strip() or None)
        if tab == "Barcode":
            return barcode_to_image(self.bc_data.get().strip() or "0", self.bc_type.get())
        if tab == "Banner":
            return banner_to_image(self.bn_text.get().strip() or "BANNER", direction=self.bn_dir.get())
        if tab == "Bild":
            path = self.img_path.get()
            if path and path != "(keine Datei)":
                return Image.open(path)
        return None

    def _framed_image(self):
        """Aktuelles Bild inkl. gewähltem Rahmen (Banner bekommt keinen Rahmen)."""
        img = self._current_image()
        if img is None:
            return None
        tab = self.tabs.tab(self.tabs.select(), "text")
        style = self.frame_style.get()
        if tab != "Banner" and style and style != "kein":
            img = frame_image(img, style)
        return img

    def _preview(self):
        try:
            img = self._framed_image()
        except Exception as e:
            self._log(f"Vorschau-Fehler: {e}"); return
        if img is None:
            return
        disp = img.convert("L")
        if disp.size[0] != mx.WIDTH_DOTS:
            disp = disp.resize((mx.WIDTH_DOTS, round(disp.size[1] * mx.WIDTH_DOTS / disp.size[0])))
        # Bild-Tab mit Foto-Modus: gedithertes Ergebnis zeigen (wie es druckt)
        if self.tabs.tab(self.tabs.select(), "text") == "Bild" and self.dither.get():
            disp = disp.convert("1", dither=Image.FLOYDSTEINBERG).convert("L")
        self._preview_img = ImageTk.PhotoImage(disp)
        self.canvas.config(image=self._preview_img)

    def _pick_image(self):
        p = filedialog.askopenfilename(filetypes=[("Bilder", "*.png *.jpg *.jpeg *.bmp *.gif")])
        if p:
            self.img_path.set(p); self._preview()

    # ── Verbindung & Druck ───────────────────────────────────────────────────
    def _toggle_conn(self):
        if self.connected:
            self._run(self.printer.disconnect(), self._on_disconnected)
        else:
            self._log("Verbinde… (Drucker an, FunPrint getrennt)")
            self.printer = MXWPrinter()
            self._run(self.printer.connect(), self._on_connected)

    def _on_connected(self):
        self.connected = True
        self.conn_lbl.config(text="● verbunden", foreground="#A6E3A1")
        self.btn_conn.config(text="✖ Trennen")
        self._log("Verbunden. Bereit zum Drucken.")

    def _on_disconnected(self):
        self.connected = False
        self.conn_lbl.config(text="● getrennt", foreground="#F38BA8")
        self.btn_conn.config(text="🔗 Verbinden")
        self._log("Getrennt.")

    def _do_print(self):
        if not self.connected:
            messagebox.showwarning("Nicht verbunden", "Bitte zuerst verbinden."); return
        try:
            img = self._framed_image()
        except Exception as e:
            messagebox.showerror("Fehler", str(e)); return
        if img is None:
            messagebox.showwarning("Kein Inhalt", "Nichts zu drucken."); return
        self.printer.density = self.density.get()
        n = self.copies.get()
        # Dithering nur für den Bild-Tab
        use_dither = (self.tabs.tab(self.tabs.select(), "text") == "Bild" and self.dither.get())
        self._log(f"Drucke {n}x (Dichte {self.density.get()})…")
        self._run(self.printer.print_image(img, copies=n, dither=use_dither),
                  lambda: self._log("Druck fertig ✓"))


if __name__ == "__main__":
    PrinterApp().mainloop()
