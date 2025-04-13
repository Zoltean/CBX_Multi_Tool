# -*- coding: utf-8 -*-
import os
import sqlite3
import subprocess
import sys
import time
import zipfile
import threading
from typing import Dict, Optional, List
from tqdm import tqdm
from colorama import Fore, Style

import psutil
from config import DRIVES
from utils import find_process_by_path, find_all_processes_by_name, manage_processes, show_spinner
from network import download_file
from backup_restore import create_backup, restore_from_backup, delete_backup

def find_external_cash_registers_by_processes() -> list:
    """
    Finds cash registers by checking running processes for checkbox_kasa.exe.
    """
    external_cashes = []
    seen_paths = set()

    for proc in psutil.process_iter(['pid', 'exe', 'cwd']):
        try:
            if proc.name().lower() == "checkbox_kasa.exe":
                proc_cwd = os.path.normpath(proc.cwd()).lower()
                if proc_cwd not in seen_paths:
                    seen_paths.add(proc_cwd)
                    external_cashes.append({
                        "path": proc_cwd,
                        "source": "process"
                    })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return external_cashes

def find_external_cash_registers_by_filesystem(manager_dir: str, seen_paths: set) -> list:
    """
    Performs a recursive search for cash registers within the manager's profiles directory (depth of 2).
    Excludes paths already seen to avoid duplicates.
    """
    external_cashes = []
    import glob

    pattern = os.path.join(manager_dir, "profiles", "*", "checkbox_kasa.exe")
    try:
        for kasa_exe in glob.glob(pattern, recursive=False):
            kasa_dir = os.path.normpath(os.path.dirname(kasa_exe)).lower()
            if kasa_dir not in seen_paths:
                seen_paths.add(kasa_dir)
                external_cashes.append({
                    "path": kasa_dir,
                    "source": "filesystem"
                })
    except Exception:
        pass

    return external_cashes

