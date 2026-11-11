"""
github_relay.py - GitHub Relay, Cloud Discovery va 1-soatlik TTL xizmati moduli
GitHub Pages (github.io) va GitHub REST API orqali Agent va Admin aloqasini ta'minlaydi.

Xavfsizlik qoidalari:
1. Barcha ma'lumotlar faqat AES-256-GCM bilan shifrlangan (.enc) holatda uzatiladi.
2. GitHub sahifasida yoki repoda HECH QANDAY bemor ismi, rasmi yoki shaxsiy ma'lumotlari ko'rinmaydi.
3. Admin qabul qilib olishi bilan fayl GitHubdan bir zumda o'chiriladi (DELETE).
4. Agar 1 soat ichida qabul qilinmasa, avtomatik o'chiriladi (TTL: 60 daqiqa).
5. Agar Admin offline bo'lsa, Agent ma'lumotni GitHubga chiqarmaydi, o'zining mahalliy keshida (outbox) saqlab turadi.
"""
import os
import sys
import time
import json
import base64
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

class GitHubRelayClient:
    def __init__(self, config: dict):
        self.config = config
        relay_cfg = config.get('github_relay', {})
        self.enabled = relay_cfg.get('enabled', False)
        self.repo = relay_cfg.get('repo', '').strip() # Masalan: "onkologiya-radiologiya/dicom-hub"
        self.token = relay_cfg.get('token', '').strip() # GitHub Personal Access Token (ghp_...)
        self.branch = relay_cfg.get('branch', 'main')
        self.queue_dir = relay_cfg.get('queue_dir', 'queue')
        self.status_file = relay_cfg.get('status_file', 'admin_status.json')
        self.ttl_minutes = int(relay_cfg.get('ttl_minutes', 60)) # 1 soat
        self.github_io_url = relay_cfg.get('github_io_url', '').strip() # https://username.github.io/repo/

    def _get_headers(self):
        headers = {
            'User-Agent': 'Siemens-Fuji-DICOM-Relay/2.5',
            'Accept': 'application/vnd.github.v3+json'
        }
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    # =========================================================================
    # 1. ADMIN TOMONI: STATUS YUKLASH (HEARTBEAT) & KASHF QILISH
    # =========================================================================
    def update_admin_heartbeat(self, status_data: dict) -> bool:
        """
        Admin kompyuteri har 30 soniyada o'zining faollik holati va IP manzilini GitHubga yozadi.
        Bu fayl ochiq bo'ladi (bemor ma'lumotlari yo'q), Agentlar va github.io sayti orqali o'qiladi.
        """
        if not self.enabled or not self.repo or not self.token:
            return False

        content_bytes = json.dumps(status_data, indent=2, ensure_ascii=False).encode('utf-8')
        b64_content = base64.b64encode(content_bytes).decode('ascii')
        
        url = f"https://api.github.com/repos/{self.repo}/contents/{self.status_file}"
        headers = self._get_headers()
        
        # Mavjud faylning SHA sini olish
        sha = None
        try:
            req_get = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req_get, timeout=5) as res:
                info = json.loads(res.read().decode())
                sha = info.get('sha')
        except Exception:
            pass

        # Faylni yangilash (PUT)
        body = {
            "message": f"Heartbeat ping at {datetime.now(timezone.utc).isoformat()}",
            "content": b64_content,
            "branch": self.branch
        }
        if sha:
            body["sha"] = sha

        try:
            req_put = urllib.request.Request(
                url,
                data=json.dumps(body).encode('utf-8'),
                headers={'Content-Type': 'application/json', **headers},
                method='PUT'
            )
            with urllib.request.urlopen(req_put, timeout=8) as res:
                return res.status in (200, 201)
        except Exception as e:
            # print(f"[GitHubRelay] Heartbeat yangilashda xato: {e}")
            return False

    # =========================================================================
    # 2. AGENT TOMONI: ADMIN HOLATINI VA MANZILINI TEKSHIRISH
    # =========================================================================
    def get_admin_status(self) -> dict:
        """
        Agent Admin kompyuteri onlayn yoki yo'qligini tekshiradi.
        Agar oxirgi signal 5 daqiqadan oshgan bo'lsa, Admin oflayn hisoblanadi.
        """
        if not self.enabled or not self.repo:
            return {"online": False, "reason": "Relay sozlanmagan"}

        # 1. github.io yoki raw orqali tekshirish
        urls_to_try = []
        if self.github_io_url:
            urls_to_try.append(f"{self.github_io_url.rstrip('/')}/{self.status_file}")
        urls_to_try.append(f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/{self.status_file}")
        urls_to_try.append(f"https://api.github.com/repos/{self.repo}/contents/{self.status_file}")

        for u in urls_to_try:
            try:
                headers = self._get_headers() if 'api.github.com' in u else {'User-Agent': 'DICOM-Agent/2.5'}
                req = urllib.request.Request(u, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as res:
                    raw_body = res.read().decode('utf-8')
                    if 'api.github.com' in u:
                        meta = json.loads(raw_body)
                        raw_body = base64.b64decode(meta['content']).decode('utf-8')
                    data = json.loads(raw_body)
                    
                    # Faollik vaqtini tekshirish
                    epoch = data.get('timestamp_epoch', 0)
                    now_epoch = int(time.time())
                    if now_epoch - epoch < 300: # 5 daqiqa
                        return {"online": True, **data}
                    else:
                        return {"online": False, "reason": f"Admin javob bermayapti ({now_epoch - epoch} soniya oldin faol bo'lgan)"}
            except Exception:
                continue

        return {"online": False, "reason": "Admin status faylini o'qib bo'lmadi"}

    # =========================================================================
    # 3. AGENT TOMONI: SHIFRLANGAN PLONKANI GITHUB QUEUE GA YUBORISH
    # =========================================================================
    def push_encrypted_job(self, job_uid: str, encrypted_b64: str) -> bool:
        """
        Shifrlangan ma'lumotni GitHubdagi queue/<job_uid>.enc fayliga joylash.
        MUHIM: Faqat Admin onlayn bo'lsagina yuboriladi!
        """
        if not self.enabled or not self.repo or not self.token:
            return False

        # Admin faoliyatini tekshirish
        admin_st = self.get_admin_status()
        if not admin_st.get('online'):
            print(f"[Agent] Admin oflayn ({admin_st.get('reason')}). Plonka mahalliy navbatda qoladi.")
            return False

        filename = f"{self.queue_dir}/{job_uid}.enc"
        url = f"https://api.github.com/repos/{self.repo}/contents/{filename}"
        headers = self._get_headers()

        # Fayl kontenti shifrlangan Base64 matni bo'ladi
        body = {
            "message": f"Push encrypted job {job_uid}",
            "content": base64.b64encode(encrypted_b64.encode('ascii')).decode('ascii'),
            "branch": self.branch
        }

        try:
            req_put = urllib.request.Request(
                url,
                data=json.dumps(body).encode('utf-8'),
                headers={'Content-Type': 'application/json', **headers},
                method='PUT'
            )
            with urllib.request.urlopen(req_put, timeout=12) as res:
                return res.status in (200, 201)
        except Exception as e:
            print(f"[Agent] GitHubga yuklashda xatolik: {e}")
            return False

    # =========================================================================
    # 4. ADMIN TOMONI: NAVBATDAN SHIFRLANGAN PLONKALARNI OLISH VA O'CHIRISH
    # =========================================================================
    def pull_pending_jobs(self) -> list:
        """
        GitHubdagi queue/ papkasini tekshirib, kutayotgan shifrlangan plonkalarni yuklab oladi.
        Eski (1 soatdan oshgan) fayllarni avtomatik o'chiradi (TTL qoidasi).
        """
        if not self.enabled or not self.repo or not self.token:
            return []

        url = f"https://api.github.com/repos/{self.repo}/contents/{self.queue_dir}?ref={self.branch}"
        headers = self._get_headers()

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as res:
                items = json.loads(res.read().decode())
        except urllib.error.HTTPError as he:
            if he.code == 404:
                return [] # Navbat bo'sh
            return []
        except Exception:
            return []

        jobs = []
        now = time.time()
        ttl_seconds = self.ttl_minutes * 60

        for item in items:
            name = item.get('name', '')
            if not name.endswith('.enc'):
                continue
            
            sha = item.get('sha')
            download_url = item.get('download_url')
            file_path = item.get('path')

            # 1 soatlik muddatni tekshirish (TTL)
            # Nomidan vaqtni aniqlash: masalan JOB_1793721900_uuid.enc
            created_epoch = 0
            parts = name.split('_')
            if len(parts) >= 2 and parts[1].isdigit():
                created_epoch = int(parts[1])

            if created_epoch > 0 and (now - created_epoch) > ttl_seconds:
                print(f"[Admin Relay] 1 soatdan oshgan eski fayl o'chirilmoqda: {name}")
                self.delete_remote_file(file_path, sha)
                continue

            # Kontentni yuklab olish
            try:
                dl_req = urllib.request.Request(download_url, headers=headers)
                with urllib.request.urlopen(dl_req, timeout=12) as dl_res:
                    enc_content = dl_res.read().decode('ascii').strip()
                jobs.append({
                    'name': name,
                    'path': file_path,
                    'sha': sha,
                    'encrypted_b64': enc_content
                })
            except Exception as e:
                print(f"[Admin Relay] Faylni o'qishda xato ({name}): {e}")

        return jobs

    def delete_remote_file(self, file_path: str, sha: str) -> bool:
        """Faylni muvaffaqiyatli qabul qilib olingach, darhol GitHubdan o'chirish"""
        if not self.enabled or not self.repo or not self.token:
            return False

        url = f"https://api.github.com/repos/{self.repo}/contents/{file_path}"
        headers = self._get_headers()
        body = {
            "message": f"Delete processed job {file_path}",
            "sha": sha,
            "branch": self.branch
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode('utf-8'),
                headers={'Content-Type': 'application/json', **headers},
                method='DELETE'
            )
            with urllib.request.urlopen(req, timeout=8) as res:
                return res.status in (200, 204)
        except Exception as e:
            print(f"[Admin Relay] GitHubdan o'chirishda xatolik: {e}")
            return False
