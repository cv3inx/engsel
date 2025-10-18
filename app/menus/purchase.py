from random import randint
import requests
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.align import Align
from rich.text import Text
from rich import box

from app.client.encrypt import BASE_CRYPTO_URL
from app.client.engsel import get_family, get_package_details

from app.menus.util import pause
from app.service.auth import AuthInstance
from app.type_dict import PaymentItem
from app.client.balance import settlement_balance

from app.util import getScreen
WIDTH = getScreen()
console = Console()


def _fmt_rp(value):
    try:
        return f"Rp{int(value):,}".replace(",", ".")
    except Exception:
        return str(value)


def _panel(title: str, body: str, border_style: str = "grey35", subtitle: str | None = None):
    """Helper: buat Panel konsisten."""
    return Panel(
        Align.left(body),
        title=f"[bold white]{title}[/bold white]",
        subtitle=subtitle or "",
        padding=(1, 2),
        box=box.ROUNDED,
        border_style=border_style,
    )


def purchase_loop(
    family_code: str,
    order: int,
    use_decoy: bool,
    delay: int,
    pause_on_success: bool = False,
):
    api_key = AuthInstance.api_key
    tokens: dict = AuthInstance.get_active_tokens() or {}

    # 1. Find the package variant and option from the order
    family_data = get_family(api_key, tokens, family_code)
    if not family_data:
        console.print(_panel("Family Error", f"Failed to get family data for code: {family_code}.", "red"))
        pause()
        return False  # Stop the loop in maincopy.py

    target_variant = None
    target_option = None
    for variant in family_data["package_variants"]:
        for option in variant["package_options"]:
            if option["order"] == order:
                target_variant = variant
                target_option = option
                break
        if target_option:
            break

    if not target_option or not target_variant:
        console.print(_panel("Not Found", f"Option order {order} not found in family {family_code}.", "red"))
        pause()
        return False  # Stop the loop

    option_name = target_option["name"]
    option_price = target_option["price"]
    variant_code = target_variant["package_variant_code"]

    table = Table(
            title="[bold]Trying to Buy[/bold]",
            title_style="bold",
            box=box.HEAVY_HEAD,
            header_style="bold cyan",
            show_header=True,
            width=WIDTH
        )

    table.add_column("Name", style="bold")
    table.add_column("Deskripsi")

    table.add_row("Family",   f"[grey70]{family_data['package_family']['name']}[/grey70]")
    table.add_row("Variant",  f"[grey70]{target_variant['name']}[/grey70]")
    table.add_row("Famcode",  f"[grey70]{variant_code}[/grey70]")
    table.add_row("Option",   f"[grey70]{order}. {option_name}[/grey70]")
    table.add_row("Price",    f"[bold]{_fmt_rp(option_price)}[/bold]")  # bold biar menonjol

    console.print(Align.left(table))


    # 2. Decoy logic
    decoy_package_detail = None
    decoy_data = None
    if use_decoy:
        url = BASE_CRYPTO_URL + "/decoyxcp"
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                console.print(_panel("Decoy", "Gagal mengambil data decoy package.", "yellow"))
            else:
                decoy_data = response.json()
                decoy_package_detail = get_package_details(
                    api_key,
                    tokens,
                    decoy_data["family_code"],
                    decoy_data["variant_code"],
                    decoy_data["order"],
                    decoy_data["is_enterprise"],
                    decoy_data["migration_type"],
                )
        except Exception as e:
            console.print(_panel("Decoy Error", f"Exception saat ambil decoy: {e}", "yellow"))

    # 3. Prepare payment items
    payment_items = []
    try:
        target_package_detail = get_package_details(
            api_key,
            tokens,
            family_code,
            variant_code,
            order,
            None,
            None,
        )
    except Exception as e:
        console.print(_panel("Package Detail Error", f"Exception occurred while fetching package details: {e}", "red"))
        time.sleep(delay)
        return True  # Continue loop

    payment_items.append(
        PaymentItem(
            item_code=target_package_detail["package_option"]["package_option_code"],
            product_type="",
            item_price=target_package_detail["package_option"]["price"],
            item_name=str(randint(1000, 9999)) + target_package_detail["package_option"]["name"],
            tax=0,
            token_confirmation=target_package_detail["token_confirmation"],
        )
    )

    if use_decoy and decoy_package_detail:
        payment_items.append(
            PaymentItem(
                item_code=decoy_package_detail["package_option"]["package_option_code"],
                product_type="",
                item_price=decoy_package_detail["package_option"]["price"],
                item_name=str(randint(1000, 9999)) + decoy_package_detail["package_option"]["name"],
                tax=0,
                token_confirmation=decoy_package_detail["token_confirmation"],
            )
        )

    # 4. Settle payment
    overwrite_amount = target_package_detail["package_option"]["price"]
    if use_decoy and decoy_package_detail:
        overwrite_amount += decoy_package_detail["package_option"]["price"]

    try:
        res = settlement_balance(
            api_key,
            tokens,
            payment_items,
            "BUY_PACKAGE",
            False,
            overwrite_amount,
        )

        if res and res.get("status", "") == "SUCCESS":
            if pause_on_success:
                choice = console.input("Lanjut Dor? (y/n): ").lower()
                if choice == 'n':
                    return False  # Stop the loop
    except Exception as e:
        console.print(_panel("Order Error", f"Exception occurred while creating order: {e}", "red"))

    # 5. Delay for the loop (countdown)
    for i in range(delay, 0, -1):
        console.print(f"[grey50]Waiting for {i} seconds...[/grey50]", end="\r")
        time.sleep(1)
    console.print()  # newline after countdown
    return True  # Continue loop


