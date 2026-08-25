# Network Radio Player for Anbernic Handhelds

A lightweight, full‑screen network radio player designed for **Anbernic RG series** devices (RG35XX, RG40XX, RG34XXSP, etc.) running EmuELEC or similar Linux distributions. It uses **SDL2 + Pillow** for rendering and **mpv** for audio playback, with a retro radio UI and real‑time spectrum visualization.

<img width="640" height="480" alt="screenshot_20260825_161422" src="https://github.com/user-attachments/assets/7cfabbbe-3d18-4001-82be-c605dfbf2dab" />

<img width="640" height="480" alt="screenshot_20260825_180519" src="https://github.com/user-attachments/assets/0d7c51c6-ab52-476a-9ab8-2d8cb2b439c6" />

## Features

- 📻 **Radio station browser** – scans `.txt` playlists from `/roms/Radio`, `/mnt/mmc/Radio`, `/mnt/sdcard/Radio` and local `./Radio` directory.
- 🎚️ **Category switching** – each `.txt` file is a category; switch with L1/R1.
- ▶️ **Play / Stop** – press A to play selected station, B to stop.
- 🔊 **Volume control** – hardware ALSA volume (0–100%) via `lineout volume` / `digital volume`, adjustable with V‑/V+ or L2/R2.
- 📡 **Spectrum analyzer** – simulated 28‑bar LED spectrum that moves with the music.
- 🔋 **System status** – WiFi SSID, battery percentage, charging status, and clock.
- 🌙 **Screen blanking** – press X to dim the screen (software black overlay) while playback continues.
- 🌐 **Multi‑language** – built‑in translations for English, Chinese, etc.; switch with SELECT.
- 💾 **Resume playback** – remembers last station and volume across restarts.
- 🎮 **Gamepad‑first** – all controls are mapped to physical buttons (no mouse/touch needed).

## Supported Devices

Tested on **Anbernic RG35XX+, RG35XXH, RG35XXSP, RG40XXH, RG40XXV, RG34XXSP, RG CubeXX** and clones with similar hardware. Works on any Linux system with SDL2, Python 3, and ALSA.

## Installation

1. **Download** the latest release or clone the repository.
2. **Place** the app folder (e.g., `radio/`) into your device’s `Roms/PORTS/` or `oms/APPS/` directory.
3. **Install dependencies** (if not already present):
   - Python 3.8+
   - `sdl2` and `Pillow` libraries – the app will automatically extract the required modules from `module.zip` on first run.
   - `mpv` – must be installed (usually pre‑installed on EmuELEC).
4. **Add radio playlists** – create `.txt` files in any `Radio` folder (e.g., `/mnt/mmc/Radio`) with one station per line: `Name,URL` or `Name<tab>URL`.

### Running

Launch the app via a launcher script or from the terminal:

```bash
cd /path/to/radio
python3 radio.py
```

## Controls

| Button | Function |
|--------|----------|
| `↑` / `↓` | Previous / next station |
| `←` / `→` | Page up / down (scrolls station list) |
| `L1` / `R1` | Previous / next category |
| `A` | Play selected station (if not already playing the same) |
| `B` | Stop playback / wake screen |
| `X` | Toggle screen blank (black overlay) |
| `Y` | Refresh station list (rescan all Radio folders) |
| `V‑` / `V+` | Volume down / up |
| `SELECT` | Cycle UI language (EN → ZH‑CN → ZH‑TW → …) |
| `START` | Dial style |
| `MENUF` | Exit application |

## Configuration

### Playlist Format

Each `.txt` file represents a category. Lines starting with `#` or `;` are ignored. Supported formats:

```
Station Name,http://example.com/stream.mp3
Another Station,http://other.com/radio
```

### Volume Control

The app automatically detects the appropriate ALSA mixer control (`lineout volume` or `digital volume`). If neither works, it falls back to mpv’s software volume.

### Screen Blanking

Because the device lacks a standard backlight sysfs, screen blanking is implemented as a software black overlay. The display stays powered on but shows a black screen, saving minimal power while preserving audio playback.

### Language Files

Place JSON translation files in `lang/` (e.g., `en_US.json`, `zh_CN.json`). The app reads the system language from `/mnt/vendor/oem/language.ini` and allows switching via SELECT.

## Building from Source

No compilation is needed – it’s pure Python. Dependencies are bundled via `module.zip` (automatically extracted on first run).

To modify the UI, edit `radio.py`. The rendering engine uses PIL (Pillow) and SDL2 via the `sdl2` Python binding.

## License

This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by the original LÖVE‑based radio app for Anbernic devices.
- Uses `mpv` for audio playback and `SDL2` + `Pillow` for graphics.

## Troubleshooting

- **No sound**: Ensure `mpv` is installed and ALSA mixer controls are correctly set. Try `amixer scontrols` to list available controls.
- **No stations found**: Verify that your `.txt` files are in one of the scanned directories (`/roms/Radio`, `/mnt/mmc/Radio`, etc.) and that they contain valid URLs.
- **Screen blank not working**: The app uses a software overlay; if you see no black screen, check that `backlight.dimmed` is toggled in the log.

For more details, see the [hardware baseline document](docs/H700_BASELINE.md) (if available).

---

**Enjoy your radio!** 🎵
```
