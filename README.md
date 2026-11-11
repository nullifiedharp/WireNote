<p align="center">
  <img src="assets/icon.png" width="128" alt="WireNote icon">
</p>

<h1 align="center">WireNote</h1>

<p align="center">Right-click any wiring diagram → <b>Annotate</b> → click next to a wire, type your readings, done.</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-blue.svg" alt="License: GPLv3"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB.svg?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6.svg?logo=windows&logoColor=white" alt="Windows 10 | 11">
</p>

---

## Why

Marking up a wiring diagram during diagnosis usually means Paint: pick the text tool, set a font, type, reposition, pick a colour, draw a line… for every single reading. WireNote is built for exactly one job — stamping **expected vs. actual voltage, voltage drop and resistance** onto a diagram where you measured them — so each reading is one click and a few keystrokes. Readings colour themselves green or red so a finished diagram reads at a glance.

Works great with ISTA screenshots, OEM service manual diagrams, and any schematic image.

## Features

- **Right-click → Annotate** on any image in Explorer (PNG, JPG, BMP, GIF, TIFF…)
- **Click-to-annotate** — click next to a trace or pin, a small form pops up right there; Enter places it
- **V / Vd / Ω** expected + actual, with automatic pass/fail colouring and the difference shown (`V: 11.8 / 12.0 (-0.20)`)
- **Location labels** with autocomplete from your recent labels (module · connector · pin)
- **Indicator arrows** — drag to point at a trace, connector or pin; 7 colours; right-click to recolour
- **Move anything** — drag label boxes, anchor dots, or arrow ends; double-click to edit
- **Fits the window** on open and re-fits as you resize; wide/tall diagrams scroll and pan with all tools available
- **Zoom at cursor**, scrollbars, Space/right/middle-drag panning, full-screen (F11)
- **Save** as PNG, JPG or PDF at full resolution · **Copy** the annotated image to the clipboard · **Print** a report with the diagram and a readings table
- **Readings table** — copy as a tab-separated table (pastes straight into Excel) or export CSV
- **Paste a screenshot** with Ctrl+V — no need to save it first
- **Re-open and keep going** — readings are saved alongside the original image and come back automatically
- Undo/redo, dark UI, light "print-friendly" label style

## Requirements

- Windows 10 or 11
- To run from source or build: Python 3.10+ (tested on 3.13) and Pillow

## Installation

### Installer (recommended)
Download `WireNote-Setup-x.y.z.exe` from [Releases](https://github.com/nullifiedharp/WireNote/releases) and run it. Leave **Add "Annotate" to the right-click menu for images** ticked. No admin rights needed (it installs per-user unless you choose all users).

### Run from source
```bat
git clone https://github.com/nullifiedharp/WireNote.git
cd WireNote
pip install -r requirements.txt
python wirenote.py path\to\diagram.png
```
or double-click `run.bat` (drag an image onto it to open that image). To add the right-click entry when running from source, use **☰ → Add "Annotate" to right-click menu** (or `python wirenote.py --register`).

### Build it yourself
Double-click **`build.bat`**. It installs PyInstaller, builds `dist\WireNote\WireNote.exe`, fetches Inno Setup with `winget` if you don't have it, and writes the installer to `installer\`.

## Usage

1. Right-click a diagram → **Annotate** (Windows 11: under *Show more options*, or Shift+right-click).
2. **✚ Annotate (A)** — click next to the wire or pin you measured. Type a location (optional), then expected/actual values for whatever you measured — leave the rest blank. Press **Enter**.
3. **➚ Arrow (W)** — drag from your label toward the exact trace, connector or pin.
4. **💾 Save (Ctrl+S)**, **📋 Copy (Ctrl+C)** to drop it into an email/Teams/Word, or **🖨 Print (Ctrl+P)**.

| Action | Shortcut |
|---|---|
| Annotate / Arrow / Select tool | `A` / `W` / `S` |
| Edit reading | double-click it, or select + `Enter` |
| Delete selected | `Delete` (or right-click → Delete) |
| Undo / redo | `Ctrl+Z` / `Ctrl+Y` |
| Zoom | mouse wheel at cursor, `+` / `-` |
| Pan | drag empty space, right/middle-drag, `Space`+drag, Shift+wheel |
| Fit width / whole diagram / 100% | `0` / `Shift+0` / `1` |
| Readings table | `T` |
| Open / paste screenshot | `Ctrl+O` / `Ctrl+V` |
| Save / save as | `Ctrl+S` / `Ctrl+Shift+S` |
| Full screen | `F11` |

Clicking somewhere else while the form has values in it places the reading — so you can just keep clicking down a connector.

## How it works

- **Pass/fail:** voltage and resistance pass within ±10% of expected (adjustable under ☰ → *Pass/fail tolerance*). Resistance also passes within 0.5 Ω so near-zero continuity specs behave sensibly. **Voltage drop is treated as a maximum** — it passes when actual ≤ expected.
- **Text size:** labels are sized so they appear at the chosen point size (default 9 pt Arial) when the diagram is fit to the window, and scale with the drawing when you zoom — like ink on the page. The saved file matches what you see at fit-width, upscaling small diagrams so labels stay legible.
- **Saving:** the annotated image is a new file (`<name>_annotated.png` by default); the original is never modified. Your readings are also stored in `<name>.png.wirenote.json` next to the original, which WireNote loads automatically the next time you open that diagram.
- **Right-click menu:** registered under `HKCU\Software\Classes\SystemFileAssociations\image\shell\WireNote.Annotate` (HKLM for all-user installs) and removed on uninstall.

## Notes and limitations

- Windows-only for clipboard image copy and the right-click menu; the editor itself runs anywhere Python + Tk does.
- Image formats are whatever Pillow can read; WebP/HEIC appear in the right-click menu only if Windows treats them as images.
- Print opens a report in your default browser and shows the print dialog; *☰ → Print image only* sends just the diagram to the Windows print handler.

## License

GPLv3 © 2026 NullHarp — see [LICENSE](LICENSE). You're free to use, modify and share it, but derivatives must stay open source under the same license.
