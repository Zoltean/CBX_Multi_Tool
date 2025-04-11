# -*- coding: utf-8 -*-
import os
import logging
import threading

import requests
import time
from typing import Dict, Optional, Tuple
from tqdm import tqdm
from ping3 import ping
from colorama import Fore, Style
from utils import show_spinner
from config import VPS_VERSION_URL

logger = logging.getLogger(__name__)

def check_for_updates() -> Tuple[bool, str]:
    logger.info(f"Checking for updates at {VPS_VERSION_URL}")
    try:
        response = requests.get(VPS_VERSION_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        latest_version = data.get("version")
        download_url = data.get("download_url", "")
        from config import PROGRAM_VERSION
        if latest_version and latest_version != PROGRAM_VERSION:
            logger.info(f"New version available: {latest_version} (current: {PROGRAM_VERSION})")
            return True, download_url
        else:
            logger.info("No updates available")
            return False, ""
    except requests.RequestException as e:
        logger.error(f"Failed to check updates: {e}")
        return False, ""
    except Exception as e:
        logger.error(f"Unexpected error in check_for_updates: {e}")
        return False, ""

def check_server_status(url: str) -> bool:
    logger.info(f"Checking server status at {url} via ICMP ping")
    try:
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        result = ping(domain, timeout=5)
        if result is not None and result is not False:
            logger.info(f"Server {domain} is online (ping response: {result} ms)")
            return True
        else:
            logger.error(f"Server {domain} is offline (no ping response)")
            return False
    except Exception as e:
        logger.error(f"Failed to ping {url}: {e}")
        return False

def fetch_json(url: str) -> Optional[Dict]:
    logger.info(f"Fetching JSON from {url}")
    print(f"{Fore.CYAN}Fetching data from server...{Style.RESET_ALL}")
    try:
        with tqdm(total=100, desc="Downloading JSON", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
            response = requests.get(url, timeout=10)
            logger.info(f"Response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                logger.error(f"Server returned an error: {data['error']}")
                print(f"{Fore.RED}Server error: {data['error']}{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Server error"))
                spinner_thread.start()
                time.sleep(5)
                stop_event.set()
                spinner_thread.join()
                return None
            logger.debug(f"Fetched data: {data}")
            pbar.update(100)
            print(f"{Fore.GREEN}Data fetched successfully!{Style.RESET_ALL}")
            return data
    except requests.RequestException as e:
        logger.error(f"Failed to fetch JSON: {e}")
        print(f"{Fore.RED}Failed to fetch data: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Fetch failed"))
        spinner_thread.start()
        time.sleep(5)
        stop_event.set()
        spinner_thread.join()
        return None
    except Exception as e:
        logger.error(f"Unexpected error in fetch_json: {e}")
        print(f"{Fore.RED}Unexpected error fetching data: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Fetch error"))
        spinner_thread.start()
        time.sleep(5)
        stop_event.set()
        spinner_thread.join()
        return None


def download_file(url: str, filename: str) -> bool:
    logger.info(f"Checking existence of {filename}")
    try:
        if os.path.exists(filename):
            logger.info(f"{filename} exists, skipping download")
            print(f"{Fore.YELLOW}{filename} already exists, skipping...{Style.RESET_ALL}")
            return True

        logger.info(f"Downloading {filename} from {url}")
        print(f"{Fore.CYAN}Downloading {filename}...{Style.RESET_ALL}")

        max_retries = 3
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                with requests.get(url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0)) or (55 * 1024 * 1024)
                    with open(filename, 'wb') as f:
                        with tqdm(total=total_size, unit='B', unit_scale=True, desc="Progress",
                                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                                pbar.update(len(chunk))
                logger.info(f"Downloaded {filename}")
                print(f"{Fore.GREEN}Downloaded {filename} successfully!{Style.RESET_ALL}")
                return True
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Download failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
                    print(f"{Fore.YELLOW}Download failed: {e}. Retrying...{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Retrying download"))
                    spinner_thread.start()
                    time.sleep(retry_delay)
                    stop_event.set()
                    spinner_thread.join()
                else:
                    logger.error(f"Download failed after {max_retries} attempts: {e}")
                    print(f"{Fore.RED}Download failed after {max_retries} attempts: {e}{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Download failed"))
                    spinner_thread.start()
                    time.sleep(5)
                    stop_event.set()
                    spinner_thread.join()
                    return False
    except Exception as e:
        logger.error(f"Unexpected error in download_file: {e}")
        print(f"{Fore.RED}Unexpected error downloading file: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Download error"))
        spinner_thread.start()
        time.sleep(5)
        stop_event.set()
        spinner_thread.join()
        return False

def refresh_shift():
    logger.info("Starting shift refresh")
    print(f"{Fore.CYAN}Attempting to refresh shift...{Style.RESET_ALL}")
    try:
        port = input(f"{Fore.CYAN}On which port is the cash register running?{Style.RESET_ALL} ").strip()
        logger.info(f"User entered port: {port}")

        port = int(port)
        if not (1 <= port <= 65535):
            raise ValueError("Port must be between 1 and 65535")

        url = f"http://127.0.0.1:{port}/api/v1/shift/refresh"
        logger.info(f"Sending POST request to {url}")
        print(f"{Fore.CYAN}Sending request to port {port}...{Style.RESET_ALL}")

        response = requests.post(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == True:
                logger.info(f"Successful response from {url}")
                print(f"{Fore.GREEN}Shift refreshed on port {port}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}Shift was refreshed successfully{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Shift refreshed"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                return True
            else:
                logger.warning(f"Unexpected response from {url}: {data}")
                print(f"{Fore.RED}Failed to refresh shift: unexpected response from port {port}{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Shift failed"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                return False
        else:
            logger.warning(f"Failed with status code {response.status_code} from {url}")
            print(
                f"{Fore.RED}Failed to refresh shift: received status {response.status_code} from port {port}{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Shift failed"))
            spinner_thread.start()
            time.sleep(2)
            stop_event.set()
            spinner_thread.join()
            return False
    except ValueError as e:
        logger.error(f"Invalid port input: {e}")
        print(f"{Fore.RED}Error: Invalid port number ({e}){Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid port"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return False
    except requests.RequestException as e:
        logger.error(f"Failed to connect to port: {e}")
        print(f"{Fore.RED}Failed to refresh shift: could not connect to port ({e}){Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Connection failed"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return False
    except Exception as e:
        logger.error(f"Unexpected error in refresh_shift: {e}")
        print(f"{Fore.RED}Unexpected error refreshing shift: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Shift error"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return False