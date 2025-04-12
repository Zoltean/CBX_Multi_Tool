# -*- coding: utf-8 -*-
import os
import subprocess
import time
import threading
import sqlite3
from sqlite3 import Error
from typing import Dict
import json
import requests
import glob

import psutil
from colorama import Fore, Style

from config import DRIVES
from utils import show_spinner, find_process_by_path, find_all_processes_by_name
from cleanup import cleanup

def find_external_cash_registers_by_processes() -> list:
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
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return external_cashes

def find_external_cash_registers_by_filesystem() -> list:
    external_cashes = []
    seen_paths = set()

    for drive in DRIVES:
        try:
            pattern = os.path.join(drive, "*", "*", "checkbox_kasa.exe")
            for kasa_exe in glob.glob(pattern, recursive=False):
                kasa_dir = os.path.normpath(os.path.dirname(kasa_exe)).lower()
                if kasa_dir not in seen_paths:
                    seen_paths.add(kasa_dir)
                    external_cashes.append({
                        "path": kasa_dir,
                        "source": "filesystem"
                    })
        except Exception:
            continue

    return external_cashes

def get_cash_register_info(cash_path: str, is_external: bool = False) -> Dict:
    db_path = os.path.join(cash_path, "agent.db")
    version = "Unknown"
    fiscal_number = "Unknown"
    health = "BAD"
    trans_status = "ERROR"
    shift_status = "OPENED"
    is_running = bool(find_process_by_path("checkbox_kasa.exe", cash_path))

    try:
        version_path = os.path.join(cash_path, "version")
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
    except Exception:
        pass

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT fiscal_number FROM cash_register LIMIT 1;")
            result = cursor.fetchone()
            if result and result[0]:
                fiscal_number = result[0]
            conn.close()
        except Error:
            pass

        for attempt in range(3):
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                cursor = conn.cursor()

                cursor.execute("PRAGMA integrity_check;")
                result = cursor.fetchone()[0]
                if result == "ok":
                    health = "OK"
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

                    cursor.execute("SELECT status FROM shifts WHERE id = (SELECT MAX(id) FROM shifts);")
                    shift_result = cursor.fetchone()
                    if shift_result:
                        shift_status = shift_result[0].upper()
                    else:
                        shift_status = "CLOSED"
                break
            except Error:
                time.sleep(2)
            finally:
                if conn:
                    conn.close()
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

