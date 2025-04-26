import os
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
from utils import find_process_by_path, find_all_processes_by_name, manage_processes, run_spinner, launch_executable
from network import download_file
from backup_restore import create_backup, restore_from_backup, delete_backup
from search_utils import find_cash_registers_by_profiles_json, find_cash_registers_by_exe, get_cash_register_info, reset_cache

def install_file(file_data: Dict, paylink_patch_data: Optional[Dict] = None, data: Optional[Dict] = None, expected_sha256: str = "") -> bool:
    filename = file_data["name"]
    url = file_data["url"]
    print(f"{Fore.CYAN}📥 Preparing to install {filename}...{Style.RESET_ALL}")

    try:
        if not download_file(url, filename, expected_sha256=expected_sha256):
            if expected_sha256:
                print(f"{Fore.YELLOW}⚠ Hash verification failed for {filename}.{Style.RESET_ALL}")
                choice = input(f"{Fore.CYAN}Continue with installation anyway? (Y/N): {Style.RESET_ALL}").strip().lower()
                if choice != "y":
                    print(f"{Fore.RED}✗ Installation cancelled.{Style.RESET_ALL}")
                    return False
                print(f"{Fore.YELLOW}⚠ Proceeding without hash verification.{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}✗ Installation cancelled.{Style.RESET_ALL}")
                return False

        print(f"{Fore.CYAN}🚀 Launching installer...{Style.RESET_ALL}")
        if not os.path.exists(filename):
            raise FileNotFoundError(f"Installer {filename} not found")

        full_path = os.path.abspath(filename)
        cmd = f'start "" "{full_path}"'
        subprocess.Popen(cmd, shell=True, cwd=os.path.dirname(full_path))

        run_spinner("Starting installation", 1.0)

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
                            is_paylink=True,
                            expected_sha256=latest_paylink_patch.get("patch_sha256", "")
                        )
                        if patch_success:
                            print(f"{Fore.GREEN}✓ PayLink updated successfully!{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.RED}✗ Failed to update PayLink.{Style.RESET_ALL}")

                        paylink_dir = None
                        drives = DRIVES if DRIVES is not None else ["C:\\"]
                        for drive in drives:
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
                        run_spinner("Update completed", 2.0)
                    else:
                        print(f"{Fore.GREEN}✓ Update skipped.{Style.RESET_ALL}")
                        run_spinner("Update skipped", 1.0)

        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Installation failed: {e}{Style.RESET_ALL}")
        run_spinner("Installation failed", 2.0)
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

