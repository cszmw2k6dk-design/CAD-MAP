# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = [('C:/pybuild/python/VCRUNTIME140.dll', '.'), ('C:/pybuild/python/VCRUNTIME140_1.dll', '.'), ('C:/pybuild/python/msvcp140.dll', '.'), ('C:/pybuild/python/concrt140.dll', '.')]
binaries += collect_dynamic_libs('PySide6')
binaries += collect_dynamic_libs('shiboken6')


a = Analysis(
    ['_qttest.py'],
    pathex=[],
    binaries=binaries,
    datas=[('C:/pybuild/python/Lib/site-packages/PySide6/plugins/platforms', 'PySide6/plugins/platforms')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='qttest',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='qttest',
)
