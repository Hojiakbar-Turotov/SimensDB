"""
storage_manager.py - Arxivlash, SQLite bazasi, KarMed integratsiyasi va tibbiy plonkalarni boshqarish moduli
1000+ bemorlar uchun yuqori unumdorlik va uzoq muddatli barqarorlik (WAL rejimi, indekslar, audit jurnali)
"""
import os
import sys
import re
import json
import sqlite3
import datetime
import secrets
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from karmed_client import KarMedClient, format_uzbek_phone

def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Standalone portativ variant uchun Siemens Altea shrifti (0-9) shablonlari
BUILTIN_SIEMENS_DIGITS = {
    "0": [[0, 0, 1, 1, 1, 0, 0], [0, 1, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [0, 1, 0, 0, 0, 1, 0], [0, 0, 1, 1, 1, 0, 0]],
    "1": [[0, 0, 0, 1], [0, 0, 1, 1], [0, 1, 0, 1], [1, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1]],
    "2": [[0, 0, 1, 1, 1, 1, 0], [0, 1, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 1, 0, 0], [0, 0, 0, 1, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1, 1]],
    "3": [[0, 0, 1, 1, 1, 0, 0], [0, 1, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 1, 1, 0], [0, 0, 1, 1, 1, 0, 0], [0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 1, 0, 0, 0, 1, 0], [0, 0, 1, 1, 1, 0, 0]],
    "4": [[0, 0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 1, 1, 0], [0, 0, 0, 0, 1, 0, 1, 0], [0, 0, 0, 1, 0, 0, 1, 0], [0, 0, 0, 1, 0, 0, 1, 0], [0, 0, 1, 0, 0, 0, 1, 0], [0, 1, 0, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 0, 1, 0], [1, 1, 1, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 0, 1, 0]],
    "5": [[0, 1, 1, 1, 1, 1, 1], [0, 1, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 0, 0], [1, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [0, 1, 0, 0, 0, 1, 0], [0, 0, 1, 1, 1, 0, 0]],
    "6": [[0, 0, 1, 1, 1, 0, 0], [0, 1, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 0], [1, 0, 1, 1, 1, 0, 0], [1, 1, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [0, 1, 0, 0, 0, 1, 0], [0, 0, 1, 1, 1, 0, 0]],
    "7": [[1, 1, 1, 1, 1, 1, 1], [0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 0, 1, 0], [0, 0, 0, 0, 1, 0, 0], [0, 0, 0, 0, 1, 0, 0], [0, 0, 0, 1, 0, 0, 0], [0, 0, 0, 1, 0, 0, 0], [0, 0, 0, 1, 0, 0, 0], [0, 0, 0, 1, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0, 0]],
    "8": [[0, 0, 1, 1, 1, 0, 0], [0, 1, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [0, 1, 0, 0, 0, 1, 0], [0, 0, 1, 1, 1, 0, 0], [0, 1, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [0, 1, 0, 0, 0, 1, 0], [0, 0, 1, 1, 1, 0, 0]],
    "9": [[0, 0, 1, 1, 1, 0, 0], [0, 1, 0, 0, 0, 1, 0], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [0, 1, 0, 0, 0, 1, 1], [0, 0, 1, 1, 1, 0, 1], [0, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 1], [0, 1, 0, 0, 0, 1, 0], [0, 0, 1, 1, 1, 0, 0]]
}

class StorageManager:
    def __init__(self, config):
        self.config = config
        self.base_dir = get_base_path()
        
        # Absolute storage paths
        raw_archive = config.get('storage', {}).get('archive_dir', 'storage/archive')
        raw_db = config.get('storage', {}).get('db_path', 'storage/data/print_spooler.db')
        
        self.archive_dir = os.path.normpath(os.path.join(self.base_dir, raw_archive))
        self.db_path = os.path.normpath(os.path.join(self.base_dir, raw_db))
        
        os.makedirs(self.archive_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self.hospital_name = config.get('options', {}).get('hospital_name', 'RESPUBLIKA ONKOLOGIYA VA RADIOLOGIYA MARKAZI')
        self.modality_name = config.get('options', {}).get('modality_name', 'SIEMENS MAGNETOM ALTEA (1.5T)')
        
        # KarMed mijozi
        self.karmed = KarMedClient()
        self._digit_templates = {}
        self._load_digit_templates()
        
        self._init_db()

    def _load_digit_templates(self):
        """Siemens Altea shrifti shablonlarini yuklash (Standalone & External)"""
        # Standart o'rnatilgan shablonlarni yuklash (100% mustaqil ishlash uchun)
        self._digit_templates = {k: np.array(v, dtype=np.uint8) for k, v in BUILTIN_SIEMENS_DIGITS.items()}
        
        # Tashqi fayllar bo'lsa yangilab olamiz
        meipass = getattr(sys, '_MEIPASS', '')
        candidates = [
            os.path.join(meipass, 'siemens_digit_templates.json') if meipass else None,
            os.path.join(meipass, 'dicom_server', 'siemens_digit_templates.json') if meipass else None,
            os.path.join(self.base_dir, 'dicom_server', 'siemens_digit_templates.json'),
            os.path.join(self.base_dir, 'siemens_digit_templates.json'),
            os.path.join(os.path.dirname(__file__), 'siemens_digit_templates.json')
        ]
        for p in candidates:
            if p and os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self._digit_templates = {k: np.array(v, dtype=np.uint8) for k, v in data.items()}
                    return
                except Exception as e:
                    print(f"[Storage] Raqamlar shablonini o'qishda xato: {e}")

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS print_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_uid TEXT UNIQUE NOT NULL,
                patient_id TEXT,
                sample_no TEXT,
                patient_name TEXT,
                phone_number TEXT,
                patient_dob TEXT,
                patient_gender TEXT,
                study_date TEXT,
                study_time TEXT,
                protocol_no TEXT,
                modality TEXT DEFAULT 'MR',
                film_format TEXT DEFAULT 'STANDARD\\2,3',
                film_size TEXT DEFAULT '14INX17IN',
                orientation TEXT DEFAULT 'PORTRAIT',
                copies INTEGER DEFAULT 1,
                total_frames INTEGER DEFAULT 0,
                archive_dir TEXT,
                preview_image TEXT,
                status TEXT DEFAULT 'SAVED',
                fuji_status TEXT DEFAULT 'PENDING',
                delivery_status TEXT DEFAULT 'PENDING_PICKUP',
                delivered_at TEXT,
                delivered_by TEXT,
                print_count INTEGER DEFAULT 0,
                print_success_count INTEGER DEFAULT 0,
                print_fail_count INTEGER DEFAULT 0,
                last_print_attempt TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                printed_at TEXT
            )
            """)
            
            # Mavjud bazani yangi ustunlar bilan to'ldirish (Auto-migration)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(print_jobs)")
            cols = {row[1] for row in cur.fetchall()}
            new_cols = [
                ("sample_no", "TEXT"),
                ("phone_number", "TEXT"),
                ("delivery_status", "TEXT DEFAULT 'PENDING_PICKUP'"),
                ("delivered_at", "TEXT"),
                ("delivered_by", "TEXT"),
                ("print_count", "INTEGER DEFAULT 0"),
                ("print_success_count", "INTEGER DEFAULT 0"),
                ("print_fail_count", "INTEGER DEFAULT 0"),
                ("last_print_attempt", "TEXT")
            ]
            for c_name, c_type in new_cols:
                if c_name not in cols:
                    conn.execute(f"ALTER TABLE print_jobs ADD COLUMN {c_name} {c_type}")

            conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_received INTEGER DEFAULT 0,
                total_printed INTEGER DEFAULT 0,
                total_saved INTEGER DEFAULT 0,
                total_failed INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """)
            
            # Harakatlar jurnali (Audit Logging)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                user_login TEXT,
                user_name TEXT,
                ip_address TEXT,
                action TEXT NOT NULL,
                job_id INTEGER,
                patient_id TEXT,
                patient_name TEXT,
                details TEXT
            )
            """)

            # Foydalanuvchi sessiyalari
            conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                full_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """)

            # 1000+ bemorlar uchun yuqori tezlikdagi indekslar
            conn.execute("CREATE INDEX IF NOT EXISTS idx_print_jobs_created_at ON print_jobs(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_print_jobs_patient_id ON print_jobs(patient_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_print_jobs_sample_no ON print_jobs(sample_no)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_print_jobs_patient_name ON print_jobs(patient_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_print_jobs_status ON print_jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_print_jobs_delivery ON print_jobs(delivery_status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_job_id ON audit_logs(job_id)")
            
            conn.commit()

    def get_today_str(self):
        return datetime.date.today().isoformat()

    def _increment_stat(self, field):
        today = self.get_today_str()
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(f"""
            INSERT INTO daily_stats (date, {field}, updated_at)
            VALUES (?, 1, ?)
            ON CONFLICT(date) DO UPDATE SET
                {field} = {field} + 1,
                updated_at = excluded.updated_at
            """, (today, now))
            conn.commit()

    # =========================================================================
    # AUDIT LOGGING & SESSIONS
    # =========================================================================
    def add_audit_log(self, user_login, user_name, ip_address, action, job_id=None, patient_id=None, patient_name=None, details=""):
        now_str = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO audit_logs (
                created_at, user_login, user_name, ip_address, action,
                job_id, patient_id, patient_name, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now_str, user_login, user_name, ip_address, action,
                job_id, patient_id, patient_name, details
            ))
            conn.commit()

    def get_audit_logs(self, limit=100):
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def create_session(self, username, full_name, duration_hours=24):
        token = secrets.token_hex(24)
        now = datetime.datetime.now()
        exp = now + datetime.timedelta(hours=duration_hours)
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO auth_sessions (token, username, full_name, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """, (token, username, full_name, now.isoformat(), exp.isoformat()))
            conn.commit()
        return token

    def validate_session(self, token):
        if not token:
            return None
        now_str = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            row = conn.execute("""
            SELECT * FROM auth_sessions WHERE token = ? AND expires_at > ?
            """, (token, now_str)).fetchone()
            return dict(row) if row else None

    def delete_session(self, token):
        if not token:
            return
        with self._get_connection() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
            conn.commit()

    # =========================================================================
    # PLONKALARNI SAQLASH VA BOSHQARISH
    # =========================================================================
    def save_print_job(self, job_uid, film_session_ds, film_box_ds, images_map, calling_aet="SIEMENS"):
        """
        Siemensdan kelgan barcha DICOM ma'lumotlarini arxivga saqlash va KarMed bilan boyitish
        """
        now = datetime.datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        timestamp_str = now.strftime('%Y%m%d_%H%M%S')
        
        # Demografik ma'lumotlarni aniqlash va KarMeddan qidirish
        patient_info = self._extract_demographics(film_session_ds, film_box_ds, images_map)
        patient_id = patient_info.get('patient_id') or f"MR_{int(now.timestamp())}"
        patient_name = patient_info.get('patient_name') or f"BEMOR_{patient_id}"
        sample_no = patient_info.get('sample_no') or patient_id
        phone_number = patient_info.get('phone_number') or ''
        
        # Xavfsiz papka nomi
        clean_name = "".join(c for c in patient_name if c.isalnum() or c in (' ', '_', '-')).strip()[:30]
        folder_name = f"{timestamp_str}_{sample_no}_{clean_name}".replace(' ', '_')
        job_archive_dir = os.path.join(self.archive_dir, today_str, folder_name)
        images_dir = os.path.join(job_archive_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)
        
        # Plonka parametrlari
        film_format = getattr(film_box_ds, 'ImageDisplayFormat', 'STANDARD\\2,3')
        film_size = getattr(film_box_ds, 'FilmSizeID', '14INX17IN')
        orientation = getattr(film_box_ds, 'FilmOrientation', 'PORTRAIT')
        copies = int(getattr(film_session_ds, 'NumberOfCopies', 1) or 1)
        
        cols, rows = self._parse_display_format(film_format)
        
        # Har bir kadrdan tasvir va DICOM fayl yaratish
        frames_data = []
        pil_frames = {}
        sorted_boxes = sorted(images_map.values(), key=lambda b: b.get('position', 1))
        
        for item in sorted_boxes:
            pos = item.get('position', 1)
            ds = item.get('dataset')
            if not ds:
                continue
                
            img_seq = getattr(ds, 'BasicGrayscaleImageSequence', None)
            if not img_seq or len(img_seq) == 0:
                continue
                
            raw_img_ds = img_seq[0]
            
            # 1. Standart DICOM fayl (.dcm)
            dcm_filename = f"frame_{pos:02d}.dcm"
            dcm_path = os.path.join(images_dir, dcm_filename)
            self._save_image_as_dicom(raw_img_ds, patient_info, pos, dcm_path)
            
            # 2. NumPy va PIL tasvir
            pil_img = self._dataset_to_pil(raw_img_ds)
            if pil_img:
                png_filename = f"frame_{pos:02d}.png"
                png_path = os.path.join(images_dir, png_filename)
                pil_img.save(png_path, format="PNG")
                pil_frames[pos] = pil_img
                
                # Agar namuna raqami yoki bemor F.I.SH hali aniqlanmagan bo'lsa, 1-kadr overlayidan o'qish
                if pos == 1 and (not patient_info.get('sample_no') or not patient_info.get('patient_name') or patient_info['patient_name'].startswith('BEMOR_')):
                    detected_sample = self._extract_sample_from_image(pil_img)
                    if detected_sample:
                        print(f"[Storage] Tasvirdan namuna raqami o'qildi: {detected_sample}")
                        patient_info['sample_no'] = detected_sample
                        sample_no = detected_sample
                        k_data = self.karmed.lookup_patient(detected_sample)
                        if k_data:
                            print(f"[Storage] KarMeddan topildi: {k_data.get('patient_name')}, Tel: {k_data.get('phone_number')}")
                            for k in ('patient_name', 'patient_id', 'protocol_no', 'phone_number'):
                                if k_data.get(k):
                                    patient_info[k] = k_data[k]
                            patient_name = patient_info['patient_name']
                            patient_id = patient_info['patient_id']
                            phone_number = patient_info['phone_number']
                            # 1-kadr DICOM faylini yangilangan bemor ma'lumotlari bilan qayta saqlash
                            try:
                                self._save_image_as_dicom(raw_img_ds, patient_info, pos, dcm_path)
                            except Exception:
                                pass
                
            frames_data.append({
                'position': pos,
                'rows': getattr(raw_img_ds, 'Rows', 0),
                'columns': getattr(raw_img_ds, 'Columns', 0),
                'bits_stored': getattr(raw_img_ds, 'BitsStored', 8),
                'dcm_file': os.path.relpath(dcm_path, job_archive_dir).replace('\\', '/'),
                'png_file': os.path.relpath(png_path, job_archive_dir).replace('\\', '/') if pil_img else None
            })
            
        # 3. 14x17 dyuymli umumiy kompozit ko'rinish (Composite Sheet)
        preview_filename = "preview_sheet.png"
        preview_path = os.path.join(job_archive_dir, preview_filename)
        self._render_composite_film(
            pil_frames=pil_frames,
            cols=cols,
            rows=rows,
            patient_info=patient_info,
            film_format=film_format,
            film_size=film_size,
            orientation=orientation,
            save_path=preview_path
        )
        
        # 4. Metadata.json
        metadata = {
            'job_uid': job_uid,
            'calling_aet': calling_aet,
            'created_at': now.isoformat(),
            'patient': patient_info,
            'film': {
                'format': film_format,
                'size': film_size,
                'orientation': orientation,
                'copies': copies,
                'cols': cols,
                'rows': rows,
                'total_frames': len(frames_data)
            },
            'frames': frames_data
        }
        with open(os.path.join(job_archive_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        rel_preview = os.path.relpath(preview_path, self.base_dir).replace('\\', '/')
        rel_archive = os.path.relpath(job_archive_dir, self.base_dir).replace('\\', '/')
        
        # 5. SQLite ga yozish
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO print_jobs (
                job_uid, patient_id, sample_no, patient_name, phone_number,
                patient_dob, patient_gender, study_date, study_time, protocol_no,
                modality, film_format, film_size, orientation, copies,
                total_frames, archive_dir, preview_image, status, fuji_status,
                delivery_status, print_count, print_success_count, print_fail_count,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
            """, (
                job_uid,
                patient_id,
                sample_no,
                patient_name,
                phone_number,
                patient_info.get('patient_dob', ''),
                patient_info.get('patient_gender', ''),
                patient_info.get('study_date', today_str),
                patient_info.get('study_time', now.strftime('%H:%M:%S')),
                patient_info.get('protocol_no', ''),
                'MR',
                film_format,
                film_size,
                orientation,
                copies,
                len(frames_data),
                rel_archive,
                rel_preview,
                'SAVED',
                'PENDING',
                'PENDING_PICKUP',
                now.isoformat()
            ))
            job_id = cur.lastrowid
            conn.commit()
            
        self._increment_stat('total_received')
        self._increment_stat('total_saved')
        
        # Audit jurnali
        self.add_audit_log(
            user_login="SIEMENS",
            user_name=f"Siemens Magnetom Altea ({calling_aet})",
            ip_address="10.34.14.33",
            action="JOB_RECEIVED",
            job_id=job_id,
            patient_id=patient_id,
            patient_name=patient_name,
            details=f"Plonka saqlandi: Namuna #{sample_no}, Format: {film_format}, {len(frames_data)} kadr"
        )
        
        return self.get_job_by_id(job_id)

    def save_remote_agent_job(self, payload: dict):
        """
        Masofaviy Agentdan (boshqa filial yoki tomografdan) shifrlanib kelgan
        plonkani qabul qilish, keshga saqlash va KarMed bilan boyitish.
        """
        job_uid = payload.get('job_uid') or f"JOB_{int(time.time())}_{secrets.token_hex(4)}"
        clinic = payload.get('source_clinic', 'Filial')
        modality_name = payload.get('source_modality', 'MRT')
        calling_aet = payload.get('calling_aet', 'AGENT')
        film_format = payload.get('film_format', 'STANDARD\\1,1')
        film_size = payload.get('film_size', '14INX17IN')
        orientation = payload.get('orientation', 'PORTRAIT')
        frames_list = payload.get('frames', [])

        now = datetime.datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        timestamp_str = now.strftime('%Y%m%d_%H%M%S')

        patient_info = {
            'patient_id': f"MR_{int(now.timestamp())}",
            'sample_no': '',
            'patient_name': '',
            'patient_dob': '',
            'patient_gender': '',
            'study_date': today_str,
            'study_time': now.strftime('%H:%M:%S'),
            'protocol_no': '',
            'phone_number': ''
        }

        temp_name = f"{timestamp_str}_AGENT_{clinic}".replace(' ', '_')
        job_archive_dir = os.path.join(self.archive_dir, today_str, temp_name)
        images_dir = os.path.join(job_archive_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)

        cols, rows = self._parse_display_format(film_format)
        pil_frames = {}
        frames_data = []

        for frame_item in frames_list:
            pos = frame_item.get('position', 1)
            rows_px = frame_item.get('rows', 0)
            cols_px = frame_item.get('columns', 0)
            b64_pixels = frame_item.get('pixel_data_b64', '')
            if not b64_pixels or rows_px <= 0 or cols_px <= 0:
                continue

            raw_bytes = base64.b64decode(b64_pixels.encode('ascii'))
            
            ds = Dataset()
            ds.Rows = rows_px
            ds.Columns = cols_px
            ds.BitsAllocated = frame_item.get('bits_allocated', 16)
            ds.BitsStored = frame_item.get('bits_stored', 12)
            ds.HighBit = frame_item.get('high_bit', 11)
            ds.PixelRepresentation = frame_item.get('pixel_representation', 0)
            ds.PhotometricInterpretation = frame_item.get('photometric', 'MONOCHROME2')
            ds.PixelData = raw_bytes

            pil_img = self._dataset_to_pil(ds)
            if pil_img:
                png_path = os.path.join(images_dir, f"frame_{pos:02d}.png")
                pil_img.save(png_path, format="PNG")
                pil_frames[pos] = pil_img

                if pos == 1:
                    detected_sample = self._extract_sample_from_image(pil_img)
                    if detected_sample:
                        patient_info['sample_no'] = detected_sample
                        k_data = self.karmed.lookup_patient(detected_sample)
                        if k_data:
                            for k in ('patient_name', 'patient_id', 'protocol_no', 'phone_number'):
                                if k_data.get(k):
                                    patient_info[k] = k_data[k]

            dcm_path = os.path.join(images_dir, f"frame_{pos:02d}.dcm")
            self._save_image_as_dicom(ds, patient_info, pos, dcm_path)

            frames_data.append({
                'position': pos,
                'rows': rows_px,
                'columns': cols_px,
                'bits_stored': frame_item.get('bits_stored', 12),
                'dcm_file': os.path.relpath(dcm_path, job_archive_dir).replace('\\', '/'),
                'png_file': os.path.relpath(png_path, job_archive_dir).replace('\\', '/') if pil_img else None
            })

        sample_no = patient_info.get('sample_no') or patient_info['patient_id']
        patient_name = patient_info.get('patient_name') or f"BEMOR_{sample_no}"
        patient_id = patient_info.get('patient_id')
        phone_number = patient_info.get('phone_number', '')

        clean_name = "".join(c for c in patient_name if c.isalnum() or c in (' ', '_', '-')).strip()[:30]
        final_folder_name = f"{timestamp_str}_{sample_no}_{clean_name}".replace(' ', '_')
        final_archive_dir = os.path.join(self.archive_dir, today_str, final_folder_name)
        if job_archive_dir != final_archive_dir:
            try:
                os.rename(job_archive_dir, final_archive_dir)
                job_archive_dir = final_archive_dir
            except Exception:
                pass

        preview_path = os.path.join(job_archive_dir, "preview_sheet.png")
        self._render_composite_film(
            pil_frames=pil_frames,
            cols=cols,
            rows=rows,
            patient_info=patient_info,
            film_format=film_format,
            film_size=film_size,
            orientation=orientation,
            save_path=preview_path
        )

        metadata = {
            'job_uid': job_uid,
            'source_clinic': clinic,
            'source_modality': modality_name,
            'calling_aet': calling_aet,
            'created_at': now.isoformat(),
            'patient': patient_info,
            'film': {
                'format': film_format,
                'size': film_size,
                'orientation': orientation,
                'copies': 1,
                'cols': cols,
                'rows': rows,
                'total_frames': len(frames_data)
            },
            'frames': frames_data
        }
        with open(os.path.join(job_archive_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        rel_preview = os.path.relpath(preview_path, self.base_dir).replace('\\', '/')
        rel_archive = os.path.relpath(job_archive_dir, self.base_dir).replace('\\', '/')

        modality_display = f"{clinic} ({modality_name})"

        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO print_jobs (
                job_uid, patient_id, sample_no, patient_name, phone_number,
                patient_dob, patient_gender, study_date, study_time, protocol_no,
                modality, film_format, film_size, orientation, copies,
                total_frames, archive_dir, preview_image, status, fuji_status,
                delivery_status, print_count, print_success_count, print_fail_count,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)
            """, (
                job_uid,
                patient_id,
                sample_no,
                patient_name,
                phone_number,
                patient_info.get('patient_dob', ''),
                patient_info.get('patient_gender', ''),
                patient_info.get('study_date', today_str),
                patient_info.get('study_time', now.strftime('%H:%M:%S')),
                patient_info.get('protocol_no', ''),
                modality_display,
                film_format,
                film_size,
                orientation,
                1,
                len(frames_data),
                rel_archive,
                rel_preview,
                'SAVED',
                'PENDING',
                'PENDING_PICKUP',
                now.isoformat()
            ))
            job_id = cur.lastrowid
            conn.commit()

        self._increment_stat('total_received')
        self._increment_stat('total_saved')

        self.add_audit_log(
            user_login="AGENT",
            user_name=f"Agent: {clinic}",
            ip_address=calling_aet,
            action="AGENT_JOB_RECEIVED",
            job_id=job_id,
            patient_id=patient_id,
            patient_name=patient_name,
            details=f"{clinic} apparatidan shifrlangan plonka qabul qilindi va keshga saqlandi"
        )
        print(f"[Admin] Agentdan plonka qabul qilindi: ID={job_id}, Bemor={patient_name}, Namuna={sample_no}")
        return self.get_job_by_id(job_id)

    def record_print_attempt(self, job_id, success, error_msg=""):
        """Chop etish urinishi hisobini yuritish"""
        now_str = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            if success:
                conn.execute("""
                UPDATE print_jobs SET 
                    status = 'PRINTED', 
                    fuji_status = 'PRINTED', 
                    printed_at = ?, 
                    last_print_attempt = ?, 
                    print_count = COALESCE(print_count, 0) + 1, 
                    print_success_count = COALESCE(print_success_count, 0) + 1,
                    error_message = NULL,
                    delivery_status = CASE WHEN delivery_status IS NULL OR delivery_status = '' THEN 'PENDING_PICKUP' ELSE delivery_status END
                WHERE id = ?
                """, (now_str, now_str, job_id))
                self._increment_stat('total_printed')
            else:
                conn.execute("""
                UPDATE print_jobs SET 
                    status = 'FORWARD_FAILED', 
                    fuji_status = 'ERROR', 
                    last_print_attempt = ?, 
                    print_count = COALESCE(print_count, 0) + 1, 
                    print_fail_count = COALESCE(print_fail_count, 0) + 1,
                    error_message = ?
                WHERE id = ?
                """, (now_str, str(error_msg), job_id))
                self._increment_stat('total_failed')
            conn.commit()
        return self.get_job_by_id(job_id)

    def update_job_status(self, job_id, status, fuji_status=None, error_msg=None):
        with self._get_connection() as conn:
            params = [status]
            q = "UPDATE print_jobs SET status = ?"
            if fuji_status is not None:
                q += ", fuji_status = ?"
                params.append(fuji_status)
            if error_msg is not None:
                q += ", error_message = ?"
                params.append(str(error_msg))
            elif status == 'PRINTED':
                q += ", error_message = NULL"
            if status == 'PRINTED':
                now_str = datetime.datetime.now().isoformat()
                q += ", printed_at = ?"
                params.append(now_str)
                self._increment_stat('total_printed')
            elif status == 'FORWARD_FAILED':
                self._increment_stat('total_failed')
                
            q += " WHERE id = ?"
            params.append(job_id)
            conn.execute(q, params)
            conn.commit()
        return self.get_job_by_id(job_id)

    def update_delivery_status(self, job_id, delivery_status, delivered_by=""):
        now_str = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            if delivery_status == 'DELIVERED':
                conn.execute("""
                UPDATE print_jobs SET 
                    delivery_status = 'DELIVERED', 
                    delivered_at = ?, 
                    delivered_by = ? 
                WHERE id = ?
                """, (now_str, delivered_by, job_id))
            else:
                conn.execute("""
                UPDATE print_jobs SET 
                    delivery_status = 'PENDING_PICKUP', 
                    delivered_at = NULL, 
                    delivered_by = NULL 
                WHERE id = ?
                """, (job_id,))
            conn.commit()
        return self.get_job_by_id(job_id)

    def update_patient_details(self, job_id, patient_name=None, patient_id=None, sample_no=None, phone_number=None):
        with self._get_connection() as conn:
            updates = []
            params = []
            if patient_name is not None:
                updates.append("patient_name = ?")
                params.append(patient_name)
            if patient_id is not None:
                updates.append("patient_id = ?")
                params.append(patient_id)
            if sample_no is not None:
                updates.append("sample_no = ?")
                params.append(sample_no)
            if phone_number is not None:
                updates.append("phone_number = ?")
                params.append(format_uzbek_phone(phone_number))
            if updates:
                params.append(job_id)
                conn.execute(f"UPDATE print_jobs SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()
        return self.get_job_by_id(job_id)

    def get_job_by_id(self, job_id):
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM print_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def get_recent_jobs(self, limit=500, delivery_filter=None, search=None, search_sample=None, search_id=None, search_name=None):
        with self._get_connection() as conn:
            query = "SELECT * FROM print_jobs WHERE 1=1"
            params = []
            
            if delivery_filter == 'PENDING_PICKUP':
                query += " AND status = 'PRINTED' AND (delivery_status IS NULL OR delivery_status = 'PENDING_PICKUP')"
            elif delivery_filter == 'DELIVERED':
                query += " AND delivery_status = 'DELIVERED'"
            elif delivery_filter == 'PRINTED':
                query += " AND status = 'PRINTED'"
            elif delivery_filter == 'SAVED':
                query += " AND status = 'SAVED'"
                
            # 1. Alohida Namuna raqami bo'yicha qidiruv (Indekslangan)
            if search_sample and search_sample.strip():
                query += " AND (sample_no LIKE ? OR sample_no = ?)"
                val = search_sample.strip()
                params.extend([f"%{val}%", val])

            # 2. Alohida Bemor ID bo'yicha qidiruv (Indekslangan)
            if search_id and search_id.strip():
                query += " AND (patient_id LIKE ? OR patient_id = ?)"
                val = search_id.strip()
                params.extend([f"%{val}%", val])

            # 3. Alohida Bemor F.I.SH bo'yicha qidiruv (Indekslangan)
            if search_name and search_name.strip():
                query += " AND LOWER(patient_name) LIKE ?"
                params.append(f"%{search_name.strip().lower()}%")

            # 4. Umumiy qidiruv (agar kiritilgan bo'lsa)
            if search and search.strip():
                s_param = f"%{search.strip().lower()}%"
                query += " AND (LOWER(patient_name) LIKE ? OR LOWER(patient_id) LIKE ? OR LOWER(COALESCE(sample_no,'')) LIKE ? OR LOWER(COALESCE(phone_number,'')) LIKE ?)"
                params.extend([s_param, s_param, s_param, s_param])
                
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self):
        today = self.get_today_str()
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM daily_stats WHERE date = ?", (today,)).fetchone()
            totals = conn.execute("""
            SELECT 
                COUNT(*) as total_all,
                SUM(CASE WHEN status = 'PRINTED' THEN 1 ELSE 0 END) as printed_all,
                SUM(CASE WHEN status = 'SAVED' THEN 1 ELSE 0 END) as saved_all,
                SUM(CASE WHEN status = 'FORWARD_FAILED' THEN 1 ELSE 0 END) as failed_all,
                SUM(CASE WHEN status = 'PRINTED' AND (delivery_status IS NULL OR delivery_status = 'PENDING_PICKUP') THEN 1 ELSE 0 END) as pending_pickup_all,
                SUM(CASE WHEN delivery_status = 'DELIVERED' THEN 1 ELSE 0 END) as delivered_all
            FROM print_jobs
            """).fetchone()

            t_dict = dict(row) if row else {
                'date': today,
                'total_received': 0,
                'total_printed': 0,
                'total_saved': 0,
                'total_failed': 0
            }
            
            t_dict['pending_pickup'] = totals['pending_pickup_all'] or 0 if totals else 0
            t_dict['delivered'] = totals['delivered_all'] or 0 if totals else 0

            return {
                'today': t_dict,
                'all_time': dict(totals) if totals else {}
            }

    # =========================================================================
    # DEMOGRAFIYA VA TIBBIY TASVIRLAR
    # =========================================================================
    def _match_digit(self, char_img):
        """12px li Siemens Altea shrifti bilan raqamni aniqlash (surilishlarni hisobga olgan holda)"""
        if not self._digit_templates:
            return None, 0.0
            
        r_sums = char_img.sum(axis=1)
        nz_r = np.where(r_sums > 0)[0]
        if len(nz_r) > 0:
            char_img = char_img[nz_r[0]:nz_r[-1]+1, :]
            
        best_digit = None
        best_score = -1.0
        h, w = char_img.shape
        for d, t in self._digit_templates.items():
            th, tw = t.shape
            pad_h = max(h, th) + 2
            pad_w = max(w, tw) + 2
            
            pc = np.zeros((pad_h, pad_w), dtype=np.uint8)
            pc[1:1+h, 1:1+w] = char_img
            
            for dy in range(pad_h - th + 1):
                for dx in range(pad_w - tw + 1):
                    pt = np.zeros((pad_h, pad_w), dtype=np.uint8)
                    pt[dy:dy+th, dx:dx+tw] = t
                    intersection = np.sum(pc & pt)
                    union = np.sum(pc | pt)
                    score = intersection / union if union > 0 else 0
                    if score > best_score:
                        best_score = score
                        best_digit = d
        return best_digit, best_score

    def _recognize_digits_from_crop(self, arr_crop):
        """Binarizatsiya qilingan satrdan raqamlarni ajratib o'qish"""
        col_sums = arr_crop.sum(axis=0)
        chars = []
        in_c = False
        sx = 0
        for x, s in enumerate(col_sums):
            if s > 0 and not in_c:
                in_c = True
                sx = x
            elif s == 0 and in_c:
                in_c = False
                if x - sx >= 2:
                    chars.append((sx, x))
        if in_c:
            chars.append((sx, len(col_sums)))
            
        res = ""
        for sx, ex in chars:
            char_img = arr_crop[:, sx:ex]
            d, score = self._match_digit(char_img)
            if score >= 0.28:
                res += str(d)
        return res

    def _extract_sample_from_image(self, pil_img):
        """Siemens Altea MRT tasvirining yuqori-chap burchagidan namuna raqamini (HastaSiraNo) o'qish"""
        try:
            corner = pil_img.crop((10, 10, min(500, pil_img.width), 200))
            arr = np.array(corner)
            bin_arr = (arr > 130).astype(np.uint8)
            
            row_sums = bin_arr.sum(axis=1)
            lines = []
            in_line = False
            start_y = 0
            for y, s in enumerate(row_sums):
                if s > 0 and not in_line:
                    in_line = True
                    start_y = y
                elif s == 0 and in_line:
                    in_line = False
                    if y - start_y >= 8:
                        lines.append((start_y, y))
            if in_line:
                lines.append((start_y, len(row_sums)))
                
            # Line 1 da namuna raqami (masalan: 3404359)
            if len(lines) >= 2:
                y1, y2 = lines[1]
                num_str = self._recognize_digits_from_crop(bin_arr[y1:y2, :120])
                if num_str and len(num_str) >= 4:
                    return num_str
                    
            # Line 0 ni ham tekshirish
            if len(lines) >= 1:
                y1, y2 = lines[0]
                num_str = self._recognize_digits_from_crop(bin_arr[y1:y2, :120])
                if num_str and len(num_str) >= 4:
                    return num_str
        except Exception as e:
            print(f"[Storage] Tasvirdan namuna raqamini o'qishda xatolik: {e}")
        return None

    def _extract_demographics(self, fs_ds, fb_ds, images_map):
        info = {
            'patient_id': '',
            'sample_no': '',
            'patient_name': '',
            'patient_dob': '',
            'patient_gender': '',
            'study_date': '',
            'study_time': '',
            'protocol_no': '',
            'phone_number': ''
        }
        
        # 1. Film session label tekshirish
        label = str(getattr(fs_ds, 'FilmSessionLabel', '') or '').strip()
        if label:
            info['patient_name'] = label
            m_sira = re.search(r'\b(?:SIRA|ID|NO|NAMUNA|STID)?\s*[:=#-]?\s*(\d{4,12})\b', label, re.I)
            if m_sira:
                info['sample_no'] = m_sira.group(1)
            
        # 2. Barcha mavjud DICOM datasetlaridan (fs_ds, fb_ds, ds, seq) to'liq qidirish
        datasets_to_check = [fs_ds, fb_ds]
        for box in images_map.values():
            ds = box.get('dataset')
            if ds:
                datasets_to_check.append(ds)
                seq = getattr(ds, 'BasicGrayscaleImageSequence', None)
                if seq and len(seq) > 0:
                    datasets_to_check.append(seq[0])

        for target in datasets_to_check:
            if not target:
                continue
            for field, tag in [
                ('patient_id', 'PatientID'),
                ('patient_name', 'PatientName'),
                ('patient_dob', 'PatientBirthDate'),
                ('patient_gender', 'PatientSex'),
                ('study_date', 'StudyDate'),
                ('study_time', 'StudyTime'),
                ('protocol_no', 'ProtocolName')
            ]:
                if not info[field] and hasattr(target, tag):
                    val = str(getattr(target, tag) or '').strip()
                    if val and not val.startswith('000000'):
                        info[field] = val
                        
            # Namuna raqami yoki Accession Number
            if not info['sample_no']:
                for tag in ['AccessionNumber', 'StudyID', 'RequestedProcedureID']:
                    if hasattr(target, tag):
                        v = str(getattr(target, tag) or '').strip()
                        if v:
                            info['sample_no'] = v
                            break

            # Agar dataset ichida 5-10 xonali son bo'lsa (namuna raqami)
            if not info['sample_no']:
                for elem in target:
                    if elem.VR in ('LO', 'SH', 'IS', 'CS') and elem.value:
                        val_s = str(elem.value).strip()
                        m_num = re.search(r'\b(\d{6,10})\b', val_s)
                        if m_num:
                            info['sample_no'] = m_num.group(1)
                            break

        if not info['sample_no'] and info['patient_id'] and info['patient_id'].isdigit():
            info['sample_no'] = info['patient_id']

        # KarMeddan avtomatik boyitish
        lookup_key = info['sample_no'] or info['patient_id']
        if lookup_key:
            karmed_data = self.karmed.lookup_patient(lookup_key)
            if karmed_data:
                if karmed_data.get('patient_name'):
                    info['patient_name'] = karmed_data['patient_name']
                if karmed_data.get('patient_id'):
                    info['patient_id'] = karmed_data['patient_id']
                if karmed_data.get('protocol_no'):
                    info['protocol_no'] = karmed_data['protocol_no']
                if karmed_data.get('phone_number'):
                    info['phone_number'] = karmed_data['phone_number']
                if karmed_data.get('sample_no'):
                    info['sample_no'] = karmed_data['sample_no']

        if not info['patient_id']:
            info['patient_id'] = f"MR_{int(datetime.datetime.now().timestamp())}"
        if not info['patient_name']:
            info['patient_name'] = f"BEMOR_{info['patient_id']}"
            
        return info

    def _parse_display_format(self, fmt_str):
        cols, rows = 2, 3
        if fmt_str and 'STANDARD\\' in fmt_str:
            clean = fmt_str.replace('STANDARD\\', '')
            parts = clean.split(',')
            if len(parts) >= 2:
                try:
                    cols = int(parts[0])
                    rows = int(parts[1])
                except ValueError:
                    pass
        return max(1, cols), max(1, rows)

    def _dataset_to_pil(self, img_ds):
        try:
            rows = int(getattr(img_ds, 'Rows', 0))
            cols = int(getattr(img_ds, 'Columns', 0))
            if rows <= 0 or cols <= 0:
                return None
                
            bits_alloc = int(getattr(img_ds, 'BitsAllocated', 8))
            photometric = str(getattr(img_ds, 'PhotometricInterpretation', 'MONOCHROME2')).strip()
            pixel_bytes = img_ds.PixelData
            
            dtype = np.uint16 if bits_alloc > 8 else np.uint8
            arr = np.frombuffer(pixel_bytes, dtype=dtype)
            expected_len = rows * cols
            if len(arr) < expected_len:
                return None
            arr = arr[:expected_len].reshape((rows, cols))
            
            # 8-bit normalizatsiya
            min_v = float(arr.min())
            max_v = float(arr.max())
            if max_v > min_v:
                norm = ((arr.astype(np.float32) - min_v) / (max_v - min_v) * 255.0).astype(np.uint8)
            else:
                norm = np.zeros((rows, cols), dtype=np.uint8)
                
            if photometric == 'MONOCHROME1':
                norm = 255 - norm
                
            return Image.fromarray(norm, mode='L')
        except Exception as e:
            print(f"[Storage] Tasvirga o'tkazishda xato: {e}")
            return None

    def _render_composite_film(self, pil_frames, cols, rows, patient_info, film_format, film_size, orientation, save_path):
        """To'liq 14x17 dyuymli fizik rentgen/MRT plonkasi simulyatsiyasini chizish"""
        width, height = (1120, 1440) if orientation == 'PORTRAIT' else (1440, 1120)
        film = Image.new('RGB', (width, height), color=(10, 12, 16))
        draw = ImageDraw.Draw(film)
        
        # Sarlavha
        header_h = 65
        draw.rectangle([(0, 0), (width, header_h)], fill=(15, 23, 42))
        draw.line([(0, header_h), (width, header_h)], fill=(51, 65, 85), width=2)
        
        p_name = patient_info.get('patient_name', 'NOMALUM')
        p_id = patient_info.get('patient_id', '-')
        s_no = patient_info.get('sample_no', '-')
        p_phone = patient_info.get('phone_number', '')
        s_date = patient_info.get('study_date', datetime.date.today().isoformat())
        
        draw.text((20, 10), f"🏥 {self.hospital_name}", fill=(241, 245, 249))
        phone_txt = f" | Tel: {p_phone}" if p_phone else ""
        draw.text((20, 34), f"Bemor: {p_name} | Namuna: #{s_no} | ID: {p_id}{phone_txt} | Sana: {s_date}", fill=(148, 163, 184))
        
        dev_text = f"{self.modality_name} | {film_format} ({film_size})"
        draw.text((width - 450, 20), dev_text, fill=(56, 189, 248))
        
        # Kataklar
        margin = 8
        avail_w = width - margin * (cols + 1)
        avail_h = height - header_h - margin * (rows + 1)
        cell_w = avail_w // cols
        cell_h = avail_h // rows
        
        for r in range(rows):
            for c in range(cols):
                pos = r * cols + c + 1
                x = margin + c * (cell_w + margin)
                y = header_h + margin + r * (cell_h + margin)
                draw.rectangle([(x, y), (x + cell_w, y + cell_h)], fill=(0, 0, 0), outline=(30, 41, 59), width=1)
                
                if pos in pil_frames:
                    frame_img = pil_frames[pos]
                    frame_img.thumbnail((cell_w - 4, cell_h - 4), Image.Resampling.LANCZOS)
                    offset_x = x + (cell_w - frame_img.width) // 2
                    offset_y = y + (cell_h - frame_img.height) // 2
                    film.paste(frame_img, (offset_x, offset_y))
                    
                draw.text((x + 6, y + 4), f"#{pos}", fill=(100, 116, 139))
                
        film.save(save_path, format="PNG")

    def _save_image_as_dicom(self, raw_ds, patient_info, position, out_path):
        """Xom piksel ma'lumotlarini to'liq standart DICOM Secondary Capture fayliga aylantirish"""
        try:
            file_meta = FileMetaDataset()
            file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
            file_meta.MediaStorageSOPInstanceUID = generate_uid()
            file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            
            ds = Dataset()
            ds.file_meta = file_meta
            ds.is_little_endian = True
            ds.is_implicit_VR = False
            
            ds.PatientName = str(patient_info.get('patient_name', 'NOMALUM'))
            ds.PatientID = str(patient_info.get('patient_id', '000000'))
            ds.PatientBirthDate = str(patient_info.get('patient_dob', ''))
            ds.PatientSex = str(patient_info.get('patient_gender', 'O'))
            ds.StudyDate = str(patient_info.get('study_date', datetime.date.today().strftime('%Y%m%d')))
            ds.Modality = "MR"
            ds.InstanceNumber = position
            
            ds.SOPClassUID = SecondaryCaptureImageStorage
            ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
            ds.Rows = raw_ds.Rows
            ds.Columns = raw_ds.Columns
            ds.SamplesPerPixel = getattr(raw_ds, 'SamplesPerPixel', 1)
            ds.PhotometricInterpretation = getattr(raw_ds, 'PhotometricInterpretation', 'MONOCHROME2')
            ds.BitsAllocated = getattr(raw_ds, 'BitsAllocated', 8)
            ds.BitsStored = getattr(raw_ds, 'BitsStored', 8)
            ds.HighBit = getattr(raw_ds, 'HighBit', 7)
            ds.PixelRepresentation = getattr(raw_ds, 'PixelRepresentation', 0)
            ds.PixelData = raw_ds.PixelData
            
            ds.save_as(out_path, write_like_original=False)
        except Exception as e:
            print(f"[Storage] DICOM saqlashda xato: {e}")
