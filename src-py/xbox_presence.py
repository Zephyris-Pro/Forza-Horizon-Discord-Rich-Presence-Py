import ctypes
import ctypes.wintypes as wintypes
import logging
import sys
import time
import requests

SCAN_TIME_LIMIT_S = 6.0
SCAN_MAX_BYTES = 268435456
CHUNK_SIZE = 1048576

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

TH32CS_SNAPPROCESS = 0x02
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
PROCESS_VM_OPERATION = 0x0008
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
TOKEN_ADJUST_PRIVILEGES = 0x20
TOKEN_QUERY = 0x08
SE_PRIVILEGE_ENABLED = 0x02


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * wintypes.MAX_PATH),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_size_t),
        ("AllocationBase", ctypes.c_size_t),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [
        ("PrivilegeCount", wintypes.DWORD),
        ("Privileges", LUID_AND_ATTRIBUTES * 1),
    ]


kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.GetCurrentProcess.argtypes = []
kernel32.GetCurrentProcess.restype = wintypes.HANDLE
kernel32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
advapi32.OpenProcessToken.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
]
advapi32.OpenProcessToken.restype = wintypes.BOOL
advapi32.LookupPrivilegeValueW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    ctypes.POINTER(LUID),
]
advapi32.LookupPrivilegeValueW.restype = wintypes.BOOL
advapi32.AdjustTokenPrivileges.argtypes = [
    wintypes.HANDLE,
    wintypes.BOOL,
    ctypes.POINTER(TOKEN_PRIVILEGES),
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
advapi32.AdjustTokenPrivileges.restype = wintypes.BOOL


def _get_win_error_message():
    err = ctypes.get_last_error()
    if err == 0:
        return "no error"
    try:
        return f"{err}: {ctypes.WinError(err).strerror}"
    except Exception:
        return str(err)


def _enable_debug_privilege():
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
        ctypes.byref(token),
    ):
        return False
    luid = LUID()
    if not advapi32.LookupPrivilegeValueW(None, "SeDebugPrivilege", ctypes.byref(luid)):
        kernel32.CloseHandle(token)
        return False
    privileges = TOKEN_PRIVILEGES()
    privileges.PrivilegeCount = 1
    privileges.Privileges[0].Luid = luid
    privileges.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
    if not advapi32.AdjustTokenPrivileges(
        token, False, ctypes.byref(privileges), 0, None, None
    ):
        kernel32.CloseHandle(token)
        return False
    kernel32.CloseHandle(token)
    return True


def _find_xbox_app_pids():
    names = {
        "gamingapp.exe",
        "gamingservices.exe",
        "xboxpcappft.exe",
        "applicationframehost.exe",
        "xboxpcapp.exe",
        "microsoft.gamingapp.exe",
        "xboxgamebarft.exe",
        "xboxidentityprovider.exe",
        "xboxgamebar.exe",
        "xboxappservices.exe",
        "xboxgamebarftserver.exe",
        "gamingservicesnet.exe",
    }
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    results = []
    try:
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return []
        while True:
            name = entry.szExeFile.lower()
            if name in names:
                results.append((entry.szExeFile, entry.th32ProcessID))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    order = [
        "xboxpcapp.exe",
        "xboxpcappft.exe",
        "gamingservices.exe",
        "gamingservicesnet.exe",
        "gamingapp.exe",
        "microsoft.gamingapp.exe",
        "xboxidentityprovider.exe",
        "applicationframehost.exe",
        "xboxappservices.exe",
        "xboxgamebar.exe",
        "xboxgamebarft.exe",
        "xboxgamebarftserver.exe",
    ]
    order_index = {name: idx for idx, name in enumerate(order)}
    results.sort(key=lambda item: order_index.get(item[0].lower(), 999))
    return results


def list_processes():
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return []
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    results = []
    try:
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return []
        while True:
            results.append((entry.szExeFile, entry.th32ProcessID))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return results


def get_process_image_path(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _iter_process_memory(handle):
    address = 0
    mbi = MEMORY_BASIC_INFORMATION()
    while True:
        ctypes.set_last_error(0)
        result = kernel32.VirtualQueryEx(
            handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi)
        )
        if not result:
            err = ctypes.get_last_error()
            if err not in (0, 87):
                logging.debug("VirtualQueryEx stopped: %s", _get_win_error_message())
            return
        if not mbi.RegionSize:
            return
        if (
            mbi.State == MEM_COMMIT
            and not (mbi.Protect & PAGE_NOACCESS)
            and not (mbi.Protect & PAGE_GUARD)
        ):
            yield (int(mbi.BaseAddress), int(mbi.RegionSize))
        next_address = int(mbi.BaseAddress) + int(mbi.RegionSize)
        if next_address <= address:
            return
        address = next_address


def _read_process_bytes(handle, address, length):
    buffer = ctypes.create_string_buffer(length)
    bytes_read = ctypes.c_size_t()
    if not kernel32.ReadProcessMemory(
        handle, ctypes.c_void_p(address), buffer, length, ctypes.byref(bytes_read)
    ):
        return None
    return buffer.raw[: bytes_read.value]


