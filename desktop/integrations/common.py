"""Bounded, local-only result snapshots and plain-data presentation contracts."""
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys

MAX_JSON = 4 * 1024 * 1024
MAX_ARTIFACT = 32 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_ITEMS = 500


class IntegrationError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code + ": " + message)


def require(condition, code="INVALID_STRUCTURE", message="结果合同字段缺失、类型错误或内容不一致"):
    if not condition:
        raise IntegrationError(code, message)


def text(value):
    require(isinstance(value, str) and 0 < len(value) <= 4096)
    require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value), "INVALID_TEXT", "字段含非文本控制字符")
    return value


def array(value):
    require(isinstance(value, list) and len(value) <= MAX_ITEMS)
    return value


def mapping(value):
    require(isinstance(value, dict))
    return value


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None,
            "INVALID_HASH", "SHA256 格式错误")
    return value.lower()


def integer(value):
    require(type(value) is int and value >= 0)
    return value


def _identity(s):
    # On Windows/Python 3.13, path-stat ctime can mean creation time while
    # handle-fstat ctime means change time. Birthtime has the same meaning on
    # both paths; write/delete sharing locks plus full rehashing guard content.
    last = getattr(s, "st_birthtime_ns", s.st_ctime_ns) if os.name == "nt" else s.st_ctime_ns
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, last


def _regular(s, directory=False):
    require(not stat.S_ISLNK(s.st_mode) and not getattr(s, "st_file_attributes", 0) & 0x400,
            "UNSAFE_LINK", "不支持符号链接、junction 或其他重解析点")
    require(stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode),
            "UNSAFE_FILE_TYPE", "只接受普通本地文件与目录")


@contextmanager
def _pinned_file(path):
    """Pin parents against link/rename races; never create a file or directory.

    POSIX uses descriptor-relative O_NOFOLLOW traversal. Windows pins every
    parent and leaf without write/delete sharing (including reparse mutation),
    and never follows a leaf reparse point. Hashes demonstrate consistency, not authenticity.
    """
    with ExitStack() as stack:
        if os.name == "posix":
            parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
            stack.callback(os.close, parent)
            for part in path.parts[1:-1]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                stack.callback(os.close, parent)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            stream = stack.enter_context(os.fdopen(fd, "rb"))
        elif os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                          ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            kernel.CreateFileW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]

            def open_handle(target, directory):
                sys.audit("open", str(target), "rb", os.O_RDONLY)
                _regular(target.lstat(), directory)
                handle = kernel.CreateFileW(str(target), 0x80 if directory else 0x80000000,
                                            1, None, 3,
                                            0x00200000 | (0x02000000 if directory else 0x80), None)
                if handle == ctypes.c_void_p(-1).value:
                    raise IntegrationError("SOURCE_UNAVAILABLE", "文件被锁定、无权限或不可读取")
                return handle

            for parent in reversed(path.parents):
                handle = open_handle(parent, True)
                stack.callback(kernel.CloseHandle, handle)
                _regular(parent.lstat(), True)
            handle = open_handle(path, False)
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            except BaseException:
                kernel.CloseHandle(handle)
                raise
            stream = stack.enter_context(os.fdopen(fd, "rb"))
        else:
            raise IntegrationError("UNSUPPORTED_PLATFORM", "当前平台没有安全只读文件策略")
        _regular(os.fstat(stream.fileno()))
        yield stream


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_JSON_KEY", "JSON 含重复字段")
        result[key] = value
    return result


def _bounded(value, depth=0, count=None):
    count = count if count is not None else [0]
    count[0] += 1
    require(depth <= 40 and count[0] <= 100000, "JSON_COMPLEXITY_LIMIT", "JSON 嵌套或节点数量过大")
    if isinstance(value, float):
        require(math.isfinite(value), "NONFINITE_JSON", "JSON 含非有限数值")
    elif isinstance(value, dict):
        for item in value.values():
            _bounded(item, depth + 1, count)
    elif isinstance(value, list):
        for item in value:
            _bounded(item, depth + 1, count)


