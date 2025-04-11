# -*- coding: utf-8 -*-
import logging
import os
import sys
import subprocess
import time
import threading
from typing import Dict

import psutil
from tqdm import tqdm
from colorama import Fore, Style

from utils import find_all_processes_by_name, show_spinner

logger = logging.getLogger(__name__)

def cleanup(data: Dict, api_handler):  # Добавляем api_handler как аргумент
    logger.info("Starting cleanup (user-initiated)")
    print(f"{Fore.CYAN}Cleaning up...{Style.RESET_ALL}")
    files_to_delete = []

    try:
        for category in ["legacy", "dev", "tools"]:
            if category in data:
                logger.info(f"Processing category: {category}")
                for key, item in data[category].items():
                    if isinstance(item, list):
                        for sub_item in item:
                            files_to_delete.extend([sub_item.get("name", ""), sub_item.get("patch_name", "")])
                            logger.debug(
                                f"Added file from {category}/{key}: {sub_item.get('name', '')}, {sub_item.get('patch_name', '')}")
                    elif isinstance(item, dict):
                        for sub_key, sub_item in item.items():
                            if isinstance(sub_item, list):
                                for sub_sub_item in sub_item:
                                    files_to_delete.extend(
                                        [sub_sub_item.get("name", ""), sub_sub_item.get("patch_name", "")])
                                    logger.debug(
                                        f"Added file from {category}/{key}/{sub_key}: {sub_sub_item.get('name', '')}, {sub_sub_item.get('patch_name', '')}")
                            else:
                                files_to_delete.extend([sub_item.get("name", ""), sub_item.get("patch_name", "")])
                                logger.debug(
                                    f"Added file from {category}/{key}/{sub_key}: {sub_item.get('name', '')}, {sub_item.get('patch_name', '')}")

        files_to_delete = [f for f in files_to_delete if f and isinstance(f, str)]
        logger.info(f"Files to delete: {files_to_delete}")

        print(f"{Fore.YELLOW}Checking and terminating related processes...{Style.RESET_ALL}")
        for file in files_to_delete:
            process_name = os.path.splitext(os.path.basename(file))[0] + ".exe"
            processes = find_all_processes_by_name(process_name)
            if processes:
                for proc in processes:
                    try:
                        proc.kill()
                        logger.info(f"Killed process {process_name} (PID: {proc.pid})")
                        print(f"{Fore.GREEN}Terminated {process_name} (PID: {proc.pid}){Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process terminated"))
                        spinner_thread.start()
                        time.sleep(0.5)
                        stop_event.set()
                        spinner_thread.join()
                    except psutil.NoSuchProcess:
                        logger.warning(f"Process {process_name} (PID: {proc.pid}) already terminated")
                    except psutil.AccessDenied:
                        logger.error(f"Access denied to kill {process_name} (PID: {proc.pid})")
                        print(
                            f"{Fore.RED}Access denied to terminate {process_name} (PID: {proc.pid}) - run as admin{Style.RESET_ALL}")
                    except Exception as e:
                        logger.error(f"Failed to kill {process_name} (PID: {proc.pid}): {e}")
                        print(f"{Fore.RED}Failed to terminate {process_name} (PID: {proc.pid}): {e}{Style.RESET_ALL}")

        with tqdm(total=len(files_to_delete), desc="Removing files",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
            for file in files_to_delete:
                if os.path.exists(file):
                    try:
                        os.remove(file)
                        logger.info(f"Deleted {file}")
                        print(f"{Fore.GREEN}Deleted {file}{Style.RESET_ALL}")
                    except PermissionError:
                        logger.error(f"Permission denied to delete {file} - file may be in use")
                        print(
                            f"{Fore.RED}Failed to delete {file}: file in use or insufficient permissions{Style.RESET_ALL}")
                    except Exception as e:
                        logger.error(f"Failed to delete {file}: {e}")
                        print(f"{Fore.RED}Failed to delete {file}: {e}{Style.RESET_ALL}")
                    pbar.update(1)
                else:
                    logger.debug(f"File {file} does not exist, skipping")
                    pbar.update(1)

        if api_handler:  # Используем переданный api_handler
            logger.info("Flushing remaining logs before cleanup exit")
            api_handler.flush()

        # Ждём завершения всех потоков
        for thread in threading.enumerate():
            if thread is not threading.current_thread() and thread.is_alive():
                logger.info(f"Waiting for thread {thread.name} to finish")
                thread.join(timeout=2.0)

        logger.info("Scheduling script self-deletion via batch file")
        print(f"{Fore.GREEN}Cleanup completed! Scheduling self-deletion...{Style.RESET_ALL}")

        exe_path = os.path.abspath(sys.argv[0])
        if getattr(sys, 'frozen', False):
            exe_path = os.path.abspath(sys.executable)
            logger.info(f"Running as frozen executable, adjusted exe_path: {exe_path}")
        else:
            logger.info(f"Running as script, exe_path: {exe_path}")

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
        logger.error(f"Unexpected error in cleanup: {e}")
        print(f"{Fore.RED}Unexpected error during cleanup: {e}{Style.RESET_ALL}")

    sys.exit(0)