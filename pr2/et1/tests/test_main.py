import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.main import FIELDS, load_config, validate_config


ROOT = Path(__file__).resolve().parents[1]


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.config = {
            'package': 'requests',
            'repository': 'https://pypi.org',
            'test_mode': False,
            'output': 'graph.png',
            'max_depth': 3,
        }

    def test_valid(self):
        self.assertEqual(validate_config(self.config, self.folder),
                         self.config)

    def test_zero_depth(self):
        self.config['max_depth'] = 0
        validate_config(self.config, self.folder)

    def test_missing_parameters(self):
        for key in FIELDS:
            with self.subTest(key=key):
                config = self.config.copy()
                del config[key]
                with self.assertRaisesRegex(ValueError, key):
                    validate_config(config, self.folder)

    def test_invalid_parameters(self):
        cases = {
            'package': ['', 15, 'my package', '-requests', 'a/../b'],
            'repository': ['', 15, 'pypi.org', 'ftp://pypi.org',
                           'https://', 'https://host:bad', 'https://['],
            'test_mode': ['false', 0, 1],
            'output': ['', 15, 'graph.jpg', '../graph.png', 'CON.png'],
            'max_depth': [-1, 1.5, '3', True],
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    config = dict(self.config, **{key: value})
                    with self.assertRaisesRegex(ValueError, key):
                        validate_config(config, self.folder)

    def test_unknown_parameter(self):
        self.config['depth'] = 5
        with self.assertRaisesRegex(ValueError, 'depth'):
            validate_config(self.config, self.folder)

    def test_test_repository(self):
        (self.folder / 'repo.txt').write_text('A: B\nB:\n')
        self.config.update(package='A', test_mode=True,
                           repository='repo.txt')
        validate_config(self.config, self.folder)
        self.config['repository'] = 'missing.txt'
        with self.assertRaisesRegex(ValueError, 'repository'):
            validate_config(self.config, self.folder)

    def test_test_package_name(self):
        self.config.update(package='requests', test_mode=True)
        with self.assertRaisesRegex(ValueError, 'package'):
            validate_config(self.config, self.folder)

    def test_output_is_directory(self):
        (self.folder / 'graph.png').mkdir()
        with self.assertRaisesRegex(ValueError, 'output'):
            validate_config(self.config, self.folder)

    def test_bad_toml(self):
        path = self.folder / 'bad.toml'
        path.write_text('package = [')
        with self.assertRaises(ValueError):
            load_config(path)

    def test_missing_file(self):
        with self.assertRaises(OSError):
            load_config(self.folder / 'missing.toml')

    def test_cli_success(self):
        result = subprocess.run(
            [sys.executable, 'src/main.py'], cwd=ROOT,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.splitlines()), len(FIELDS))
        self.assertIn('test_mode = false', result.stdout)
        self.assertEqual(result.stderr, '')

    def test_cli_failure(self):
        result = subprocess.run(
            [sys.executable, 'src/main.py', 'missing.toml'], cwd=ROOT,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
