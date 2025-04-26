import ctypes
import json
import os
import time
import threading
import itertools
import sys
import subprocess
from typing import List, Optional, Dict, Tuple
import psutil
from colorama import Fore, Style


def run_spinner(message: str, duration: float = 2.0) -> None:
    """
    Запускає анімований спінер із повідомленням на заданий час.

    Args:
        message (str): Повідомлення, яке відображається поряд зі спінером.
        duration (float): Тривалість роботи спінера в секундах.
    """
    stop_event = threading.Event()
    spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, message))
    spinner_thread.start()
    time.sleep(duration)
    stop_event.set()
    spinner_thread.join()

def show_spinner(stop_event: threading.Event, message: str = "Processing") -> None:
    """
    Відображає анімований спінер у консолі до отримання сигналу зупинки.

    Args:
        stop_event (threading.Event): Подія для зупинки спінера.
        message (str): Повідомлення, яке відображається поряд зі спінером.
    """
    spinner = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
    while not stop_event.is_set():
        sys.stdout.write(f"\r{Fore.CYAN}{message} {next(spinner)}{Style.RESET_ALL}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write(f"\r{Fore.GREEN}✓ {message} completed!{Style.RESET_ALL}\n")
    sys.stdout.flush()


def manage_process_lifecycle(
        process_names: List[str],
        target_dirs: List[str],
        action: str = "terminate",
        prompt: bool = True,
        spinner_message: Optional[str] = None,
        spinner_duration: float = 1.0
) -> bool:
    """
    Керує життєвим циклом процесів: зупиняє, призупиняє або відновлює їх.

    Args:
        process_names (List[str]): Список імен процесів для обробки.
        target_dirs (List[str]): Список директорій для перевірки процесів.
        action (str): Дія для виконання ('terminate', 'suspend', 'resume'). За замовчуванням 'terminate'.
        prompt (bool): Чи запитувати підтвердження у користувача. За замовчуванням True.
        spinner_message (Optional[str]): Повідомлення для спінера. Якщо None, спінер не відображається.
        spinner_duration (float): Тривалість роботи спінера в секундах. За замовчуванням 1.0.

    Returns:
        bool: True, якщо операція успішна, False у разі помилки.

    Raises:
        psutil.TimeoutExpired: Якщо процес не завершився вчасно.
        psutil.NoSuchProcess: Якщо процес не існує.
        psutil.AccessDenied: Якщо відсутні права доступу до процесу.
        Exception: Інші непередбачені помилки.
    """
    success = True
    for target_dir in target_dirs:
        for proc_name in process_names:
            process = find_process_by_path(proc_name, target_dir)
            if not process:
                continue

            if prompt:
                confirm = input(
                    f"{Fore.CYAN}{action.capitalize()} {proc_name} (PID: {process.pid})? (Y/N): {Style.RESET_ALL}"
                ).strip().lower()
                if confirm != "y":
                    print(f"{Fore.RED}✗ Operation cancelled for {proc_name}.{Style.RESET_ALL}")
                    return False

            try:
                if action == "terminate":
                    process.terminate()
                    process.wait(timeout=5)
                    print(f"{Fore.GREEN}✓ Terminated {proc_name} (PID: {process.pid}).{Style.RESET_ALL}")
                elif action == "suspend":
                    process.suspend()
                    print(f"{Fore.GREEN}✓ Suspended {proc_name} (PID: {process.pid}).{Style.RESET_ALL}")
                elif action == "resume":
                    process.resume()
                    print(f"{Fore.GREEN}✓ Resumed {proc_name} (PID: {process.pid}).{Style.RESET_ALL}")
            except psutil.TimeoutExpired:
                if action == "terminate":
                    process.terminate()
                    print(f"{Fore.GREEN}✓ Force terminated {proc_name} (PID: {process.pid}).{Style.RESET_ALL}")
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                print(f"{Fore.RED}✗ Failed to {action} {proc_name}: {e}{Style.RESET_ALL}")
                success = False
            except Exception as e:
                print(f"{Fore.RED}✗ Error during {action} of {proc_name}: {e}{Style.RESET_ALL}")
                success = False

    if spinner_message:
        run_spinner(spinner_message, spinner_duration)

    return success


def read_json_file(file_path: str) -> Optional[Dict]:
    """
    Читає JSON-файл із обробкою помилок.

    Args:
        file_path (str): Шлях до JSON-файлу.

    Returns:
        Optional[Dict]: Словник із даними або None у разі помилки.

    Raises:
        json.JSONDecodeError: Якщо файл містить некоректний JSON.
        Exception: Інші помилки, такі як відсутність файлу або проблеми з доступом.
    """
    file_path = os.path.normpath(os.path.abspath(file_path))
    if not os.path.exists(file_path):
        print(f"{Fore.RED}✗ File not found: {file_path}{Style.RESET_ALL}")
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"{Fore.RED}✗ Error reading JSON {file_path}: {e}{Style.RESET_ALL}")
        return None
    except Exception as e:
        print(f"{Fore.RED}✗ Error accessing {file_path}: {e}{Style.RESET_ALL}")
        return None


