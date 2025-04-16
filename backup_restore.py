# -*- coding: utf-8 -*-
import os
import zipfile
import shutil
from datetime import datetime
from typing import Optional

import psutil
from tqdm import tqdm
from colorama import Fore, Style

from utils import find_process_by_path, find_all_processes_by_name, launch_executable, manage_process_lifecycle, \
    run_spinner


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
        run_spinner("Backup created", 1.0)
        return backup_path
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to create backup: {e}{Style.RESET_ALL}")
        run_spinner("Backup failed", 2.0)
        return None


def delete_backup(backup_path: str) -> bool:
    print(f"{Fore.CYAN}🗑 Deleting backup {os.path.basename(backup_path)}...{Style.RESET_ALL}")
    try:
        os.remove(backup_path)
        print(f"{Fore.GREEN}✓ Backup deleted successfully!{Style.RESET_ALL}")
        run_spinner("Backup deleted", 1.0)
        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to delete backup: {e}{Style.RESET_ALL}")
        run_spinner("Delete failed", 2.0)
        return False


def restore_from_backup(target_dir: str, backup_path: str, is_rro_agent: bool = False,
                        is_paylink: bool = False) -> bool:
    print(f"{Fore.CYAN}🔄 Restoring backup {os.path.basename(backup_path)}...{Style.RESET_ALL}")

    processes_to_check = ["checkbox_kasa.exe"] if is_rro_agent else (
        ["CheckboxPayLink.exe", "POSServer.exe"] if is_paylink else ["kasa_manager.exe"])

    if not manage_process_lifecycle(processes_to_check, [target_dir], action="terminate",
                                    prompt=True, spinner_message="Processes terminated", spinner_duration=2.0):
        print(f"{Fore.RED}✗ Restoration cancelled due to process termination failure.{Style.RESET_ALL}")
        run_spinner("Restore cancelled", 2.0)
        return False

    manager_processes = []
    manager_running = False
    if is_rro_agent:
        try:
            manager_processes = find_all_processes_by_name("kasa_manager.exe")
            manager_running = bool(manager_processes)
            if manager_running:
                print(f"{Fore.YELLOW}Pausing manager processes...{Style.RESET_ALL}")
                manage_process_lifecycle(["kasa_manager.exe"], [target_dir], action="suspend",
                                         prompt=False, spinner_message="Manager paused", spinner_duration=1.0)
        except Exception:
            pass

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
        run_spinner("Clear failed", 2.0)
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
        run_spinner("Restore failed", 2.0)
        return False

    try:
        if is_rro_agent:
            launch_executable("checkbox_kasa.exe", target_dir, "Cash register", spinner_duration=10.0)
        elif is_paylink:
            launch_executable("CheckboxPayLink.exe", target_dir, "PayLink", spinner_duration=2.0)
        else:
            launch_executable("kasa_manager.exe", target_dir, "Manager", spinner_duration=2.0)
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to launch process: {e}{Style.RESET_ALL}")

    if is_rro_agent and manager_running:
        print(f"{Fore.YELLOW}Resuming manager processes...{Style.RESET_ALL}")
        manage_process_lifecycle(["kasa_manager.exe"], [target_dir], action="resume",
                                 prompt=False, spinner_message="Manager resumed", spinner_duration=1.0)

    run_spinner("Restore completed", 2.0)
    return True