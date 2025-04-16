# -*- coding: utf-8 -*-
import json
import os
import subprocess
import time
import threading
from typing import Dict, List

import psutil
import requests
from colorama import Fore, Style, init
from config import DRIVES
from utils import show_spinner, find_process_by_path, find_all_processes_by_name
from cleanup import cleanup
from search_utils import find_manager_by_exe, find_cash_registers_by_profiles_json, find_cash_registers_by_exe, get_cash_register_info, reset_cache

# Инициализация colorama
init(autoreset=True)

def terminate_process_with_confirmation(proc: psutil.Process, process_name: str) -> bool:
    confirm = input(f"{Fore.CYAN}Terminate {process_name} (PID: {proc.pid})? (Y/N): {Style.RESET_ALL}").strip().lower()
    if confirm == "y":
        try:
            proc.terminate()
            proc.wait(timeout=5)
            print(f"{Fore.GREEN}✓ Stopped {process_name} (PID: {proc.pid}){Style.RESET_ALL}")
            return True
        except psutil.TimeoutExpired:
            proc.terminate()
            print(f"{Fore.GREEN}✓ Force stopped {process_name} (PID: {proc.pid}){Style.RESET_ALL}")
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print(f"{Fore.RED}✗ Failed to stop {process_name} (PID: {proc.pid}){Style.RESET_ALL}")
            return False
    return False

