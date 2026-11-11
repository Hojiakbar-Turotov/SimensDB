"""
dicom_scp.py - Siemens Magnetom Altea apparatidan DICOM Print so'rovlarini qabul qiluvchi SCP server
Tinglaydi: 0.0.0.0:1005 (10.34.14.33:1005)
"""
import sys
import threading
import datetime

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from pynetdicom import AE, evt
from pynetdicom.sop_class import (
    BasicGrayscalePrintManagementMeta,
    BasicColorPrintManagementMeta,
    BasicFilmSession,
    BasicFilmBox,
    BasicGrayscaleImageBox,
    BasicColorImageBox,
    Printer,
    PresentationLUT,
    PrintJob,
    BasicAnnotationBox,
    Verification
)
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid

class DicomPrintSCP:
    def __init__(self, config, storage_manager, scu_client):
        self.config = config
        self.storage = storage_manager
        self.scu = scu_client
        
        srv_cfg = config.get('server', {})
        self.listen_ip = srv_cfg.get('listen_ip', '0.0.0.0')
        self.listen_port = int(srv_cfg.get('listen_port', 1005))
        self.ae_title = srv_cfg.get('ae_title', 'DRYPIX2').encode('ascii')
        
        self.auto_forward = config.get('options', {}).get('auto_forward_to_printer', False)
        
        self.ae = None
        self.server = None
        self.is_running = False
        
        self.sessions = {}
        self._lock = threading.Lock()

    def start(self):
        """DICOM Print SCP serverni ishga tushirish (Port 1005)"""
        self.ae = AE(ae_title=self.ae_title)
        
        supported_classes = [
            BasicGrayscalePrintManagementMeta,
            BasicColorPrintManagementMeta,
            BasicFilmSession,
            BasicFilmBox,
            BasicGrayscaleImageBox,
            BasicColorImageBox,
            Printer,
            PresentationLUT,
            PrintJob,
            BasicAnnotationBox,
            Verification
        ]
        
        for sc in supported_classes:
            self.ae.add_supported_context(sc)
            
        self.ae.require_calling_aet = b''
        self.ae.require_called_aet = b''
        
        handlers = [
            (evt.EVT_C_ECHO, self._handle_echo),
            (evt.EVT_N_GET, self._handle_get),
            (evt.EVT_N_CREATE, self._handle_create),
            (evt.EVT_N_SET, self._handle_set),
            (evt.EVT_N_ACTION, self._handle_action),
            (evt.EVT_N_DELETE, self._handle_delete),
            (evt.EVT_CONN_CLOSE, self._handle_conn_close),
        ]
        
        print("\n" + "=" * 60)
        print(">> DICOM PRINT SCP SERVER ISHGA TUSHMOQDA...")
        print(f"[*] Tinglash manzili: {self.listen_ip}:{self.listen_port}")
        print(f"[*] Called AE Title: {self.ae_title.decode()} (Barcha AE Title-lar qabul qilinadi)")
        print(f"[*] Fuji DryPix Forwarder: {self.scu.ip}:{self.scu.port} (Auto: {self.auto_forward})")
        print("=" * 60 + "\n")
        
        self.server = self.ae.start_server(
            (self.listen_ip, self.listen_port),
            block=False,
            evt_handlers=handlers
        )
        self.is_running = True
        return True

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.is_running = False
            print("[PrintSCP] Server to'xtatildi.")

    def _get_assoc_state(self, assoc):
        assoc_id = id(assoc)
        with self._lock:
            if assoc_id not in self.sessions:
                calling = 'SIEMENS'
                if hasattr(assoc, 'requestor') and hasattr(assoc.requestor, 'ae_title'):
                    calling = assoc.requestor.ae_title.strip()
                self.sessions[assoc_id] = {
                    'calling_aet': calling,
                    'film_sessions': {},
                    'film_boxes': {},
                    'active_fb_uid': None,
                    'active_fs_uid': None
                }
            return self.sessions[assoc_id]

    def _handle_echo(self, event):
        calling = 'Mijoz'
        if hasattr(event.assoc, 'requestor') and hasattr(event.assoc.requestor, 'ae_title'):
            calling = event.assoc.requestor.ae_title.strip()
        print(f"[PrintSCP] C-ECHO (DICOM Ping) qabul qilindi. Mijoz: {calling} -> Status: 0x0000 (Success)")
        return 0x0000

    def _handle_get(self, event):
        print("[PrintSCP] N-GET (Printer Status) so'rovi qabul qilindi...")
        ds = Dataset()
        ds.PrinterStatus = 'NORMAL'
        ds.PrinterStatusInfo = 'NORMAL'
        ds.PrinterName = 'DRYPIX2'
        ds.Manufacturer = 'FUJIFILM Corporation'
        ds.ManufacturerModelName = 'DRYPIX Lite'
        return 0x0000, ds

    def _handle_create(self, event):
        state = self._get_assoc_state(event.assoc)
        sop_class = str(event.request.AffectedSOPClassUID)
        assigned_uid = event.request.AffectedSOPInstanceUID or generate_uid()
        
        # pynetdicom da N-CREATE dataseti event.attribute_list ichida bo'ladi
        req_dataset = getattr(event, 'attribute_list', None) or Dataset()
        
        rsp_ds = Dataset()
        rsp_ds.AffectedSOPInstanceUID = assigned_uid
        
        if sop_class == str(BasicFilmSession):
            state['film_sessions'][assigned_uid] = req_dataset
            state['active_fs_uid'] = assigned_uid
            copies = getattr(req_dataset, 'NumberOfCopies', 1) or 1
            print(f"[PrintSCP] [+] N-CREATE: Film Session yaratildi (UID: {assigned_uid}, Nusxa: {copies})")
            return 0x0000, rsp_ds

        elif sop_class == str(BasicFilmBox):
            state['active_fb_uid'] = assigned_uid
            fb_ds = req_dataset
            
            fmt = getattr(fb_ds, 'ImageDisplayFormat', 'STANDARD\\2,3')
            cols, rows = self.storage._parse_display_format(fmt)
            total_boxes = cols * rows
            
            image_box_seq = Sequence()
            boxes_map = {}
            for pos in range(1, total_boxes + 1):
                box_uid = generate_uid()
                item = Dataset()
                item.ReferencedSOPClassUID = BasicGrayscaleImageBox
                item.ReferencedSOPInstanceUID = box_uid
                image_box_seq.append(item)
                
                boxes_map[box_uid] = {
                    'position': pos,
                    'dataset': None
                }
                
            rsp_ds.ReferencedImageBoxSequence = image_box_seq
            state['film_boxes'][assigned_uid] = {
                'dataset': fb_ds,
                'cols': cols,
                'rows': rows,
                'boxes': boxes_map
            }
            
            size_id = getattr(fb_ds, 'FilmSizeID', '14INX17IN')
            orient = getattr(fb_ds, 'FilmOrientation', 'PORTRAIT')
            print(f"[PrintSCP] [+] N-CREATE: Film Box yaratildi (Format: {fmt} -> {cols}x{rows} = {total_boxes} kadr, O'lcham: {size_id}, Yo'nalish: {orient})")
            return 0x0000, rsp_ds
            
        return 0x0000, rsp_ds

    def _handle_set(self, event):
        state = self._get_assoc_state(event.assoc)
        target_uid = str(event.request.RequestedSOPInstanceUID)
        
        # pynetdicom da N-SET dataseti event.modification_list ichida bo'ladi
        mod_list = getattr(event, 'modification_list', None) or getattr(event, 'attribute_list', None) or Dataset()
        
        found = False
        for fb_uid, fb_info in state['film_boxes'].items():
            if target_uid in fb_info['boxes']:
                box_slot = fb_info['boxes'][target_uid]
                box_slot['dataset'] = mod_list
                pos = getattr(mod_list, 'ImageBoxPosition', box_slot['position']) or box_slot['position']
                
                seq = getattr(mod_list, 'BasicGrayscaleImageSequence', None)
                img_dims = ""
                if seq and len(seq) > 0:
                    r = getattr(seq[0], 'Rows', 0)
                    c = getattr(seq[0], 'Columns', 0)
                    img_dims = f"({c}x{r} px)"
                    
                print(f"[PrintSCP] [KADR] N-SET: Kadr #{pos} qabul qilindi {img_dims}")
                found = True
                break
                
        if not found:
            print(f"[PrintSCP] Ogohlantirish: N-SET noma'lum Image Box UID uchun keldi: {target_uid}")
            
        return 0x0000, Dataset()

    def _handle_action(self, event):
        state = self._get_assoc_state(event.assoc)
        target_uid = str(event.request.RequestedSOPInstanceUID)
        action_type = event.request.ActionTypeID
        
        print(f"\n[PrintSCP] >>> N-ACTION (CHOP ETISH BUYRUG'I) QABUL QILINDI! (ActionType: {action_type})")
        
        fb_info = state['film_boxes'].get(target_uid)
        if not fb_info and state['active_fb_uid']:
            fb_info = state['film_boxes'].get(state['active_fb_uid'])
            
        fs_ds = state['film_sessions'].get(state['active_fs_uid'], Dataset())
        fb_ds = fb_info.get('dataset', Dataset()) if fb_info else Dataset()
        images_map = fb_info.get('boxes', {}) if fb_info else {}
        
        job_uid = f"MR_{int(datetime.datetime.now().timestamp())}_{target_uid[-8:]}"
        calling_aet = state.get('calling_aet', 'SIEMENS')
        
        try:
            print(f"[PrintSCP] Plonka to'liq diskka va arxivga saqlanmoqda...")
            job = self.storage.save_print_job(
                job_uid=job_uid,
                film_session_ds=fs_ds,
                film_box_ds=fb_ds,
                images_map=images_map,
                calling_aet=calling_aet
            )
            print(f"[PrintSCP] [OK] Plonka saqlandi! Job #{job['id']} (Bemor: {job['patient_name']})")
            print(f"[*] Arxiv: {job['archive_dir']}")
            print(f"[*] Preview: {job['preview_image']}")
            
            if self.auto_forward:
                threading.Thread(
                    target=self._forward_job_worker,
                    args=(job['id'], fs_ds, fb_ds, images_map),
                    daemon=True
                ).start()
            else:
                print(f"[PrintSCP] Avto-chop etish o'chirilgan. Plonka keshda saqlandi.")
                
        except Exception as e:
            print(f"[PrintSCP] [XATO] Saqlashda xatolik yuz berdi: {e}")
            
        return 0x0000, Dataset()

    def _forward_job_worker(self, job_id, fs_ds, fb_ds, images_map):
        try:
            self.storage.update_job_status(job_id, 'FORWARDING', 'PRINTING')
            print(f"[PrintSCP] [>] Job #{job_id} Fujifilm DryPix 2000 ({self.scu.ip}:{self.scu.port}) ga yuborilmoqda...")
            self.scu.forward_to_drypix(fs_ds, fb_ds, images_map)
            job = self.storage.record_print_attempt(job_id, success=True)
            self.storage.add_audit_log(
                user_login="AUTO_SPOOLER",
                user_name="Avtomatik Spooler",
                ip_address="127.0.0.1",
                action="PRINT_SUCCESS",
                job_id=job_id,
                patient_id=job.get('patient_id') if job else None,
                patient_name=job.get('patient_name') if job else None,
                details="Fuji DRYPIX 2000 ga muvaffaqiyatli chop etildi"
            )
            print(f"[PrintSCP] [SUCCESS] Job #{job_id} Fujifilm DryPix 2000 da MUVAFFAQIYATLI CHOP ETILDI!")
        except Exception as err:
            print(f"[PrintSCP] [XATO] DryPix ga chop etishda xato: {err}")
            job = self.storage.record_print_attempt(job_id, success=False, error_msg=str(err))
            self.storage.add_audit_log(
                user_login="AUTO_SPOOLER",
                user_name="Avtomatik Spooler",
                ip_address="127.0.0.1",
                action="PRINT_FAILED",
                job_id=job_id,
                patient_id=job.get('patient_id') if job else None,
                patient_name=job.get('patient_name') if job else None,
                details=f"Chop etishda xatolik: {err}"
            )

    def _handle_delete(self, event):
        return 0x0000, Dataset()

    def _handle_conn_close(self, event):
        assoc_id = id(event.assoc)
        with self._lock:
            if assoc_id in self.sessions:
                del self.sessions[assoc_id]
        print(f"[PrintSCP] Ulanish yopildi")
