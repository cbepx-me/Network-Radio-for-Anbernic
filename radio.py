#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ============================
# 导入系统库
# ============================
import os
import sys
import time
import json
import glob
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import ctypes
import logging
import math
import select
import zipfile
import struct
import configparser

VERSION = "1.0.1"

# ============================
# 导入第三方库 (确保已安装)
# ============================
def ensure_requests():
    try:
        program = os.path.dirname(os.path.abspath(__file__))
        depspath = os.path.join(program, "deps")
        if not os.path.exists(depspath):
            module_file = os.path.join(program, "module.zip")
            with zipfile.ZipFile(module_file, 'r') as zip_ref:
                zip_ref.extractall(program)
            print("Successfully installed sdl2 and PIL and flask")
        return True
    except Exception as e:
        print(f"Failed to install: {e}")
        return False

if ensure_requests():
    base_path = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(base_path, "deps"))

try:
    import sdl2
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Failed to import SDL2 and PIL modules. Please install them.")
    sys.exit(1)

# ============================
# 配置 & 常量
# ============================
APP_PATH = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(APP_PATH, "radio.log")
if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger("radio")
LOGGER.info("=== Radio App Started ===")

CUR_APP_VER = "1.0.0"

class RadioConfig:
    BOARD_MAPPING = {
        "RGcubexx": 1,
        "RG34xx": 2,
        "RG34xxSP": 2,
        "RGSP": 2,
        "RG28xx": 3,
        "RG35xx+_P": 4,
        "RG35xxH": 5,
        "RG35xxSP": 6,
        "RG40xxH": 7,
        "RG40xxV": 8,
        "RG35xxPRO": 9,
        "RGds": 10,
        "RGdsplus": 11,
    }
    SYSTEM_LIST = ("zh_CN", "zh_TW", "en_US", "ja_JP", "ko_KR", "es_LA", "ru_RU", "de_DE", "fr_FR", "pt_BR")

    COLOR_BG = "#121212"
    COLOR_BG_GRADIENT = "#2C2C2C"
    COLOR_TEXT = "#E0E0E0"
    COLOR_SHADOW = "#00000080"

    font_file = os.path.join(APP_PATH, "font", "font.ttf")
    if not os.path.exists(font_file):
        font_file = "/mnt/vendor/bin/default.ttf"

    KEYMAP = {
        304: "A", 305: "B", 306: "Y", 307: "X",
        308: "L1", 309: "R1", 314: "L2", 315: "R2",
        17: "DY", 16: "DX",
        310: "SELECT", 311: "START", 312: "MENUF",
        114: "V-", 115: "V+",
    }

    @staticmethod
    def screen_resolutions() -> Dict[int, Tuple[int, int, int]]:
        return {
            1: (576, 576, 15),
            2: (720, 480, 11),
            3: (640, 480, 11),
            4: (640, 480, 11),
            5: (640, 480, 11),
            6: (640, 480, 11),
            7: (640, 480, 11),
            8: (640, 480, 11),
            9: (640, 480, 11),
            10: (640, 480, 11),
            11: (682, 512, 11),
        }

class Translator:
    def __init__(self, lang_code="en_US"):
        self.lang_code = lang_code
        self.lang_data = {}
        self.load_language(lang_code)

    def load_language(self, lang_code):
        base = os.path.dirname(os.path.abspath(__file__))
        lang_file = os.path.join(base, "lang", f"{lang_code}.json")
        if not os.path.exists(lang_file):
            lang_file = os.path.join(base, "lang", "en_US.json")
            LOGGER.warning("Language file %s not found, using en_US", lang_code)
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                self.lang_data = json.load(f)
            LOGGER.info("Loaded language: %s", lang_code)
        except Exception as e:
            LOGGER.error("Failed to load language file: %s", e)
            self.lang_data = {}

    def t(self, key):
        return self.lang_data.get(key, key)

