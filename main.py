import os
import requests
import logging
import apscheduler.schedulers.blocking

logging.basicConfig(level=logging.INFO,
                    format="[go-ddns] %(levelname)s - %(message)s")

GODADDY_API_URL = "https://api.godaddy.com/v1/domains"
IP_API_URL = "https://api.ipify.org"
IP_STORAGE_FILE = "last_ip.txt"

# IP Service


def get_public_ip():
    response = requests.get(IP_API_URL)
    if response.status_code != 200:
        raise ValueError("Error retrieving public IP address.")
    return response.text.strip()


def check_ip_change():
    current_ip = get_public_ip()
    try:
        with open(IP_STORAGE_FILE, "r") as file:
            last_ip = file.read().strip()
            logging.info("Previous IP found: {last_ip}")
    except FileNotFoundError:
        last_ip = None
        logging.info("No previous IP found, assuming first run.")

    if current_ip != last_ip:
        with open(IP_STORAGE_FILE, "w") as file:
            file.write(current_ip)
        logging.info(
            "IP address changed: {last_ip} -> {current_ip}")
        return True, current_ip
    logging.info("IP address unchanged: {current_ip}")
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
        api_key: str = get_api_key()
        domain_name: str = get_domain_name()
    except ValueError:
        logging.error("{e}")
        return False

    URL = f"{GODADDY_API_URL}/{domain_name}"

    headers = {
        "accept": "application/json",
        "Authorization": f"sso-key {api_key}",
    }

    response = requests.get(URL, headers=headers)
    if response.status_code == 404:
        return False
    elif response.status_code != 200:
        raise ValueError("Error verifying domain existence.")
    return True


def update_dns_record(new_ip: str):
    api_key: str = get_api_key()
    domain_name: str = get_domain_name()

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

    response = requests.put(URL, json=data, headers=headers)
    if response.status_code != 200:
        raise ValueError("Error updating DNS record.")
    return True

# Script


def job():
    logging.info("Script started.")
    try:
        verify_domain_existence()
    except ValueError:
        logging.error("{e}")
        return

    ip_changed, current_ip = check_ip_change()
    if ip_changed:
        try:
            update_dns_record(current_ip)
            logging.info(
                "DNS record updated to new IP: {current_ip}")
        except ValueError:
            logging.error("{e}")
    else:
        logging.info(
            "No IP change detected. DNS record not updated.")


def main():
    logging.info("Starting GoDaddy DDNS client.")
    scheduler = apscheduler.schedulers.blocking.BlockingScheduler()
    time_preference = os.getenv("TIME_PREFERENCE", "minutes")
    interval = int(os.getenv("INTERVAL", "5"))
    match time_preference:
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
            return
    scheduler.start()
