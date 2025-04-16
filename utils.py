# -*- coding: utf-8 -*-
import ctypes
import os
import time
import threading
import itertools
import sys
import subprocess
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
                            confirm = input(
                                f"{Fore.CYAN}Terminate {proc_name} (PID: {process.pid})? (Y/N): {Style.RESET_ALL}").strip().lower()
                            if confirm == "y":
                                try:
                                    process.terminate()
                                    print(
                                        f"{Fore.YELLOW}⚠ Terminated {proc_name} (PID: {process.pid}).{Style.RESET_ALL}")
                                except psutil.NoSuchProcess:
                                    pass
                                except Exception:
                                    print(f"{Fore.RED}✗ Failed to terminate {proc_name}.{Style.RESET_ALL}")
                time.sleep(0.1)
        else:
            kill_all = False
            for target_dir in target_dirs:
                for proc_name in processes_to_kill:
                    process = find_process_by_path(proc_name, target_dir)
                    if process and not kill_all:
                        print(f"{Fore.RED}⚠ {proc_name} is running in {target_dir}!{Style.RESET_ALL}")
                        choice = input(
                            f"{Fore.CYAN}Close all detected processes? (Y/N): {Style.RESET_ALL}").strip().lower()
                        if choice == "y":
                            kill_all = True
                            confirm = input(
                                f"{Fore.CYAN}Terminate {proc_name} (PID: {process.pid})? (Y/N): {Style.RESET_ALL}").strip().lower()
                            if confirm == "y":
                                try:
                                    process.terminate()
                                    print(f"{Fore.GREEN}✓ Terminated {proc_name}.{Style.RESET_ALL}")
                                    stop_event = threading.Event()
                                    spinner_thread = threading.Thread(target=show_spinner,
                                                                      args=(stop_event, "Terminating process"))
                                    spinner_thread.start()
                                    time.sleep(1)
                                    stop_event.set()
                                    spinner_thread.join()
                                except psutil.NoSuchProcess:
                                    pass
                                except Exception:
                                    print(f"{Fore.RED}✗ Failed to terminate {proc_name}.{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.RED}✗ Operation cancelled.{Style.RESET_ALL}")
                            return False
                    elif process and kill_all:
                        confirm = input(
                            f"{Fore.CYAN}Terminate {proc_name} (PID: {process.pid})? (Y/N): {Style.RESET_ALL}").strip().lower()
                        if confirm == "y":
                            try:
                                process.terminate()
                                print(f"{Fore.GREEN}✓ Terminated {proc_name}.{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner,
                                                                  args=(stop_event, "Terminating process"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                print(f"{Fore.RED}✗ Failed to terminate {proc_name}.{Style.RESET_ALL}")
        return True
    except Exception:
        print(f"{Fore.RED}✗ Error managing processes.{Style.RESET_ALL}")
        return False


def launch_executable(executable_name: str, target_dir: str, display_name: str, spinner_duration: float = 2.0) -> bool:
    """
    Launch an executable file with appropriate messaging and spinner animation.

    Args:
        executable_name (str): Name of the executable file (e.g., 'checkbox_kasa.exe').
        target_dir (str): Directory where the executable is located.
        display_name (str): Display name for messaging (e.g., 'Cash register', 'Manager').
        spinner_duration (float): Duration of the spinner animation in seconds.

    Returns:
        bool: True if the executable was launched successfully, False otherwise.
    """
    executable_path = os.path.normpath(os.path.join(target_dir, executable_name))
    if os.path.exists(executable_path):
        try:
            print(f"{Fore.CYAN}🚀 Launching {display_name.lower()}...{Style.RESET_ALL}")
            cmd = f'start cmd /K "{executable_path}"'
            subprocess.Popen(cmd, cwd=target_dir, shell=True)
            print(f"{Fore.GREEN}✓ {display_name} launched successfully!{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, f"{display_name} launched"))
            spinner_thread.start()
            time.sleep(spinner_duration)
            stop_event.set()
            spinner_thread.join()
            return True
        except Exception as e:
            print(f"{Fore.RED}✗ Failed to launch {display_name.lower()}: {e}{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner,
                                              args=(stop_event, f"Failed to launch {display_name.lower()}"))
            spinner_thread.start()
            time.sleep(2)
            stop_event.set()
            spinner_thread.join()
            return False
    else:
        print(f"{Fore.YELLOW}⚠ {executable_name} not found.{Style.RESET_ALL}")
        return False