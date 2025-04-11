# -*- coding: utf-8 -*-
import logging
import requests
from datetime import datetime
import platform
import psutil
from colorama import Fore, Style

from config import VPS_LOGS_URL, VPS_CONFIG_URL

class APILogHandler(logging.Handler):
    def __init__(self, api_url: str, iteration_id: str):
        super().__init__()
        self.api_url = api_url
        self.iteration_id = iteration_id
        self.buffer = []

    def emit(self, record):
        log_entry = self.format(record)
        self.buffer.append(log_entry)
        try:
            payload = {"iteration_id": self.iteration_id, "logs": [log_entry]}
            response = requests.post(self.api_url, json=payload, timeout=5)
            response.raise_for_status()
            self.buffer.pop(0)
        except requests.RequestException as e:
            print(f"{Fore.RED}Failed to send log to API in real-time: {e}{Style.RESET_ALL}")

    def flush(self):
        if not self.buffer:
            return
        try:
            payload = {"iteration_id": self.iteration_id, "logs": self.buffer}
            response = requests.post(self.api_url, json=payload, timeout=10)
            response.raise_for_status()
            print(f"{Fore.GREEN}All remaining logs sent to API!{Style.RESET_ALL}")
            self.buffer.clear()
        except requests.RequestException as e:
            print(f"{Fore.RED}Failed to flush logs to API: {e}{Style.RESET_ALL}")

def fetch_config():
    temp_logger = logging.getLogger(__name__)
    temp_logger.setLevel(logging.INFO)
    temp_handler = logging.StreamHandler()
    temp_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    temp_logger.addHandler(temp_handler)

    temp_logger.info(f"Fetching config from {VPS_CONFIG_URL}")
    try:
        response = requests.get(VPS_CONFIG_URL, timeout=5)
        response.raise_for_status()
        config = response.json()
        temp_logger.info(f"Config fetched: {config}")
        return config.get("LOG_TO_FILE", False), config.get("SEND_LOGS_TO_API", True)
    except requests.RequestException as e:
        temp_logger.error(f"Failed to fetch config: {e}. Using defaults: LOG_TO_FILE=False, SEND_LOGS_TO_API=True")
        return False, True
    finally:
        temp_logger.removeHandler(temp_handler)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    logger.handlers.clear()

    iteration_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    LOG_TO_FILE, SEND_LOGS_TO_API = fetch_config()

    system_info = []
    try:
        os_name = platform.system()
        os_version = platform.release()
        os_build = platform.version()
        system_info.append(f"Operating System: {os_name} {os_version} (Build {os_build})")
        cpu_info = platform.processor() or "Unknown CPU"
        cpu_cores = psutil.cpu_count(logical=False) or "?"
        cpu_threads = psutil.cpu_count(logical=True) or "?"
        system_info.append(f"Processor: {cpu_info}, {cpu_cores} cores, {cpu_threads} threads")
        ram = psutil.virtual_memory()
        total_ram = ram.total / (1024 ** 3)
        system_info.append(f"RAM: {total_ram:.2f} GB total")
    except Exception as e:
        system_info.append(f"Failed to gather system info: {str(e)}")

    if LOG_TO_FILE:
        try:
            file_handler = logging.FileHandler("cbx.log", encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info("Logging to file 'cbx.log' enabled")
        except Exception as e:
            logger.error(f"Failed to setup file logging: {e}")

    api_handler = None
    if SEND_LOGS_TO_API:
        try:
            api_handler = APILogHandler(VPS_LOGS_URL, iteration_id)
            api_handler.setFormatter(formatter)
            logger.addHandler(api_handler)
            logger.info(f"Logging to API enabled with iteration ID: {iteration_id}")
        except Exception as e:
            logger.error(f"Failed to setup API logging: {e}")

    logger.info("System Information:")
    for info_line in system_info:
        logger.info(info_line)

    return api_handler