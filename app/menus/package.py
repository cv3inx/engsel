import json
import sys
import requests

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich import box

from app.client.encrypt import BASE_CRYPTO_URL
from app.service.auth import AuthInstance
from app.client.engsel import get_family, get_package, get_addons, get_package_details, send_api_request
from app.service.bookmark import BookmarkInstance
from app.client.purchase import settlement_bounty, settlement_loyalty
from app.menus.util import clear_screen, pause, display_html, wrap_text
from app.client.qris import show_qris_payment
from app.client.ewallet import show_multipayment
from app.client.balance import settlement_balance
from app.type_dict import PaymentItem
from app.menus.purchase import purchase_n_times

console = Console()


def show_package_details(api_key, tokens, package_option_code, is_enterprise, option_order=-1):
    clear_screen()
    
    package = get_package(api_key, tokens, package_option_code)
    if not package:
        console.print("[red]Failed to load package details.[/red]")
        pause()
        return False

    price = package["package_option"]["price"]
    detail = display_html(package["package_option"]["tnc"])
    validity = package["package_option"]["validity"]

    option_name = package.get("package_option", {}).get("name", "")
    family_name = package.get("package_family", {}).get("name", "")
    variant_name = package.get("package_detail_variant", "").get("name", "")
    
    title = f"{family_name} - {variant_name} - {option_name}".strip()
    
    token_confirmation = package["token_confirmation"]
    ts_to_sign = package["timestamp"]
    payment_for = package["package_family"]["payment_for"]
    
    payment_items = [
        PaymentItem(
            item_code=package_option_code,
            product_type="",
            item_price=price,
            item_name=f"{variant_name} {option_name}".strip(),
            tax=0,
            token_confirmation=token_confirmation,
        )
    ]
    
    # Package Info Panel
    info_table = Table(show_header=False, box=box.ROUNDED, padding=(0, 1))
    info_table.add_column("Field", style="cyan", width=15)
    info_table.add_column("Value", style="white")
    
    info_table.add_row("Nama", title)
    info_table.add_row("Harga", f"Rp {price:,}")
    info_table.add_row("Payment For", payment_for)
    info_table.add_row("Masa Aktif", validity)
    info_table.add_row("Point", str(package['package_option']['point']))
    info_table.add_row("Plan Type", package['package_family']['plan_type'])
    
    console.print(Panel(info_table, title="[bold]Detail Paket[/bold]", border_style="blue"))
    
    # Benefits Table
    benefits = package["package_option"]["benefits"]
    if benefits and isinstance(benefits, list):
        benefit_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        benefit_table.add_column("Name", style="cyan", overflow="fold")
        benefit_table.add_column("Item ID", style="yellow", justify="center")
        benefit_table.add_column("Total/Quota", style="green", justify="right")
        benefit_table.add_column("Unlimited", style="red", justify="center")
        
        for benefit in benefits:
            name = benefit['name'] if benefit['name']  else "None" 
            item_id = benefit['item_id'] if benefit['item_id']  else "None" 
            data_type = benefit['data_type'] if benefit['data_type']  else "None" 
            is_unlimited = "Yes ✓" if benefit["is_unlimited"] else "No"
            
            quota_str = ""
            if data_type == "VOICE" and benefit['total'] > 0:
                quota_str = f"{benefit['total']/60:.0f} menit"
            elif data_type == "TEXT" and benefit['total'] > 0:
                quota_str = f"{benefit['total']} SMS"
            elif data_type == "DATA" and benefit['total'] > 0:
                quota = int(benefit['total'])
                if quota >= 1_000_000_000:
                    quota_gb = quota / (1024 ** 3)
                    quota_str = f"{quota_gb:.2f} GB"
                elif quota >= 1_000_000:
                    quota_mb = quota / (1024 ** 2)
                    quota_str = f"{quota_mb:.2f} MB"
                elif quota >= 1_000:
                    quota_kb = quota / 1024
                    quota_str = f"{quota_kb:.2f} KB"
                else:
                    quota_str = str(quota)
            elif data_type not in ["DATA", "VOICE", "TEXT"]:
                quota_str = f"{benefit['total']} ({data_type})"
            
            benefit_table.add_row(name, item_id, quota_str, is_unlimited)
        
        console.print(Panel(benefit_table, title="[bold]Benefits[/bold]", border_style="green"))
    
    # Addons
    addons = get_addons(api_key, tokens, package_option_code)
    console.print(Panel(f"[dim]{json.dumps(addons, indent=2)}[/dim]", title="[bold]Addons[/bold]", border_style="yellow"))
    
    # Terms & Conditions
    console.print(Panel(detail, title="[bold]Syarat & Ketentuan MyXL[/bold]", border_style="red"))
    
    # Set default payment_for
    if payment_for == "":
        payment_for = "BUY_PACKAGE"
    
    in_package_detail_menu = True
    while in_package_detail_menu:
        # Options Menu
        menu_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
        menu_table.add_column("No", style="cyan")
        menu_table.add_column("Option", style="white")
        
        menu_table.add_row("1", "Beli dengan Pulsa")
        menu_table.add_row("2", "Beli dengan E-Wallet")
        menu_table.add_row("3", "Bayar dengan QRIS")
        menu_table.add_row("4", "Pulsa + Decoy XCP")
        menu_table.add_row("5", "Pulsa + Decoy XCP V2")
        menu_table.add_row("6", "Pulsa N kali")
        menu_table.add_row("7", "QRIS + Decoy Edu")
        
        if payment_for == "REDEEM_VOUCHER":
            menu_table.add_row("B", "Ambil sebagai bonus (jika tersedia)")
            menu_table.add_row("L", "Beli dengan Poin (jika tersedia)")
        
        if option_order != -1:
            menu_table.add_row("0", "Tambah ke Bookmark")
        menu_table.add_row("00", "Kembali ke daftar paket")
        
        console.print(Panel(menu_table, title="[bold]Menu Pembelian[/bold]", border_style="cyan"))

        choice = console.input("[bold yellow]Pilihan: [/bold yellow]")
        
        if choice == "00":
            return False
        1
        if choice == "0" and option_order != -1:
            success = BookmarkInstance.add_bookmark(
                family_code=package.get("package_family", {}).get("package_family_code", ""),
                family_name=package.get("package_family", {}).get("name", ""),
                is_enterprise=is_enterprise,
                variant_name=variant_name,
                option_name=option_name,
                order=option_order,
            )
            if success:
                console.print("[green]Paket berhasil ditambahkan ke bookmark.[/green]")
            else:
                console.print("[yellow]Paket sudah ada di bookmark.[/yellow]")
            pause()
            continue
        
        if choice == '1':
            settlement_balance(api_key, tokens, payment_items, payment_for, True)
            console.input("[green]Silahkan cek hasil pembelian di aplikasi MyXL. Tekan Enter untuk kembali.[/green]")
            return True
        
        elif choice == '2':
            show_multipayment(api_key, tokens, payment_items, payment_for, True)
            console.input("[green]Silahkan lakukan pembayaran & cek hasil pembelian di aplikasi MyXL. Tekan Enter untuk kembali.[/green]")
            return True
        
        elif choice == '3':
            show_qris_payment(api_key, tokens, payment_items, payment_for, True)
            console.input("[green]Silahkan lakukan pembayaran & cek hasil pembelian di aplikasi MyXL. Tekan Enter untuk kembali.[/green]")
            return True
        
        elif choice in ['4', '5']:
            # Balance; Decoy XCP
            url = BASE_CRYPTO_URL + "/decoyxcp"
            
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                console.print("[red]Gagal mengambil data decoy package.[/red]")
                pause()
                return None
            
            decoy_data = response.json()
            decoy_package_detail = get_package_details(
                api_key, tokens,
                decoy_data["family_code"],
                decoy_data["variant_code"],
                decoy_data["order"],
                decoy_data["is_enterprise"],
                decoy_data["migration_type"],
            )

            payment_items.append(
                PaymentItem(
                    item_code=decoy_package_detail["package_option"]["package_option_code"],
                    product_type="",
                    item_price=decoy_package_detail["package_option"]["price"],
                    item_name=decoy_package_detail["package_option"]["name"],
                    tax=0,
                    token_confirmation=decoy_package_detail["token_confirmation"],
                )
            )

            overwrite_amount = price + decoy_package_detail["package_option"]["price"]
            token_idx = -1 if choice == '5' else None
            
            res = settlement_balance(
                api_key, tokens, payment_items, "BUY_PACKAGE", False,
                overwrite_amount,
                token_confirmation_idx=token_idx
            )
            
            if res and res.get("status", "") != "SUCCESS":
                error_msg = res.get("message", "Unknown error")
                if "Bizz-err.Amount.Total" in error_msg:
                    error_msg_arr = error_msg.split("=")
                    valid_amount = int(error_msg_arr[1].strip())
                    
                    console.print(f"[yellow]Adjusted total amount to: {valid_amount}[/yellow]")
                    res = settlement_balance(
                        api_key, tokens, payment_items, "BUY_PACKAGE", False,
                        valid_amount,
                        token_confirmation_idx=token_idx
                    )
                    if res and res.get("status", "") == "SUCCESS":
                        console.print("[green]Purchase successful![/green]")
            else:
                console.print("[green]Purchase successful![/green]")
            pause()
            return True
        
        elif choice == '6':
            use_decoy = console.input("[yellow]Use decoy package? (y/n): [/yellow]").strip().lower() == 'y'
            n_times_str = console.input("[yellow]Enter number of times to purchase: [/yellow]").strip()
            try:
                n_times = int(n_times_str)
                if n_times < 1:
                    raise ValueError("Number must be at least 1.")
            except ValueError:
                console.print("[red]Invalid number entered. Please enter a valid integer.[/red]")
                pause()
                continue
            
            purchase_n_times(
                n_times,
                family_code=package.get("package_family", {}).get("package_family_code", ""),
                variant_code=package.get("package_detail_variant", {}).get("package_variant_code", ""),
                option_order=option_order,
                use_decoy=use_decoy,
                pause_on_success=False,
            )
        
        elif choice == '7':
            # QRIS; Decoy Edu
            url = "https://pastebin.com/raw/c4JBxxhu"
            
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                console.print("[red]Gagal mengambil data decoy package.[/red]")
                pause()
                return None
            
            decoy_data = response.json()
            decoy_package_detail = get_package_details(
                api_key, tokens,
                decoy_data["family_code"],
                decoy_data["variant_code"],
                decoy_data["order"],
                decoy_data["is_enterprise"],
                decoy_data["migration_type"],
            )

            payment_items.append(
                PaymentItem(
                    item_code=decoy_package_detail["package_option"]["package_option_code"],
                    product_type="",
                    item_price=decoy_package_detail["package_option"]["price"],
                    item_name=decoy_package_detail["package_option"]["name"],
                    tax=0,
                    token_confirmation=decoy_package_detail["token_confirmation"],
                )
            )
            
            price_table = Table(show_header=False, box=box.DOUBLE)
            price_table.add_column("Item", style="cyan")
            price_table.add_column("Price", style="green", justify="right")
            price_table.add_row("Harga Paket Utama", f"Rp {price:,}")
            price_table.add_row("Harga Decoy Paket Edu", f"Rp {decoy_package_detail['package_option']['price']:,}")
            
            console.print(Panel(price_table, title="[bold]Silahkan sesuaikan amount (trial & error)[/bold]"))

            show_qris_payment(
                api_key, tokens, payment_items, "BUY_PACKAGE", True,
                token_confirmation_idx=1
            )
            
            console.input("[green]Silahkan lakukan pembayaran & cek hasil pembelian di aplikasi MyXL. Tekan Enter untuk kembali.[/green]")
            return True
        
        elif choice.lower() == 'b':
            settlement_bounty(
                api_key=api_key, tokens=tokens,
                token_confirmation=token_confirmation,
                ts_to_sign=ts_to_sign,
                payment_target=package_option_code,
                price=price,
                item_name=variant_name
            )
            console.input("[green]Silahkan lakukan pembayaran & cek hasil pembelian di aplikasi MyXL. Tekan Enter untuk kembali.[/green]")
            return True
        
        elif choice.lower() == 'l':
            settlement_loyalty(
                api_key=api_key, tokens=tokens,
                token_confirmation=token_confirmation,
                ts_to_sign=ts_to_sign,
                payment_target=package_option_code,
                price=price,
            )
            console.input("[green]Silahkan lakukan pembayaran & cek hasil pembelian di aplikasi MyXL. Tekan Enter untuk kembali.[/green]")
            return True
        
        else:
            console.print("[red]Purchase cancelled.[/red]")
            return False
    
    pause()
    sys.exit(0)


