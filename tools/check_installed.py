import argparse
import ctypes
import hashlib
import os
import re
import subprocess
import sys
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
APP = "Pinion"


_lines: list[str] = []
_ok = True


def check(name: str, cond: bool, detail: str = "") -> bool:
    global _ok
    _lines.append(f"[{'OK' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    print(_lines[-1], flush=True)
    if not cond:
        _ok = False
    return cond


def warn(name: str, cond: bool, detail: str = "") -> None:
    _lines.append(f"[{'OK' if cond else 'WARN'}] {name}{(' — ' + detail) if detail else ''}")
    print(_lines[-1], flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def exe_file_version(path: Path):
    ver = ctypes.windll.version
    p = str(path)
    size = ver.GetFileVersionInfoSizeW(p, None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(p, 0, size, buf):
        return None
    lp = ctypes.c_void_p()
    ln = wintypes.UINT()
    if not ver.VerQueryValueW(buf, "\\", ctypes.byref(lp), ctypes.byref(ln)):
        return None
    ffi = ctypes.cast(lp, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    ms, ls = ffi.dwFileVersionMS, ffi.dwFileVersionLS
    return f"{ms >> 16 & 0xFFFF}.{ms & 0xFFFF}.{ls >> 16 & 0xFFFF}.{ls & 0xFFFF}"


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


def find_window_for_pid(pid: int, timeout: float = 30.0):
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[int] = []

    def _cb(hwnd, _lparam):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid and user32.IsWindowVisible(hwnd):
            if not user32.GetWindow(hwnd, 4):
                found.append(hwnd)
        return True

    cb = WNDENUMPROC(_cb)
    deadline = time.time() + timeout
    while time.time() < deadline:
        found.clear()
        user32.EnumWindows(cb, 0)
        if found:
            return found[0]
        time.sleep(0.5)
    return None


def window_icon_width(hwnd: int, which: int):
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.SendMessageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    WM_GETICON = 0x007F
    h = user32.SendMessageW(ctypes.c_void_p(hwnd), WM_GETICON, ctypes.c_void_p(which), ctypes.c_void_p(0))
    if not h:
        get_class = getattr(user32, "GetClassLongPtrW", None) or user32.GetClassLongW
        GCLP_HICON, GCLP_HICONSM = -14, -34
        h = get_class(ctypes.c_void_p(hwnd), GCLP_HICON if which == 1 else GCLP_HICONSM)
    if not h:
        return None
    info = ICONINFO()
    if not user32.GetIconInfo(ctypes.c_void_p(h), ctypes.byref(info)):
        return None
    bmp = BITMAP()
    try:
        if info.hbmColor and gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bmp), ctypes.byref(bmp)):
            return int(bmp.bmWidth)
        if info.hbmMask and gdi32.GetObjectW(info.hbmMask, ctypes.sizeof(bmp), ctypes.byref(bmp)):
            return int(bmp.bmWidth)
    finally:
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)
    return None


def default_release_url() -> str:
    owner, repo = "pinion-mailer", "pinion"
    try:
        url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"], cwd=REPO_ROOT
        ).decode("utf-8", "replace").strip()
        m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url)
        if m:
            owner, repo = m.group(1), m.group(2)
    except Exception:
        pass
    return f"https://github.com/{owner}/{repo}/releases/latest/download/{APP}-setup.exe"


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP}-check/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)


