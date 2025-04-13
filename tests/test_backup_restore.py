import os
import time
import unittest
import zipfile
import shutil
import tempfile
import threading
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open
from contextlib import contextmanager
from typing import List, Optional

import psutil
from colorama import Fore, Style

from backup_restore import create_backup, delete_backup, restore_from_backup
from utils import show_spinner, is_admin, find_process_by_path, find_all_processes_by_name, manage_processes

class TestBackupRestoreUtils(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.target_dir = os.path.join(self.temp_dir, "test_dir")
        os.makedirs(self.target_dir)
        self.backup_path = os.path.join(self.temp_dir, "backup.zip")
        self.sample_file = os.path.join(self.target_dir, "sample.txt")
        with open(self.sample_file, "w") as f:
            f.write("Test content")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @contextmanager
    def mock_zipfile(self, fail=False, empty=False):
        mock_zip = MagicMock()
        if fail:
            mock_zip.__enter__.side_effect = Exception("Zip write error")
        elif empty:
            mock_zip.infolist.return_value = []
        else:
            mock_zip.write = MagicMock()
            mock_zip.infolist.return_value = [MagicMock()]
            mock_zip.extract = MagicMock()
        with patch("zipfile.ZipFile", return_value=mock_zip) as mock_zipfile:
            yield mock_zipfile

    @contextmanager
    def mock_os_walk(self, files=None):
        files = files or [(self.target_dir, [], ["sample.txt"])]
        with patch("os.walk", return_value=files) as mock_walk:
            yield mock_walk

    @contextmanager
    def mock_tqdm(self):
        with patch("tqdm.tqdm", return_value=MagicMock()) as mock_progress:
            yield mock_progress

    def test_create_backup_success(self):
        with self.mock_zipfile(), self.mock_os_walk(), self.mock_tqdm():
            result = create_backup(self.target_dir)
            self.assertIsNotNone(result)
            self.assertTrue(result.endswith(".zip"))
            self.assertIn("backup", result)
            self.assertIn(datetime.now().strftime("%Y%m%d"), result)

    def test_create_backup_empty_directory(self):
        empty_dir = os.path.join(self.temp_dir, "empty_dir")
        os.makedirs(empty_dir)
        with self.mock_zipfile(), self.mock_os_walk(files=[(empty_dir, [], [])]), self.mock_tqdm():
            result = create_backup(empty_dir)
            self.assertIsNotNone(result)
            self.assertTrue(result.endswith(".zip"))

    def test_create_backup_zipfile_error(self):
        with self.mock_zipfile(fail=True), self.mock_os_walk(), self.mock_tqdm():
            result = create_backup(self.target_dir)
            self.assertIsNone(result)

    def test_create_backup_permission_denied(self):
        with patch("os.walk", side_effect=PermissionError("Permission denied")):
            result = create_backup(self.target_dir)
            self.assertIsNone(result)

    def test_create_backup_invalid_directory(self):
        invalid_dir = os.path.join(self.temp_dir, "nonexistent")
        with patch("os.walk", side_effect=FileNotFoundError("Directory not found")):
            with self.mock_zipfile(fail=True), self.mock_tqdm():
                result = create_backup(invalid_dir)
                self.assertIsNone(result)

    def test_create_backup_disk_full(self):
        with self.mock_zipfile(fail=True), self.mock_os_walk(), self.mock_tqdm():
            with patch("os.walk", side_effect=OSError("Disk full")):
                result = create_backup(self.target_dir)
                self.assertIsNone(result)

    def test_create_backup_many_files(self):
        many_files = [(self.target_dir, [], [f"file_{i}.txt" for i in range(1000)])]
        with self.mock_zipfile(), self.mock_os_walk(files=many_files), self.mock_tqdm():
            result = create_backup(self.target_dir)
            self.assertIsNotNone(result)

    def test_delete_backup_success(self):
        with patch("os.remove") as mock_remove:
            result = delete_backup(self.backup_path)
            mock_remove.assert_called_once_with(self.backup_path)
            self.assertTrue(result)

    def test_delete_backup_file_not_found(self):
        with patch("os.remove", side_effect=FileNotFoundError("File not found")):
            result = delete_backup(self.backup_path)
            self.assertFalse(result)

    def test_delete_backup_permission_denied(self):
        with patch("os.remove", side_effect=PermissionError("Permission denied")):
            result = delete_backup(self.backup_path)
            self.assertFalse(result)

    def test_delete_backup_read_only(self):
        with patch("os.remove", side_effect=OSError("Read-only file system")):
            result = delete_backup(self.backup_path)
            self.assertFalse(result)

    def test_restore_from_backup_success_no_processes(self):
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path)
                self.assertTrue(result)

    def test_restore_from_backup_stop_process(self):
        mock_process = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=mock_process), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("builtins.input", return_value="y"), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertTrue(result)
                mock_process.kill.assert_called_once()

    def test_restore_from_backup_rro_manager_running(self):
        mock_manager = MagicMock(pid=456, info={"name": "kasa_manager.exe"})
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[mock_manager]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertTrue(result)

    def test_restore_from_backup_cancelled(self):
        mock_process = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=mock_process), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("builtins.input", return_value="n"):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertFalse(result)

    def test_restore_from_backup_clear_directory_failure(self):
        with patch("os.listdir", side_effect=PermissionError("Permission denied")), \
             patch("backup_restore.find_process_by_path", return_value=None), \
             patch("backup_restore.find_all_processes_by_name", return_value=[]):
            result = restore_from_backup(self.target_dir, self.backup_path)
            self.assertFalse(result)

    def test_restore_from_backup_invalid_zip(self):
        with patch("zipfile.ZipFile", side_effect=zipfile.BadZipFile("Invalid zip file")), \
             patch("backup_restore.find_process_by_path", return_value=None), \
             patch("backup_restore.find_all_processes_by_name", return_value=[]), \
             patch("os.listdir", return_value=[]):
            result = restore_from_backup(self.target_dir, self.backup_path)
            self.assertFalse(result)

    def test_restore_from_backup_launch_rro_agent(self):
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("os.path.exists", return_value=True), \
                 patch("subprocess.Popen"), \
                 patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertTrue(result)

    def test_restore_from_backup_launch_paylink(self):
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("os.path.exists", return_value=True), \
                 patch("subprocess.Popen"), \
                 patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_paylink=True)
                self.assertTrue(result)

    def test_restore_from_backup_launch_failure(self):
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("os.path.exists", return_value=True), \
                 patch("subprocess.Popen", side_effect=OSError("Failed to launch")), \
                 patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path)
                self.assertTrue(result)

    def test_restore_from_backup_process_check_exception(self):
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", side_effect=Exception("Process check error")), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path)
                self.assertTrue(result)

    def test_restore_from_backup_manager_check_exception(self):
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", side_effect=Exception("Manager check error")), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertTrue(result)

    def test_restore_from_backup_no_such_process_kill(self):
        mock_process = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        mock_process.kill.side_effect = psutil.NoSuchProcess("Process gone")
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=mock_process), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("builtins.input", return_value="y"), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertTrue(result)
                mock_process.kill.assert_called_once()

    def test_restore_from_backup_no_such_process_suspend(self):
        mock_process = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        mock_manager = MagicMock(pid=456, info={"name": "kasa_manager.exe"})
        mock_manager.suspend.side_effect = psutil.NoSuchProcess("Process gone")
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=mock_process), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[mock_manager]), \
                 patch("builtins.input", return_value="y"), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertTrue(result)
                mock_manager.suspend.assert_called_once()

    def test_restore_from_backup_partial_clear_failure(self):
        with patch("os.remove", side_effect=[None, PermissionError("Permission denied")]), \
             patch("os.listdir", return_value=["file1.txt", "file2.txt"]), \
             patch("backup_restore.find_process_by_path", return_value=None), \
             patch("backup_restore.find_all_processes_by_name", return_value=[]):
            result = restore_from_backup(self.target_dir, self.backup_path)
            self.assertFalse(result)

    def test_restore_from_backup_zip_extraction_permission(self):
        with self.mock_zipfile(fail=True), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path)
                self.assertFalse(result)

    def test_restore_from_backup_invalid_executable(self):
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("os.path.exists", return_value=True), \
                 patch("subprocess.Popen", side_effect=OSError("Invalid executable")), \
                 patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertTrue(result)

    def test_restore_from_backup_multiple_processes(self):
        mock_process1 = MagicMock(pid=123, info={"name": "CheckboxPayLink.exe"})
        mock_process2 = MagicMock(pid=124, info={"name": "POSServer.exe"})
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", side_effect=[mock_process1, mock_process2]), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("builtins.input", return_value="y"), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_paylink=True)
                self.assertTrue(result)
                mock_process1.kill.assert_called_once()
                mock_process2.kill.assert_called_once()

    def test_restore_from_backup_empty_zip(self):
        with self.mock_zipfile(empty=True), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=None), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path)
                self.assertTrue(result)

    def test_restore_from_backup_case_insensitive_input(self):
        mock_process = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=mock_process), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("builtins.input", return_value="Y"), \
                 patch("os.listdir", return_value=[]):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertTrue(result)

    def test_restore_from_backup_invalid_input(self):
        mock_process = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        with self.mock_zipfile(), self.mock_tqdm():
            with patch("backup_restore.find_process_by_path", return_value=mock_process), \
                 patch("backup_restore.find_all_processes_by_name", return_value=[]), \
                 patch("builtins.input", return_value="x"):
                result = restore_from_backup(self.target_dir, self.backup_path, is_rro_agent=True)
                self.assertFalse(result)

    def test_show_spinner_success(self):
        stop_event = threading.Event()
        with patch("sys.stdout") as mock_stdout:
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, "Test"))
            spinner_thread.start()
            time.sleep(0.1)
            stop_event.set()
            spinner_thread.join()
            mock_stdout.write.assert_called()
            mock_stdout.flush.assert_called()

    def test_show_spinner_empty_message(self):
        stop_event = threading.Event()
        with patch("sys.stdout") as mock_stdout:
            spinner_thread = threading.Thread(target=show_spinner, args=(stop_event, ""))
            spinner_thread.start()
            time.sleep(0.1)
            stop_event.set()
            spinner_thread.join()
            mock_stdout.write.assert_called()
            mock_stdout.flush.assert_called()

    def test_show_spinner_no_output(self):
        stop_event = threading.Event()
        stop_event.set()
        with patch("sys.stdout") as mock_stdout:
            show_spinner(stop_event, "Test")
            mock_stdout.write.assert_called_once()
            mock_stdout.flush.assert_called_once()

    def test_is_admin_true(self):
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1):
            result = is_admin()
            self.assertTrue(result)

    def test_is_admin_false(self):
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0):
            result = is_admin()
            self.assertFalse(result)

    def test_is_admin_exception(self):
        with patch("ctypes.windll.shell32.IsUserAnAdmin", side_effect=Exception("Access error")):
            result = is_admin()
            self.assertFalse(result)

    def test_find_process_by_path_success(self):
        mock_proc = MagicMock(pid=123, info={"name": "checkbox_kasa.exe", "exe": os.path.join(self.target_dir, "checkbox_kasa.exe")})
        with patch("psutil.process_iter", return_value=[mock_proc]):
            with patch("os.path.realpath", side_effect=lambda x: x):
                result = find_process_by_path("checkbox_kasa.exe", self.target_dir)
                self.assertEqual(result, mock_proc)

    def test_find_process_by_path_no_match(self):
        mock_proc = MagicMock(pid=123, info={"name": "other.exe", "exe": os.path.join(self.temp_dir, "other.exe")})
        with patch("psutil.process_iter", return_value=[mock_proc]):
            result = find_process_by_path("checkbox_kasa.exe", self.target_dir)
            self.assertIsNone(result)

    def test_find_process_by_path_access_denied(self):
        mock_proc = MagicMock(pid=123, info={"name": "checkbox_kasa.exe", "exe": None})
        with patch("psutil.process_iter", return_value=[mock_proc]):
            result = find_process_by_path("checkbox_kasa.exe", self.target_dir)
            self.assertIsNone(result)

    def test_find_process_by_path_no_such_process(self):
        mock_proc = MagicMock(pid=123, info={"name": "checkbox_kasa.exe", "exe": None})
        with patch("psutil.process_iter", return_value=[mock_proc]):
            result = find_process_by_path("checkbox_kasa.exe", self.target_dir)
            self.assertIsNone(result)

    def test_find_process_by_path_exception(self):
        with patch("psutil.process_iter", side_effect=Exception("Process error")):
            result = find_process_by_path("checkbox_kasa.exe", self.target_dir)
            self.assertIsNone(result)

    def test_find_process_by_path_empty_name(self):
        with patch("psutil.process_iter", return_value=[]):
            result = find_process_by_path("", self.target_dir)
            self.assertIsNone(result)

    def test_find_process_by_path_case_insensitive(self):
        mock_proc = MagicMock(pid=123, info={"name": "CHECKBOX_KASA.EXE", "exe": os.path.join(self.target_dir, "checkbox_kasa.exe")})
        with patch("psutil.process_iter", return_value=[mock_proc]):
            with patch("os.path.realpath", side_effect=lambda x: x):
                result = find_process_by_path("checkbox_kasa.exe", self.target_dir)
                self.assertEqual(result, mock_proc)

    def test_find_all_processes_by_name_success(self):
        mock_proc1 = MagicMock(pid=123, info={"name": "kasa_manager.exe"})
        mock_proc2 = MagicMock(pid=124, info={"name": "kasa_manager.exe"})
        with patch("psutil.process_iter", return_value=[mock_proc1, mock_proc2, MagicMock(info={"name": "other.exe"})]):
            result = find_all_processes_by_name("kasa_manager.exe")
            self.assertEqual(result, [mock_proc1, mock_proc2])

    def test_find_all_processes_by_name_no_match(self):
        with patch("psutil.process_iter", return_value=[MagicMock(info={"name": "other.exe"})]):
            result = find_all_processes_by_name("kasa_manager.exe")
            self.assertEqual(result, [])

    def test_find_all_processes_by_name_exception(self):
        with patch("psutil.process_iter", side_effect=Exception("Process error")):
            result = find_all_processes_by_name("kasa_manager.exe")
            self.assertEqual(result, [])

    def test_find_all_processes_by_name_empty_name(self):
        with patch("psutil.process_iter", return_value=[]):
            result = find_all_processes_by_name("")
            self.assertEqual(result, [])

    def test_find_all_processes_by_name_case_insensitive(self):
        mock_proc = MagicMock(pid=123, info={"name": "KASA_MANAGER.EXE"})
        with patch("psutil.process_iter", return_value=[mock_proc]):
            result = find_all_processes_by_name("kasa_manager.exe")
            self.assertEqual(result, [mock_proc])

    def test_manage_processes_no_stop_event_success(self):
        mock_proc = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        with patch("utils.find_process_by_path", side_effect=[mock_proc, None]):
            with patch("builtins.input", return_value="y"):
                result = manage_processes(["checkbox_kasa.exe"], [self.target_dir])
                self.assertTrue(result)
                mock_proc.kill.assert_called_once()

    def test_manage_processes_no_stop_event_cancel(self):
        mock_proc = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        with patch("utils.find_process_by_path", return_value=mock_proc):
            with patch("builtins.input", return_value="n"):
                result = manage_processes(["checkbox_kasa.exe"], [self.target_dir])
                self.assertFalse(result)
                mock_proc.kill.assert_not_called()

    def test_manage_processes_no_stop_event_no_processes(self):
        with patch("utils.find_process_by_path", return_value=None):
            result = manage_processes(["checkbox_kasa.exe"], [self.target_dir])
            self.assertTrue(result)

    def test_manage_processes_no_stop_event_no_such_process(self):
        mock_proc = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        mock_proc.kill.side_effect = psutil.NoSuchProcess("Process gone")
        with patch("utils.find_process_by_path", side_effect=[mock_proc, None]):
            with patch("builtins.input", return_value="y"):
                result = manage_processes(["checkbox_kasa.exe"], [self.target_dir])
                self.assertTrue(result)
                mock_proc.kill.assert_called_once()

    def test_manage_processes_no_stop_event_kill_failure(self):
        mock_proc = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        mock_proc.kill.side_effect = Exception("Kill error")
        with patch("utils.find_process_by_path", side_effect=[mock_proc, None]):
            with patch("builtins.input", return_value="y"):
                result = manage_processes(["checkbox_kasa.exe"], [self.target_dir])
                self.assertTrue(result)
                mock_proc.kill.assert_called_once()

    def test_manage_processes_with_stop_event(self):
        mock_proc = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        with patch("utils.find_process_by_path", side_effect=[mock_proc, None]):
            stop_event = threading.Event()
            def set_stop_event():
                time.sleep(0.1)
                stop_event.set()
            threading.Thread(target=set_stop_event).start()
            result = manage_processes(["checkbox_kasa.exe"], [self.target_dir], stop_event)
            self.assertTrue(result)
            mock_proc.kill.assert_called()

    def test_manage_processes_with_stop_event_no_processes(self):
        with patch("utils.find_process_by_path", return_value=None):
            stop_event = threading.Event()
            stop_event.set()
            result = manage_processes(["checkbox_kasa.exe"], [self.target_dir], stop_event)
            self.assertTrue(result)

    def test_manage_processes_exception(self):
        with patch("utils.find_process_by_path", side_effect=Exception("Process error")):
            result = manage_processes(["checkbox_kasa.exe"], [self.target_dir])
            self.assertFalse(result)

    def test_manage_processes_empty_inputs(self):
        with patch("utils.find_process_by_path", return_value=None):
            result = manage_processes([], [self.target_dir])
            self.assertTrue(result)
            result = manage_processes(["checkbox_kasa.exe"], [])
            self.assertTrue(result)

    def test_manage_processes_multiple_dirs_processes(self):
        mock_proc1 = MagicMock(pid=123, info={"name": "checkbox_kasa.exe"})
        mock_proc2 = MagicMock(pid=124, info={"name": "checkbox_kasa.exe"})
        with patch("utils.find_process_by_path", side_effect=[mock_proc1, mock_proc2, None]):
            with patch("builtins.input", return_value="y"):
                result = manage_processes(["checkbox_kasa.exe"],
                                         [self.target_dir, os.path.join(self.temp_dir, "other_dir")])
                self.assertTrue(result)
                mock_proc1.kill.assert_called_once()
                mock_proc2.kill.assert_called_once()

if __name__ == "__main__":
    unittest.main()