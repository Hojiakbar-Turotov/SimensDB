"""
admin_relay_worker.py - Admin kompyuteridagi GitHub Relay va Cloud Sinxronizatsiya Xizmati
Vazifalari:
1. Har 30 soniyada GitHubga admin_status.json (Heartbeat) yangilab turish (Agentlar Admin onlaynligini bilishi uchun)
2. Har 5-10 soniyada GitHub queue/ papkasidan shifrlangan (.enc) plonkalarni tortib olish
3. Plonkani AES-256-GCM bilan yechish (Decryption)
4. Markaziy arxiv va SQLite bazasiga saqlash (KarMeddan ma'lumotlarni to'ldirish)
5. Muvaffaqiyatli saqlangach, GitHubdan darhol o'chirish (Fayl 1 daqiqadan ortiq turmaydi)
6. 1 soatdan oshgan eski fayllar bo'lsa, avtomatik tozalash (TTL: 60 daqiqa)
"""
import time
import threading
from datetime import datetime, timezone
from crypto_manager import E2EESecurity
from github_relay import GitHubRelayClient

class AdminRelayWorker:
    def __init__(self, config: dict, storage_manager, scu_client):
        self.config = config
        self.storage = storage_manager
        self.scu = scu_client
        self.github = GitHubRelayClient(config)
        
        enc_key = config.get('security', {}).get('encryption_key', '')
        self.security = E2EESecurity(enc_key)
        self.running = True

    def start(self):
        if not self.github.enabled:
            print("[Admin Relay] GitHub Relay o'chirilgan (Faqat mahalliy / to'g'ridan-to'g'ri rejim).")
            return

        print(f"[*] Admin GitHub Relay faollashdi. Repozitoriy: {self.github.repo}")
        
        # 1. Heartbeat pinger (har 30s)
        t_heartbeat = threading.Thread(target=self._heartbeat_loop, daemon=True)
        t_heartbeat.start()

        # 2. Queue puller (har 5-8s)
        t_puller = threading.Thread(target=self._pull_loop, daemon=True)
        t_puller.start()

    def _heartbeat_loop(self):
        while self.running:
            try:
                self._send_heartbeat()
            except Exception as e:
                pass
            time.sleep(30)

    def _send_heartbeat(self):
        now_utc = datetime.now(timezone.utc)
        stats = self.storage.get_stats()
        p_st = self.scu.check_printer()

        srv_cfg = self.config.get('server', {})
        status_data = {
            "status": "ONLINE",
            "timestamp": now_utc.isoformat(),
            "timestamp_epoch": int(now_utc.timestamp()),
            "version": "2.5",
            "hospital": self.config.get('options', {}).get('hospital_name', 'RESPUBLIKA ONKOLOGIYA VA RADIOLOGIYA MARKAZI'),
            "modality": self.config.get('options', {}).get('modality_name', 'SIEMENS MAGNETOM ALTEA (1.5T)'),
            "dicom_port": srv_cfg.get('listen_port', 1005),
            "web_port": srv_cfg.get('web_port', 3000),
            "printer_status": p_st.get('status', 'UNKNOWN'),
            "printer_online": p_st.get('online', False),
            "stats": {
                "today_received": stats.get('today', {}).get('total_received', 0),
                "today_printed": stats.get('today', {}).get('total_printed', 0),
                "today_saved": stats.get('today', {}).get('total_saved', 0),
                "total_all": stats.get('all_time', {}).get('total_all', 0)
            }
        }
        self.github.update_admin_heartbeat(status_data)

    def _pull_loop(self):
        while self.running:
            try:
                self._check_and_pull_queue()
            except Exception as e:
                pass
            time.sleep(5)

    def _check_and_pull_queue(self):
        jobs = self.github.pull_pending_jobs()
        if not jobs:
            return

        print(f"\n[Admin Relay] GitHub navbatida {len(jobs)} ta shifrlangan plonka aniqlandi!")
        for job_item in jobs:
            fname = job_item['name']
            fpath = job_item['path']
            fsha = job_item['sha']
            enc_b64 = job_item['encrypted_b64']

            try:
                # 1. AES-256-GCM shifrni yechish
                payload = self.security.decrypt_payload(enc_b64)
                job_uid = payload.get('job_uid', fname)
                clinic = payload.get('source_clinic', 'Filial')
                print(f"[Admin Relay] Shifr muvaffaqiyatli yechildi: {job_uid} ({clinic})")

                # 2. Markaziy arxiv va bazaga saqlash
                saved_job = self.storage.save_remote_agent_job(payload)

                # 3. Darhol GitHubdan o'chirish (Bemor ma'lumotlari bulutda qolmasligi shart!)
                del_ok = self.github.delete_remote_file(fpath, fsha)
                if del_ok:
                    print(f"[Admin Relay] Plonka GitHubdan muvaffaqiyatli o'chirildi: {fname}")
                else:
                    print(f"[Admin Relay] Ogohlantirish: GitHubdan o'chirishda kechikish bo'ldi: {fname}")

            except Exception as e:
                print(f"[Admin Relay] XATO: {fname} faylini yechishda xatolik: {e}")
                # Agar shifr noto'g'ri bo'lsa yoki buzilgan bo'lsa, qotib qolmasligi uchun o'chirish
                self.github.delete_remote_file(fpath, fsha)
