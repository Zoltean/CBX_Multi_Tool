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
    """
    Обчислює SHA256-хеш файлу.

    Функція зчитує файл поблочно та обчислює його SHA256-хеш для перевірки цілісності.

    Args:
        filepath (str): Шлях до файлу, для якого обчислюється хеш.

    Returns:
        str: Рядок із SHA256-хешем у нижньому регістрі або порожній рядок у разі помилки.

    Raises:
        Exception: Помилки, такі як FileNotFoundError або PermissionError, якщо файл недоступний.
    """
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
    """
    Перевіряє наявність оновлень програми, порівнюючи поточну версію з версією на сервері.

    Функція звертається до API за URL із конфігурації, отримує дані про останню версію,
    URL для завантаження та SHA256-хеш, і порівнює версію з поточною.

    Args:
        None

    Returns:
        Tuple[bool, str, str]: Кортеж, що містить:
            - bool: Чи доступне оновлення (True, якщо є нова версія).
            - str: URL для завантаження оновлення (або порожній рядок).
            - str: SHA256-хеш оновлення (або порожній рядок).

    Raises:
        requests.RequestException: Якщо не вдалося виконати HTTP-запит.
        Exception: Інші непередбачені помилки під час перевірки.
    """
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
    """
    Перевіряє доступність сервера шляхом виконання пінгу.

    Функція видаляє протокол і шлях із URL, виконує пінг до домену та визначає,
    чи сервер доступний.

    Args:
        url (str): URL сервера для перевірки.

    Returns:
        bool: True, якщо сервер доступний, False у разі помилки або недоступності.

    Raises:
        Exception: Помилки, пов’язані з пінгуванням або обробкою URL.
    """
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
    """
    Отримує JSON-дані з вказаного URL.

    Функція виконує HTTP GET-запит до сервера, отримує відповідь у форматі JSON
    та повертає її як словник. Відображає прогрес із використанням tqdm.

    Args:
        url (str): URL для отримання JSON-даних.

    Returns:
        Optional[Dict]: Словник із даними або None у разі помилки.

    Raises:
        requests.RequestException: Якщо не вдалося виконати HTTP-запит.
        Exception: Інші помилки, такі як некоректний JSON або серверна помилка.
    """
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
    """
    Завантажує файл із вказаного URL із підтримкою докачки та перевіркою SHA256-хеша.

    Функція перевіряє, чи файл уже існує, і якщо так, порівнює його хеш із очікуваним.
    Якщо хеш не збігається або файл частково завантажений, продовжує завантаження з потрібного місця
    за допомогою HTTP-заголовка Range. Виконує до трьох спроб завантаження у разі помилок мережі.
    Прогрес відображається за допомогою tqdm.

    Args:
        url (str): URL для завантаження файлу.
        filename (str): Ім'я файлу для збереження.
        expected_sha256 (str, optional): Очікуваний SHA256-хеш файлу. Defaults to "".

    Returns:
        bool: True, якщо завантаження та перевірка успішні, False у разі помилки.

    Raises:
        requests.RequestException: Якщо не вдалося виконати HTTP-запит.
        Exception: Інші помилки, такі як проблеми з файловою системою.
    """
    print(f"{Fore.CYAN}📥 Preparing to download {filename}...{Style.RESET_ALL}")
    expected_sha256 = expected_sha256.lower() if expected_sha256 else ""

    try:
        # Перевірка, чи файл уже існує
        if os.path.exists(filename):
            print(f"{Fore.YELLOW}⚠ {filename} already exists, checking hash...{Style.RESET_ALL}")
            if expected_sha256:
                computed_hash = calculate_file_hash(filename)
                if computed_hash == expected_sha256:
                    print(f"{Fore.GREEN}✓ Hash matches: {filename} is valid.{Style.RESET_ALL}")
                    run_spinner("Hash check completed", 1.0)
                    return True
                else:
                    print(f"{Fore.RED}✗ Hash mismatch: {filename} is corrupted. Checking for partial download...{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠ No expected hash provided, checking for partial download...{Style.RESET_ALL}")

        # Отримання розміру файлу на сервері
        response = requests.head(url, timeout=10)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0)) or (55 * 1024 * 1024)  # Запасний розмір, якщо не вказано

        # Перевірка розміру локального файлу для докачки
        current_size = os.path.getsize(filename) if os.path.exists(filename) else 0

        if current_size >= total_size and expected_sha256:
            computed_hash = calculate_file_hash(filename)
            if computed_hash == expected_sha256:
                print(f"{Fore.GREEN}✓ File already fully downloaded and valid.{Style.RESET_ALL}")
                run_spinner("Download completed", 1.0)
                return True
            else:
                print(f"{Fore.RED}✗ Hash mismatch, restarting download...{Style.RESET_ALL}")
                os.remove(filename)
                current_size = 0
        elif current_size > 0:
            print(f"{Fore.YELLOW}⚠ Resuming download from {current_size} bytes...{Style.RESET_ALL}")

        max_retries = 3
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                headers = {'Range': f'bytes={current_size}-'} if current_size > 0 else {}
                with requests.get(url, stream=True, headers=headers, timeout=10) as r:
                    r.raise_for_status()
                    # Оновлення розміру для докачки
                    remaining_size = total_size - current_size
                    with open(filename, 'ab' if current_size > 0 else 'wb') as f:
                        with tqdm(total=total_size, initial=current_size, unit='B', unit_scale=True, desc="Downloading",
                                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                                pbar.update(len(chunk))
                                current_size += len(chunk)

                print(f"{Fore.GREEN}✓ Downloaded {filename} successfully!{Style.RESET_ALL}")

                # Перевірка хеша після завантаження
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
                    print(f"{Fore.YELLOW}⚠ Download failed, retrying in {retry_delay} seconds...{Style.RESET_ALL}")
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
    """

    Функція запитує порт у користувача, формує URL для API касового апарата
    та надсилає POST-запит для оновлення зміни.

    Args:
        None

    Returns:
        bool: True, якщо зміна успішно оновлена, False у разі помилки.

    Raises:
        ValueError: Якщо введено некоректний порт.
        requests.RequestException: Якщо не вдалося виконати HTTP-запит.
        Exception: Інші непередбачені помилки під час виконання запиту.
    """
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