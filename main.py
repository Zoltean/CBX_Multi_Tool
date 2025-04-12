# -*- coding: utf-8 -*-
import atexit
import logging
import os
import time
import threading
import platform
from colorama import init, Fore, Style

from config import PROGRAM_TITLE, VPS_API_URL
from network import check_for_updates, fetch_json
from menu import display_menu
from utils import is_admin, show_spinner
from cleanup import cleanup  # Импортируем cleanup

# Инициализация colorama
init()

# Настройка локального логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cbx_multi_tool.log'),  # Логи в файл
        logging.StreamHandler()  # Логи в консоль (опционально)
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting CBX Core")
    print(f"{Fore.CYAN}Starting CBX Core...{Style.RESET_ALL}")

    try:
        if not is_admin():
            print(
                f"{Fore.YELLOW}Warning: {PROGRAM_TITLE} is not running as administrator, some features will be unavailable.{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Checking privileges"))
            spinner_thread.start()
            time.sleep(3)
            stop_event.set()
            spinner_thread.join()
        else:
            print(f"{Fore.GREEN}Running with admin privileges.{Style.RESET_ALL}")
            time.sleep(1)

        update_available, download_url = check_for_updates()

        data = fetch_json(VPS_API_URL)
        if not data:
            logger.error("No data fetched, exiting")
            print(
                f"{Fore.RED}Could not fetch data from server. Please check your internet connection.{Style.RESET_ALL}")
            input("Press Enter to exit...")
            return

        # Формирование меню с твоей структурой
        menu_options = {
            "legacy": {
                "kasa_manager": data["legacy"]["kasa_manager"],
                "rro_agent": data["legacy"]["rro_agent"]
            },
            "dev": {
                "kasa_manager": data["dev"]["kasa_manager"],
                "rro_agent": data["dev"]["rro_agent"],
                "paylink": data["dev"]["paylink"]
            },
            "cloudlike": {
                "cloudlike": data["legacy"]["cloudlike"]
            },
            "patching": {
                "legacy": {
                    "kasa_manager": [
                        {"patch_name": item["patch_name"], "patch_url": item["patch_url"]}
                        for item in data["legacy"]["kasa_manager"]
                        if "patch_name" in item and "patch_url" in item
                    ],
                    "rro_agent": [
                        {"patch_name": item["patch_name"], "patch_url": item["patch_url"]}
                        for item in data["legacy"]["rro_agent"]
                        if "patch_name" in item and "patch_url" in item
                    ]
                },
                "dev": {
                    "kasa_manager": [
                        {"patch_name": item["patch_name"], "patch_url": item["patch_url"]}
                        for item in data["dev"]["kasa_manager"]
                        if "patch_name" in item and "patch_url" in item
                    ],
                    "rro_agent": [
                        {"patch_name": item["patch_name"], "patch_url": item["patch_url"]}
                        for item in data["dev"]["rro_agent"]
                        if "patch_name" in item and "patch_url" in item
                    ],
                    "paylink": [
                        {"patch_name": item["patch_name"], "patch_url": item["patch_url"]}
                        for item in data["dev"]["paylink"]
                        if "patch_name" in item and "patch_url" in item
                    ]
                }
            },
            "tools": {
                "paylink": {
                    "terminal_drivers": data["tools"]["paylink"]["terminal_drivers"],
                    "os_tools": data["tools"]["paylink"]["os_tools"]
                },
                "rro_agent_tools": {
                    "diagnostics": data["tools"]["rro_agent_tools"]["diagnostics"],
                    "config_tools": data["tools"]["rro_agent_tools"]["config_tools"]
                }
            },
        }

        # Вызов display_menu без api_handler
        display_menu("Main Menu", menu_options, data,
                     update_available=update_available, download_url=download_url)

        logger.info("Program completed normally")
        print(f"{Fore.GREEN}Program completed!{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        print(f"{Fore.RED}Unexpected error in program: {e}{Style.RESET_ALL}")
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()