# Purchase many by family (UI improved only)
def purchase_by_family(
    family_code: str,
    use_decoy: bool,
    pause_on_success: bool = True,
    token_confirmation_idx: int = 0,
):
    api_key = AuthInstance.api_key
    tokens: dict = AuthInstance.get_active_tokens() or {}

    decoy_data = None
    decoy_package_detail = None
    if use_decoy:
        url = BASE_CRYPTO_URL + "/decoyxcp"
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                console.print(_panel("Decoy", "Gagal mengambil data decoy package.", "yellow"))
                pause()
                return None
            decoy_data = response.json()
            decoy_package_detail = get_package_details(
                api_key,
                tokens,
                decoy_data["family_code"],
                decoy_data["variant_code"],
                decoy_data["order"],
                decoy_data["is_enterprise"],
                decoy_data["migration_type"],
            )
            balance_treshold = decoy_package_detail["package_option"]["price"]
            console.print(_panel("Balance Notice", f"Pastikan sisa balance KURANG DARI {_fmt_rp(balance_treshold)}", "grey35"))
            balance_answer = console.input("Apakah anda yakin ingin melanjutkan pembelian? (y/n): ")
            if balance_answer.lower() != "y":
                console.print(_panel("Cancelled", "Pembelian dibatalkan oleh user.", "yellow"))
                pause()
                return None
        except Exception as e:
            console.print(_panel("Decoy Error", f"Exception saat ambil decoy: {e}", "yellow"))
            pause()
            return None

    family_data = get_family(api_key, tokens, family_code)
    if not family_data:
        console.print(_panel("Family Error", f"Failed to get family data for code: {family_code}.", "red"))
        pause()
        return None

    family_name = family_data["package_family"]["name"]
    variants = family_data["package_variants"]

    header = (
        f"[bold]{family_name}[/bold]\n"
        f"Variants: {len(variants)}"
    )
    console.print(_panel("Purchase By Family", header, "grey35"))

    successful_purchases = []
    packages_count = sum(len(v["package_options"]) for v in variants)

    purchase_count = 0
    for variant in variants:
        variant_name = variant["name"]
        for option in variant["package_options"]:
            tokens = AuthInstance.get_active_tokens()

            option_name = option["name"]
            option_order = option["order"]
            option_price = option["price"]

            purchase_count += 1
            summary = (
                f"[bold]Purchase {purchase_count} of {packages_count}[/bold]\n"
                f"- Variant: [grey70]{variant_name}[/grey70]\n"
                f"- Option: [grey70]{option_order}. {option_name}[/grey70]\n"
                f"- Price: [bold]{_fmt_rp(option_price)}[/bold]"
            )
            console.print(_panel("Attempt", summary, "grey35"))

            payment_items = []

            try:
                if use_decoy and decoy_data:
                    decoy_package_detail = get_package_details(
                        api_key,
                        tokens,
                        decoy_data["family_code"],
                        decoy_data["variant_code"],
                        decoy_data["order"],
                        decoy_data["is_enterprise"],
                        decoy_data["migration_type"],
                    )

                target_package_detail = get_package_details(
                    api_key,
                    tokens,
                    family_code,
                    variant["package_variant_code"],
                    option["order"],
                    None,
                    None,
                )
            except Exception as e:
                console.print(_panel("Package Error", f"Exception occurred while fetching package details: {e}\nSkipping.", "yellow"))
                continue

            payment_items.append(
                PaymentItem(
                    item_code=target_package_detail["package_option"]["package_option_code"],
                    product_type="",
                    item_price=target_package_detail["package_option"]["price"],
                    item_name=str(randint(1000, 9999)) + target_package_detail["package_option"]["name"],
                    tax=0,
                    token_confirmation=target_package_detail["token_confirmation"],
                )
            )

            if use_decoy and decoy_package_detail:
                payment_items.append(
                    PaymentItem(
                        item_code=decoy_package_detail["package_option"]["package_option_code"],
                        product_type="",
                        item_price=decoy_package_detail["package_option"]["price"],
                        item_name=str(randint(1000, 9999)) + decoy_package_detail["package_option"]["name"],
                        tax=0,
                        token_confirmation=decoy_package_detail["token_confirmation"],
                    )
                )

            res = None
            overwrite_amount = target_package_detail["package_option"]["price"]
            if use_decoy and decoy_package_detail:
                overwrite_amount += decoy_package_detail["package_option"]["price"]

            try:
                res = settlement_balance(
                    api_key,
                    tokens,
                    payment_items,
                    "BUY_PACKAGE",
                    False,
                    overwrite_amount,
                )

                if res and res.get("status", "") != "SUCCESS":
                    error_msg = res.get("message", "Unknown error")
                    if "Bizz-err.Amount.Total" in error_msg:
                        try:
                            error_msg_arr = error_msg.split("=")
                            valid_amount = int(error_msg_arr[1].strip())
                            console.print(_panel("Auto Adjust", f"Adjusted total amount to: {valid_amount}", "grey35"))
                            res = settlement_balance(
                                api_key,
                                tokens,
                                payment_items,
                                "BUY_PACKAGE",
                                False,
                                valid_amount,
                            )
                            if res and res.get("status", "") == "SUCCESS":
                                successful_purchases.append(
                                    f"{variant_name}|{option_order}. {option_name} - {_fmt_rp(option_price)}"
                                )
                                console.print(_panel("SUCCESS", "Purchase successful!", "green"))
                                if pause_on_success:
                                    pause()
                        except Exception as e:
                            console.print(_panel("Adjust Error", f"Error parsing adjusted amount: {e}", "red"))
                else:
                    successful_purchases.append(
                        f"{variant_name}|{option_order}. {option_name} - {_fmt_rp(option_price)}"
                    )
                    console.print(_panel("SUCCESS", "Purchase successful!", "green"))
                    if pause_on_success:
                        pause()

            except Exception as e:
                console.print(_panel("Order Error", f"Exception occurred while creating order: {e}", "red"))
                res = None

    console.print(_panel("Summary", f"Total successful purchases for family {family_name}: {len(successful_purchases)}", "grey35"))

    if successful_purchases:
        table = Table(show_header=False, box=box.MINIMAL)
        for idx, purchase in enumerate(successful_purchases, start=1):
            table.add_row(f"{idx}.", purchase)
        console.print(Panel(table, title="[bold white]Successful purchases[/bold white]", border_style="grey35"))

    pause()


