import argparse
import ctypes
import getpass
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from ctypes import wintypes
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import pefile
except ImportError:
    pefile = None

EPOCH_1980 = 315532800
ZIP_DT = (1980, 1, 1, 0, 0, 0)

_CI_SAFE_USERS = {
    "runneradmin",
    "runner",
    "actions",
    "vscode",
    "root",
    "system",
    "administrator",
    "defaultuser0",
    "pinion",
    "pinion@users.noreply.github.com",
}

_SAFE_UPSTREAM_PATH_USERS = {
    "runneradmin",
    "runner",
    "vssadministrator",
    "containeradministrator",
    "actions",
    "user",
}

_WIN_USER_RX = re.compile(rb"(?<![A-Za-z0-9_])[A-Za-z]:\\" + b"Users" + rb"\\([^\\\s\"'<>|\x00]{1,80})", re.I)
_POSIX_HOME_RX = re.compile(rb"(?<![A-Za-z0-9_/])/(?:home|" + b"Users)/([A-Za-z0-9_.-]+)")

_ALWAYS_BYTES_PATTERNS = [
    re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(rb"\b" + b"CL" + b"AUDE" + rb"\.md\b", re.I),
    re.compile(rb"\b" + b"GA" + b"TES" + rb"\.md\b", re.I),
    re.compile(rb"(?<![A-Za-z0-9_])\." + b"un" + b"lazy" + rb"(?![A-Za-z0-9_])", re.I),
]

_VENDOR_PATH_SKIP_EXT = {".dll", ".pyd", ".so"}
_VENDOR_INTERNAL_PREFIXES = (
    "webview/",
    "clr_loader/",
    "cryptography/",
    "bcrypt/",
    "pythonnet/",
    "certifi/",
    "setuptools/",
)

IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", "logs", "results", ".venv", "node_modules", "build"}
SCAN_SKIP_EXT = {".png", ".ico", ".webp", ".jpg", ".gif", ".ttf", ".otf", ".woff", ".woff2"}


_DYNAMIC_MARKERS_CACHE = None


def _collect_dynamic_markers(extra_markers=None):
    global _DYNAMIC_MARKERS_CACHE
    if _DYNAMIC_MARKERS_CACHE is None:
        base = set()
        candidates = [
            os.environ.get("USERNAME", ""),
            os.environ.get("USER", ""),
            Path.home().name,
        ]
        try:
            candidates.append(getpass.getuser())
        except Exception:
            pass
        try:
            for key in ("user.name", "user.email"):
                val = subprocess.check_output(
                    ["git", "config", "--get", key],
                    stderr=subprocess.DEVNULL,
                    text=True,
                ).strip()
                if val:
                    candidates.append(val)
                    if "@" in val:
                        candidates.append(val.split("@", 1)[0])
        except Exception:
            pass
        for env_key in ("PRIVATE_MARKERS", "SCRUB_MARKERS"):
            raw = os.environ.get(env_key, "")
            for part in raw.split(","):
                part = part.strip()
                if part:
                    candidates.append(part)
        for item in candidates:
            low = item.strip().lower()
            if len(low) >= 3 and low not in _CI_SAFE_USERS:
                base.add(item.strip())
        _DYNAMIC_MARKERS_CACHE = tuple(sorted(base, key=len, reverse=True))
    markers = set(_DYNAMIC_MARKERS_CACHE)
    if extra_markers:
        for item in extra_markers:
            low = item.strip().lower()
            if len(low) >= 3 and low not in _CI_SAFE_USERS:
                markers.add(item.strip())
    return sorted(markers, key=len, reverse=True)


