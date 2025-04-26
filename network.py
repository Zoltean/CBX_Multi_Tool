import os
import requests
import hashlib
from typing import Dict, Optional, Tuple
from tqdm import tqdm
from ping3 import ping
from colorama import Fore, Style
from utils import run_spinner
from config import VPS_VERSION_URL

def calculate_file_hash(filepath: str) -> str:
    """Вычисление SHA256 хэша файла."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest().lower()
    except Exception as e:
        print(f"{Fore.RED}✗ Error calculating hash for {filepath}: {e}{Style.RESET_ALL}")
        return ""

def check_for_updates() -> Tuple[bool, str, str]:
    print(f"{Fore.CYAN}🔍 Checking for updates...{Style.RESET_ALL}")
    try:
        response = requests.get(VPS_VERSION_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        latest_version = data.get("version")
        download_url = data.get("download_url", "")
        sha256 = data.get("sha256", "")
        from config import PROGRAM_VERSION
        if latest_version and latest_version != PROGRAM_VERSION:
            print(f"{Fore.GREEN}✓ New version {latest_version} available!{Style.RESET_ALL}")
            run_spinner("Update check completed", 1.0)
            return True, download_url, sha256
        else:
            print(f"{Fore.GREEN}✓ You are using the latest version.{Style.RESET_ALL}")
            run_spinner("Update check completed", 1.0)
            return False, "", ""
    except requests.RequestException:
        print(f"{Fore.RED}✗ Failed to check for updates.{Style.RESET_ALL}")
        run_spinner("Update check failed", 2.0)
        return False, "", ""
    except Exception as e:
        print(f"{Fore.RED}✗ Update check error: {e}{Style.RESET_ALL}")
        run_spinner("Update check error", 2.0)
        return False, "", ""

def check_server_status(url: str) -> bool:
    try:
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]
        result = ping(domain, timeout=5)
        if result is not None and result is not False:
            print(f"{Fore.GREEN}✓ Server is online.{Style.RESET_ALL}")
            run_spinner("Server check completed", 1.0)
            return True
        else:
            print(f"{Fore.RED}✗ Server is offline.{Style.RESET_ALL}")
            run_spinner("Server check failed", 2.0)
            return False
    except Exception:
        print(f"{Fore.RED}✗ Failed to ping server.{Style.RESET_ALL}")
        run_spinner("Server ping failed", 2.0)
        return False

def fetch_json(url: str) -> Optional[Dict]:
    print(f"{Fore.CYAN}📡 Connecting to server...{Style.RESET_ALL}")
    try:
        with tqdm(total=100, desc="Fetching data", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                print(f"{Fore.RED}✗ Server error: {data['error']}{Style.RESET_ALL}")
                run_spinner("Server error", 2.0)
                return None
            pbar.update(100)
            print(f"{Fore.GREEN}✓ Data retrieved successfully!{Style.RESET_ALL}")
            run_spinner("Data fetch completed", 1.0)
            return data
    except requests.RequestException as e:
        print(f"{Fore.RED}✗ Failed to connect: {e}{Style.RESET_ALL}")
        run_spinner("Connection failed", 2.0)
        return None
    except Exception as e:
        print(f"{Fore.RED}✗ Data fetch error: {e}{Style.RESET_ALL}")
        run_spinner("Fetch error", 2.0)
        return None

def download_file(url: str, filename: str, expected_sha256: str = "") -> bool:
    print(f"{Fore.CYAN}📥 Preparing to download {filename}...{Style.RESET_ALL}")
    expected_sha256 = expected_sha256.lower() if expected_sha256 else ""
    try:
        if os.path.exists(filename):
            print(f"{Fore.YELLOW}⚠ {filename} already exists, checking hash...{Style.RESET_ALL}")
            if expected_sha256:
                computed_hash = calculate_file_hash(filename)
                if computed_hash == expected_sha256:
                    print(f"{Fore.GREEN}✓ Hash matches: {filename} is valid.{Style.RESET_ALL}")
                    run_spinner("Hash check completed", 1.0)
                    return True
                else:
                    print(f"{Fore.RED}✗ Hash mismatch: {filename} is corrupted. Redownloading...{Style.RESET_ALL}")
                    os.remove(filename)
            else:
                print(f"{Fore.YELLOW}⚠ No expected hash provided, skipping hash check.{Style.RESET_ALL}")
                run_spinner("Hash check skipped", 1.0)
                return True

        max_retries = 3
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                with requests.get(url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0)) or (55 * 1024 * 1024)
                    with open(filename, 'wb') as f:
                        with tqdm(total=total_size, unit='B', unit_scale=True, desc="Downloading",
                                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                                pbar.update(len(chunk))
                print(f"{Fore.GREEN}✓ Downloaded {filename} successfully!{Style.RESET_ALL}")

                if expected_sha256:
                    computed_hash = calculate_file_hash(filename)
                    if computed_hash == expected_sha256:
                        print(f"{Fore.GREEN}✓ Hash matches: {filename} is valid.{Style.RESET_ALL}")
                        run_spinner("Download completed", 1.0)
                        return True
                    else:
                        print(f"{Fore.RED}✗ Hash mismatch: {filename} is corrupted.{Style.RESET_ALL}")
                        os.remove(filename)
                        run_spinner("Hash mismatch", 2.0)
                        return False
                else:
                    print(f"{Fore.YELLOW}⚠ No expected hash provided, skipping hash check.{Style.RESET_ALL}")
                    run_spinner("Download completed", 1.0)
                    return True

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    print(f"{Fore.YELLOW}⚠ Download failed, retrying...{Style.RESET_ALL}")
                    run_spinner("Retrying download", retry_delay)
                else:
                    print(f"{Fore.RED}✗ Download failed after {max_retries} attempts.{Style.RESET_ALL}")
                    run_spinner("Download failed", 2.0)
                    return False
    except Exception as e:
        print(f"{Fore.RED}✗ Download error: {e}{Style.RESET_ALL}")
        run_spinner("Download error", 2.0)
        return False

def refresh_shift():
    print(f"{Fore.CYAN}🔄 Refreshing shift...{Style.RESET_ALL}")
    try:
        port = input(f"{Fore.CYAN}Enter cash register port: {Style.RESET_ALL}").strip()
        port = int(port)
        if not (1 <= port <= 65535):
            raise ValueError("Port must be between 1 and 65535")

        url = f"http://127.0.0.1:{port}/api/v1/shift/refresh"
        print(f"{Fore.CYAN}Sending request to port {port}...{Style.RESET_ALL}")

        response = requests.post(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == True:
                print(f"{Fore.GREEN}✓ Shift refreshed successfully on port {port}!{Style.RESET_ALL}")
                run_spinner("Shift refreshed", 1.0)
                return True
            else:
                print(f"{Fore.RED}✗ Failed to refresh shift: unexpected response.{Style.RESET_ALL}")
                run_spinner("Shift failed", 2.0)
                return False
        else:
            print(f"{Fore.RED}✗ Failed to refresh shift: error {response.status_code}.{Style.RESET_ALL}")
            run_spinner("Shift failed", 2.0)
            return False
    except ValueError as e:
        print(f"{Fore.RED}✗ Invalid port: {e}{Style.RESET_ALL}")
        run_spinner("Invalid port", 2.0)
        return False
    except requests.RequestException as e:
        print(f"{Fore.RED}✗ Failed to connect: {e}{Style.RESET_ALL}")
        run_spinner("Connection failed", 2.0)
        return False
    except Exception as e:
        print(f"{Fore.RED}✗ Shift refresh error: {e}{Style.RESET_ALL}")
        run_spinner("Refresh error", 2.0)
        return False