def check_cash_profiles(data: Dict):
    cache_valid = False
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
        print(f"{Fore.CYAN} CASH REGISTER HEALTH CHECK ".center(50) + f"{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}\n")

        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Searching cash registers"))
        spinner_thread.start()

        try:
            profiles_info = []
            manager_dir = None
            seen_paths = set()
            profile_paths = set()

            manager_dir = find_manager_by_exe(DRIVES, use_cache=cache_valid)
            if not manager_dir:
                print(f"{Fore.RED}✗ Manager directory or kasa_manager.exe not found!{Style.RESET_ALL}")

            if manager_dir:
                profile_cashes, is_empty, profile_seen_paths = find_cash_registers_by_profiles_json(manager_dir, use_cache=cache_valid)
                if is_empty:
                    print(f"{Fore.RED}! ! ! PROFILES.JSON IS EMPTY ! ! !{Style.RESET_ALL}")
                for cash in profile_cashes:
                    normalized_path = os.path.normpath(os.path.abspath(cash["path"]))
                    if normalized_path not in seen_paths:
                        profiles_info.append(get_cash_register_info(cash["path"], is_external=False))
                        seen_paths.add(normalized_path)
                        profile_paths.add(normalized_path)

            cash_registers = find_cash_registers_by_exe(manager_dir, DRIVES, use_cache=cache_valid)
            for cash in cash_registers:
                normalized_path = os.path.normpath(os.path.abspath(cash["path"]))
                if normalized_path not in seen_paths:
                    is_external = normalized_path not in profile_paths
                    profiles_info.append(get_cash_register_info(cash["path"], is_external=is_external))
                    seen_paths.add(normalized_path)

            stop_event.set()
            spinner_thread.join()

            if not profiles_info:
                print(f"{Fore.RED}✗ No cash registers found!{Style.RESET_ALL}")
                input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
                return

            print(f"{Fore.CYAN}Found {len(profiles_info)} cash registers:{Style.RESET_ALL}\n")
            for i, profile in enumerate(profiles_info, 1):
                health_color = Fore.GREEN if profile["health"] == "OK" else Fore.RED
                trans_color = Fore.GREEN if profile["trans_status"] in ["DONE", "EMPTY"] else Fore.RED
                shift_color = Fore.GREEN if profile["shift_status"] == "CLOSED" else Fore.RED
                status_text = "ON" if profile["is_running"] else "OFF"
                status_color = Fore.GREEN if profile["is_running"] else Fore.RED
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
                cache_valid = True
                stop_event.set()
                spinner_thread.join()
                return

            if choice.lower().startswith("o") and len(choice) > 1:
                try:
                    profile_num = int(choice[1:])
                    if 1 <= profile_num <= len(profiles_info):
                        selected_profile = profiles_info[profile_num - 1]
                        folder_path = os.path.normpath(os.path.abspath(selected_profile['path']))
                        if os.path.exists(folder_path):
                            os.startfile(folder_path)
                            print(f"{Fore.GREEN}✓ Opened folder {folder_path}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.RED}✗ Folder not found: {folder_path}{Style.RESET_ALL}")
                        cache_valid = True
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
                            if not terminate_process_with_confirmation(kasa_process, "checkbox_kasa.exe"):
                                continue
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process stopped"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()

                        if manager_processes:
                            print(f"{Fore.YELLOW}⏸ Suspending manager processes...{Style.RESET_ALL}")
                            for proc in manager_processes:
                                try:
                                    proc.suspend()
                                    print(f"{Fore.GREEN}✓ Suspended kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                                    manager_suspended = True
                                except psutil.NoSuchProcess:
                                    pass
                                except Exception as e:
                                    print(f"{Fore.RED}✗ Failed to suspend process {proc.pid}: {e}{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes suspended"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()

                        config_path = os.path.normpath(os.path.join(selected_profile['path'], "config.json"))
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
                                    except Exception as e:
                                        print(f"{Fore.RED}✗ Failed to resume process {proc.pid}: {e}{Style.RESET_ALL}")
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
                        except json.JSONDecodeError as e:
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
                                    except Exception as e:
                                        print(f"{Fore.RED}✗ Failed to resume process {proc.pid}: {e}{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes resumed"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            continue
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
                                    except Exception as e:
                                        print(f"{Fore.RED}✗ Failed to resume process {proc.pid}: {e}{Style.RESET_ALL}")
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
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config updated"))
                            spinner_thread.start()
                            time.sleep(5)
                            stop_event.set()
                            spinner_thread.join()
                        else:
                            print(f"{Fore.YELLOW}⚠ No changes made (empty inputs){Style.RESET_ALL}")

                        kasa_path = os.path.normpath(os.path.join(selected_profile['path'], "checkbox_kasa.exe"))
                        if os.path.exists(kasa_path):
                            try:
                                print(f"{Fore.CYAN}🚀 Launching cash register...{Style.RESET_ALL}")
                                cmd = f'cmd /c start cmd /k ""{kasa_path}""'
                                subprocess.Popen(cmd, cwd=os.path.normpath(os.path.abspath(selected_profile['path'])), shell=True)
                                print(f"{Fore.GREEN}✓ Cash register launched successfully!{Style.RESET_ALL}")
                                reset_cache()
                                cache_valid = False
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
                                except Exception as e:
                                    print(f"{Fore.RED}✗ Failed to resume process {proc.pid}: {e}{Style.RESET_ALL}")
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

                        config_path = os.path.normpath(os.path.join(selected_profile['path'], "config.json"))
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
                        except json.JSONDecodeError as e:
                            print(f"{Fore.RED}✗ Error reading config.json: {e}{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Config error"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            continue
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
                            reset_cache()
                            cache_valid = False
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
                        if not terminate_process_with_confirmation(kasa_process, "checkbox_kasa.exe"):
                            continue
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process stopped"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()

                    manager_processes = find_all_processes_by_name("kasa_manager.exe")
                    if manager_processes:
                        print(f"{Fore.YELLOW}⏸ Suspending manager processes...{Style.RESET_ALL}")
                        for proc in manager_processes:
                            try:
                                proc.suspend()
                                print(f"{Fore.GREEN}✓ Suspended kasa_manager.exe (PID: {proc.pid}){Style.RESET_ALL}")
                            except psutil.NoSuchProcess:
                                pass
                            except Exception as e:
                                print(f"{Fore.RED}✗ Failed to suspend process {proc.pid}: {e}{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Processes suspended"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()

                    kasa_path = os.path.normpath(os.path.join(selected_profile['path'], "checkbox_kasa.exe"))
                    if os.path.exists(kasa_path):
                        try:
                            print(f"{Fore.CYAN}🚀 Launching cash register...{Style.RESET_ALL}")
                            cmd = f'cmd /c start cmd /k ""{kasa_path}""'
                            subprocess.Popen(cmd, cwd=os.path.normpath(os.path.abspath(selected_profile['path'])), shell=True)
                            print(f"{Fore.GREEN}✓ Cash register launched successfully!{Style.RESET_ALL}")
                            reset_cache()
                            cache_valid = False
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
                            except Exception as e:
                                print(f"{Fore.RED}✗ Failed to resume process {proc.pid}: {e}{Style.RESET_ALL}")
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

if __name__ == "__main__":
    data = {}
    check_cash_profiles(data)