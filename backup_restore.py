# -*- coding: utf-8 -*-
import os
import subprocess
import time
import zipfile
import shutil
import threading
from datetime import datetime
from typing import Optional

import psutil
from tqdm import tqdm
from colorama import Fore, Style

from utils import find_process_by_path, find_all_processes_by_name, manage_processes, show_spinner

def create_backup(target_dir: str) -> Optional[str]:
    print(f"{Fore.CYAN}📦 Creating backup for {os.path.basename(target_dir)}...{Style.RESET_ALL}")
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
        print(f"{Fore.GREEN}✓ Backup created: {backup_name}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Backup created"))
        try:
            spinner_thread.start()
            time.sleep(1)
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
        stop_event.set()
        spinner_thread.join()
        return backup_path
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to create backup: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Backup failed"))
        try:
            spinner_thread.start()
            time.sleep(2)
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
        stop_event.set()
        spinner_thread.join()
        return None

def delete_backup(backup_path: str) -> bool:
    print(f"{Fore.CYAN}🗑 Deleting backup {os.path.basename(backup_path)}...{Style.RESET_ALL}")
    try:
        os.remove(backup_path)
        print(f"{Fore.GREEN}✓ Backup deleted successfully!{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Backup deleted"))
        try:
            spinner_thread.start()
            time.sleep(1)
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
        stop_event.set()
        spinner_thread.join()
        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to delete backup: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Delete failed"))
        try:
            spinner_thread.start()
            time.sleep(2)
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
        stop_event.set()
        spinner_thread.join()
        return False

