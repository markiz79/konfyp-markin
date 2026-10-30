#include <algorithm>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <chrono>
#include <cstdio>
#include <cctype>
#include <nlohmann/json.hpp>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace fs = std::filesystem;
using json = nlohmann::json;

struct Node {
    bool directory = true;
    std::string content;
    std::map<std::string, Node> children;
};

struct Config {
    fs::path vfsPath = "vfs/default.json";
    fs::path logPath = "commands.json";
    fs::path scriptPath;
};

class Shell {
public:
    explicit Shell(Config cfg) : config(std::move(cfg)) {
        loadVfs(config.vfsPath);
    }

    int run() {
        std::cout << "=== Параметры запуска ===\n"
                  << "VFS: " << config.vfsPath.string() << "\n"
                  << "Лог: " << config.logPath.string() << "\n"
                  << "Стартовый скрипт: "
                  << (config.scriptPath.empty() ? "(не задан)" : config.scriptPath.string())
                  << "\n=========================\n";
        if (!config.scriptPath.empty()) {
            if (!runScript(config.scriptPath)) {
                std::cerr << "Ошибка: не удалось выполнить стартовый скрипт.\n";
            }
        }
        repl();
        return 0;
    }

private:
    Config config;
    Node root;
    std::string vfsName = "default";
    std::string currentPath = "/";
    std::vector<std::string> history;

    static std::string trim(const std::string& s) {
        const auto b = s.find_first_not_of(" \t\r\n");
        if (b == std::string::npos) return "";
        const auto e = s.find_last_not_of(" \t\r\n");
        return s.substr(b, e - b + 1);
    }

    static std::string username() {
        const char* value = std::getenv("USER");
        if (!value) value = std::getenv("USERNAME");
        return value ? value : "user";
    }

    static std::string hostname() {
#ifdef _WIN32
        char name[MAX_COMPUTERNAME_LENGTH + 1] = {};
        DWORD size = sizeof(name);
        return GetComputerNameA(name, &size) ? std::string(name) : "host";
#else
        char name[256] = {};
        return gethostname(name, sizeof(name)) == 0 ? std::string(name) : "host";
#endif
    }

    static std::string expandVariables(const std::string& input) {
        std::string out;
        for (std::size_t i = 0; i < input.size();) {
            if (input[i] != '$') {
                out += input[i++];
                continue;
            }
            ++i;
            std::string key;
            if (i < input.size() && input[i] == '{') {
                ++i;
                while (i < input.size() && input[i] != '}') key += input[i++];
                if (i < input.size()) ++i;
            } else {
                while (i < input.size() &&
                       (std::isalnum(static_cast<unsigned char>(input[i])) || input[i] == '_')) {
                    key += input[i++];
                }
            }
            if (key.empty()) {
                out += '$';
                continue;
            }
            const char* value = std::getenv(key.c_str());
            if (value) out += value;
        }
        return out;
    }

    static std::vector<std::string> tokenize(const std::string& line) {
        std::vector<std::string> tokens;
        std::string token;
        char quote = 0;
        bool active = false;
        for (char c : line) {
            if ((c == '"' || c == '\'') && (!quote || quote == c)) {
                quote = quote ? 0 : c;
                active = true;
            } else if (std::isspace(static_cast<unsigned char>(c)) && !quote) {
                if (active) {
                    tokens.push_back(expandVariables(token));
                    token.clear();
                    active = false;
                }
            } else {
                token += c;
                active = true;
            }
        }
        if (quote) throw std::runtime_error("незакрытая кавычка");
        if (active) tokens.push_back(expandVariables(token));
        return tokens;
    }

    static std::vector<std::string> splitPath(const std::string& path) {
        std::vector<std::string> parts;
        std::stringstream ss(path);
        std::string part;
        while (std::getline(ss, part, '/')) {
            if (!part.empty() && part != ".") parts.push_back(part);
        }
        return parts;
    }