def patch_file(patch_data: Dict, folder_name: str, data: Dict, is_rro_agent: bool = False,
               is_paylink: bool = False, expected_sha256: str = "") -> bool:
    patch_file_name = patch_data["patch_name"]
    patch_url = patch_data["patch_url"]
    print(f"{Fore.CYAN}📥 Preparing to apply {patch_file_name}...{Style.RESET_ALL}")

    try:
        if not download_file(patch_url, patch_file_name, expected_sha256=expected_sha256):
            if expected_sha256:
                print(f"{Fore.YELLOW}⚠ Hash verification failed for {patch_file_name}.{Style.RESET_ALL}")
                choice = input(f"{Fore.CYAN}Continue with update anyway? (Y/N): {Style.RESET_ALL}").strip().lower()
                if choice != "y":
                    print(f"{Fore.RED}✗ Update cancelled.{Style.RESET_ALL}")
                    return False
                print(f"{Fore.YELLOW}⚠ Proceeding without hash verification.{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}⚠ No hash provided for {patch_file_name}. Proceeding without verification.{Style.RESET_ALL}")

        target_folder = "checkbox.kasa.manager" if is_rro_agent else (
            "Checkbox PayLink (Beta)" if is_paylink else "checkbox.kasa.manager")

        install_dir = None
        drives = DRIVES if DRIVES is not None else ["C:\\"]
        for drive in drives:
            path = f"{drive}\\{target_folder}"
            if os.path.exists(path):
                install_dir = path
                break

        if not install_dir:
            print(f"{Fore.RED}✗ {target_folder} not found on any drive.{Style.RESET_ALL}")
            run_spinner("Directory not found", 2.0)
            return False

        try:
            test_file = os.path.join(install_dir, "test_access.tmp")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except PermissionError:
            print(f"{Fore.RED}✗ No write permissions for {install_dir}. Please run as administrator.{Style.RESET_ALL}")
            run_spinner("Permission error", 2.0)
            return False
        except Exception as e:
            print(f"{Fore.RED}✗ Permission check failed: {e}{Style.RESET_ALL}")
            run_spinner("Permission error", 2.0)
            return False

        print(f"{Fore.GREEN}✓ Found installation directory: {install_dir}{Style.RESET_ALL}")

        if is_rro_agent:
            profiles_info = []
            manager_dir = install_dir

            run_spinner("Searching cash registers", 2.0)

            reset_cache()
            if manager_dir:
                cash_registers, is_empty, seen_paths = find_cash_registers_by_profiles_json(manager_dir)
                if is_empty:
                    print(f"{Fore.RED}! ! ! PROFILES.JSON IS EMPTY ! ! !{Style.RESET_ALL}")

                if cash_registers:
                    for cash in cash_registers:
                        if cash and "path" in cash:
                            profile_info = get_cash_register_info(cash["path"], is_external=False)
                            if profile_info:
                                profiles_info.append(profile_info)
                external_cashes = find_cash_registers_by_exe(manager_dir, drives, max_depth=4)
                if external_cashes:
                    for cash in external_cashes:
                        if cash and "path" in cash:
                            normalized_path = os.path.normpath(os.path.abspath(cash["path"]))
                            if normalized_path not in seen_paths:
                                profile_info = get_cash_register_info(cash["path"], is_external=True)
                                if profile_info:
                                    profiles_info.append(profile_info)
                            seen_paths.add(normalized_path)
            else:
                external_cashes = find_cash_registers_by_exe(None, drives, max_depth=4)
                if external_cashes:
                    for cash in external_cashes:
                        if cash and "path" in cash:
                            profile_info = get_cash_register_info(cash["path"], is_external=True)
                            if profile_info:
                                profiles_info.append(profile_info)

            if not profiles_info:
                print(f"{Fore.RED}✗ No profiles found in {install_dir}.{Style.RESET_ALL}")
                run_spinner("No profiles", 2.0)
                return False

            while True:
                os.system("cls")
                print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
                print(f"{Fore.CYAN} SELECT PROFILE TO UPDATE {Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}\n")
                print(f"{Fore.CYAN}Available profiles:{Style.RESET_ALL}\n")
                for i, profile in enumerate(profiles_info, 1):
                    if profile is None:
                        continue
                    health_color = Fore.GREEN if profile["health"] == "OK" else Fore.RED
                    trans_color = Fore.GREEN if profile["trans_status"] in ["DONE", "EMPTY"] else Fore.RED
                    shift_color = Fore.GREEN if profile["shift_status"] == "CLOSED" else Fore.RED
                    status_text = "ON" if profile["is_running"] else "OFF"
                    status_color = Fore.RED if profile["is_running"] else Fore.GREEN
                    profile_str = (
                        f"| {Fore.YELLOW}FN:{profile['fiscal_number']}{Style.RESET_ALL} "
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
                backup_files = []
                try:
                    if os.path.exists(profiles_dir):
                        backup_files = [f for f in os.listdir(profiles_dir) if f.endswith(".zip") and "backup" in f.lower()]
                except Exception as e:
                    print(f"{Fore.RED}✗ Failed to list backups: {e}{Style.RESET_ALL}")

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
                                    run_spinner("Restore completed", 1.0)
                                else:
                                    print(f"{Fore.RED}✗ Restore failed.{Style.RESET_ALL}")
                                    input("Press Enter to continue...")
                            else:
                                print(f"{Fore.RED}✗ Target directory not found for backup.{Style.RESET_ALL}")
                                run_spinner("Directory not found", 2.0)
                        else:
                            print(f"{Fore.RED}✗ Invalid backup selection.{Style.RESET_ALL}")
                            run_spinner("Invalid selection", 2.0)
                    except ValueError:
                        print(f"{Fore.RED}✗ Invalid backup input.{Style.RESET_ALL}")
                        run_spinner("Invalid input", 2.0)
                    except Exception as e:
                        print(f"{Fore.RED}✗ Restore error: {e}{Style.RESET_ALL}")
                        run_spinner("Restore error", 2.0)
                    continue

                if choice.lower().startswith("d") and len(choice) > 1:
                    try:
                        backup_idx = int(choice[1:]) - 1
                        if 0 <= backup_idx < len(backup_files):
                            backup_path = os.path.join(profiles_dir, backup_files[backup_idx])
                            if delete_backup(backup_path):
                                print(f"{Fore.GREEN}✓ Backup deleted.{Style.RESET_ALL}")
                                run_spinner("Backup deleted", 1.0)
                            else:
                                print(f"{Fore.RED}✗ Failed to delete backup.{Style.RESET_ALL}")
                                input("Press Enter to continue...")
                        else:
                            print(f"{Fore.RED}✗ Invalid delete selection.{Style.RESET_ALL}")
                            run_spinner("Invalid selection", 2.0)
                    except ValueError:
                        print(f"{Fore.RED}✗ Invalid delete input.{Style.RESET_ALL}")
                        run_spinner("Invalid input", 2.0)
                    except Exception as e:
                        print(f"{Fore.RED}✗ Delete error: {e}{Style.RESET_ALL}")
                        run_spinner("Delete error", 2.0)
                    continue

                try:
                    choice_int = int(choice)
                    if choice_int == 0:
                        print(f"{Fore.GREEN}✓ Returning to previous menu...{Style.RESET_ALL}")
                        run_spinner("Returning", 1.0)
                        return False
                    elif 1 <= choice_int <= len(profiles_info):
                        selected_profile = profiles_info[choice_int - 1]
                        if selected_profile is None:
                            print(f"{Fore.RED}✗ Selected profile is invalid.{Style.RESET_ALL}")
                            run_spinner("Invalid profile", 2.0)
                            continue
                        if selected_profile["health"] == "BAD":
                            print(f"{Fore.RED}✗ Cannot update {selected_profile['name']}: Database corrupted.{Style.RESET_ALL}")
                            run_spinner("Update cancelled", 2.0)
                            continue
                        target_dirs = [selected_profile["path"]]
                        break
                    elif choice_int == len(profiles_info) + 1:
                        valid_profiles = [p for p in profiles_info if p is not None and p["health"] != "BAD"]
                        if not valid_profiles:
                            print(f"{Fore.RED}✗ No valid profiles available for update.{Style.RESET_ALL}")
                            run_spinner("Update cancelled", 2.0)
                            return False
                        target_dirs = [profile["path"] for profile in valid_profiles]
                        break
                    else:
                        print(f"{Fore.RED}✗ Invalid choice.{Style.RESET_ALL}")
                        run_spinner("Invalid choice", 2.0)
                except ValueError:
                    print(f"{Fore.RED}✗ Invalid input.{Style.RESET_ALL}")
                    run_spinner("Invalid input", 2.0)

            for target_dir in target_dirs:
                choice = input(
                    f"{Fore.CYAN}Create backup of {os.path.basename(target_dir)} before updating? (Y/N): {Style.RESET_ALL}").strip().lower()
                if choice == "y":
                    backup_path = create_backup(target_dir)
                    if not backup_path:
                        print(f"{Fore.RED}✗ Backup failed. Continuing without backup...{Style.RESET_ALL}")
                        run_spinner("Backup failed", 2.0)
                else:
                    print(f"{Fore.GREEN}✓ Backup skipped.{Style.RESET_ALL}")

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
                        confirm = input(f"{Fore.CYAN}Terminate checkbox_kasa.exe (PID: {proc.pid})? (Y/N): {Style.RESET_ALL}").strip().lower()
                        if confirm == "y":
                            try:
                                proc.terminate()
                                print(f"{Fore.GREEN}✓ Terminated checkbox_kasa.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                                run_spinner("Process terminated", 1.0)
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                print(f"{Fore.RED}✗ Failed to terminate checkbox_kasa.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                    time.sleep(1)
                else:
                    print(f"{Fore.RED}✗ Update cancelled.{Style.RESET_ALL}")
                    run_spinner("Update cancelled", 2.0)
                    return False

                if manager_running:
                    print(f"{Fore.YELLOW}Pausing manager processes...{Style.RESET_ALL}")
                    for proc in manager_processes:
                        try:
                            proc.suspend()
                            print(f"{Fore.GREEN}✓ Paused kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                            run_spinner("Process paused", 1.0)
                        except psutil.NoSuchProcess:
                            pass
                        except Exception:
                            print(f"{Fore.RED}✗ Failed to pause kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
            elif manager_running:
                print(f"{Fore.YELLOW}Cash register not running, manager running - proceeding...{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}No cash register or manager processes found, proceeding...{Style.RESET_ALL}")

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
        print(f"{Fore.CYAN}🔒 Monitoring processes during update...{Style.RESET_ALL}")

        print(f"{Fore.CYAN}📦 Extracting {patch_file_name}...{Style.RESET_ALL}")
        try:
            with zipfile.ZipFile(patch_file_name, 'r') as zip_ref:
                total_files = len(zip_ref.infolist())
                if is_rro_agent and len(target_dirs) > 1:
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
            run_spinner("Permission error", 2.0)
            return False
        except zipfile.BadZipFile:
            print(f"{Fore.RED}✗ Invalid update file.{Style.RESET_ALL}")
            run_spinner("Invalid file", 2.0)
            return False
        except Exception as e:
            print(f"{Fore.RED}✗ Update error: {e}{Style.RESET_ALL}")
            run_spinner("Update error", 2.0)
            return False
        finally:
            stop_monitoring.set()
            for thread in monitor_threads:
                try:
                    thread.join()
                except Exception:
                    pass
            print(f"{Fore.GREEN}✓ Process monitoring stopped.{Style.RESET_ALL}")

        for target_dir in target_dirs:
            try:
                if is_rro_agent:
                    launch_executable("checkbox_kasa.exe", target_dir, "Cash register", spinner_duration=10.0)

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

        if is_rro_agent and cash_running and manager_running and 'manager_processes' in locals():
            print(f"{Fore.YELLOW}Resuming manager processes...{Style.RESET_ALL}")
            for proc in manager_processes:
                try:
                    proc.resume()
                    print(f"{Fore.GREEN}✓ Resumed kasa_manager.exe (PID: {proc.pid}).{Style.RESET_ALL}")
                    run_spinner("Process resumed", 1.0)
                except psutil.NoSuchProcess:
                    print(f"{Fore.YELLOW}⚠ kasa_manager.exe (PID: {proc.pid}) already terminated.{Style.RESET_ALL}")
                except Exception as e:
                    print(f"{Fore.RED}✗ Failed to resume kasa_manager.exe: {e}{Style.RESET_ALL}")

        run_spinner("Update completed", 1.0)
        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Update error: {e}{Style.RESET_ALL}")
        run_spinner("Update error", 2.0)
        return False