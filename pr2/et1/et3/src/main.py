import argparse
import json
import re
import sys
import tomllib
from collections import deque
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import urlopen


FIELDS = ('package', 'repository', 'test_mode', 'output', 'max_depth')
MIN_DEPTH = 0
REQUEST_TIMEOUT = 20
HTTP_NOT_FOUND = 404
CONTROL_CHAR_LIMIT = 32
INVALID_PORT = 0


def check_text(config, key):
    value = config[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key}: требуется непустая строка')
    has_control = any(ord(c) < CONTROL_CHAR_LIMIT for c in value)
    if value != value.strip() or has_control:
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
    check_url(value)


def check_url(value):
    try:
        url = urlsplit(value)
        valid = url.scheme in ('http', 'https') and bool(url.hostname)
        valid = valid and not any(c.isspace() for c in value)
        valid = valid and url.username is None and url.password is None
        port = url.port
        if port is not None and port == INVALID_PORT:
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
    check_types(config)
    package = config['package']
    repository = config['repository']
    output = config['output']
    pattern = r'[A-Z]+' if config['test_mode'] else (
        r'[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?'
    )
    if not re.fullmatch(pattern, package):
        raise ValueError('package: недопустимое имя пакета')
    check_repository(repository, config['test_mode'], folder)
    check_output(output, folder)
    return config


def check_types(config):
    for key in ('package', 'repository', 'output'):
        check_text(config, key)
    if type(config['test_mode']) is not bool:
        raise ValueError('test_mode: требуется true или false без кавычек')
    if type(config['max_depth']) is not int:
        raise ValueError('max_depth: требуется целое число')
    if config['max_depth'] < MIN_DEPTH:
        raise ValueError('max_depth: число должно быть неотрицательным')


def load_config(path):
    with path.open('rb') as file:
        config = tomllib.load(file)
    return validate_config(config, path.resolve().parent)


def extract_dependencies(data):
    if not isinstance(data, dict) or not isinstance(data.get('info'), dict):
        raise ValueError('Некорректные метаданные пакета')
    info = data['info']
    if 'requires_dist' not in info:
        raise ValueError('В ответе отсутствует requires_dist')
    dependencies = info['requires_dist']
    if dependencies is None:
        return []
    if not isinstance(dependencies, list):
        raise ValueError('Некорректный список зависимостей')
    for dependency in dependencies:
        if not isinstance(dependency, str) or not dependency.strip():
            raise ValueError('Некорректная запись зависимости')
    return dependencies


def get_dependencies(package, repository):
    url = repository.rstrip('/') + '/pypi/' + quote(package) + '/json'
    try:
        with urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code == HTTP_NOT_FOUND:
            raise ValueError('Пакет или адрес API не найден') from error
        raise ValueError(f'Ошибка HTTP: {error.code}') from error
    except (URLError, OSError) as error:
        raise ValueError(f'Ошибка репозитория: {error}') from error
    except (ValueError, UnicodeError) as error:
        raise ValueError('Репозиторий вернул некорректный JSON') from error
    return extract_dependencies(data)


def parse_test_line(line):
    package, separator, value = line.partition(':')
    package = package.strip()
    dependencies = value.split()
    if not separator or not re.fullmatch(r'[A-Z]+', package):
        raise ValueError('Неверная строка тестового репозитория')
    if any(not re.fullmatch(r'[A-Z]+', item) for item in dependencies):
        raise ValueError('Имена пакетов должны быть заглавными буквами')
    return package, dependencies


def read_test_repository(path):
    graph = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        package, dependencies = parse_test_line(line)
        if package in graph:
            raise ValueError(f'Повторное описание пакета {package}')
        graph[package] = list(dict.fromkeys(dependencies))
    for dependencies in graph.values():
        for package in dependencies:
            if package not in graph:
                raise ValueError(f'Нет описания пакета {package}')
    return graph


def normalize_package(package):
    return re.sub(r'[-_.]+', '-', package).lower()


def dependency_names(requirements):
    names = []
    for requirement in requirements:
        match = re.match(r'[A-Za-z0-9][A-Za-z0-9._-]*', requirement.strip())
        if match is None:
            raise ValueError(f'Неверная зависимость: {requirement}')
        name = normalize_package(match.group())
        if name not in names:
            names.append(name)
    return names


def build_graph(start, max_depth, get_neighbors):
    graph = {start: None}
    depths = {start: 0}
    queue = deque([start])
    while queue:
        package = queue.popleft()
        if depths[package] >= max_depth:
            continue
        dependencies = list(dict.fromkeys(get_neighbors(package)))
        graph[package] = dependencies
        for dependency in dependencies:
            if dependency not in depths:
                depths[dependency] = depths[package] + 1
                graph[dependency] = None
                queue.append(dependency)
    return graph


def analyze(config, folder):
    package = config['package']
    if config['test_mode']:
        repository = read_test_repository(folder / config['repository'])
        if package not in repository:
            raise ValueError(f'Пакет {package} отсутствует в репозитории')
        get_neighbors = repository.__getitem__
    else:
        package = normalize_package(package)

        def get_neighbors(name):
            return dependency_names(
                get_dependencies(name, config['repository'])
            )

    return build_graph(package, config['max_depth'], get_neighbors)


def print_graph(graph):
    for package, dependencies in graph.items():
        if dependencies is None:
            value = 'достигнута максимальная глубина'
        elif dependencies:
            value = ', '.join(dependencies)
        else:
            value = 'нет зависимостей'
        print(f'{package}: {value}')


def main():
    parser = argparse.ArgumentParser(description='Вариант 15. Этап 3')
    parser.add_argument('config', nargs='?', default='config.toml',
                        help='путь к TOML-файлу (по умолчанию config.toml)')
    args = parser.parse_args()
    try:
        path = Path(args.config).resolve()
        config = load_config(path)
        graph = analyze(config, path.parent)
    except (OSError, ValueError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        return 1
    print_graph(graph)
    return 0


if __name__ == '__main__':
    sys.exit(main())