    std::string normalize(const std::string& path) const {
        std::vector<std::string> parts = path.empty() || path[0] != '/'
            ? splitPath(currentPath) : std::vector<std::string>{};
        for (const auto& part : splitPath(path)) {
            if (part == "..") {
                if (!parts.empty()) parts.pop_back();
            } else {
                parts.push_back(part);
            }
        }
        std::string result = "/";
        for (std::size_t i = 0; i < parts.size(); ++i) {
            if (i) result += "/";
            result += parts[i];
        }
        return result;
    }

    Node* findNode(const std::string& path) {
        Node* node = &root;
        for (const auto& part : splitPath(normalize(path))) {
            if (!node->directory) return nullptr;
            auto it = node->children.find(part);
            if (it == node->children.end()) return nullptr;
            node = &it->second;
        }
        return node;
    }

    static Node fromJson(const json& value) {
        Node node;
        const std::string type = value.value("type", "directory");
        node.directory = type == "directory";
        if (node.directory) {
            if (value.contains("children") && value["children"].is_array()) {
                for (const auto& child : value["children"]) {
                    const std::string name = child.at("name").get<std::string>();
                    node.children[name] = fromJson(child);
                }
            }
        } else {
            node.content = value.value("content", "");
        }
        return node;
    }

    static json toJson(const std::string& name, const Node& node) {
        json value;
        value["name"] = name;
        value["type"] = node.directory ? "directory" : "file";
        if (node.directory) {
            value["children"] = json::array();
            for (const auto& [childName, child] : node.children)
                value["children"].push_back(toJson(childName, child));
        } else {
            value["content"] = node.content;
        }
        return value;
    }

    void loadVfs(const fs::path& path) {
        std::ifstream file(path);
        if (!file) throw std::runtime_error("не удалось открыть VFS: " + path.string());
        json data;
        file >> data;
        if (!data.is_object() || data.value("type", "") != "directory")
            throw std::runtime_error("неверный формат VFS: корень должен быть directory");
        vfsName = data.value("name", path.stem().string());
        root = fromJson(data);
        currentPath = "/";
    }

    void resetVfs() {
        const json emptyVfs = {
            {"name", "default"},
            {"type", "directory"},
            {"children", json::array()}
        };

        std::ofstream file(config.vfsPath, std::ios::out | std::ios::trunc);
        if (!file.is_open()) {
            throw std::runtime_error(
                "не удалось открыть файл VFS для очистки: " +
                config.vfsPath.string()
            );
        }

        file << emptyVfs.dump(4) << '\n';
        file.flush();
        if (!file) {
            throw std::runtime_error(
                "ошибка записи пустой VFS в файл: " + config.vfsPath.string()
            );
        }
        file.close();
        if (file.fail()) {
            throw std::runtime_error(
                "ошибка закрытия файла VFS: " + config.vfsPath.string()
            );
        }

        root = Node{};
        vfsName = "default";
        currentPath = "/";

        std::cout << "VFS сброшена к пустой файловой системе по умолчанию.\n";
    }

    void appendLog(const std::string& command, const std::vector<std::string>& args,
                   bool success, const std::string& error) {
        json events = json::array();
        std::ifstream in(config.logPath);
        if (in) {
            try { in >> events; } catch (...) { events = json::array(); }
            if (!events.is_array()) events = json::array();
        }
        const auto now = std::chrono::system_clock::now();
        const auto time = std::chrono::system_clock::to_time_t(now);
        std::tm tm{};
#ifdef _WIN32
        localtime_s(&tm, &time);
#else
        localtime_r(&time, &tm);
#endif
        std::ostringstream stamp;
        stamp << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S");
        events.push_back({
            {"timestamp", stamp.str()},
            {"command", command},
            {"arguments", args},
            {"success", success},
            {"error", error}
        });
        fs::path parent = config.logPath.parent_path();
        if (!parent.empty()) fs::create_directories(parent);
        std::ofstream out(config.logPath);
        out << events.dump(2) << '\n';
    }