class ResultDirectory:
    """Authorization scope is the explicitly selected manifest's parent only."""
    def __init__(self, selected):
        require(selected is not None and bool(str(selected)), "NO_SELECTION", "请明确选择本地 manifest")
        self.manifest = Path(os.path.abspath(selected))
        require(not str(self.manifest).startswith(("\\\\", "//")), "UNSAFE_PATH", "不支持网络路径")
        self.root = self.manifest.parent
        for parent in reversed(self.manifest.parents):
            _regular(parent.lstat(), True)
        self.root_identity = _identity(self.root.stat())[:2]
        self.total = 0
        self.ledger = {}

    def path(self, value):
        value = text(value)
        require(not any(ord(c) < 32 for c in value), "UNSAFE_PATH", "路径含控制字符")
        windows = PureWindowsPath(value)
        require(not value.startswith(("\\\\", "//")) and ":" not in value.replace(str(windows.drive), "", 1),
                "UNSAFE_PATH", "拒绝网络路径或备用数据流")
        parts = value.replace("\\", "/").split("/")
        require(".." not in parts and "." not in parts, "UNSAFE_PATH", "拒绝路径跳转")
        require(not any(p.rstrip(" .") != p for p in parts), "UNSAFE_PATH", "拒绝不明确的文件名")
        require(not any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p) for p in parts),
                "UNSAFE_PATH", "拒绝设备路径")
        candidate = Path(value.replace("\\", "/"))
        if windows.drive and os.name != "nt":
            raise IntegrationError("UNSAFE_PATH", "异平台绝对路径不可自动重映射")
        if not candidate.is_absolute():
            require(not windows.drive, "UNSAFE_PATH", "拒绝盘符相对路径")
            candidate = self.root / candidate
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise IntegrationError("UNSAFE_PATH", "结果路径越出已授权 manifest 目录") from exc
        return candidate

    def read(self, path, limit=MAX_JSON):
        require(path == self.manifest or self.root in path.parents, "UNSAFE_PATH", "文件越界")
        with _pinned_file(path) as stream:
            before = os.fstat(stream.fileno())
            require(before.st_size <= limit, "FILE_TOO_LARGE", "文件超过只读接入大小限制")
            data = stream.read(limit + 1)
            self.total += len(data)
            require(len(data) <= limit and self.total <= MAX_TOTAL, "FILE_TOO_LARGE", "文件或累计读取量过大")
            after = os.fstat(stream.fileno())
            require(_identity(before) == _identity(after) == _identity(path.lstat()),
                    "SOURCE_CHANGED", "读取时来源发生变化")
            fingerprint = hashlib.sha256(data).hexdigest()
            old = self.ledger.get(path)
            observed = (_identity(after), fingerprint)
            require(old is None or old == observed, "SOURCE_CHANGED", "同次接入来源快照不一致")
            self.ledger[path] = observed
            return data

    def json(self, path, object_only=True):
        try:
            value = json.loads(self.read(path).decode("utf-8-sig"), object_pairs_hook=_pairs,
                               parse_constant=lambda _: require(False, "NONFINITE_JSON", "JSON 含非有限常量"))
            _bounded(value)
            return mapping(value) if object_only else value
        except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
            raise IntegrationError("INVALID_JSON", "文件不是有效、受限的 UTF-8 JSON") from exc

    def finish(self):
        for path in tuple(self.ledger):
            self.read(path, MAX_ARTIFACT)
        require(_identity(self.root.stat())[:2] == self.root_identity, "SOURCE_CHANGED", "结果目录已被替换")


@dataclass(frozen=True)
class Artifact:
    path: str
    role: str
    exists: bool
    hash_status: str
    declared_sha256: str | None = None
    observed_sha256: str | None = None


@dataclass(frozen=True)
class Evidence:
    document_id: str
    source_content_sha256: str | None
    quote: str
    page_start: int | None
    page_end: int | None
    upstream_verified: bool
    quality_flags: tuple[str, ...]
    source_file: str | None = None
    source_alias: str | None = None
    batch_id: str | None = None


@dataclass(frozen=True)
class ResultSummary:
    project: str
    contract_revision: str
    schema_version: str
    identifier: str
    state: str
    source_state: str
    experiment: str
    manifest_path: str
    manifest_sha256: str
    artifacts: tuple[Artifact, ...]
    declared_sources: tuple[str, ...]
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    counts: tuple[tuple[str, int], ...] = ()
    evidence: tuple[Evidence, ...] = ()
    producer_versions: tuple[tuple[str, str], ...] = ()

    def as_dict(self):
        value = asdict(self)
        json.dumps(value, allow_nan=False)
        return value


def artifact(directory, value, role, expected=None, size=None, read_bytes=True):
    path = directory.path(value)
    try:
        _regular(path.lstat())
    except FileNotFoundError:
        return Artifact(value, role, False, "MISSING", expected)
    # Parent links are checked by the pinned reader even when only inventory is wanted.
    with _pinned_file(path) as stream:
        info = os.fstat(stream.fileno())
        if size is not None:
            require(info.st_size == size, "HASH_MISMATCH", "产物大小与声明不符")
    if not read_bytes:
        return Artifact(value, role, True, "NOT_READ_SOURCE_DATA", expected)
    observed = hashlib.sha256(directory.read(path, MAX_ARTIFACT)).hexdigest()
    require(expected is None or observed == expected, "HASH_MISMATCH", "产物 SHA256 与声明不符")
    return Artifact(value, role, True, "CONTENT_HASH_MATCH" if expected else "OBSERVED_HASH_ONLY", expected, observed)
