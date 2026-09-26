# -*- mode: python ; coding: utf-8 -*-
# Сборка Pinion. Каждая строка обоснована паспортом проекта (шаг 0), а не скопирована:
#  - вход main.py: по умолчанию поднимает веб (pywebview), `ctk` — старый CustomTkinter;
#  - datas: webui/web (HTML/JS/CSS интерфейса; host.py читает их через resource_path из
#    _MEIPASS) и VERSION (единый источник версии, читается core/appenv.app_version);
#  - collect_all('webview'): pywebview возит с собой loader WebView2 и JS-мост — без сбора
#    приложение стартует с пустым окном/падает; collect_all('customtkinter'): темы *.json;
#  - pythonnet/clr (Windows-бэкенд pywebview) собирают штатные хуки hook-clr/hook-webview
#    из pyinstaller-hooks-contrib — дублировать не нужно;
#  - hiddenimports: fallback `from letter_score import ...` в host.py (bare-имя) на всякий.
from PyInstaller.utils.hooks import collect_all

datas = [('webui/web', 'webui/web'), ('VERSION', '.')]
binaries = []
hiddenimports = ['webui.letter_score', 'clr']

for pkg in ('webview', 'customtkinter'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Тяжёлое и ненужное, что может притянуться транзитивно. numpy/PIL НЕ исключаем:
    # приложение их не импортирует (значит и не попадут), а хуки могли бы на них
    # опираться — перестраховка от случайной поломки сборки.
    excludes=['matplotlib', 'scipy', 'pandas', 'pytest', 'IPython', 'jedi', 'zmq', 'tornado'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Pinion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # GUI: без чёрного окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/Pinion.ico',
    version='version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Pinion',
)