def set_win_file_times(path: str, epoch_sec: int) -> bool:
    try:
        os.utime(path, (epoch_sec, epoch_sec))
    except OSError:
        return False

    if sys.platform != "win32":
        return True

    try:
        wintime = int((epoch_sec + 11644473600) * 10000000)
        low = wintime & 0xFFFFFFFF
        high = wintime >> 32
        ft = wintypes.FILETIME(low, high)

        FILE_WRITE_ATTRIBUTES = 0x0100
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

        handle = ctypes.windll.kernel32.CreateFileW(
            str(path),
            FILE_WRITE_ATTRIBUTES,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle == -1 or handle == ctypes.c_void_p(-1).value:
            return False
        try:
            ctypes.windll.kernel32.SetFileTime(
                handle, ctypes.byref(ft), ctypes.byref(ft), ctypes.byref(ft)
            )
            return True
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return False


def remove_ads_zone_identifier(path: str) -> None:
    if sys.platform != "win32":
        return
    zone_path = f"{path}:Zone.Identifier"
    if os.path.exists(zone_path):
        try:
            ctypes.windll.kernel32.DeleteFileW(zone_path)
        except Exception:
            pass


def clean_zip_file(path: str) -> bool:
    with zipfile.ZipFile(path, "r") as z:
        if all(i.date_time == ZIP_DT and not i.extra for i in z.infolist()):
            return False
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    tmp = f"{path}.clean.tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        for info, data in items:
            ni = zipfile.ZipInfo(info.filename, ZIP_DT)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            ni.internal_attr = info.internal_attr
            ni.create_system = info.create_system
            z.writestr(ni, data)
    os.replace(tmp, path)
    return True


def clean_pe_file(path: str, epoch_sec: int = EPOCH_1980) -> bool:
    if not pefile:
        raise RuntimeError("pefile module is required to clean PE files")
    try:
        with open(path, "rb") as f:
            raw = f.read()
        pe = pefile.PE(data=raw, fast_load=False)
        data = bytearray(raw)
        pe.FILE_HEADER.TimeDateStamp = epoch_sec

        if hasattr(pe, "DIRECTORY_ENTRY_DEBUG"):
            for dbg in pe.DIRECTORY_ENTRY_DEBUG:
                dbg.struct.TimeDateStamp = epoch_sec
                if hasattr(dbg, "entry") and dbg.entry is not None and hasattr(dbg.entry, "PdbFileName"):
                    pdb_bytes = dbg.entry.PdbFileName
                    if b"\\" in pdb_bytes or b"/" in pdb_bytes:
                        clean_name = Path(pdb_bytes.decode("utf-8", errors="ignore").rstrip("\x00")).name
                        new_pdb = clean_name.encode("utf-8") + b"\x00"
                        raw_off = dbg.struct.PointerToRawData
                        if raw_off > 0 and raw_off + 24 + len(pdb_bytes) <= len(data):
                            old_slice = data[raw_off + 24 : raw_off + 24 + len(pdb_bytes)]
                            if pdb_bytes.rstrip(b"\x00") in old_slice:
                                padded = new_pdb.ljust(len(pdb_bytes), b"\x00")[: len(pdb_bytes)]
                                data[raw_off + 24 : raw_off + 24 + len(pdb_bytes)] = padded

        if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            pe.DIRECTORY_ENTRY_EXPORT.struct.TimeDateStamp = epoch_sec

        if hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
            pe.DIRECTORY_ENTRY_RESOURCE.struct.TimeDateStamp = epoch_sec
            for entry in getattr(pe.DIRECTORY_ENTRY_RESOURCE, "entries", []):
                if hasattr(entry, "directory") and entry.directory:
                    entry.directory.struct.TimeDateStamp = epoch_sec

        pe.close()
        pe2 = pefile.PE(data=bytes(data), fast_load=False)
        pe2.FILE_HEADER.TimeDateStamp = epoch_sec
        if hasattr(pe2, "DIRECTORY_ENTRY_DEBUG"):
            for dbg in pe2.DIRECTORY_ENTRY_DEBUG:
                dbg.struct.TimeDateStamp = epoch_sec
        if hasattr(pe2, "DIRECTORY_ENTRY_EXPORT"):
            pe2.DIRECTORY_ENTRY_EXPORT.struct.TimeDateStamp = epoch_sec
        if hasattr(pe2, "DIRECTORY_ENTRY_RESOURCE"):
            pe2.DIRECTORY_ENTRY_RESOURCE.struct.TimeDateStamp = epoch_sec
            for entry in getattr(pe2.DIRECTORY_ENTRY_RESOURCE, "entries", []):
                if hasattr(entry, "directory") and entry.directory:
                    entry.directory.struct.TimeDateStamp = epoch_sec

        pe2.OPTIONAL_HEADER.CheckSum = 0
        pe2.OPTIONAL_HEADER.CheckSum = pe2.generate_checksum()
        final_data = bytearray(pe2.write())
        pe2.close()

        with open(path, "wb") as f:
            f.write(final_data)
        return True
    except Exception as e:
        print(f"[WARN] PE cleanup error for {path}: {e}", file=sys.stderr)
        return False


def _is_vendor_internal(path_str: str) -> bool:
    norm = path_str.replace("\\", "/").lower()
    if "/_internal/" in norm:
        sub = norm.split("/_internal/", 1)[1]
    elif norm.startswith("_internal/"):
        sub = norm.split("_internal/", 1)[1]
    else:
        return False
    ext = os.path.splitext(norm)[1]
    if ext in _VENDOR_PATH_SKIP_EXT:
        return True
    return sub.startswith(_VENDOR_INTERNAL_PREFIXES)


def scan_bytes_for_leaks(raw_bytes: bytes, label_prefix: str, extra_markers=None, check_generic_paths: bool = True) -> list[str]:
    errors = []
    if check_generic_paths:
        for rx in (_WIN_USER_RX, _POSIX_HOME_RX):
            for m in rx.finditer(raw_bytes):
                user_part = m.group(1).decode("utf-8", errors="ignore").lower()
                if user_part not in _SAFE_UPSTREAM_PATH_USERS:
                    errors.append(f"{label_prefix}: matched user path ({user_part})")
    for pattern in _ALWAYS_BYTES_PATTERNS:
        if pattern.search(raw_bytes):
            errors.append(f"{label_prefix}: matched static leak pattern")
    for m in _collect_dynamic_markers(extra_markers=extra_markers):
        tok_rx = re.compile(rb"(?<![A-Za-z0-9_])" + re.escape(m.encode("utf-8")) + rb"(?![A-Za-z0-9_])", re.I)
        if tok_rx.search(raw_bytes):
            errors.append(f"{label_prefix}: matched local identity marker")
    return errors


def verify_file(path: str, epoch_sec: int = EPOCH_1980, extra_markers=None) -> list[str]:
    errors = []
    p = Path(path)
    if not p.is_file():
        return errors

    for part in p.parts:
        if part.lower() in IGNORED_DIRS:
            return []

    check_paths = not _is_vendor_internal(str(path))
    if p.suffix.lower() not in SCAN_SKIP_EXT:
        try:
            raw_bytes = p.read_bytes()
            errors.extend(scan_bytes_for_leaks(raw_bytes, str(path), extra_markers=extra_markers, check_generic_paths=check_paths))
        except Exception:
            pass

    if p.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path, "r") as z:
                for info in z.infolist():
                    if info.date_time != ZIP_DT:
                        errors.append(f"{path}::{info.filename}: zip date={info.date_time} != {ZIP_DT}")
                    if not info.filename.endswith("/"):
                        try:
                            if os.path.splitext(info.filename)[1].lower() in SCAN_SKIP_EXT:
                                continue
                            member_raw = z.read(info.filename)
                            member_check_paths = not _is_vendor_internal(info.filename)
                            errors.extend(
                                scan_bytes_for_leaks(
                                    member_raw,
                                    f"{path}::{info.filename}",
                                    extra_markers=extra_markers,
                                    check_generic_paths=member_check_paths,
                                )
                            )
                        except Exception:
                            pass
        except Exception as e:
            errors.append(f"{path}: zip read error: {e}")

    if p.suffix.lower() == ".exe":
        if not pefile:
            errors.append(f"{path}: pefile not installed")
        else:
            try:
                with open(path, "rb") as f:
                    pe = pefile.PE(data=f.read(), fast_load=False)
                ts = pe.FILE_HEADER.TimeDateStamp
                if ts not in (0, epoch_sec):
                    errors.append(f"{path}: PE TimeDateStamp {hex(ts)} != {hex(epoch_sec)}")
                for dbg in getattr(pe, "DIRECTORY_ENTRY_DEBUG", []) or []:
                    pdb = getattr(getattr(dbg, "entry", None), "PdbFileName", b"")
                    if pdb and (b"\\" in pdb.rstrip(b"\x00") or b"/" in pdb.rstrip(b"\x00")):
                        errors.append(f"{path}: non-clean PDB path in debug dir")
                if pe.OPTIONAL_HEADER.CheckSum != pe.generate_checksum():
                    errors.append(f"{path}: PE CheckSum mismatch")
                pe.close()
            except Exception as e:
                errors.append(f"{path}: PE parse error: {e}")

    return errors