def extract_token(text: str) -> str | None:
    lowered = text.lower()
    prefix = "xbl3.0 x="
    start = lowered.find(prefix)
    if start == -1:
        return None
    tail = text[start + len(prefix) :]
    allowed = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/_=.-;"
    )
    token_rest = []
    for ch in tail:
        if ch in allowed:
            token_rest.append(ch)
        else:
            break
    token = "XBL3.0 x=" + "".join(token_rest)
    if ";" not in token:
        return None
    return token


def _scan_xauth_in_process(pid):
    access = (
        PROCESS_QUERY_INFORMATION
        | PROCESS_QUERY_LIMITED_INFORMATION
        | PROCESS_VM_READ
        | PROCESS_VM_OPERATION
    )
    handle = kernel32.OpenProcess(access, False, pid)
    if not handle:
        logging.warning(
            "OpenProcess failed for PID %s: %s", pid, _get_win_error_message()
        )
        return None

    pattern = b"XBL3.0 x="
    pattern_lower = b"xbl3.0 x="
    pattern_wide = "XBL3.0 x=".encode("utf-16-le")
    pattern_wide_lower = "xbl3.0 x=".encode("utf-16-le")
    candidates: dict[str, int] = {}
    best_token = None
    best_count = 0
    tail_len = max(
        len(pattern), len(pattern_lower), len(pattern_wide), len(pattern_wide_lower)
    )

    def record_token(token):
        nonlocal best_token, best_count
        count = candidates.get(token, 0) + 1
        candidates[token] = count
        if count > best_count:
            best_count = count
            best_token = token
        return best_count >= 3

    def read_token_at(address, is_wide):
        if is_wide:
            raw = _read_process_bytes(handle, address, 20000)
            if not raw:
                return None
            terminator = raw.find(b"\x00\x00")
            if terminator != -1:
                raw = raw[:terminator]
            text = raw.decode("utf-16-le", errors="ignore")
        else:
            raw = _read_process_bytes(handle, address, 10000)
            if not raw:
                return None
            terminator = raw.find(b"\x00")
            if terminator != -1:
                raw = raw[:terminator]
            text = raw.decode("utf-8", errors="ignore")
        return extract_token(text)

    bytes_scanned = 0
    start_time = time.monotonic()
    scan_stopped = False

    for base, size in _iter_process_memory(handle):
        offset = 0
        tail = b""
        while offset < size:
            if time.monotonic() - start_time >= SCAN_TIME_LIMIT_S:
                scan_stopped = True
                break
            to_read = min(CHUNK_SIZE, size - offset)
            chunk = _read_process_bytes(handle, base + offset, to_read)
            if chunk:
                bytes_scanned += len(chunk)
                if bytes_scanned >= SCAN_MAX_BYTES:
                    scan_stopped = True
                    break
                data = tail + chunk
                base_addr = base + offset - len(tail)
                for sig in [pattern, pattern_lower]:
                    idx = data.find(sig)
                    while idx != -1:
                        token = read_token_at(base_addr + idx, False)
                        if token and record_token(token):
                            kernel32.CloseHandle(handle)
                            return best_token
                        idx = data.find(sig, idx + 1)
                for sig in [pattern_wide, pattern_wide_lower]:
                    idx = data.find(sig)
                    while idx != -1:
                        token = read_token_at(base_addr + idx, True)
                        if token and record_token(token):
                            kernel32.CloseHandle(handle)
                            return best_token
                        idx = data.find(sig, idx + 2)
                tail = data[-tail_len:] if len(data) >= tail_len else data
            else:
                tail = b""
            offset += to_read
        if scan_stopped:
            break

    kernel32.CloseHandle(handle)
    if not candidates:
        return None
    return max(candidates.items(), key=lambda item: (item[1], len(item[0])))[0]


def grab_xauth():
    if sys.platform != "win32":
        return None
    _enable_debug_privilege()
    for name, pid in _find_xbox_app_pids():
        logging.info("Scanning %s (PID %s) for XAUTH.", name, pid)
        xauth = _scan_xauth_in_process(pid)
        if xauth:
            return xauth
    return None


def _parse_status(payload, title: str | None = None) -> str | None:
    fallback = None
    for device in (payload or {}).get("devices", []):
        for t in device.get("titles", []):
            rp = (t.get("activity") or {}).get("richPresence")
            if not rp:
                continue
            if title and t.get("name") == title:
                return rp
            if fallback is None:
                fallback = rp
    return fallback


def _fetch_current_status(xauth, title: str | None = None) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36 Edge/18.26200",
        "Authorization": xauth,
        "x-xbl-contract-version": "3",
        "Accept": "application/json",
        "Accept-Language": "en-US",
    }
    try:
        response = requests.get(
            "https://userpresence.xboxlive.com/users/me",
            headers=headers,
            params={"level": "all"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None
    return _parse_status(payload, title) or ""


class XboxStatusReader:
    def __init__(self, title: str | None = None):
        self._title = title
        self._xauth = grab_xauth()

    def poll(self) -> str | None:
        if not self._xauth:
            self._xauth = grab_xauth()
            if not self._xauth:
                return None
        status = _fetch_current_status(self._xauth, self._title)
        if status is None:
            self._xauth = grab_xauth()
            if self._xauth:
                status = _fetch_current_status(self._xauth, self._title)
        return status or None

    def close(self):
        pass
