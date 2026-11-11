"""
dicom_scu.py - Fujifilm DryPix Lite (10.34.14.12:104) printeriga DICOM Print SCU orqali yuboruvchi modul
"""
import time
import threading
from pynetdicom import AE
from pynetdicom.sop_class import (
    BasicGrayscalePrintManagementMeta,
    BasicFilmSession,
    BasicFilmBox,
    BasicGrayscaleImageBox,
    Printer
)
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import UID, generate_uid

def is_success_or_warning(status):
    """
    DICOM standartiga ko'ra Status tekshiruvi:
    0x0000 = Success (Muvaffaqiyatli)
    0x0001 = Warning (Atribut ro'yxatida ogohlantirish)
    0xB000 - 0xBFFF = Barcha DICOM Warning kodlari (Chop etish qabul qilingan va davom etadi):
      - 0xB604 (46596): Kadr o'lchami printer katagidan katta, printer uni avtomatik moslashtirdi (demagnified)
      - 0xB605: Optik zichlik (Min/Max density) printer diapazoniga moslashtirildi
      - 0xB600: Xotira taqsimoti
    """
    if not status:
        return False
    code = getattr(status, 'Status', status)
    if code in (0x0000, 0x0001):
        return True
    if (code & 0xF000) == 0xB000:
        return True
    return False