def clean_target(target_path: str, epoch_sec: int = EPOCH_1980) -> int:
    target = Path(target_path)
    if not target.exists():
        print(f"Path not found: {target_path}", file=sys.stderr)
        return 0

    cleaned_files = 0
    if target.is_file():
        sp = str(target)
        remove_ads_zone_identifier(sp)
        if target.suffix.lower() == ".exe":
            clean_pe_file(sp, epoch_sec)
        elif target.suffix.lower() == ".zip":
            clean_zip_file(sp)
        set_win_file_times(sp, epoch_sec)
        return 1

    all_files = []
    all_dirs = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS]
        all_dirs.append(Path(root))
        for fn in files:
            all_files.append(Path(root) / fn)

    for f in all_files:
        sp = str(f)
        remove_ads_zone_identifier(sp)
        if f.suffix.lower() == ".exe":
            clean_pe_file(sp, epoch_sec)
        elif f.suffix.lower() == ".zip":
            clean_zip_file(sp)
        set_win_file_times(sp, epoch_sec)
        cleaned_files += 1

    for d in reversed(all_dirs):
        set_win_file_times(str(d), epoch_sec)

    return cleaned_files


def verify_target(target_path: str, epoch_sec: int = EPOCH_1980) -> list[str]:
    target = Path(target_path)
    if not target.exists():
        return [f"Path does not exist: {target_path}"]

    ignore = set(IGNORED_DIRS)
    if (target / ".git").exists():
        ignore.add("data")

    all_errors = []
    if target.is_file():
        return verify_file(str(target), epoch_sec)

    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d.lower() not in ignore]
        for fn in files:
            all_errors.extend(verify_file(str(Path(root) / fn), epoch_sec))
    return all_errors


