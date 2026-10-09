import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from data_paths import data_root


class PortablePaths(unittest.TestCase):
    def test_frozen_path_is_beside_exe_not_internal(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', 'E:/portable/Kotoba.exe'):
            self.assertEqual(data_root(), Path('E:/portable/data'))

    def test_source_path(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(data_root(), Path(__file__).resolve().parent / 'data')
