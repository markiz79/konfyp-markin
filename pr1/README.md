
# Эмулятор командной оболочки — вариант 15 (C++17)

## Описание
Консольный эмулятор UNIX-подобной оболочки с виртуальной файловой системой,
загружаемой из JSON. Все операции над VFS выполняются в оперативной памяти.
Исходный JSON-файл не распаковывается и не изменяется.

## Реализовано по этапам
- **Этап 1:** CLI, приглашение `username@hostname`, переменные окружения `$NAME` и `${NAME}`,
  кавычки, команды-заглушки/обработчики `ls`, `cd`, команда `exit`, ошибки.
- **Этап 2:** параметры `--vfs`, `--log`, `--script`; отладочный вывод конфигурации;
  стартовый скрипт с отображением вводимых команд; ошибочные строки пропускаются;
  события записываются в JSON-файл.
- **Этап 3:** загрузка VFS из JSON; дерево каталогов и файлов; `vfs-init` сбрасывает
  файловую систему в памяти к пустой VFS по умолчанию.
- **Этап 4:** полноценные `ls` (`-a`, `-l`, путь), `cd`, `head` (`-n`),
  `clear`, `cal` (текущий месяц, год или месяц+год).

## Формат VFS
Корневой объект должен иметь `type: "directory"`. Каталог содержит массив `children`,
файл — строковое поле `content`. Пример находится в `vfs/default.json`.

## Зависимости
- CMake 3.16+
- Компилятор с поддержкой C++17
- Библиотека nlohmann-json 3.x

Ubuntu/Debian:
```bash
sudo apt install build-essential cmake nlohmann-json3-dev
```

Windows (vcpkg):
```powershell
vcpkg install nlohmann-json
```
При необходимости подключите toolchain-файл vcpkg к CMake.

## Сборка и запуск
Linux:
```bash
cmake -S . -B build
cmake --build build
./build/shell_emulator --vfs vfs/default.json --log commands.json
```

Windows:
```powershell
cmake -S . -B build
cmake --build build
.uild\Debug\shell_emulator.exe --vfs vfs\default.json --log commands.json
```

Параметры:
- `--vfs PATH` — JSON-файл виртуальной файловой системы.
- `--log PATH` — JSON-файл журнала команд.
- `--script PATH` — стартовый скрипт.
- `--help` — справка.

Пример запуска всех тестов этапов:
```bash
./build/shell_emulator --vfs vfs/default.json --log commands.json --script scripts/stage4_demo.sh
```

## Команды
- `ls [-a] [-l] [путь]` — список файлов и каталогов.
- `cd [каталог]` — смена текущего каталога; без аргумента переход в `/`.
- `head [-n N] ФАЙЛ` — первые N строк, по умолчанию 10.
- `clear` — очистка терминала.
- `cal [месяц] [год]` — календарь текущего месяца, указанного года или месяца указанного года.
- `vfs-init` — сброс VFS в памяти.
- `exit` — выход.

## Логирование
`commands.json` — JSON-массив. Каждая запись содержит дату и время,
имя команды, аргументы, признак успеха и текст ошибки.

## Проверка
Сценарий `scripts/stage4_demo.sh` демонстрирует команды и обработку ошибок.
Дополнительный перечень проверок находится в `tests/manual_tests.md`.


## Восстановление демонстрационной VFS

Команда `vfs-init` записывает пустую VFS в JSON-файл, указанный параметром `--vfs`, и очищает дерево в памяти. Перед первым тестом сохранена резервная копия `vfs/default.backup.json`.

Чтобы восстановить демонстрационную структуру после `vfs-init`, из корня проекта выполните:

```bash
cp vfs/default.backup.json vfs/default.json
```

После этого можно снова запустить программу:

```bash
./build/shell_emulator --vfs vfs/default.json --log commands.json
```

