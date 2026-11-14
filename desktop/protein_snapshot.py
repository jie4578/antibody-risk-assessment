"""Desktop source acquisition: SQLite opens only verified private copies."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile

STRATEGY='ISOLATED_LOCKED_ROLLBACK_COPY_V1'
SUFFIXES=('-wal','-shm','-journal')


def _identity(value):
    return (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)


def _check_path(path):
    path=Path(path)
    if str(path).startswith(('\\\\','//')):raise ValueError('LOCAL_SOURCE_REQUIRED')
    path=path.resolve(strict=True)
    if str(path).startswith(('\\\\','//')) or not path.is_file():raise ValueError('LOCAL_SOURCE_REQUIRED')
    return path


def _sidecars(path):
    for suffix in SUFFIXES:
        try:Path(str(path)+suffix).lstat()
        except FileNotFoundError:continue
        except OSError as exc:raise ValueError('SOURCE_SIDECAR_UNVERIFIABLE: '+str(exc)) from exc
        raise ValueError('SOURCE_SIDECAR_PRESENT: checkpoint/离线审核后重试；不恢复或删除日志')


@contextmanager
def _locked_stream(path):
    """Windows sharing denies writers/replacement. POSIX locks SQLite lock bytes.

    POSIX locks are cooperative: raw writes are additionally checked using full
    byte hashes and inode/ctime/mtime. Not an adversarial filesystem certificate.
    No SQLite connection is opened to the source.
    """
    # Native CreateFileW must remain observable by Python's existing audit hooks.
    sys.audit('open',str(path),'rb',os.O_RDONLY)
    if os.name=='nt':
        import ctypes,msvcrt
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype=wintypes.HANDLE
        handle=kernel.CreateFileW(str(path),0x80000000,1,None,3,0x80,None)
        if handle==ctypes.c_void_p(-1).value:
            raise sqlite3.OperationalError('SOURCE_LOCKED: database is locked or unavailable (Win32 '+str(ctypes.get_last_error())+')')
        try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
        except BaseException:
            kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle(handle);raise
        with os.fdopen(fd,'rb') as stream:yield stream
    elif os.name=='posix':
        import fcntl
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as stream:
            try:fcntl.lockf(stream.fileno(),fcntl.LOCK_SH|fcntl.LOCK_NB,512,0x40000000,os.SEEK_SET)
            except OSError as exc:raise sqlite3.OperationalError('SOURCE_LOCKED: database is locked') from exc
            try:yield stream
            finally:fcntl.lockf(stream.fileno(),fcntl.LOCK_UN,512,0x40000000,os.SEEK_SET)
    else:raise ValueError('SOURCE_LOCK_STRATEGY_UNSUPPORTED')


def _digest(stream,destination=None):
    stream.seek(0);result=hashlib.sha256()
    for block in iter(lambda:stream.read(1024*1024),b''):
        result.update(block)
        if destination is not None:destination.write(block)
    return result.hexdigest()


def _header(stream):
    stream.seek(0);header=stream.read(100)
    if len(header)!=100 or header[:16]!=b'SQLite format 3\x00':raise ValueError('INVALID_SQLITE_HEADER')
    if header[18:20]!=b'\x01\x01':raise ValueError('WAL_FORMAT_REJECTED: WAL 需要独立 checkpoint/离线审核')


def _observe(stream,path):
    _sidecars(path);_header(stream)
    value=os.fstat(stream.fileno());named=path.stat()
    if not stat.S_ISREG(value.st_mode) or (value.st_dev,value.st_ino)!=(named.st_dev,named.st_ino):
        raise ValueError('SOURCE_IDENTITY_CHANGED')
    return _identity(value)


@dataclass(frozen=True)
class SourceSnapshot:
    source:Path
    copy:Path
    sha256:str
    identity:tuple

    def validate(self):
        with _locked_stream(self.source) as stream:
            identity=_observe(stream,self.source);before=_digest(stream)
            after=_observe(stream,self.source)
            if identity!=after or after!=self.identity or before!=self.sha256:
                raise ValueError('SOURCE_CHANGED: 来源已变化；旧审核失效')


@contextmanager
def isolated_source(path):
    source=_check_path(path)
    _sidecars(source)
    # Windows mkdir(0700) ACL support is backported to these maintained versions.
    if os.name=='nt':
        minimum={10:(3,10,15),11:(3,11,10),12:(3,12,4)}.get(sys.version_info.minor,(3,13,0))
        if sys.version_info[:3]<minimum:raise ValueError('PRIVATE_TEMP_ACL_UNSUPPORTED_PYTHON')
    base=os.environ.get('RUNNER_TEMP')
    if base is None and os.environ.get('LOCALAPPDATA'):
        base=str(Path(os.environ['LOCALAPPDATA'])/'AntibodyRiskAssessment'/'private-snapshots')
        Path(base).mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='protein-mm-private-',dir=base) as directory:
        copy=Path(directory)/'source.sqlite3'
        with _locked_stream(source) as stream:
            identity=_observe(stream,source);before=_digest(stream)
            with copy.open('xb') as target:
                copied=_digest(stream,target);target.flush()
            # Ephemeral copy needs byte equality, not crash durability. Reread
            # the closed copy before SQLite use; report publication still fsyncs.
            with copy.open('rb') as stored:stored_hash=_digest(stored)
            after=_digest(stream)
            if before!=copied or copied!=stored_hash or copied!=after or identity!=_observe(stream,source):
                raise ValueError('SOURCE_CHANGED_DURING_COPY')
        snapshot=SourceSnapshot(source,copy,copied,identity)
        # Source handle is released. Only the private, verified copy is opened by
        # SQLite. Any later source change is checked before publishing records.
        yield snapshot
        with copy.open('rb') as acquired:
            if _digest(acquired)!=snapshot.sha256:raise ValueError('PRIVATE_COPY_CHANGED')
        snapshot.validate()