# ============================
# 输入处理 (从 launcher 移植)
# ============================
class InputHandler:
    def __init__(self, cfg: RadioConfig):
        self.cfg = cfg
        self.code_name = ""
        self.value = 0

        try:
            self.board_info = Path("/mnt/vendor/oem/board.ini").read_text().splitlines()[0]
        except:
            self.board_info = "RG35xxH"
        self.device_path = self._find_anbernic_device()
        self.dev_fd = None

        try:
            self.dev_fd = open(self.device_path, "rb", buffering=0)

            import fcntl
            flags = fcntl.fcntl(self.dev_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.dev_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        except Exception as e:
            LOGGER.error("Failed to open input device: %s", e)
            self.dev_fd = None

    def _find_anbernic_device(self):
        keyword = "ANBERNIC"
        for event_path in glob.glob("/dev/input/event*"):
            dev_name = os.path.basename(event_path)
            sys_path = f"/sys/class/input/{dev_name}/device/name"
            try:
                with open(sys_path, 'r') as f:
                    name = f.read().strip()
                    if keyword in name:
                        return event_path
            except Exception:
                continue
        fallback = f"/dev/input/event{self.cfg.BOARD_MAPPING.get(self.board_info, 5)}"
        if os.path.exists(fallback):
            return fallback
        raise RuntimeError("No ANBERNIC input device found")

    def poll(self) -> None:
        if self.dev_fd is None:
            self.code_name = ""
            self.value = 0
            return
        try:
            # 使用select检查可读，超时0.01秒
            rlist, _, _ = select.select([self.dev_fd], [], [], 0.01)
            if not rlist:
                self.code_name = ""
                self.value = 0
                return
            event = self.dev_fd.read(24)
            if not event:
                self.code_name = ""
                self.value = 0
                return
            (tv_sec, tv_usec, etype, kcode, kvalue) = struct.unpack("llHHI", event)
            if kvalue != 0:
                if kvalue != 1:
                    kvalue = -1
                else:
                    kvalue = 1
                self.code_name = self.cfg.KEYMAP.get(kcode, str(kcode))
                self.value = kvalue
                LOGGER.debug("Key: %s (code:%s val:%s)", self.code_name, kcode, kvalue)
            else:
                self.code_name = ""
                self.value = 0
        except Exception as e:
            LOGGER.error("Input error: %s", e)
            self.code_name = ""
            self.value = 0

    def is_key(self, name: str, key_value: int = 99) -> bool:
        if self.code_name == name:
            if key_value != 99:
                return self.value == key_value
            return True
        return False

    def slide_key(self) -> bool:
        return bool(self.code_name)

    def reset(self) -> None:
        self.code_name = ""
        self.value = 0

# ============================
# UI 渲染器
# ============================
class RadioUIRenderer:
    _instance = None
    _initialized = False

    def __init__(self, cfg: RadioConfig, hw_info: int):
        self.cfg = cfg
        self.hw_info = hw_info
        x_size, y_size, _ = RadioConfig.screen_resolutions().get(hw_info, (640, 480, 11))
        self.x_size = x_size
        self.y_size = y_size
        self.screen_size = x_size * y_size * 4

        self.active_image: Optional[Image.Image] = None
        self.active_draw: Optional[ImageDraw.ImageDraw] = None

        if self._initialized:
            return
        self.window = self._create_window()
        self.renderer = self._create_renderer()
        self._initialized = True
        self._draw_start()
        self.clear()
        self.set_active(self.create_image())

        try:
            self.hdmi_info = Path("/sys/class/extcon/hdmi/state").read_text().splitlines()[0]
        except:
            self.hdmi_info = 'HDMI=0'

    def _create_window(self):
        window = sdl2.SDL_CreateWindow(
            b"Radio",
            sdl2.SDL_WINDOWPOS_UNDEFINED,
            sdl2.SDL_WINDOWPOS_UNDEFINED,
            0, 0,
            sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP | sdl2.SDL_WINDOW_SHOWN,
        )
        if not window:
            raise RuntimeError("Failed to create window")
        return window

    def _create_renderer(self):
        renderer = sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_ACCELERATED)
        if not renderer:
            raise RuntimeError("Failed to create renderer")
        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"0")
        return renderer

    def _draw_start(self):
        sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 255)
        sdl2.SDL_RenderClear(self.renderer)
        self.active_image = self.create_image()
        self.active_draw = ImageDraw.Draw(self.active_image)

    def create_image(self) -> Image.Image:
        return Image.new("RGBA", (self.x_size, self.y_size), color=self.cfg.COLOR_BG)

    def set_active(self, image: Image.Image):
        self.active_image = image
        self.active_draw = ImageDraw.Draw(self.active_image)

    def paint(self):
        if self.hw_info == 3:
            rotated_image = self.active_image.rotate(90, expand=True)
            rgba_data = rotated_image.tobytes()
            temp_width, temp_height = rotated_image.size
        else:
            rgba_data = self.active_image.tobytes()
            temp_width, temp_height = self.x_size, self.y_size

        surface = sdl2.SDL_CreateRGBSurfaceWithFormatFrom(
            rgba_data,
            temp_width, temp_height,
            32, temp_width * 4,
            sdl2.SDL_PIXELFORMAT_RGBA32,
        )
        texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
        sdl2.SDL_FreeSurface(surface)

        window_w = ctypes.c_int()
        window_h = ctypes.c_int()
        sdl2.SDL_GetWindowSize(self.window, ctypes.byref(window_w), ctypes.byref(window_h))
        dst_rect = sdl2.SDL_Rect(0, 0, window_w.value, window_h.value)
        sdl2.SDL_RenderCopy(self.renderer, texture, None, dst_rect)
        sdl2.SDL_RenderPresent(self.renderer)
        sdl2.SDL_DestroyTexture(texture)

    def clear(self):
        self.screen_reset()

    def screen_reset(self):
        for i in range(self.y_size):
            ratio = i / self.y_size
            color = self.blend_colors(self.cfg.COLOR_BG_GRADIENT, self.cfg.COLOR_BG, ratio)
            self.active_draw.rectangle([0, i, self.x_size, i + 1], fill=color)

    def blend_colors(self, color1: str, color2: str, ratio: float) -> str:
        r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
        r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        return f"#{r:02x}{g:02x}{b:02x}"

    def text(self, pos, text, font_size=22, color=None, anchor=None, bold=False, shadow=False):
        color = color or self.cfg.COLOR_TEXT
        font_path = self.cfg.font_file
        try:
            if bold:
                fnt = ImageFont.truetype(font_path, font_size)
            else:
                fnt = ImageFont.truetype(font_path, font_size)
            if shadow:
                for dx, dy in [(1,1),(1,-1),(-1,1),(-1,-1)]:
                    self.active_draw.text((pos[0]+dx, pos[1]+dy), text, font=fnt, fill=self.cfg.COLOR_SHADOW, anchor=anchor)
            self.active_draw.text(pos, text, font=fnt, fill=color, anchor=anchor)
        except:
            fnt = ImageFont.load_default()
            self.active_draw.text(pos, text, font=fnt, fill=color, anchor=anchor)

    def rect(self, xy, fill=None, outline=None, width=1, radius=0, shadow=False):
        if shadow and radius > 0:
            sh_xy = [xy[0]+2, xy[1]+2, xy[2]+2, xy[3]+2]
            self.active_draw.rounded_rectangle(sh_xy, radius=radius, fill=self.cfg.COLOR_SHADOW)
        if radius > 0:
            self.active_draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
        else:
            self.active_draw.rectangle(xy, fill=fill, outline=outline, width=width)

    def circle(self, center, radius, fill=None, outline=None, shadow=False):
        x, y = center
        if shadow:
            self.active_draw.ellipse([x-radius-2, y-radius-2, x+radius+2, y+radius+2],
                                     fill=self.cfg.COLOR_SHADOW)
        self.active_draw.ellipse([x-radius, y-radius, x+radius, y+radius], fill=fill, outline=outline)

    def save_screenshot(self, filename=None):
        if filename is None:
            save_dir = "/mnt/mmc/anbernic/screenshots"
            os.makedirs(save_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(save_dir, f"screenshot_{timestamp}.png")
        self.active_image.save(filename)
        return filename

    def draw_end(self):
        sdl2.SDL_DestroyRenderer(self.renderer)
        sdl2.SDL_DestroyWindow(self.window)
        sdl2.SDL_Quit()

# ============================
# 收音机核心功能
# ============================
class RadioScanner:
    @staticmethod
    def find_sources() -> List[Dict]:
        bases = [
            "/roms/Radio", "/mnt/mmc/Radio", "/mnt/sdcard/Radio",
        ]

        bases.append(os.path.join(APP_PATH, "Radio"))

        sources = []
        seen = set()
        for b in bases:
            if not os.path.isdir(b):
                continue
            for f in os.listdir(b):
                if f.endswith(".txt"):
                    path = os.path.join(b, f)
                    real = os.path.realpath(path)
                    if real in seen:
                        continue
                    seen.add(real)
                    sources.append({"file": path, "name": f[:-4]})
                    LOGGER.info("Found source: %s", f)
        return sources

    @staticmethod
    def parse_txt(filepath: str) -> List[Dict]:
        channels = []
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line[0] in "#;":
                        continue
                    sep = line.find(',') if ',' in line else line.find('\t')
                    if sep != -1:
                        name = line[:sep].strip()
                        url = line[sep+1:].strip()
                        if url.startswith("http"):
                            channels.append({"name": name, "url": url})
                    else:
                        if line.startswith("http"):
                            host = line.split('/')[2] if '://' in line else "电台"
                            channels.append({"name": host, "url": line})
        except Exception as e:
            LOGGER.error("Parse error %s: %s", filepath, e)
        return channels

class RadioPlayer:
    def __init__(self):
        self.pid = None
        self.proc = None
        self.status = "idle"
        self.fail_reason = ""
        self.volume = 100
        self.last_url = ""
        self.last_play_time = 0

        self.volume_control = self._detect_volume_control()
        LOGGER.info("Selected ALSA volume control: %s", self.volume_control)
        self._enable_outputs()
        self._load_volume()

    def _list_controls(self) -> List[str]:
        try:
            out = subprocess.check_output(["amixer", "scontrols"], stderr=subprocess.DEVNULL).decode()
            controls = [line.split("'")[1] for line in out.splitlines() if "Simple mixer control" in line]
            return controls
        except Exception as e:
            LOGGER.error("Failed to list controls: %s", e)
            return []

    def _detect_volume_control(self) -> Optional[str]:
        controls = self._list_controls()
        if not controls:
            return None

        for cand in ["lineout volume", "digital volume", "Master", "PCM", "Playback"]:
            if cand in controls:
                try:
                    info = subprocess.check_output(["amixer", "sget", cand], stderr=subprocess.DEVNULL).decode()
                    if "volume" in info.lower() or "%" in info:
                        return cand
                except:
                    pass
        for c in controls:
            if "volume" in c.lower():
                return c

        return controls[0] if controls else None

    def _enable_outputs(self):
        for ctrl in ["LINEOUT", "SPK"]:
            try:
                subprocess.run(["amixer", "set", ctrl, "on"], stderr=subprocess.DEVNULL, check=False)
            except:
                pass
        LOGGER.info("Outputs enabled (LINEOUT, SPK)")

    def _load_volume(self):
        vf = os.path.join(APP_PATH, "volume.txt")
        vol = 80
        if os.path.exists(vf):
            try:
                with open(vf, 'r') as f:
                    v = int(f.read().strip())
                    if 0 <= v <= 100:
                        vol = v
            except:
                pass
        self.set_volume(vol)

    def set_volume(self, vol):
        self.volume = max(0, min(100, vol))
        hardware_vol = self.volume

        self._enable_outputs()

        if not self.volume_control:
            LOGGER.warning("No ALSA control, only mpv soft volume")
            return

        try:
            if self.volume_control == "digital volume":
                val = int(round(hardware_vol * 63 / 100))
                val = max(0, min(63, val))
                cmd = ["amixer", "set", "digital volume", str(val)]
            else:
                cmd = ["amixer", "set", self.volume_control, f"{hardware_vol}%"]
            subprocess.run(cmd, check=True, stderr=subprocess.PIPE)
            LOGGER.info("Set %s to %d%% (hardware)", self.volume_control, hardware_vol)
        except subprocess.CalledProcessError as e:
            LOGGER.error("Failed to set ALSA volume: %s, stderr: %s", e, e.stderr)
            if self.volume_control == "digital volume":
                fallback = "lineout volume"
                if fallback in self._list_controls():
                    self.volume_control = fallback
                    LOGGER.info("Fallback to %s", fallback)
                    self.set_volume(vol)
            elif self.volume_control == "lineout volume":
                fallback = "digital volume"
                if fallback in self._list_controls():
                    self.volume_control = fallback
                    LOGGER.info("Fallback to %s", fallback)
                    self.set_volume(vol)

    def play(self, url: str):
        now = time.time()
        if url == self.last_url and now - self.last_play_time < 1.0:
            LOGGER.info("防连发跳过: %s", url)
            return
        self.stop()
        self.status = "connecting"
        self.fail_reason = ""
        self.last_url = url
        self.last_play_time = now
        mpv_vol = min(100, self.volume)
        cmd = [
            "mpv", "--vid=no", "--no-video", "--no-osc", "--no-osd-bar",
            f"--volume={mpv_vol}",
            "--network-timeout=20", "--cache=yes", "--cache-secs=10",
            "--stream-lavf-o=reconnect=1",
            "--user-agent=Mozilla/5.0",
            url
        ]
        LOGGER.info("Playing: %s (mpv volume=%d%%)", url, mpv_vol)
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.pid = self.proc.pid
            self.status = "playing"
        except Exception as e:
            self.status = "failed"
            self.fail_reason = str(e)
            LOGGER.error("mpv start failed: %s", e)

    def stop(self):
        if self.pid:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1)
            except:
                self.proc.kill()
            self.pid = None
            self.proc = None
            self.status = "idle"
            LOGGER.info("Stopped")

    def is_alive(self) -> bool:
        if self.proc is not None:
            ret = self.proc.poll()
            if ret is None:
                return True
            # 进程已退出，清理 proc 引用
            self.proc = None
            self.pid = None
            return False
        return False