def run_selftest() -> int:
    drv = "C:" + "\\"
    sample_dirty = (drv + "Users" + "\\sample_user\\Desktop ghp_" + ("A" * 36)).encode("utf-8")
    hits = scan_bytes_for_leaks(sample_dirty, "<selftest>", extra_markers=["sample_user"])
    if len(hits) < 3:
        print("SELFTEST FAILED: leak scanner did not catch synthetic sample", file=sys.stderr)
        return 1

    tmp_dir = tempfile.mkdtemp(prefix="pinion_clean_selftest_")
    try:
        zpath = os.path.join(tmp_dir, "sample.zip")
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("ok.txt", b"clean payload")
        clean_zip_file(zpath)
        errs = verify_file(zpath)
        if errs:
            print(f"SELFTEST FAILED: zip cleanup check failed: {errs}", file=sys.stderr)
            return 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("METADATA_SELFTEST_OK")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Pinion metadata cleaner & verifier")
    parser.add_argument("--verify", action="store_true", help="Verify paths for leaks and timestamps")
    parser.add_argument("--selftest", action="store_true", help="Run negative-control self-test")
    parser.add_argument("action_or_target", nargs="*", help="[clean] <path>")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    targets = [t for t in args.action_or_target if t != "clean"]
    if not targets:
        targets = ["."]

    if args.verify:
        all_errors = []
        for t in targets:
            all_errors.extend(verify_target(t))
        if all_errors:
            print("METADATA VERIFICATION FAILED:", file=sys.stderr)
            for err in all_errors[:40]:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)
        print("METADATA_VERIFY_OK")
        sys.exit(0)
    else:
        for t in targets:
            count = clean_target(t)
            print(f"Cleaned {count} items in {t}")
            set_win_file_times(t, EPOCH_1980)
        print("METADATA_CLEAN_OK")
        sys.exit(0)


if __name__ == "__main__":
    main()
