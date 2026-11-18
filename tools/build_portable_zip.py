# -*- coding: utf-8 -*-
"""Сборка детерминированного портативного ZIP-архива Pinion без метаданных."""
import os
import sys
import zipfile
from pathlib import Path

EPOCH_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def build_portable_zip(src_dir: str = "dist/Pinion", out_zip: str = "dist/Pinion-portable.zip") -> str:
    src = Path(src_dir)
    out = Path(out_zip)
    if not src.exists():
        raise FileNotFoundError(f"Source dir {src_dir} does not exist")

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    with zipfile.ZipFile(str(out), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src):
            dirs.sort()
            files.sort()
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, src)
                archive_name = os.path.join("Pinion", rel_path).replace("\\", "/")

                with open(full_path, "rb") as fp:
                    data = fp.read()

                zinfo = zipfile.ZipInfo(archive_name, date_time=EPOCH_ZIP_TIME)
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                # Права доступа (Unix / Windows compatible)
                zinfo.external_attr = 0o755 << 16 if f.lower().endswith((".exe", ".dll", ".pyd")) else 0o644 << 16
                zf.writestr(zinfo, data)

    size_mb = round(out.stat().st_size / (1024 * 1024), 1)
    print(f"PORTABLE_ZIP_OK: {out} ({size_mb} MB)")
    return str(out)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "dist/Pinion"
    dst = sys.argv[2] if len(sys.argv) > 2 else "dist/Pinion-portable.zip"
    build_portable_zip(src, dst)
