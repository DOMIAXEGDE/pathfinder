# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\execute\\omicron\\pathfinder.py'],
    pathex=[],
    binaries=[('D:\\execute\\omicron\\basis_tensor.exe', '.')],
    datas=[('D:\\execute\\omicron\\25.py', '.'), ('D:\\execute\\omicron\\pathfinder.md', '.'), ('D:\\execute\\omicron\\pathfinder_instruction_template.py', '.'), ('D:\\execute\\omicron\\17.txt', '.')],
    hiddenimports=['PIL.Image', 'PIL.ImageTk', 'tkinter', 'tkinter.filedialog', 'tkinter.messagebox'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pygame'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Pathfinder',
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
    name='Pathfinder',
)