def restore_from_backup(target_dir: str, backup_path: str, is_rro_agent: bool = False,
                        is_paylink: bool = False) -> bool:
    print(f"{Fore.CYAN}🔄 Restoring backup {os.path.basename(backup_path)}...{Style.RESET_ALL}")

    processes_to_check = ["checkbox_kasa.exe"] if is_rro_agent else (
        ["CheckboxPayLink.exe", "POSServer.exe"] if is_paylink else ["kasa_manager.exe"])

    running_processes = []
    try:
        for proc_name in processes_to_check:
            process = find_process_by_path(proc_name, target_dir)
            if process:
                running_processes.append(process)
    except Exception:
        pass

    manager_processes = []
    manager_running = False
    cash_running = bool(running_processes)
    if is_rro_agent:
        try:
            manager_processes = find_all_processes_by_name("kasa_manager.exe")
            manager_running = bool(manager_processes)
        except Exception:
            pass

    if running_processes:
        print(f"{Fore.RED}⚠ Processes running in {target_dir}!{Style.RESET_ALL}")
        for proc in running_processes:
            print(f" - {proc.info['name']} (PID: {proc.pid})")
        choice = input(f"{Fore.CYAN}Close all processes? (Y/N): {Style.RESET_ALL}").strip().lower()
        if choice == "y":
            print(f"{Fore.YELLOW}Stopping processes...{Style.RESET_ALL}")
            for proc in running_processes:
                try:
                    proc.kill()
                    print(f"{Fore.GREEN}✓ Stopped {proc.info['name']} (PID: {proc.pid}).{Style.RESET_ALL}")
                except psutil.NoSuchProcess:
                    pass
                except Exception:
                    print(f"{Fore.RED}✗ Failed to stop {proc.info['name']} (PID: {proc.pid}).{Style.RESET_ALL}")
            # Immediately suspend manager processes to prevent cash restart
            if is_rro_agent and manager_running:
                print(f"{Fore.YELLOW}Pausing manager processes...{Style.RESET_ALL}")
                for proc in manager_processes:
                    try:
                        proc.suspend()
                        print(f"{Fore.GREEN}✓ Paused kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                    except psutil.NoSuchProcess:
                        pass
                    except Exception:
                        print(f"{Fore.RED}✗ Failed to pause kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Restoration cancelled.{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Restore cancelled"))
            try:
                spinner_thread.start()
                time.sleep(2)
            except Exception as e:
                print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
            stop_event.set()
            spinner_thread.join()
            return False
    elif is_rro_agent and manager_running:
        print(f"{Fore.YELLOW}Cash register not running, manager running - proceeding...{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}No relevant processes found, proceeding...{Style.RESET_ALL}")

    try:
        print(f"{Fore.YELLOW}Clearing {target_dir}...{Style.RESET_ALL}")
        for item in os.listdir(target_dir):
            item_path = os.path.join(target_dir, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        print(f"{Fore.GREEN}✓ Directory cleared.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to clear directory: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Clear failed"))
        try:
            spinner_thread.start()
            time.sleep(2)
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
        stop_event.set()
        spinner_thread.join()
        return False

    try:
        with zipfile.ZipFile(backup_path, 'r') as zip_ref:
            total_files = len(zip_ref.infolist())
            with tqdm(total=total_files, desc="Restoring files",
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
                for file_info in zip_ref.infolist():
                    zip_ref.extract(file_info, target_dir)
                    pbar.update(1)
        print(f"{Fore.GREEN}✓ Restored successfully to {target_dir}!{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}✗ Restore failed: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Restore failed"))
        try:
            spinner_thread.start()
            time.sleep(2)
        except Exception as e:
            print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
        stop_event.set()
        spinner_thread.join()
        return False

    try:
        if is_rro_agent:
            kasa_path = os.path.join(target_dir, "checkbox_kasa.exe")
            if os.path.exists(kasa_path):
                print(f"{Fore.CYAN}🚀 Launching cash register...{Style.RESET_ALL}")
                cmd = f'start cmd /K "{kasa_path}"'
                subprocess.Popen(cmd, cwd=target_dir, shell=True)
                print(f"{Fore.GREEN}✓ Cash register launched successfully!{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Cash register launched"))
                try:
                    spinner_thread.start()
                    time.sleep(10)
                except Exception as e:
                    print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
                stop_event.set()
                spinner_thread.join()
            else:
                print(f"{Fore.YELLOW}⚠ Cash register executable not found.{Style.RESET_ALL}")
        elif is_paylink:
            paylink_path = os.path.join(target_dir, "CheckboxPayLink.exe")
            if os.path.exists(paylink_path):
                print(f"{Fore.CYAN}🚀 Launching PayLink...{Style.RESET_ALL}")
                subprocess.Popen(f'start "" "{paylink_path}"', cwd=target_dir, shell=True)
                print(f"{Fore.GREEN}✓ PayLink launched successfully!{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠ PayLink executable not found.{Style.RESET_ALL}")
        else:
            manager_path = os.path.join(target_dir, "kasa_manager.exe")
            if os.path.exists(manager_path):
                print(f"{Fore.CYAN}🚀 Launching manager...{Style.RESET_ALL}")
                subprocess.Popen(f'start "" "{manager_path}"', cwd=target_dir, shell=True)
                print(f"{Fore.GREEN}✓ Manager launched successfully!{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠ Manager executable not found.{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to launch process: {e}{Style.RESET_ALL}")

    if is_rro_agent and cash_running and manager_running and manager_processes:
        print(f"{Fore.YELLOW}Resuming manager processes...{Style.RESET_ALL}")
        for proc in manager_processes:
            try:
                proc.resume()
                print(f"{Fore.GREEN}✓ Resumed kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process resumed"))
                try:
                    spinner_thread.start()
                    time.sleep(1)
                except Exception as e:
                    print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
                stop_event.set()
                spinner_thread.join()
            except psutil.NoSuchProcess:
                print(f"{Fore.YELLOW}⚠ kasa_manager.exe (PID: {proc.pid}) already terminated.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}✗ Failed to resume kasa_manager.exe: {e}{Style.RESET_ALL}")

    stop_event = threading.Event()
    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Restore completed"))
    try:
        spinner_thread.start()
        time.sleep(2)
    except Exception as e:
        print(f"{Fore.YELLOW}⚠ Spinner thread failed: {e}{Style.RESET_ALL}")
    stop_event.set()
    spinner_thread.join()
    return True