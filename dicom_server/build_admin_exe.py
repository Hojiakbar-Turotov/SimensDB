"""
build_admin_exe.py - DICOM_Spooler_Admin.exe faylini yig'ish (Markaziy Server)
"""
import os
import sys
import shutil
import subprocess

cur_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(cur_dir, '..'))

main_py = os.path.join(cur_dir, 'main.py')
build_dir = os.path.join(root_dir, 'build_admin_temp')

data_files = [
    (os.path.join(root_dir, 'siemens_digit_templates.json'), '.'),
    (os.path.join(cur_dir, 'siemens_digit_templates.json'), 'dicom_server'),
    (os.path.join(root_dir, 'config.json'), '.'),
    (os.path.join(root_dir, 'config', 'karmed_profiles.json'), '.'),
    (os.path.join(root_dir, 'config', 'karmed_profiles.json'), 'data'),
    (os.path.join(root_dir, 'config', 'karmed_profiles.json'), 'config'),
]

add_data_args = []
for src, dst in data_files:
    if os.path.exists(src):
        add_data_args.extend(["--add-data", f"{src};{dst}"])

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--console",
    "--name", "DICOM_Spooler_Admin",
    f"--distpath={root_dir}",
    f"--workpath={build_dir}",
    f"--specpath={cur_dir}",
    *add_data_args,
    "--hidden-import=pynetdicom",
    "--hidden-import=pynetdicom.sop_class",
    "--hidden-import=pynetdicom.service_class",
    "--hidden-import=pynetdicom.service_class_n",
    "--hidden-import=pynetdicom.events",
    "--hidden-import=pynetdicom.transport",
    "--hidden-import=pydicom",
    "--hidden-import=pydicom.encoders",
    "--hidden-import=PIL",
    "--hidden-import=PIL.Image",
    "--hidden-import=PIL.ImageDraw",
    "--hidden-import=PIL.ImageFont",
    "--hidden-import=numpy",
    "--hidden-import=sqlite3",
    "--hidden-import=cryptography",
    "--hidden-import=cryptography.hazmat.primitives.ciphers.aead",
    "--hidden-import=urllib.request",
    "--hidden-import=urllib.parse",
    "--hidden-import=http.cookiejar",
    main_py
]

print("=" * 60)
print("ADMIN .EXE (MARKAZIY SERVER) YIG'ILMOQDA...")
print("=" * 60)

res = subprocess.run(cmd)

if res.returncode == 0:
    exe_path = os.path.join(root_dir, "DICOM_Spooler_Admin.exe")
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print("\n" + "=" * 60)
    print("ADMIN .EXE MUVAFFAQIYATLI YIG'ILDI!")
    print(f"Chiqish fayli (.exe): {exe_path}")
    print(f"Hajmi               : {size_mb:.2f} MB")
    print("=" * 60)
    try:
        shutil.rmtree(build_dir, ignore_errors=True)
    except Exception:
        pass
else:
    print(f"Admin yig'ishda xatolik: {res.returncode}")
    sys.exit(res.returncode)
