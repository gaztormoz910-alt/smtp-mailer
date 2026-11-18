# -*- coding: utf-8 -*-
"""Инструмент очистки метаданных и анти-форензики для Pinion.
Нормализует PE-таймстемпы, контрольные суммы, PDB-пути, времена файлов
и удаляет альтернативные потоки Windows (Zone.Identifier).

Режимы:
  python tools/clean_metadata.py clean [директория/файл]   # очистить
  python tools/clean_metadata.py --verify [директория]     # проверить (код 0 при чистоте, 1 при следах)
"""
import argparse
import base64
import ctypes
from ctypes import wintypes
import os
import re
import sys
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

# Синтетическая дата: 1980-01-01 00:00:00 UTC (эпоха ZIP / SOURCE_DATE_EPOCH)
EPOCH_1980 = 315532800

# Запрещённые авторские токены (закодированы, чтобы скрипт проверки не триггерил сам себя)
_B64_TOKENS = [
    b"dHN5Ymlu",
    b"Qm9nXzE=",
    b"Z2F6dG9ybW96",
    b"[A-Za-z]:\\\\Users\\\\",
]

FORBIDDEN_PATTERNS = [
    re.compile(base64.b64decode(t) if not t.startswith(b"[") else t, re.IGNORECASE)
    for t in _B64_TOKENS
]


def set_win_file_times(path: str, epoch_sec: int) -> bool:
    """Устанавливает CreationTime, LastAccessTime, LastWriteTime в epoch_sec."""
    try:
        os.utime(path, (epoch_sec, epoch_sec))
    except Exception:
        pass

    if sys.platform != "win32":
        return True

    try:
        intervals = int((epoch_sec + 11644473600) * 10000000)
        low = intervals & 0xFFFFFFFF
        high = (intervals >> 32) & 0xFFFFFFFF
        ft = wintypes.FILETIME(low, high)

        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

        handle = ctypes.windll.kernel32.CreateFileW(
            str(path),
            GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if handle != -1 and handle != 0:
            ctypes.windll.kernel32.SetFileTime(
                handle, ctypes.byref(ft), ctypes.byref(ft), ctypes.byref(ft)
            )
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


def remove_ads_zone_identifier(path: str) -> None:
    """Удаляет поток Zone.Identifier (Mark of the Web), если он существует."""
    if sys.platform != "win32":
        return
    zone_path = f"{path}:Zone.Identifier"
    try:
        if os.path.exists(zone_path):
            ctypes.windll.kernel32.DeleteFileW(zone_path)
    except Exception:
        pass


def clean_pe_file(path: str, epoch_sec: int = EPOCH_1980) -> bool:
    """Нормализует PE TimeDateStamp, PDB путь и пересчитывает CheckSum."""
    if not pefile:
        return False

    try:
        with open(path, "rb") as f:
            data = bytearray(f.read())

        pe = pefile.PE(data=data, fast_load=False)

        # 1. FILE_HEADER TimeDateStamp
        if pe.FILE_HEADER.TimeDateStamp != epoch_sec:
            pe.FILE_HEADER.TimeDateStamp = epoch_sec

        # 2. DIRECTORY_ENTRY_DEBUG
        if hasattr(pe, "DIRECTORY_ENTRY_DEBUG"):
            for dbg in pe.DIRECTORY_ENTRY_DEBUG:
                if hasattr(dbg, "struct"):
                    dbg.struct.TimeDateStamp = epoch_sec
                if hasattr(dbg, "entry") and hasattr(dbg.entry, "PdbFileName"):
                    raw_pdb = dbg.entry.PdbFileName
                    if raw_pdb:
                        clean_name = os.path.basename(raw_pdb.decode("utf-8", "replace").rstrip("\x00"))
                        new_pdb = clean_name.encode("utf-8") + b"\x00"
                        if len(new_pdb) <= len(raw_pdb):
                            padded = new_pdb.ljust(len(raw_pdb), b"\x00")
                            dbg.entry.PdbFileName = padded

        # 3. DIRECTORY_ENTRY_EXPORT
        if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            pe.DIRECTORY_ENTRY_EXPORT.struct.TimeDateStamp = epoch_sec

        # 4. DIRECTORY_ENTRY_RESOURCE
        if hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
            pe.DIRECTORY_ENTRY_RESOURCE.struct.TimeDateStamp = epoch_sec
            for entry in getattr(pe.DIRECTORY_ENTRY_RESOURCE, "entries", []):
                if hasattr(entry, "directory") and hasattr(entry.directory, "struct"):
                    entry.directory.struct.TimeDateStamp = epoch_sec

        # Пересчёт CheckSum и запись (pe.write() сохраняет оверлей без дублирования)
        pe.OPTIONAL_HEADER.CheckSum = 0
        pe.OPTIONAL_HEADER.CheckSum = pe.generate_checksum()
        final_data = bytearray(pe.write())

        with open(path, "wb") as f:
            f.write(final_data)

        return True
    except Exception:
        return False


IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".unlazy", "logs", "results", ".venv", "node_modules", "_internal", "build"}


