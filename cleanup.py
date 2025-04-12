# -*- coding: utf-8 -*-
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
            if category in data:
                for key, item in data[category].items():
                    if isinstance(item, list):
                        for sub_item in item:
                            files_to_delete.extend([sub_item.get("name", ""), sub_item.get("patch_name", "")])
                    elif isinstance(item, dict):
                        for sub_key, sub_item in item.items():
                            if isinstance(sub_item, list):
                                for sub_sub_item in sub_item:
                                    files_to_delete.extend(
                                        [sub_sub_item.get("name", ""), sub_sub_item.get("patch_name", "")])
                            else:
                                files_to_delete.extend([sub_item.get("name", ""), sub_item.get("patch_name", "")])

        files_to_delete = [f for f in files_to_delete if f and isinstance(f, str)]

        print(f"{Fore.YELLOW}🔒 Checking running processes...{Style.RESET_ALL}")
        for file in files_to_delete:
            process_name = os.path.splitext(os.path.basename(file))[0] + ".exe"
            processes = find_all_processes_by_name(process_name)
            if processes:
                for proc in processes:
                    try:
                        proc.kill()
                        print(f"{Fore.GREEN}✓ Stopped {process_name} (PID: {proc.pid}).{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process stopped"))
                        spinner_thread.start()
                        time.sleep(0.5)
                        stop_event.set()
                        spinner_thread.join()
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.AccessDenied:
                        print(f"{Fore.RED}✗ Access denied for {process_name}. Please run as admin.{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"{Fore.RED}✗ Failed to stop {process_name}: {e}{Style.RESET_ALL}")

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

        print(f"{Fore.GREEN}✓ Cleanup completed! Preparing to exit...{Style.RESET_ALL}")

        exe_path = os.path.abspath(sys.argv[0])
        if getattr(sys, 'frozen', False):
            exe_path = os.path.abspath(sys.executable)

        bat_path = os.path.join(os.path.dirname(exe_path), "delete_me.bat")
        with open(bat_path, "w", encoding="utf-8") as bat_file:
            bat_file.write(f"@echo off\n")
            bat_file.write(f":repeat\n")
            bat_file.write(f"ping 127.0.0.1 -n 3 >nul\n")
            bat_file.write(f"del /f /q \"{exe_path}\"\n")
            bat_file.write(f"if exist \"{exe_path}\" goto repeat\n")
            bat_file.write(f"del /f /q \"{bat_path}\"\n")
        subprocess.Popen(f"cmd /c \"{bat_path}\"", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        print(f"{Fore.RED}✗ Cleanup error: {e}{Style.RESET_ALL}")

    sys.exit(0)