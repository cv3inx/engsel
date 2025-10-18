from dotenv import load_dotenv
load_dotenv()

import sys
import os

from datetime import datetime
from app.client.engsel import *
from app.client.engsel2 import get_tiering_info
from app.menus.util import clear_screen, pause
from app.service.auth import AuthInstance
from app.menus.account import show_account_menu
from app.menus.purchase import purchase_by_family, purchase_loop
from app.menus.family_bookmark import show_family_bookmark_menu
import requests
from app.menus.loop import start_loop
from app.menus.bot import run_edubot
from app.util import get_api_key, save_api_key, getScreen, PACKAGES_URL
from app.service.util import fetch_api_key_from_remote, ensure_api_key
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich.prompt import Prompt
from rich import box

WIDTH = getScreen()
console: Console = Console(width=WIDTH)

def fetch_packages():
    """Mengambil daftar paket dengan spinner dan penanganan error yang lebih baik."""
    response = None
    with console.status("[bold green]Mengambil daftar paket...", spinner="dots") as status:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(PACKAGES_URL, timeout=10, headers=headers)
            response.raise_for_status()
            return response.json().get("packages", {})
        except Exception as e:
            return {}

def show_main_menu(packages, active_user):
    """Menampilkan UI menu utama yang sederhana tanpa Layout."""
    clear_screen()
    table = Table(
        title=f"[bold]Profile Info[/bold]",
        title_style="bold not italic",
        box=box.HEAVY_HEAD,
        header_style="bold cyan",
        show_header=True,
        width=WIDTH
    )
    expired_at_dt = datetime.fromtimestamp(active_user["balance_expired_at"]).strftime("%Y-%m-%d")
    table.add_column("Name", style="dim", width=5)
    table.add_column("Info")
    table.add_row("Nomor", f"{active_user['number']}")
    table.add_row("Type", f"{active_user['subscription_type']}")
    table.add_row("Pulsa", f"Rp {active_user['balance']}")
    table.add_row("Expired", f"{expired_at_dt}")
    table.add_row("Point", f"{active_user['point_info']}")
    console.print(Align.left(table))


    table = Table(
        box=box.HEAVY_HEAD,
        header_style="bold cyan",
        show_header=True,
        width=WIDTH
    )
    table.add_column("ID", style="dim", justify="center")
    table.add_column("Deskripsi Menu")
    table.add_column("Status")

    # --- Grup Menu ---
    table.add_row("1", "👤 Login / Ganti Akun")
    table.add_row("2", "🛒 [Test] Beli Semua Paket")
    table.add_section()

    if packages:
        for i, pkg in enumerate(packages, start=3):
            status = pkg.get('status', 'N/A').lower()
            status_style = "green" if status == 'good' else "yellow" if status == 'test' else "red"
            name = pkg.get('name', 'Tanpa Nama')
            status_text = f"[{status_style}]({status.capitalize()})[/{status_style}]"
            table.add_row(str(i), f"📦 {name}", status_text)
    else:
        table.add_row("-", "📭 [yellow]Tidak ada paket aktif ditemukan.[/yellow]")
    table.add_section()
    table.add_row("C", "🔧 Mode Custom (family code + order)")
    table.add_row("B", "🔖 Bookmark Family Code")
    table.add_row("P", "📊 Pantau Sisa Kuota")
    table.add_section()
    table.add_row("0", "📜 Original Menu (Legacy)")
    table.add_row("[bold red]99[/bold red]", "🚪 Keluar Aplikasi")

    console.print(Align.left(table))


