"""
simulator.py - Siemens Magnetom Altea MRT apparati DICOM Print simulyatori
Tizimni Siemens apparatisiz to'liq tekshirish va sinash uchun ishlatiladi.
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import datetime
import numpy as np
from pynetdicom import AE
from pynetdicom.sop_class import (
    BasicGrayscalePrintManagementMeta,
    BasicFilmSession,
    BasicFilmBox,
    BasicGrayscaleImageBox,
    Printer,
    Verification
)
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid

def generate_mri_slice(pos, total=6, width=256, height=256):
    """Realistik MRT miya kesimi (axial brain MRI) simulyatsiyasini chizish"""
    y, x = np.ogrid[:height, :width]
    center_y, center_x = height / 2, width / 2
    
    dist_sq = ((x - center_x) / (width * 0.38))**2 + ((y - center_y) / (height * 0.44))**2
    brain_mask = dist_sq <= 1.0
    
    arr = np.random.randint(10, 25, (height, width), dtype=np.uint8)
    tissue = 90 + int(35 * np.sin(pos * 0.5)) + (60 * (1.0 - dist_sq)).clip(0, 70).astype(np.uint8)
    arr[brain_mask] = tissue[brain_mask]
    
    v_mask = (((x - center_x) / 18)**2 + ((y - center_y) / 36)**2) <= 1.0
    arr[v_mask] = np.random.randint(15, 30, v_mask.sum(), dtype=np.uint8)
    
    skull_mask = (dist_sq <= 1.05) & (dist_sq >= 0.96)
    arr[skull_mask] = 230
    
    return arr

def send_simulated_print_job(
    server_ip="127.0.0.1",
    server_port=1005,
    patient_id="52360",
    patient_name="ALIMOV VALI KARIMOVICH",
    film_format="STANDARD\\2,3",
    film_size="14INX17IN"
):
    calling_ae = b"ALTEA_MRT1"
    called_ae = b"DRYPIX2"
    
    ae = AE(ae_title=calling_ae)
    for sc in [BasicGrayscalePrintManagementMeta, BasicFilmSession, BasicFilmBox, BasicGrayscaleImageBox, Printer, Verification]:
        ae.add_requested_context(sc)
        
    print(f"[Simulyator] {server_ip}:{server_port} ga Siemens Altea ulanishi o'rnatilmoqda...")
    assoc = ae.associate(server_ip, server_port, ae_title=called_ae)
    if not assoc.is_established:
        raise ConnectionError(f"Serverga ulanib bo'lmadi: {server_ip}:{server_port}")
        
    try:
        # 1. Echo
        assoc.send_c_echo()
        
        # 2. Film Session
        fs_ds = Dataset()
        fs_ds.NumberOfCopies = 1
        fs_ds.PrintPriority = 'HIGH'
        fs_ds.MediumType = 'BLUE FILM'
        fs_ds.FilmDestination = 'PROCESSOR'
        fs_ds.FilmSessionLabel = f"ID: {patient_id} - {patient_name}"
        
        fs_inst_uid = generate_uid()
        fs_status, fs_rsp = assoc.send_n_create(fs_ds, BasicFilmSession, fs_inst_uid, meta_uid=BasicGrayscalePrintManagementMeta)
        if not fs_status or fs_status.Status != 0:
            raise RuntimeError(f"Film Session yaratib bo'lmadi: {fs_status}")
            
        # 3. Film Box
        cols, rows = 2, 3
        if 'STANDARD\\' in film_format:
            p = film_format.replace('STANDARD\\', '').split(',')
            cols, rows = int(p[0]), int(p[1])
        total_boxes = cols * rows
        
        fb_ds = Dataset()
        fb_ds.ImageDisplayFormat = film_format
        fb_ds.FilmOrientation = 'PORTRAIT'
        fb_ds.FilmSizeID = film_size
        fb_ds.MagnificationType = 'CUBIC'
        
        ref_fs = Dataset()
        ref_fs.ReferencedSOPClassUID = BasicFilmSession
        ref_fs.ReferencedSOPInstanceUID = fs_inst_uid
        fb_ds.ReferencedFilmSessionSequence = Sequence([ref_fs])
        
        fb_inst_uid = generate_uid()
        fb_status, fb_rsp = assoc.send_n_create(fb_ds, BasicFilmBox, fb_inst_uid, meta_uid=BasicGrayscalePrintManagementMeta)
        if not fb_status or fb_status.Status != 0:
            raise RuntimeError(f"Film Box yaratib bo'lmadi: {fb_status}")
            
        box_seq = fb_rsp.ReferencedImageBoxSequence
        print(f"[Simulyator] Serverdan {len(box_seq)} ta kadr katagi qabul qilindi.")
        
        # 4. Kadrlar piksellarini yuborish (N-SET)
        today_ymd = datetime.date.today().strftime('%Y%m%d')
        for idx, item in enumerate(box_seq):
            pos = idx + 1
            box_uid = item.ReferencedSOPInstanceUID
            
            arr = generate_mri_slice(pos, total=total_boxes, width=256, height=256)
            
            raw_img = Dataset()
            raw_img.SamplesPerPixel = 1
            raw_img.PhotometricInterpretation = 'MONOCHROME2'
            raw_img.Rows = arr.shape[0]
            raw_img.Columns = arr.shape[1]
            raw_img.BitsAllocated = 8
            raw_img.BitsStored = 8
            raw_img.HighBit = 7
            raw_img.PixelRepresentation = 0
            raw_img.PixelData = arr.tobytes()
            
            raw_img.PatientName = patient_name
            raw_img.PatientID = patient_id
            raw_img.PatientBirthDate = "19850412"
            raw_img.PatientSex = "M"
            raw_img.StudyDate = today_ymd
            raw_img.ProtocolName = "10036"
            
            set_ds = Dataset()
            set_ds.ImageBoxPosition = pos
            set_ds.BasicGrayscaleImageSequence = Sequence([raw_img])
            
            assoc.send_n_set(set_ds, BasicGrayscaleImageBox, box_uid, meta_uid=BasicGrayscalePrintManagementMeta)
            print(f"[Simulyator] Kadr #{pos}/{total_boxes} uzatildi.")
            
        # 5. N-ACTION (Pechat buyrug'i)
        act_status, _ = assoc.send_n_action(None, 1, BasicFilmBox, fb_inst_uid)
        print(f"[Simulyator] N-ACTION yuborildi. Server javobi: {act_status}")
        
        assoc.release()
        print("[Simulyator] [OK] Test plonka muvaffaqiyatli serverga uzatildi!")
        return True
        
    except Exception as e:
        assoc.abort()
        raise e

if __name__ == '__main__':
    send_simulated_print_job()
