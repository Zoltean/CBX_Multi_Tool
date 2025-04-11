# -*- coding: utf-8 -*-
import logging
import os
import subprocess
import time
import zipfile
import threading
from typing import Dict, Optional, List
from tqdm import tqdm
from colorama import Fore, Style

from config import DRIVES
from utils import find_process_by_path, find_all_processes_by_name, manage_processes
from network import download_file
from backup_restore import create_backup, restore_from_backup, delete_backup

logger = logging.getLogger(__name__)

def install_file(file_data: Dict, paylink_patch_data: Optional[Dict] = None, data: Optional[Dict] = None) -> bool:
    filename = file_data["name"]
    url = file_data["url"]
    logger.info(f"Installing {filename} from {url}")
    print(f"{Fore.CYAN}Preparing to install {filename}...{Style.RESET_ALL}")

    try:
        if not download_file(url, filename):
            logger.error(f"Aborted installation of {filename}")
            return False

        logger.info(f"Running installer: {filename}")
        print(f"{Fore.CYAN}Running installer...{Style.RESET_ALL}")
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Installer {filename} not found after download")

        full_path = os.path.abspath(filename)
        logger.debug(f"Full path to installer: {full_path}")

        cmd = f'start "" "{full_path}"'
        process = subprocess.Popen(cmd, shell=True, cwd=os.path.dirname(full_path))
        logger.info(f"Installer {filename} launched asynchronously via cmd")
        print(f"{Fore.GREEN}Installation of {filename} started!{Style.RESET_ALL}")
        time.sleep(2)

        if data and "dev" in data and "paylink" in data["dev"]:
            paylink_items = data["dev"]["paylink"]
            if any(item.get("name") == filename for item in paylink_items):
                latest_paylink_patch = paylink_items[-1]
                if "patch_name" in latest_paylink_patch and "patch_url" in latest_paylink_patch:
                    print()
                    choice = input(
                        f"{Fore.CYAN}Would you like to patch PayLink to the latest version ({latest_paylink_patch['patch_name']})? (Y/N): {Style.RESET_ALL}"
                    ).strip().lower()
                    logger.info(f"User prompted to patch PayLink after install, response: {choice}")
                    if choice == "y":
                        logger.info(f"User chose to patch PayLink to {latest_paylink_patch['patch_name']}")
                        patch_success = patch_file(
                            latest_paylink_patch,
                            "Checkbox PayLink (Beta)",
                            data,
                            is_paylink=True
                        )
                        if patch_success:
                            logger.info(f"PayLink patched successfully to {latest_paylink_patch['patch_name']}")
                            print(f"{Fore.GREEN}PayLink patched successfully!{Style.RESET_ALL}")
                        else:
                            logger.error("PayLink patching failed")
                            print(f"{Fore.RED}Failed to patch PayLink.{Style.RESET_ALL}")

                        paylink_dir = None
                        for drive in DRIVES:
                            path = f"{drive}\\Checkbox PayLink (Beta)"
                            if os.path.exists(path):
                                paylink_dir = path
                                break

                        if paylink_dir:
                            paylink_path = os.path.join(paylink_dir, "CheckboxPayLink.exe")
                            if os.path.exists(paylink_path):
                                logger.info(f"Launching {paylink_path}")
                                print(f"{Fore.CYAN}Launching PayLink {paylink_path}...{Style.RESET_ALL}")
                                subprocess.Popen(f'start "" "{paylink_path}"', cwd=paylink_dir, shell=True)
                                logger.info(f"Successfully launched {paylink_path}")
                                print(f"{Fore.GREEN}PayLink launched successfully!{Style.RESET_ALL}")
                            else:
                                logger.warning(f"CheckboxPayLink.exe not found in {paylink_dir}")
                                print(
                                    f"{Fore.YELLOW}CheckboxPayLink.exe not found in {paylink_dir}, skipping launch{Style.RESET_ALL}")
                        else:
                            logger.warning("Checkbox PayLink (Beta) directory not found")
                            print(
                                f"{Fore.YELLOW}Checkbox PayLink (Beta) directory not found, skipping launch{Style.RESET_ALL}")
                        time.sleep(2)
                    else:
                        logger.info("User declined PayLink patch after install")
                        print(f"{Fore.GREEN}Patch skipped.{Style.RESET_ALL}")
                        time.sleep(1)

        return True
    except Exception as e:
        logger.error(f"Installation failed: {e}")
        print(f"{Fore.RED}Installation failed: {e}{Style.RESET_ALL}")
        time.sleep(5)
        return False

