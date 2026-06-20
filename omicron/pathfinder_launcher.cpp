#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

#include <iostream>
#include <string>
#include <vector>

static std::wstring quote_arg(const std::wstring &arg) {
    if (arg.empty()) return L"\"\"";
    bool needs_quotes = false;
    for (wchar_t ch : arg) {
        if (ch == L' ' || ch == L'\t' || ch == L'"') {
            needs_quotes = true;
            break;
        }
    }
    if (!needs_quotes) return arg;

    std::wstring out = L"\"";
    size_t backslashes = 0;
    for (wchar_t ch : arg) {
        if (ch == L'\\') {
            ++backslashes;
        } else if (ch == L'"') {
            out.append(backslashes * 2 + 1, L'\\');
            out.push_back(ch);
            backslashes = 0;
        } else {
            out.append(backslashes, L'\\');
            backslashes = 0;
            out.push_back(ch);
        }
    }
    out.append(backslashes * 2, L'\\');
    out.push_back(L'"');
    return out;
}

static std::wstring module_directory() {
    std::vector<wchar_t> buffer(MAX_PATH);
    DWORD size = 0;
    for (;;) {
        size = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
        if (size == 0) return L".";
        if (size < buffer.size() - 1) break;
        buffer.resize(buffer.size() * 2);
    }
    std::wstring path(buffer.data(), size);
    size_t slash = path.find_last_of(L"\\/");
    if (slash == std::wstring::npos) return L".";
    return path.substr(0, slash);
}

static std::wstring current_directory() {
    DWORD needed = GetCurrentDirectoryW(0, nullptr);
    if (needed == 0) return L".";
    std::vector<wchar_t> buffer(needed);
    DWORD got = GetCurrentDirectoryW(needed, buffer.data());
    if (got == 0) return L".";
    return std::wstring(buffer.data(), got);
}

static bool file_exists(const std::wstring &path) {
    DWORD attrs = GetFileAttributesW(path.c_str());
    return attrs != INVALID_FILE_ATTRIBUTES && !(attrs & FILE_ATTRIBUTE_DIRECTORY);
}

static std::wstring env_value(const wchar_t *name) {
    DWORD needed = GetEnvironmentVariableW(name, nullptr, 0);
    if (needed == 0) return L"";
    std::vector<wchar_t> buffer(needed);
    DWORD got = GetEnvironmentVariableW(name, buffer.data(), needed);
    if (got == 0) return L"";
    return std::wstring(buffer.data(), got);
}

static bool run_command(const std::wstring &command, const std::wstring &working_dir, DWORD &exit_code) {
    std::wstring mutable_command = command;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si);

    BOOL ok = CreateProcessW(
        nullptr,
        mutable_command.data(),
        nullptr,
        nullptr,
        TRUE,
        0,
        nullptr,
        working_dir.c_str(),
        &si,
        &pi
    );
    if (!ok) return false;

    WaitForSingleObject(pi.hProcess, INFINITE);
    if (!GetExitCodeProcess(pi.hProcess, &exit_code)) {
        exit_code = 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return true;
}

int main() {
    int argc = 0;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) {
        std::wcerr << L"pathfinder.exe: unable to parse command line\n";
        return 1;
    }

    std::wstring dir = module_directory();
    std::wstring cwd = current_directory();
    std::wstring script = dir + L"\\pathfinder.py";
    if (!file_exists(script)) {
        std::wcerr << L"pathfinder.exe: pathfinder.py was not found beside the executable: " << script << L"\n";
        LocalFree(argv);
        return 1;
    }

    std::vector<std::wstring> prefixes;
    std::wstring configured_python = env_value(L"PATHFINDER_PYTHON");
    if (!configured_python.empty()) prefixes.push_back(quote_arg(configured_python));
    prefixes.push_back(L"python.exe");
    prefixes.push_back(L"py.exe -3");

    std::wstring forwarded;
    for (int i = 1; i < argc; ++i) {
        forwarded += L" ";
        forwarded += quote_arg(argv[i]);
    }
    LocalFree(argv);

    for (const std::wstring &prefix : prefixes) {
        std::wstring command = prefix + L" " + quote_arg(script) + forwarded;
        DWORD exit_code = 1;
        if (run_command(command, cwd, exit_code)) {
            return static_cast<int>(exit_code);
        }
    }

    std::wcerr << L"pathfinder.exe: could not launch Python. Set PATHFINDER_PYTHON to a Python executable path.\n";
    return 1;
}
