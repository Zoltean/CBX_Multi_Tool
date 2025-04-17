import os
import subprocess
import sys
import time
import threading
from typing import Dict

import psutil
from tqdm import tqdm
from colorama import Fore, Style

from utils import find_all_processes_by_name, show_spinner


def cleanup(data: Dict):
    print(f"{Fore.CYAN}🧹 Starting cleanup...{Style.RESET_ALL}")
    files_to_delete = []

    try:
        for category in ["legacy", "dev", "tools"]:
            if category not in data:
                continue
            category_data = data[category]
            if not isinstance(category_data, dict):
                print(f"{Fore.YELLOW}⚠ Skipping invalid category data for {category}: not a dictionary{Style.RESET_ALL}")
                continue

            for key, item in category_data.items():
                if isinstance(item, list):
                    for sub_item in item:
                        if isinstance(sub_item, dict):
                            files_to_delete.extend([sub_item.get("name", ""), sub_item.get("patch_name", "")])
                        else:
                            print(f"{Fore.YELLOW}⚠ Skipping invalid sub-item in {category}/{key}: not a dictionary{Style.RESET_ALL}")
                elif isinstance(item, dict):
                    for sub_key, sub_item in item.items():
                        if isinstance(sub_item, list):
                            for sub_sub_item in sub_item:
                                if isinstance(sub_sub_item, dict):
                                    files_to_delete.extend([sub_sub_item.get("name", ""), sub_sub_item.get("patch_name", "")])
                                else:
                                    print(f"{Fore.YELLOW}⚠ Skipping invalid sub-sub-item in {category}/{key}/{sub_key}: not a dictionary{Style.RESET_ALL}")
                        elif isinstance(sub_item, dict):
                            files_to_delete.extend([sub_item.get("name", ""), sub_item.get("patch_name", "")])
                        else:
                            print(f"{Fore.YELLOW}⚠ Skipping invalid sub-item in {category}/{key}/{sub_key}: not a dictionary{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}⚠ Skipping invalid item in {category}/{key}: not a dictionary or list{Style.RESET_ALL}")

        files_to_delete = [f for f in files_to_delete if f and isinstance(f, str)]

        print(f"{Fore.YELLOW}🔒 Checking running processes...{Style.RESET_ALL}")
        for file in files_to_delete:
            process_name = os.path.splitext(os.path.basename(file))[0] + ".exe"
            processes = find_all_processes_by_name(process_name)
            if processes:
                print(f"{Fore.RED}⚠ Found running processes for {process_name}:{Style.RESET_ALL}")
                for proc in processes:
                    print(f" - PID: {proc.pid}")
                choice = input(f"{Fore.CYAN}Close these processes to proceed? (Y/N): {Style.RESET_ALL}").strip().lower()
                if choice != "y":
                    print(f"{Fore.RED}✗ Process termination cancelled. Some files may not be deleted.{Style.RESET_ALL}")
                    continue

                for proc in processes:
                    confirm = input(f"{Fore.CYAN}Terminate {process_name} (PID: {proc.pid})? (Y/N): {Style.RESET_ALL}").strip().lower()
                    if confirm == "y":
                        try:
                            proc.terminate()
                            proc.wait(timeout=5)
                            print(f"{Fore.GREEN}✓ Terminated {process_name} (PID: {proc.pid}).{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process terminated"))
                            spinner_thread.start()
                            time.sleep(0.5)
                            stop_event.set()
                            spinner_thread.join()
                        except psutil.TimeoutExpired:
                            print(f"{Fore.YELLOW}⚠ Process {process_name} did not terminate gracefully. Forcing...{Style.RESET_ALL}")
                            proc.terminate()
                            print(f"{Fore.GREEN}✓ Force terminated {process_name} (PID: {proc.pid}).{Style.RESET_ALL}")
                        except psutil.NoSuchProcess:
                            pass
                        except psutil.AccessDenied:
                            print(f"{Fore.RED}✗ Access denied for {process_name}. Please run as admin.{Style.RESET_ALL}")
                        except Exception as e:
                            print(f"{Fore.RED}✗ Failed to terminate {process_name}: {e}{Style.RESET_ALL}")

        with tqdm(total=len(files_to_delete), desc="Cleaning files",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
            for file in files_to_delete:
                if os.path.exists(file):
                    try:
                        os.remove(file)
                        print(f"{Fore.GREEN}✓ Removed {file}{Style.RESET_ALL}")
                    except PermissionError:
                        print(f"{Fore.RED}✗ Cannot remove {file}: file in use or access denied.{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"{Fore.RED}✗ Failed to remove {file}: {e}{Style.RESET_ALL}")
                    pbar.update(1)
                else:
                    pbar.update(1)

        for thread in threading.enumerate():
            if thread is not threading.current_thread() and thread.is_alive():
                thread.join(timeout=0.1)

        print(f"{Fore.GREEN}✓ Cleanup completed!{Style.RESET_ALL}")

    except Exception as e:
        print(f"{Fore.RED}✗ Cleanup error: {e}{Style.RESET_ALL}")

    sys.exit(0)