class DicomPrintSCU:
    def __init__(self, config):
        self.config = config
        p_cfg = config.get('printer', {})
        self.ip = p_cfg.get('ip', '10.34.14.12')
        self.port = int(p_cfg.get('port', 104))
        self.called_ae = p_cfg.get('called_ae', 'DRYPIX2').encode('ascii')
        self.calling_ae = p_cfg.get('calling_ae', 'MRT1').encode('ascii')
        self.timeout = int(p_cfg.get('timeout_sec', 15))

        self._cached_status = {
            'online': True,
            'status': 'NORMAL',
            'info': 'NORMAL',
            'name': 'DRYPIX2',
            'model': 'DRYPIX',
            'manufacturer': 'FUJIFILM Corporation'
        }
        self._check_lock = threading.Lock()
        
        # Orqa fonda printer holatini tekshiruvchi oqim
        self._bg_thread = threading.Thread(target=self._background_status_checker, daemon=True)
        self._bg_thread.start()

    def _background_status_checker(self):
        time.sleep(1)
        while True:
            try:
                st = self._do_check_printer()
                with self._check_lock:
                    self._cached_status = st
            except Exception:
                pass
            time.sleep(20)

    def check_printer(self, force=False):
        """
        Printer holatini zudlik bilan qaytarish (veb-panel qotib qolmasligi uchun keshdan o'qiladi)
        """
        if force:
            return self._do_check_printer()
        with self._check_lock:
            return dict(self._cached_status)

    def _do_check_printer(self):
        """
        Fujifilm DryPix 2000 printerining holatini N-GET so'rovi orqali tekshirish
        """
        ae = AE(ae_title=self.calling_ae)
        ae.add_requested_context(BasicGrayscalePrintManagementMeta)
        ae.add_requested_context(Printer)
        ae.network_timeout = 4
        ae.acse_timeout = 4
        ae.dimse_timeout = 4

        try:
            assoc = ae.associate(self.ip, self.port, ae_title=self.called_ae)
            if not assoc.is_established:
                return {
                    'online': False,
                    'status': 'OFFLINE',
                    'error': f"Aloqa yo'q ({self.ip}:{self.port})"
                }

            # N-GET orqali printer ma'lumotlarini o'qish
            status, ds = assoc.send_n_get(
                [0x00080070, 0x00081090, 0x21100010, 0x21100020, 0x21100030],
                Printer,
                UID('1.2.840.10008.5.1.1.17')
            )
            assoc.release()

            if status and is_success_or_warning(status) and ds:
                p_status = str(getattr(ds, 'PrinterStatus', 'NORMAL'))
                p_info = str(getattr(ds, 'PrinterStatusInfo', 'NORMAL'))
                p_name = str(getattr(ds, 'PrinterName', 'DRYPIX2'))
                p_model = str(getattr(ds, 'ManufacturerModelName', 'DRYPIX'))
                mfr = str(getattr(ds, 'Manufacturer', 'FUJIFILM Corporation'))

                return {
                    'online': True,
                    'status': p_status,
                    'info': p_info,
                    'name': p_name,
                    'model': p_model,
                    'manufacturer': mfr
                }
            else:
                return {
                    'online': True,
                    'status': 'NORMAL',
                    'info': f"N-GET status: {status}"
                }
        except Exception as e:
            return {
                'online': False,
                'status': 'OFFLINE',
                'error': str(e)
            }

    def forward_to_drypix(self, film_session_ds, film_box_ds, images_map):
        """
        Siemens apparatidan qabul qilingan to'liq plonkani Fujifilm DryPix 2000 ga chop etish
        """
        print(f"[PrintSCU] DryPix 2000 ({self.ip}:{self.port}, AE: {self.called_ae.decode()}) ga chop etish boshlandi...")

        ae = AE(ae_title=self.calling_ae)
        ae.add_requested_context(BasicGrayscalePrintManagementMeta)
        ae.network_timeout = self.timeout
        ae.acse_timeout = self.timeout
        ae.dimse_timeout = self.timeout

        assoc = ae.associate(self.ip, self.port, ae_title=self.called_ae)
        if not assoc.is_established:
            raise ConnectionError(f"Fujifilm DryPix 2000 printeriga ulanib bo'lmadi ({self.ip}:{self.port})")

        fs_inst_uid = generate_uid()
        fb_inst_uid = generate_uid()

        try:
            # 1-BOSQICH: Basic Film Session (N-CREATE)
            fs_req = Dataset()
            fs_req.NumberOfCopies = int(getattr(film_session_ds, 'NumberOfCopies', 1) or 1)
            fs_req.PrintPriority = getattr(film_session_ds, 'PrintPriority', 'HIGH')
            fs_req.MediumType = getattr(film_session_ds, 'MediumType', 'BLUE FILM')
            fs_req.FilmDestination = getattr(film_session_ds, 'FilmDestination', 'PROCESSOR')

            fs_status, fs_rsp = assoc.send_n_create(
                fs_req,
                BasicFilmSession,
                fs_inst_uid,
                meta_uid=BasicGrayscalePrintManagementMeta
            )
            if not is_success_or_warning(fs_status):
                raise RuntimeError(f"DryPix Film Session yaratishni rad etdi: {fs_status}")
            print(f"[PrintSCU] 1. Film Session muvaffaqiyatli yaratildi ({fs_inst_uid})")

            # 2-BOSQICH: Basic Film Box (N-CREATE)
            fb_req = Dataset()
            fb_req.ImageDisplayFormat = getattr(film_box_ds, 'ImageDisplayFormat', 'STANDARD\\2,3')
            fb_req.FilmOrientation = getattr(film_box_ds, 'FilmOrientation', 'PORTRAIT')
            fb_req.FilmSizeID = getattr(film_box_ds, 'FilmSizeID', '14INX17IN')
            fb_req.MagnificationType = getattr(film_box_ds, 'MagnificationType', 'CUBIC')

            if hasattr(film_box_ds, 'MinDensity'):
                fb_req.MinDensity = film_box_ds.MinDensity
            if hasattr(film_box_ds, 'MaxDensity'):
                fb_req.MaxDensity = film_box_ds.MaxDensity
            if hasattr(film_box_ds, 'BorderDensity'):
                fb_req.BorderDensity = film_box_ds.BorderDensity
            if hasattr(film_box_ds, 'EmptyImageDensity'):
                fb_req.EmptyImageDensity = film_box_ds.EmptyImageDensity

            ref_fs = Dataset()
            ref_fs.ReferencedSOPClassUID = BasicFilmSession
            ref_fs.ReferencedSOPInstanceUID = fs_inst_uid
            fb_req.ReferencedFilmSessionSequence = Sequence([ref_fs])

            fb_status, fb_rsp = assoc.send_n_create(
                fb_req,
                BasicFilmBox,
                fb_inst_uid,
                meta_uid=BasicGrayscalePrintManagementMeta
            )
            if not is_success_or_warning(fb_status) or not fb_rsp:
                raise RuntimeError(f"DryPix Film Box yaratishni rad etdi: {fb_status}")

            img_box_seq = getattr(fb_rsp, 'ReferencedImageBoxSequence', None)
            if not img_box_seq or len(img_box_seq) == 0:
                raise RuntimeError("DryPix ReferencedImageBoxSequence qaytarmadi!")

            print(f"[PrintSCU] 2. Film Box yaratildi. DryPix {len(img_box_seq)} ta Image Box taqdim etdi.")

            # DryPix bergan Image Box UID larni position bo'yicha bog'laymiz
            drypix_boxes = {}
            for idx, item in enumerate(img_box_seq):
                pos = idx + 1
                drypix_boxes[pos] = item.ReferencedSOPInstanceUID

            # 3-BOSQICH: Har bir kadrni DryPix ga uzatish (N-SET)
            sorted_images = sorted(images_map.values(), key=lambda x: x.get('position', 1))
            for item in sorted_images:
                pos = item.get('position', 1)
                ds = item.get('dataset')
                if not ds:
                    continue

                target_box_uid = drypix_boxes.get(pos)
                if not target_box_uid:
                    print(f"[PrintSCU] Ogohlantirish: Kadr #{pos} uchun DryPix Image Box topilmadi, o'tkazib yuborilmoqda.")
                    continue

                seq = getattr(ds, 'BasicGrayscaleImageSequence', None)
                if not seq or len(seq) == 0:
                    continue

                raw_img = seq[0]

                # Standart DICOM Image Box atributlarini tozalab olish (DryPix xatolik bermasligi uchun)
                clean_raw_img = Dataset()
                for attr in [
                    'SamplesPerPixel', 'PhotometricInterpretation', 'Rows', 'Columns',
                    'PixelAspectRatio', 'BitsAllocated', 'BitsStored', 'HighBit',
                    'PixelRepresentation', 'PixelData'
                ]:
                    if hasattr(raw_img, attr):
                        setattr(clean_raw_img, attr, getattr(raw_img, attr))

                # N-SET so'rovi datasetini shakllantirish
                n_set_ds = Dataset()
                n_set_ds.ImageBoxPosition = pos
                n_set_ds.BasicGrayscaleImageSequence = Sequence([clean_raw_img])

                status_set, _ = assoc.send_n_set(
                    n_set_ds,
                    BasicGrayscaleImageBox,
                    target_box_uid,
                    meta_uid=BasicGrayscalePrintManagementMeta
                )

                if not is_success_or_warning(status_set):
                    err_comm = getattr(status_set, 'ErrorComment', '')
                    raise RuntimeError(f"Kadr #{pos} N-SET xatosi: {status_set} ({err_comm})")

                # Agar Warning qaytsa (masalan 0xB604 demagnified)
                if status_set and status_set.Status != 0:
                    err_comm = getattr(status_set, 'ErrorComment', '')
                    print(f"[PrintSCU] Kadr #{pos} qabul qilindi (Ogohlantirish: {hex(status_set.Status)} - {err_comm})")
                else:
                    print(f"[PrintSCU] 3. Kadr #{pos} muvaffaqiyatli DryPix ga yuklandi.")

            # 4-BOSQICH: Chop etish buyrug'i (N-ACTION)
            print("[PrintSCU] 4. DryPix ga N-ACTION (Chop etish) yuborilmoqda...")
            action_status, _ = assoc.send_n_action(
                None, # Action Information dataset shart emas (None)
                1,    # ActionTypeID = 1 (Print)
                BasicFilmBox,
                fb_inst_uid,
                meta_uid=BasicGrayscalePrintManagementMeta
            )

            if not is_success_or_warning(action_status):
                err_comm = getattr(action_status, 'ErrorComment', '')
                raise RuntimeError(f"DryPix N-ACTION rad etdi: {action_status} ({err_comm})")

            print("[PrintSCU] 5. DryPix 2000 chop etishni qabul qildi va tasdiqladi!")

            # 5-BOSQICH: Assotsiatsiyani toza yakunlash
            assoc.release()
            return True

        except Exception as e:
            try:
                assoc.abort()
            except Exception:
                pass
            raise e