def purchase_n_times(
    n: int,
    family_code: str,
    variant_code: str,
    option_order: int,
    use_decoy: bool,
    pause_on_success: bool = False,
    token_confirmation_idx: int = 0,
):
    api_key = AuthInstance.api_key
    tokens: dict = AuthInstance.get_active_tokens() or {}

    decoy_data = None
    decoy_package_detail = None
    if use_decoy:
        url = BASE_CRYPTO_URL + "/decoyxcp"
        try:
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                console.print(_panel("Decoy", "Gagal mengambil data decoy package.", "yellow"))
                pause()
                return None
            decoy_data = response.json()
            decoy_package_detail = get_package_details(
                api_key,
                tokens,
                decoy_data["family_code"],
                decoy_data["variant_code"],
                decoy_data["order"],
                decoy_data["is_enterprise"],
                decoy_data["migration_type"],
            )
            balance_treshold = decoy_package_detail["package_option"]["price"]
            console.print(_panel("Balance Notice", f"Pastikan sisa balance KURANG DARI {_fmt_rp(balance_treshold)}", "grey35"))
            balance_answer = console.input("Apakah anda yakin ingin melanjutkan pembelian? (y/n): ")
            if balance_answer.lower() != "y":
                console.print(_panel("Cancelled", "Pembelian dibatalkan oleh user.", "yellow"))
                pause()
                return None
        except Exception as e:
            console.print(_panel("Decoy Error", f"Exception saat ambil decoy: {e}", "yellow"))
            pause()
            return None

    family_data = get_family(api_key, tokens, family_code)
    if not family_data:
        console.print(_panel("Family Error", f"Failed to get family data for code: {family_code}.", "red"))
        pause()
        return None

    family_name = family_data["package_family"]["name"]
    variants = family_data["package_variants"]

    target_variant = None
    for variant in variants:
        if variant["package_variant_code"] == variant_code:
            target_variant = variant
            break

    if not target_variant:
        console.print(_panel("Not Found", f"Variant code {variant_code} not found in family {family_name}.", "red"))
        pause()
        return None

    target_option = None
    for option in target_variant["package_options"]:
        if option["order"] == option_order:
            target_option = option
            break

    if not target_option:
        console.print(_panel("Not Found", f"Option order {option_order} not found in variant {target_variant['name']}.", "red"))
        pause()
        return None

    option_name = target_option["name"]
    option_price = target_option["price"]

    console.print(_panel("Bulk Purchase", f"Will run {n} purchases for {target_variant['name']} - {option_order}. {option_name} - {_fmt_rp(option_price)}", "grey35"))

    successful_purchases = []

    for i in range(n):
        console.print(_panel("Attempt", f"Purchase {i + 1} of {n}...", "grey35"))

        api_key = AuthInstance.api_key
        tokens: dict = AuthInstance.get_active_tokens() or {}

        payment_items = []

        try:
            if use_decoy and decoy_data:
                decoy_package_detail = get_package_details(
                    api_key,
                    tokens,
                    decoy_data["family_code"],
                    decoy_data["variant_code"],
                    decoy_data["order"],
                    decoy_data["is_enterprise"],
                    decoy_data["migration_type"],
                )

            target_package_detail = get_package_details(
                api_key,
                tokens,
                family_code,
                target_variant["package_variant_code"],
                target_option["order"],
                None,
                None,
            )
        except Exception as e:
            console.print(_panel("Package Error", f"Exception occurred while fetching package details: {e}\nSkipping.", "yellow"))
            continue

        payment_items.append(
            PaymentItem(
                item_code=target_package_detail["package_option"]["package_option_code"],
                product_type="",
                item_price=target_package_detail["package_option"]["price"],
                item_name=str(randint(1000, 9999)) + target_package_detail["package_option"]["name"],
                tax=0,
                token_confirmation=target_package_detail["token_confirmation"],
            )
        )

        if use_decoy and decoy_package_detail:
            payment_items.append(
                PaymentItem(
                    item_code=decoy_package_detail["package_option"]["package_option_code"],
                    product_type="",
                    item_price=decoy_package_detail["package_option"]["price"],
                    item_name=str(randint(1000, 9999)) + decoy_package_detail["package_option"]["name"],
                    tax=0,
                    token_confirmation=decoy_package_detail["token_confirmation"],
                )
            )

        res = None
        overwrite_amount = target_package_detail["package_option"]["price"]
        if use_decoy and decoy_package_detail:
            overwrite_amount += decoy_package_detail["package_option"]["price"]

        try:
            res = settlement_balance(
                api_key,
                tokens,
                payment_items,
                "BUY_PACKAGE",
                False,
                overwrite_amount,
            )

            if res and res.get("status", "") != "SUCCESS":
                error_msg = res.get("message", "Unknown error")
                if "Bizz-err.Amount.Total" in error_msg:
                    try:
                        error_msg_arr = error_msg.split("=")
                        valid_amount = int(error_msg_arr[1].strip())
                        console.print(_panel("Auto Adjust", f"Adjusted total amount to: {valid_amount}", "grey35"))
                        res = settlement_balance(
                            api_key,
                            tokens,
                            payment_items,
                            "BUY_PACKAGE",
                            False,
                            valid_amount,
                        )
                        if res and res.get("status", "") == "SUCCESS":
                            successful_purchases.append(
                                f"{target_variant['name']}|{option_order}. {option_name} - {_fmt_rp(option_price)}"
                            )
                            console.print(_panel("SUCCESS", "Purchase successful!", "green"))
                            if pause_on_success:
                                pause()
                    except Exception as e:
                        console.print(_panel("Adjust Error", f"Error parsing adjusted amount: {e}", "red"))
            else:
                successful_purchases.append(
                    f"{target_variant['name']}|{option_order}. {option_name} - {_fmt_rp(option_price)}"
                )
                console.print(_panel("SUCCESS", "Purchase successful!", "green"))
                if pause_on_success:
                    pause()

        except Exception as e:
            console.print(_panel("Order Error", f"Exception occurred while creating order: {e}", "red"))
            res = None

    console.print(_panel("Summary", f"Total successful purchases {len(successful_purchases)}/{n} for:\nFamily: {family_name}\nVariant: {target_variant['name']}\nOption: {option_order}. {option_name} - {_fmt_rp(option_price)}", "grey35"))

    if successful_purchases:
        table = Table(show_header=False, box=box.MINIMAL)
        for idx, purchase in enumerate(successful_purchases, start=1):
            table.add_row(f"{idx}.", purchase)
        console.print(Panel(table, title="[bold white]Successful purchases[/bold white]", border_style="grey35"))

    pause()
    return True