def main() -> int:
    global _ok
    ap = argparse.ArgumentParser(description="Проверка установленной копии")
    ap.add_argument("--source", help="локальный .exe установщика вместо скачивания по ссылке")
    ap.add_argument("--no-launch", action="store_true", help="пропустить запуск окна (шаги 5-6)")
    ap.add_argument("--keep", action="store_true", help="не удалять установку в конце")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("CHECK_INSTALLED_SKIP — только Windows", flush=True)
        return 0

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    repo_ico = REPO_ROOT / "assets" / f"{APP}.ico"
    repo_version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    check("исходная иконка репозитория на месте", repo_ico.exists(), str(repo_ico))
    check("VERSION репозитория прочитан", bool(repo_version), repo_version)

    tmp = Path(os.environ.get("TEMP", ".")) / f"{APP}-check"
    tmp.mkdir(parents=True, exist_ok=True)
    setup = Path(args.source) if args.source else tmp / f"{APP}-setup.exe"

    if args.source:
        check("источник-установщик найден (локальный)", setup.exists(), str(setup))
    else:
        url = default_release_url()
        print(f"[..] качаю {url}", flush=True)
        try:
            download(url, setup)
            mb = setup.stat().st_size / (1 << 20)
            check("установщик скачан по постоянной ссылке", setup.stat().st_size > 15 << 20,
                  f"{mb:.1f} МБ")
        except Exception as e:
            check("установщик скачан по постоянной ссылке", False, repr(e))

    if not _ok:
        return _finish()

    install_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / APP
    print(f"[..] тихая установка в {install_dir}", flush=True)
    rc = subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]).returncode
    check("установщик отработал молча (код 0)", rc == 0, f"код {rc}")
    exe = install_dir / f"{APP}.exe"
    check("установленный .exe на месте", exe.exists(), str(exe))
    if not exe.exists():
        return _finish()

    if repo_ico.exists():
        want = sha256(repo_ico)
        found_icons = list(install_dir.rglob(f"{APP}.ico"))
        match = any(sha256(p) == want for p in found_icons)
        check("иконка в установке совпадает с репо (sha256)", match,
              f"want={want[:12]}…, найдено {len(found_icons)} .ico")

    bundled = list(install_dir.rglob("VERSION"))
    bundled_ok = any(p.read_text(encoding="utf-8", errors="replace").strip() == repo_version
                     for p in bundled)
    check("вшитый файл VERSION совпадает с репо", bundled_ok,
          f"{repo_version} (файлов VERSION: {len(bundled)})")
    fv = exe_file_version(exe)
    fv_ok = bool(fv) and fv.rsplit(".", 1)[0] == repo_version or (bool(fv) and fv.startswith(repo_version))
    check("FileVersion ресурса .exe совпадает с VERSION", fv_ok, f"{fv} vs {repo_version}")

    if not args.no_launch:
        print("[..] запускаю установленную программу", flush=True)
        proc = subprocess.Popen([str(exe)], cwd=str(install_dir))
        hwnd = find_window_for_pid(proc.pid, timeout=40)
        appeared = hwnd is not None
        if not appeared:
            hwnd = _find_window_any_related(proc.pid, timeout=5)
            appeared = hwnd is not None
        check("окно программы найдено по PID", appeared, f"pid={proc.pid}")

        if appeared:
            sm = ctypes.windll.user32.GetSystemMetrics(49)
            big = ctypes.windll.user32.GetSystemMetrics(11)
            w_small = window_icon_width(hwnd, 0)
            w_big = window_icon_width(hwnd, 1)
            warn("иконка окна ICON_SMALL == SM_CXSMICON", w_small == sm, f"{w_small} vs {sm}")
            warn("иконка окна ICON_BIG == SM_CXICON", w_big == big, f"{w_big} vs {big}")

        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    if not args.keep:
        unins = install_dir / "unins000.exe"
        if unins.exists():
            print("[..] тихое удаление установки", flush=True)
            rc = subprocess.run([str(unins), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]).returncode
            time.sleep(3)
            warn("установка удалена", not exe.exists(), f"код {rc}")
        else:
            warn("деинсталлятор найден", False, str(unins))

    return _finish()


def _find_window_any_related(pid: int, timeout: float):
    try:
        import subprocess as sp
        out = sp.check_output(
            ["wmic", "process", "where", f"ParentProcessId={pid}", "get", "ProcessId"],
        ).decode("ascii", "replace")
        kids = [int(x) for x in re.findall(r"\d+", out) if int(x) != pid]
    except Exception:
        kids = []
    end = time.time() + timeout
    while time.time() < end:
        for kid in kids:
            h = find_window_for_pid(kid, timeout=0.1)
            if h:
                return h
        time.sleep(0.3)
    return None


def _finish() -> int:
    _lines.append("CHECK_INSTALLED_OK" if _ok else "CHECK_INSTALLED_FAIL")
    print(_lines[-1], flush=True)
    return 0 if _ok else 1


if __name__ == "__main__":
    sys.exit(main())
