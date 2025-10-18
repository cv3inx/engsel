from datetime import datetime, timezone, timedelta
import json
import uuid
import base64
import qrcode
import time
import requests

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich import box

from app.client.engsel import *
from app.client.encrypt import API_KEY, decrypt_xdata, encryptsign_xdata, java_like_timestamp, get_x_signature_payment
from app.type_dict import PaymentItem

console = Console()

def settlement_qris(
    api_key: str,
    tokens: dict,
    items: list[PaymentItem],
    payment_for: str,
    ask_overwrite: bool,
    overwrite_amount: int = -1,
    token_confirmation_idx: int = 0,
    amount_idx: int = -1,
):  
    if overwrite_amount == -1 and not ask_overwrite:
        console.print("[red]Either ask_overwrite must be True or overwrite_amount must be set.[/red]")
        return None

    token_confirmation = items[token_confirmation_idx]["token_confirmation"]
    payment_targets = ";".join([item["item_code"] for item in items])

    amount_int = overwrite_amount if overwrite_amount != -1 else items[amount_idx]["item_price"]

    if ask_overwrite:
        console.print(Panel(f"Total amount is {amount_int}.\nEnter new amount if you need to overwrite.", title="Amount Overwrite", style="cyan"))
        amount_str = console.input("Press enter to ignore & use default amount: ")
        if amount_str != "":
            try:
                amount_int = int(amount_str)
            except ValueError:
                console.print("[yellow]Invalid overwrite input, using original price.[/yellow]")

    intercept_page(api_key, tokens, items[0]["item_code"], False)

    payment_path = "payments/api/v8/payment-methods-option"
    payment_payload = {
        "payment_type": "PURCHASE",
        "is_enterprise": False,
        "payment_target": items[token_confirmation_idx]["item_code"],
        "lang": "en",
        "is_referral": False,
        "token_confirmation": token_confirmation
    }

    # Spinner untuk fetching payment methods
    with Live(Spinner("dots", text="Getting payment methods..."), console=console, refresh_per_second=12):
        payment_res = send_api_request(api_key, payment_path, payment_payload, tokens["id_token"], "POST")
        time.sleep(0.5)  # spinner effect

    if payment_res["status"] != "SUCCESS":
        console.print(Panel(json.dumps(payment_res, indent=2), title="Failed to fetch payment methods", border_style="red"))
        return None

    token_payment = payment_res["data"]["token_payment"]
    ts_to_sign = payment_res["data"]["timestamp"]

    # --- Settlement request ---
    path = "payments/api/v8/settlement-multipayment/qris"
    settlement_payload = {
        "akrab": {"akrab_members": [], "akrab_parent_alias": "", "members": []},
        "can_trigger_rating": False,
        "total_discount": 0,
        "coupon": "",
        "payment_for": payment_for,
        "topup_number": "",
        "is_enterprise": False,
        "autobuy": {"is_using_autobuy": False, "activated_autobuy_code": "", "autobuy_threshold_setting": {"label": "", "type": "", "value": 0}},
        "access_token": tokens["access_token"],
        "is_myxl_wallet": False,
        "additional_data": {
            "original_price": items[0]["item_price"],
            "is_spend_limit_temporary": False,
            "migration_type": "",
            "spend_limit_amount": 0,
            "is_spend_limit": False,
            "tax": 0,
            "benefit_type": "",
            "quota_bonus": 0,
            "cashtag": "",
            "is_family_plan": False,
            "combo_details": [],
            "is_switch_plan": False,
            "discount_recurring": 0,
            "has_bonus": False,
            "discount_promo": 0
        },
        "total_amount": amount_int,
        "total_fee": 0,
        "is_use_point": False,
        "lang": "en",
        "items": items,
        "verification_token": token_payment,
        "payment_method": "QRIS",
        "timestamp": int(time.time()),
    }

    encrypted_payload = encryptsign_xdata(api_key, "POST", path, tokens["id_token"], settlement_payload)
    xtime = int(encrypted_payload["encrypted_body"]["xtime"])
    sig_time_sec = xtime // 1000
    x_requested_at = datetime.fromtimestamp(sig_time_sec, tz=timezone.utc).astimezone()
    settlement_payload["timestamp"] = ts_to_sign

    body = encrypted_payload["encrypted_body"]
    x_sig = get_x_signature_payment(api_key, tokens["access_token"], ts_to_sign, payment_targets, token_payment, "QRIS", payment_for, path)

    headers = {
        "host": BASE_API_URL.replace("https://", ""),
        "content-type": "application/json; charset=utf-8",
        "user-agent": UA,
        "x-api-key": API_KEY,
        "authorization": f"Bearer {tokens['id_token']}",
        "x-hv": "v3",
        "x-signature-time": str(sig_time_sec),
        "x-signature": x_sig,
        "x-request-id": str(uuid.uuid4()),
        "x-request-at": java_like_timestamp(x_requested_at),
        "x-version-app": "8.8.0",
    }

    # Spinner untuk settlement request
    with Live(Spinner("dots", text="Sending settlement request..."), console=console, refresh_per_second=12):
        resp = requests.post(f"{BASE_API_URL}/{path}", headers=headers, data=json.dumps(body), timeout=30)
        time.sleep(0.5)

    try:
        decrypted_body = decrypt_xdata(api_key, json.loads(resp.text))
        if decrypted_body["status"] != "SUCCESS":
            console.print(Panel(json.dumps(decrypted_body, indent=2), title="[red]Failed to initiate settlement[/red]", border_style="red"))
            return None

        transaction_id = decrypted_body["data"]["transaction_code"]
        console.print(Panel(f"Transaction initiated successfully!\nTransaction ID: [bold green]{transaction_id}[/bold green]", title="Success", border_style="green"))

        table = Table(title="Items Purchased", show_lines=True, box=box.SIMPLE, header_style="bold cyan", expand=True)
        table.add_column("Item Code", style="bold white")
        table.add_column("Price", style="green")
        table.add_column("Token Confirmation", style="magenta")

        for item in items:
            table.add_row(item["item_code"], str(item["item_price"]), str(item["token_confirmation"]))

        console.print(table)
        return transaction_id

    except Exception as e:
        console.print(Panel(f"[red][decrypt err][/red] {e}\nResponse:\n{resp.text}", title="Error", border_style="red"))
        return resp.text

