import getpass
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

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

_WIN_USER_RX = re.compile(rb"(?<![A-Za-z0-9_])[A-Za-z]:\\" + b"Users" + rb"\\([^\\\s\"'<>|\x00]{1,80})", re.I)
_POSIX_HOME_RX = re.compile(rb"(?<![A-Za-z0-9_/])/(?:home|" + b"Users)/([A-Za-z0-9_.-]+)")
_TOKEN_RX = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})")

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "logs", "results", ".venv", "node_modules", "build"}


def _collect_markers():
    markers = set()
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
            markers.add(item.strip())
    return [
        re.compile(rb"(?<![A-Za-z0-9_])" + re.escape(m.encode("utf-8")) + rb"(?![A-Za-z0-9_])", re.I)
        for m in sorted(markers, key=len, reverse=True)
    ]


def _is_vendor_internal(path_str: str) -> bool:
    norm = path_str.replace("\\", "/").lower()
    if "/_internal/" in norm:
        sub = norm.split("/_internal/", 1)[1]
    elif norm.startswith("_internal/"):
        sub = norm.split("_internal/", 1)[1]
    else:
        return False
    if os.path.splitext(norm)[1] in _VENDOR_PATH_SKIP_EXT:
        return True
    return sub.startswith(_VENDOR_INTERNAL_PREFIXES)


def _scan_payload(raw: bytes, label: str, marker_rxs: list, hits: list, check_paths: bool = True) -> None:
    if check_paths:
        for m in _WIN_USER_RX.finditer(raw):
            if m.group(1).decode("utf-8", errors="ignore").lower() not in _SAFE_UPSTREAM_PATH_USERS:
                hits.append(f"{label}: Windows user profile path")
        for m in _POSIX_HOME_RX.finditer(raw):
            if m.group(1).decode("utf-8", errors="ignore").lower() not in _SAFE_UPSTREAM_PATH_USERS:
                hits.append(f"{label}: POSIX home path")
    if _TOKEN_RX.search(raw):
        hits.append(f"{label}: GitHub token pattern")
    for rx in marker_rxs:
        if rx.search(raw):
            hits.append(f"{label}: local identity marker")


def scan_path(target_dir: str) -> int:
    target = Path(target_dir)
    if not target.exists():
        print(f"Missing target: {target_dir}")
        return 1

    marker_rxs = _collect_markers()
    hits = []

    skip_dirs = set(SKIP_DIRS)
    if (target / ".git").exists():
        skip_dirs.add("data")

    files = [target] if target.is_file() else []
    if target.is_dir():
        for root, dirs, fnames in os.walk(target):
            dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]
            for fn in fnames:
                files.append(Path(root) / fn)

    for p in files:
        if p.suffix.lower() in (".png", ".ico", ".webp", ".jpg", ".gif"):
            continue
        try:
            raw = p.read_bytes()
        except Exception as e:
            hits.append(f"{p}: read error {e}")
            continue

        check_paths = not _is_vendor_internal(str(p))
        _scan_payload(raw, str(p), marker_rxs, hits, check_paths=check_paths)

        if p.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(p, "r") as z:
                    for info in z.infolist():
                        if not info.filename.endswith("/"):
                            if os.path.splitext(info.filename)[1].lower() in (".png", ".ico", ".webp", ".jpg", ".gif"):
                                continue
                            try:
                                _scan_payload(
                                    z.read(info.filename),
                                    f"{p}::{info.filename}",
                                    marker_rxs,
                                    hits,
                                    check_paths=not _is_vendor_internal(info.filename),
                                )
                            except Exception:
                                pass
            except Exception as e:
                hits.append(f"{p}: zip error {e}")

    if hits:
        print("DEEP SCAN FOUND LEAKS:")
        for h in hits[:40]:
            print("  -", h)
        return 1
    print(f"DEEP_SCAN_OK target={target_dir} files={len(files)}")
    return 0


def main() -> int:
    targets = sys.argv[1:] or ["dist/Pinion"]
    for t in targets:
        if scan_path(t) != 0:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
