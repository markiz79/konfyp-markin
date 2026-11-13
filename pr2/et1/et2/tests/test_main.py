import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from src.main import FIELDS, load_config, validate_config
from src.main import extract_dependencies, get_dependencies, main


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
        output = io.StringIO()
        with patch('sys.argv', ['main.py', str(ROOT / 'config.toml')]):
            with patch('src.main.get_dependencies', return_value=['B>=1']):
                with redirect_stdout(output):
                    self.assertEqual(main(), 0)
        self.assertIn('B>=1', output.getvalue())
        self.assertNotIn('max_depth =', output.getvalue())

    def test_cli_failure(self):
        result = subprocess.run(
            [sys.executable, 'src/main.py', 'missing.toml'], cwd=ROOT,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr)
        self.assertNotIn('Traceback', result.stderr)


class DependencyTests(unittest.TestCase):
    def test_preserves_requirements(self):
        values = ['B>=1', 'C; python_version < "3.12"',
                  'D; extra == "test"']
        data = {'info': {'requires_dist': values}}
        self.assertEqual(extract_dependencies(data), values)

    def test_no_dependencies(self):
        for value in (None, []):
            with self.subTest(value=value):
                data = {'info': {'requires_dist': value}}
                self.assertEqual(extract_dependencies(data), [])

    def test_invalid_metadata(self):
        for data in ([], {}, {'info': []}, {'info': {}},
                     {'info': {'requires_dist': 'B'}},
                     {'info': {'requires_dist': [1]}},
                     {'info': {'requires_dist': ['']}}):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    extract_dependencies(data)

    def test_download(self):
        data = {'info': {'requires_dist': ['B>=1']}}
        response = io.BytesIO(json.dumps(data).encode())
        with patch('src.main.urlopen', return_value=response) as request:
            result = get_dependencies('A', 'https://example.org/index/')
        self.assertEqual(result, ['B>=1'])
        request.assert_called_once_with(
            'https://example.org/index/pypi/A/json', timeout=20,
        )

    def test_network_errors(self):
        errors = [URLError('offline'), TimeoutError(),
                  HTTPError('url', 404, 'Not Found', None, None),
                  HTTPError('url', 500, 'Server Error', None, None)]
        for error in errors:
            with self.subTest(error=error):
                with patch('src.main.urlopen', side_effect=error):
                    with self.assertRaises(ValueError):
                        get_dependencies('A', 'https://example.org')

    def test_invalid_json(self):
        with patch('src.main.urlopen', return_value=io.BytesIO(b'bad')):
            with self.assertRaisesRegex(ValueError, 'JSON'):
                get_dependencies('A', 'https://example.org')

    def test_cli_empty(self):
        output = io.StringIO()
        with patch('sys.argv', ['main.py', str(ROOT / 'config.toml')]):
            with patch('src.main.get_dependencies', return_value=[]):
                with redirect_stdout(output):
                    self.assertEqual(main(), 0)
        self.assertIn('Зависимости отсутствуют', output.getvalue())

    def test_cli_network_error(self):
        output = io.StringIO()
        with patch('sys.argv', ['main.py', str(ROOT / 'config.toml')]):
            with patch('src.main.urlopen', side_effect=URLError('offline')):
                with redirect_stderr(output):
                    self.assertEqual(main(), 1)
        self.assertIn('Ошибка:', output.getvalue())

    def test_cli_test_mode(self):
        path = str(ROOT / 'examples/test.toml')
        with patch('sys.argv', ['main.py', path]):
            with patch('src.main.urlopen') as request:
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(main(), 1)
                request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
