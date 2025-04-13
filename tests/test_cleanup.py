# -*- coding: utf-8 -*-
import os
import unittest
import tempfile
import threading
import sys
import shutil
from unittest.mock import patch, MagicMock, mock_open
from contextlib import contextmanager

import psutil
from colorama import Fore, Style

from cleanup import cleanup  # Замените на имя модуля, где находится cleanup
from utils import find_all_processes_by_name, show_spinner

class TestCleanup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.sample_file = os.path.join(self.temp_dir, "test.exe")
        with open(self.sample_file, "w") as f:
            f.write("dummy content")
        self.sample_patch = os.path.join(self.temp_dir, "patch.exe")
        with open(self.sample_patch, "w") as f:
            f.write("dummy patch content")
        self.data = {
            "legacy": {
                "item1": {"name": self.sample_file, "patch_name": self.sample_patch}
            },
            "dev": {
                "item2": {"name": os.path.join(self.temp_dir, "dev.exe"), "patch_name": os.path.join(self.temp_dir, "dev_patch.exe")}
            },
            "tools": {
                "item3": {"name": os.path.join(self.temp_dir, "tool.exe"), "patch_name": ""}
            }
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @contextmanager
    def mock_sys_exit(self):
        with patch("sys.exit") as mock_exit:
            yield mock_exit

    def test_cleanup_file_permission_error(self):
        with self.mock_sys_exit() as mock_exit, \
             patch("os.path.exists", side_effect=lambda x: x in [self.sample_file, self.sample_patch]), \
             patch("os.remove", side_effect=PermissionError("Permission denied")), \
             patch("utils.find_all_processes_by_name", return_value=[]), \
             patch("subprocess.Popen") as mock_popen, \
             patch("builtins.open", mock_open()) as mock_file:
            cleanup(self.data)
            self.assertTrue(mock_popen.called)
            mock_file.assert_called_once()
            mock_exit.assert_called_with(0)

    def test_cleanup_non_existent_file(self):
        with self.mock_sys_exit() as mock_exit, \
             patch("os.path.exists", return_value=False), \
             patch("os.remove") as mock_remove, \
             patch("utils.find_all_processes_by_name", return_value=[]), \
             patch("subprocess.Popen") as mock_popen, \
             patch("builtins.open", mock_open()) as mock_file:
            cleanup(self.data)
            mock_remove.assert_not_called()
            mock_popen.assert_called_once()
            mock_file.assert_called_once()
            mock_exit.assert_called_with(0)

    def test_cleanup_empty_data(self):
        with self.mock_sys_exit() as mock_exit, \
             patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove, \
             patch("utils.find_all_processes_by_name", return_value=[]), \
             patch("subprocess.Popen") as mock_popen, \
             patch("builtins.open", mock_open()) as mock_file:
            cleanup({})
            mock_remove.assert_not_called()
            mock_popen.assert_called_once()
            mock_file.assert_called_once()
            mock_exit.assert_called_with(0)

    def test_cleanup_invalid_data(self):
        invalid_data = {
            "legacy": {"item1": {"name": "", "patch_name": ""}},
            "dev": {"item2": {"name": "", "patch_name": ""}},
            "tools": {"item3": {"name": "", "patch_name": ""}}
        }
        with self.mock_sys_exit() as mock_exit, \
             patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove, \
             patch("utils.find_all_processes_by_name", return_value=[]), \
             patch("subprocess.Popen") as mock_popen, \
             patch("builtins.open", mock_open()) as mock_file:
            cleanup(invalid_data)
            mock_remove.assert_not_called()
            mock_popen.assert_called_once()
            mock_file.assert_called_once()
            mock_exit.assert_called_with(0)

if __name__ == "__main__":
    unittest.main()