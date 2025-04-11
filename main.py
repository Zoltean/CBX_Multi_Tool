# -*- coding: utf-8 -*-
import logging
import os
import time  # Добавлен импорт time
from colorama import Fore, Style

from config import PROGRAM_TITLE, VPS_API_URL
from logging_setup import setup_logging
from network import check_for_updates, fetch_json
from menu import display_menu
from utils import is_admin

logger = logging.getLogger(__name__)

def main():
    logger.info("Starting CBX Core")
    print(f"{Fore.CYAN}Starting CBX Core...{Style.RESET_ALL}")

    try:
        if not is_admin():
            print(
                f"{Fore.YELLOW}Warning: {PROGRAM_TITLE} is not running as administrator, some features will be unavailable.{Style.RESET_ALL}")
            time.sleep(3)  # Теперь time определен
        else:
            print(f"{Fore.GREEN}Running with admin privileges.{Style.RESET_ALL}")
            time.sleep(1)  # Теперь time определен

        update_available, download_url = check_for_updates()

        data = fetch_json(VPS_API_URL)
        if not data:
            logger.error("No data fetched, exiting")
            input("Press Enter to exit...")
            return

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
            }
        }

        display_menu("Main Menu", menu_options, data, update_available=update_available, download_url=download_url)
        logger.info("Program completed normally")
        print(f"{Fore.GREEN}Program completed!{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        print(f"{Fore.RED}Unexpected error in program: {e}{Style.RESET_ALL}")
        input("Press Enter to exit...")

if __name__ == "__main__":
    setup_logging()
    main()