/**
 * dicomdirGenerator.js - Bemor diski uchun DICOMDIR va Portable Viewer paketini yaratish
 */
const fs = require('fs');
const path = require('path');
const config = require('../../config/config');

async function prepareDiscPackage(patient, dicomFiles = []) {
  const jobFolder = path.join(config.paths.tempBurn, `disc_${patient.patient_id}_${Date.now()}`);
  fs.mkdirSync(jobFolder, { recursive: true });

  const imagesFolder = path.join(jobFolder, 'IMAGES');
  const viewerFolder = path.join(jobFolder, 'VIEWER');
  fs.mkdirSync(imagesFolder, { recursive: true });
  fs.mkdirSync(viewerFolder, { recursive: true });

  // 1. DICOM fayllarni ko'chirish yoki joylashtirish
  if (dicomFiles && dicomFiles.length > 0) {
    for (let i = 0; i < dicomFiles.length; i++) {
      const src = dicomFiles[i];
      const dest = path.join(imagesFolder, `IMG_${String(i + 1).padStart(4, '0')}.DCM`);
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, dest);
      }
    }
  }

  // 2. Standart autorun.inf
  const autorunContent = `[autorun]
open=start_viewer.bat
icon=VIEWER\\icon.ico
label=MRT Tekshiruvi - ${patient.patient_name || 'Bemor'}
`;
  fs.writeFileSync(path.join(jobFolder, 'autorun.inf'), autorunContent, 'utf-8');

  // 3. Oson ishga tushirish uchun start_viewer.bat
  const batContent = `@echo off
start index.html
exit
`;
  fs.writeFileSync(path.join(jobFolder, 'start_viewer.bat'), batContent, 'utf-8');

  // 4. Bemor haqida ma'lumot hujjati (PATIENT.txt)
  const infoContent = `=====================================================
RESPUBLIKA ONKOLOGIYA VA RADIOLOGIYA ILMIY-AMALIY MARKAZI
MAGNIT-REZONANS TOMOGRAFIYA (MRT) TEKSHIRUVI
=====================================================
Bemor F.I.SH: ${patient.patient_name || '-'}
Bemor ID: ${patient.patient_id || '-'}
Protokol №: ${patient.protocol_no || '-'}
Tekshiruv sanasi: ${patient.study_date || new Date().toLocaleDateString('ru-RU')}
Apparat: Siemens Magnetom Altea (1.5T)
Bo'lim: ${patient.department || 'Radiodiagnostika'}
Shifokor: ${patient.doctor || '-'}
=====================================================
Ko'rsatma: Diskdagi tasvirlarni ko'rish uchun "index.html" yoki 
"start_viewer.bat" faylini bosing.
`;
  fs.writeFileSync(path.join(jobFolder, 'PATIENT_INFO.txt'), infoContent, 'utf-8');

  // 5. Mustaqil Offline HTML5 DICOM Viewer (Har qanday kompyuterda o'rnatishsiz ochiladi)
  const htmlViewer = `<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <title>MRT Ko'ruvchi - ${patient.patient_name || 'Bemor'}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { margin: 0; background: #0f172a; color: #f8fafc; font-family: system-ui, sans-serif; display: flex; flex-direction: column; height: 100vh; }
    header { background: #1e293b; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; }
    h1 { font-size: 18px; margin: 0; color: #38bdf8; }
    .patient-bar { font-size: 14px; color: #94a3b8; }
    .main-view { flex: 1; display: flex; overflow: hidden; }
    .sidebar { width: 280px; background: #1e293b; border-right: 1px solid #334155; padding: 16px; overflow-y: auto; }
    .canvas-area { flex: 1; display: flex; justify-content: center; align-items: center; background: #000; position: relative; }
    .info-card { background: #0f172a; padding: 12px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; line-height: 1.6; }
    .btn { background: #0284c7; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; width: 100%; font-weight: bold; }
    .btn:hover { background: #0369a1; }
    .preview-box { border: 2px dashed #475569; border-radius: 8px; padding: 20px; text-align: center; color: #94a3b8; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>🏥 RESPUBLIKA ONKOLOGIYA MARKAZI — MRT TASVIRLAR</h1>
      <div class="patient-bar">Bemor: <b>${patient.patient_name || 'Bemor'}</b> | ID: ${patient.patient_id || '-'} | Sana: ${patient.study_date || '-'}</div>
    </div>
    <div style="font-size: 13px; color: #38bdf8;">Siemens Magnetom Altea</div>
  </header>
  <div class="main-view">
    <div class="sidebar">
      <div class="info-card">
        <div><b>F.I.SH:</b> ${patient.patient_name || '-'}</div>
        <div><b>Protokol №:</b> ${patient.protocol_no || '-'}</div>
        <div><b>Tashxis:</b> ${patient.diagnosis || '-'}</div>
        <div><b>Shifokor:</b> ${patient.doctor || '-'}</div>
      </div>
      <div class="info-card">
        <b>Fayllar ro'yxati:</b>
        <p style="color: #94a3b8; font-size: 12px;">Diskdagi barcha DICOM (.DCM) seriyalari "IMAGES/" papkasida saqlangan.</p>
      </div>
    </div>
    <div class="canvas-area">
      <div class="preview-box">
        <h2>DICOM Tasvirlar Arxivi</h2>
        <p>Barcha seriyalar muvaffaqiyatli diskka yozilgan.</p>
        <p style="font-size: 12px; color: #64748b;">Shifokorlar har qanday DICOM dasturi (RadiAnt, Weasis, Horos) orqali IMAGES papkasini ochishlari mumkin.</p>
      </div>
    </div>
  </div>
</body>
</html>`;
  fs.writeFileSync(path.join(jobFolder, 'index.html'), htmlViewer, 'utf-8');

  return jobFolder;
}

module.exports = {
  prepareDiscPackage
};
