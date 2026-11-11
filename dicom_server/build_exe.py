"""
build_exe.py - Siemens_Fuji_DICOM_Print_Server.exe faylini yig'ish (PyInstaller Standalone OneFile)
"""
import os
import sys
import shutil
import subprocess

cur_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(cur_dir, '..'))

main_py = os.path.join(cur_dir, 'main.py')
build_dir = os.path.join(root_dir, 'build_temp')

# Qo'shiladigan ma'lumot fayllari
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
    "--console", # Server loglarini ko'rish uchun konsol oynasi bilan
    "--name", "Siemens_Fuji_DICOM_Print_Server",
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
    "--hidden-import=pydicom.encoders.native",
    "--hidden-import=PIL",
    "--hidden-import=PIL.Image",
    "--hidden-import=PIL.ImageDraw",
    "--hidden-import=PIL.ImageFont",
    "--hidden-import=numpy",
    "--hidden-import=sqlite3",
    "--hidden-import=urllib.request",
    "--hidden-import=urllib.parse",
    "--hidden-import=http.cookiejar",
    main_py
]

print("=" * 60)
print("PORTATIV YAGONA .EXE YIG'ISH JARAYONI BOSHLANDI...")
print("=" * 60)

res = subprocess.run(cmd)

if res.returncode == 0:
    exe_path = os.path.join(root_dir, "Siemens_Fuji_DICOM_Print_Server.exe")
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print("\n" + "=" * 60)
    print("MUVAFFAQIYATLI YIG'ILDI!")
    print(f"Chiqish fayli (.exe): {exe_path}")
    print(f"Hajmi               : {size_mb:.2f} MB")
    print("=" * 60)
    
    # build_temp tozalash
    try:
        shutil.rmtree(build_dir, ignore_errors=True)
    except Exception:
        pass
else:
    print(f"Kompilyatsiyada xatolik yuz berdi: {res.returncode}")
    sys.exit(res.returncode)
