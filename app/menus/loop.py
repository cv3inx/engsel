from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich import box
from app.menus.purchase import purchase_loop
from app.menus.util import clear_screen, pause
from app.util import getScreen

WIDTH = getScreen()
console = Console()

def start_loop(package: dict):
    clear_screen()
    console.print("[bold cyan]Auto Purchase Loop :[/bold cyan]", justify="left")
    # --- Info Paket ---
    info = Table(
        show_header=False,
        box=box.SIMPLE_HEAVY,
        padding=(0, 1),
        width=WIDTH,
    )
    info.add_column("Info", style="grey70")
    info.add_column("Value", style="white")

    info.add_row("- Paket", str(package.get('name', '')))
    info.add_row("- Famcode", str(package.get('family_code', '')))
    info.add_row("- No Order", str(package.get('order', '')))

    console.print(info)
    
    # Garis tipis elegan
    console.print(Text("────────────────────────────────────────────", style="grey30"))

    # --- Input ---
    try:
        delay = int(Prompt.ask("ℹ Delay per attempt (detik)", default="10"))
    except ValueError:
        delay = 10

    pause_on_success = Confirm.ask("ℹ FPause setelah sukses?", default=True)

    # Tampilkan summary mode
    console.print()
    console.print(
        f"[grey70]Mode: decoy=ON, pause={'ON' if pause_on_success else 'OFF'}, delay={delay}s[/grey70]"
    )
    console.print("[bold green]Loop dimulai... (CTRL + C untuk stop)[/bold green]\n")

    # --- Loop utama ---
    while True:
        success = purchase_loop(
            family_code=package['family_code'],
            order=package['order'],
            use_decoy=True,
            delay=delay,
            pause_on_success=pause_on_success
        )

        if not success:
            console.print(f"\n[bold red]Loop dihentikan untuk paket '{package['name']}'[/bold red]")
            pause()
            break
