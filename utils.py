# -*- coding: utf-8 -*-
import ctypes
import os
import time
import threading
import itertools
import sys
from typing import List, Optional

import psutil
from colorama import Fore, Style

def show_spinner(stop_event: threading.Event, message: str = "Processing") -> None:
    spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
    while not stop_event.is_set():
        sys.stdout.write(f"\r{Fore.CYAN}{message} {next(spinner)}{Style.RESET_ALL}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write(f"\r{Fore.GREEN}✓ {message} completed!{Style.RESET_ALL}\n")
    sys.stdout.flush()

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def find_process_by_path(process_name: str, target_path: str) -> Optional[psutil.Process]:
    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            if proc.info['name'].lower() == process_name.lower():
                try:
                    if os.path.realpath(proc.info['exe']).startswith(os.path.realpath(target_path)):
                        return proc
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        return None
    except Exception:
        return None

def find_all_processes_by_name(process_name: str) -> List[psutil.Process]:
    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'].lower() == process_name.lower():
                processes.append(proc)
        return processes
    except Exception:
        return processes

def manage_processes(processes_to_kill: List[str], target_dirs: List[str],
                    stop_event: Optional[threading.Event] = None) -> bool:
    try:
        if stop_event:
            while not stop_event.is_set():
                for target_dir in target_dirs:
                    for proc_name in processes_to_kill:
                        process = find_process_by_path(proc_name, target_dir)
                        if process:
                            try:
                                process.kill()
                                print(f"{Fore.YELLOW}⚠ Stopped {proc_name} (PID: {process.pid}).{Style.RESET_ALL}")
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                print(f"{Fore.RED}✗ Failed to stop {proc_name}.{Style.RESET_ALL}")
                time.sleep(0.1)
        else:
            kill_all = False
            for target_dir in target_dirs:
                for proc_name in processes_to_kill:
                    process = find_process_by_path(proc_name, target_dir)
                    if process and not kill_all:
                        print(f"{Fore.RED}⚠ {proc_name} is running in {target_dir}!{Style.RESET_ALL}")
                        choice = input(f"{Fore.CYAN}Close all detected processes? (Y/N): {Style.RESET_ALL}").strip().lower()
                        if choice == "y":
                            kill_all = True
                            try:
                                process.kill()
                                print(f"{Fore.GREEN}✓ Closed {proc_name}.{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Closing process"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                print(f"{Fore.RED}✗ Failed to close {proc_name}.{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.RED}✗ Operation cancelled.{Style.RESET_ALL}")
                            return False
                    elif process and kill_all:
                        try:
                            process.kill()
                            print(f"{Fore.GREEN}✓ Closed {proc_name}.{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Closing process"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()
                        except psutil.NoSuchProcess:
                            pass
                        except Exception:
                            print(f"{Fore.RED}✗ Failed to close {proc_name}.{Style.RESET_ALL}")
        return True
    except Exception:
        print(f"{Fore.RED}✗ Error managing processes.{Style.RESET_ALL}")
        return False