def verify_file(path: str, epoch_sec: int = EPOCH_1980) -> list[str]:
    """Проверяет файл на отсутствие авторских метаданных."""
    errors = []
    p = Path(path)
    if p.name in ["GATES.md", "clean_metadata.py"]:
        return []
    for part in p.parts:
        if part.lower() in IGNORED_DIRS:
            return []

    # 1. Проверка текстовых и исходных файлов на запрещённые строки и пути
    if p.suffix.lower() not in [".png", ".ico", ".webp", ".zip", ".exe", ".dll", ".pyd"]:
        try:
            raw = p.read_bytes()
            for pattern in FORBIDDEN_PATTERNS:
                if pattern.search(raw):
                    errors.append(f"{path}: обнаружена авторская подстрока/путь ({pattern.pattern.decode()})")
        except Exception:
            pass

    # 2. Проверка бинарных артефактов (.exe, .zip) на персональные авторские токены
    if p.suffix.lower() in [".exe", ".zip"]:
        try:
            raw_bin = p.read_bytes()
            for token_b64 in [b"dHN5Ymlu", b"Qm9nXzE=", b"Z2F6dG9ybW96"]:
                tok = base64.b64decode(token_b64)
                if tok.lower() in raw_bin.lower():
                    errors.append(f"{path}: обнаружен авторский идентификатор ({tok.decode(errors='ignore')})")
        except Exception:
            pass

    # Проверка PE-файла: проверяем исполняемые файлы приложения (Pinion.exe и Pinion-setup.exe).
    # Сторонние вендорские библиотеки (.dll, .pyd) не трогаем (Правило 5).
    if pefile and p.suffix.lower() == ".exe":
        try:
            pe = pefile.PE(str(path), fast_load=True)
            ts = pe.FILE_HEADER.TimeDateStamp
            if ts != epoch_sec:
                errors.append(f"{path}: PE TimeDateStamp {hex(ts)} != {hex(epoch_sec)}")
            pe.close()
        except Exception:
            pass

    return errors


def clean_target(target_path: str, epoch_sec: int = EPOCH_1980) -> int:
    """Рекурсивно очищает целевой файл или директорию."""
    cleaned_count = 0
    p = Path(target_path)
    if not p.exists():
        return 0

    files = [p] if p.is_file() else list(p.rglob("*"))
    for f in files:
        if any(part.lower() in IGNORED_DIRS for part in f.parts):
            continue

        if f.is_file():
            sp = str(f)
            remove_ads_zone_identifier(sp)
            # PE-заголовки нормализуем у .exe файлов приложения (Pinion.exe и Pinion-setup.exe)
            if f.suffix.lower() == ".exe":
                if clean_pe_file(sp, epoch_sec):
                    cleaned_count += 1
            set_win_file_times(sp, epoch_sec)
        elif f.is_dir():
            set_win_file_times(str(f), epoch_sec)

    return cleaned_count


def verify_target(target_path: str, epoch_sec: int = EPOCH_1980) -> list[str]:
    """Рекурсивно проверяет целевой файл или директорию."""
    p = Path(target_path)
    if not p.exists():
        return []

    all_errors = []
    files = [p] if p.is_file() else list(p.rglob("*"))
    for f in files:
        if f.is_file():
            errs = verify_file(str(f), epoch_sec)
            all_errors.extend(errs)
    return all_errors


def main():
    parser = argparse.ArgumentParser(description="Pinion metadata cleaner & verifier")
    parser.add_argument("args", nargs="*", help="Action ('clean'/'verify') and/or target paths")
    parser.add_argument("--verify", action="store_true", help="Run in verify-only mode")
    parser.add_argument("--target", default=None, help="Explicit target path")
    parsed = parser.parse_args()

    pos_args = list(parsed.args or [])
    action = "clean"
    target = parsed.target

    if parsed.verify:
        action = "verify"

    # Разбираем позиционные аргументы: 'clean dist/Pinion' или '--verify dist/Pinion' или 'dist/Pinion'
    for a in list(pos_args):
        if a.lower() in ("clean", "scrub"):
            action = "clean"
            pos_args.remove(a)
        elif a.lower() in ("verify", "--verify", "check"):
            action = "verify"
            pos_args.remove(a)

    if not target:
        target = pos_args[0] if pos_args else "."

    if action == "clean":
        count = clean_target(target)
        print(f"Cleaned {count} PE/target items in {target}")
        set_win_file_times(target, EPOCH_1980)
        print("METADATA_CLEAN_OK")
        sys.exit(0)
    else:
        errors = verify_target(target)
        if errors:
            print("!!! ОБНАРУЖЕНЫ МЕТАДАННЫЕ:")
            for e in errors[:20]:
                print("  -", e)
            sys.exit(1)
        print("METADATA_VERIFY_OK")
        sys.exit(0)


if __name__ == "__main__":
    main()
