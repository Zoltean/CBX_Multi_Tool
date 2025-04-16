# -*- coding: utf-8 -*-
import logging
import sys
import time

import requests
from datetime import datetime
import platform
import psutil
from queue import Queue
from threading import Thread

from config import VPS_CONFIG_URL, VPS_API_URL

class ApiHandler(logging.Handler):
    """
    Обработчик логов для отправки на сервер через API.
    Буферизирует логи и отправляет их пакетами.
    """
    def __init__(self, api_url: str, iteration_id: str):
        super().__init__()
        self.api_url = api_url
        self.iteration_id = iteration_id
        self.buffer = Queue()
        self.max_buffer_size = 10  # Максимальное количество логов в пакете
        self.flush_interval = 5  # Интервал отправки в секундах
        self.running = True
        self.thread = Thread(target=self._flush_buffer)
        self.thread.daemon = True
        self.thread.start()

    def emit(self, record):
        try:
            log_entry = self.format(record)
            self.buffer.put(log_entry)
            if self.buffer.qsize() >= self.max_buffer_size:
                self._send_logs()
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to buffer log: {e}")

    def _flush_buffer(self):
        while self.running:
            if not self.buffer.empty():
                self._send_logs()
            time.sleep(self.flush_interval)

    def _send_logs(self):
        logs = []
        while not self.buffer.empty() and len(logs) < self.max_buffer_size:
            logs.append(self.buffer.get())

        if logs:
            try:
                response = requests.post(
                    f"{self.api_url}/logs",
                    json={"iteration_id": self.iteration_id, "logs": logs},
                    timeout=5
                )
                response.raise_for_status()
                logging.debug(f"Logs sent to server: {len(logs)} entries")
            except requests.RequestException as e:
                logging.error(f"Failed to send logs to server: {e}")

    def close(self):
        self.running = False
        self._send_logs()  # Отправляем оставшиеся логи
        self.thread.join(timeout=2.0)
        super().close()

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
        return {
            "LOG_TO_FILE": config.get("LOG_TO_FILE", False),
            "SEND_LOGS_TO_API": config.get("SEND_LOGS_TO_API", False)
        }
    except requests.RequestException as e:
        temp_logger.error(f"Failed to fetch config: {e}. Using defaults: LOG_TO_FILE=False, SEND_LOGS_TO_API=False")
        return {"LOG_TO_FILE": False, "SEND_LOGS_TO_API": False}
    finally:
        temp_logger.removeHandler(temp_handler)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    logger.handlers.clear()

    iteration_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    config = fetch_config()
    LOG_TO_FILE = True #config["LOG_TO_FILE"]
    SEND_LOGS_TO_API = config["SEND_LOGS_TO_API"]

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

    # Консольный обработчик с utf-8
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1))
    logger.addHandler(console_handler)

    # Обработчик для файла, если включено
    if LOG_TO_FILE:
        try:
            file_handler = logging.FileHandler("cbx.log", encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info("Logging to file 'cbx.log' enabled")
        except Exception as e:
            logger.error(f"Failed to setup file logging: {e}")

    # Обработчик для отправки логов на сервер, если включено
    if SEND_LOGS_TO_API:
        try:
            api_handler = ApiHandler(VPS_API_URL, iteration_id)
            api_handler.setFormatter(formatter)
            logger.addHandler(api_handler)
            logger.info(f"Logging to API {VPS_API_URL} enabled with iteration_id={iteration_id}")
        except Exception as e:
            logger.error(f"Failed to setup API logging: {e}")

    logger.info("System Information:")
    for info_line in system_info:
        logger.info(info_line)

    return logger