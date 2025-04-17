import json
import os
import subprocess
import requests
from typing import Dict

import psutil
from colorama import Fore, Style, init
from config import DRIVES
from utils import (
    run_spinner, find_process_by_path, find_all_processes_by_name,
    launch_executable, manage_process_lifecycle, read_json_file, write_json_file
)
from cleanup import cleanup
from search_utils import (
    find_manager_by_exe, find_cash_registers_by_profiles_json,
    find_cash_registers_by_exe, get_cash_register_info, reset_cache
)

init(autoreset=True)

def check_cash_profiles(data: Dict):
    cache_valid = False
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
        print(f"{Fore.CYAN} CASH REGISTER HEALTH CHECK ".center(50) + f"{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}\n")

        profiles_info = []
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

        run_spinner("Searching cash registers", 1.0)

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
            run_spinner("Cleaning up", 1.0)
            cleanup(data)
            return

        if choice == "0":
            print(f"{Fore.GREEN}✓ Returning to main menu...{Style.RESET_ALL}")
            cache_valid = True
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
                        run_spinner("Folder opened", 1.0)
                    else:
                        print(f"{Fore.RED}✗ Folder not found: {folder_path}{Style.RESET_ALL}")
                        run_spinner("Folder not found", 2.0)
                    cache_valid = True
                else:
                    print(f"{Fore.RED}✗ Invalid profile number!{Style.RESET_ALL}")
                    run_spinner("Invalid choice", 2.0)
            except ValueError:
                print(f"{Fore.RED}✗ Invalid format! Use O<number> (e.g., O1){Style.RESET_ALL}")
                run_spinner("Invalid input", 2.0)
            continue

        if choice.lower().startswith("c") and len(choice) > 1:
            try:
                profile_num = int(choice[1:])
                if 1 <= profile_num <= len(profiles_info):
                    selected_profile = profiles_info[profile_num - 1]
                    print(f"{Fore.CYAN}Updating config for {selected_profile['name']}...{Style.RESET_ALL}")

                    license_key = input(f"{Fore.CYAN}Enter license_key (or press Enter to skip): {Style.RESET_ALL}").strip()
                    pin_code = input(f"{Fore.CYAN}Enter pin-code (or press Enter to skip): {Style.RESET_ALL}").strip()

                    if not manage_process_lifecycle(["checkbox_kasa.exe"], [selected_profile['path']],
                                                  action="terminate", prompt=True,
                                                  spinner_message="Process stopped", spinner_duration=1.0):
                        continue

                    if not manage_process_lifecycle(["kasa_manager.exe"], [selected_profile['path']],
                                                  action="suspend", prompt=False,
                                                  spinner_message="Processes suspended", spinner_duration=1.0):
                        print(f"{Fore.RED}✗ Failed to suspend manager processes{Style.RESET_ALL}")
                        run_spinner("Suspend failed", 2.0)
                        continue

                    config_path = os.path.normpath(os.path.join(selected_profile['path'], "config.json"))
                    config = read_json_file(config_path)
                    if not config:
                        manage_process_lifecycle(["kasa_manager.exe"], [selected_profile['path']],
                                               action="resume", prompt=False,
                                               spinner_message="Processes resumed", spinner_duration=1.0)
                        run_spinner("Config error", 2.0)
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
                        if write_json_file(config_path, config):
                            print(f"{Fore.GREEN}✓ Config updated successfully!{Style.RESET_ALL}")
                            run_spinner("Config updated", 5.0)
                        else:
                            print(f"{Fore.RED}✗ Error writing config.json{Style.RESET_ALL}")
                            run_spinner("Config error", 2.0)
                    else:
                        print(f"{Fore.YELLOW}⚠ No changes made (empty inputs){Style.RESET_ALL}")
                        run_spinner("No changes", 2.0)

                    if launch_executable("checkbox_kasa.exe", selected_profile['path'], "Cash register"):
                        reset_cache()
                        cache_valid = False

                    manage_process_lifecycle(["kasa_manager.exe"], [selected_profile['path']],
                                           action="resume", prompt=False,
                                           spinner_message="Processes resumed", spinner_duration=1.0)
                else:
                    print(f"{Fore.RED}✗ Invalid profile number!{Style.RESET_ALL}")
                    run_spinner("Invalid choice", 2.0)
            except ValueError:
                print(f"{Fore.RED}✗ Invalid format! Use C<number> (e.g., C1){Style.RESET_ALL}")
                run_spinner("Invalid input", 2.0)
            continue

        if choice.lower().startswith("r") and len(choice) > 1:
            try:
                profile_num = int(choice[1:])
                if 1 <= profile_num <= len(profiles_info):
                    selected_profile = profiles_info[profile_num - 1]
                    print(f"{Fore.CYAN}🔄 Refreshing shift for {selected_profile['name']}...{Style.RESET_ALL}")

                    config_path = os.path.normpath(os.path.join(selected_profile['path'], "config.json"))
                    config = read_json_file(config_path)
                    if not config:
                        run_spinner("Config error", 2.0)
                        continue

                    web_server = config.get("web_server", {})
                    host = web_server.get("host", "127.0.0.1")
                    port = web_server.get("port", 9200)
                    url = f"http://{host}:{port}/api/v1/shift/refresh"

                    try:
                        response = requests.post(url, timeout=5)
                        response.raise_for_status()
                        print(f"{Fore.GREEN}✓ Shift refreshed successfully!{Style.RESET_ALL}")
                        reset_cache()
                        cache_valid = False
                        run_spinner("Shift refreshed", 1.0)
                    except requests.RequestException as e:
                        print(f"{Fore.RED}✗ Failed to refresh shift: {e}{Style.RESET_ALL}")
                        run_spinner("Shift refresh failed", 2.0)
                else:
                    print(f"{Fore.RED}✗ Invalid profile number!{Style.RESET_ALL}")
                    run_spinner("Invalid choice", 2.0)
            except ValueError:
                print(f"{Fore.RED}✗ Invalid format! Use R<number> (e.g., R1){Style.RESET_ALL}")
                run_spinner("Invalid input", 2.0)
            continue

        try:
            choice_int = int(choice)
            if 1 <= choice_int <= len(profiles_info):
                selected_profile = profiles_info[choice_int - 1]
                print(f"{Fore.CYAN}Launching profile {selected_profile['name']}...{Style.RESET_ALL}")

                if not manage_process_lifecycle(["checkbox_kasa.exe"], [selected_profile['path']],
                                              action="terminate", prompt=True,
                                              spinner_message="Process stopped", spinner_duration=1.0):
                    continue

                if not manage_process_lifecycle(["kasa_manager.exe"], [selected_profile['path']],
                                              action="suspend", prompt=False,
                                              spinner_message="Processes suspended", spinner_duration=1.0):
                    print(f"{Fore.RED}✗ Failed to suspend manager processes{Style.RESET_ALL}")
                    run_spinner("Suspend failed", 2.0)
                    continue

                if launch_executable("checkbox_kasa.exe", selected_profile['path'], "Cash register"):
                    reset_cache()
                    cache_valid = False

                manage_process_lifecycle(["kasa_manager.exe"], [selected_profile['path']],
                                       action="resume", prompt=False,
                                       spinner_message="Processes resumed", spinner_duration=1.0)
            else:
                print(f"{Fore.RED}✗ Invalid choice!{Style.RESET_ALL}")
                run_spinner("Invalid choice", 2.0)
        except ValueError:
            print(f"{Fore.RED}✗ Invalid input!{Style.RESET_ALL}")
            run_spinner("Invalid input", 2.0)
        except Exception as e:
            print(f"{Fore.RED}✗ Unexpected error: {e}{Style.RESET_ALL}")
            run_spinner("Error occurred", 2.0)
            input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
            return

if __name__ == "__main__":
    data = {}
    check_cash_profiles(data)