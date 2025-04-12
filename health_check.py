# -*- coding: utf-8 -*-
import logging
import os
import subprocess
import time
import threading
import sqlite3
from sqlite3 import Error
from typing import Dict, Optional
import json
import requests
import glob

import psutil
from colorama import Fore, Style

from config import DRIVES
from utils import show_spinner, find_process_by_path, find_all_processes_by_name
from cleanup import cleanup  # Импортируем функцию cleanup

logger = logging.getLogger(__name__)

def find_external_cash_registers_by_processes() -> list:
    """
    Ищет кассы по запущенным процессам checkbox_kasa.exe.

    Returns:
        list: Список словарей с информацией о кассах, найденных по процессам.
    """
    external_cashes = []
    seen_paths = set()

    for proc in psutil.process_iter(['pid', 'exe', 'cwd']):
        try:
            if proc.name().lower() == "checkbox_kasa.exe":
                proc_cwd = os.path.normpath(proc.cwd()).lower()
                if proc_cwd not in seen_paths:
                    seen_paths.add(proc_cwd)
                    external_cashes.append({
                        "path": proc_cwd,
                        "source": "process"
                    })
                    logger.info(f"Found external cash register via process at {proc_cwd}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return external_cashes

def find_external_cash_registers_by_filesystem() -> list:
    """
    Ищет кассы по файловой системе с ограничением на глубину 2 от корня диска.

    Returns:
        list: Список словарей с информацией о кассах, найденных по файлам.
    """
    external_cashes = []
    seen_paths = set()

    for drive in DRIVES:
        try:
            # Ищем checkbox_kasa.exe на глубине 2
            pattern = os.path.join(drive, "*", "*", "checkbox_kasa.exe")
            for kasa_exe in glob.glob(pattern, recursive=False):
                kasa_dir = os.path.normpath(os.path.dirname(kasa_exe)).lower()
                if kasa_dir not in seen_paths:
                    seen_paths.add(kasa_dir)
                    external_cashes.append({
                        "path": kasa_dir,
                        "source": "filesystem"
                    })
                    logger.info(f"Found external cash register via filesystem at {kasa_dir}")
        except Exception as e:
            logger.warning(f"Error searching in {drive}: {e}")

    return external_cashes

def get_cash_register_info(cash_path: str, is_external: bool = False) -> Dict:
    """
    Собирает информацию о кассе по её пути.

    Args:
        cash_path (str): Путь к папке кассы.
        is_external (bool): Является ли касса внешней.

    Returns:
        Dict: Информация о кассе (имя, здоровье, статусы и т.д.).
    """
    db_path = os.path.join(cash_path, "agent.db")
    version = "Unknown"
    fiscal_number = "Unknown"
    health = "BAD"
    trans_status = "ERROR"
    shift_status = "OPENED"
    is_running = bool(find_process_by_path("checkbox_kasa.exe", cash_path))

    # Проверяем файл version
    try:
        version_path = os.path.join(cash_path, "version")
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
    except Exception as e:
        logger.error(f"Failed to read version file for cash at {cash_path}: {e}")

    # Проверяем базу данных
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT fiscal_number FROM cash_register LIMIT 1;")
            result = cursor.fetchone()
            if result and result[0]:
                fiscal_number = result[0]
            else:
                logger.debug(f"No fiscal_number found for cash at {cash_path}")
            conn.close()
        except Error as e:
            logger.error(f"Failed to fetch fiscal_number for cash at {cash_path}: {e}")

        for attempt in range(3):
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
                    logger.info(f"Transactions status for cash at {cash_path}: {trans_status}")

                    cursor.execute("SELECT status FROM shifts WHERE id = (SELECT MAX(id) FROM shifts);")
                    shift_result = cursor.fetchone()
                    if shift_result:
                        shift_status = shift_result[0].upper()
                        logger.info(f"Shift status for cash at {cash_path}: {shift_status}")
                    else:
                        logger.debug(f"No shifts found for cash at {cash_path}")
                        shift_status = "CLOSED"
                break
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

    name = f"[External] {os.path.basename(cash_path)}" if is_external else os.path.basename(cash_path)
    return {
        "name": name,
        "path": cash_path,
        "health": health,
        "trans_status": trans_status,
        "shift_status": shift_status,
        "version": version,
        "fiscal_number": fiscal_number,
        "is_running": is_running,
        "is_external": is_external
    }

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
        print(f"{Fore.CYAN}      CHECK CASH REGISTER HEALTH{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
        print()

        # Показываем спиннер на время поиска
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Searching cash registers"))
        spinner_thread.start()

        try:
            profiles_info = []
            target_folder = "checkbox.kasa.manager"
            profiles_dir = None

            # 1. Проверяем наличие папки менеджера
            for drive in DRIVES:
                path = f"{drive}\\{target_folder}"
                profiles_path = os.path.join(path, "profiles")
                if os.path.exists(profiles_path):
                    profiles_dir = profiles_path
                    break

            if profiles_dir:
                # Если менеджер найден, ищем только внутри profiles
                logger.info(f"Manager folder found at {profiles_dir}, searching profiles only")
                profile_folders = [f for f in os.listdir(profiles_dir) if os.path.isdir(os.path.join(profiles_dir, f))]
                if not profile_folders:
                    logger.warning(f"No profile folders found in {profiles_dir}")
                    print(f"{Fore.YELLOW}No profiles found in {profiles_dir}{Style.RESET_ALL}")
                else:
                    for profile in profile_folders:
                        profile_path = os.path.join(profiles_dir, profile)
                        profiles_info.append(get_cash_register_info(profile_path, is_external=False))
            else:
                # Если менеджер не найден, ищем процессы
                logger.info("Manager folder not found, searching for processes")
                external_cashes = find_external_cash_registers_by_processes()
                if external_cashes:
                    for cash in external_cashes:
                        profiles_info.append(get_cash_register_info(cash["path"], is_external=True))
                else:
                    # Если процессы не найдены, ищем по файловой системе
                    logger.info("No processes found, searching filesystem")
                    external_cashes = find_external_cash_registers_by_filesystem()
                    for cash in external_cashes:
                        profiles_info.append(get_cash_register_info(cash["path"], is_external=True))

            if not profiles_info:
                logger.error("No profiles or external cash registers found")
                print(f"{Fore.RED}Error: No profiles or external cash registers found!{Style.RESET_ALL}")
                stop_event.set()
                spinner_thread.join()
                input("Press Enter to continue...")
                return

            logger.info(f"Total profiles found: {len(profiles_info)}")
            stop_event.set()
            spinner_thread.join()

            # Выводим профили с номерами
            print(f"{Fore.CYAN}Available profiles:{Style.RESET_ALL}")
            print()
            for i, profile in enumerate(profiles_info, 1):
                health_color = Fore.GREEN if profile["health"] == "OK" else Fore.RED
                trans_color = Fore.GREEN if profile["trans_status"] in ["DONE", "EMPTY"] else Fore.RED
                shift_color = Fore.GREEN if profile["shift_status"] == "CLOSED" else Fore.RED
                status_text = "ON" if profile["is_running"] else "OFF"
                status_color = Fore.GREEN if profile["is_running"] else Fore.RED
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
            print(f"Use 'R<number>' to refresh shift, 'C<number>' to update config, 'O<number>' to open folder, 'Q' to quit, or 0 to go back")
            print(f"0. Back")
            print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")

            # Запрашиваем выбор пользователя
            choice = input("Select a profile, R<number>, C<number>, O<number>, Q to quit, or 0 to go back: ").strip()
            logger.info(f"User input in profile selection: {choice}")

            # Проверяем команду Q (выход с очисткой)
            if choice.lower() == "q":
                logger.info("User chose to quit the application")
                print(f"{Fore.GREEN}Initiating cleanup and exit...{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Cleaning up"))
                spinner_thread.start()
                time.sleep(1)
                stop_event.set()
                spinner_thread.join()
                cleanup(data, api_handler)
                return

            # Проверяем команду 0 (возврат в меню)
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

            # Проверяем команду O<number> (открытие папки)
            if choice.lower().startswith("o") and len(choice) > 1:
                try:
                    profile_num = int(choice[1:])  # Извлекаем число после 'O'
                    if 1 <= profile_num <= len(profiles_info):
                        selected_profile = profiles_info[profile_num - 1]
                        logger.info(f"User chose to open folder for profile: {selected_profile['name']}")
                        folder_path = selected_profile['path']
                        if os.path.exists(folder_path):
                            try:
                                os.startfile(folder_path)  # Открываем папку в проводнике
                                logger.info(f"Opened folder {folder_path} in explorer")
                                print(f"{Fore.GREEN}Opened folder {folder_path} in explorer!{Style.RESET_ALL}")
                            except Exception as e:
                                logger.error(f"Failed to open folder {folder_path}: {e}")
                                print(f"{Fore.RED}Failed to open folder: {e}{Style.RESET_ALL}")
                        else:
                            logger.error(f"Folder not found: {folder_path}")
                            print(f"{Fore.RED}Folder not found: {folder_path}{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Folder opened"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                        continue
                    else:
                        logger.warning(f"Invalid profile number for open folder: {choice}")
                        print(f"{Fore.RED}Invalid profile number!{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                        continue
                except ValueError:
                    logger.warning(f"Invalid open folder command format: {choice}")
                    print(f"{Fore.RED}Invalid open folder command format! Use O<number> (e.g., O1){Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    continue

            # Проверяем команду C<number> (обновление конфига)
            if choice.lower().startswith("c") and len(choice) > 1:
                try:
                    profile_num = int(choice[1:])  # Извлекаем число после 'C'
                    if 1 <= profile_num <= len(profiles_info):
                        selected_profile = profiles_info[profile_num - 1]
                        logger.info(f"User chose to update config for profile: {selected_profile['name']}")

                        # Запрашиваем license_key
                        license_key = input("Please paste license_key and press ENTER: ").strip()
                        if license_key.isspace() or not license_key:
                            license_key = None
                            logger.info("User provided empty license_key, will not update")
                        else:
                            logger.info(f"User provided license_key: {license_key}")

                        # Запрашиваем pin_code
                        pin_code = input("Please paste pin-code and press ENTER: ").strip()
                        if pin_code.isspace() or not pin_code:
                            pin_code = None
                            logger.info("User provided empty pin_code, will not update")
                        else:
                            logger.info(f"User provided pin_code: {pin_code}")

                        # Проверяем состояние кассы и менеджера
                        kasa_process = find_process_by_path("checkbox_kasa.exe", selected_profile['path'])
                        manager_processes = find_all_processes_by_name("kasa_manager.exe")
                        manager_suspended = False

                        # Выключаем кассу, если она запущена
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
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process error"))
                                spinner_thread.start()
                                time.sleep(2)
                                stop_event.set()
                                spinner_thread.join()
                                continue

                        # Замораживаем менеджер, если он запущен
                        if manager_processes:
                            print(f"{Fore.YELLOW}Freezing all manager processes...{Style.RESET_ALL}")
                            for proc in manager_processes:
                                try:
                                    proc.suspend()
                                    logger.info(f"Suspended kasa_manager.exe (PID: {proc.pid})")
                                    print(f"{Fore.GREEN}Suspended kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                                    manager_suspended = True
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

                        # Читаем config.json
                        config_path = os.path.join(selected_profile['path'], "config.json")
                        if not os.path.exists(config_path):
                            logger.error(f"config.json not found in {selected_profile['path']}")
                            print(f"{Fore.RED}Error: config.json not found!{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            # Размораживаем менеджер
                            if manager_suspended and manager_processes:
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
                            continue

                        try:
                            with open(config_path, "r", encoding="utf-8") as f:
                                config = json.load(f)
                        except Exception as e:
                            logger.error(f"Failed to read config.json for {selected_profile['name']}: {e}")
                            print(f"{Fore.RED}Error reading config.json: {e}{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            # Размораживаем менеджер
                            if manager_suspended and manager_processes:
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
                            continue

                        # Обновляем provider
                        provider = config.get("provider", {})
                        updated = False
                        if license_key:
                            provider["license_key"] = license_key
                            updated = True
                            logger.info(f"Updated license_key to {license_key}")
                        if pin_code:
                            provider["pin_code"] = pin_code
                            updated = True
                            logger.info(f"Updated pin_code to {pin_code}")
                        config["provider"] = provider

                        # Сохраняем config.json
                        if updated:
                            try:
                                with open(config_path, "w", encoding="utf-8") as f:
                                    json.dump(config, f, indent=4, ensure_ascii=False)
                                logger.info(f"Successfully updated config.json for {selected_profile['name']}")
                                print(f"{Fore.GREEN}Config updated successfully for {selected_profile['name']}!{Style.RESET_ALL}")
                            except Exception as e:
                                logger.error(f"Failed to write config.json for {selected_profile['name']}: {e}")
                                print(f"{Fore.RED}Error writing config.json: {e}{Style.RESET_ALL}")
                                # Размораживаем менеджер
                                if manager_suspended and manager_processes:
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
                                continue
                        else:
                            logger.info(f"No changes made to config.json for {selected_profile['name']}")
                            print(f"{Fore.YELLOW}No changes made to config (empty inputs).{Style.RESET_ALL}")

                        # Запускаем кассу
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
                                # Размораживаем менеджер
                                if manager_suspended and manager_processes:
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
                                continue
                        else:
                            logger.warning(f"checkbox_kasa.exe not found in {selected_profile['path']}")
                            print(f"{Fore.YELLOW}checkbox_kasa.exe not found in {selected_profile['path']}{Style.RESET_ALL}")
                            # Размораживаем менеджер
                            if manager_suspended and manager_processes:
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
                            continue

                        # Размораживаем менеджер
                        if manager_suspended and manager_processes:
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

                        # Возвращаемся в меню
                        print(f"{Fore.GREEN}Returning to cash register health check...{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Returning"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                        continue
                    else:
                        logger.warning(f"Invalid profile number for config update: {choice}")
                        print(f"{Fore.RED}Invalid profile number!{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                        continue
                except ValueError:
                    logger.warning(f"Invalid config command format: {choice}")
                    print(f"{Fore.RED}Invalid config command format! Use C<number> (e.g., C1){Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    continue

            # Проверяем команду R<number> (обновление смены)
            if choice.lower().startswith("r") and len(choice) > 1:
                try:
                    profile_num = int(choice[1:])  # Извлекаем число после 'R'
                    if 1 <= profile_num <= len(profiles_info):
                        selected_profile = profiles_info[profile_num - 1]
                        logger.info(f"User chose to refresh shift for profile: {selected_profile['name']}")

                        # Читаем config.json
                        config_path = os.path.join(selected_profile['path'], "config.json")
                        if not os.path.exists(config_path):
                            logger.error(f"config.json not found in {selected_profile['path']}")
                            print(f"{Fore.RED}Error: config.json not found!{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            continue

                        try:
                            with open(config_path, "r", encoding="utf-8") as f:
                                config = json.load(f)
                            web_server = config.get("web_server", {})
                            host = web_server.get("host", "127.0.0.1")
                            port = web_server.get("port", 9200)
                        except Exception as e:
                            logger.error(f"Failed to read config.json for {selected_profile['name']}: {e}")
                            print(f"{Fore.RED}Error reading config.json: {e}{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            continue

                        # Отправляем POST-запрос для обновления смены
                        url = f"http://{host}:{port}/api/v1/shift/refresh"
                        try:
                            response = requests.post(url, timeout=5)
                            response.raise_for_status()
                            logger.info(f"Shift refresh successful for {selected_profile['name']}: {response.status_code}")
                            print(f"{Fore.GREEN}Shift refreshed successfully for {selected_profile['name']}!{Style.RESET_ALL}")
                        except requests.RequestException as e:
                            logger.error(f"Failed to refresh shift for {selected_profile['name']}: {e}")
                            print(f"{Fore.RED}Failed to refresh shift: {e}{Style.RESET_ALL}")

                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Shift refresh"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                        continue
                    else:
                        logger.warning(f"Invalid profile number for refresh: {choice}")
                        print(f"{Fore.RED}Invalid profile number!{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                        continue
                except ValueError:
                    logger.warning(f"Invalid refresh command format: {choice}")
                    print(f"{Fore.RED}Invalid refresh command format! Use R<number> (e.g., R1){Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    continue

            # Обрабатываем выбор профиля
            try:
                choice_int = int(choice)
                if 1 <= choice_int <= len(profiles_info):
                    selected_profile = profiles_info[choice_int - 1]
                    logger.info(f"User selected profile: {selected_profile['name']}")

                    # Убиваем процесс кассы
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

                    # Запускаем кассу
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

                    # Размораживаем менеджер
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

                    # Возвращаемся в меню
                    print(f"{Fore.GREEN}Returning to cash register health check...{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Returning"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    continue
                else:
                    logger.warning(f"Invalid profile choice: {choice}")
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