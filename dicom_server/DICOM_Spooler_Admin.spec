# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['d:/SimensDB/dicom_server/main.py'],
    pathex=[],
    binaries=[],
    datas=[('d:/SimensDB/siemens_digit_templates.json', '.'), ('d:/SimensDB/dicom_server/siemens_digit_templates.json', 'dicom_server'), ('d:/SimensDB/config.json', '.'), ('d:/SimensDB/config/karmed_profiles.json', '.'), ('d:/SimensDB/config/karmed_profiles.json', 'data'), ('d:/SimensDB/config/karmed_profiles.json', 'config')],
    hiddenimports=['pynetdicom', 'pynetdicom.sop_class', 'pynetdicom.service_class', 'pynetdicom.service_class_n', 'pynetdicom.events', 'pynetdicom.transport', 'pydicom', 'pydicom.encoders', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont', 'numpy', 'sqlite3', 'cryptography', 'cryptography.hazmat.primitives.ciphers.aead', 'urllib.request', 'urllib.parse', 'http.cookiejar'],
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
    a.binaries,
    a.datas,
    [],
    name='DICOM_Spooler_Admin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