    static void printUsage(const std::string& command) {
        if (command == "cd") std::cout << "Использование: cd [каталог]\n";
        else if (command == "ls") std::cout << "Использование: ls [-a] [-l] [путь]\n";
        else if (command == "head") std::cout << "Использование: head [-n число] файл\n";
        else if (command == "cal") std::cout << "Использование: cal [месяц] [год] | cal [год]\n";
    }

    bool execute(const std::string& line) {
        std::vector<std::string> args;
        std::string command;
        bool success = true;
        std::string error;
        try {
            args = tokenize(line);
            if (args.empty()) return true;
            command = args.front();
            args.erase(args.begin());

            if (command == "exit") {
                if (!args.empty()) throw std::runtime_error("exit не принимает аргументы");
                return false;
            } else if (command == "ls") {
                if (args.size() > 3) throw std::runtime_error("слишком много аргументов");
                bool all = false, longFormat = false;
                std::string path = currentPath;
                for (const auto& arg : args) {
                    if (arg == "-a") all = true;
                    else if (arg == "-l") longFormat = true;
                    else if (!arg.empty() && arg[0] == '-') throw std::runtime_error("неизвестный параметр " + arg);
                    else path = arg;
                }
                Node* dir = findNode(path);
                if (!dir) throw std::runtime_error("путь не найден: " + path);
                if (!dir->directory) {
                    std::cout << normalize(path) << '\n';
                } else {
                    for (const auto& [name, child] : dir->children) {
                        if (!all && !name.empty() && name[0] == '.') continue;
                        if (longFormat)
                            std::cout << (child.directory ? "d" : "-")
                                      << std::setw(8) << (child.directory ? 0 : child.content.size())
                                      << " " << name << (child.directory ? "/" : "") << '\n';
                        else
                            std::cout << name << (child.directory ? "/" : "") << '\n';
                    }
                }
            } else if (command == "cd") {
                if (args.size() > 1) throw std::runtime_error("ожидается не более одного аргумента");
                const std::string target = args.empty() ? "/" : args[0];
                Node* dir = findNode(target);
                if (!dir) throw std::runtime_error("каталог не найден: " + target);
                if (!dir->directory) throw std::runtime_error("это файл, а не каталог: " + target);
                currentPath = normalize(target);
            } else if (command == "clear") {
                if (!args.empty()) throw std::runtime_error("clear не принимает аргументы");
                std::cout << "\033[2J\033[H";
            } else if (command == "head") {
                int count = 10;
                std::string filePath;
                for (std::size_t i = 0; i < args.size(); ++i) {
                    if (args[i] == "-n") {
                        if (i + 1 >= args.size()) throw std::runtime_error("после -n требуется число");
                        std::size_t used = 0;
                        count = std::stoi(args[++i], &used);
                        if (used != args[i].size() || count < 0) throw std::runtime_error("неверное число строк");
                    } else if (!args[i].empty() && args[i][0] == '-') {
                        throw std::runtime_error("неизвестный параметр " + args[i]);
                    } else if (filePath.empty()) filePath = args[i];
                    else throw std::runtime_error("укажите только один файл");
                }
                if (filePath.empty()) throw std::runtime_error("не указан файл");
                Node* file = findNode(filePath);
                if (!file) throw std::runtime_error("файл не найден: " + filePath);
                if (file->directory) throw std::runtime_error("указан каталог, а не файл");
                std::istringstream content(file->content);
                std::string row;
                for (int i = 0; i < count && std::getline(content, row); ++i)
                    std::cout << row << '\n';
            } else if (command == "cal") {
                if (args.size() > 2) throw std::runtime_error("слишком много аргументов");
                std::time_t now = std::time(nullptr);
                std::tm current{};
#ifdef _WIN32
                localtime_s(&current, &now);
#else
                localtime_r(&now, &current);
#endif
                int month = current.tm_mon + 1;
                int year = current.tm_year + 1900;
                if (args.size() == 1) {
                    int value = std::stoi(args[0]);
                    if (value < 1 || value > 9999) throw std::runtime_error("неверный год");
                    year = value;
                } else if (args.size() == 2) {
                    month = std::stoi(args[0]);
                    year = std::stoi(args[1]);
                    if (month < 1 || month > 12 || year < 1 || year > 9999)
                        throw std::runtime_error("месяц должен быть 1..12, год 1..9999");
                }
                static const char* months[] = {"Январь","Февраль","Март","Апрель","Май","Июнь",
                                                "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"};
                std::cout << "       " << months[month - 1] << " " << year << "\n"
                          << "Пн Вт Ср Чт Пт Сб Вс\n";
                std::tm first{};
                first.tm_year = year - 1900;
                first.tm_mon = month - 1;
                first.tm_mday = 1;
                std::mktime(&first);
                int offset = (first.tm_wday + 6) % 7;
                int days = 31;
                if (month == 4 || month == 6 || month == 9 || month == 11) days = 30;
                if (month == 2) {
                    bool leap = (year % 400 == 0) || (year % 4 == 0 && year % 100 != 0);
                    days = leap ? 29 : 28;
                }
                for (int i = 0; i < offset; ++i) std::cout << "   ";
                for (int day = 1; day <= days; ++day) {
                    std::cout << std::setw(2) << day << " ";
                    if ((offset + day) % 7 == 0) std::cout << '\n';
                }
                std::cout << '\n';
            } else if (command == "vfs-init") {
                if (!args.empty()) throw std::runtime_error("vfs-init не принимает аргументы");
                resetVfs();
            } else {
                throw std::runtime_error("неизвестная команда: " + command);
            }
        } catch (const std::exception& ex) {
            success = false;
            error = ex.what();
            std::cerr << "Ошибка: " << error << '\n';
            printUsage(command);
        }
        if (!command.empty()) {
            history.push_back(line);
            appendLog(command, args, success, error);
        }
        return true;
    }

