# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = [('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/.build-venv/Lib/site-packages/PySide6/VCRUNTIME140.dll', '.'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/.build-venv/Lib/site-packages/PySide6/VCRUNTIME140_1.dll', '.'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/.build-venv/Lib/site-packages/PySide6/msvcp140.dll', '.'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/.build-venv/Lib/site-packages/PySide6/concrt140.dll', '.')]
binaries += collect_dynamic_libs('PySide6')
binaries += collect_dynamic_libs('shiboken6')


a = Analysis(
    ['C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/CAD-MAP-main/编排器/app.py'],
    pathex=[],
    binaries=binaries,
    datas=[('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/CAD-MAP-main/编排器/app_icon.png', '.'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/CAD-MAP-main/编排器/logo_blue.png', '.'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/CAD-MAP-main/编排器/PdfLayout_auto.lsp', '.'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/CAD-MAP-main/编排器/PdfLayout_ai.lsp', '.'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/CAD-MAP-main/PdfLayout插件包/PdfLayout.lsp', '.'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/.build-venv/Lib/site-packages/PySide6/plugins/platforms', 'PySide6/plugins/platforms'), ('C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/.build-venv/Lib/site-packages/PySide6/plugins/styles', 'PySide6/plugins/styles')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Voltage-CAD MAP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/ZhaokeShi/Downloads/CAD-MAP-main/CAD-MAP-main/编排器/app.ico'],
)
