"""
main.py - Siemens Altea DICOM Spooler & Fuji DryPix 2000 Forwarder Portativ Serveri
Yagona .exe ko'rinishida, avtomatik sozlamalar va to'liq avtonom ishlash imkoniyati bilan.
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

cur_dir = os.path.dirname(os.path.abspath(__file__))
if cur_dir not in sys.path:
    sys.path.insert(0, cur_dir)

import json
import time
import socket
import webbrowser
from storage_manager import StorageManager, get_base_path
from dicom_scu import DicomPrintSCU
from dicom_scp import DicomPrintSCP
from web_server import start_web_server
from admin_relay_worker import AdminRelayWorker

DEFAULT_CONFIG = {
    "server": {
        "listen_ip": "0.0.0.0",
        "listen_port": 1005,
        "ae_title": "DRYPIX2",
        "web_port": 3000
    },
    "security": {
        "encryption_key": "RESPUBLIKA_ONKO_MASTER_KEY_2026"
    },
    "github_relay": {
        "enabled": False,
        "repo": "",
        "token": "",
        "branch": "main",
        "queue_dir": "queue",
        "status_file": "admin_status.json",
        "github_io_url": "",
        "ttl_minutes": 60
    },
    "printer": {
        "ip": "10.34.14.12",
        "port": 104,
        "called_ae": "DRYPIX2",
        "calling_ae": "MRT1",
        "timeout_sec": 15
    },
    "storage": {
        "archive_dir": "storage/archive",
        "db_path": "storage/data/print_spooler.db"
    },
    "options": {
        "auto_forward_to_printer": False,
        "save_raw_dicom": True,
        "save_preview_images": True,
        "hospital_name": "RESPUBLIKA ONKOLOGIYA VA RADIOLOGIYA MARKAZI",
        "modality_name": "SIEMENS MAGNETOM ALTEA (1.5T)"
    }
}

def load_config():
    base = get_base_path()
    cfg_path = os.path.join(base, 'config.json')
    if not os.path.exists(cfg_path):
        alt = os.path.join(base, 'dicom_server', 'config.json')
        if os.path.exists(alt):
            cfg_path = alt
            
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[XATO] config.json ni o'qishda xatolik: {e}")

    # Agar config.json mavjud bo'lmasa, dastur yonida yangi yaratamiz
    target_cfg = os.path.join(base, 'config.json')
    try:
        with open(target_cfg, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        print(f"[*] Yangi sozlama fayli yaratildi: {target_cfg}")
    except Exception as e:
        print(f"[Ogohlantirish] config.json faylini yozib bo'lmadi: {e}")
        
    return DEFAULT_CONFIG

def get_local_ip():
    for target in [("10.34.14.12", 104), ("192.168.150.111", 2025), ("8.8.8.8", 80)]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(target)
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith('127.'):
                return ip
        except Exception:
            pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "10.34.14.33"

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def main():
    base = get_base_path()
    config = load_config()
    local_ip = get_local_ip()

    dicom_port = config.get('server', {}).get('listen_port', 1005)
    web_port = config.get('server', {}).get('web_port', 3000)

    print("=" * 70)
    print("   RESPUBLIKA ONKOLOGIYA VA RADIOLOGIYA MARKAZI")
    print("   SIEMENS MAGNETOM ALTEA - DICOM PRINT SPOOLER (PORTABLE)")
    print("=" * 70)
    print(f"[*] Dastur papkasi    : {base}")
    print(f"[*] Server IP manzili : {local_ip}")
    print(f"[*] DICOM Port        : {dicom_port} (AE Title: {config['server']['ae_title']})")
    print(f"[*] Web boshqaruv     : http://{local_ip}:{web_port} (yoki http://localhost:{web_port})")
    print(f"[*] Fuji DryPix 2000  : {config['printer']['ip']}:{config['printer']['port']}")
    print(f"[*] Avto-chop etish   : {'YOQILGAN' if config.get('options', {}).get('auto_forward_to_printer') else 'OCHIRILGAN (Keshga xavfsiz saqlash)'}")
    print("=" * 70)

    if is_port_in_use(dicom_port):
        print(f"\n[OGOHLANTIRISH] {dicom_port}-port allaqachon band! Dasturning boshqa nusxasi ishlayotgan bo'lishi mumkin.")
    if is_port_in_use(web_port):
        print(f"[OGOHLANTIRISH] {web_port}-port allaqachon band!\n")

    # 1. Saqlash boshqaruvchisi
    storage = StorageManager(config)

    # 2. Fuji DryPix 2000 SCU klienti
    scu = DicomPrintSCU(config)
    p_status = scu.check_printer()
    if p_status.get('online'):
        print(f"[OK] FUJI DRYPIX PRINTER ALOQASI FAOL: {p_status.get('status')} ({p_status.get('model')})")
    else:
        print(f"[!] Fuji DryPix printer hozircha javob bermadi ({p_status.get('error')}). Keshga saqlash davom etadi.")

    # 3. DICOM Print SCP serverni ishga tushirish (Port 1005)
    scp = DicomPrintSCP(config, storage, scu)
    scp.start()

    # 4. Veb serverni ishga tushirish (Port 3000)
    start_web_server(storage, scu, scp, config, local_ip=local_ip)

    # 5. Brauzerda avtomatik ochish
    web_url = f"http://localhost:{web_port}"
    print(f"\n[*] Veb boshqaruv paneli brauzerda ochilmoqda: {web_url}")
    try:
        webbrowser.open(web_url)
    except Exception:
        pass

    # 6. Masofaviy Agentlar va GitHub Relay xizmati
    relay_worker = AdminRelayWorker(config, storage, scu)
    relay_worker.start()

    print("\n[Server Faol] Siemens va boshqa apparatlardan so'rovlar qabul qilinmoqda...")
    print("Dasturni to'xtatish uchun klaviaturada Ctrl+C bosing.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nServer to'xtatilmoqda...")
        scp.stop()
        print("Tizim muvaffaqiyatli to'xtatildi.")

if __name__ == '__main__':
    main()
