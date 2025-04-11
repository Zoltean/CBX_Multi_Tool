# -*- coding: utf-8 -*-
import os
import subprocess
import time
import zipfile
import shutil
import logging
import threading
from datetime import datetime
from typing import Optional

import psutil
from tqdm import tqdm
from colorama import Fore, Style

from utils import find_process_by_path, find_all_processes_by_name, manage_processes, show_spinner

logger = logging.getLogger(__name__)

def create_backup(target_dir: str) -> Optional[str]:
    logger.info(f"Creating backup for {target_dir}")
    backup_name = f"{os.path.basename(target_dir)}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    backup_path = os.path.join(os.path.dirname(target_dir), backup_name)

    try:
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            total_files = sum(len(files) for _, _, files in os.walk(target_dir))
            with tqdm(total=total_files, desc="Creating backup",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
                for root, _, files in os.walk(target_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, target_dir)
                        zipf.write(file_path, arcname)
                        pbar.update(1)
        logger.info(f"Backup created: {backup_path}")
        print(f"{Fore.GREEN}Backup created: {backup_path}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Backup created"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        print(f"{Fore.RED}Failed to create backup: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Backup failed"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return None

def delete_backup(backup_path: str) -> bool:
    logger.info(f"Deleting backup {backup_path}")
    print(f"{Fore.CYAN}Deleting backup {os.path.basename(backup_path)}...{Style.RESET_ALL}")
    try:
        os.remove(backup_path)
        logger.info(f"Successfully deleted backup: {backup_path}")
        print(f"{Fore.GREEN}Backup {os.path.basename(backup_path)} deleted successfully!{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Backup deleted"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return True
    except Exception as e:
        logger.error(f"Failed to delete backup {backup_path}: {e}")
        print(f"{Fore.RED}Failed to delete backup {os.path.basename(backup_path)}: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Delete failed"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return False

def restore_from_backup(target_dir: str, backup_path: str, is_rro_agent: bool = False,
                        is_paylink: bool = False) -> bool:
    logger.info(f"Restoring from backup {backup_path} to {target_dir}")
    print(f"{Fore.CYAN}Restoring from backup {backup_path}...{Style.RESET_ALL}")

    processes_to_check = ["checkbox_kasa.exe"] if is_rro_agent else (
        ["CheckboxPayLink.exe", "POSServer.exe"] if is_paylink else ["kasa_manager.exe"])

    running_processes = []
    try:
        for proc_name in processes_to_check:
            process = find_process_by_path(proc_name, target_dir)
            if process:
                running_processes.append(process)
    except Exception as e:
        logger.error(f"Error checking running processes: {e}")

    manager_processes = []
    manager_running = False
    cash_running = bool(running_processes)
    if is_rro_agent:
        try:
            manager_processes = find_all_processes_by_name("kasa_manager.exe")
            manager_running = bool(manager_processes)
        except Exception as e:
            logger.error(f"Error finding manager processes: {e}")

    if running_processes:
        print(f"{Fore.RED}Warning: The following processes are running in {target_dir}!{Style.RESET_ALL}")
        for proc in running_processes:
            print(f" - {proc.info['name']} (PID: {proc.pid})")
        print(f"{Fore.RED}To proceed with restoration, these processes must be closed.{Style.RESET_ALL}")
        choice = input(f"Close all detected processes? (Y/N): ").strip().lower()
        logger.info(f"User prompted to kill processes for restore, response: {choice}")
        if choice == "y":
            print(f"{Fore.YELLOW}Stopping all detected processes...{Style.RESET_ALL}")
            for proc in running_processes:
                try:
                    proc.kill()
                    logger.info(f"Killed {proc.info['name']} (PID: {proc.pid})")
                    print(f"{Fore.GREEN}Killed {proc.info['name']} (PID: {proc.pid}).{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process killed"))
                    spinner_thread.start()
                    time.sleep(1)
                    stop_event.set()
                    spinner_thread.join()
                except psutil.NoSuchProcess:
                    logger.warning(f"{proc.info['name']} (PID: {proc.pid}) already terminated")
                except Exception as e:
                    logger.error(f"Failed to kill process {proc.info['name']} (PID: {proc.pid}): {e}")
            time.sleep(1)
        else:
            logger.info("User declined to kill processes, aborting restore")
            print(f"{Fore.RED}Restoration aborted by user.{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Restore aborted"))
            spinner_thread.start()
            time.sleep(2)
            stop_event.set()
            spinner_thread.join()
            return False

        if is_rro_agent and cash_running and manager_running:
            print(f"{Fore.YELLOW}Freezing all manager processes...{Style.RESET_ALL}")
            for proc in manager_processes:
                try:
                    proc.suspend()
                    logger.info(f"Suspended kasa_manager.exe (PID: {proc.pid})")
                    print(f"{Fore.GREEN}Suspended kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process suspended"))
                    spinner_thread.start()
                    time.sleep(1)
                    stop_event.set()
                    spinner_thread.join()
                except psutil.NoSuchProcess:
                    logger.warning(f"kasa_manager.exe (PID: {proc.pid}) already terminated")
                except Exception as e:
                    logger.error(f"Failed to suspend kasa_manager.exe (PID: {proc.pid}): {e}")
            time.sleep(1)
    elif is_rro_agent and manager_running:
        logger.info("Cash register not running, manager running - proceeding without suspending manager")
        print(
            f"{Fore.YELLOW}Cash register not running, manager running - proceeding with restoration...{Style.RESET_ALL}")
    else:
        logger.info("No relevant processes found")
        print(f"{Fore.YELLOW}No relevant processes found, proceeding with restoration...{Style.RESET_ALL}")

    try:
        print(f"{Fore.YELLOW}Removing all files in {target_dir}...{Style.RESET_ALL}")
        for item in os.listdir(target_dir):
            item_path = os.path.join(target_dir, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        logger.info(f"All files removed from {target_dir}")
    except Exception as e:
        logger.error(f"Failed to remove files from {target_dir}: {e}")
        print(f"{Fore.RED}Failed to clear {target_dir}: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Clear failed"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return False

    try:
        with zipfile.ZipFile(backup_path, 'r') as zip_ref:
            total_files = len(zip_ref.infolist())
            with tqdm(total=total_files, desc="Restoring backup",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
                for file_info in zip_ref.infolist():
                    zip_ref.extract(file_info, target_dir)
                    pbar.update(1)
        logger.info(f"Restored from backup: {backup_path}")
        print(f"{Fore.GREEN}Successfully restored from backup to {target_dir}!{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"Failed to restore from backup: {e}")
        print(f"{Fore.RED}Failed to restore from backup: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Restore failed"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return False

    try:
        if is_rro_agent:
            kasa_path = os.path.join(target_dir, "checkbox_kasa.exe")
            if os.path.exists(kasa_path):
                logger.info(f"Launching {kasa_path} via cmd")
                print(f"{Fore.CYAN}Launching cash register {kasa_path}...{Style.RESET_ALL}")
                cmd = f'start cmd /K "{kasa_path}"'
                subprocess.Popen(cmd, cwd=target_dir, shell=True)
                logger.info(f"Successfully launched {kasa_path}")
                print(f"{Fore.GREEN}Cash register launched successfully!{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Cash register launched"))
                spinner_thread.start()
                time.sleep(5)
                stop_event.set()
                spinner_thread.join()
            else:
                logger.warning(f"checkbox_kasa.exe not found in {target_dir}")
                print(f"{Fore.YELLOW}checkbox_kasa.exe not found in {target_dir}, skipping launch{Style.RESET_ALL}")
        elif is_paylink:
            paylink_path = os.path.join(target_dir, "CheckboxPayLink.exe")
            if os.path.exists(paylink_path):
                logger.info(f"Launching {paylink_path}")
                print(f"{Fore.CYAN}Launching PayLink {paylink_path}...{Style.RESET_ALL}")
                subprocess.Popen(f'start "" "{paylink_path}"', cwd=target_dir, shell=True)
                logger.info(f"Successfully launched {paylink_path}")
                print(f"{Fore.GREEN}PayLink launched successfully!{Style.RESET_ALL}")
            else:
                logger.warning(f"CheckboxPayLink.exe not found in {target_dir}")
                print(f"{Fore.YELLOW}CheckboxPayLink.exe not found in {target_dir}, skipping launch{Style.RESET_ALL}")
        else:
            manager_path = os.path.join(target_dir, "kasa_manager.exe")
            if os.path.exists(manager_path):
                logger.info(f"Launching {manager_path}")
                print(f"{Fore.CYAN}Launching manager {manager_path}...{Style.RESET_ALL}")
                subprocess.Popen(f'start "" "{manager_path}"', cwd=target_dir, shell=True)
                logger.info(f"Successfully launched {manager_path}")
                print(f"{Fore.GREEN}Manager launched successfully!{Style.RESET_ALL}")
            else:
                logger.warning(f"kasa_manager.exe not found in {target_dir}")
                print(f"{Fore.YELLOW}kasa_manager.exe not found in {target_dir}, skipping launch{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"Failed to launch process after restore: {e}")
        print(f"{Fore.RED}Failed to launch process: {e}{Style.RESET_ALL}")

    if is_rro_agent and cash_running and manager_running and manager_processes:
        print(f"{Fore.YELLOW}Resuming all manager processes...{Style.RESET_ALL}")
        for proc in manager_processes:
            try:
                proc.resume()
                logger.info(f"Resumed kasa_manager.exe (PID: {proc.pid})")
                print(f"{Fore.GREEN}Resumed kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process resumed"))
                spinner_thread.start()
                time.sleep(1)
                stop_event.set()
                spinner_thread.join()
            except psutil.NoSuchProcess:
                logger.warning(f"kasa_manager.exe (PID: {proc.pid}) already terminated")
                print(f"{Fore.YELLOW}kasa_manager.exe (PID: {proc.pid}) already terminated{Style.RESET_ALL}")
            except Exception as e:
                logger.error(f"Failed to resume kasa_manager.exe (PID: {proc.pid}): {e}")
                print(f"{Fore.RED}Failed to resume kasa_manager.exe (PID: {proc.pid}): {e}{Style.RESET_ALL}")

    stop_event = threading.Event()
    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Restore completed"))
    spinner_thread.start()
    time.sleep(2)
    stop_event.set()
    spinner_thread.join()
    return True