import os
import json
import uuid
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.text import Text

from app.client.encrypt import (
    encryptsign_xdata,
    java_like_timestamp,
    ts_gmt7_without_colon,
    ax_api_signature,
    decrypt_xdata,
    API_KEY,
    load_ax_fp,
    ax_device_id
)

# ============================================================================
# CONFIGURATION
# ============================================================================

console = Console()

BASE_API_URL = os.getenv("BASE_API_URL")
BASE_CIAM_URL = os.getenv("BASE_CIAM_URL")

if not BASE_API_URL or not BASE_CIAM_URL:
    raise ValueError("BASE_API_URL or BASE_CIAM_URL environment variable not set")

GET_OTP_URL = f"{BASE_CIAM_URL}/realms/xl-ciam/auth/otp"
SUBMIT_OTP_URL = f"{BASE_CIAM_URL}/realms/xl-ciam/protocol/openid-connect/token"

BASIC_AUTH = os.getenv("BASIC_AUTH")
UA = os.getenv("UA")
AX_DEVICE_ID = ax_device_id()
AX_FP = load_ax_fp()

# Device constants
DEVICE_NAME = "samsung"
DEVICE_MODEL = "SM-N935F"
APP_VERSION = "8.8.0"
SUBSTYPE = "PREPAID"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def validate_contact(contact: str) -> bool:
    """
    Validate contact number format.
    
    Args:
        contact: Phone number string
        
    Returns:
        True if valid, False otherwise
    """
    if not contact.startswith("628") or len(contact) > 14:
        console.print("[red]✗[/red] Invalid number format", style="bold")
        return False
    return True


def log_success(message: str) -> None:
    """Log success message with green checkmark."""
    console.print(f"[green]✓[/green] {message}", style="bold")


def log_error(message: str) -> None:
    """Log error message with red cross."""
    console.print(f"[red]✗[/red] {message}", style="bold red")


def log_info(message: str) -> None:
    """Log info message with blue icon."""
    console.print(f"[cyan]ℹ[/cyan] {message}", style="bold cyan")


def log_warning(message: str) -> None:
    """Log warning message with yellow icon."""
    console.print(f"[yellow]⚠[/yellow] {message}", style="bold yellow")


# ============================================================================
# AUTHENTICATION FUNCTIONS
# ============================================================================

def get_otp(contact: str) -> Optional[str]:
    """
    Request OTP for the given contact number.
    
    Args:
        contact: Phone number (e.g., "6287896089467")
        
    Returns:
        subscriber_id if successful, None otherwise
    """
    if not validate_contact(contact):
        return None
    
    querystring = {
        "contact": contact,
        "contactType": "SMS",
        "alternateContact": "false"
    }
    
    now = datetime.now(timezone(timedelta(hours=7)))
    ax_request_at = java_like_timestamp(now)
    ax_request_id = str(uuid.uuid4())

    headers = {
        "Accept-Encoding": "gzip, deflate, br",
        "Authorization": f"Basic {BASIC_AUTH}",
        "Ax-Device-Id": AX_DEVICE_ID,
        "Ax-Fingerprint": AX_FP,
        "Ax-Request-At": ax_request_at,
        "Ax-Request-Device": DEVICE_NAME,
        "Ax-Request-Device-Model": DEVICE_MODEL,
        "Ax-Request-Id": ax_request_id,
        "Ax-Substype": SUBSTYPE,
        "Content-Type": "application/json",
        "Host": BASE_CIAM_URL.replace("https://", ""),
        "User-Agent": UA,
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True  # Membuat progress bar hilang setelah selesai
    ) as progress:
        task = progress.add_task("[cyan]Requesting OTP...", total=None)
        
        try:
            response = requests.get(
                GET_OTP_URL,
                headers=headers,
                params=querystring,
                timeout=30
            )
            
            json_body = json.loads(response.text)
            
            if "subscriber_id" not in json_body:
                error_msg = json_body.get("error", "No error message in response")
                log_error(f"OTP request failed: {error_msg}")
                return None
            
            log_success("OTP sent successfully")
            return json_body["subscriber_id"]
            
        except Exception as e:
            log_error(f"Error requesting OTP: {e}")
            return None


