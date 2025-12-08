import os
import time
import requests
import logging
import apscheduler.schedulers.blocking

logging.basicConfig(level=logging.INFO,
                    format="[go-ddns] %(levelname)s  -  %(message)s")

aps_logger = logging.getLogger("apscheduler")
aps_logger.setLevel(logging.WARNING)
aps_logger.propagate = False

DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
DEBUG = True
if DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger("requests").setLevel(logging.DEBUG)
    logging.getLogger("urllib3").setLevel(logging.DEBUG)

GODADDY_API_URL = "https://api.godaddy.com/v1/domains"
IP_API_URL = "https://api.ipify.org"
IP_STORAGE_FILE = "last_ip.txt"

# Utility


def safe_retry(func, retries=3, delay=2):
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            logging.warning(
                f"Attempt {attempt + 1} failed with error: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    raise ValueError(f"All {retries} attempts failed.")


def send_request(method: str, url: str, **kwargs):
    """Wrapper around requests.request that logs full request/response
    details when the global DEBUG flag is enabled.
    """
    if DEBUG:
        logging.debug(f"[http] Request -> {method.upper()} {url}")
        hdrs = kwargs.get("headers")
        if hdrs:
            logging.debug(f"[http] Request headers: {hdrs}")
        if "json" in kwargs:
            logging.debug(f"[http] Request json: {kwargs['json']}")
        if "data" in kwargs:
            logging.debug(f"[http] Request data: {kwargs['data']}")
        if "params" in kwargs:
            logging.debug(f"[http] Request params: {kwargs['params']}")
    response = requests.request(method, url, **kwargs)
    if DEBUG:
        logging.debug(f"[http] Response status: {response.status_code}")
        try:
            logging.debug(f"[http] Response headers: {dict(response.headers)}")
        except Exception:
            pass
        body = None
        try:
            body = response.text
        except Exception:
            body = None
        if body is not None:
            max_len = 10000
            if len(body) > max_len:
                logging.debug(
                    f"[http] Response body (truncated): {body[:max_len]}...")
            else:
                logging.debug(f"[http] Response body: {body}")
    return response

# IP Service


def get_public_ip():
    response = send_request("get", IP_API_URL, timeout=5)
    if response.status_code != 200:
        raise ValueError("Failed to retrieve public IP address.")
    return response.text.strip()


def check_ip_change():
    current_ip = get_public_ip()
    try:
        with open(IP_STORAGE_FILE, "r") as file:
            last_ip = file.read().strip()
            logging.info(f"Previous IP found: {last_ip}")
    except FileNotFoundError:
        last_ip = None
        logging.info("No previous IP found, assuming first run.")

    if current_ip != last_ip:
        with open(IP_STORAGE_FILE, "w") as file:
            file.write(current_ip)
        logging.info(
            f"IP address changed: {last_ip} -> {current_ip}")
        return True, current_ip
    logging.info(f"IP address unchanged: {current_ip}")
    return False, current_ip

# GoDaddy API Service


def get_api_key() -> str:
    api_key = os.getenv("GODADDY_API_KEY")
    if not api_key:
        raise ValueError("GoDaddy API key not found in environment variables.")
    return api_key


def get_domain_name() -> str:
    domain_name = os.getenv("GODADDY_DOMAIN_NAME")
    if not domain_name:
        raise ValueError(
            "GoDaddy domain name not found in environment variables.")
    return domain_name


def verify_domain_existence():
    try:
        api_key: str = safe_retry(get_api_key)
        domain_name: str = safe_retry(get_domain_name)
    except ValueError as e:
        logging.error(f"{e}")
        return False

    URL = f"{GODADDY_API_URL}/{domain_name}"

    headers = {
        "accept": "application/json",
        "Authorization": f"sso-key {api_key}",
    }

    response = send_request("get", URL, headers=headers, timeout=10)
    if response.status_code == 404:
        return False
    elif response.status_code != 200:
        raise ValueError("Failed to verify domain existence.")
    return True


def update_dns_record(new_ip: str):
    api_key: str = safe_retry(get_api_key)
    domain_name: str = safe_retry(get_domain_name)

    URL = f"{GODADDY_API_URL}/{domain_name}/records"

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"sso-key {api_key}",
    }

    data = [
        {
            "type": "A",
            "name": "@",
            "data": new_ip,
            "ttl": 600
        }
    ]

    response = send_request("put", URL, json=data, headers=headers, timeout=10)
    if response.status_code != 200:
        raise ValueError(f"Failed to update DNS record - {response.text}")
    return True

# Script


def job():
    logging.info("Script started.")
    ip_changed, current_ip = check_ip_change()
    if ip_changed:
        try:
            update_dns_record(current_ip)
            logging.info(
                "DNS record updated to new IP: {current_ip}")
        except ValueError as e:
            logging.error(f"{e}")
    else:
        logging.info(
            "No IP change detected. DNS record not updated.")


if __name__ == "__main__":
    logging.info("Starting GoDaddy DDNS client.")
    logging.info("Verifying domain existence / ownership.")
    try:
        verify_domain_existence()
    except ValueError as e:
        logging.error(f"{e}")
        raise SystemExit(1)
    scheduler = apscheduler.schedulers.blocking.BlockingScheduler()
    frequency = os.getenv("CHECK_FREQUENCY", "minutes")
    interval = int(os.getenv("CHECK_INTERVAL", "5"))
    match frequency:
        case "seconds":
            scheduler.add_job(job, "interval", seconds=interval)
        case "minutes":
            scheduler.add_job(job, "interval", minutes=interval)
        case "hours":
            scheduler.add_job(job, "interval", hours=interval)
        case "days":
            scheduler.add_job(job, "interval", days=interval)
        case _:
            logging.error(
                "Invalid TIME_PREFERENCE value. Use 'seconds', 'minutes', 'hours', or 'days'.")
            raise SystemExit(1)
    scheduler.start()
