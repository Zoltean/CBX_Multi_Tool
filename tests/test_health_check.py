# -*- coding: utf-8 -*-
import os
import shutil
import unittest
import tempfile
import threading
import sys
import json
import sqlite3
from unittest.mock import patch, MagicMock, mock_open
from contextlib import contextmanager

import psutil
import requests
from colorama import Fore, Style

from health_check import (
    find_external_cash_registers_by_processes,
    find_external_cash_registers_by_filesystem,
    find_cash_registers_by_profiles_json,
    get_cash_register_info,
    check_cash_profiles
)
from utils import show_spinner, find_process_by_path, find_all_processes_by_name
from cleanup import cleanup

class TestHealthCheck(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager_dir = os.path.join(self.temp_dir, "checkbox.kasa.manager")
        self.profile_dir = os.path.join(self.manager_dir, "profiles", "profile1")
        os.makedirs(self.profile_dir)
        self.kasa_exe = os.path.join(self.profile_dir, "checkbox_kasa.exe")
        with open(self.kasa_exe, "w") as f:
            f.write("dummy content")
        self.version_file = os.path.join(self.profile_dir, "version")
        with open(self.version_file, "w") as f:
            f.write("1.2.3")
        self.config_json = os.path.join(self.profile_dir, "config.json")
        with open(self.config_json, "w") as f:
            json.dump({"provider": {}, "web_server": {"host": "127.0.0.1", "port": 9200}}, f)
        self.profiles_json = os.path.join(self.manager_dir, "profiles.json")
        with open(self.profiles_json, "w") as f:
            json.dump({"profiles": {"profile1": {"local": {"paths": {"exec_path": self.profile_dir}}}}}, f)
        self.db_path = os.path.join(self.profile_dir, "agent.db")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE cash_register (fiscal_number TEXT);")
        cursor.execute("INSERT INTO cash_register (fiscal_number) VALUES ('1234567890');")
        cursor.execute("CREATE TABLE transactions (status TEXT);")
        cursor.execute("INSERT INTO transactions (status) VALUES ('DONE');")
        cursor.execute("CREATE TABLE shifts (id INTEGER PRIMARY KEY, status TEXT);")
        cursor.execute("INSERT INTO shifts (status) VALUES ('CLOSED');")
        conn.commit()
        conn.close()
        self.data = {"legacy": {}, "dev": {}, "tools": {}}

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @contextmanager
    def mock_sys_exit(self):
        with patch("sys.exit") as mock_exit:
            yield mock_exit

    def test_find_external_cash_registers_by_processes(self):
        mock_proc = MagicMock(pid=123, name=MagicMock(return_value="checkbox_kasa.exe"), cwd=MagicMock(return_value=self.profile_dir))
        with patch("psutil.process_iter", return_value=[mock_proc]):
            result = find_external_cash_registers_by_processes()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["path"], os.path.normpath(self.profile_dir).lower())
            self.assertEqual(result[0]["source"], "process")

    def test_find_external_cash_registers_by_processes_no_processes(self):
        with patch("psutil.process_iter", return_value=[]):
            result = find_external_cash_registers_by_processes()
            self.assertEqual(result, [])

    def test_find_external_cash_registers_by_processes_access_denied(self):
        mock_proc = MagicMock()
        mock_proc.name.side_effect = psutil.AccessDenied("Access denied")
        with patch("psutil.process_iter", return_value=[mock_proc]):
            result = find_external_cash_registers_by_processes()
            self.assertEqual(result, [])

    def test_find_external_cash_registers_by_filesystem(self):
        seen_paths = set()
        result = find_external_cash_registers_by_filesystem(self.manager_dir, seen_paths)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["path"], os.path.normpath(self.profile_dir).lower())
        self.assertEqual(result[0]["source"], "filesystem")
        self.assertIn(os.path.normpath(self.profile_dir).lower(), seen_paths)

    def test_find_external_cash_registers_by_filesystem_no_files(self):
        seen_paths = set()
        empty_dir = os.path.join(self.temp_dir, "empty")
        os.makedirs(empty_dir)
        result = find_external_cash_registers_by_filesystem(empty_dir, seen_paths)
        self.assertEqual(result, [])
        self.assertEqual(seen_paths, set())

    def test_find_external_cash_registers_by_filesystem_duplicate(self):
        seen_paths = {os.path.normpath(self.profile_dir).lower()}
        result = find_external_cash_registers_by_filesystem(self.manager_dir, seen_paths)
        self.assertEqual(result, [])
        self.assertEqual(seen_paths, {os.path.normpath(self.profile_dir).lower()})

    def test_find_cash_registers_by_profiles_json(self):
        cash_registers, is_empty, seen_paths = find_cash_registers_by_profiles_json(self.manager_dir)
        self.assertEqual(len(cash_registers), 1)
        self.assertEqual(cash_registers[0]["path"], os.path.normpath(self.profile_dir).lower())
        self.assertEqual(cash_registers[0]["source"], "profiles_json")
        self.assertFalse(is_empty)
        self.assertEqual(seen_paths, {os.path.normpath(self.profile_dir).lower()})

    def test_find_cash_registers_by_profiles_json_empty(self):
        empty_json = os.path.join(self.manager_dir, "profiles.json")
        with open(empty_json, "w") as f:
            json.dump({"profiles": {}}, f)
        cash_registers, is_empty, seen_paths = find_cash_registers_by_profiles_json(self.manager_dir)
        self.assertEqual(cash_registers, [])
        self.assertTrue(is_empty)
        self.assertEqual(seen_paths, set())

    def test_find_cash_registers_by_profiles_json_missing(self):
        os.remove(self.profiles_json)
        cash_registers, is_empty, seen_paths = find_cash_registers_by_profiles_json(self.manager_dir)
        self.assertEqual(cash_registers, [])
        self.assertFalse(is_empty)
        self.assertEqual(seen_paths, set())

    def test_find_cash_registers_by_profiles_json_invalid(self):
        with open(self.profiles_json, "w") as f:
            f.write("invalid json")
        cash_registers, is_empty, seen_paths = find_cash_registers_by_profiles_json(self.manager_dir)
        self.assertEqual(cash_registers, [])
        self.assertFalse(is_empty)
        self.assertEqual(seen_paths, set())

    def test_get_cash_register_info(self):
        result = get_cash_register_info(self.profile_dir, is_external=False)
        self.assertEqual(result["name"], os.path.basename(self.profile_dir))
        self.assertEqual(result["path"], self.profile_dir)
        self.assertEqual(result["health"], "OK")
        self.assertEqual(result["trans_status"], "DONE")
        self.assertEqual(result["shift_status"], "CLOSED")
        self.assertEqual(result["version"], "1.2.3")
        self.assertEqual(result["fiscal_number"], "1234567890")
        self.assertFalse(result["is_running"])
        self.assertFalse(result["is_external"])

    def test_get_cash_register_info_external(self):
        result = get_cash_register_info(self.profile_dir, is_external=True)
        self.assertEqual(result["name"], f"[Ext] {os.path.basename(self.profile_dir)}")
        self.assertTrue(result["is_external"])

    def test_get_cash_register_info_no_db(self):
        os.remove(self.db_path)
        result = get_cash_register_info(self.profile_dir, is_external=False)
        self.assertEqual(result["health"], "BAD")
        self.assertEqual(result["trans_status"], "ERROR")
        self.assertEqual(result["shift_status"], "OPENED")
        self.assertEqual(result["fiscal_number"], "Unknown")

    def test_get_cash_register_info_no_version(self):
        os.remove(self.version_file)
        result = get_cash_register_info(self.profile_dir, is_external=False)
        self.assertEqual(result["version"], "Unknown")

    def test_get_cash_register_info_db_error(self):
        with patch("sqlite3.connect", side_effect=sqlite3.Error("Database error")):
            result = get_cash_register_info(self.profile_dir, is_external=False)
            self.assertEqual(result["health"], "BAD")
            self.assertEqual(result["fiscal_number"], "Unknown")

if __name__ == "__main__":
    unittest.main()