def submit_otp(api_key: str, contact: str, code: str) -> Optional[Dict[str, Any]]:
    """
    Submit OTP code for authentication.
    
    Args:
        api_key: API key for signature
        contact: Phone number
        code: 6-digit OTP code
        
    Returns:
        Token dictionary if successful, None otherwise
    """
    if not validate_contact(contact):
        return None
    
    if not code or len(code) != 6:
        log_error("Invalid OTP code format (must be 6 digits)")
        return None
    
    now_gmt7 = datetime.now(timezone(timedelta(hours=7)))
    ts_for_sign = ts_gmt7_without_colon(now_gmt7)
    ts_header = ts_gmt7_without_colon(now_gmt7 - timedelta(minutes=5))
    signature = ax_api_signature(api_key, ts_for_sign, contact, code, "SMS")

    payload = f"contactType=SMS&code={code}&grant_type=password&contact={contact}&scope=openid"

    headers = {
        "Accept-Encoding": "gzip, deflate, br",
        "Authorization": f"Basic {BASIC_AUTH}",
        "Ax-Api-Signature": signature,
        "Ax-Device-Id": AX_DEVICE_ID,
        "Ax-Fingerprint": AX_FP,
        "Ax-Request-At": ts_header,
        "Ax-Request-Device": DEVICE_NAME,
        "Ax-Request-Device-Model": DEVICE_MODEL,
        "Ax-Request-Id": str(uuid.uuid4()),
        "Ax-Substype": SUBSTYPE,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": UA,
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Verifying OTP...", total=None)
        
        try:
            response = requests.post(SUBMIT_OTP_URL, data=payload, headers=headers, timeout=30)
            json_body = json.loads(response.text)
            
            if "error" in json_body:
                log_error(f"Login failed: {json_body.get('error_description', 'Unknown error')}")
                return None
            
            log_success("Login successful")
            return json_body
            
        except requests.RequestException as e:
            log_error(f"Request error: {e}")
            return None


def get_new_token(refresh_token: str) -> Optional[Dict[str, Any]]:
    """
    Refresh access token using refresh token.
    
    Args:
        refresh_token: Refresh token string
        
    Returns:
        New token dictionary if successful, None otherwise
    """
    now = datetime.now(timezone(timedelta(hours=7)))
    ax_request_at = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+0700"
    ax_request_id = str(uuid.uuid4())

    headers = {
        "Host": BASE_CIAM_URL.replace("https://", ""),
        "ax-request-at": ax_request_at,
        "ax-device-id": AX_DEVICE_ID,
        "ax-request-id": ax_request_id,
        "ax-request-device": DEVICE_NAME,
        "ax-request-device-model": DEVICE_MODEL,
        "ax-fingerprint": AX_FP,
        "authorization": f"Basic {BASIC_AUTH}",
        "user-agent": UA,
        "ax-substype": SUBSTYPE,
        "content-type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Refreshing token...", total=None)
        
        try:
            resp = requests.post(SUBMIT_OTP_URL, headers=headers, data=data, timeout=30)
            
            if resp.status_code == 400:
                error_data = resp.json()
                if error_data.get("error_description") == "Session not active":
                    log_error("Refresh token expired. Please remove and re-add the account.")
                    return None
            
            resp.raise_for_status()
            body = resp.json()
            
            if "id_token" not in body:
                log_error("ID token not found in response")
                return None
                
            if "error" in body:
                log_error(f"Error: {body['error']} - {body.get('error_description', '')}")
                return None
            
            log_success("Token refreshed successfully")
            return body
            
        except Exception as e:
            log_error(f"Error refreshing token: {e}")
            return None


# ============================================================================
# API REQUEST FUNCTIONS
# ============================================================================

def send_api_request(
    api_key: str,
    path: str,
    payload_dict: Dict[str, Any],
    id_token: str,
    method: str = "POST",
) -> Any:
    """
    Send encrypted API request.
    
    Args:
        api_key: API key for encryption
        path: API endpoint path
        payload_dict: Request payload dictionary
        id_token: ID token for authorization
        method: HTTP method (default: POST)
        
    Returns:
        Decrypted response data
    """
    encrypted_payload = encryptsign_xdata(
        api_key=api_key,
        method=method,
        path=path,
        id_token=id_token,
        payload=payload_dict
    )
    
    xtime = int(encrypted_payload["encrypted_body"]["xtime"])
    sig_time_sec = xtime // 1000
    now = datetime.now(timezone.utc).astimezone()

    body = encrypted_payload["encrypted_body"]
    x_sig = encrypted_payload["x_signature"]
    
    headers = {
        "host": BASE_API_URL.replace("https://", ""),
        "content-type": "application/json; charset=utf-8",
        "user-agent": UA,
        "x-api-key": API_KEY,
        "authorization": f"Bearer {id_token}",
        "x-hv": "v3",
        "x-signature-time": str(sig_time_sec),
        "x-signature": x_sig,
        "x-request-id": str(uuid.uuid4()),
        "x-request-at": java_like_timestamp(now),
        "x-version-app": APP_VERSION,
    }

    url = f"{BASE_API_URL}/{path}"
    resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)

    try:
        decrypted_body = decrypt_xdata(api_key, json.loads(resp.text))
        return decrypted_body
    except Exception as e:
        log_error(f"Decryption error: {e}")
        return resp.text


