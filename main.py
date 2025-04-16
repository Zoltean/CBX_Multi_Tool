# -*- coding: utf-8 -*-
import atexit
import os
import time
import threading
import platform
from colorama import init, Fore, Style

from config import PROGRAM_TITLE, VPS_API_URL, VPS_CONFIG_URL
from network import check_for_updates, fetch_json
from menu import display_menu
from utils import is_admin, show_spinner
from cleanup import cleanup

init()

def main():
    print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}")
    print(f"{Fore.CYAN} Welcome to {PROGRAM_TITLE} {Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 40}{Style.RESET_ALL}\n")

    try:
        if not is_admin():
            print(f"{Fore.YELLOW}⚠ Please run as administrator for full functionality.{Style.RESET_ALL}")
            stop_event = threading.Event()
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Checking permissions"))
            spinner_thread.start()
            time.sleep(3)
            stop_event.set()
            spinner_thread.join()
        else:
            print(f"{Fore.GREEN}✓ Admin privileges confirmed.{Style.RESET_ALL}")

        update_available, download_url, sha256 = check_for_updates()

        data = fetch_json(VPS_API_URL)

        if not data:
            print(f"{Fore.RED}✗ Failed to connect to server. Please check your internet.{Style.RESET_ALL}")
            input("\nPress Enter to exit...")
            return

        menu_options = {
            "legacy": {
                "kasa_manager": data["legacy"]["kasa_manager"],
                "rro_agent": data["legacy"]["rro_agent"]
            },
            "dev": {
                "kasa_manager": data["dev"]["kasa_manager"],
                "rro_agent": data["dev"]["rro_agent"],
                "paylink": data["dev"]["paylink"]
            },
            "cloudlike": {
                "cloudlike": data["legacy"]["cloudlike"]
            },
            "patching": {
                "legacy": {
                    "kasa_manager": [
                        {
                            "patch_name": item["patch_name"],
                            "patch_url": item["patch_url"],
                            "sha256": item.get("patch_sha256", "")
                        }
                        for item in data["legacy"]["kasa_manager"]
                        if "patch_name" in item and "patch_url" in item
                    ],
                    "rro_agent": [
                        {
                            "patch_name": item["patch_name"],
                            "patch_url": item["patch_url"],
                            "sha256": item.get("patch_sha256", "")
                        }
                        for item in data["legacy"]["rro_agent"]
                        if "patch_name" in item and "patch_url" in item
                    ]
                },
                "dev": {
                    "kasa_manager": [
                        {
                            "patch_name": item["patch_name"],
                            "patch_url": item["patch_url"],
                            "sha256": item.get("patch_sha256", "")
                        }
                        for item in data["dev"]["kasa_manager"]
                        if "patch_name" in item and "patch_url" in item
                    ],
                    "rro_agent": [
                        {
                            "patch_name": item["patch_name"],
                            "patch_url": item["patch_url"],
                            "sha256": item.get("patch_sha256", "")
                        }
                        for item in data["dev"]["rro_agent"]
                        if "patch_name" in item and "patch_url" in item
                    ],
                    "paylink": [
                        {
                            "patch_name": item["patch_name"],
                            "patch_url": item["patch_url"],
                            "sha256": item.get("patch_sha256", "")
                        }
                        for item in data["dev"]["paylink"]
                        if "patch_name" in item and "patch_url" in item
                    ]
                }
            },
            "tools": {
                "paylink": {
                    "terminal_drivers": data["tools"]["paylink"]["terminal_drivers"],
                    "os_tools": data["tools"]["paylink"]["os_tools"]
                },
                "rro_agent_tools": {
                    "diagnostics": data["tools"]["rro_agent_tools"]["diagnostics"],
                    "config_tools": data["tools"]["rro_agent_tools"]["config_tools"]
                }
            },
        }

        display_menu("Main Menu", menu_options, data,
                     update_available=update_available, download_url=download_url, sha256=sha256)

        print(f"{Fore.GREEN}✓ Program completed successfully!{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}✗ Error: {e}{Style.RESET_ALL}")
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()