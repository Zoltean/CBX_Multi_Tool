# -*- coding: utf-8 -*-
import logging
import os
import subprocess
import sys
import time
import threading
import platform
import sqlite3
from sqlite3 import Error
from typing import Dict, Optional

import psutil
from colorama import init, Fore, Style

from config import PROGRAM_TITLE, VPS_API_URL, DRIVES
from logging_setup import setup_logging
from network import check_for_updates, fetch_json, refresh_shift
from utils import is_admin, show_spinner, find_all_processes_by_name, find_process_by_path
from cleanup import cleanup
from patching import install_file, patch_file
from health_check import check_cash_profiles  # Новый импорт

logger = logging.getLogger(__name__)

def display_menu(title: str, options: Dict, data: Dict, api_handler=None, parent_menu: Optional[Dict] = None,
                 update_available: bool = False, download_url: str = ""):
    logger.info(f"Rendering menu: {title}")
    while True:
        try:
            os.system("cls")
            print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}           {title.upper()}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
            print()

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
                            (
                                    title.lower() == "cloudlike" and "kasa_manager" not in key.lower() and "paylink" not in key.lower()):
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
                            not (
                                    title.lower() == "cloudlike" and "kasa_manager" not in key.lower() and "paylink" not in key.lower())):
                        ordered_items.append((key, value))

            if not ordered_items:
                logger.warning("No items to display in menu")
                print(f"{Fore.RED}No options available!{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "No options"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                return

            current_index = 1

            if is_top_level:
                for key, value in ordered_items:
                    name = key.capitalize() if isinstance(value, dict) else value.get("name", value.get("patch_name",
                                                                                                        key.capitalize()))
                    print(f"{current_index}. {name}")
                    logger.info(f"Item {current_index}: {name}")
                    current_index += 1
            else:
                managers = [item for item in ordered_items if "kasa_manager" in item[0].lower()]
                if managers:
                    print(f"{Fore.CYAN}=== Managers ==={Style.RESET_ALL}")
                    for key, value in managers:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{current_index}. {name}")
                        logger.info(f"Item {current_index}: {name}")
                        current_index += 1
                    print(f"{Fore.CYAN}---------------{Style.RESET_ALL}")
                    print()

                cash_registers = [item for item in ordered_items if
                                  "rro_agent" in item[0].lower() and "tools" not in item[0].lower() or
                                  (title.lower() == "cloudlike" and "kasa_manager" not in item[
                                      0].lower() and "paylink" not in item[0].lower())]
                if cash_registers:
                    print(f"{Fore.GREEN}=== Cash Registers ==={Style.RESET_ALL}")
                    for key, value in cash_registers:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{current_index}. {name}")
                        logger.info(f"Item {current_index}: {name}")
                        current_index += 1
                    print(f"{Fore.GREEN}---------------{Style.RESET_ALL}")
                    print()

                paylinks = [item for item in ordered_items if "paylink" in item[0].lower()]
                if paylinks:
                    print(f"{Fore.YELLOW}=== PayLinks ==={Style.RESET_ALL}")
                    for key, value in paylinks:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{current_index}. {name}")
                        logger.info(f"Item {current_index}: {name}")
                        current_index += 1
                    print(f"{Fore.YELLOW}---------------{Style.RESET_ALL}")
                    print()

                terminal_drivers = [item for item in ordered_items if "terminal_drivers" in item[0].lower()]
                if terminal_drivers:
                    print(f"{Fore.MAGENTA}=== Terminal Drivers ==={Style.RESET_ALL}")
                    for key, value in terminal_drivers:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{current_index}. {name}")
                        logger.info(f"Item {current_index}: {name}")
                        current_index += 1
                    print(f"{Fore.MAGENTA}---------------{Style.RESET_ALL}")
                    print()

                os_tools = [item for item in ordered_items if "os_tools" in item[0].lower()]
                if os_tools:
                    print(f"{Fore.BLUE}=== OS Tools ==={Style.RESET_ALL}")
                    for key, value in os_tools:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{current_index}. {name}")
                        logger.info(f"Item {current_index}: {name}")
                        current_index += 1
                    print(f"{Fore.BLUE}---------------{Style.RESET_ALL}")
                    print()

                diagnostics = [item for item in ordered_items if "diagnostics" in item[0].lower()]
                if diagnostics:
                    print(f"{Fore.GREEN}=== Diagnostics ==={Style.RESET_ALL}")
                    for key, value in diagnostics:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{current_index}. {name}")
                        logger.info(f"Item {current_index}: {name}")
                        current_index += 1
                    print(f"{Fore.GREEN}---------------{Style.RESET_ALL}")
                    print()

                config_tools = [item for item in ordered_items if "config_tools" in item[0].lower()]
                if config_tools:
                    print(f"{Fore.BLUE}=== Config Tools ==={Style.RESET_ALL}")
                    for key, value in config_tools:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{current_index}. {name}")
                        logger.info(f"Item {current_index}: {name}")
                        current_index += 1
                    print(f"{Fore.BLUE}---------------{Style.RESET_ALL}")
                    print()

                rro_agent_tools = [item for item in ordered_items if "rro_agent_tools" in item[0].lower()]
                if rro_agent_tools:
                    print(f"{Fore.GREEN}=== RRO Agent Tools ==={Style.RESET_ALL}")
                    for key, value in rro_agent_tools:
                        name = value.get("name", value.get("patch_name", key.capitalize()))
                        print(f"{current_index}. {name}")
                        logger.info(f"Item {current_index}: {name}")
                        current_index += 1
                    print(f"{Fore.GREEN}---------------{Style.RESET_ALL}")
                    print()

            print()
            print(f"{Fore.WHITE}=== Options ==={Style.RESET_ALL}")
            if parent_menu:
                print(f"0. Back")
                logger.info("Added Back option: 0")
            if title.lower() == "main menu":
                print(f"H. Check Cash register Health")
                print(f"R. Refresh Shift")
                logger.info("Added Check Cash register Health option: H/Р")
                logger.info("Added Refresh Shift option: R/К")
            print(f"Q. Exit with cleanup")
            logger.info("Added Exit with cleanup option: Q/Й")
            print(f"{Fore.WHITE}---------------{Style.RESET_ALL}")
            print()

            if title.lower() == "main menu" and update_available:
                print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}New version available.{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Press U to download update{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")

            print("Select an option:")
            choice = input("")
            logger.info(f"User input: {choice}")

            if choice.lower() in ["q", "й"]:
                logger.info("User chose to exit with cleanup")
                cleanup(data, api_handler)
                sys.exit(0)

            if title.lower() == "main menu" and choice.lower() in ["h", "р"]:
                logger.info("User chose to check profiles health")
                check_cash_profiles(data, api_handler)  # Вызов из health_check.py
                continue

            if title.lower() == "main menu" and choice.lower() in ["r", "к"]:
                logger.info("User chose to refresh shift")
                refresh_shift()
                continue

            if title.lower() == "main menu" and choice.lower() in ["u", "г"] and update_available:
                logger.info("User chose to download update")
                print(f"{Fore.CYAN}Opening download link in browser...{Style.RESET_ALL}")
                try:
                    import webbrowser
                    webbrowser.open(download_url)
                except Exception as e:
                    logger.error(f"Failed to open browser for update: {e}")
                    print(f"{Fore.RED}Failed to open browser: {e}{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Opening browser"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                continue

            try:
                choice_int = int(choice)
                if choice_int == 0 and parent_menu:
                    logger.info(f"Returning to {parent_menu['title']}")
                    return
                if 1 <= choice_int <= len(ordered_items):
                    key, value = ordered_items[choice_int - 1]
                    logger.info(f"Selected: {key}")
                    if callable(value):
                        value()
                    elif "url" in value:
                        paylink_patch_data = None
                        if "paylink" in key.lower() and "dev" in title.lower():
                            paylink_patch_data = data["dev"]["paylink"][-1]
                        install_file(value, paylink_patch_data, data)
                    elif "patch_url" in value:
                        is_rro_agent = "rro_agent" in key.lower() and "tools" not in key.lower()
                        is_paylink = "paylink" in key.lower()
                        patch_file(value, "checkbox.kasa.manager" if not (
                                    is_rro_agent or is_paylink) else "Checkbox PayLink (Beta)" if is_paylink else "checkbox.kasa.manager",
                                   data, is_rro_agent, is_paylink)
                    else:
                        display_menu(key.capitalize(), value, data, api_handler=api_handler,
                                     parent_menu={"title": title, "options": options},
                                     update_available=update_available, download_url=download_url)
                else:
                    logger.warning(f"Invalid option: {choice_int}")
                    print(f"{Fore.RED}[ERROR] Invalid option!{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid option"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
            except ValueError:
                logger.warning(f"Invalid input: {choice}")
                print(f"{Fore.RED}[ERROR] Invalid option!{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid option"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
        except Exception as e:
            logger.error(f"Unexpected error in display_menu: {e}")
            print(f"{Fore.RED}Unexpected error in menu: {e}{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Menu error"))
            spinner_thread.start()
            time.sleep(2)
            stop_event.set()
            spinner_thread.join()

if __name__ == "__main__":
    API_HANDLER = setup_logging()
    from main import main
    main(API_HANDLER)