"""
agent_main.py - Siemens, GE, Philips va boshqa tomograflar uchun DICOM Spooler Agent
Turli klinika va filiallarga o'rnatiladi.
O'z apparatidan DICOM Print so'rovlarini qabul qilib, shifrlangan holda Asosiy Admin kompyuteriga yuboradi.
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
import uuid
import base64
import socket
import threading
import urllib.request
import urllib.parse
from datetime import datetime

from pynetdicom import AE, evt
from pynetdicom.sop_class import (
    BasicGrayscalePrintManagementMeta,
    BasicFilmSession,
    BasicFilmBox,
    BasicGrayscaleImageBox,
    Printer,
    Verification
)

from crypto_manager import E2EESecurity
from github_relay import GitHubRelayClient

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

DEFAULT_AGENT_CONFIG = {
    "agent": {
        "clinic_name": "FILIAL / KLINIKA 1",
        "modality_name": "SIEMENS MAGNETOM ALTEA (MRT 2)",
        "listen_ip": "0.0.0.0",
        "listen_port": 1005,
        "ae_title": "DRYPIX2"
    },
    "security": {
        "encryption_key": "RESPUBLIKA_ONKO_MASTER_KEY_2026"
    },
    "admin_connection": {
        "direct_url": "http://10.34.14.33:3000/api/relay/push",
        "prefer_direct": True
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
    "storage": {
        "outbox_dir": "agent_storage/outbox",
        "sent_dir": "agent_storage/sent"
    }
}

class DicomAgentService:
    def __init__(self, config: dict, base_dir: str):
        self.config = config
        self.base_dir = base_dir
        
        raw_outbox = config.get('storage', {}).get('outbox_dir', 'agent_storage/outbox')
        raw_sent = config.get('storage', {}).get('sent_dir', 'agent_storage/sent')
        
        self.outbox_dir = os.path.normpath(os.path.join(base_dir, raw_outbox))
        self.sent_dir = os.path.normpath(os.path.join(base_dir, raw_sent))
        os.makedirs(self.outbox_dir, exist_ok=True)
        os.makedirs(self.sent_dir, exist_ok=True)

        # Xavfsizlik va Shifrlash (E2EE AES-256-GCM)
        enc_key = config.get('security', {}).get('encryption_key', '')
        self.security = E2EESecurity(enc_key)

        # GitHub Relay
        self.github = GitHubRelayClient(config)

        # Sessiyalar xotirasi
        self.film_sessions = {}
        self.film_boxes = {}
        self.image_boxes = {}

        self.running = True

    # =========================================================================
    # DICOM PRINT SCP HANDLERS
    # =========================================================================
    def start_dicom_scp(self):
        ag_cfg = self.config.get('agent', {})
        port = int(ag_cfg.get('listen_port', 1005))
        listen_ip = ag_cfg.get('listen_ip', '0.0.0.0')
        ae_title = ag_cfg.get('ae_title', 'DRYPIX2').encode('ascii')

        ae = AE(ae_title=ae_title)
        for sc in [BasicGrayscalePrintManagementMeta, BasicFilmSession, BasicFilmBox, BasicGrayscaleImageBox, Printer, Verification]:
            ae.add_supported_context(sc)

        handlers = [
            (evt.EVT_CONN_OPEN, self._on_conn_open),
            (evt.EVT_N_CREATE, self._on_n_create),
            (evt.EVT_N_SET, self._on_n_set),
            (evt.EVT_N_ACTION, self._on_n_action),
            (evt.EVT_N_DELETE, self._on_n_delete),
            (evt.EVT_N_GET, self._on_n_get),
            (evt.EVT_C_ECHO, self._on_c_echo)
        ]

        server = ae.start_server((listen_ip, port), block=False, evt_handlers=handlers)
        print(f"[*] Agent DICOM SCP ishga tushdi: {listen_ip}:{port} (AE: {ae_title.decode()})")
        return server

    def _on_conn_open(self, event):
        assoc = event.assoc
        calling = assoc.requestor.ae_title.strip() if hasattr(assoc, 'requestor') else 'UNKNOWN'
        # print(f"[Agent] Aloqa ochildi: {calling}")

    def _on_c_echo(self, event):
        return 0x0000

    def _on_n_get(self, event):
        ds = event.dataset
        return 0x0000, ds

    def _on_n_create(self, event):
        req = event.request
        sop_class = str(req.AffectedSOPClassUID)
        ds = event.dataset

        if '1.2.840.10008.5.1.1.1' in sop_class: # Film Session
            sess_uid = f"SESS_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            self.film_sessions[sess_uid] = ds
            rsp_ds = ds
            rsp_ds.SOPInstanceUID = sess_uid
            rsp_ds.SOPClassUID = req.AffectedSOPClassUID
            return 0x0000, rsp_ds

        elif '1.2.840.10008.5.1.1.2' in sop_class: # Film Box
            fb_uid = f"FB_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            self.film_boxes[fb_uid] = ds
            rsp_ds = ds
            rsp_ds.SOPInstanceUID = fb_uid
            rsp_ds.SOPClassUID = req.AffectedSOPClassUID
            return 0x0000, rsp_ds

        return 0x0000, ds

    def _on_n_set(self, event):
        req = event.request
        sop_instance = str(req.RequestedSOPInstanceUID)
        ds = event.dataset
        pos = getattr(ds, 'ImageBoxPosition', len(self.image_boxes) + 1)
        self.image_boxes[sop_instance] = {
            'position': pos,
            'dataset': ds
        }
        return 0x0000, ds

    def _on_n_delete(self, event):
        return 0x0000

    def _on_n_action(self, event):
        """Siemensdan PRINT komandasi keldi -> Plonkani mahalliy outboxga joylash"""
        assoc = event.assoc
        calling_aet = assoc.requestor.ae_title.decode('latin1', errors='replace').strip() if hasattr(assoc, 'requestor') else "SIEMENS"
        now = datetime.now()
        timestamp_epoch = int(now.timestamp())
        job_uid = f"JOB_{timestamp_epoch}_{uuid.uuid4().hex[:8]}"

        print(f"\n[Agent] Yangi chop etish so'rovi qabul qilindi! UID: {job_uid}")
        
        # 1. Kadrlar piksellarini yig'ish
        frames_payload = []
        sorted_boxes = sorted(self.image_boxes.values(), key=lambda b: b.get('position', 1))
        
        fb_ds = list(self.film_boxes.values())[-1] if self.film_boxes else None
        film_format = getattr(fb_ds, 'ImageDisplayFormat', 'STANDARD\\1,1') if fb_ds else 'STANDARD\\1,1'
        film_size = getattr(fb_ds, 'FilmSizeID', '14INX17IN') if fb_ds else '14INX17IN'
        orientation = getattr(fb_ds, 'FilmOrientation', 'PORTRAIT') if fb_ds else 'PORTRAIT'

        for item in sorted_boxes:
            pos = item.get('position', 1)
            ds = item.get('dataset')
            if not ds:
                continue
            seq = getattr(ds, 'BasicGrayscaleImageSequence', None)
            if not seq or len(seq) == 0:
                continue
            raw_ds = seq[0]
            pixel_bytes = getattr(raw_ds, 'PixelData', None)
            if not pixel_bytes:
                continue

            frames_payload.append({
                'position': pos,
                'rows': getattr(raw_ds, 'Rows', 0),
                'columns': getattr(raw_ds, 'Columns', 0),
                'bits_stored': getattr(raw_ds, 'BitsStored', 12),
                'bits_allocated': getattr(raw_ds, 'BitsAllocated', 16),
                'high_bit': getattr(raw_ds, 'HighBit', 11),
                'pixel_representation': getattr(raw_ds, 'PixelRepresentation', 0),
                'photometric': getattr(raw_ds, 'PhotometricInterpretation', 'MONOCHROME2'),
                'pixel_data_b64': base64.b64encode(pixel_bytes).decode('ascii')
            })

        # 2. Xavfsiz paket shakllantirish
        ag_cfg = self.config.get('agent', {})
        payload = {
            'job_uid': job_uid,
            'source_clinic': ag_cfg.get('clinic_name', 'Filial'),
            'source_modality': ag_cfg.get('modality_name', 'MRT'),
            'calling_aet': calling_aet,
            'created_at': now.isoformat(),
            'timestamp_epoch': timestamp_epoch,
            'film_format': film_format,
            'film_size': film_size,
            'orientation': orientation,
            'total_frames': len(frames_payload),
            'frames': frames_payload
        }

        # 3. Mahalliy Outbox ga saqlash (.json fayl)
        outbox_file = os.path.join(self.outbox_dir, f"{job_uid}.json")
        try:
            with open(outbox_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
            print(f"[Agent] Plonka mahalliy navbatga saqlandi: {outbox_file}")
        except Exception as e:
            print(f"[Agent] XATO: Outboxga saqlab bo'lmadi: {e}")

        # Xotirani tozalash
        self.image_boxes.clear()
        return 0x0000

    # =========================================================================
    # YUBORISH VA SINXRONIZATSIYA (BACKGROUND SYNC WORKER)
    # =========================================================================
    def run_sync_worker(self):
        """
        Orqa fonda navbatdagi fayllarni tekshiradi va Admin onlayn bo'lsa,
        shifrlab (AES-256-GCM) uzatadi.
        """
        print("[*] Agent jo'natish xizmati faollashdi (Har 5 soniyada tekshiriladi)")
        while self.running:
            try:
                self._process_outbox()
            except Exception as e:
                pass
            time.sleep(5)

    def _process_outbox(self):
        files = [f for f in os.listdir(self.outbox_dir) if f.endswith('.json')]
        if not files:
            return

        for fname in sorted(files):
            fpath = os.path.join(self.outbox_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    payload = json.load(f)
            except Exception:
                continue

            job_uid = payload.get('job_uid', fname.replace('.json', ''))
            
            # 1. To'liq shifrlash (AES-256-GCM)
            encrypted_b64 = self.security.encrypt_payload(payload)

            # 2. To'g'ridan-to'g'ri Admin manziliga yuborib ko'rish (Direct IP)
            direct_cfg = self.config.get('admin_connection', {})
            direct_url = direct_cfg.get('direct_url', '').strip()
            prefer_direct = direct_cfg.get('prefer_direct', True)
            
            success = False
            if prefer_direct and direct_url:
                success = self._push_direct(direct_url, job_uid, encrypted_b64)
                if success:
                    print(f"[Agent] Plonka to'g'ridan-to'g'ri Adminga yetkazildi: {job_uid}")

            # 3. Agar to'g'ridan-to'g'ri ulanish bo'lmasa, GitHub Relay orqali tekshirish
            if not success and self.github.enabled:
                admin_st = self.github.get_admin_status()
                if admin_st.get('online'):
                    print(f"[Agent] Admin GitHub orqali onlayn deb topildi. Shifrlangan paket uzatilmoqda...")
                    success = self.github.push_encrypted_job(job_uid, encrypted_b64)
                    if success:
                        print(f"[Agent] Plonka GitHub navbatiga muvaffaqiyatli yuklandi: {job_uid}")
                else:
                    # Admin oflayn! Hech qayerga yuklamaymiz, navbatda kutamiz!
                    # print(f"[Agent] Admin oflayn. Plonka mahalliy navbatda kutmoqda.")
                    pass

            # 4. Agar yetkazilgan bo'lsa, Outbox dan Sent papkasiga ko'chirish
            if success:
                try:
                    sent_file = os.path.join(self.sent_dir, fname)
                    os.replace(fpath, sent_file)
                except Exception:
                    pass

    def _push_direct(self, url: str, job_uid: str, encrypted_b64: str) -> bool:
        """To'g'ridan-to'g'ri Admin veb-serveriga (Port 3000) shifrlangan paketni yuborish"""
        req_data = json.dumps({
            'job_uid': job_uid,
            'payload': encrypted_b64
        }).encode('utf-8')
        
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'DICOM-Agent/2.5'}
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as res:
                if res.status in (200, 201):
                    rsp = json.loads(res.read().decode())
                    return rsp.get('success', False)
        except Exception:
            return False
        return False

def load_agent_config():
    base = get_base_path()
    cfg_path = os.path.join(base, 'agent_config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
            
    # Standart agent sozlamasini yaratish
    try:
        with open(cfg_path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_AGENT_CONFIG, f, indent=2, ensure_ascii=False)
        print(f"[*] Yangi agent sozlama fayli yaratildi: {cfg_path}")
    except Exception:
        pass
    return DEFAULT_AGENT_CONFIG

def main():
    base = get_base_path()
    config = load_agent_config()
    ag_cfg = config.get('agent', {})

    print("=" * 70)
    print("   RESPUBLIKA ONKOLOGIYA VA RADIOLOGIYA MARKAZI")
    print("   DICOM PRINT SPOOLER - MASOFAVIY AGENT (STANDALONE CLIENT)")
    print("=" * 70)
    print(f"[*] Klinika / Filial : {ag_cfg.get('clinic_name')}")
    print(f"[*] Qurilma / Tomograf: {ag_cfg.get('modality_name')}")
    print(f"[*] DICOM Port       : {ag_cfg.get('listen_port')} (AE: {ag_cfg.get('ae_title')})")
    print(f"[*] Shifrlash        : AES-256-GCM (Uchdan-uchga xavfsiz)")
    print(f"[*] Admin aloqasi    : {config.get('admin_connection', {}).get('direct_url')}")
    if config.get('github_relay', {}).get('enabled'):
        print(f"[*] GitHub Relay     : Faol ({config.get('github_relay', {}).get('repo')})")
    else:
        print(f"[*] GitHub Relay     : O'chirilgan (Faqat to'g'ridan-to'g'ri tarmoq orqali)")
    print("=" * 70 + "\n")

    agent = DicomAgentService(config, base)
    agent.start_dicom_scp()

    # Jo'natuvchi fonda ishlashi
    sync_thread = threading.Thread(target=agent.run_sync_worker, daemon=True)
    sync_thread.start()

    print("[Agent Faol] Mahalliy tomografdan so'rovlar qabul qilinmoqda...")
    print("Dasturni to'xtatish uchun Ctrl+C bosing.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nAgent to'xtatildi.")

if __name__ == '__main__':
    main()