def get_packages_by_family(family_code: str, is_enterprise: bool | None = None, migration_type: str | None = None):
    api_key = AuthInstance.api_key
    tokens = AuthInstance.get_active_tokens()
    if not tokens:
        console.print("[red]No active user tokens found.[/red]")
        pause()
        return None
    
    packages = []
    
    data = get_family(api_key, tokens, family_code, is_enterprise, migration_type)
    
    if not data:
        console.print("[red]Failed to load family data.[/red]")
        pause()
        return None
    
    price_currency = "Rp"
    rc_bonus_type = data["package_family"].get("rc_bonus_type", "")
    if rc_bonus_type == "MYREWARDS":
        price_currency = "Poin"
    
    in_package_menu = True
    while in_package_menu:
        clear_screen()
        
        # Family Info Panel
        family_info = Table(show_header=False, box=box.ROUNDED)
        family_info.add_column("Field", style="cyan", width=15)
        family_info.add_column("Value", style="white")
        
        family_info.add_row("Family Name", data['package_family']['name'])
        family_info.add_row("Family Code", family_code)
        family_info.add_row("Family Type", data['package_family']['package_family_type'])
        family_info.add_row("Variant Count", str(len(data['package_variants'])))
        
        console.print(Panel(family_info, title="[bold]Family Information[/bold]", border_style="blue"))
        
        # Packages Table
        package_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        package_table.add_column("No", style="cyan", justify="center", width=5)
        package_table.add_column("Variant", style="yellow", overflow="fold")
        package_table.add_column("Paket", style="white", overflow="fold")
        package_table.add_column("Harga", style="green", justify="right", width=15)
        
        package_variants = data["package_variants"]
        
        option_number = 1
        variant_number = 1
        
        for variant in package_variants:
            variant_name = variant["name"]
            variant_code = variant["package_variant_code"]
            
            for idx, option in enumerate(variant["package_options"]):
                option_name = option["name"]
                
                packages.append({
                    "number": option_number,
                    "variant_name": variant_name,
                    "option_name": option_name,
                    "price": option["price"],
                    "code": option["package_option_code"],
                    "option_order": option["order"]
                })
                
                display_variant = variant_name if idx == 0 else ""
                package_table.add_row(
                    str(option_number),
                    display_variant,
                    option_name,
                    f"{price_currency} {option['price']:,}"
                )
                
                option_number += 1
            
            variant_number += 1
        
        console.print(Panel(package_table, title="[bold]Paket Tersedia[/bold]", border_style="green"))
        console.print("[dim]00. Kembali ke menu utama[/dim]")
        
        pkg_choice = console.input("[bold yellow]Pilih paket (nomor): [/bold yellow]")
        
        if pkg_choice == "00":
            in_package_menu = False
            return None
        
        selected_pkg = next((p for p in packages if p["number"] == int(pkg_choice)), None)
        
        if not selected_pkg:
            console.print("[red]Paket tidak ditemukan. Silakan masukan nomor yang benar.[/red]")
            pause()
            continue
        
        is_done = show_package_details(api_key, tokens, selected_pkg["code"], is_enterprise, option_order=selected_pkg["option_order"])
        if is_done:
            in_package_menu = False
            return None
        else:
            continue
    
    return packages


