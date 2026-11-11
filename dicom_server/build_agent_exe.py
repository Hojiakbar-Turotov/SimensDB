"""
build_agent_exe.py - DICOM_Spooler_Agent.exe faylini yig'ish (Masofaviy Filial Client)
"""
import os
import sys
import shutil
import subprocess

cur_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(cur_dir, '..'))

agent_main_py = os.path.join(cur_dir, 'agent_main.py')
build_dir = os.path.join(root_dir, 'build_agent_temp')

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--console",
    "--name", "DICOM_Spooler_Agent",
    f"--distpath={root_dir}",
    f"--workpath={build_dir}",
    f"--specpath={cur_dir}",
    "--hidden-import=pynetdicom",
    "--hidden-import=pynetdicom.sop_class",
    "--hidden-import=pynetdicom.service_class",
    "--hidden-import=pynetdicom.service_class_n",
    "--hidden-import=pynetdicom.events",
    "--hidden-import=pynetdicom.transport",
    "--hidden-import=pydicom",
    "--hidden-import=cryptography",
    "--hidden-import=cryptography.hazmat.primitives.ciphers.aead",
    "--hidden-import=urllib.request",
    "--hidden-import=urllib.parse",
    agent_main_py
]

print("=" * 60)
print("AGENT .EXE (MASOFAVIY CLIENT) YIG'ILMOQDA...")
print("=" * 60)

res = subprocess.run(cmd)

if res.returncode == 0:
    exe_path = os.path.join(root_dir, "DICOM_Spooler_Agent.exe")
    size_mb = os.path.getsize(exe_path) / (1024 * 1024)
    print("\n" + "=" * 60)
    print("AGENT .EXE MUVAFFAQIYATLI YIG'ILDI!")
    print(f"Chiqish fayli (.exe): {exe_path}")
    print(f"Hajmi               : {size_mb:.2f} MB")
    print("=" * 60)
    try:
        shutil.rmtree(build_dir, ignore_errors=True)
    except Exception:
        pass
else:
    print(f"Agent yig'ishda xatolik: {res.returncode}")
    sys.exit(res.returncode)