def check_cash_profiles(data: Dict):
    while True:
        os.system("cls")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
        print(f"{Fore.CYAN} CASH REGISTER HEALTH CHECK ".center(50) + f"{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}\n")

        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Searching cash registers"))
        spinner_thread.start()

        try:
            profiles_info = []
            target_folder = "checkbox.kasa.manager"
            profiles_dir = None

            for drive in DRIVES:
                path = f"{drive}\\{target_folder}"
                profiles_path = os.path.join(path, "profiles")
                if os.path.exists(profiles_path):
                    profiles_dir = profiles_path
                    break

            if profiles_dir:
                profile_folders = [f for f in os.listdir(profiles_dir) if os.path.isdir(os.path.join(profiles_dir, f))]
                if not profile_folders:
                    print(f"{Fore.YELLOW}⚠ No profiles found in {profiles_dir}{Style.RESET_ALL}")
                else:
                    for profile in profile_folders:
                        profile_path = os.path.join(profiles_dir, profile)
                        profiles_info.append(get_cash_register_info(profile_path, is_external=False))
            else:
                external_cashes = find_external_cash_registers_by_processes()
                if external_cashes:
                    for cash in external_cashes:
                        profiles_info.append(get_cash_register_info(cash["path"], is_external=True))
                else:
                    external_cashes = find_external_cash_registers_by_filesystem()
                    for cash in external_cashes:
                        profiles_info.append(get_cash_register_info(cash["path"], is_external=True))

            stop_event.set()
            spinner_thread.join()

            if not profiles_info:
                print(f"{Fore.RED}✗ No profiles or external cash registers found!{Style.RESET_ALL}")
                input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
                return

            print(f"{Fore.CYAN}Found {len(profiles_info)} cash registers:{Style.RESET_ALL}\n")
            for i, profile in enumerate(profiles_info, 1):
                health_color = Fore.GREEN if profile["health"] == "OK" else Fore.RED
                trans_color = Fore.GREEN if profile["trans_status"] in ["DONE", "EMPTY"] else Fore.RED
                shift_color = Fore.GREEN if profile["shift_status"] == "CLOSED" else Fore.RED
                status_text = "ON" if profile["is_running"] else "OFF"
                status_color = Fore.RED if profile["is_running"] else Fore.GREEN
                profile_str = (
                    f"| {Fore.YELLOW}FN: {profile['fiscal_number']}{Style.RESET_ALL} "
                    f"| {status_color}{status_text}{Style.RESET_ALL} "
                    f"| H:{health_color}{profile['health']}{Style.RESET_ALL} "
                    f"| T:{trans_color}{profile['trans_status']}{Style.RESET_ALL} "
                    f"| S:{shift_color}{profile['shift_status']}{Style.RESET_ALL} "
                    f"| v{profile['version']}"
                )
                print(f"{Fore.WHITE}{i}. {profile['name']} {profile_str}{Style.RESET_ALL}")

            print(f"\n{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Options:{Style.RESET_ALL}")
            print(f"{Fore.WHITE}  <number> - Launch profile{Style.RESET_ALL}")
            print(f"{Fore.WHITE}  O<number> - Open profile folder{Style.RESET_ALL}")
            print(f"{Fore.WHITE}  C<number> - Update config{Style.RESET_ALL}")
            print(f"{Fore.WHITE}  R<number> - Refresh shift{Style.RESET_ALL}")
            print(f"{Fore.WHITE}  0 - Back to main menu{Style.RESET_ALL}")
            print(f"{Fore.WHITE}  Q - Quit{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

            choice = input(f"{Fore.CYAN}Enter your choice: {Style.RESET_ALL}").strip()

            if choice.lower() == "q":
                print(f"{Fore.CYAN}🧹 Initiating cleanup and exit...{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Cleaning up"))
                spinner_thread.start()
                time.sleep(1)
                stop_event.set()
                spinner_thread.join()
                cleanup(data)
                return

            if choice == "0":
                print(f"{Fore.GREEN}✓ Returning to main menu...{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Returning"))
                spinner_thread.start()
                time.sleep(1)
                stop_event.set()
                spinner_thread.join()
                return

            if choice.lower().startswith("o") and len(choice) > 1:
                try:
                    profile_num = int(choice[1:])
                    if 1 <= profile_num <= len(profiles_info):
                        selected_profile = profiles_info[profile_num - 1]
                        folder_path = selected_profile['path']
                        if os.path.exists(folder_path):
                            os.startfile(folder_path)
                            print(f"{Fore.GREEN}✓ Opened folder {folder_path}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.RED}✗ Folder not found: {folder_path}{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Folder opened"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()
                    else:
                        print(f"{Fore.RED}✗ Invalid profile number!{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                except ValueError:
                    print(f"{Fore.RED}✗ Invalid format! Use O<number> (e.g., O1){Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                continue

            if choice.lower().startswith("c") and len(choice) > 1:
                try:
                    profile_num = int(choice[1:])
                    if 1 <= profile_num <= len(profiles_info):
                        selected_profile = profiles_info[profile_num - 1]
                        print(f"{Fore.CYAN}Updating config for {selected_profile['name']}...{Style.RESET_ALL}")

                        license_key = input(f"{Fore.CYAN}Enter license_key (or press Enter to skip): {Style.RESET_ALL}").strip()
                        pin_code = input(f"{Fore.CYAN}Enter pin-code (or press Enter to skip): {Style.RESET_ALL}").strip()

                        kasa_process = find_process_by_path("checkbox_kasa.exe", selected_profile['path'])
                        manager_processes = find_all_processes_by_name("kasa_manager.exe")
                        manager_suspended = False

                        if kasa_process:
                            try:
                                kasa_process.kill()
                                print(f"{Fore.GREEN}✓ Stopped checkbox_kasa.exe (PID: {kasa_process.pid}){Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process stopped"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            except psutil.NoSuchProcess:
                                pass
                            except Exception as e:
                                print(f"{Fore.RED}✗ Failed to stop process: {e}{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process error"))
                                spinner_thread.start()
                                time.sleep(2)
                                stop_event.set()
                                spinner_thread.join()
                                continue

                        if manager_processes:
                            print(f"{Fore.YELLOW}⏸ Suspending manager processes...{Style.RESET_ALL}")
                            for proc in manager_processes:
                                try:
                                    proc.suspend()
                                    print(f"{Fore.GREEN}✓ Suspended kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                                    manager_suspended = True
                                except psutil.NoSuchProcess:
                                    pass
                                except Exception:
                                    pass
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes suspended"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()

                        config_path = os.path.join(selected_profile['path'], "config.json")
                        if not os.path.exists(config_path):
                            print(f"{Fore.RED}✗ config.json not found!{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            if manager_suspended and manager_processes:
                                print(f"{Fore.YELLOW}▶ Resuming manager processes...{Style.RESET_ALL}")
                                for proc in manager_processes:
                                    try:
                                        proc.resume()
                                        print(f"{Fore.GREEN}✓ Resumed kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                                    except psutil.NoSuchProcess:
                                        pass
                                    except Exception:
                                        pass
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
                            print(f"{Fore.RED}✗ Error reading config.json: {e}{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            if manager_suspended and manager_processes:
                                print(f"{Fore.YELLOW}▶ Resuming manager processes...{Style.RESET_ALL}")
                                for proc in manager_processes:
                                    try:
                                        proc.resume()
                                        print(f"{Fore.GREEN}✓ Resumed kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                                    except psutil.NoSuchProcess:
                                        pass
                                    except Exception:
                                        pass
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes resumed"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            continue

                        provider = config.get("provider", {})
                        updated = False
                        if license_key:
                            provider["license_key"] = license_key
                            updated = True
                        if pin_code:
                            provider["pin_code"] = pin_code
                            updated = True
                        config["provider"] = provider

                        if updated:
                            try:
                                with open(config_path, "w", encoding="utf-8") as f:
                                    json.dump(config, f, indent=4, ensure_ascii=False)
                                print(f"{Fore.GREEN}✓ Config updated successfully!{Style.RESET_ALL}")
                            except Exception as e:
                                print(f"{Fore.RED}✗ Error writing config.json: {e}{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                                spinner_thread.start()
                                time.sleep(2)
                                stop_event.set()
                                spinner_thread.join()
                                if manager_suspended and manager_processes:
                                    print(f"{Fore.YELLOW}▶ Resuming manager processes...{Style.RESET_ALL}")
                                    for proc in manager_processes:
                                        try:
                                            proc.resume()
                                            print(f"{Fore.GREEN}✓ Resumed kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                                        except psutil.NoSuchProcess:
                                            pass
                                        except Exception:
                                            pass
                                    stop_event = threading.Event()
                                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes resumed"))
                                    spinner_thread.start()
                                    time.sleep(1)
                                    stop_event.set()
                                    spinner_thread.join()
                                continue
                        else:
                            print(f"{Fore.YELLOW}⚠ No changes made (empty inputs){Style.RESET_ALL}")

                        kasa_path = os.path.join(selected_profile['path'], "checkbox_kasa.exe")
                        if os.path.exists(kasa_path):
                            try:
                                print(f"{Fore.CYAN}🚀 Launching cash register...{Style.RESET_ALL}")
                                cmd = f'start cmd /K "{kasa_path}"'
                                subprocess.Popen(cmd, cwd=selected_profile['path'], shell=True)
                                print(f"{Fore.GREEN}✓ Cash register launched successfully!{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Cash register launched"))
                                spinner_thread.start()
                                time.sleep(2)
                                stop_event.set()
                                spinner_thread.join()
                            except Exception as e:
                                print(f"{Fore.RED}✗ Failed to launch cash register: {e}{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Launch error"))
                                spinner_thread.start()
                                time.sleep(2)
                                stop_event.set()
                                spinner_thread.join()
                        else:
                            print(f"{Fore.YELLOW}⚠ checkbox_kasa.exe not found{Style.RESET_ALL}")

                        if manager_suspended and manager_processes:
                            print(f"{Fore.YELLOW}▶ Resuming manager processes...{Style.RESET_ALL}")
                            for proc in manager_processes:
                                try:
                                    proc.resume()
                                    print(f"{Fore.GREEN}✓ Resumed kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                                except psutil.NoSuchProcess:
                                    pass
                                except Exception:
                                    pass
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes resumed"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()
                    else:
                        print(f"{Fore.RED}✗ Invalid profile number!{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                except ValueError:
                    print(f"{Fore.RED}✗ Invalid format! Use C<number> (e.g., C1){Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                continue

            if choice.lower().startswith("r") and len(choice) > 1:
                try:
                    profile_num = int(choice[1:])
                    if 1 <= profile_num <= len(profiles_info):
                        selected_profile = profiles_info[profile_num - 1]
                        print(f"{Fore.CYAN}🔄 Refreshing shift for {selected_profile['name']}...{Style.RESET_ALL}")

                        config_path = os.path.join(selected_profile['path'], "config.json")
                        if not os.path.exists(config_path):
                            print(f"{Fore.RED}✗ config.json not found!{Style.RESET_ALL}")
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
                            print(f"{Fore.RED}✗ Error reading config.json: {e}{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            continue

                        url = f"http://{host}:{port}/api/v1/shift/refresh"
                        try:
                            response = requests.post(url, timeout=5)
                            response.raise_for_status()
                            print(f"{Fore.GREEN}✓ Shift refreshed successfully!{Style.RESET_ALL}")
                        except requests.RequestException as e:
                            print(f"{Fore.RED}✗ Failed to refresh shift: {e}{Style.RESET_ALL}")

                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Shift refreshed"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()
                    else:
                        print(f"{Fore.RED}✗ Invalid profile number!{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                except ValueError:
                    print(f"{Fore.RED}✗ Invalid format! Use R<number> (e.g., R1){Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                continue

            try:
                choice_int = int(choice)
                if 1 <= choice_int <= len(profiles_info):
                    selected_profile = profiles_info[choice_int - 1]
                    print(f"{Fore.CYAN}Launching profile {selected_profile['name']}...{Style.RESET_ALL}")

                    kasa_process = find_process_by_path("checkbox_kasa.exe", selected_profile['path'])
                    if kasa_process:
                        try:
                            kasa_process.kill()
                            print(f"{Fore.GREEN}✓ Stopped checkbox_kasa.exe (PID: {kasa_process.pid}){Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process stopped"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()
                        except psutil.NoSuchProcess:
                            pass
                        except Exception as e:
                            print(f"{Fore.RED}✗ Failed to stop process: {e}{Style.RESET_ALL}")

                    manager_processes = find_all_processes_by_name("kasa_manager.exe")
                    if manager_processes:
                        print(f"{Fore.YELLOW}⏸ Suspending manager processes...{Style.RESET_ALL}")
                        for proc in manager_processes:
                            try:
                                proc.suspend()
                                print(f"{Fore.GREEN}✓ Suspended kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                pass
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes suspended"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()

                    kasa_path = os.path.join(selected_profile['path'], "checkbox_kasa.exe")
                    if os.path.exists(kasa_path):
                        try:
                            print(f"{Fore.CYAN}🚀 Launching cash register...{Style.RESET_ALL}")
                            cmd = f'start cmd /K "{kasa_path}"'
                            subprocess.Popen(cmd, cwd=selected_profile['path'], shell=True)
                            print(f"{Fore.GREEN}✓ Cash register launched successfully!{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Cash register launched"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                        except Exception as e:
                            print(f"{Fore.RED}✗ Failed to launch cash register: {e}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.YELLOW}⚠ checkbox_kasa.exe not found{Style.RESET_ALL}")

                    if manager_processes:
                        print(f"{Fore.YELLOW}▶ Resuming manager processes...{Style.RESET_ALL}")
                        for proc in manager_processes:
                            try:
                                proc.resume()
                                print(f"{Fore.GREEN}✓ Resumed kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                pass
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes resumed"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()
                else:
                    print(f"{Fore.RED}✗ Invalid choice!{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
            except ValueError:
                print(f"{Fore.RED}✗ Invalid input!{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()

        except Exception as e:
            print(f"{Fore.RED}✗ Unexpected error: {e}{Style.RESET_ALL}")
            if 'stop_event' in locals():
                stop_event.set()
                spinner_thread.join()
            input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
            return