def find_cash_registers_by_profiles_json(manager_dir: str) -> tuple[list, bool, set]:
    """
    Reads profiles.json to find cash register locations.
    Returns a list of cash registers, a boolean indicating if the file is empty, and a set of seen paths.
    """
    profiles_json_path = os.path.join(manager_dir, "profiles.json")
    cash_registers = []
    is_empty = False
    seen_paths = set()
    import json

    if not os.path.exists(profiles_json_path):
        return cash_registers, False, seen_paths

    try:
        with open(profiles_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profiles = data.get("profiles", {})
        if not profiles:
            is_empty = True
        else:
            for profile_id, profile in profiles.items():
                exec_path = profile.get("local", {}).get("paths", {}).get("exec_path", "")
                if exec_path and os.path.exists(exec_path):
                    norm_path = os.path.normpath(exec_path).lower()
                    seen_paths.add(norm_path)
                    cash_registers.append({
                        "path": norm_path,
                        "source": "profiles_json"
                    })
    except Exception:
        pass

    return cash_registers, is_empty, seen_paths

def install_file(file_data: Dict, paylink_patch_data: Optional[Dict] = None, data: Optional[Dict] = None) -> bool:
    filename = file_data["name"]
    url = file_data["url"]
    print(f"{Fore.CYAN}📥 Preparing to install {filename}...{Style.RESET_ALL}")

    try:
        if not download_file(url, filename):
            print(f"{Fore.RED}✗ Installation cancelled.{Style.RESET_ALL}")
            return False

        print(f"{Fore.CYAN}🚀 Launching installer...{Style.RESET_ALL}")
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Installer {filename} not found")

        full_path = os.path.abspath(filename)
        cmd = f'start "" "{full_path}"'
        subprocess.Popen(cmd, shell=True, cwd=os.path.dirname(full_path))

        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Starting installation"))
        spinner_thread.start()
        time.sleep(1)
        stop_event.set()
        spinner_thread.join()

        print(f"{Fore.GREEN}✓ Installation started successfully!{Style.RESET_ALL}")

        if data and "dev" in data and "paylink" in data["dev"]:
            paylink_items = data["dev"]["paylink"]
            if any(item.get("name") == filename for item in paylink_items):
                latest_paylink_patch = paylink_items[-1]
                if "patch_name" in latest_paylink_patch and "patch_url" in latest_paylink_patch:
                    print()
                    choice = input(
                        f"{Fore.CYAN}Update PayLink to {latest_paylink_patch['patch_name']}? (Y/N): {Style.RESET_ALL}"
                    ).strip().lower()
                    if choice == "y":
                        patch_success = patch_file(
                            latest_paylink_patch,
                            "Checkbox PayLink (Beta)",
                            data,
                            is_paylink=True
                        )
                        if patch_success:
                            print(f"{Fore.GREEN}✓ PayLink updated successfully!{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.RED}✗ Failed to update PayLink.{Style.RESET_ALL}")

                        paylink_dir = None
                        for drive in DRIVES:
                            path = f"{drive}\\Checkbox PayLink (Beta)"
                            if os.path.exists(path):
                                paylink_dir = path
                                break

                        if paylink_dir:
                            paylink_path = os.path.join(paylink_dir, "CheckboxPayLink.exe")
                            if os.path.exists(paylink_path):
                                print(f"{Fore.CYAN}🚀 Launching PayLink...{Style.RESET_ALL}")
                                subprocess.Popen(f'start "" "{paylink_path}"', cwd=paylink_dir, shell=True)
                                print(f"{Fore.GREEN}✓ PayLink launched successfully!{Style.RESET_ALL}")
                            else:
                                print(f"{Fore.YELLOW}⚠ PayLink executable not found.{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.YELLOW}⚠ PayLink directory not found.{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update completed"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                    else:
                        print(f"{Fore.GREEN}✓ Update skipped.{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update skipped"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()

        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Installation failed: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Installation failed"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return False

def extract_to_multiple_dirs(zip_ref: zipfile.ZipFile, target_dirs: List[str], total_files: int) -> None:
    try:
        with tqdm(total=total_files * len(target_dirs), desc="Extracting to directories",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
            for file_info in zip_ref.infolist():
                for target_dir in target_dirs:
                    target_path = os.path.join(target_dir, file_info.filename)
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    zip_ref.extract(file_info, target_dir)
                    pbar.update(1)
    except Exception as e:
        print(f"{Fore.RED}✗ Extraction error: {e}{Style.RESET_ALL}")
        raise

def collect_profiles_info(manager_dir: str, is_rro_agent: bool) -> tuple[list, bool]:
    """
    Collects information about cash register profiles from profiles.json, filesystem, and processes.
    Returns a tuple of profiles_info list and a boolean indicating if profiles.json is empty.
    """
    profiles_info = []
    is_empty = False

    if is_rro_agent and manager_dir:
        # Check profiles.json
        cash_registers, is_empty, seen_paths = find_cash_registers_by_profiles_json(manager_dir)
        if is_empty:
            print(f"{Fore.RED}! ! ! PROFILES.JSON ARE EMPTY ! ! !{Style.RESET_ALL}")

        # Add cash registers from profiles.json (non-external)
        for cash in cash_registers:
            db_path = os.path.join(cash["path"], "agent.db")
            version = "Unknown"
            fiscal_number = "Unknown"
            health = "BAD"
            trans_status = "ERROR"
            shift_status = "OPENED"
            is_running = bool(find_process_by_path("checkbox_kasa.exe", cash["path"]))

            try:
                version_path = os.path.join(cash["path"], "version")
                if os.path.exists(version_path):
                    with open(version_path, "r", encoding="utf-8") as f:
                        version = f.read().strip()
            except Exception:
                pass

            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("SELECT fiscal_number FROM cash_register LIMIT 1;")
                    result = cursor.fetchone()
                    if result and result[0]:
                        fiscal_number = result[0]
                    conn.close()
                except Exception:
                    pass

                for attempt in range(3):
                    try:
                        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                        cursor = conn.cursor()

                        cursor.execute("PRAGMA integrity_check;")
                        result = cursor.fetchone()[0]
                        if result == "ok":
                            health = "OK"
                            cursor.execute("SELECT status FROM transactions;")
                            statuses = [row[0] for row in cursor.fetchall()]
                            if not statuses:
                                trans_status = "EMPTY"
                            elif any(s == "ERROR" for s in statuses):
                                trans_status = "ERROR"
                            elif any(s == "PENDING" for s in statuses):
                                trans_status = "PENDING"
                            else:
                                trans_status = "DONE"

                            cursor.execute("SELECT status FROM shifts WHERE id = (SELECT MAX(id) FROM shifts);")
                            shift_result = cursor.fetchone()
                            if shift_result:
                                shift_status = shift_result[0].upper()
                            else:
                                shift_status = "CLOSED"
                        break
                    except Exception:
                        time.sleep(1)
                    finally:
                        if 'conn' in locals():
                            conn.close()
                            time.sleep(0.1)

            profiles_info.append({
                "name": os.path.basename(cash["path"]),
                "path": cash["path"],
                "health": health,
                "trans_status": trans_status,
                "shift_status": shift_status,
                "version": version,
                "fiscal_number": fiscal_number,
                "is_running": is_running,
                "is_external": False
            })

        # Perform filesystem search to find additional cash registers
        external_cashes = find_external_cash_registers_by_filesystem(manager_dir, seen_paths)
        for cash in external_cashes:
            db_path = os.path.join(cash["path"], "agent.db")
            version = "Unknown"
            fiscal_number = "Unknown"
            health = "BAD"
            trans_status = "ERROR"
            shift_status = "OPENED"
            is_running = bool(find_process_by_path("checkbox_kasa.exe", cash["path"]))

            try:
                version_path = os.path.join(cash["path"], "version")
                if os.path.exists(version_path):
                    with open(version_path, "r", encoding="utf-8") as f:
                        version = f.read().strip()
            except Exception:
                pass

            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("SELECT fiscal_number FROM cash_register LIMIT 1;")
                    result = cursor.fetchone()
                    if result and result[0]:
                        fiscal_number = result[0]
                    conn.close()
                except Exception:
                    pass

                for attempt in range(3):
                    try:
                        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                        cursor = conn.cursor()

                        cursor.execute("PRAGMA integrity_check;")
                        result = cursor.fetchone()[0]
                        if result == "ok":
                            health = "OK"
                            cursor.execute("SELECT status FROM transactions;")
                            statuses = [row[0] for row in cursor.fetchall()]
                            if not statuses:
                                trans_status = "EMPTY"
                            elif any(s == "ERROR" for s in statuses):
                                trans_status = "ERROR"
                            elif any(s == "PENDING" for s in statuses):
                                trans_status = "PENDING"
                            else:
                                trans_status = "DONE"

                            cursor.execute("SELECT status FROM shifts WHERE id = (SELECT MAX(id) FROM shifts);")
                            shift_result = cursor.fetchone()
                            if shift_result:
                                shift_status = shift_result[0].upper()
                            else:
                                shift_status = "CLOSED"
                        break
                    except Exception:
                        time.sleep(1)
                    finally:
                        if 'conn' in locals():
                            conn.close()
                            time.sleep(0.1)

            profiles_info.append({
                "name": f"[Ext] {os.path.basename(cash['path'])}",
                "path": cash["path"],
                "health": health,
                "trans_status": trans_status,
                "shift_status": shift_status,
                "version": version,
                "fiscal_number": fiscal_number,
                "is_running": is_running,
                "is_external": True
            })
    else:
        # If no manager directory, search for running processes
        external_cashes = find_external_cash_registers_by_processes()
        for cash in external_cashes:
            db_path = os.path.join(cash["path"], "agent.db")
            version = "Unknown"
            fiscal_number = "Unknown"
            health = "BAD"
            trans_status = "ERROR"
            shift_status = "OPENED"
            is_running = bool(find_process_by_path("checkbox_kasa.exe", cash["path"]))

            try:
                version_path = os.path.join(cash["path"], "version")
                if os.path.exists(version_path):
                    with open(version_path, "r", encoding="utf-8") as f:
                        version = f.read().strip()
            except Exception:
                pass

            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("SELECT fiscal_number FROM cash_register LIMIT 1;")
                    result = cursor.fetchone()
                    if result and result[0]:
                        fiscal_number = result[0]
                    conn.close()
                except Exception:
                    pass

                for attempt in range(3):
                    try:
                        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
                        cursor = conn.cursor()

                        cursor.execute("PRAGMA integrity_check;")
                        result = cursor.fetchone()[0]
                        if result == "ok":
                            health = "OK"
                            cursor.execute("SELECT status FROM transactions;")
                            statuses = [row[0] for row in cursor.fetchall()]
                            if not statuses:
                                trans_status = "EMPTY"
                            elif any(s == "ERROR" for s in statuses):
                                trans_status = "ERROR"
                            elif any(s == "PENDING" for s in statuses):
                                trans_status = "PENDING"
                            else:
                                trans_status = "DONE"

                            cursor.execute("SELECT status FROM shifts WHERE id = (SELECT MAX(id) FROM shifts);")
                            shift_result = cursor.fetchone()
                            if shift_result:
                                shift_status = shift_result[0].upper()
                            else:
                                shift_status = "CLOSED"
                        break
                    except Exception:
                        time.sleep(1)
                    finally:
                        if 'conn' in locals():
                            conn.close()
                            time.sleep(0.1)

            profiles_info.append({
                "name": f"[Ext] {os.path.basename(cash['path'])}",
                "path": cash["path"],
                "health": health,
                "trans_status": trans_status,
                "shift_status": shift_status,
                "version": version,
                "fiscal_number": fiscal_number,
                "is_running": is_running,
                "is_external": True
            })

    return profiles_info, is_empty

def patch_file(patch_data: Dict, folder_name: str, data: Dict, is_rro_agent: bool = False,
               is_paylink: bool = False) -> bool:
    """
    Applies a patch to the specified folder, handling cash registers, PayLink, or manager.
    For cash registers, stays in profile selection menu after patching until '0' or 'Q'.
    """
    patch_file_name = patch_data["patch_name"]
    patch_url = patch_data["patch_url"]
    print(f"{Fore.CYAN}📥 Preparing to apply {patch_file_name}...{Style.RESET_ALL}")

    try:
        if not download_file(patch_url, patch_file_name):
            print(f"{Fore.RED}✗ Update cancelled.{Style.RESET_ALL}")
            return False

        target_folder = "checkbox.kasa.manager" if is_rro_agent else (
            "Checkbox PayLink (Beta)" if is_paylink else "checkbox.kasa.manager")

        install_dir = None
        for drive in DRIVES:
            path = f"{drive}\\{target_folder}"
            if os.path.exists(path):
                install_dir = path
                break

        if not install_dir:
            print(f"{Fore.RED}✗ {target_folder} not found on any drive.{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Directory not found"))
            spinner_thread.start()
            time.sleep(2)
            stop_event.set()
            spinner_thread.join()
            return False

        try:
            test_file = os.path.join(install_dir, "test_access.tmp")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except PermissionError:
            print(f"{Fore.RED}✗ No write permissions for {install_dir}. Please run as administrator.{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Permission error"))
            spinner_thread.start()
            time.sleep(2)
            stop_event.set()
            spinner_thread.join()
            return False
        except Exception as e:
            print(f"{Fore.RED}✗ Permission check failed: {e}{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Permission error"))
            spinner_thread.start()
            time.sleep(2)
            stop_event.set()
            spinner_thread.join()
            return False

        print(f"{Fore.GREEN}✓ Found installation directory: {install_dir}{Style.RESET_ALL}")

        if is_rro_agent:
            manager_dir = install_dir
            # Initial collection of profiles
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Searching cash registers"))
            spinner_thread.start()
            profiles_info, is_empty = collect_profiles_info(manager_dir, is_rro_agent)
            stop_event.set()
            spinner_thread.join()

            if not profiles_info:
                print(f"{Fore.RED}✗ No profiles found in {install_dir}.{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "No profiles"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                return False

            while True:
                os.system("cls")
                print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
                print(f"{Fore.CYAN} SELECT PROFILE TO UPDATE {Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}\n")
                print(f"{Fore.CYAN}Available profiles:{Style.RESET_ALL}\n")
                for i, profile in enumerate(profiles_info, 1):
                    health_color = Fore.GREEN if profile["health"] == "OK" else Fore.RED
                    trans_color = Fore.GREEN if profile["trans_status"] in ["DONE", "EMPTY"] else Fore.RED
                    shift_color = Fore.GREEN if profile["shift_status"] == "CLOSED" else Fore.RED
                    status_text = "ON" if profile["is_running"] else "OFF"
                    status_color = Fore.RED if profile["is_running"] else Fore.GREEN
                    profile_str = (
                        f"| {Fore.YELLOW}FN: {profile['fiscal_number']}{Style.RESET_ALL} "
                        f"| {status_color}{status_text}{Style.RESET_ALL} "
                        f"| H:{health_color}{profile['health']}{Style.RESET_ALL} "
                        f"| T:{trans_color}{profile['trans_status']}{Style.RESET_ALL} "
                        f"| S:{shift_color}{profile['shift_status']}{Style.RESET_ALL} "
                        f"| v{profile['version']}"
                    )
                    print(f"{Fore.WHITE}{i}. {profile['name']} {profile_str}{Style.RESET_ALL}")
                print(f"\n{Fore.WHITE}{len(profiles_info) + 1}. All profiles{Style.RESET_ALL}")
                print(f"{Fore.WHITE}0. Back{Style.RESET_ALL}")
                print(f"{Fore.WHITE}Q. Exit{Style.RESET_ALL}")

                profiles_dir = os.path.join(install_dir, "profiles")
                backup_files = [f for f in os.listdir(profiles_dir) if f.endswith(".zip") and "backup" in f.lower()]
                if backup_files:
                    print(f"\n{Fore.YELLOW}Available backups:{Style.RESET_ALL}")
                    for i, backup in enumerate(backup_files, 1):
                        print(f"{Fore.WHITE}B{i}. Restore {backup}{Style.RESET_ALL}")
                        print(f"{Fore.WHITE}D{i}. Delete {backup}{Style.RESET_ALL}")
                    print()

                print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
                choice = input(f"{Fore.CYAN}Enter your choice: {Style.RESET_ALL}")

                if choice.lower() in ["q", "й"]:
                    from cleanup import cleanup
                    cleanup(data)
                    sys.exit(0)

                if choice.lower().startswith("b") and len(choice) > 1:
                    try:
                        backup_idx = int(choice[1:]) - 1
                        if 0 <= backup_idx < len(backup_files):
                            backup_path = os.path.join(profiles_dir, backup_files[backup_idx])
                            target_dir = os.path.join(profiles_dir,
                                                      os.path.splitext(backup_files[backup_idx])[0].split("_backup_")[0])
                            if os.path.exists(target_dir):
                                if restore_from_backup(target_dir, backup_path, is_rro_agent=is_rro_agent,
                                                       is_paylink=is_paylink):
                                    print(f"{Fore.GREEN}✓ Profile {os.path.basename(target_dir)} restored.{Style.RESET_ALL}")
                                    stop_event = threading.Event()
                                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Restore completed"))
                                    spinner_thread.start()
                                    time.sleep(1)
                                    stop_event.set()
                                    spinner_thread.join()
                                else:
                                    print(f"{Fore.RED}✗ Restore failed.{Style.RESET_ALL}")
                                    input("Press Enter to continue...")
                            else:
                                print(f"{Fore.RED}✗ Target directory not found for backup.{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Directory not found"))
                                spinner_thread.start()
                                time.sleep(2)
                                stop_event.set()
                                spinner_thread.join()
                        else:
                            print(f"{Fore.RED}✗ Invalid backup selection.{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid selection"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                    except ValueError:
                        print(f"{Fore.RED}✗ Invalid backup input.{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                    except Exception as e:
                        print(f"{Fore.RED}✗ Restore error: {e}{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Restore error"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                    # Refresh profiles after restore
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Refreshing profiles"))
                    spinner_thread.start()
                    profiles_info, is_empty = collect_profiles_info(manager_dir, is_rro_agent)
                    stop_event.set()
                    spinner_thread.join()
                    continue

                if choice.lower().startswith("d") and len(choice) > 1:
                    try:
                        backup_idx = int(choice[1:]) - 1
                        if 0 <= backup_idx < len(backup_files):
                            backup_path = os.path.join(profiles_dir, backup_files[backup_idx])
                            if delete_backup(backup_path):
                                print(f"{Fore.GREEN}✓ Backup deleted.{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Backup deleted"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            else:
                                print(f"{Fore.RED}✗ Failed to delete backup.{Style.RESET_ALL}")
                                input("Press Enter to continue...")
                        else:
                            print(f"{Fore.RED}✗ Invalid delete selection.{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid selection"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                    except ValueError:
                        print(f"{Fore.RED}✗ Invalid delete input.{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                    except Exception as e:
                        print(f"{Fore.RED}✗ Delete error: {e}{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Delete error"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                    continue

                try:
                    choice_int = int(choice)
                    if choice_int == 0:
                        print(f"{Fore.GREEN}✓ Returning to previous menu...{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Returning"))
                        spinner_thread.start()
                        time.sleep(1)
                        stop_event.set()
                        spinner_thread.join()
                        return False
                    elif 1 <= choice_int <= len(profiles_info):
                        selected_profile = profiles_info[choice_int - 1]
                        if selected_profile["health"] == "BAD":
                            print(f"{Fore.RED}✗ Cannot update {selected_profile['name']}: Database corrupted.{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update cancelled"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                            continue
                        target_dirs = [selected_profile["path"]]
                    elif choice_int == len(profiles_info) + 1:
                        for profile in profiles_info:
                            if profile["health"] == "BAD":
                                print(f"{Fore.RED}✗ Cannot update all profiles: {profile['name']} database corrupted.{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update cancelled"))
                                spinner_thread.start()
                                time.sleep(2)
                                stop_event.set()
                                spinner_thread.join()
                                return False
                        target_dirs = [profile["path"] for profile in profiles_info]
                    else:
                        print(f"{Fore.RED}✗ Invalid choice.{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid choice"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                        continue
                except ValueError:
                    print(f"{Fore.RED}✗ Invalid input.{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid input"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    continue

                # Handle backups
                for target_dir in target_dirs:
                    choice = input(
                        f"{Fore.CYAN}Create backup of {os.path.basename(target_dir)} before updating? (Y/N): {Style.RESET_ALL}").strip().lower()
                    if choice == "y":
                        backup_path = create_backup(target_dir)
                        if not backup_path:
                            print(f"{Fore.RED}✗ Backup failed. Continuing without backup...{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Backup failed"))
                            spinner_thread.start()
                            time.sleep(2)
                            stop_event.set()
                            spinner_thread.join()
                    else:
                        print(f"{Fore.GREEN}✓ Backup skipped.{Style.RESET_ALL}")

                # Manage cash register processes
                cash_processes = []
                for target_dir in target_dirs:
                    process = find_process_by_path("checkbox_kasa.exe", target_dir)
                    if process:
                        cash_processes.append(process)

                manager_processes = find_all_processes_by_name("kasa_manager.exe")
                manager_running = bool(manager_processes)
                cash_running = bool(cash_processes)

                if cash_running:
                    print(f"{Fore.RED}⚠ Cash register process is running!{Style.RESET_ALL}")
                    for proc in cash_processes:
                        print(f" - PID: {proc.pid}")
                    choice = input(f"{Fore.CYAN}Close cash register processes? (Y/N): {Style.RESET_ALL}").strip().lower()
                    if choice == "y":
                        print(f"{Fore.YELLOW}Stopping cash register processes...{Style.RESET_ALL}")
                        for proc in cash_processes:
                            try:
                                proc.kill()
                                print(f"{Fore.GREEN}✓ Stopped checkbox_kasa.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process stopped"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                print(f"{Fore.RED}✗ Failed to stop checkbox_kasa.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                        time.sleep(1)
                    else:
                        print(f"{Fore.RED}✗ Update cancelled.{Style.RESET_ALL}")
                        stop_event = threading.Event()
                        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update cancelled"))
                        spinner_thread.start()
                        time.sleep(2)
                        stop_event.set()
                        spinner_thread.join()
                        continue

                    if manager_running:
                        print(f"{Fore.YELLOW}Pausing manager processes...{Style.RESET_ALL}")
                        for proc in manager_processes:
                            try:
                                proc.suspend()
                                print(f"{Fore.GREEN}✓ Paused kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                                stop_event = threading.Event()
                                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process paused"))
                                spinner_thread.start()
                                time.sleep(1)
                                stop_event.set()
                                spinner_thread.join()
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                print(f"{Fore.RED}✗ Failed to pause kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                elif manager_running:
                    print(f"{Fore.YELLOW}Cash register not running, manager running - proceeding...{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}No cash register or manager processes found, proceeding...{Style.RESET_ALL}")

                # Monitor processes during update
                stop_monitoring = threading.Event()
                monitor_threads = []
                processes_to_kill = ["checkbox_kasa.exe"]
                for target_dir in target_dirs:
                    thread = threading.Thread(target=manage_processes, args=(processes_to_kill, [target_dir], stop_monitoring))
                    thread.start()
                    monitor_threads.append(thread)
                print(f"{Fore.CYAN}🔒 Monitoring processes during update...{Style.RESET_ALL}")

                # Extract patch
                print(f"{Fore.CYAN}📦 Extracting {patch_file_name}...{Style.RESET_ALL}")
                try:
                    with zipfile.ZipFile(patch_file_name, 'r') as zip_ref:
                        total_files = len(zip_ref.infolist())
                        if len(target_dirs) > 1:
                            extract_to_multiple_dirs(zip_ref, target_dirs, total_files)
                        else:
                            with tqdm(total=total_files, desc="Extracting files",
                                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
                                for file_info in zip_ref.infolist():
                                    target_path = os.path.join(target_dirs[0], file_info.filename)
                                    if os.path.exists(target_path):
                                        os.remove(target_path)
                                    zip_ref.extract(file_info, target_dirs[0])
                                    pbar.update(1)
                        for target_dir in target_dirs:
                            need_reboot_file = os.path.join(target_dir, ".need_reboot")
                            if os.path.exists(need_reboot_file):
                                os.remove(need_reboot_file)
                    print(f"{Fore.GREEN}✓ Files updated successfully in {', '.join(target_dirs)}!{Style.RESET_ALL}")
                except PermissionError:
                    print(f"{Fore.RED}✗ Permission denied. Please close applications or run as administrator.{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Permission error"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    return False
                except zipfile.BadZipFile:
                    print(f"{Fore.RED}✗ Invalid update file.{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid file"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    return False
                except Exception as e:
                    print(f"{Fore.RED}✗ Update error: {e}{Style.RESET_ALL}")
                    stop_event = threading.Event()
                    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update error"))
                    spinner_thread.start()
                    time.sleep(2)
                    stop_event.set()
                    spinner_thread.join()
                    return False
                finally:
                    stop_monitoring.set()
                    for thread in monitor_threads:
                        try:
                            thread.join()
                        except Exception:
                            pass
                    print(f"{Fore.GREEN}✓ Process monitoring stopped.{Style.RESET_ALL}")

                # Launch updated applications
                for target_dir in target_dirs:
                    try:
                        kasa_path = os.path.join(target_dir, "checkbox_kasa.exe")
                        if os.path.exists(kasa_path):
                            print(f"{Fore.CYAN}🚀 Launching cash register...{Style.RESET_ALL}")
                            cmd = f'start cmd /K "{kasa_path}"'
                            subprocess.Popen(cmd, cwd=target_dir, shell=True)
                            print(f"{Fore.GREEN}✓ Cash register launched successfully!{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Cash register launched"))
                            spinner_thread.start()
                            time.sleep(10)
                            stop_event.set()
                            spinner_thread.join()
                        else:
                            print(f"{Fore.YELLOW}⚠ Cash register executable not found.{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"{Fore.RED}✗ Failed to launch process: {e}{Style.RESET_ALL}")

                # Resume manager processes if paused
                if cash_running and manager_running and 'manager_processes' in locals():
                    print(f"{Fore.YELLOW}Resuming manager processes...{Style.RESET_ALL}")
                    for proc in manager_processes:
                        try:
                            proc.resume()
                            print(f"{Fore.GREEN}✓ Resumed kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                            stop_event = threading.Event()
                            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Process resumed"))
                            spinner_thread.start()
                            time.sleep(1)
                            stop_event.set()
                            spinner_thread.join()
                        except psutil.NoSuchProcess:
                            print(f"{Fore.YELLOW}⚠ kasa_manager.exe (PID: {proc.pid}) already terminated.{Style.RESET_ALL}")
                        except Exception as e:
                            print(f"{Fore.RED}✗ Failed to resume kasa_manager.exe: {e}{Style.RESET_ALL}")

                # Refresh profiles after patching
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Refreshing profiles"))
                spinner_thread.start()
                profiles_info, is_empty = collect_profiles_info(manager_dir, is_rro_agent)
                stop_event.set()
                spinner_thread.join()

                # Display update completion
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update completed"))
                spinner_thread.start()
                time.sleep(1)
                stop_event.set()
                spinner_thread.join()
                continue

        else:
            target_dirs = [install_dir]
            processes_to_kill = ["CheckboxPayLink.exe", "POSServer.exe"] if is_paylink else ["kasa_manager.exe"]
            if not manage_processes(processes_to_kill, target_dirs):
                return False

            # Monitor processes during update
            stop_monitoring = threading.Event()
            monitor_threads = []
            processes_to_kill = ["CheckboxPayLink.exe", "POSServer.exe"] if is_paylink else ["kasa_manager.exe"]
            for target_dir in target_dirs:
                thread = threading.Thread(target=manage_processes, args=(processes_to_kill, [target_dir], stop_monitoring))
                thread.start()
                monitor_threads.append(thread)
            print(f"{Fore.CYAN}🔒 Monitoring processes during update...{Style.RESET_ALL}")

            # Extract patch
            print(f"{Fore.CYAN}📦 Extracting {patch_file_name}...{Style.RESET_ALL}")
            try:
                with zipfile.ZipFile(patch_file_name, 'r') as zip_ref:
                    total_files = len(zip_ref.infolist())
                    with tqdm(total=total_files, desc="Extracting files",
                              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
                        for file_info in zip_ref.infolist():
                            target_path = os.path.join(target_dirs[0], file_info.filename)
                            if os.path.exists(target_path):
                                os.remove(target_path)
                            zip_ref.extract(file_info, target_dirs[0])
                            pbar.update(1)
                    need_reboot_file = os.path.join(target_dirs[0], ".need_reboot")
                    if os.path.exists(need_reboot_file):
                        os.remove(need_reboot_file)
                print(f"{Fore.GREEN}✓ Files updated successfully in {target_dirs[0]}!{Style.RESET_ALL}")
            except PermissionError:
                print(f"{Fore.RED}✗ Permission denied. Please close applications or run as administrator.{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Permission error"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                return False
            except zipfile.BadZipFile:
                print(f"{Fore.RED}✗ Invalid update file.{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Invalid file"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                return False
            except Exception as e:
                print(f"{Fore.RED}✗ Update error: {e}{Style.RESET_ALL}")
                stop_event = threading.Event()
                spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update error"))
                spinner_thread.start()
                time.sleep(2)
                stop_event.set()
                spinner_thread.join()
                return False
            finally:
                stop_monitoring.set()
                for thread in monitor_threads:
                    try:
                        thread.join()
                    except Exception:
                        pass
                print(f"{Fore.GREEN}✓ Process monitoring stopped.{Style.RESET_ALL}")

            # Launch updated applications
            try:
                if is_paylink:
                    paylink_path = os.path.join(target_dirs[0], "CheckboxPayLink.exe")
                    if os.path.exists(paylink_path):
                        print(f"{Fore.CYAN}🚀 Launching PayLink...{Style.RESET_ALL}")
                        subprocess.Popen(f'start "" "{paylink_path}"', cwd=target_dirs[0], shell=True)
                        print(f"{Fore.GREEN}✓ PayLink launched successfully!{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.YELLOW}⚠ PayLink executable not found.{Style.RESET_ALL}")
                else:
                    manager_path = os.path.join(target_dirs[0], "kasa_manager.exe")
                    if os.path.exists(manager_path):
                        print(f"{Fore.CYAN}🚀 Launching manager...{Style.RESET_ALL}")
                        subprocess.Popen(f'start "" "{manager_path}"', cwd=target_dirs[0], shell=True)
                        print(f"{Fore.GREEN}✓ Manager launched successfully!{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.YELLOW}⚠ Manager executable not found.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}✗ Failed to launch process: {e}{Style.RESET_ALL}")

            # Display update completion
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update completed"))
            spinner_thread.start()
            time.sleep(1)
            stop_event.set()
            spinner_thread.join()
            return True

    except Exception as e:
        print(f"{Fore.RED}✗ Update error: {e}{Style.RESET_ALL}")
        stop_event = threading.Event()
        spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Update error"))
        spinner_thread.start()
        time.sleep(2)
        stop_event.set()
        spinner_thread.join()
        return False