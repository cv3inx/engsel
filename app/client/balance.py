from datetime import timezone, datetime
import json
import time
import uuid

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich.text import Text
from rich.prompt import Prompt
from rich.json import JSON

from app.client.encrypt import API_KEY, build_encrypted_field, decrypt_xdata, encryptsign_xdata, get_x_signature_payment, java_like_timestamp
from app.client.engsel import BASE_API_URL, UA, intercept_page, send_api_request
from app.type_dict import PaymentItem

console = Console()

def settlement_balance(
    api_key: str,
    tokens: dict,
    items: list[PaymentItem],
    payment_for: str,
    ask_overwrite: bool,
    overwrite_amount: int = -1,
    token_confirmation_idx: int = 0,
    amount_idx: int = -1,
):
    # Sanity check
    if overwrite_amount == -1 and not ask_overwrite:
        console.print("[red]Either ask_overwrite must be True or overwrite_amount must be set.[/red]")
        return None

    token_confirmation = items[token_confirmation_idx]["token_confirmation"]
    payment_targets = ";".join(item["item_code"] for item in items)

    amount_int = 0
    
    # Determine amount to use
    if overwrite_amount != -1:
        amount_int = overwrite_amount
    elif amount_idx != -1 and amount_idx < len(items):
        amount_int = items[amount_idx]["item_price"]
    else:
        # Jika amount_idx -1, gunakan item terakhir
        amount_int = items[-1]["item_price"]

    # If Overwrite
    if ask_overwrite:
        console.print(f"[yellow]Total amount is {amount_int}.[/yellow]")
        amount_str = console.input("Enter new amount if you need to overwrite (Press enter to ignore & use default amount): ")
        if amount_str != "":
            try:
                amount_int = int(amount_str)
            except ValueError:
                console.print("[yellow]Invalid overwrite input, using original price.[/yellow]")
                # return None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Intercepting page...", total=None)
        intercept_page(api_key, tokens, items[0]["item_code"], False)

    # Get payment methods
    payment_path = "payments/api/v8/payment-methods-option"
    payment_payload = {
        "payment_type": "PURCHASE",
        "is_enterprise": False,
        "payment_target": items[token_confirmation_idx]["item_code"],
        "lang": "en",
        "is_referral": False,
        "token_confirmation": token_confirmation
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Getting payment methods...", total=None)
        payment_res = send_api_request(api_key, payment_path, payment_payload, tokens["id_token"], "POST")
    
    if payment_res.get("status") != "SUCCESS":
        console.print("[red]Failed to fetch payment methods.[/red]")
        console.print(f"[red]Error: {payment_res}[/red]")
        return payment_res
    
    token_payment = payment_res["data"]["token_payment"]
    ts_to_sign = payment_res["data"]["timestamp"]
    
    # Settlement request
    path = "payments/api/v8/settlement-multipayment"
    settlement_payload = {
        "total_discount": 0,
        "is_enterprise": False,
        "payment_token": "",
        "token_payment": token_payment,
        "activated_autobuy_code": "",
        "cc_payment_type": "",
        "is_myxl_wallet": False,
        "pin": "",
        "ewallet_promo_id": "",
        "members": [],
        "total_fee": 0,
        "fingerprint": "",
        "autobuy_threshold_setting": {
            "label": "",
            "type": "",
            "value": 0
        },
        "is_use_point": False,
        "lang": "en",
        "payment_method": "BALANCE",
        "timestamp": int(time.time()),
        "points_gained": 0,
        "can_trigger_rating": False,
        "akrab_members": [],
        "akrab_parent_alias": "",
        "referral_unique_code": "",
        "coupon": "",
        "payment_for": payment_for,
        "with_upsell": False,
        "topup_number": "",
        "stage_token": "",
        "authentication_id": "",
        "encrypted_payment_token": build_encrypted_field(urlsafe_b64=True),
        "token": "",
        "token_confirmation": "",
        "access_token": tokens["access_token"],
        "wallet_number": "",
        "encrypted_authentication_id": build_encrypted_field(urlsafe_b64=True),
        "additional_data": {
            "original_price": items[-1]["item_price"],
            "is_spend_limit_temporary": False,
            "migration_type": "",
            "akrab_m2m_group_id": "false",
            "spend_limit_amount": 0,
            "is_spend_limit": False,
            "mission_id": "",
            "tax": 0,
            "quota_bonus": 0,
            "cashtag": "",
            "is_family_plan": False,
            "combo_details": [],
            "is_switch_plan": False,
            "discount_recurring": 0,
            "is_akrab_m2m": False,
            "balance_type": "PREPAID_BALANCE",
            "has_bonus": False,
            "discount_promo": 0
        },
        "total_amount": amount_int,
        "is_using_autobuy": False,
        "items": items,
    }
    
    encrypted_payload = encryptsign_xdata(
        api_key=api_key,
        method="POST",
        path=path,
        id_token=tokens["id_token"],
        payload=settlement_payload
    )
    
    xtime = int(encrypted_payload["encrypted_body"]["xtime"])
    sig_time_sec = (xtime // 1000)
    x_requested_at = datetime.fromtimestamp(sig_time_sec, tz=timezone.utc).astimezone()
    settlement_payload["timestamp"] = ts_to_sign
    
    body = encrypted_payload["encrypted_body"]
    x_sig = get_x_signature_payment(
                api_key,
                tokens["access_token"],
                ts_to_sign,
                payment_targets,
                token_payment,
                "BALANCE",
                payment_for,
                path
            )
    
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
    
    url = f"{BASE_API_URL}/{path}"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[cyan]Sending settlement request...", total=None)
        resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
    
    try:
        decrypted_body = decrypt_xdata(api_key, json.loads(resp.text))
        table = Table(title="Purchase Result", expand=True, show_lines=False, header_style="bold cyan")
        table.add_column("Name", style="bold white", no_wrap=True)
        table.add_column("Value", style="green", overflow="fold")

        for key, value in decrypted_body.items():
            table.add_row(str(key).capitalize(), str(value))

        console.print(Panel(table, border_style="green"))

        console.print("\n[bold cyan]Raw JSON Response[/bold cyan]")
        console.print(JSON.from_data(decrypted_body, indent=2))
        return decrypted_body

        
    except Exception as e:
        console.print(f"[red][decrypt err] {e}[/red]")
        return resp.text