def main():
    AuthInstance.api_key = ensure_api_key(None, "apikey.anomali")
    packages = fetch_packages()
    while True:
        active_user = AuthInstance.get_active_user()
        if active_user is not None:
            balance = get_balance(AuthInstance.api_key, active_user["tokens"]["id_token"])
            balance_remaining = balance.get("remaining")
            balance_expired_at = balance.get("expired_at")
            
            profile_data = get_profile(AuthInstance.api_key, active_user["tokens"]["access_token"], active_user["tokens"]["id_token"])
            sub_id = profile_data["profile"]["subscriber_id"]
            sub_type = profile_data["profile"]["subscription_type"]
            
            point_info = "[bold]Points[/bold]: N/A | [bold]Tier[/bold]: N/A"
            
            if sub_type == "PREPAID":
                tiering_data = get_tiering_info(AuthInstance.api_key, active_user["tokens"])
                tier = tiering_data.get("tier", 0)
                current_point = tiering_data.get("current_point", 0)
                point_info = f"[bold]Points[/bold]: {current_point} | [bold]Tier[/bold]: {tier}"
            
            user = {
                "number": active_user["number"],
                "subscriber_id": sub_id,
                "subscription_type": sub_type,
                "balance": balance_remaining,
                "balance_expired_at": balance_expired_at,
                "point_info": point_info
            }

            show_main_menu(packages, user)
            choice = Prompt.ask("\n[bold]Pilih menu[/bold]", default="")

            if choice == "0":
                os.system(f'"{sys.executable}" master.py'); continue
            elif choice == "1":
                selected_user_number = show_account_menu()
                if selected_user_number: AuthInstance.set_active_user(selected_user_number)
                else: console.print("[red]Tidak ada user yang dipilih atau gagal memuat user.[/red]")
                continue
            elif choice == "2":
                family_code = Prompt.ask("Masukkan family code (atau '99' untuk batal)", default="99")
                if family_code == "99": continue
                use_decoy = Prompt.ask("Gunakan paket decoy?", choices=["y", "n"], default="y") == 'y'
                pause_on_success = Prompt.ask("Aktifkan mode jeda?", choices=["y", "n"], default="y") == 'y'
                purchase_by_family(family_code, use_decoy, pause_on_success); continue
            elif choice == "99":
                console.print(Panel("[bold green]Terima kasih telah menggunakan aplikasi ini! Sampai jumpa lagi.[/bold green] 👋"))
                sys.exit(0)

            # --- Menu Baru: Input String ---
            elif choice.upper() == "C":
                family_code = Prompt.ask("Masukkan family code (atau '99' untuk batal)", default="99")
                if family_code == "99": continue
                orders_input = Prompt.ask("Masukkan 1 atau lebih nomor order (contoh: 1 atau 1,2,3)")
                orders = [int(o.strip()) for o in orders_input.split(',')]
                delay = int(Prompt.ask("Masukkan jeda (detik)", default="5"))
                pause_on_success = Prompt.ask("Aktifkan jeda saat sukses?", choices=["y", "n"]) == 'y'
                # Looping logic remains the same
                while True:
                    for order in orders:
                        console.print(f"Memproses order {order}...")
                        if not purchase_loop(family_code, order, True, delay, pause_on_success):
                            console.print(f"[red]Pembelian order {order} gagal. Berhenti.[/red]")
                            break
                    else: continue
                    break
            elif choice.upper() == "B":
                show_family_bookmark_menu()
            elif choice.upper() == "P":
                run_edubot()
            elif choice == "":
                main()
            else:
                try:
                    choice_int = int(choice)
                    if 3 <= choice_int < 3 + len(packages):
                        selected_package = packages[choice_int - 3]
                        start_loop(selected_package); continue
                    else:
                        console.print("[bold red]Pilihan tidak valid. Coba lagi.[/bold red]"); pause()
                except ValueError:
                    console.print("[bold red]Input tidak valid. Masukkan angka atau huruf menu.[/bold red]"); pause()
        else:
            selected_user_number = show_account_menu()
            if selected_user_number: AuthInstance.set_active_user(selected_user_number)
            else: console.print("[red]Tidak ada user yang dipilih atau gagal memuat user.[/red]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Aplikasi ditutup oleh pengguna.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Terjadi error yang tidak terduga:[/bold red]")
        console.print_exception()