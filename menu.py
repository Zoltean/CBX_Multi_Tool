import os
import subprocess
import sys
import time
import threading
import platform
import sqlite3
from typing import Dict, Optional

import psutil
from colorama import init, Fore, Style

from config import PROGRAM_TITLE, VPS_API_URL, DRIVES
from network import check_for_updates, fetch_json, refresh_shift
from utils import is_admin, run_spinner, find_all_processes_by_name, find_process_by_path
from cleanup import cleanup
from patching import install_file, patch_file
from health_check import check_cash_profiles

if sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
if sys.stderr.encoding != 'utf-8':
    sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

def display_menu(title: str, options: Dict, data: Dict, parent_menu: Optional[Dict] = None,
                 update_available: bool = False, download_url: str = "", sha256: str = ""):
    """
    Відображає інтерактивне меню з опціями та обробляє вибір користувача.

    Функція створює структуроване меню на основі переданих опцій, групуючи їх за категоріями
    (Менеджери, каси, PayLink тощо), і дозволяє користувачу вибирати дії,
    такі як встановлення файлів, застосування патчів, перевірка стану кас або вихід із програми.
    Підтримує навігацію між меню, оновлення програми та очищення даних при виході.

    Args:
        title (str): Заголовок меню.
        options (Dict): Словник із опціями меню, де ключі — назви категорій, а значення — списки
                        або словники з даними.
        data (Dict): Дані, отримані з API.
        parent_menu (Optional[Dict], optional): Дані про батьківське меню для повернення назад.
                                               Defaults to None.
        update_available (bool, optional): Чи доступне оновлення програми. Defaults to False.
        download_url (str, optional): URL для завантаження оновлення. Defaults to "".
        sha256 (str, optional): SHA256-хеш оновлення для перевірки. Defaults to "".

    Returns:
        None: Функція не повертає значень, а керує інтерфейсом та завершує виконання при виході.

    Raises:
        Exception: Загальні помилки, такі як ValueError при некоректному введенні або проблеми
                   з мережею чи файловою системою.
    """
    while True:
        try:
            os.system("cls")
            print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{title.center(50)}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}\n")

            menu_items = []
            for key, value in options.items():
                if isinstance(value, list):
                    for i, item in enumerate(value):
                        menu_items.append((f"{key}_{i}", item))
                else:
                    menu_items.append((key, value))

            is_top_level = title.lower() in ["main menu", "patching", "tools"]
            ordered_items = menu_items.copy()

            if not is_top_level:
                ordered_items = []
                for key, value in menu_items:
                    if "kasa_manager" in key.lower():
                        ordered_items.append((key, value))
                for key, value in menu_items:
                    if ("rro_agent" in key.lower() and "tools" not in key.lower()) or \
                            (title.lower() == "cloudlike" and "kasa_manager" not in key.lower() and "paylink" not in key.lower()):
                        ordered_items.append((key, value))
                for key, value in menu_items:
                    if "paylink" in key.lower():
                        ordered_items.append((key, value))
                for key, value in menu_items:
                    if "terminal_drivers" in key.lower():
                        ordered_items.append((key, value))
                for key, value in menu_items:
                    if "os_tools" in key.lower():
                        ordered_items.append((key, value))
                for key, value in menu_items:
                    if "diagnostics" in key.lower():
                        ordered_items.append((key, value))
                for key, value in menu_items:
                    if "config_tools" in key.lower():
                        ordered_items.append((key, value))
                for key, value in menu_items:
                    if "rro_agent_tools" in key.lower():
                        ordered_items.append((key, value))
                for key, value in menu_items:
                    if (all(x not in key.lower() for x in
                            ["kasa_manager", "rro_agent", "paylink", "terminal_drivers", "os_tools", "diagnostics",
                             "config_tools", "rro_agent_tools"]) and
                            not (title.lower() == "cloudlike" and "kasa_manager" not in key.lower() and "paylink" not in key.lower())):
                        ordered_items.append((key, value))

            if not ordered_items:
                print(f"{Fore.RED}✗ No options available.{Style.RESET_ALL}")
                run_spinner("No options", 2.0)
                return

            current_index = 1

            if is_top_level:
                for key, value in ordered_items:
                    name = key.capitalize() if isinstance(value, dict) else value.get("name", value.get("patch_name", key.capitalize()))
                    print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                    current_index += 1
            else:
                managers = [item for item in ordered_items if "kasa_manager" in item[0].lower()]
                if managers:
                    print(f"{Fore.CYAN}=== Managers ==={Style.RESET_ALL}")
                    for key, value in managers:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                        current_index += 1
                    print()

                cash_registers = [item for item in ordered_items if "rro_agent" in item[0].lower() and "tools" not in item[0].lower() or (title.lower() == "cloudlike" and "kasa_manager" not in item[0].lower() and "paylink" not in item[0].lower())]
                if cash_registers:
                    print(f"{Fore.GREEN}=== Cash Registers ==={Style.RESET_ALL}")
                    for key, value in cash_registers:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                        current_index += 1
                    print()

                paylinks = [item for item in ordered_items if "paylink" in item[0].lower()]
                if paylinks:
                    print(f"{Fore.YELLOW}=== PayLinks ==={Style.RESET_ALL}")
                    for key, value in paylinks:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                        current_index += 1
                    print()

                terminal_drivers = [item for item in ordered_items if "terminal_drivers" in item[0].lower()]
                if terminal_drivers:
                    print(f"{Fore.MAGENTA}=== Terminal Drivers ==={Style.RESET_ALL}")
                    for key, value in terminal_drivers:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                        current_index += 1
                    print()

                os_tools = [item for item in ordered_items if "os_tools" in item[0].lower()]
                if os_tools:
                    print(f"{Fore.BLUE}=== OS Tools ==={Style.RESET_ALL}")
                    for key, value in os_tools:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                        current_index += 1
                    print()

                diagnostics = [item for item in ordered_items if "diagnostics" in item[0].lower()]
                if diagnostics:
                    print(f"{Fore.GREEN}=== Diagnostics ==={Style.RESET_ALL}")
                    for key, value in diagnostics:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                        current_index += 1
                    print()

                config_tools = [item for item in ordered_items if "config_tools" in item[0].lower()]
                if config_tools:
                    print(f"{Fore.BLUE}=== Config Tools ==={Style.RESET_ALL}")
                    for key, value in config_tools:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                        current_index += 1
                    print()

                rro_agent_tools = [item for item in ordered_items if "rro_agent_tools" in item[0].lower()]
                if rro_agent_tools:
                    print(f"{Fore.GREEN}=== RRO Agent Tools ==={Style.RESET_ALL}")
                    for key, value in rro_agent_tools:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{Fore.WHITE}{current_index}. {name}{Style.RESET_ALL}")
                        current_index += 1
                    print()

            print(f"\n{Fore.WHITE}=== Options ==={Style.RESET_ALL}")
            if parent_menu:
                print(f"{Fore.WHITE}0. Back{Style.RESET_ALL}")
            if title.lower() == "main menu":
                print(f"{Fore.WHITE}H. Check Cash Register Health{Style.RESET_ALL}")
                print(f"{Fore.WHITE}R. Refresh Shift{Style.RESET_ALL}")
            print(f"{Fore.WHITE}Q. Exit{Style.RESET_ALL}")
            print(f"{Fore.WHITE}{'=' * 50}{Style.RESET_ALL}\n")

            if title.lower() == "main menu" and update_available:
                print(f"{Fore.YELLOW}🎉 New version available! Press U to download.{Style.RESET_ALL}\n")

            choice = input(f"{Fore.CYAN}Enter your choice: {Style.RESET_ALL}")

            if choice.lower() in ["q", "й"]:
                cleanup(data)
                sys.exit(0)

            if title.lower() == "main menu" and choice.lower() in ["h", "р"]:
                check_cash_profiles(data)
                continue

            if title.lower() == "main menu" and choice.lower() in ["r", "к"]:
                refresh_shift()
                continue

            if title.lower() == "main menu" and choice.lower() in ["u", "г"] and update_available:
                print(f"{Fore.CYAN}Downloading update...{Style.RESET_ALL}")
                from network import download_file
                filename = os.path.basename(download_url)
                if not sha256:
                    print(f"{Fore.YELLOW}⚠ Warning: No SHA256 hash provided by API. Download will proceed without hash verification.{Style.RESET_ALL}")
                if download_file(download_url, filename, expected_sha256=sha256):
                    print(f"{Fore.GREEN}✓ Update downloaded and verified successfully!{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}✗ Failed to download or verify update.{Style.RESET_ALL}")
                run_spinner("Update processed", 2.0)
                continue

            try:
                choice_int = int(choice)
                if choice_int == 0 and parent_menu:
                    return
                if 1 <= choice_int <= len(ordered_items):
                    key, value = ordered_items[choice_int - 1]
                    if callable(value):
                        value()
                    elif "url" in value:
                        paylink_patch_data = None
                        if "paylink" in key.lower() and "dev" in title.lower():
                            paylink_patch_data = data["dev"]["paylink"][-1]
                        install_file(value, paylink_patch_data, data, expected_sha256=value.get("sha256", ""))
                    elif "patch_url" in value:
                        is_rro_agent = "rro_agent" in key.lower() and "tools" not in key.lower()
                        is_paylink = "paylink" in key.lower()
                        patch_file(value, "checkbox.kasa.manager" if not (is_rro_agent or is_paylink) else "Checkbox PayLink (Beta)" if is_paylink else "checkbox.kasa.manager", data, is_rro_agent, is_paylink, expected_sha256=value.get("sha256", ""))
                    else:
                        display_menu(key.capitalize(), value, data, parent_menu={"title": title, "options": options},
                                     update_available=update_available, download_url=download_url, sha256=sha256)
                else:
                    print(f"{Fore.RED}✗ Invalid option!{Style.RESET_ALL}")
                    run_spinner("Invalid option", 2.0)
            except ValueError:
                print(f"{Fore.RED}✗ Invalid input!{Style.RESET_ALL}")
                run_spinner("Invalid input", 2.0)
        except Exception as e:
            print(f"{Fore.RED}✗ Menu error: {e}{Style.RESET_ALL}")
            run_spinner("Menu error", 2.0)

if __name__ == "__main__":
    from main import main
    main()