def show_qris_payment(
    api_key: str,
    tokens: dict,
    items: list[PaymentItem],
    payment_for: str,
    ask_overwrite: bool,
    overwrite_amount: int = -1,
    token_confirmation_idx: int = 0,
    amount_idx: int = -1,
):
    transaction_id = settlement_qris(api_key, tokens, items, payment_for, ask_overwrite, overwrite_amount, token_confirmation_idx, amount_idx)
    if not transaction_id:
        console.print("[red]Failed to create QRIS transaction.[/red]")
        return

    with Live(Spinner("dots", text="Fetching QRIS code..."), console=console, refresh_per_second=12):
        qris_code = get_qris_code(api_key, tokens, transaction_id)
        time.sleep(0.5)

    if not qris_code:
        console.print("[red]Failed to get QRIS code.[/red]")
        return

    console.print(Panel(f"QRIS data:\n{qris_code}", title="QRIS Code", border_style="green"))

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=1)
    qr.add_data(qris_code)
    qr.make(fit=True)
    qr.print_ascii(invert=True)

    qris_b64 = base64.urlsafe_b64encode(qris_code.encode()).decode()
    qris_url = f"https://ki-ar-kod.netlify.app/?data={qris_b64}"
    console.print(Panel(f"Or open the following link to view QRIS:\n[q]{qris_url}[/q]", title="QRIS URL", border_style="cyan"))