class BacklightController:
    def __init__(self):
        self.dimmed = False

    def restore(self):
        self.dimmed = False

# ============================
# 频谱生成器
# ============================
class SpectrumGenerator:
    def __init__(self, num_bars=28):
        self.num_bars = num_bars
        self.levels = [0.0] * num_bars
        self.targets = [0.0] * num_bars
        self.timer = 0.0

    def update(self, dt: float, play_status: str, now_sec: float):
        if play_status == "playing":
            self.timer -= dt
            if self.timer <= 0:
                self.timer = 0.07
                import random
                for i in range(self.num_bars):
                    base = 0.9 - 0.55 * (i / self.num_bars)
                    wob = 0.5 * abs((now_sec * 3.3 + i * 1.7) % (2*3.14159) - 3.14159)
                    wob += 0.3 * abs((now_sec * 7.9 + i * 0.9) % (2*3.14159) - 3.14159)
                    t = base * wob / 3.14159 + random.random() * 0.30
                    t = max(0.04, min(1.0, t))
                    self.targets[i] = t
            for i in range(self.num_bars):
                d = self.targets[i] - self.levels[i]
                if d > 0:
                    self.levels[i] += d * min(1.0, dt * 20)
                else:
                    self.levels[i] += d * min(1.0, dt * 9)
        elif play_status == "connecting":
            v = 0.08 + 0.05 * (0.5 + 0.5 * (now_sec * 6) % (2*3.14159) / 3.14159)
            for i in range(self.num_bars):
                self.levels[i] += (v - self.levels[i]) * min(1.0, dt * 6)
        else:
            for i in range(self.num_bars):
                self.levels[i] *= max(0.0, 1.0 - dt * 4)

