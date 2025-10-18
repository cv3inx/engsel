import os
import re
import json
import textwrap
from typing import List, Dict, Optional, Any
from html.parser import HTMLParser

import requests
from rich.console import Console
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
from rich import box
from rich.spinner import Spinner
from rich.live import Live

from app.util import getScreen, NOTIF_URL  # Pastikan ada di app/util.py

# --- Konfigurasi Global ---
WIDTH = getScreen()
console: Console = Console(width=WIDTH)

# --- Kelas Style (opsional) ---
class Style:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    WHITE = '\033[97m'
    RESET = '\033[0m'

# --- HTML to Text Parser ---
class HTMLToText(HTMLParser):
    """
    Parser sederhana untuk mengonversi HTML ke teks biasa.
    """
    def __init__(self, width: int = 80):
        super().__init__()
        self.width: int = width
        self.result: List[str] = []
        self.in_li: bool = False

    def handle_starttag(self, tag: str, attrs):
        if tag == "li":
            self.in_li = True
        elif tag == "br":
            self.result.append("\n")

    def handle_endtag(self, tag: str):
        if tag == "li":
            self.in_li = False
            self.result.append("\n")

    def handle_data(self, data):
        text = data.strip()
        if text:
            prefix = "- " if self.in_li else ""
            self.result.append(f"{prefix}{text}")

    def get_text(self) -> str:
        text = "".join(self.result)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return "\n".join(textwrap.wrap(text, width=self.width, replace_whitespace=False))

def display_html(html_text: str, width: int = 80) -> str:
    """
    Konversi string HTML ke teks biasa dengan format dasar.
    """
    parser = HTMLToText(width=width)
    parser.feed(html_text)
    return parser.get_text()

# --- Fungsi Utilitas Umum ---
def clear_screen():
    """
    Bersihkan layar dan tampilkan header dengan notifikasi opsional.
    """
    os.system('cls' if os.name == 'nt' else 'clear')

    header_text = Text("Special Thx for Baka Mitai 😘", style="bold magenta")
    console.print(Align.center(header_text, width=WIDTH))
    console.print("=" * WIDTH)

    notif = load_notifications(NOTIF_URL)
    if notif:
        pesan_val = notif.get("pesan", "").strip()
        full_text = pesan_val if pesan_val and pesan_val != "-" else Align.center("Tidak ada notifikasi terbaru", width=WIDTH)

        panel = Panel(
            full_text,
            title=f"[ {notif.get('type', 'N/A')} ]",
            title_align="center",
            subtitle=f"[ {notif.get('footer', 'N/A')} ]",
            subtitle_align="center",
            box=box.ROUNDED,
            style="blue",
            width=WIDTH,
        )
        console.print(panel)

    console.print()

def print_header(title: str):
    """
    Cetak header rapi terpusat dengan pemisah.
    """
    clear_screen()
    console.print(Align.center(f"[bold]{title}[/]", width=WIDTH))
    console.print("=" * WIDTH)

def pause():
    """
    Jeda eksekusi dan tunggu input pengguna.
    """
    console.input("\n[bold yellow]Press Enter to continue...[/]")

def format_quota(byte_val: Optional[int]) -> str:
    """
    Format nilai byte menjadi string mudah dibaca (B, KB, MB, dll.).
    """
    if byte_val is None:
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(byte_val)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"

def wrap_text(text: str, width: int = WIDTH) -> str:
    """
    Bungkus teks sesuai lebar, tetap pertahankan baris baru.
    """
    lines = text.split('\n')
    wrapped = []
    for line in lines:
        if line.strip():
            wrapped.extend(textwrap.wrap(line, width=width))
        else:
            wrapped.append("")
    return "\n".join(wrapped)

def load_notifications(url: str) -> Dict[str, Any]:
    """
    Ambil dan parsing notifikasi JSON dari URL remote.
    Format JSON: {"type": "...", "pesan": "...", "footer": "..."}
    """
    spinner = Spinner("dots", text="Loading notifications...")
    with Live(spinner, refresh_per_second=12, transient=True):
        try:
            response = requests.get(url.strip(), timeout=5)
            response.raise_for_status()
            data = response.json()
            if not data:
                console.log("[dim]Tidak ada notifikasi valid ditemukan.[/dim]")
            return data
        except requests.exceptions.RequestException as e:
            console.log(f"[red]Gagal mengambil notifikasi (Request Error): {e}[/red]")
            return {}
        except json.JSONDecodeError:
            console.log("[red]Gagal mem-parsing JSON dari notifikasi.[/red]")
            return {}
        except Exception as e:
            console.log(f"[red]Gagal mengambil notifikasi (Error tak terduga): {e}[/red]")
            return {}
