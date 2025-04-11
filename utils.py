# -*- coding: utf-8 -*-
import ctypes
import logging
import os
import time
import threading
import itertools
import sys
from typing import List, Optional

import psutil
from colorama import Fore, Style

logger = logging.getLogger(__name__)

def show_spinner(stop_event: threading.Event, message: str = "Processing") -> None:
    spinner = itertools.cycle(['-', '/', '|', '\\'])
    while not stop_event.is_set():
        sys.stdout.write(f"\r{Fore.CYAN}{message} {next(spinner)}{Style.RESET_ALL}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write(f"\r{Fore.GREEN}{message} Done!{Style.RESET_ALL}\n")
    sys.stdout.flush()

def is_admin() -> bool:
    logger.info("Checking admin privileges")
    try:
        result = ctypes.windll.shell32.IsUserAnAdmin() != 0
        logger.info(f"Admin privileges: {result}")
        return result
    except Exception as e:
        logger.error(f"Error checking admin privileges: {e}")
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
    except Exception as e:
        logger.error(f"Error in find_process_by_path: {e}")
        return None

def find_all_processes_by_name(process_name: str) -> List[psutil.Process]:
    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'].lower() == process_name.lower():
                processes.append(proc)
        return processes
    except Exception as e:
        logger.error(f"Error in find_all_processes_by_name: {e}")
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
                                logger.info(f"Prevented {proc_name} from starting (PID: {process.pid})")
                                print(f"{Fore.YELLOW}Detected and killed {proc_name} launch attempt.{Style.RESET_ALL}")
                            except psutil.NoSuchProcess:
                                pass
                            except Exception as e:
                                logger.error(f"Failed to kill process {proc_name}: {e}")
                time.sleep(0.1)
        else:
            kill_all = False
            for target_dir in target_dirs:
                for proc_name in processes_to_kill:
                    process = find_process_by_path(proc_name, target_dir)
                    if process and not kill_all:
                        print(f"{Fore.RED}Warning: {proc_name} is running from {target_dir}!{Style.RESET_ALL}")
                        print("To proceed with patching, this process must be closed.")
                        choice = input("Close all detected processes? (Y/N): ").strip().lower()
                        if choice == "y":
                            kill_all = True
                            try:
                                process.kill()
                                logger.info(f"Killed {proc_name} (PID: {process.pid})")
                                print(f"{Style.RESET_ALL}{Fore.GREEN}Process {proc_name} closed.{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Closing process"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            except psutil.NoSuchProcess:
                                logger.warning(f"{proc_name} already terminated")
                            except Exception as e:
                                logger.error(f"Failed to kill {proc_name}: {e}")
                        else:
                            print(f"{Fore.RED}Patching aborted by user.{Style.RESET_ALL}")
                            return False
                    elif process and kill_all:
                        try:
                            process.kill()
                            logger.info(f"Killed {proc_name} (PID: {process.pid})")
                            print(f"{Style.RESET_ALL}{Fore.GREEN}Process {proc_name} closed.{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Closing process"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()
                        except psutil.NoSuchProcess:
                            logger.warning(f"{proc_name} already terminated")
                        except Exception as e:
                            logger.error(f"Failed to kill {proc_name}: {e}")
        return True
    except Exception as e:
        logger.error(f"Unexpected error in manage_processes: {e}")
        return False