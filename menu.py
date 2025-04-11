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
                print(f"H. Check Profiles Health")
                print(f"R. Refresh Shift")
                logger.info("Added Check Profiles Health option: H/Р")
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
                check_cash_profiles(data, api_handler)
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

def check_cash_profiles(data: Dict, api_handler=None):
    logger.info("Starting cash profiles health check")
    while True:  # Зацикливаем для возврата в меню
        os.system("cls")
        print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}           CHECK PROFILES HEALTH{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
        print()

        # Показываем спиннер на время поиска
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Searching profiles"))
        spinner_thread.start()

        try:
            target_folder = "checkbox.kasa.manager"
            profiles_dir = None
            for drive in DRIVES:
                path = f"{drive}\\{target_folder}"
                profiles_path = os.path.join(path, "profiles")
                if os.path.exists(profiles_path):
                    profiles_dir = profiles_path
                    break

            if not profiles_dir:
                logger.error(f"Profiles folder not found for {target_folder}")
                print(f"{Fore.RED}Error: Profiles folder not found on any drive!{Style.RESET_ALL}")
                stop_event.set()
                spinner_thread.join()
                input("Press Enter to continue...")
                return

            profile_folders = [f for f in os.listdir(profiles_dir) if os.path.isdir(os.path.join(profiles_dir, f))]
            if not profile_folders:
                logger.error(f"No profile folders found in {profiles_dir}")
                print(f"{Fore.RED}Error: No profile folders found in {profiles_dir}!{Style.RESET_ALL}")
                stop_event.set()
                spinner_thread.join()
                input("Press Enter to continue...")
                return

            logger.info(f"Found profiles: {profile_folders}")
            stop_event.set()
            spinner_thread.join()

            # Собираем информацию о профилях
            profiles_info = []
            for profile in profile_folders:
                profile_path = os.path.join(profiles_dir, profile)
                db_path = os.path.join(profile_path, "agent.db")
                version = "Unknown"

                try:
                    if os.path.exists(os.path.join(profile_path, "version")):
                        with open(os.path.join(profile_path, "version"), "r", encoding="utf-8") as f:
                            version = f.read().strip()
                except Exception as e:
                    logger.error(f"Failed to read version file for {profile}: {e}")

                health = "BAD"
                trans_status = "ERROR"
                shift_status = "OPENED"
                conn = None
                for attempt in range(3):  # 3 попытки подключения
                    try:
                        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                        cursor = conn.cursor()

                        cursor.execute("PRAGMA integrity_check;")
                        result = cursor.fetchone()[0]
                        if result == "ok":
                            health = "OK"
                            logger.info(f"Database {db_path} is healthy")

                            cursor.execute("SELECT status FROM transactions;")
                            statuses = [row[0] for row in cursor.fetchall()]
                            if not statuses:
                                trans_status = "EMPTY"
                            elif any(s == "ERROR" for s in statuses):
                                trans_status = "ERROR"
                            elif any(s == "PENDING" for s in statuses):
                                trans_status = "PENDING"
                            else:
                                trans_status = "DONE"
                            logger.info(f"Transactions status for {profile}: {trans_status}")

                            cursor.execute("SELECT status FROM shifts WHERE id = (SELECT MAX(id) FROM shifts);")
                            shift_result = cursor.fetchone()
                            if shift_result:
                                shift_status = shift_result[0].upper()
                                logger.info(f"Shift status for {profile}: {shift_status}")
                            else:
                                logger.debug(f"No shifts found in {profile}")
                                shift_status = "CLOSED"
                        break  # Успешное подключение
                    except Error as e:
                        logger.warning(f"Attempt {attempt + 1}/3 failed to connect to {db_path}: {e}")
                        if attempt == 2:
                            logger.error(f"All attempts failed for {db_path}: {e}")
                        time.sleep(1)
                    finally:
                        if conn:
                            conn.close()
                            logger.debug(f"Closed connection to {db_path}")
                            time.sleep(0.1)

                # Формируем строку вывода для профиля
                health_color = Fore.GREEN if health == "OK" else Fore.RED
                trans_status_color = Fore.GREEN if trans_status in ["DONE", "EMPTY"] else Fore.RED
                shift_status_color = Fore.GREEN if shift_status == "CLOSED" else Fore.RED
                output = (
                    f"Health: {health_color}{health}{Style.RESET_ALL} | "
                    f"{trans_status_color}{trans_status}{Style.RESET_ALL} | "
                    f"{shift_status_color}{shift_status}{Style.RESET_ALL} "
                    f"v{version}"
                )
                profiles_info.append((profile, output, profile_path))

            # Выводим профили с номерами
            print(f"{Fore.CYAN}Available profiles:{Style.RESET_ALL}")
            for i, (profile, info, _) in enumerate(profiles_info, 1):
                print(f"{i}. {Fore.WHITE}{profile}{Style.RESET_ALL} {info}")
            print(f"0. Back")
            print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")

            # Запрашиваем выбор пользователя
            choice = input("Select a profile to restart or 0 to go back: ").strip()
            logger.info(f"User input in profile selection: {choice}")

            if choice == "0":
                logger.info("User chose to return from profile health check")
                print(f"{Fore.GREEN}Returning to main menu...{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Returning"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                return

            try:
                choice_int = int(choice)
                if 1 <= choice_int <= len(profiles_info):
                    selected_profile, _, selected_path = profiles_info[choice_int - 1]
                    logger.info(f"User selected profile: {selected_profile}")

                    # Убиваем процесс кассы, если он запущен
                    kasa_process = find_process_by_path("checkbox_kasa.exe", selected_path)
                    if kasa_process:
                        try:
                            kasa_process.kill()
                            logger.info(f"Killed checkbox_kasa.exe (PID: {kasa_process.pid}) for {selected_profile}")
                            print(f"{Fore.GREEN}Killed checkbox_kasa.exe (PID: {kasa_process.pid}).{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process killed"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()
                        except psutil.NoSuchProcess:
                            logger.warning(f"checkbox_kasa.exe already terminated for {selected_profile}")
                        except Exception as e:
                            logger.error(f"Failed to kill checkbox_kasa.exe for {selected_profile}: {e}")
                            print(f"{Fore.RED}Failed to kill process: {e}{Style.RESET_ALL}")

                    # Замораживаем процессы менеджера
                    manager_processes = find_all_processes_by_name("kasa_manager.exe")
                    if manager_processes:
                        print(f"{Fore.YELLOW}Freezing all manager processes...{Style.RESET_ALL}")
                        for proc in manager_processes:
                            try:
                                proc.suspend()
                                logger.info(f"Suspended kasa_manager.exe (PID: {proc.pid})")
                                print(f"{Fore.GREEN}Suspended kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                            except psutil.NoSuchProcess:
                                logger.warning(f"kasa_manager.exe (PID: {proc.pid}) already terminated")
                            except Exception as e:
                                logger.error(f"Failed to suspend kasa_manager.exe (PID: {proc.pid}): {e}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes suspended"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()

                    # Запускаем кассу в отдельной консоли
                    kasa_path = os.path.join(selected_path, "checkbox_kasa.exe")
                    if os.path.exists(kasa_path):
                        try:
                            logger.info(f"Launching {kasa_path} via cmd")
                            print(f"{Fore.CYAN}Launching cash register {kasa_path}...{Style.RESET_ALL}")
                            cmd = f'start cmd /K "{kasa_path}"'
                            subprocess.Popen(cmd, cwd=selected_path, shell=True)
                            logger.info(f"Successfully launched {kasa_path}")
                            print(f"{Fore.GREEN}Cash register launched successfully!{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Cash register launched"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                        except Exception as e:
                            logger.error(f"Failed to launch {kasa_path}: {e}")
                            print(f"{Fore.RED}Failed to launch cash register: {e}{Style.RESET_ALL}")
                    else:
                        logger.warning(f"checkbox_kasa.exe not found in {selected_path}")
                        print(f"{Fore.YELLOW}checkbox_kasa.exe not found in {selected_path}{Style.RESET_ALL}")

                    # Ждём 3 секунды и размораживаем менеджер
                    time.sleep(3)
                    if manager_processes:
                        print(f"{Fore.YELLOW}Resuming all manager processes...{Style.RESET_ALL}")
                        for proc in manager_processes:
                            try:
                                proc.resume()
                                logger.info(f"Resumed kasa_manager.exe (PID: {proc.pid})")
                                print(f"{Fore.GREEN}Resumed kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                            except psutil.NoSuchProcess:
                                logger.warning(f"kasa_manager.exe (PID: {proc.pid}) already terminated")
                            except Exception as e:
                                logger.error(f"Failed to resume kasa_manager.exe (PID: {proc.pid}): {e}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes resumed"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()

                    # Возвращаемся в меню "H" (continue перезапустит цикл)
                    print(f"{Fore.GREEN}Returning to profile health check...{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Returning"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    continue
                else:
                    logger.warning(f"Invalid profile choice: {choice_int}")
                    print(f"{Fore.RED}Invalid choice!{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
            except ValueError:
                logger.warning(f"Invalid input: {choice}")
                print(f"{Fore.RED}Invalid input!{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()

        except Exception as e:
            logger.error(f"Unexpected error in check_cash_profiles: {e}")
            print(f"{Fore.RED}Unexpected error: {e}{Style.RESET_ALL}")
            if 'stop_event' in locals():
                stop_event.set()
                spinner_thread.join()
            input("Press Enter to continue...")
            return

        if api_handler:
            api_handler.flush()

if __name__ == "__main__":
    API_HANDLER = setup_logging()
    from main import main
    main(API_HANDLER)