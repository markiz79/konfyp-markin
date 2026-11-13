import argparse
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlsplit


FIELDS = ('package', 'repository', 'test_mode', 'output', 'max_depth')
MIN_DEPTH = 0


def check_text(config, key):
    value = config[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key}: требуется непустая строка')
    if value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f'{key}: недопустимые пробелы или символы')
    return value


def check_repository(value, test_mode, folder):
    if test_mode:
        path = folder / value
        if not path.is_file():
            raise ValueError('repository: тестовый файл не найден')
        try:
            with path.open('rb') as file:
                file.read(1)
        except OSError as error:
            raise ValueError('repository: файл недоступен') from error
        return
    try:
        url = urlsplit(value)
        valid = url.scheme in ('http', 'https') and bool(url.hostname)
        valid = valid and not any(c.isspace() for c in value)
        valid = valid and url.username is None and url.password is None
        port = url.port
        if port is not None and port == 0:
            valid = False
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('repository: требуется URL http:// или https://')


def check_output(value, folder):
    if any(c in value for c in '<>:"|?*\\/'):
        raise ValueError('output: укажите имя файла без пути')
    if Path(value).suffix.lower() != '.png' or value.lower() == '.png':
        raise ValueError('output: требуется имя файла с расширением .png')
    reserved = {'CON', 'PRN', 'AUX', 'NUL'}
    reserved.update(f'{prefix}{i}' for prefix in ('COM', 'LPT')
                    for i in range(1, 10))
    if value.split('.')[0].upper() in reserved:
        raise ValueError('output: зарезервированное имя файла Windows')
    if (folder / value).is_dir():
        raise ValueError('output: это имя уже занято каталогом')


def validate_config(config, folder):
    for key in FIELDS:
        if key not in config:
            raise ValueError(f'{key}: отсутствует обязательный параметр')
    extra = set(config) - set(FIELDS)
    if extra:
        raise ValueError('Неизвестные параметры: ' + ', '.join(sorted(extra)))
    package = check_text(config, 'package')
    repository = check_text(config, 'repository')
    output = check_text(config, 'output')
    if type(config['test_mode']) is not bool:
        raise ValueError('test_mode: требуется true или false без кавычек')
    if type(config['max_depth']) is not int:
        raise ValueError('max_depth: требуется целое число')
    if config['max_depth'] < MIN_DEPTH:
        raise ValueError('max_depth: число должно быть неотрицательным')
    pattern = r'[A-Z]+' if config['test_mode'] else (
        r'[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?'
    )
    if not re.fullmatch(pattern, package):
        raise ValueError('package: недопустимое имя пакета')
    check_repository(repository, config['test_mode'], folder)
    check_output(output, folder)
    return config


def load_config(path):
    with path.open('rb') as file:
        config = tomllib.load(file)
    return validate_config(config, path.resolve().parent)


def main():
    parser = argparse.ArgumentParser(description='Вариант 15. Этап 1')
    parser.add_argument('config', nargs='?', default='config.toml',
                        help='путь к TOML-файлу (по умолчанию config.toml)')
    args = parser.parse_args()
    try:
        config = load_config(Path(args.config))
    except (OSError, ValueError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        return 1
    for key in FIELDS:
        value = config[key]
        if isinstance(value, bool):
            value = str(value).lower()
        print(f'{key} = {value}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