def write_json_file(file_path: str, data: Dict, indent: int = 4) -> bool:
    """
    Записує дані у JSON-файл із форматуванням.

    Args:
        file_path (str): Шлях до файлу для запису.
        data (Dict): Дані для запису у форматі словника.
        indent (int): Рівень відступу для форматування JSON. За замовчуванням 4.

    Returns:
        bool: True, якщо запис успішний, False у разі помилки.

    Raises:
        Exception: Помилки, такі як відсутність прав доступу або проблеми з файловою системою.
    """
    file_path = os.path.normpath(os.path.abspath(file_path))
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        print(f"{Fore.GREEN}✓ Successfully wrote {file_path}{Style.RESET_ALL}")
        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Error writing {file_path}: {e}{Style.RESET_ALL}")
        return False


def check_write_permissions(directory: str) -> bool:
    """
    Перевіряє наявність прав запису в указану директорію.

    Args:
        directory (str): Шлях до директорії для перевірки.

    Returns:
        bool: True, якщо є права запису, False у разі помилки.

    Raises:
        PermissionError: Якщо відсутні права запису.
        Exception: Інші помилки, пов’язані з доступом до файлової системи.
    """
    directory = os.path.normpath(os.path.abspath(directory))
    try:
        test_file = os.path.join(directory, "test_access.tmp")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except PermissionError:
        print(f"{Fore.RED}✗ No write permissions for {directory}. Run as admin.{Style.RESET_ALL}")
        return False
    except Exception as e:
        print(f"{Fore.RED}✗ Permission check failed for {directory}: {e}{Style.RESET_ALL}")
        return False


def launch_executable(
        executable_name: str,
        target_dir: str,
        display_name: str,
        spinner_duration: float = 2.0,
        shell: bool = False,
        command: Optional[str] = None
) -> bool:
    """
    Запускає виконуваний файл із підтримкою різних режимів запуску.

    Args:
        executable_name (str): Ім’я виконуваного файлу.
        target_dir (str): Директорія, де розташований файл.
        display_name (str): Назва для відображення в повідомленнях.
        spinner_duration (float): Тривалість роботи спінера в секундах. За замовчуванням 2.0.
        shell (bool): Чи використовувати shell-режим для запуску. За замовчуванням False.
        command (Optional[str]): Кастомна команда для запуску. Якщо None, формується стандартна.

    Returns:
        bool: True, якщо запуск успішний, False у разі помилки.

    Raises:
        Exception: Помилки, такі як відсутність файлу або проблеми з запуском процесу.
    """
    executable_path = os.path.normpath(os.path.join(target_dir, executable_name))
    if not os.path.exists(executable_path):
        print(f"{Fore.YELLOW}⚠ {executable_name} not found.{Style.RESET_ALL}")
        return False

    try:
        print(f"{Fore.CYAN}🚀 Launching {display_name.lower()}...{Style.RESET_ALL}")
        cmd = command or f'start "" "{executable_path}"'
        subprocess.Popen(cmd, cwd=target_dir, shell=shell)
        print(f"{Fore.GREEN}✓ {display_name} launched successfully!{Style.RESET_ALL}")
        run_spinner(f"{display_name} launched", spinner_duration)
        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to launch {display_name.lower()}: {e}{Style.RESET_ALL}")
        run_spinner(f"Failed to launch {display_name.lower()}", 2.0)
        return False