def extract_to_multiple_dirs(zip_ref: zipfile.ZipFile, target_dirs: List[str], total_files: int) -> None:
    try:
        with tqdm(total=total_files * len(target_dirs), desc="Extracting to all dirs",
                  bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]") as pbar:
            for file_info in zip_ref.infolist():
                for target_dir in target_dirs:
                    target_path = os.path.join(target_dir, file_info.filename)
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    zip_ref.extract(file_info, target_dir)
                    pbar.update(1)
    except Exception as e:
        logger.error(f"Error in extract_to_multiple_dirs: {e}")
        raise

def patch_file(patch_data: Dict, folder_name: str, data: Dict, is_rro_agent: bool = False,
               is_paylink: bool = False) -> bool:
    patch_file_name = patch_data["patch_name"]
    patch_url = patch_data["patch_url"]
    logger.info(f"Patching with {patch_file_name} from {patch_url}")
    print(f"{Fore.CYAN}Preparing to patch with {patch_file_name}...{Style.RESET_ALL}")

    try:
        if not download_file(patch_url, patch_file_name):
            logger.error(f"Aborted patching of {patch_file_name}")
            return False

        target_folder = "checkbox.kasa.manager" if is_rro_agent else (
            "Checkbox PayLink (Beta)" if is_paylink else "checkbox.kasa.manager")

        install_dir = None
        for drive in DRIVES:
            path = f"{drive}\\{target_folder}"
            logger.debug(f"Checking for folder: {path}")
            if os.path.exists(path):
                install_dir = path
                break

        if not install_dir:
            logger.error(f"Folder {target_folder} not found on any drive")
            print(f"{Fore.RED}Error: Folder {target_folder} not found on any drive!{Style.RESET_ALL}")
            time.sleep(2)
            return False

        logger.info(f"Found installation directory: {install_dir}")
        print(f"{Fore.GREEN}Found installation directory: {install_dir}{Style.RESET_ALL}")

        if is_rro_agent:
            profiles_dir = os.path.join(install_dir, "profiles")
            if not os.path.exists(profiles_dir):
                logger.error(f"Profiles folder not found in {install_dir}")
                print(f"{Fore.RED}Error: Profiles folder not found in {install_dir}!{Style.RESET_ALL}")
                time.sleep(2)
                return False

            profile_folders = [f for f in os.listdir(profiles_dir) if os.path.isdir(os.path.join(profiles_dir, f))]
            if not profile_folders:
                logger.error(f"No profile folders found in {profiles_dir}")
                print(f"{Fore.RED}Error: No profile folders found in {profiles_dir}!{Style.RESET_ALL}")
                time.sleep(2)
                return False

            while True:
                os.system("cls")
                print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}           SELECT PROFILE{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
                print(f"{Fore.CYAN}Available profiles:{Style.RESET_ALL}")
                for i, folder in enumerate(profile_folders, 1):
                    print(f"{i}. {folder}")
                print(f"{len(profile_folders) + 1}. All profiles")
                print(f"0. Back")
                print(f"Q. Exit with cleanup")
                print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")

                backup_files = [f for f in os.listdir(profiles_dir) if f.endswith(".zip") and "backup" in f.lower()]
                if backup_files:
                    print(f"{Fore.YELLOW}Found backups:{Style.RESET_ALL}")
                    for i, backup in enumerate(backup_files, 1):
                        print(f"B{i}. Restore {backup}")
                        print(f"D{i}. Delete {backup}")
                    print(f"{Fore.YELLOW}---------------{Style.RESET_ALL}")

                choice = input("Select an option: ").strip()
                logger.info(f"User input in profile selection: {choice}")

                if choice.lower() in ["q", "й"]:
                    logger.info("User chose to exit with cleanup from profile selection")
                    from cleanup import cleanup
                    cleanup(data)
                    sys.exit(0)

                if choice.lower().startswith("b") and len(choice) > 1:
                    try:
                        backup_idx = int(choice[1:]) - 1
                        if 0 <= backup_idx < len(backup_files):
                            backup_path = os.path.join(profiles_dir, backup_files[backup_idx])
                            target_dir = os.path.join(profiles_dir,
                                                      os.path.splitext(backup_files[backup_idx])[0].split("_backup_")[
                                                          0])
                            if os.path.exists(target_dir):
                                if restore_from_backup(target_dir, backup_path, is_rro_agent=is_rro_agent,
                                                       is_paylink=is_paylink):
                                    print(
                                        f"{Fore.GREEN}Profile {os.path.basename(target_dir)} restored.{Style.RESET_ALL}")
                                    time.sleep(2)
                                else:
                                    print(f"{Fore.RED}Restore failed. Press ENTER to continue...{Style.RESET_ALL}")
                                    input()
                            else:
                                logger.error(f"Target directory {target_dir} does not exist for restore")
                                print(f"{Fore.RED}Target directory not found for this backup!{Style.RESET_ALL}")
                                time.sleep(2)
                        else:
                            print(f"{Fore.RED}Invalid backup choice!{Style.RESET_ALL}")
                            time.sleep(2)
                    except ValueError:
                        print(f"{Fore.RED}Invalid backup input!{Style.RESET_ALL}")
                        time.sleep(2)
                    except Exception as e:
                        logger.error(f"Error restoring backup: {e}")
                        print(f"{Fore.RED}Error restoring backup: {e}{Style.RESET_ALL}")
                        time.sleep(2)
                    continue

                if choice.lower().startswith("d") and len(choice) > 1:
                    try:
                        backup_idx = int(choice[1:]) - 1
                        if 0 <= backup_idx < len(backup_files):
                            backup_path = os.path.join(profiles_dir, backup_files[backup_idx])
                            if delete_backup(backup_path):
                                print(f"{Fore.GREEN}Backup deleted.{Style.RESET_ALL}")
                                time.sleep(2)
                            else:
                                print(f"{Fore.RED}Failed to delete backup. Press ENTER to continue...{Style.RESET_ALL}")
                                input()
                        else:
                            print(f"{Fore.RED}Invalid delete choice!{Style.RESET_ALL}")
                            time.sleep(2)
                    except ValueError:
                        print(f"{Fore.RED}Invalid delete input!{Style.RESET_ALL}")
                        time.sleep(2)
                    except Exception as e:
                        logger.error(f"Error deleting backup: {e}")
                        print(f"{Fore.RED}Error deleting backup: {e}{Style.RESET_ALL}")
                        time.sleep(2)
                    continue

                try:
                    choice_int = int(choice)
                    if choice_int == 0:
                        logger.info("User chose to return from profile selection")
                        print(f"{Fore.GREEN}Returning to previous menu...{Style.RESET_ALL}")
                        time.sleep(2)
                        return False
                    elif 1 <= choice_int <= len(profile_folders):
                        target_dirs = [os.path.join(profiles_dir, profile_folders[choice_int - 1])]
                        break
                    elif choice_int == len(profile_folders) + 1:
                        target_dirs = [os.path.join(profiles_dir, f) for f in profile_folders]
                        break
                    else:
                        print(f"{Fore.RED}Invalid choice!{Style.RESET_ALL}")
                        time.sleep(2)
                except ValueError:
                    print(f"{Fore.RED}Invalid input!{Style.RESET_ALL}")
                    time.sleep(2)

            for target_dir in target_dirs:
                choice = input(
                    f"{Fore.CYAN}Would you like to create a backup of {os.path.basename(target_dir)} before patching? (Y/N): {Style.RESET_ALL}").strip().lower()
                logger.info(f"User prompted for backup of {target_dir}, response: {choice}")
                if choice == "y":
                    backup_path = create_backup(target_dir)
                    if not backup_path:
                        print(f"{Fore.RED}Backup creation failed. Proceeding without backup...{Style.RESET_ALL}")
                        time.sleep(2)
                else:
                    logger.info(f"User declined backup for {target_dir}")

            cash_processes = []
            for target_dir in target_dirs:
                process = find_process_by_path("checkbox_kasa.exe", target_dir)
                if process:
                    cash_processes.append(process)

            manager_processes = find_all_processes_by_name("kasa_manager.exe")
            manager_running = bool(manager_processes)
            cash_running = bool(cash_processes)

            if cash_running:
                print(f"{Fore.RED}Warning: checkbox_kasa.exe is running!{Style.RESET_ALL}")
                for proc in cash_processes:
                    print(f" - PID: {proc.pid}")
                print(f"{Fore.RED}To proceed with patching, this process must be closed.{Style.RESET_ALL}")
                choice = input(f"Close cash register processes? (Y/N): ").strip().lower()
                logger.info(f"User prompted to kill cash processes, response: {choice}")
                if choice == "y":
                    print(f"{Fore.YELLOW}Stopping all cash register processes...{Style.RESET_ALL}")
                    for proc in cash_processes:
                        try:
                            proc.kill()
                            logger.info(f"Killed checkbox_kasa.exe (PID: {proc.pid})")
                            print(f"{Fore.GREEN}Killed checkbox_kasa.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                        except psutil.NoSuchProcess:
                            logger.warning(f"checkbox_kasa.exe (PID: {proc.pid}) already terminated")
                        except Exception as e:
                            logger.error(f"Failed to kill checkbox_kasa.exe (PID: {proc.pid}): {e}")
                    time.sleep(1)
                else:
                    logger.info("User declined to kill cash processes, aborting patch")
                    print(f"{Fore.RED}Patching aborted by user.{Style.RESET_ALL}")
                    time.sleep(2)
                    return False

                if manager_running:
                    print(f"{Fore.YELLOW}Freezing all manager processes...{Style.RESET_ALL}")
                    for proc in manager_processes:
                        try:
                            proc.suspend()
                            logger.info(f"Suspended kasa_manager.exe (PID: {proc.pid})")
                            print(f"{Fore.GREEN}Suspended kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                        except psutil.NoSuchProcess:
                            logger.warning(f"kasa_manager.exe (PID: {proc.pid}) already terminated")
                        except Exception as e:
                            logger.error(f"Failed to suspend kasa_manager.exe (PID: {proc.pid}): {e}")
            elif manager_running:
                logger.info("Cash register not running, manager running - proceeding without suspending manager")
                print(
                    f"{Fore.YELLOW}Cash register not running, manager running - proceeding with patching...{Style.RESET_ALL}")
            else:
                logger.info("No cash register or manager processes found")
                print(
                    f"{Fore.YELLOW}No cash register or manager processes found, proceeding with patching...{Style.RESET_ALL}")

        else:
            target_dirs = [install_dir]
            processes_to_kill = ["CheckboxPayLink.exe", "POSServer.exe"] if is_paylink else ["kasa_manager.exe"]
            if not manage_processes(processes_to_kill, target_dirs):
                return False

        stop_monitoring = threading.Event()
        monitor_threads = []
        processes_to_kill = ["checkbox_kasa.exe"] if is_rro_agent else (
            ["CheckboxPayLink.exe", "POSServer.exe"] if is_paylink else ["kasa_manager.exe"])
        for target_dir in target_dirs:
            thread = threading.Thread(target=manage_processes, args=(processes_to_kill, [target_dir], stop_monitoring))
            thread.start()
            monitor_threads.append(thread)
        print(f"{Fore.CYAN}Monitoring processes to prevent launch during patching...{Style.RESET_ALL}")

        logger.info(f"Extracting {patch_file_name}")
        print(f"{Fore.CYAN}Extracting {patch_file_name} with replacement...{Style.RESET_ALL}")
        try:
            with zipfile.ZipFile(patch_file_name, 'r') as zip_ref:
                total_files = len(zip_ref.infolist())
                if is_rro_agent and len(target_dirs) > 1:
                    extract_to_multiple_dirs(zip_ref, target_dirs, total_files)
                else:
                    with tqdm(total=total_files, desc="Extracting",
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
                        logger.info(f"Removed .need_reboot marker from {target_dir}")
            logger.info("Patching completed")
            print(
                f"{Fore.GREEN}Files extracted successfully to {', '.join(target_dirs)} with replacement!{Style.RESET_ALL}")
        except PermissionError as e:
            logger.error(f"Permission denied: {e}")
            print(
                f"{Fore.RED}Error: Permission denied. Please close any running applications or run as Administrator.{Style.RESET_ALL}")
            time.sleep(2)
            return False
        except zipfile.BadZipFile as e:
            logger.error(f"Extraction failed: {e}")
            print(f"{Fore.RED}Error: Invalid archive file!{Style.RESET_ALL}")
            time.sleep(2)
            return False
        except Exception as e:
            logger.error(f"Unexpected error during extraction: {e}")
            print(f"{Fore.RED}Unexpected error during patching: {e}{Style.RESET_ALL}")
            time.sleep(2)
            return False
        finally:
            stop_monitoring.set()
            for thread in monitor_threads:
                try:
                    thread.join()
                    logger.info("Monitoring thread stopped")
                except Exception as e:
                    logger.error(f"Error joining monitoring thread: {e}")
            print(f"{Fore.GREEN}Monitoring stopped.{Style.RESET_ALL}")

        for target_dir in target_dirs:
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
                        time.sleep(5)
                    else:
                        logger.warning(f"checkbox_kasa.exe not found in {target_dir}")
                        print(
                            f"{Fore.YELLOW}checkbox_kasa.exe not found in {target_dir}, skipping launch{Style.RESET_ALL}")

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
                        print(
                            f"{Fore.YELLOW}CheckboxPayLink.exe not found in {target_dir}, skipping launch{Style.RESET_ALL}")

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
                        print(
                            f"{Fore.YELLOW}kasa_manager.exe not found in {target_dir}, skipping launch{Style.RESET_ALL}")
            except Exception as e:
                logger.error(f"Failed to launch process after patching: {e}")
                print(f"{Fore.RED}Failed to launch process: {e}{Style.RESET_ALL}")

        if is_rro_agent and cash_running and manager_running and 'manager_processes' in locals():
            print(f"{Fore.YELLOW}Resuming all manager processes...{Style.RESET_ALL}")
            for proc in manager_processes:
                try:
                    proc.resume()
                    logger.info(f"Resumed kasa_manager.exe (PID: {proc.pid})")
                    print(f"{Fore.GREEN}Resumed kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                except psutil.NoSuchProcess:
                    logger.warning(f"kasa_manager.exe (PID: {proc.pid}) already terminated")
                    print(f"{Fore.YELLOW}kasa_manager.exe (PID: {proc.pid}) already terminated{Style.RESET_ALL}")
                except Exception as e:
                    logger.error(f"Failed to resume kasa_manager.exe (PID: {proc.pid}): {e}")
                    print(f"{Fore.RED}Failed to resume kasa_manager.exe (PID: {proc.pid}): {e}{Style.RESET_ALL}")

        time.sleep(2)
        return True
    except Exception as e:
        logger.error(f"Unexpected error in patch_file: {e}")
        print(f"{Fore.RED}Unexpected error in patching: {e}{Style.RESET_ALL}")
        time.sleep(2)
        return False