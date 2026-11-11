"""
web_server.py - Veb boshqaruv paneli va REST API serveri (Port 3000)
1000+ bemorlar uchun kengaytirilgan boshqaruv, KarMed avtorizatsiyasi, 
bemor namuna raqami, telefon eslatmalari va harakatlar auditi (logging) bilan.
"""
import os
import sys
import json
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse
from datetime import datetime

from simulator import send_simulated_print_job

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def make_handler(storage_manager, scu_client, scp_server, config):
    base_dir = storage_manager.base_dir

    class WebHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _get_client_ip(self):
            return self.headers.get('X-Forwarded-For', self.client_address[0])

        def _get_current_user(self):
            auth_header = self.headers.get('Authorization', '')
            token = ''
            if auth_header.startswith('Bearer '):
                token = auth_header[7:].strip()
            if not token:
                token = self.headers.get('X-Auth-Token', '')
            if not token:
                # Query param
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                token = params.get('token', [''])[0]
            
            if token:
                return storage_manager.validate_session(token)
            return None

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            params = urllib.parse.parse_qs(parsed.query)

            if path == '/' or path == '/index.html':
                self._serve_html()
            elif path == '/api/status':
                self._api_status()
            elif path == '/api/jobs':
                limit = int(params.get('limit', [500])[0])
                delivery_filter = params.get('filter', [None])[0]
                search = params.get('search', [None])[0]
                search_sample = params.get('sample', [None])[0]
                search_id = params.get('id', [None])[0]
                search_name = params.get('name', [None])[0]
                self._api_jobs(
                    limit=limit,
                    delivery_filter=delivery_filter,
                    search=search,
                    search_sample=search_sample,
                    search_id=search_id,
                    search_name=search_name
                )
            elif path == '/api/auth/me':
                self._api_auth_me()
            elif path == '/api/audit-logs':
                limit = int(params.get('limit', [100])[0])
                self._api_audit_logs(limit)
            elif path == '/api/karmed/lookup':
                q = params.get('q', [''])[0]
                self._api_karmed_lookup(q)
            elif path.startswith('/storage/'):
                self._serve_static_storage(path)
            else:
                self.send_error(404, "Sahifa topilmadi")

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}

            if path == '/api/auth/login':
                self._api_auth_login(data)
            elif path == '/api/relay/push':
                self._api_relay_push(data)
            elif path == '/api/auth/logout':
                self._api_auth_logout()
            elif path == '/api/test/simulate':
                self._api_simulate(data)
            elif path.startswith('/api/jobs/') and path.endswith('/print'):
                parts = path.split('/')
                job_id = int(parts[3])
                self._api_reprint(job_id)
            elif path.startswith('/api/jobs/') and path.endswith('/open'):
                parts = path.split('/')
                job_id = int(parts[3])
                self._api_open_folder(job_id)
            elif path.startswith('/api/jobs/') and path.endswith('/deliver'):
                parts = path.split('/')
                job_id = int(parts[3])
                self._api_deliver(job_id, data)
            elif path.startswith('/api/jobs/') and path.endswith('/update-patient'):
                parts = path.split('/')
                job_id = int(parts[3])
                self._api_update_patient(job_id, data)
            elif path == '/api/config/toggle-autoprint':
                self._api_toggle_autoprint()
            else:
                self.send_error(404, "Endpoint topilmadi")

        def _serve_html(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))

        def _api_status(self):
            printer_status = scu_client.check_printer()
            stats = storage_manager.get_stats()
            resp = {
                'server': {
                    'ip': scp_server.listen_ip,
                    'port': scp_server.listen_port,
                    'ae_title': scp_server.ae_title.decode(),
                    'is_running': scp_server.is_running,
                    'auto_forward': scp_server.auto_forward
                },
                'printer': {
                    'ip': scu_client.ip,
                    'port': scu_client.port,
                    'called_ae': scu_client.called_ae.decode(),
                    **printer_status
                },
                'stats': stats
            }
            self._send_json(resp)

        def _api_jobs(self, limit=500, delivery_filter=None, search=None, search_sample=None, search_id=None, search_name=None):
            jobs = storage_manager.get_recent_jobs(
                limit=limit,
                delivery_filter=delivery_filter,
                search=search,
                search_sample=search_sample,
                search_id=search_id,
                search_name=search_name
            )
            self._send_json({'success': True, 'jobs': jobs})

        def _api_auth_login(self, data):
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
            ip = self._get_client_ip()

            auth_res = storage_manager.karmed.authenticate(username, password)
            if auth_res.get('success'):
                full_name = auth_res.get('full_name', username)
                token = storage_manager.create_session(username, full_name)
                
                # Audit log
                storage_manager.add_audit_log(
                    user_login=username,
                    user_name=full_name,
                    ip_address=ip,
                    action="LOGIN",
                    details="KarMed orqali muvaffaqiyatli tizimga kirdi"
                )
                
                self._send_json({
                    'success': True,
                    'token': token,
                    'user': {
                        'username': username,
                        'fullName': full_name
                    }
                })
            else:
                # Muvaffaqiyatsiz urinish
                storage_manager.add_audit_log(
                    user_login=username or "NOMALUM",
                    user_name="Noma'lum foydalanuvchi",
                    ip_address=ip,
                    action="LOGIN_FAILED",
                    details=f"Noto'g'ri login/parol kiritildi: {auth_res.get('error')}"
                )
                self._send_json({
                    'success': False,
                    'error': auth_res.get('error', "Login yoki parol noto'g'ri")
                }, status=401)

        def _api_auth_logout(self):
            user = self._get_current_user()
            auth_header = self.headers.get('Authorization', '')
            token = auth_header[7:].strip() if auth_header.startswith('Bearer ') else ''
            
            if user:
                storage_manager.add_audit_log(
                    user_login=user['username'],
                    user_name=user['full_name'],
                    ip_address=self._get_client_ip(),
                    action="LOGOUT",
                    details="Tizimdan chiqdi"
                )
            if token:
                storage_manager.delete_session(token)
            self._send_json({'success': True})

        def _api_auth_me(self):
            user = self._get_current_user()
            if user:
                self._send_json({
                    'authenticated': True,
                    'user': {
                        'username': user['username'],
                        'fullName': user['full_name']
                    }
                })
            else:
                self._send_json({'authenticated': False})

        def _api_audit_logs(self, limit=100):
            logs = storage_manager.get_audit_logs(limit)
            self._send_json({'success': True, 'logs': logs})

        def _api_karmed_lookup(self, query):
            data = storage_manager.karmed.lookup_patient(query)
            if data:
                self._send_json({'success': True, 'found': True, 'patient': data})
            else:
                self._send_json({'success': True, 'found': False, 'message': "KarMeddan bemor topilmadi"})

        def _api_deliver(self, job_id, data):
            user = self._get_current_user()
            user_name = user['full_name'] if user else "Navbatchi Operator"
            user_login = user['username'] if user else "OPERATOR"
            
            status = data.get('delivery_status', 'DELIVERED')
            job = storage_manager.update_delivery_status(job_id, status, delivered_by=user_name)
            
            action = "MARK_DELIVERED" if status == 'DELIVERED' else "MARK_PENDING"
            details = "Plonka bemorga topshirildi deb belgilandi" if status == 'DELIVERED' else "Plonka kutilmoqda (olib ketilmadi) deb belgilandi"
            
            storage_manager.add_audit_log(
                user_login=user_login,
                user_name=user_name,
                ip_address=self._get_client_ip(),
                action=action,
                job_id=job_id,
                patient_id=job.get('patient_id') if job else None,
                patient_name=job.get('patient_name') if job else None,
                details=details
            )
            self._send_json({'success': True, 'job': job})

        def _api_update_patient(self, job_id, data):
            user = self._get_current_user()
            user_name = user['full_name'] if user else "Navbatchi Operator"
            user_login = user['username'] if user else "OPERATOR"

            p_name = data.get('patient_name')
            p_id = data.get('patient_id')
            s_no = data.get('sample_no')
            phone = data.get('phone_number')

            job = storage_manager.update_patient_details(job_id, patient_name=p_name, patient_id=p_id, sample_no=s_no, phone_number=phone)
            
            storage_manager.add_audit_log(
                user_login=user_login,
                user_name=user_name,
                ip_address=self._get_client_ip(),
                action="UPDATE_PATIENT",
                job_id=job_id,
                patient_id=p_id,
                patient_name=p_name,
                details=f"Bemor ma'lumotlari yangilandi: Namuna #{s_no}, Tel: {phone}"
            )
            self._send_json({'success': True, 'job': job})

        def _api_simulate(self, data):
            try:
                p_id = data.get('patient_id', '30001')
                p_name = data.get('patient_name', 'SERGEY MAKEYEV')
                fmt = data.get('film_format', 'STANDARD\\2,3')

                def run_sim():
                    send_simulated_print_job(
                        server_ip="127.0.0.1",
                        server_port=scp_server.listen_port,
                        patient_id=p_id,
                        patient_name=p_name,
                        film_format=fmt
                    )
                threading.Thread(target=run_sim, daemon=True).start()
                
                user = self._get_current_user()
                storage_manager.add_audit_log(
                    user_login=user['username'] if user else "OPERATOR",
                    user_name=user['full_name'] if user else "Operator",
                    ip_address=self._get_client_ip(),
                    action="SIMULATE_TEST",
                    details=f"Test simulyatsiya plonkasi yuborildi: {p_name} ({p_id})"
                )
                self._send_json({'success': True, 'message': 'Simulyatsiya qilingan plonka yuborilmoqda...'})
            except Exception as e:
                self._send_json({'success': False, 'error': str(e)}, status=500)

        def _api_reprint(self, job_id):
            job = storage_manager.get_job_by_id(job_id)
            if not job:
                return self._send_json({'success': False, 'error': 'Job topilmadi'}, status=404)

            user = self._get_current_user()
            user_login = user['username'] if user else "OPERATOR"
            user_name = user['full_name'] if user else "Navbatchi Operator"
            ip = self._get_client_ip()

            storage_manager.add_audit_log(
                user_login=user_login,
                user_name=user_name,
                ip_address=ip,
                action="PRINT_REQUEST",
                job_id=job_id,
                patient_id=job.get('patient_id'),
                patient_name=job.get('patient_name'),
                details=f"Fuji DRYPIX Lite ga qo'lda chop etish buyrug'i berildi"
            )

            def do_print():
                try:
                    storage_manager.update_job_status(job_id, 'FORWARDING', 'PRINTING')
                    archive_dir = os.path.join(base_dir, job['archive_dir'])
                    images_dir = os.path.join(archive_dir, 'images')
                    
                    import pydicom
                    from pydicom.dataset import Dataset
                    from pydicom.sequence import Sequence
                    
                    fs_ds = Dataset()
                    fs_ds.NumberOfCopies = job.get('copies', 1)
                    
                    fb_ds = Dataset()
                    fb_ds.ImageDisplayFormat = job.get('film_format', 'STANDARD\\2,3')
                    fb_ds.FilmOrientation = job.get('orientation', 'PORTRAIT')
                    fb_ds.FilmSizeID = job.get('film_size', '14INX17IN')
                    
                    images_map = {}
                    if os.path.exists(images_dir):
                        files = sorted([f for f in os.listdir(images_dir) if f.endswith('.dcm')])
                        for idx, fname in enumerate(files):
                            pos = idx + 1
                            fpath = os.path.join(images_dir, fname)
                            dcm = pydicom.dcmread(fpath)
                            
                            box_ds = Dataset()
                            box_ds.ImageBoxPosition = pos
                            box_ds.BasicGrayscaleImageSequence = Sequence([dcm])
                            images_map[pos] = {'position': pos, 'dataset': box_ds}
                            
                    scu_client.forward_to_drypix(fs_ds, fb_ds, images_map)
                    storage_manager.record_print_attempt(job_id, success=True)
                    storage_manager.add_audit_log(
                        user_login=user_login,
                        user_name=user_name,
                        ip_address=ip,
                        action="PRINT_SUCCESS",
                        job_id=job_id,
                        patient_id=job.get('patient_id'),
                        patient_name=job.get('patient_name'),
                        details="Fuji DRYPIX 2000 da muvaffaqiyatli chop etildi"
                    )
                except Exception as err:
                    storage_manager.record_print_attempt(job_id, success=False, error_msg=str(err))
                    storage_manager.add_audit_log(
                        user_login=user_login,
                        user_name=user_name,
                        ip_address=ip,
                        action="PRINT_FAILED",
                        job_id=job_id,
                        patient_id=job.get('patient_id'),
                        patient_name=job.get('patient_name'),
                        details=f"Chop etishda xato: {err}"
                    )

            threading.Thread(target=do_print, daemon=True).start()
            self._send_json({'success': True, 'message': 'DryPix ga chop etish buyrug\'i yuborildi'})

        def _api_open_folder(self, job_id):
            job = storage_manager.get_job_by_id(job_id)
            if job and job.get('archive_dir'):
                folder_path = os.path.normpath(os.path.join(base_dir, job['archive_dir']))
                if os.path.exists(folder_path):
                    subprocess.Popen(f'explorer "{folder_path}"')
                    return self._send_json({'success': True})
            self._send_json({'success': False, 'error': 'Papka topilmadi'}, status=404)

        def _api_toggle_autoprint(self):
            scp_server.auto_forward = not scp_server.auto_forward
            if 'options' not in config:
                config['options'] = {}
            config['options']['auto_forward_to_printer'] = scp_server.auto_forward
            try:
                cfg_path = os.path.join(base_dir, 'config.json')
                with open(cfg_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[Web] Konfiguratsiyani saqlashda xato: {e}")
                
            user = self._get_current_user()
            storage_manager.add_audit_log(
                user_login=user['username'] if user else "OPERATOR",
                user_name=user['full_name'] if user else "Operator",
                ip_address=self._get_client_ip(),
                action="TOGGLE_AUTOPRINT",
                details=f"Avto-chop etish holati: {'YOQILDI' if scp_server.auto_forward else 'OCHIRILDI'}"
            )
            self._send_json({'success': True, 'auto_forward': scp_server.auto_forward})

        def _api_relay_push(self, data):
            payload_enc = data.get('payload', '')
            job_uid = data.get('job_uid', 'UNKNOWN')
            if not payload_enc:
                return self._send_json({'success': False, 'error': 'Payload topilmadi'}, status=400)
            
            try:
                from crypto_manager import E2EESecurity
                enc_key = config.get('security', {}).get('encryption_key', '')
                sec = E2EESecurity(enc_key)
                job_payload = sec.decrypt_payload(payload_enc)
                saved_job = storage_manager.save_remote_agent_job(job_payload)
                self._send_json({
                    'success': True,
                    'job_id': saved_job.get('id') if saved_job else None,
                    'message': 'Plonka qabul qilindi va keshga saqlandi'
                })
            except Exception as e:
                self._send_json({'success': False, 'error': f'Shifrni yechishda xatolik: {e}'}, status=400)

        def _serve_static_storage(self, path):
            rel_path = path.lstrip('/')
            full_path = os.path.normpath(os.path.join(base_dir, rel_path))
            
            if not full_path.startswith(os.path.abspath(base_dir)) or not os.path.exists(full_path):
                return self.send_error(404, "Fayl topilmadi")

            mime = 'image/png' if full_path.endswith('.png') else 'application/octet-stream'
            try:
                with open(full_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, str(e))

        def _send_json(self, obj, status=200):
            data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return WebHandler

def start_web_server(storage_manager, scu_client, scp_server, config, local_ip="127.0.0.1"):
    srv_cfg = config.get('server', {})
    port = int(srv_cfg.get('web_port', 3000))
    host = '0.0.0.0'
    
    handler = make_handler(storage_manager, scu_client, scp_server, config)
    httpd = ThreadedHTTPServer((host, port), handler)
    
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"[*] Web Boshqaruv Paneli: http://{local_ip}:{port} (yoki http://localhost:{port})")
    return httpd


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="uz" class="dark">
<head>
  <meta charset="UTF-8">
  <title>Siemens Magnetom Altea & Fuji DryPix 2000 — Spooler & Arxiv</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    body { background-color: #080d1a; color: #f1f5f9; font-family: system-ui, -apple-system, sans-serif; }
    .glass { background: rgba(15, 23, 42, 0.75); backdrop-filter: blur(12px); border: 1px solid rgba(51, 65, 85, 0.5); }
    .modal-backdrop { background: rgba(3, 7, 18, 0.85); backdrop-filter: blur(8px); }
  </style>
</head>
<body class="min-h-screen flex flex-col justify-between">

  <!-- Header -->
  <header class="glass sticky top-0 z-40 px-6 py-4 border-b border-slate-800">
    <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
      
      <!-- Logo & Title -->
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <i class="fa-solid fa-hospital text-white text-lg"></i>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-extrabold text-white text-base tracking-wide">Siemens Altea Spooler & Fuji DryPix 2000</h1>
            <span class="px-2 py-0.5 text-[10px] font-bold rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">Port 1005</span>
          </div>
          <p class="text-xs text-slate-400">Respublika Onkologiya Markazi • Radiodiagnostika Bo&#39;limi (KarMed integratsiyalangan)</p>
        </div>
      </div>

      <!-- Right Controls -->
      <div class="flex items-center flex-wrap gap-2.5">
        
        <!-- User Badge -->
        <div id="userBadge" class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs font-semibold text-slate-200">
          <i class="fa-solid fa-user-doctor text-cyan-400"></i>
          <span id="userNameText">Kirilmagan</span>
          <button onclick="handleLogout()" class="ml-1 text-slate-400 hover:text-rose-400" title="Chiqish">
            <i class="fa-solid fa-right-from-bracket"></i>
          </button>
        </div>

        <!-- Audit Log Button -->
        <button onclick="openAuditModal()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-semibold transition" title="Harakatlar jurnali (Audit)">
          <i class="fa-solid fa-clipboard-list text-indigo-400"></i>
          <span>Jurnal</span>
        </button>

        <!-- DryPix Status -->
        <div id="printerBadge" class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 text-xs font-medium">
          <span class="w-2 h-2 rounded-full bg-slate-400"></span>
          <span>DryPix Tekshirilmoqda...</span>
        </div>

        <!-- Auto-Print Toggle -->
        <button id="btnAutoPrint" onclick="toggleAutoPrint()" class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 text-xs font-semibold transition" title="Avtomatik pechatni yoqish / o'chirish">
          <i class="fa-solid fa-hand"></i>
          <span id="autoPrintText">Avto-Chop: O&#39;CHIRILGAN (Faqat saqlash)</span>
        </button>

        <!-- Test Film Button -->
        <button onclick="simulateTestFilm()" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow-md shadow-cyan-600/20 transition">
          <i class="fa-solid fa-plus"></i>
          <span>+ Test</span>
        </button>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto p-4 sm:p-6 flex-1 w-full space-y-6">

    <!-- KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="glass p-4 rounded-2xl cursor-pointer hover:border-cyan-500/50 transition" onclick="setFilter('ALL')">
        <div class="flex justify-between items-center text-slate-400 text-xs mb-1">
          <span>Jami Plonkalar</span>
          <i class="fa-solid fa-film text-cyan-400"></i>
        </div>
        <div id="statReceived" class="text-3xl font-extrabold text-white">0</div>
        <div class="text-[11px] text-slate-500 mt-1">Siemens Altea (1000+ kesh)</div>
      </div>

      <div class="glass p-4 rounded-2xl cursor-pointer hover:border-emerald-500/50 transition" onclick="setFilter('PRINTED')">
        <div class="flex justify-between items-center text-slate-400 text-xs mb-1">
          <span>DryPix da Chop Etildi</span>
          <i class="fa-solid fa-print text-emerald-400"></i>
        </div>
        <div id="statPrinted" class="text-3xl font-extrabold text-emerald-400">0</div>
        <div class="text-[11px] text-slate-500 mt-1">Fuji DryPix Lite</div>
      </div>

      <!-- Olib ketilmaganlar (Telefon qilish kerak) -->
      <div class="glass p-4 rounded-2xl cursor-pointer border border-amber-500/40 hover:border-amber-400 transition bg-amber-500/5" onclick="setFilter('PENDING_PICKUP')">
        <div class="flex justify-between items-center text-amber-300 text-xs mb-1 font-semibold">
          <span>Olib Ketilmaganlar</span>
          <i class="fa-solid fa-phone-volume text-amber-400 animate-pulse"></i>
        </div>
        <div id="statPendingPickup" class="text-3xl font-extrabold text-amber-400">0</div>
        <div class="text-[11px] text-amber-300/70 mt-1">⚠️ Telefon qilib eslatish kerak</div>
      </div>

      <!-- Topshirilganlar -->
      <div class="glass p-4 rounded-2xl cursor-pointer hover:border-indigo-500/50 transition" onclick="setFilter('DELIVERED')">
        <div class="flex justify-between items-center text-slate-400 text-xs mb-1">
          <span>Bemorga Topshirildi</span>
          <i class="fa-solid fa-circle-check text-indigo-400"></i>
        </div>
        <div id="statDelivered" class="text-3xl font-extrabold text-indigo-400">0</div>
        <div class="text-[11px] text-slate-500 mt-1">Qabul qilib olganlar</div>
      </div>
    </div>

    <!-- Filter Tabs & Kengaytirilgan Tezkor Qidiruv Paneli -->
    <div class="glass p-4 rounded-2xl shadow-xl border border-slate-800/80 flex flex-col gap-3">
      <!-- Yuqori qism: Holat tablari -->
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 pb-3 border-b border-slate-800/80">
        <div class="flex items-center gap-2 text-xs font-bold text-slate-300">
          <i class="fa-solid fa-magnifying-glass-chart text-cyan-400"></i>
          <span>Bemorlarni Qidirish & Holat Bo'yicha Saralash</span>
        </div>
        <div class="flex flex-wrap items-center gap-1.5 p-1 rounded-xl bg-slate-900/90 border border-slate-800 text-xs font-semibold">
          <button id="tabAll" onclick="setFilter('ALL')" class="px-3 py-1.5 rounded-lg bg-cyan-600 text-white transition">Barchasi</button>
          <button id="tabPending" onclick="setFilter('PENDING_PICKUP')" class="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white transition flex items-center gap-1">
            <i class="fa-solid fa-bell text-amber-400"></i> Olib ketilmaganlar
          </button>
          <button id="tabPrinted" onclick="setFilter('PRINTED')" class="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white transition">Chop etilganlar</button>
          <button id="tabDelivered" onclick="setFilter('DELIVERED')" class="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white transition">Topshirilganlar</button>
        </div>
      </div>

      <!-- Pastki qism: 3 ta alohida indekslangan qidiruv maydoni -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 items-end">
        <!-- 1. Namuna raqami bo'yicha alohida qidiruv -->
        <div>
          <label for="searchSample" class="block text-[11px] font-bold text-cyan-400 mb-1 flex items-center gap-1.5">
            <i class="fa-solid fa-hashtag text-cyan-400"></i> Namuna raqami (HastaSiraNo)
          </label>
          <div class="relative">
            <input type="text" id="searchSample" oninput="handleSearch()" placeholder="Masalan: 3414091" class="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition">
          </div>
        </div>

        <!-- 2. Bemor ID bo'yicha alohida qidiruv -->
        <div>
          <label for="searchId" class="block text-[11px] font-bold text-emerald-400 mb-1 flex items-center gap-1.5">
            <i class="fa-solid fa-id-card text-emerald-400"></i> Bemor ID (KimlikNo)
          </label>
          <div class="relative">
            <input type="text" id="searchId" oninput="handleSearch()" placeholder="Masalan: 52199" class="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400 transition">
          </div>
        </div>

        <!-- 3. Bemor F.I.SH bo'yicha alohida qidiruv -->
        <div>
          <label for="searchName" class="block text-[11px] font-bold text-blue-400 mb-1 flex items-center gap-1.5">
            <i class="fa-solid fa-user text-blue-400"></i> Bemor F.I.SH
          </label>
          <div class="relative">
            <input type="text" id="searchName" oninput="handleSearch()" placeholder="Masalan: Qodirov Navruz" class="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400 transition">
          </div>
        </div>

        <!-- 4. Tozalash tugmasi -->
        <div>
          <button onclick="clearSearch()" class="w-full py-2 px-3 rounded-xl bg-slate-800/90 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold flex items-center justify-center gap-2 transition border border-slate-700">
            <i class="fa-solid fa-rotate-left text-xs text-slate-400"></i> Filtrlarni tozalash
          </button>
        </div>
      </div>
    </div>

    <!-- Plonkalar Jadvali -->
    <div class="glass rounded-2xl overflow-hidden shadow-xl">
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse text-xs">
          <thead>
            <tr class="border-b border-slate-800 bg-slate-900/60 text-slate-400 uppercase font-semibold text-[11px] tracking-wider">
              <th class="p-3.5">Vaqt</th>
              <th class="p-3.5">Namuna # & Bemor</th>
              <th class="p-3.5">Telefon Raqami</th>
              <th class="p-3.5">Chop Etish Holati & Urinishlar</th>
              <th class="p-3.5">Plonka Topshirish</th>
              <th class="p-3.5 text-right">Amallar</th>
            </tr>
          </thead>
          <tbody id="jobsTableBody" class="divide-y divide-slate-800/60 font-sans">
            <tr><td colspan="6" class="p-8 text-center text-slate-500">Ma&#39;lumotlar yuklanmoqda...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

  </main>

  <!-- Footer -->
  <footer class="glass border-t border-slate-800/80 px-6 py-3 text-center text-[11px] text-slate-500">
    Respublika Ixtisoslashtirilgan Onkologiya va Radiologiya Ilmiy-Amaliy Tibbiyot Markazi • DICOM Spooler & Print Station
  </footer>

  <!-- ========================================================================= -->
  <!-- MODAL: LOGIN (KARMED ORQALI KIRISH) -->
  <!-- ========================================================================= -->
  <div id="loginModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 modal-backdrop hidden">
    <div class="glass rounded-2xl max-w-sm w-full p-6 space-y-5 border border-cyan-500/30 shadow-2xl">
      <div class="text-center space-y-1">
        <div class="w-12 h-12 rounded-2xl bg-cyan-600/20 text-cyan-400 border border-cyan-500/30 flex items-center justify-center mx-auto text-xl shadow-lg shadow-cyan-500/20">
          <i class="fa-solid fa-lock"></i>
        </div>
        <h3 class="text-base font-bold text-white pt-2">Tizimga Kirish</h3>
        <p class="text-xs text-slate-400">KarMed foydalanuvchi ma&#39;lumotlarini kiriting</p>
      </div>

      <div id="loginError" class="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs hidden text-center"></div>

      <form onsubmit="event.preventDefault(); submitLogin();" class="space-y-3">
        <div>
          <label class="block text-[11px] font-semibold text-slate-300 mb-1">KarMed Login</label>
          <div class="relative">
            <i class="fa-solid fa-user absolute left-3 top-2.5 text-slate-500 text-xs"></i>
            <input type="text" id="loginUsername" placeholder="Masalan: R5" value="R5" required class="w-full bg-slate-900 border border-slate-700 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 uppercase">
          </div>
        </div>

        <div>
          <label class="block text-[11px] font-semibold text-slate-300 mb-1">Parol</label>
          <div class="relative">
            <i class="fa-solid fa-key absolute left-3 top-2.5 text-slate-500 text-xs"></i>
            <input type="password" id="loginPassword" placeholder="Parol" value="17720" required class="w-full bg-slate-900 border border-slate-700 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500">
          </div>
        </div>

        <button type="submit" id="loginSubmitBtn" class="w-full py-2.5 bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-semibold text-xs rounded-xl shadow-lg shadow-cyan-600/30 transition flex items-center justify-center gap-2">
          <span>KarMed orqali Tasdiqlash</span>
          <i class="fa-solid fa-arrow-right"></i>
        </button>
      </form>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- MODAL: AUDIT LOGS (HARAKATLAR JURNALI) -->
  <!-- ========================================================================= -->
  <div id="auditModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 modal-backdrop hidden">
    <div class="glass rounded-2xl max-w-4xl w-full max-h-[85vh] flex flex-col border border-slate-700 shadow-2xl overflow-hidden">
      <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/60">
        <h3 class="font-bold text-white text-sm flex items-center gap-2">
          <i class="fa-solid fa-clipboard-list text-indigo-400"></i>
          <span>Xodimlar Harakatlari Jurnali (Audit Logs)</span>
        </h3>
        <button onclick="closeAuditModal()" class="text-slate-400 hover:text-white p-1 text-sm"><i class="fa-solid fa-xmark"></i></button>
      </div>
      <div class="p-4 overflow-y-auto flex-1">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="border-b border-slate-800 text-slate-400 uppercase text-[10px] pb-2">
              <th class="p-2">Vaqt</th>
              <th class="p-2">Xodim (Kim)</th>
              <th class="p-2">Amal (Nima qildi)</th>
              <th class="p-2">Bemor / Job #</th>
              <th class="p-2">Tafsilot</th>
            </tr>
          </thead>
          <tbody id="auditLogsBody" class="divide-y divide-slate-800/40">
            <tr><td colspan="5" class="p-4 text-center text-slate-500">Jurnal yuklanmoqda...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- MODAL: EDIT PATIENT & KARMED LOOKUP -->
  <!-- ========================================================================= -->
  <div id="editPatientModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 modal-backdrop hidden">
    <div class="glass rounded-2xl max-w-md w-full p-6 space-y-4 border border-cyan-500/40 shadow-2xl">
      <div class="flex justify-between items-center border-b border-slate-800 pb-3">
        <h3 class="text-sm font-bold text-white flex items-center gap-2">
          <i class="fa-solid fa-hospital-user text-cyan-400"></i>
          <span>Bemor va Namuna Ma&#39;lumotlari</span>
        </h3>
        <button onclick="closeEditModal()" class="text-slate-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button>
      </div>

      <form onsubmit="event.preventDefault(); savePatientDetails();" class="space-y-3">
        <input type="hidden" id="editJobId">
        
        <div>
          <label class="block text-[11px] font-semibold text-slate-300 mb-1">Namuna Raqami (Sira / Accession No)</label>
          <div class="flex gap-2">
            <input type="text" id="editSampleNo" placeholder="Masalan: 2695693" class="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono">
            <button type="button" onclick="karmedFetchForModal()" class="px-3 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition" title="KarMeddan qidirish">
              <i class="fa-solid fa-sync"></i> KarMed
            </button>
          </div>
        </div>

        <div>
          <label class="block text-[11px] font-semibold text-slate-300 mb-1">Bemor F.I.SH</label>
          <input type="text" id="editPatientName" placeholder="F.I.SH" required class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-bold">
        </div>

        <div>
          <label class="block text-[11px] font-semibold text-slate-300 mb-1">Bemor ID (KimlikNo / Protokol)</label>
          <input type="text" id="editPatientId" placeholder="ID raqam" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono">
        </div>

        <div>
          <label class="block text-[11px] font-semibold text-slate-300 mb-1">Telefon Raqami (Eslatma uchun)</label>
          <input type="text" id="editPhoneNumber" placeholder="+998 90 123 45 67" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono">
        </div>

        <div class="flex justify-end gap-2 pt-2 border-t border-slate-800">
          <button type="button" onclick="closeEditModal()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold">Bekor Qilish</button>
          <button type="submit" class="px-5 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-cyan-600/30">Saqlash</button>
        </div>
      </form>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- MODAL: PREVIEW (PLONKANI KO'RISH) -->
  <!-- ========================================================================= -->
  <div id="previewModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 modal-backdrop hidden">
    <div class="glass rounded-2xl max-w-5xl w-full max-h-[92vh] flex flex-col border border-slate-700 shadow-2xl overflow-hidden">
      <div class="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/80">
        <div>
          <h3 id="modalTitle" class="font-bold text-white text-sm">Bemor Plonkasi</h3>
          <p id="modalSubtitle" class="text-xs text-slate-400">Siemens Altea</p>
        </div>
        <button onclick="closePreviewModal()" class="text-slate-400 hover:text-white p-1 text-sm"><i class="fa-solid fa-xmark"></i></button>
      </div>
      <div class="p-4 overflow-auto flex-1 flex justify-center items-center bg-black/60 min-h-[300px]">
        <img id="modalImg" src="" alt="Plonka" class="max-h-[72vh] object-contain rounded border border-slate-800 shadow-2xl">
      </div>
      <div class="p-4 border-t border-slate-800 bg-slate-900/90 flex justify-between items-center">
        <button id="modalOpenFolderBtn" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg flex items-center gap-2">
          <i class="fa-solid fa-folder-open"></i> Papkani Ochish
        </button>
        <button id="modalPrintBtn" class="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg flex items-center gap-2 shadow-lg shadow-emerald-600/30">
          <i class="fa-solid fa-print"></i> DryPix 2000 ga Chop Etish
        </button>
      </div>
    </div>
  </div>

  <!-- ========================================================================= -->
  <!-- JAVASCRIPT KODI -->
  <!-- ========================================================================= -->
  <script>
    let allJobs = [];
    let currentFilter = 'ALL';
    let currentUser = null;

    // Sessiya va avtorizatsiya boshqaruvi
    function getAuthToken() {
      return localStorage.getItem('karmed_token') || '';
    }

    function checkAuth() {
      const token = getAuthToken();
      if (!token) {
        showLoginModal();
        return;
      }
      fetch('/api/auth/me', { headers: { 'Authorization': 'Bearer ' + token } })
        .then(r => r.json())
        .then(res => {
          if (res.authenticated) {
            currentUser = res.user;
            document.getElementById('userNameText').textContent = res.user.fullName || res.user.username;
            closeLoginModal();
            loadData();
          } else {
            showLoginModal();
          }
        })
        .catch(() => showLoginModal());
    }

    function showLoginModal() {
      document.getElementById('loginModal').classList.remove('hidden');
    }

    function closeLoginModal() {
      document.getElementById('loginModal').classList.add('hidden');
    }

    async function submitLogin() {
      const u = document.getElementById('loginUsername').value.trim();
      const p = document.getElementById('loginPassword').value.trim();
      const errBox = document.getElementById('loginError');
      const btn = document.getElementById('loginSubmitBtn');

      errBox.classList.add('hidden');
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Tekshirilmoqda...';

      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: u, password: p })
        }).then(r => r.json());

        if (res.success) {
          localStorage.setItem('karmed_token', res.token);
          currentUser = res.user;
          document.getElementById('userNameText').textContent = res.user.fullName || res.user.username;
          closeLoginModal();
          loadData();
        } else {
          errBox.textContent = res.error || "Login yoki parol xato";
          errBox.classList.remove('hidden');
        }
      } catch (e) {
        errBox.textContent = "Server bilan aloqa xatosi: " + e.message;
        errBox.classList.remove('hidden');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>KarMed orqali Tasdiqlash</span> <i class="fa-solid fa-arrow-right"></i>';
      }
    }

    async function handleLogout() {
      if (!confirm("Tizimdan chiqishni xohlaysizmi?")) return;
      const token = getAuthToken();
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + token }
        });
      } catch (e) {}
      localStorage.removeItem('karmed_token');
      currentUser = null;
      document.getElementById('userNameText').textContent = 'Kirilmagan';
      showLoginModal();
    }

    // =========================================================================
    // MA'LUMOTLARNI YUKLASH VA JADVALNI RENDER QILISH
    // =========================================================================
    function setFilter(filt) {
      currentFilter = filt;
      ['tabAll', 'tabPending', 'tabPrinted', 'tabDelivered'].forEach(t => {
        const el = document.getElementById(t);
        if (el) el.className = 'px-3 py-1.5 rounded-lg text-slate-400 hover:text-white transition';
      });

      if (filt === 'ALL') document.getElementById('tabAll').className = 'px-3 py-1.5 rounded-lg bg-cyan-600 text-white transition';
      if (filt === 'PENDING_PICKUP') document.getElementById('tabPending').className = 'px-3 py-1.5 rounded-lg bg-amber-500 text-slate-900 font-bold transition flex items-center gap-1';
      if (filt === 'PRINTED') document.getElementById('tabPrinted').className = 'px-3 py-1.5 rounded-lg bg-emerald-600 text-white transition';
      if (filt === 'DELIVERED') document.getElementById('tabDelivered').className = 'px-3 py-1.5 rounded-lg bg-indigo-600 text-white transition';

      loadData();
    }

    let searchDebounceTimer = null;
    function handleSearch() {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        loadData();
      }, 150);
    }

    function clearSearch() {
      const s1 = document.getElementById('searchSample');
      const s2 = document.getElementById('searchId');
      const s3 = document.getElementById('searchName');
      if (s1) s1.value = '';
      if (s2) s2.value = '';
      if (s3) s3.value = '';
      loadData();
    }

    async function loadData() {
      const sSample = document.getElementById('searchSample') ? document.getElementById('searchSample').value.trim() : '';
      const sId = document.getElementById('searchId') ? document.getElementById('searchId').value.trim() : '';
      const sName = document.getElementById('searchName') ? document.getElementById('searchName').value.trim() : '';
      const token = getAuthToken();
      
      let url = '/api/jobs?limit=500';
      if (currentFilter !== 'ALL') url += '&filter=' + encodeURIComponent(currentFilter);
      if (sSample) url += '&sample=' + encodeURIComponent(sSample);
      if (sId) url += '&id=' + encodeURIComponent(sId);
      if (sName) url += '&name=' + encodeURIComponent(sName);

      fetch(url, { headers: { 'Authorization': 'Bearer ' + token } })
        .then(r => r.json())
        .then(resJobs => {
          allJobs = resJobs.jobs || [];
          renderTable(allJobs);
        })
        .catch(e => console.error("Jobs error:", e));

      fetch('/api/status', { headers: { 'Authorization': 'Bearer ' + token } })
        .then(r => r.json())
        .then(resStatus => {
          updateBadges(resStatus);
          const st = resStatus.stats.today;
          document.getElementById('statReceived').textContent = st.total_received || 0;
          document.getElementById('statPrinted').textContent = st.total_printed || 0;
          document.getElementById('statPendingPickup').textContent = st.pending_pickup || 0;
          document.getElementById('statDelivered').textContent = st.delivered || 0;
        })
        .catch(e => console.error("Status error:", e));
    }

    function updateBadges(data) {
      const p = data.printer;
      const pBadge = document.getElementById('printerBadge');
      if (p.online) {
        pBadge.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium';
        pBadge.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400"></span><span>DryPix 2000: TAYYOR (' + (p.status || 'NORMAL') + ')</span>';
      } else {
        pBadge.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-medium';
        pBadge.innerHTML = '<span class="w-2 h-2 rounded-full bg-rose-400"></span><span>DryPix: ALOQA YO&#39;Q</span>';
      }

      const autoPrint = data.server.auto_forward;
      const btn = document.getElementById('btnAutoPrint');
      const txt = document.getElementById('autoPrintText');
      if (autoPrint) {
        btn.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-600/20 border border-emerald-500/30 text-emerald-300 text-xs font-semibold transition';
        txt.innerHTML = '<i class="fa-solid fa-bolt text-emerald-400 mr-1"></i> Avto-Chop: YOQILGAN';
      } else {
        btn.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs font-semibold transition';
        txt.innerHTML = '<i class="fa-solid fa-hand text-amber-400 mr-1"></i> Avto-Chop: O&#39;CHIRILGAN (Faqat saqlash)';
      }
    }

    function renderTable(jobs) {
      const tbody = document.getElementById('jobsTableBody');
      if (jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="p-8 text-center text-slate-500">Hech qanday plonka topilmadi.</td></tr>';
        return;
      }

      tbody.innerHTML = jobs.map(j => {
        // Chop etish statusi
        let printBadge = '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-500/10 text-sky-300 border border-sky-500/20"><i class="fa-solid fa-hard-drive mr-1"></i> Saqlangan</span>';
        if (j.status === 'PRINTED') {
          printBadge = '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"><i class="fa-solid fa-check mr-1"></i> Chop Etildi</span>';
        } else if (j.status === 'FORWARDING') {
          printBadge = '<span class="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse"><i class="fa-solid fa-spinner fa-spin mr-1"></i> Yuborilmoqda...</span>';
        } else if (j.status === 'FORWARD_FAILED') {
          printBadge = '<button onclick="showError(&#39;' + encodeURIComponent(j.error_message || '') + '&#39;)" class="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 cursor-pointer inline-flex items-center gap-1"><i class="fa-solid fa-xmark"></i> Xatolik</button>';
        }

        // Urinishlar statistikasi
        const pCount = j.print_count || 0;
        const pSuccess = j.print_success_count || 0;
        const pFail = j.print_fail_count || 0;
        let statsText = '';
        if (pCount > 0) {
          statsText = '<div class="text-[10px] text-slate-400 mt-1 font-mono">Urinish: <span class="text-white">' + pCount + '</span> (✓' + pSuccess + ' / ✗' + pFail + ')</div>';
        }

        // Topshirish statusi
        let delivBadge = '';
        if (j.delivery_status === 'DELIVERED') {
          const dTime = j.delivered_at ? j.delivered_at.replace('T', ' ').substring(11, 16) : '';
          const dBy = j.delivered_by ? ' (' + j.delivered_by.split(' ')[0] + ')' : '';
          delivBadge = '<span class="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 flex items-center gap-1.5 w-max"><i class="fa-solid fa-circle-check"></i> Topshirildi ' + dTime + dBy + '</span>';
        } else {
          if (j.status === 'PRINTED') {
            delivBadge = '<span class="px-2.5 py-1 rounded-md text-[11px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1.5 w-max animate-pulse"><i class="fa-solid fa-phone"></i> Olib ketilmadi (Eslatilsin)</span>';
          } else {
            delivBadge = '<span class="px-2 py-0.5 rounded text-[11px] text-slate-400 bg-slate-800">Chop etilmagan</span>';
          }
        }

        // Telefon raqami
        let phoneHtml = '<span class="text-slate-500 italic">Kiritilmagan</span>';
        if (j.phone_number) {
          phoneHtml = '<a href="tel:' + j.phone_number.split(' ').join('') + '" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 font-mono font-semibold flex items-center gap-1.5 w-max transition" title="Qo&#39;ng&#39;iroq qilish"><i class="fa-solid fa-phone text-emerald-400"></i> ' + j.phone_number + '</a>';
        }

        const timeStr = j.created_at ? j.created_at.replace('T', ' ').substring(0, 19) : '-';
        const sampleNo = j.sample_no || j.patient_id || '-';

        return `
          <tr class="hover:bg-slate-800/40 transition">
            <td class="p-3.5 font-mono text-slate-400 whitespace-nowrap">${timeStr}</td>
            <td class="p-3.5">
              <div class="font-bold text-white text-[13px]">${j.patient_name || 'NOMALUM BEMOR'}</div>
              <div class="flex items-center gap-2 mt-0.5 text-slate-400">
                <span>Namuna #: <strong class="text-cyan-400 font-mono">${sampleNo}</strong></span>
                <span>•</span>
                <span>ID: <span class="font-mono">${j.patient_id || '-'}</span></span>
                <button onclick="openEditModal(${j.id})" class="text-slate-400 hover:text-cyan-300 ml-1" title="KarMeddan yangilash / Tahrirlash"><i class="fa-solid fa-pen-to-square"></i></button>
              </div>
            </td>
            <td class="p-3.5">${phoneHtml}</td>
            <td class="p-3.5">
              <div>${printBadge}</div>
              ${statsText}
            </td>
            <td class="p-3.5">${delivBadge}</td>
            <td class="p-3.5 text-right space-x-1.5 whitespace-nowrap">
              <button onclick="openPreview('${j.preview_image}', '${j.patient_name}', '${j.patient_id}', ${j.id})" class="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-400 font-semibold rounded-lg transition" title="Plonkani ko'rish">
                <i class="fa-solid fa-eye"></i> Ko&#39;rish
              </button>
              <button onclick="reprintJob(${j.id})" class="px-2.5 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/30 text-emerald-300 font-semibold rounded-lg transition" title="Fuji DryPix ga chop etish">
                <i class="fa-solid fa-print"></i> Chop Etish
              </button>
              ${j.delivery_status === 'DELIVERED' 
                ? `<button onclick="toggleDelivery(${j.id}, 'PENDING_PICKUP')" class="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg transition" title="Qaytarish"><i class="fa-solid fa-rotate-left"></i></button>`
                : `<button onclick="toggleDelivery(${j.id}, 'DELIVERED')" class="px-2.5 py-1.5 bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/30 text-indigo-300 font-semibold rounded-lg transition" title="Topshirildi deb belgilash"><i class="fa-solid fa-check"></i> Berildi</button>`
              }
              <button onclick="openFolder(${j.id})" class="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg transition" title="Papkani ochish">
                <i class="fa-solid fa-folder"></i>
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    // =========================================================================
    // AMALLAR: CHOP ETISH, TOPSHIRISH, TAHRIRLASH
    // =========================================================================
    async function reprintJob(id) {
      const token = getAuthToken();
      try {
        const res = await fetch('/api/jobs/' + id + '/print', { 
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + token }
        }).then(r => r.json());
        if (res.success) {
          alert("Fuji DryPix 2000 ga chop etish buyrug'i uzatildi!");
          loadData();
        } else {
          alert("Xatolik: " + res.error);
        }
      } catch (e) {
        alert("Aloqa xatosi: " + e.message);
      }
    }

    async function toggleDelivery(id, newStatus) {
      const token = getAuthToken();
      try {
        await fetch('/api/jobs/' + id + '/deliver', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + token 
          },
          body: JSON.stringify({ delivery_status: newStatus })
        });
        loadData();
      } catch (e) {
        alert("Topshirish holatini o'zgartirib bo'lmadi");
      }
    }

    function openEditModal(jobId) {
      const job = allJobs.find(j => j.id === jobId);
      if (!job) return;
      document.getElementById('editJobId').value = job.id;
      document.getElementById('editSampleNo').value = job.sample_no || job.patient_id || '';
      document.getElementById('editPatientName').value = job.patient_name || '';
      document.getElementById('editPatientId').value = job.patient_id || '';
      document.getElementById('editPhoneNumber').value = job.phone_number || '';
      document.getElementById('editPatientModal').classList.remove('hidden');
    }

    function closeEditModal() {
      document.getElementById('editPatientModal').classList.add('hidden');
    }

    async function karmedFetchForModal() {
      const q = document.getElementById('editSampleNo').value.trim() || document.getElementById('editPatientId').value.trim();
      if (!q) {
        alert("Namuna raqami yoki ID kiritilishi shart");
        return;
      }
      const token = getAuthToken();
      try {
        const res = await fetch('/api/karmed/lookup?q=' + encodeURIComponent(q), {
          headers: { 'Authorization': 'Bearer ' + token }
        }).then(r => r.json());
        
        if (res.success && res.found) {
          const p = res.patient;
          if (p.patient_name) document.getElementById('editPatientName').value = p.patient_name;
          if (p.patient_id) document.getElementById('editPatientId').value = p.patient_id;
          if (p.sample_no) document.getElementById('editSampleNo').value = p.sample_no;
          if (p.phone_number) document.getElementById('editPhoneNumber').value = p.phone_number;
          alert("KarMeddan bemor ma'lumotlari topildi: " + p.patient_name);
        } else {
          alert("KarMedda ushbu raqam bo'yicha bemor topilmadi");
        }
      } catch (e) {
        alert("KarMeddan qidirishda xatolik: " + e.message);
      }
    }

    async function savePatientDetails() {
      const id = document.getElementById('editJobId').value;
      const sNo = document.getElementById('editSampleNo').value.trim();
      const pName = document.getElementById('editPatientName').value.trim();
      const pId = document.getElementById('editPatientId').value.trim();
      const phone = document.getElementById('editPhoneNumber').value.trim();
      const token = getAuthToken();

      try {
        await fetch('/api/jobs/' + id + '/update-patient', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + token
          },
          body: JSON.stringify({
            sample_no: sNo,
            patient_name: pName,
            patient_id: pId,
            phone_number: phone
          })
        });
        closeEditModal();
        loadData();
      } catch (e) {
        alert("Saqlashda xato: " + e.message);
      }
    }

    // =========================================================================
    // AUDIT LOGS MODAL
    // =========================================================================
    async function openAuditModal() {
      const token = getAuthToken();
      document.getElementById('auditModal').classList.remove('hidden');
      try {
        const res = await fetch('/api/audit-logs?limit=100', {
          headers: { 'Authorization': 'Bearer ' + token }
        }).then(r => r.json());
        
        const tbody = document.getElementById('auditLogsBody');
        if (!res.logs || res.logs.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-slate-500">Jurnal bo&#39;sh</td></tr>';
          return;
        }

        tbody.innerHTML = res.logs.map(l => {
          const t = l.created_at ? l.created_at.replace('T', ' ').substring(0, 19) : '-';
          return `
            <tr class="hover:bg-slate-800/30">
              <td class="p-2 font-mono text-slate-400 whitespace-nowrap">${t}</td>
              <td class="p-2 font-semibold text-white whitespace-nowrap">${l.user_name || l.user_login || '-'}</td>
              <td class="p-2"><span class="px-2 py-0.5 rounded bg-slate-800 text-cyan-300 font-mono text-[10px]">${l.action}</span></td>
              <td class="p-2 font-mono text-slate-300">${l.patient_name || (l.job_id ? 'Job #' + l.job_id : '-')}</td>
              <td class="p-2 text-slate-400">${l.details || '-'}</td>
            </tr>
          `;
        }).join('');
      } catch (e) {
        document.getElementById('auditLogsBody').innerHTML = '<tr><td colspan="5" class="p-4 text-center text-rose-400">Jurnalni yuklab bo&#39;lmadi</td></tr>';
      }
    }

    function closeAuditModal() {
      document.getElementById('auditModal').classList.add('hidden');
    }

    // =========================================================================
    // PREVIEW VA BOSHQALAR
    // =========================================================================
    function openPreview(imgUrl, name, id, jobId) {
      if (!imgUrl) return;
      document.getElementById('modalTitle').textContent = 'Bemor: ' + name;
      document.getElementById('modalSubtitle').textContent = 'ID: ' + id + ' | Siemens Altea MRT Plonkasi';
      document.getElementById('modalImg').src = '/' + imgUrl;
      document.getElementById('modalPrintBtn').onclick = () => reprintJob(jobId);
      document.getElementById('modalOpenFolderBtn').onclick = () => openFolder(jobId);
      document.getElementById('previewModal').classList.remove('hidden');
    }

    function closePreviewModal() {
      document.getElementById('previewModal').classList.add('hidden');
    }

    function showError(encMsg) {
      const msg = decodeURIComponent(encMsg);
      alert("Xatolik sababi: " + (msg || "Noma'lum xatolik"));
    }

    async function openFolder(id) {
      const token = getAuthToken();
      try {
        await fetch('/api/jobs/' + id + '/open', {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + token }
        });
      } catch (e) {
        alert("Papkani ochib bo'lmadi");
      }
    }

    async function toggleAutoPrint() {
      const token = getAuthToken();
      try {
        await fetch('/api/config/toggle-autoprint', {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + token }
        });
        loadData();
      } catch (e) {
        console.error(e);
      }
    }

    async function simulateTestFilm() {
      const token = getAuthToken();
      try {
        await fetch('/api/test/simulate', {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + token }
        });
        setTimeout(loadData, 2000);
      } catch (e) {
        alert("Simulyatsiya xatosi: " + e.message);
      }
    }

    // Ishga tushirish
    checkAuth();
    setInterval(loadData, 3500);
  </script>
</body>
</html>
"""