def display_list_and_choose(
        title: str,
        items: List[Dict],
        display_key: str,
        options: Dict[str, str] = None,
        parent_menu: Optional[Dict] = None
) -> Optional[Tuple[int, Dict]]:
    """
    Відображає список елементів і дозволяє користувачу зробити вибір.

    Args:
        title (str): Заголовок меню.
        items (List[Dict]): Список елементів для відображення.
        display_key (str): Ключ для відображення назви елемента.
        options (Dict[str, str]): Додаткові опції меню (наприклад, '0': 'Назад'). За замовчуванням None.
        parent_menu (Optional[Dict]): Дані батьківського меню для повернення. За замовчуванням None.

    Returns:
        Optional[Tuple[int, Dict]]: Кортеж із індексом вибраного елемента та самим елементом, або None.

    Raises:
        ValueError: Якщо введено некоректний вибір.
    """
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{title.center(50)}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}\n")

        for i, item in enumerate(items, 1):
            print(f"{Fore.WHITE}{i}. {item[display_key]}{Style.RESET_ALL}")

        print(f"\n{Fore.WHITE}=== Options ==={Style.RESET_ALL}")
        if options:
            for key, value in options.items():
                print(f"{Fore.WHITE}{key}. {value}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

        choice = input(f"{Fore.CYAN}Enter your choice: {Style.RESET_ALL}").strip()

        if options and choice.upper() in options:
            return choice.upper(), None

        try:
            choice_int = int(choice)
            if 1 <= choice_int <= len(items):
                return choice_int - 1, items[choice_int - 1]
            elif choice_int == 0 and parent_menu:
                return 0, None
            else:
                print(f"{Fore.RED}✗ Invalid choice!{Style.RESET_ALL}")
                run_spinner("Invalid choice", 2.0)
        except ValueError:
            print(f"{Fore.RED}✗ Invalid input!{Style.RESET_ALL}")
            run_spinner("Invalid input", 2.0)

def is_admin() -> bool:
    """
    Перевіряє, чи програма запущена з правами адміністратора.

    Returns:
        bool: True, якщо програма має права адміністратора, False інакше.

    Raises:
        Exception: Помилки, пов’язані з перевіркою прав доступу.
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def find_process_by_path(process_name: str, target_path: str) -> Optional[psutil.Process]:
    """
    Знаходить процес за ім’ям і шляхом до виконуваного файлу.

    Args:
        process_name (str): Ім’я процесу (наприклад, 'checkbox_kasa.exe').
        target_path (str): Шлях до директорії, де розташований процес.

    Returns:
        Optional[psutil.Process]: Об’єкт процесу, якщо знайдено, або None.

    Raises:
        Exception: Помилки, пов’язані з доступом до процесів або їх пошуком.
    """
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
    """
    Знаходить усі процеси за їх ім’ям.

    Args:
        process_name (str): Ім’я процесу для пошуку.

    Returns:
        List[psutil.Process]: Список знайдених процесів.

    Raises:
        Exception: Помилки, пов’язані з переглядом процесів.
    """
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
    """
    Керує процесами: завершує їх із можливістю підтвердження користувачем.

    Args:
        processes_to_kill (List[str]): Список імен процесів для завершення.
        target_dirs (List[str]): Список директорій для перевірки процесів.
        stop_event (Optional[threading.Event]): Подія для зупинки моніторингу. За замовчуванням None.

    Returns:
        bool: True, якщо операція успішна, False у разі помилки.

    Raises:
        Exception: Помилки, пов’язані з завершенням процесів або доступом до них.
    """
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
                                    run_spinner("Terminating process", 1.0)
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
                                run_spinner("Terminating process", 1.0)
                            except psutil.NoSuchProcess:
                                pass
                            except Exception:
                                print(f"{Fore.RED}✗ Failed to terminate {proc_name}.{Style.RESET_ALL}")
        return True
    except Exception:
        print(f"{Fore.RED}✗ Error managing processes.{Style.RESET_ALL}")
        return False


def launch_executable(
        executable_name: str,
        target_dir: str,
        display_name: str,
        spinner_duration: float = 2.0,
        shell: bool = True,
        command: Optional[str] = None
) -> bool:

    executable_path = os.path.normpath(os.path.join(target_dir, executable_name))
    if not os.path.exists(executable_path):
        print(f"{Fore.YELLOW}⚠ {executable_name} not found.{Style.RESET_ALL}")
        return False

    try:
        print(f"{Fore.CYAN}🚀 Launching {display_name.lower()}...{Style.RESET_ALL}")
        cmd = command or f'start "" "{executable_path}"'
        subprocess.Popen(cmd, cwd=target_dir, shell=shell)
        print(f"{Fore.GREEN}✓ {display_name} launched successfully!{Style.RESET_ALL}")
        run_spinner(f"{display_name} launched", spinner_duration)
        return True
    except Exception as e:
        print(f"{Fore.RED}✗ Failed to launch {display_name.lower()}: {e}{Style.RESET_ALL}")
        run_spinner(f"Failed to launch {display_name.lower()}", 2.0)
        return False