def fetch_my_packages():
    api_key = AuthInstance.api_key
    tokens = AuthInstance.get_active_tokens()
    if not tokens:
        console.print("[red]No active user tokens found.[/red]")
        pause()
        return None
    
    id_token = tokens.get("id_token")
    path = "api/v8/packages/quota-details"
    
    payload = {
        "is_enterprise": False,
        "lang": "en",
        "family_member_id": ""
    }
    
    console.print("[yellow]Fetching my packages...[/yellow]")
    res = send_api_request(api_key, path, payload, id_token, "POST")
    
    if res.get("status") != "SUCCESS":
        console.print("[red]Failed to fetch packages[/red]")
        console.print(f"Response: {res}")
        pause()
        return None
    
    quotas = res["data"]["quotas"]
    
    clear_screen()
    console.print(Panel("[bold cyan]My Packages[/bold cyan]", style="bold blue"))
    
    my_packages = []
    num = 1
    
    for quota in quotas:
        quota_code = quota["quota_code"]
        group_code = quota["group_code"]
        group_name = quota["group_name"]
        quota_name = quota["name"]
        family_code = "N/A"
        
        benefits = quota.get("benefits", [])
        
        console.print(f"[yellow]Fetching package no. {num} details...[/yellow]")
        package_details = get_package(api_key, tokens, quota_code)
        if package_details:
            family_code = package_details["package_family"]["package_family_code"]
        
        # Package Info
        pkg_info = Table(show_header=False, box=box.ROUNDED)
        pkg_info.add_column("Field", style="cyan", width=15)
        pkg_info.add_column("Value", style="white")
        
        pkg_info.add_row("Name", quota_name)
        pkg_info.add_row("Group Name", group_name)
        pkg_info.add_row("Quota Code", quota_code)
        pkg_info.add_row("Family Code", family_code)
        pkg_info.add_row("Group Code", group_code)
        
        console.print(Panel(pkg_info, title=f"[bold]Package {num}[/bold]", border_style="green"))
        
        # Benefits Table
        if len(benefits) > 0:
            benefit_table = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
            benefit_table.add_column("ID", style="yellow", width=10)
            benefit_table.add_column("Name", style="cyan", overflow="fold")
            benefit_table.add_column("Type", style="blue", width=8)
            benefit_table.add_column("Quota", style="green", justify="right", width=20)
            
            for benefit in benefits:
                benefit_id = benefit.get("id", "")
                name = benefit.get("name", "")
                data_type = benefit.get("data_type", "N/A")
                remaining = benefit.get("remaining", 0)
                total = benefit.get("total", 0)
                
                quota_str = ""
                if data_type == "DATA":
                    if remaining >= 1_000_000_000:
                        remaining_str = f"{remaining / (1024 ** 3):.2f} GB"
                    elif remaining >= 1_000_000:
                        remaining_str = f"{remaining / (1024 ** 2):.2f} MB"
                    elif remaining >= 1_000:
                        remaining_str = f"{remaining / 1024:.2f} KB"
                    else:
                        remaining_str = str(remaining)
                    
                    if total >= 1_000_000_000:
                        total_str = f"{total / (1024 ** 3):.2f} GB"
                    elif total >= 1_000_000:
                        total_str = f"{total / (1024 ** 2):.2f} MB"
                    elif total >= 1_000:
                        total_str = f"{total / 1024:.2f} KB"
                    else:
                        total_str = str(total)
                    
                    quota_str = f"{remaining_str} / {total_str}"
                elif data_type == "VOICE":
                    quota_str = f"{remaining/60:.2f} / {total/60:.2f} menit"
                elif data_type == "TEXT":
                    quota_str = f"{remaining} / {total} SMS"
                else:
                    quota_str = f"{remaining} / {total}"
                
                benefit_table.add_row(benefit_id, name, data_type, quota_str)
            
            console.print(Panel(benefit_table, title="[bold]Benefits[/bold]", border_style="blue"))
        
        my_packages.append({
            "number": num,
            "quota_code": quota_code,
        })
        
        num += 1
    
    console.print("\n[bold cyan]Rebuy package? Input package number to rebuy, or '00' to back.[/bold cyan]")
    choice = console.input("[bold yellow]Choice: [/bold yellow]")
    
    if choice == "00":
        return None
    
    selected_pkg = next((pkg for pkg in my_packages if str(pkg["number"]) == choice), None)
    
    if not selected_pkg:
        console.print("[red]Paket tidak ditemukan. Silakan masukan nomor yang benar.[/red]")
        pause()
        return None
    
    is_done = show_package_details(api_key, tokens, selected_pkg["quota_code"], False)
    if is_done:
        return None
    
    pause()