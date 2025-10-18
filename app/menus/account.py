from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.prompt import Prompt
from rich.table import Table

from app.util import getScreen

WIDTH = getScreen()
console: Console = Console(width=WIDTH)

from app.client.engsel import get_otp, submit_otp
from app.menus.util import clear_screen, pause
from app.service.auth import AuthInstance

def show_login_menu():
    clear_screen()
    title = Align.center("[bold white]MYXL AUTHENTICATION[/bold white]")
    console.print(Panel(title, style="grey23", border_style="grey35"))
    
    table = Table(show_header=False, box=None, padding=(0,1))
    table.add_row("1.", "Request OTP")
    table.add_row("2.", "Submit OTP")
    table.add_row("99.", "Tutup aplikasi")
    console.print(table)

def login_prompt(api_key: str):
    clear_screen()
    
    console.print(Panel(
        Align.center("[bold white]LOGIN KE MYXL[/bold white]"),
        style="grey23", border_style="grey35"
    ))
    
    phone_number = Prompt.ask("[grey70]Masukan nomor XL[/grey70]\n[white]Contoh: 6281234567890[/white]")

    if not phone_number.startswith("628") or len(phone_number) < 10 or len(phone_number) > 14:
        console.print("[bold red]Nomor tidak valid.[/bold red] Pastikan menggunakan format 628...")
        pause()
        return None

    try:
        subscriber_id = get_otp(phone_number)
        if not subscriber_id:
            return None
        
        console.print("[grey60]OTP berhasil dikirim ke nomor Anda.[/grey60]")
        otp = Prompt.ask("[white]Masukkan OTP (6 digit)[/white]")

        if not otp.isdigit() or len(otp) != 6:
            console.print("[bold red]OTP tidak valid.[/bold red]")
            pause()
            return None
        
        tokens = submit_otp(api_key, phone_number, otp)
        if not tokens:
            console.print("[bold red]Gagal login. Periksa OTP dan coba lagi.[/bold red]")
            pause()
            return None
        
        console.print("[bold green]Berhasil login.[/bold green]")
        return phone_number, tokens["refresh_token"]
    
    except Exception:
        return None, None

def show_account_menu():
    clear_screen()
    AuthInstance.load_tokens()
    users = AuthInstance.refresh_tokens
    active_user = AuthInstance.get_active_user()
    
    in_account_menu = True
    add_user = False
    while in_account_menu:
        clear_screen()
        
        if AuthInstance.get_active_user() is None or add_user:
            number, refresh_token = login_prompt(AuthInstance.api_key)
            if not refresh_token:
                console.print("[bold red]Gagal menambah akun.[/bold red]")
                pause()
                continue
            
            AuthInstance.add_refresh_token(int(number), refresh_token)
            AuthInstance.load_tokens()
            users = AuthInstance.refresh_tokens
            active_user = AuthInstance.get_active_user()
            
            if add_user:
                add_user = False
            continue
        
        panel_title = f"[bold white]AKUN TERSIMPAN[/bold white]"
        console.print(Panel(Align.center(panel_title), style="grey23", border_style="grey35"))
        
        if not users:
            console.print("[grey50]Tidak ada akun tersimpan.[/grey50]")
        else:
            for idx, user in enumerate(users):
                is_active = active_user and user["number"] == active_user["number"]
                style = "bold white" if is_active else "grey70"
                console.print(f"[{style}]{idx + 1}. {user['number']}{' (aktif)' if is_active else ''}[/]")
        
        console.print("\n[grey50]Command:[/grey50]")
        console.print(" [bold]0[/bold]: Tambah Akun")
        console.print(" [bold]00[/bold]: Kembali ke menu utama")
        console.print(" [bold]99[/bold]: Hapus Akun aktif")
        
        input_str = Prompt.ask("\n[white]Pilihan[/white]")
        
        if input_str == "00":
            return active_user["number"] if active_user else None
        elif input_str == "0":
            add_user = True
            continue
        elif input_str == "99":
            if not active_user:
                console.print("[bold red]Tidak ada akun aktif untuk dihapus.[/bold red]")
                pause()
                continue
            confirm = Prompt.ask(f"[grey70]Yakin ingin menghapus akun {active_user['number']}?[/grey70] (y/n)")
            if confirm.lower() == 'y':
                AuthInstance.remove_refresh_token(active_user["number"])
                users = AuthInstance.refresh_tokens
                active_user = AuthInstance.get_active_user()
                console.print("[bold green]Akun berhasil dihapus.[/bold green]")
                pause()
            continue
        elif input_str.isdigit() and 1 <= int(input_str) <= len(users):
            return users[int(input_str) - 1]['number']
        else:
            console.print("[bold red]Input tidak valid.[/bold red]")
            pause()