    bool runScript(const fs::path& path) {
        std::ifstream file(path);
        if (!file) {
            std::cerr << "Ошибка: стартовый скрипт не найден: " << path << '\n';
            return false;
        }
        std::cout << "Запуск скрипта: " << path << '\n';
        std::string line;
        std::size_t lineNumber = 0;
        while (std::getline(file, line)) {
            ++lineNumber;
            const std::string cleaned = trim(line);
            if (cleaned.empty() || cleaned[0] == '#') continue;
            std::cout << username() << "@" << hostname() << ":" << currentPath
                      << "$ " << line << '\n';
            if (!execute(line)) {
                std::cout << "Скрипт остановлен командой exit.\n";
                break;
            }
        }
        std::cout << "Завершение стартового скрипта.\n";
        return true;
    }

    void repl() {
        std::string line;
        while (true) {
            std::cout << username() << "@" << hostname() << ":" << currentPath
                      << " [" << vfsName << "]$ " << std::flush;
            if (!std::getline(std::cin, line)) break;
            if (!execute(line)) break;
        }
    }
};

static Config parseArgs(int argc, char* argv[]) {
    Config cfg;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if ((arg == "--vfs" || arg == "--log" || arg == "--script") && i + 1 < argc) {
            const std::string value = argv[++i];
            if (arg == "--vfs") cfg.vfsPath = value;
            else if (arg == "--log") cfg.logPath = value;
            else cfg.scriptPath = value;
        } else if (arg == "--help") {
            std::cout << "Использование: shell_emulator [--vfs файл.json] "
                         "[--log файл.json] [--script файл.sh]\n";
            std::exit(0);
        } else {
            throw std::runtime_error("неизвестный или неполный параметр: " + arg);
        }
    }
    return cfg;
}

int main(int argc, char* argv[]) {
    try {
        Shell shell(parseArgs(argc, argv));
        return shell.run();
    } catch (const std::exception& ex) {
        std::cerr << "Критическая ошибка: " << ex.what() << '\n';
        return 1;
    }
}

