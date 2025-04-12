# -*- coding: utf-8 -*-
import logging
import os
import subprocess
import time
import threading
import sqlite3
from sqlite3 import Error
from typing import Dict, Optional

import psutil
from colorama import Fore, Style

from config import DRIVES
from utils import show_spinner, find_process_by_path, find_all_processes_by_name

logger = logging.getLogger(__name__)

def check_cash_profiles(data: Dict, api_handler=None):
    """
    Проверяет здоровье профилей кассы и позволяет управлять ими.

    Args:
        data (Dict): Данные приложения (например, конфигурация).
        api_handler: Обработчик API для логирования (опционально).
    """
    logger.info("Starting cash register health check")
    while True:  # Зацикливаем для возврата в меню
        os.system("cls")
        print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}           CHECK CASH REGISTER HEALTH{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
        print()

        # Показываем спиннер на время поиска
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Searching cash registers"))
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
                fiscal_number = "Unknown"

                try:
                    if os.path.exists(os.path.join(profile_path, "version")):
                        with open(os.path.join(profile_path, "version"), "r", encoding="utf-8") as f:
                            version = f.read().strip()
                except Exception as e:
                    logger.error(f"Failed to read version file for {profile}: {e}")

                try:
                    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("SELECT fiscal_number FROM cash_register LIMIT 1;")
                    result = cursor.fetchone()
                    if result and result[0]:
                        fiscal_number = result[0]
                    else:
                        logger.debug(f"No fiscal_number found for {profile}")
                    conn.close()
                except Error as e:
                    logger.error(f"Failed to fetch fiscal_number for {profile}: {e}")

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

                # Проверяем, запущен ли процесс checkbox_kasa.exe
                is_running = bool(find_process_by_path("checkbox_kasa.exe", profile_path))

                profiles_info.append({
                    "name": profile,
                    "path": profile_path,
                    "health": health,
                    "trans_status": trans_status,
                    "shift_status": shift_status,
                    "version": version,
                    "fiscal_number": fiscal_number,
                    "is_running": is_running
                })

            # Выводим профили с номерами
            print(f"{Fore.CYAN}Available profiles:{Style.RESET_ALL}")
            print()
            for i, profile in enumerate(profiles_info, 1):
                health_color = Fore.GREEN if profile["health"] == "OK" else Fore.RED
                trans_color = Fore.GREEN if profile["trans_status"] in ["DONE", "EMPTY"] else Fore.RED
                shift_color = Fore.GREEN if profile["shift_status"] == "CLOSED" else Fore.RED
                status_text = "ON" if profile["is_running"] else "OFF"
                status_color = Fore.RED if profile["is_running"] else Fore.GREEN
                profile_str = (
                    f"| {Fore.YELLOW}FN:{profile['fiscal_number']}{Style.RESET_ALL} "
                    f"| {status_color}{status_text}{Style.RESET_ALL} "
                    f"| H:{health_color}{profile['health']}{Style.RESET_ALL} "
                    f"| T:{trans_color}{profile['trans_status']}{Style.RESET_ALL} "
                    f"| S:{shift_color}{profile['shift_status']}{Style.RESET_ALL} "
                    f"| v{profile['version']}"
                )
                print(f"{i}. {Fore.CYAN}{profile['name']}{Style.RESET_ALL} {profile_str}")
            print()
            print(f"0. Back")
            print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")

            # Запрашиваем выбор пользователя
            choice = input("Select a profile of cash register or 0 to go back: ").strip()
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
                    selected_profile = profiles_info[choice_int - 1]
                    logger.info(f"User selected profile: {selected_profile['name']}")

                    # Убиваем процесс кассы, если он запущен
                    kasa_process = find_process_by_path("checkbox_kasa.exe", selected_profile['path'])
                    if kasa_process:
                        try:
                            kasa_process.kill()
                            logger.info(f"Killed checkbox_kasa.exe (PID: {kasa_process.pid}) for {selected_profile['name']}")
                            print(f"{Fore.GREEN}Killed checkbox_kasa.exe (PID: {kasa_process.pid}).{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process killed"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()
                        except psutil.NoSuchProcess:
                            logger.warning(f"checkbox_kasa.exe already terminated for {selected_profile['name']}")
                        except Exception as e:
                            logger.error(f"Failed to kill checkbox_kasa.exe for {selected_profile['name']}: {e}")
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
                    kasa_path = os.path.join(selected_profile['path'], "checkbox_kasa.exe")
                    if os.path.exists(kasa_path):
                        try:
                            logger.info(f"Launching {kasa_path} via cmd")
                            print(f"{Fore.CYAN}Launching cash register {kasa_path}...{Style.RESET_ALL}")
                            cmd = f'start cmd /K "{kasa_path}"'
                            subprocess.Popen(cmd, cwd=selected_profile['path'], shell=True)
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
                        logger.warning(f"checkbox_kasa.exe not found in {selected_profile['path']}")
                        print(f"{Fore.YELLOW}checkbox_kasa.exe not found in {selected_profile['path']}{Style.RESET_ALL}")

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
                    print(f"{Fore.GREEN}Returning to cash register health check...{Style.RESET_ALL}")
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

        finally:
            if api_handler:
                api_handler.flush()