# ============================
# 主应用
# ============================
class RadioApp:
    def __init__(self):
        self.cfg = RadioConfig()
        self.system_langs = ("zh_CN", "zh_TW", "en_US", "ja_JP", "ko_KR", "es_LA", "ru_RU", "de_DE", "fr_FR", "pt_BR")
        self.language = "en_US"
        self.dial_mode = "1"

        try:
            board_info = Path("/mnt/vendor/oem/board.ini").read_text().splitlines()[0]
        except:
            board_info = "RG35xxH"
        self.board_info = board_info
        self.hw_info = self.cfg.BOARD_MAPPING.get(board_info, 5)

        self.input = InputHandler(self.cfg)
        self.ui = RadioUIRenderer(self.cfg, self.hw_info)
        self.player = RadioPlayer()
        self.backlight = BacklightController()
        self.spectrum = SpectrumGenerator(28)

        self.sources = []
        self.source_cache = {}
        self.current_source_idx = 0
        self.current_channel_idx = 0
        self.current_channels = []
        self.channel_list_start = 0
        self.playing_channel_idx = -1

        self.wifi_connected = False
        self.wifi_essid = ""
        self.battery_level = 0
        self.battery_charging = False
        self.status_timer = 0.0
        self.now_sec = 0.0
        self.show_hints = True
        self.hint_timer_default = 10.0
        self.reset_hint_timer()

        self._ready()
        self._load_config()
        self._scan_radio()
        self._update_system_status()

        self.skip_first_input = True

    def reset_hint_timer(self):
        self.hint_timer = self.hint_timer_default

    def _ready(self) -> None:
        target_path = [
            "/mnt/mmc",
            "/mnt/sdcard",
            APP_PATH
        ]
        for path in target_path:
            if path == "/mnt/sdcard" and not os.path.ismount(path):
                continue
            radio_dir = os.path.join(path, "Radio")
            os.makedirs(radio_dir, exist_ok=True)

    def _load_config(self):
        self.config = configparser.ConfigParser()
        self.config_file = os.path.join(APP_PATH, "radio.ini")
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)

        # 确保各节存在
        for section in ['General', 'Volume', 'Resume', 'Dial']:
            if section not in self.config:
                self.config[section] = {}

        # 语言
        lang = self.config.get('General', 'language', fallback=None)
        if lang and lang in self.system_langs:
            self.language = lang
        else:
            self.language = self._load_system_language()
        self.translator = Translator(self.language)

        # 音量
        vol = self.config.getint('Volume', 'value', fallback=80)
        vol = max(0, min(100, vol))
        self.player.set_volume(vol)

        # 恢复位置
        src = self.config.getint('Resume', 'source_index', fallback=1)
        ch = self.config.getint('Resume', 'channel_index', fallback=1)
        self.current_source_idx = src - 1
        self.current_channel_idx = ch - 1

        # 刻度盘模式
        mode = self.config.get('Dial', 'mode', fallback='1')
        if mode in ['1', '2']:
            self.dial_mode = mode
        else:
            self.dial_mode = '1'

    def _save_config(self):
        """保存所有设置到 radio.ini"""
        self.config['General']['language'] = self.language
        self.config['Volume']['value'] = str(self.player.volume)
        self.config['Resume']['source_index'] = str(self.current_source_idx + 1)
        self.config['Resume']['channel_index'] = str(self.current_channel_idx + 1)
        self.config['Dial']['mode'] = self.dial_mode
        try:
            with open(self.config_file, 'w') as f:
                self.config.write(f)
        except Exception as e:
            LOGGER.error("Failed to save config: %s", e)

    def _load_system_language(self):
        """从系统文件读取默认语言"""
        try:
            lang_path = "/mnt/vendor/oem/language.ini"
            if os.path.exists(lang_path):
                with open(lang_path, 'r') as f:
                    idx = int(f.read().strip())
                    if 0 <= idx < len(self.system_langs):
                        return self.system_langs[idx]
        except:
            pass
        return "en_US"

    def _scan_radio(self):
        self.sources = RadioScanner.find_sources()
        self.source_cache = {}
        if self.sources:
            if self.current_source_idx < 0 or self.current_source_idx >= len(self.sources):
                self.current_source_idx = 0
            self._load_source(self.current_source_idx)
        else:
            self.current_channels = []
            self.current_source_idx = 0
            LOGGER.warning("No radio sources found")

    def _load_source(self, idx: int):
        if idx < 0 or idx >= len(self.sources):
            return
        src = self.sources[idx]
        if src['file'] in self.source_cache:
            ch = self.source_cache[src['file']]
        else:
            ch = RadioScanner.parse_txt(src['file'])
            self.source_cache[src['file']] = ch
        self.current_source_idx = idx
        self.current_channels = ch
        if self.current_channel_idx < 0 or self.current_channel_idx >= len(ch):
            self.current_channel_idx = 0
        LOGGER.info("Loaded %s: %d channels", src['name'], len(ch))

    def _update_system_status(self):
        # WiFi
        try:
            with open("/sys/class/net/wlan0/operstate", 'r') as f:
                op = f.read().strip()
            self.wifi_connected = (op == "up")
            if not self.wifi_connected:
                with open("/proc/net/wireless", 'r') as f:
                    w = f.read().strip().split()
                if "wlan" in w:
                    self.wifi_connected = True
            if self.wifi_connected:
                essid = subprocess.check_output(["iw", "dev", "wlan0", "link"], stderr=subprocess.DEVNULL).decode()
                for line in essid.splitlines():
                    if line.strip().startswith('SSID'):
                        essid = str(line.split('SSID:', 1)[1].strip())
                self.wifi_essid = essid if essid else self.translator.t("Connected")
            else:
                self.wifi_essid = ""
        except:
            self.wifi_connected = False
            self.wifi_essid = ""
        # 电池
        for p in ["battery", "BAT0", "axp2202-battery"]:
            try:
                with open(f"/sys/class/power_supply/{p}/capacity", 'r') as f:
                    self.battery_level = int(f.read().strip())
                    try:
                        with open(f"/sys/class/power_supply/{p}/status", 'r') as f:
                            st = f.read().strip()
                            self.battery_charging = (st in ["Charging", "Full"])
                    except:
                        self.battery_charging = False
                    break
            except:
                continue
            
    # ---------- 按键处理 ----------
    def handle_input(self):
        if self.skip_first_input:
            self.input.reset()
            self.skip_first_input = False
            return
        self.input.poll()
        if not self.input.code_name:
            return

        k = self.input.code_name
        val = self.input.value

        if self.backlight.dimmed or not self.show_hints:  # 当前熄屏
            if k == "V-":
                self.player.set_volume(self.player.volume - 10)
                self._save_config()
                self.show_hints = True
                self.reset_hint_timer()
            elif k == "V+":
                self.player.set_volume(self.player.volume + 10)
                self._save_config()
                self.show_hints = True
                self.reset_hint_timer()
            if k == "X":
                self.backlight.dimmed = False
                self.show_hints = True
                self.reset_hint_timer()
                self.input.reset()
                return
            if k == "B":
                if k == "B":
                    self.backlight.dimmed = False
                    self.show_hints = True
                    self.reset_hint_timer()
                    self.input.reset()
                    return
        else:  # 当前亮屏
            if k == "MENUF":
                self.quit()
                return
            if k == "V-":
                self.player.set_volume(self.player.volume - 10)
                self._save_config()
                self.show_hints = True
                self.reset_hint_timer()
            elif k == "V+":
                self.player.set_volume(self.player.volume + 10)
                self._save_config()
                self.show_hints = True
                self.reset_hint_timer()
            if k == "X":
                self.backlight.dimmed = True
                self.show_hints = True   # 保留提示文字
                self.reset_hint_timer()
                self.input.reset()
                return
            if k == "B":
                if k == "B":
                    self.player.stop()
                    self.playing_channel_idx = -1
                    self.show_hints = True
                    self.reset_hint_timer()
                    self.input.reset()
                    return
            if k == "A":
                # 如果当前没有播放，或者选中的频道不是正在播放的频道，则播放选中项
                if self.player.status != "playing" or self.playing_channel_idx != self.current_channel_idx:
                    self.play_selected()
                    self.show_hints = True
                    self.reset_hint_timer()
                # 否则（正在播放且选中项就是当前播放），无操作
            if k == "Y":
                self._scan_radio()
                self.show_hints = True
                self.reset_hint_timer()
            if k == "DY":
                if val == -1:
                    self.change_channel(-1)
                elif val == 1:
                    self.change_channel(1)
                self.show_hints = True
                self.reset_hint_timer()
            if k == "DX":
                page = self._page_size()
                if val == -1:
                    self.change_channel(-page)
                elif val == 1:
                    self.change_channel(page)
                self.show_hints = True
                self.reset_hint_timer()
            if k == "L1":
                self.change_source(-1)
                self.show_hints = True
                self.reset_hint_timer()
            if k == "R1":
                self.change_source(1)
                self.show_hints = True
                self.reset_hint_timer()
            if k == "SELECT":
                langs = self.system_langs
                try:
                    idx = langs.index(self.language)
                    next_lang = langs[(idx + 1) % len(langs)]
                except:
                    next_lang = langs[0]
                self.language = next_lang
                self.translator.load_language(next_lang)
                self._save_config()
                self.show_hints = True
                self.reset_hint_timer()
                LOGGER.info("Language switched to %s", next_lang)
                self.input.reset()
                return
            if k == "START":
                if self.dial_mode == "1":
                    self.dial_mode = "2"
                else:
                    self.dial_mode = "1"
                self._save_config()
                self.show_hints = True
                self.reset_hint_timer()

        self.input.reset()

    def change_channel(self, delta: int):
        if not self.current_channels:
            return
        n = len(self.current_channels)
        self.current_channel_idx = (self.current_channel_idx + delta) % n
        LOGGER.info("Channel: %s", self.current_channels[self.current_channel_idx]['name'])
        if self.player.is_alive():
            self.play_selected()

    def change_source(self, delta: int):
        if not self.sources:
            return
        n = len(self.sources)
        self.current_source_idx = (self.current_source_idx + delta) % n
        self._load_source(self.current_source_idx)
        self.current_channel_idx = 0

        if self.player.status == "playing":
            self.playing_channel_idx = -1
            self.play_selected()
        self.show_hints = True
        self.reset_hint_timer()
        LOGGER.info("Source: %s", self.sources[self.current_source_idx]['name'])

    def play_selected(self):
        if not self.current_channels or self.current_channel_idx >= len(self.current_channels):
            return
        ch = self.current_channels[self.current_channel_idx]
        self.player.play(ch['url'])
        if self.player.status == "playing":
            self.playing_channel_idx = self.current_channel_idx
        else:
            self.playing_channel_idx = -1

    def _page_size(self) -> int:
        top_h = 100
        bottom_h = 60
        item_h = 26
        avail = self.ui.y_size - top_h - bottom_h - 80
        return max(1, int(avail / item_h))

    def update(self, dt: float):
        self.now_sec += dt
        self.status_timer += dt
        if self.status_timer >= 8:
            self.status_timer = 0
            self._update_system_status()

        if self.show_hints:
            self.hint_timer -= dt
            if self.hint_timer <= 0:
                self.show_hints = False
                self.backlight.dimmed = True

        if self.player.pid and not self.player.is_alive():
            self.player.pid = None
            self.player.proc = None
            if self.player.status != "idle":
                self.player.status = "failed"
                if not self.player.fail_reason:
                    self.player.fail_reason = self.translator.t("Playback failed")
                self.playing_channel_idx = -1
                LOGGER.info("mpv exited")

        self.spectrum.update(dt, self.player.status, self.now_sec)

    def draw(self):
        ui = self.ui
        t = self.translator.t
        ui.clear()
        W, H = ui.x_size, ui.y_size
        S = 1.0

        ch = self.current_channels
        cur = ch[self.current_channel_idx] if ch else None
        top_h = 40
        bot_h = 44

        if self.backlight.dimmed or not self.show_hints:
            ui.clear()
            ui.rect([0,0,W,H], fill="#000000C8")
            ui.text((W//2, H//2-30), f"{t('Screen off playing')} · {t('Press X/B to turn on')}", font_size=32, color="#3A3A3A", anchor="mm")
            ui.paint()
            return
            
        # ---------- 顶部状态栏 ----------
        ui.rect([0,0,W,top_h], fill="#0D1B2A")
        ui.text((12, 12), f'{t("Network Radio")} v{VERSION}', font_size=18, color="#E0E8F0")
        bat_str = f"{self.battery_level}%" + (" █" if self.battery_charging else " ")
        bat_color = "#4FC3F7" if self.battery_level >= 60 else "#64F6A6" if self.battery_level >= 20 else "#EF5350"
        ui.text((W-12, 22), bat_str, font_size=18, color=bat_color, anchor="rm")
        t_str = time.strftime("%H:%M:%S")
        ui.text((W//2-100, 22), t_str, font_size=20, color="#E0E8F0", anchor="lm")
        wifi_str = f"WiFi: {self.wifi_essid}" if self.wifi_connected else "WiFi ×"
        wifi_color = "#4FC3F7" if self.wifi_connected else "#EF5350"
        ui.text((W//2+200, 22), wifi_str, font_size=18, color=wifi_color, anchor="rm")

        # ---------- 左侧列表 ----------
        lx, ly = 12, top_h + 6
        lw = int(W * 0.45)
        lh = H - ly - bot_h - 6
        # 背景
        ui.rect([lx, ly, lx+lw, ly+lh], fill="#0F1A2E")
        ui.rect([lx+2, ly+2, lx+lw-2, ly+lh-2], fill="#152238")
        # 分类名
        src_name = self.sources[self.current_source_idx]['name'] if self.sources else t("Radio")
        ui.text((lx+12, ly+10), f"● {src_name}", font_size=22, color="#64B5F6")
        ui.text((lx+12, ly+44), f"{self.current_source_idx+1}/{len(self.sources)} {t('Category')}  {len(ch)} {t('Channels')}", font_size=14, color="#7A8BA0")

        # 列表项
        item_h = 34
        list_top = ly + 74
        visible = self._page_size()
        start = self.current_channel_idx - visible//2
        if start < 0: start = 0
        if ch and start > len(ch) - visible:
            start = max(0, len(ch) - visible)
        for i in range(visible):
            idx = start + i
            if idx < len(ch):
                y = list_top + i * item_h
                if idx == self.current_channel_idx:
                    ui.rect([lx+6, y, lx+lw-6, y+item_h-4], fill="#1E88E5")
                    col = "#FFFFFF"
                else:
                    col = "#B0C4DE"
                name = ch[idx]['name']
                if len(name) > 18: name = name[:16]+"…"
                ui.text((lx+12, y+5), f"{idx+1:2d} {name}", font_size=18, color=col)

        # ---------- 右侧主面板 ----------
        rx = lx + lw + 12
        rw = W - rx - 12
        rh = lh
        ui.rect([rx, ly, rx+rw, ly+rh], fill="#0F1A2E")
        ui.rect([rx+2, ly+2, rx+rw-2, ly+rh-2], fill="#152238")

        # 信号灯
        power_col = "#66BB6A" if not self.backlight.dimmed else "#455A64"
        ui.circle((rx+26, ly+24), 8, fill=power_col)
        play_col = "#66BB6A" if self.player.status == "playing" else "#455A64"
        ui.circle((rx+50, ly+24), 8, fill=play_col)
        wifi_col = "#66BB6A" if self.wifi_connected else "#455A64"
        ui.circle((rx+74, ly+24), 8, fill=wifi_col)

        status_text = f"{t('Power')}  {t('play')}  {t('WiFi')}"
        if self.player.status == "connecting":
            status_text += f"  ● {t('Connecting...')}"
        elif self.player.status == "playing":
            status_text += f"  ● {t('Playing')}"
        else:
            status_text += f"  ● {t('Idle')}"
        ui.text((rx+92, ly+16), status_text, font_size=16, color="#B0C4DE")

        # 当前台名+URL
        if cur:
            name = cur['name'][:30] + "…" if len(cur['name'])>30 else cur['name']
            ui.text((rx+rw//2, ly+60), name, font_size=22, color="#E0E8F0", anchor="mm")
            url = cur['url'][:30] + "…" if len(cur['url'])>30 else cur['url']
            ui.text((rx+rw//2, ly+90), url, font_size=16, color="#7A8BA0", anchor="mm")
        else:
            ui.text((rx+rw//2, ly+60), t('No stations'), font_size=22, color="#D2C3AA", anchor="mm")

        # ---------- 频谱区 ----------
        spec_x = rx + 16
        spec_w = rw - 32
        spec_y = ly + 120
        dial_zone = 110                     # 减小刻度盘区域
        spec_h = rh - 140 - dial_zone - 14  # 增大频谱高度
        if spec_h < 60: spec_h = 60
        self._draw_spectrum(spec_x, spec_y, spec_w, spec_h)

        # ---------- 调谐刻度盘（圆形） ----------
        dr = min(72, dial_zone * 0.45)      # 最大半径72，按比例缩小
        dcx = rx + dr + 12
        dcy = ly + rh - dr - 30             # 刻度盘中心下移

        if self.dial_mode == "1":
            # ---------- 调谐刻度盘（横向） ----------
            dial_y = spec_y + spec_h + 30 #ly + rh - 70          # 垂直位置
            dial_h = 30                    # 条高度
            dial_x_start = rx + 20
            dial_width = rw - 40           # 左右留边距
            self._draw_horizontal_dial(dial_x_start, dial_y, dial_width, dial_h, self.current_channel_idx)

        if self.dial_mode == "2":
            self._draw_dial(dcx, dcy, dr)
            pct = (self.current_channel_idx % 100) / 100.0 if ch else 0
            self._draw_needle(dcx, dcy, dr, pct)
            ui.text((dcx-40, dcy+dr+8), f"FM {88 + (self.current_channel_idx%100)*0.2:.1f} MHz", font_size=16, color="#D2C3AA")

        # ---------- 音量条 ----------
        dial_x = rx + 20 - dcx if self.dial_mode == "1" else dr + 20
        vx = dcx + dial_x
        vw = rx + rw - 18 - vx
        dial_y = 30 if self.dial_mode == "1" else -10
        if vw > 100:
            vy = dcy + dial_y
            vh = 18
            ui.rect([vx, vy, vx+vw, vy+vh], fill="#0A0F1A")
            ui.rect([vx, vy, vx+vw, vy+vh], fill=None, outline="#1E3A5F")
            fw = int((vw - 4) * min(self.player.volume, 100) / 100)
            if fw > 0:
                ui.rect([vx+2, vy+2, vx+2+fw, vy+vh-2], fill="#42A5F5")
                ui.text((vx, vy+vh+8), f"{t('Volume')} {self.player.volume}%", font_size=18, color="#B0C4DE")
            if self.player.status == "failed":
                ui.text((vx+vw, vy+vh+18), f"{self.player.fail_reason[:20]}", font_size=18, color="#EF5350")

        # 底部提示
        hint1 = (
        " ↑↓ " + t("channel") + "  ←→ " + t("page") +
        "  L1/R1 " + t("category") + " SEL " + t("language") +
        " STA " + t("dial style")
        )
        hint2 = (
        "  A " + t("play") +
        "  B " + t("stop/turn on") + "  X " + t("screen off") +
        "  Y " + t("refresh") + "  M " + t("exit")
        )
        ui.rect([0, H-bot_h, W, H], fill="#0D1B2A")
        ui.text((12, H-bot_h+1), hint1, font_size=16, color="#B0C4DE")
        ui.text((12, H-bot_h+23), hint2, font_size=16, color="#B0C4DE")

        # 无电台提示
        if not ch and self.sources:
            ui.text((rx+rw//2, ly+90), f"{t('No stations')}，{t('Switch category with L1/R1')}", font_size=18, color="#B0C4DE", anchor="mm")
        elif not self.sources:
            ui.text((rx+rw//2, ly+90), f"{t('No radio list found')}：{t('Please put TXT files in Radio folder')}", font_size=18, color="#FF8A65", anchor="mm")

        ui.paint()

    def _draw_spectrum(self, x, y, w, h):
        ui = self.ui
        ui.rect([x, y, x+w, y+h], fill="#0A0F1A")
        ui.rect([x, y, x+w, y+h], fill=None, outline="#1E3A5F")
        ui.text((x+10, y+6), "☢ SPECTRUM", font_size=14, color="#4FC3F7")
        pad = 10
        gap = 3
        bw = (w - 2*pad - (self.spectrum.num_bars-1)*gap) / self.spectrum.num_bars
        seg_h = 9
        seg_gap = 3
        inner_top = y + 26
        max_segs = int((y+h - pad - inner_top + seg_gap) / (seg_h + seg_gap))
        if max_segs < 2: max_segs = 2
        for i, level in enumerate(self.spectrum.levels):
            lit = int(level * max_segs)
            bx = x + pad + i*(bw+gap)
            for s in range(max_segs):
                sy = y + h - pad - s*(seg_h+seg_gap) - 5
                if s < lit:
                    frac = s / max_segs
                    if frac < 0.55:
                        col = "#3CE65A"
                    elif frac < 0.82:
                        col = "#FAC832"
                    else:
                        col = "#F0503C"
                else:
                    col = "#2C2516"
                ui.rect([bx, sy, bx+bw, sy+seg_h], fill=col)

    def _draw_dial(self, cx, cy, r):
        ui = self.ui
        ui.circle((cx+3, cy+3), r, fill="#00000064")
        ui.circle((cx, cy), r, fill="#C8D8E8")
        for a in range(0, 360, 3):
            rad = a * math.pi / 180
            r1 = r * 0.78
            r2 = r * 0.9
            x1 = cx + math.cos(rad) * r1
            y1 = cy + math.sin(rad) * r1
            x2 = cx + math.cos(rad) * r2
            y2 = cy + math.sin(rad) * r2
            color = "#1E3A5F"
            width = 2 if a % 15 == 0 else 1
            ui.active_draw.line([(x1, y1), (x2, y2)], fill=color, width=width)

    def _draw_needle(self, cx, cy, r, pct):
        ui = self.ui
        angle = math.radians(-120 + pct * 240)
        length = r * 0.8
        x2 = cx + math.cos(angle) * length
        y2 = cy + math.sin(angle) * length
        ui.active_draw.line([(cx, cy), (x2, y2)], fill="#D25014", width=4)
        ui.circle((cx, cy), 6, fill="#5A4628")

    def _draw_horizontal_dial(self, x_start, y, width, height, current_idx):
        ui = self.ui
        # 背景条
        ui.rect([x_start, y, x_start + width, y + height],
                fill="#1A1A2E", outline="#2A3A5F", radius=4)

        freq_idx = current_idx % 100
        pos = x_start + (freq_idx / 99) * width

        # 刻度：88~108 MHz，每1MHz一条
        for f in range(88, 109, 1):
            idx = f - 88
            x = x_start + (idx / 20) * width
            if idx % 5 == 0:
                ui.rect([x - 1, y + 4, x + 1, y + height - 4], fill="#B0C4DE")
                label = f"{f}.0"
                ui.text((x, y + height + 6), label, font_size=14, color="#7A8BA0", anchor="mt")
            else:
                ui.rect([x - 1, y + 10, x + 1, y + height - 10], fill="#5A6A7F")

        # 指针（红色竖线）
        ui.rect([pos - 1, y, pos + 1, y + height], fill="#FF4444")

        # 频率数字
        freq_value = 88.0 + (freq_idx / 99) * 20.0
        ui.text((x_start + width // 2, y - 6), f"FM {freq_value:.1f} MHz",
                font_size=18, color="#D2C3AA", anchor="mb")

    # ---------- 退出 ----------
    def quit(self):
        self._save_config()
        self.backlight.restore()
        self.player.stop()
        self.ui.draw_end()
        sys.exit(0)

    # ---------- 主循环 ----------
    def run(self):
        last_time = time.time()
        while True:
            now = time.time()
            dt = min(0.05, now - last_time)
            last_time = now

            self.handle_input()
            self.update(dt)
            self.draw()
            # 帧率控制约 30 FPS
            time.sleep(0.02)

# ============================
# 入口
# ============================
if __name__ == "__main__":
    app = RadioApp()

    try:
        app.run()
    except KeyboardInterrupt:
        app.quit()
    except Exception as e:
        LOGGER.exception("Unhandled exception")
        app.ui.draw_end()
        sys.exit(1)