# ============================================================================
# PROFILE & BALANCE FUNCTIONS
# ============================================================================

def get_profile(api_key: str, access_token: str, id_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch user profile information.
    
    Args:
        api_key: API key
        access_token: Access token
        id_token: ID token
        
    Returns:
        Profile data dictionary or None
    """
    path = "api/v8/profile"
    raw_payload = {
        "access_token": access_token,
        "app_version": APP_VERSION,
        "is_enterprise": False,
        "lang": "en"
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Fetching profile...", total=None)
        res = send_api_request(api_key, path, raw_payload, id_token, "POST")
        
    if res and "data" in res:
        log_success("Profile fetched successfully")
        return res.get("data")
    
    log_error("Failed to fetch profile")
    return None


def get_balance(api_key: str, id_token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch account balance information.
    
    Args:
        api_key: API key
        id_token: ID token
        
    Returns:
        Balance data dictionary or None
    """
    path = "api/v8/packages/balance-and-credit"
    raw_payload = {
        "is_enterprise": False,
        "lang": "en"
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Fetching balance...", total=None)
        res = send_api_request(api_key, path, raw_payload, id_token, "POST")
    
    if res and "data" in res and "balance" in res["data"]:
        log_success("Balance fetched successfully")
        return res["data"]["balance"]
    
    log_error(f"Error getting balance: {res.get('error', 'Unknown error')}")
    return None


def login_info(api_key: str, tokens: Dict[str, str], is_enterprise: bool = False) -> Optional[Dict[str, Any]]:
    """
    Get login information.
    
    Args:
        api_key: API key
        tokens: Token dictionary containing access_token and id_token
        is_enterprise: Enterprise flag
        
    Returns:
        Login data dictionary or None
    """
    path = "api/v8/auth/login"
    raw_payload = {
        "access_token": tokens["access_token"],
        "is_enterprise": is_enterprise,
        "lang": "en"
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Fetching login info...", total=None)
        res = send_api_request(api_key, path, raw_payload, tokens["id_token"], "POST")
    
    if res and "data" in res:
        log_success("Login info fetched successfully")
        return res["data"]
    
    log_error(f"Error getting login info: {res.get('error', 'Unknown error')}")
    return None


# ============================================================================
# PACKAGE FUNCTIONS
# ============================================================================

def get_family(
    api_key: str,
    tokens: Dict[str, str],
    family_code: str,
    is_enterprise: Optional[bool] = None,
    migration_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Fetch package family information with parameter discovery.
    
    Args:
        api_key: API key
        tokens: Token dictionary
        family_code: Package family code
        is_enterprise: Enterprise flag (None to try both)
        migration_type: Migration type (None to try all)
        
    Returns:
        Family data dictionary or None
    """
    log_info(f"Fetching package family: [yellow]{family_code}")
    
    is_enterprise_list = [False, True] if is_enterprise is None else [is_enterprise]
    migration_type_list = ["NONE", "PRE_TO_PRIOH", "PRIOH_TO_PRIO", "PRIO_TO_PRIOH"] if migration_type is None else [migration_type]

    path = "api/v8/xl-stores/options/list"
    id_token = tokens.get("id_token")
    family_data = None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Discovering family parameters...", total=None)
        
        for mt in migration_type_list:
            if family_data is not None:
                break

            for ie in is_enterprise_list:
                if family_data is not None:
                    break
            
                progress.update(task, description=f"[cyan]Trying: enterprise={ie}, migration={mt}")

                payload_dict = {
                    "is_show_tagging_tab": True,
                    "is_dedicated_event": True,
                    "is_transaction_routine": False,
                    "migration_type": mt,
                    "package_family_code": family_code,
                    "is_autobuy": False,
                    "is_enterprise": ie,
                    "is_pdlp": True,
                    "referral_code": "",
                    "is_migration": False,
                    "lang": "en"
                }
            
                res = send_api_request(api_key, path, payload_dict, id_token, "POST")
                
                if res.get("status") == "SUCCESS":
                    family_name = res["data"]["package_family"].get("name", "")
                    if family_name:
                        family_data = res["data"]
                        # Progress akan otomatis hilang karena context manager

    if family_data:
        log_success(f"Found family: [yellow]{family_data['package_family'].get('name', '')}")
    else:
        log_error(f"Failed to get valid family data for [red]{family_code}")

    return family_data


def get_families(
    api_key: str,
    tokens: Dict[str, str],
    package_category_code: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch package families by category.
    
    Args:
        api_key: API key
        tokens: Token dictionary
        package_category_code: Category code
        
    Returns:
        Families data dictionary or None
    """
    path = "api/v8/xl-stores/families"
    payload_dict = {
        "migration_type": "",
        "is_enterprise": False,
        "is_shareable": False,
        "package_category_code": package_category_code,
        "with_icon_url": True,
        "is_migration": False,
        "lang": "en"
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Fetching families...", total=None)
        res = send_api_request(api_key, path, payload_dict, tokens["id_token"], "POST")
    
    if res.get("status") == "SUCCESS":
        log_success(f"Families fetched for category: {package_category_code}")
        return res["data"]
    
    log_error(f"Failed to get families for category {package_category_code}")
    console.print(Panel(json.dumps(res, indent=2), title="Error Response", border_style="red"))
    input("Press Enter to continue...")
    return None


def get_package(
    api_key: str,
    tokens: Dict[str, str],
    package_option_code: str,
    package_family_code: str = "",
    package_variant_code: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Fetch package details by option code.
    
    Args:
        api_key: API key
        tokens: Token dictionary
        package_option_code: Package option code
        package_family_code: Package family code (optional)
        package_variant_code: Package variant code (optional)
        
    Returns:
        Package data dictionary or None
    """
    path = "api/v8/xl-stores/options/detail"
    raw_payload = {
        "is_transaction_routine": False,
        "migration_type": "NONE",
        "package_family_code": package_family_code,
        "family_role_hub": "",
        "is_autobuy": False,
        "is_enterprise": False,
        "is_shareable": False,
        "is_migration": False,
        "lang": "en",
        "package_option_code": package_option_code,
        "is_upsell_pdp": False,
        "package_variant_code": package_variant_code
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Fetching package details...", total=None)
        res = send_api_request(api_key, path, raw_payload, tokens["id_token"], "POST")
    
    if res and "data" in res:
        log_success("Package details fetched successfully")
        return res["data"]
    
    log_error(f"Error getting package: {res.get('error', 'Unknown error')}")
    console.print(Panel(json.dumps(res, indent=2), title="Error Response", border_style="red"))
    return None


def get_addons(
    api_key: str,
    tokens: Dict[str, str],
    package_option_code: str
) -> Optional[Dict[str, Any]]:
    """
    Fetch available addons for a package.
    
    Args:
        api_key: API key
        tokens: Token dictionary
        package_option_code: Package option code
        
    Returns:
        Addons data dictionary or None
    """
    path = "api/v8/xl-stores/options/addons-pinky-box"
    raw_payload = {
        "is_enterprise": False,
        "lang": "en",
        "package_option_code": package_option_code
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Fetching addons...", total=None)
        res = send_api_request(api_key, path, raw_payload, tokens["id_token"], "POST")
    
    if res and "data" in res:
        log_success("Addons fetched successfully")
        return res["data"]
    
    log_error(f"Error getting addons: {res.get('error', 'Unknown error')}")
    return None


def intercept_page(
    api_key: str,
    tokens: Dict[str, str],
    option_code: str,
    is_enterprise: bool = False
) -> None:
    """
    Fetch intercept page information.
    
    Args:
        api_key: API key
        tokens: Token dictionary
        option_code: Package option code
        is_enterprise: Enterprise flag
    """
    path = "misc/api/v8/utility/intercept-page"
    raw_payload = {
        "is_enterprise": is_enterprise,
        "lang": "en",
        "package_option_code": option_code
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]Fetching intercept page...", total=None)
        res = send_api_request(api_key, path, raw_payload, tokens["id_token"], "POST")
    
    if res and "status" in res:
        log_info(f"Intercept status: {res['status']}")
    else:
        log_error("Intercept error")


def get_package_details(
    api_key: str,
    tokens: Dict[str, str],
    family_code: str,
    variant_code: str,
    option_order: int,
    is_enterprise: Optional[bool] = None,
    migration_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Fetch complete package details by family, variant, and option order.
    
    Args:
        api_key: API key
        tokens: Token dictionary
        family_code: Package family code
        variant_code: Package variant code
        option_order: Option order number
        is_enterprise: Enterprise flag (None to auto-discover)
        migration_type: Migration type (None to auto-discover)
        
    Returns:
        Package details dictionary or None
    """
    family_data = get_family(api_key, tokens, family_code, is_enterprise, migration_type)
    if not family_data:
        log_error(f"Failed to fetch family data for {family_code}")
        return None
    
    package_variants = family_data["package_variants"]
    option_code = None
    
    for variant in package_variants:
        if variant["package_variant_code"] == variant_code:
            package_options = variant["package_options"]
            for option in package_options:
                if option["order"] == option_order:
                    option_code = option["package_option_code"]
                    break
            break

    if option_code is None:
        log_error("Failed to find matching package option")
        return None
        
    package_details_data = get_package(api_key, tokens, option_code)
    if not package_details_data:
        log_error("Failed to fetch package details")
        return None
    
    return package_details_data