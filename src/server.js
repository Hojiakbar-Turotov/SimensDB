/**
 * server.js - Siemens Altea Spooler, DryPix 2000 Driver & 6-Drive Burner Server
 */
const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

const config = require('../config/config');
const db = require('./db/database');
const printScpServer = require('./dicom/printScpServer');
const printScuClient = require('./dicom/printScuClient');
const burnerEngine = require('./burner/burnerEngine');
const { detectDrives, ejectDrive } = require('./burner/driveDetector');
const karmedClient = require('./karmed/KarmedClient');
const reportSync = require('./github/reportSync');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: '*' }
});

// Middlewares
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Statik papkalar
app.use(express.static(path.join(config.rootDir, 'public')));
app.use('/storage/previews', express.static(config.paths.previews));
app.use('/docs', express.static(config.paths.docs));

// Socket.io ni barcha xizmatlarga ulash
printScpServer.setSocketIO(io);
printScuClient.setSocketIO(io);
burnerEngine.setSocketIO(io);

// --- REST API ENDPOINTLARI ---

// 1. Statistika
app.get('/api/stats', (req, res) => {
  res.json({
    today: db.getDailyStats(),
    history: db.getAllStats(10)
  });
});

// 2. Plonkalar ro'yxati
app.get('/api/print-jobs', (req, res) => {
  const status = req.query.status;
  const patientId = req.query.patient_id;
  const jobs = db.getPrintJobs({ status, patient_id: patientId, limit: 100 });
  res.json(jobs);
});

// 3. Tanlangan plonkani Fujifilm DryPix 2000 printeriga chop etish
app.post('/api/print-jobs/:id/print', async (req, res) => {
  try {
    const jobId = parseInt(req.params.id, 10);
    const updated = await printScuClient.sendJobToDryPix(jobId);
    res.json({ success: true, job: updated });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 4. Plonkani bekor qilish (Tejab qolingan deb qayd etiladi)
app.post('/api/print-jobs/:id/cancel', (req, res) => {
  try {
    const jobId = parseInt(req.params.id, 10);
    const updated = db.updatePrintJobStatus(jobId, 'CANCELLED');
    io.emit('PRINT_JOB_STATUS', { jobId, status: 'CANCELLED' });
    io.emit('STATS_UPDATED', db.getDailyStats());
    res.json({ success: true, job: updated });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 5. Test uchun simulyatsiya qilingan plonka yaratish
app.post('/api/print-jobs/simulate', async (req, res) => {
  try {
    const samplePatients = [
      { id: '52360', name: 'ALIMOV VALI KARIMOVICH', dob: '1985-04-12', format: 'STANDARD\\2,3', proto: '10036' },
      { id: '64120', name: 'KARIMOVA NIGORA ANVAROVNA', dob: '1992-08-23', format: 'STANDARD\\3,4', proto: '10042' },
      { id: '71005', name: 'TURSUNOV BOTIR ZOKIROVICH', dob: '1978-11-05', format: 'STANDARD\\2,3', proto: '10045' },
      { id: '83419', name: 'YUSUPOVA MALIKA SHAVKATOVNA', dob: '2001-02-17', format: 'STANDARD\\1,1', proto: '10051' }
    ];
    const pick = samplePatients[Math.floor(Math.random() * samplePatients.length)];
    const job = await printScpServer.registerIncomingFilmJob({
      patient_id: req.body.patient_id || pick.id,
      patient_name: req.body.patient_name || pick.name,
      patient_dob: req.body.patient_dob || pick.dob,
      film_format: req.body.film_format || pick.format,
      protocol_no: req.body.protocol_no || pick.proto
    });
    res.json({ success: true, job });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 6. Diskovodlar holati (6 ta drayv)
app.get('/api/drives', async (req, res) => {
  try {
    await detectDrives();
    res.json(db.getAllDrives());
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 7. Diskovodni chiqarish (Eject)
app.post('/api/drives/:letter/eject', async (req, res) => {
  try {
    const letter = decodeURIComponent(req.params.letter);
    await ejectDrive(letter);
    io.emit('DRIVES_UPDATED', db.getAllDrives());
    res.json({ success: true, letter });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 8. Diskka yozish topshirig'ini boshlash
app.post('/api/burn', async (req, res) => {
  try {
    const { patient_id, patient_name, study_uid, drive_letter, protocol_no, diagnosis, doctor } = req.body;
    const dvdJob = await burnerEngine.startBurnJob({
      patient_id,
      patient_name,
      study_uid,
      protocol_no,
      diagnosis,
      doctor
    }, drive_letter);
    res.json({ success: true, job: dvdJob });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 9. Karmed tizimidan bemorni qidirish
app.get('/api/karmed/patient/:id', async (req, res) => {
  try {
    const kimlikId = req.params.id;
    const details = await karmedClient.getPatientDetailsByKimlik(kimlikId);
    if (!details) {
      return res.status(404).json({ success: false, message: "Bemor Karmedda topilmadi" });
    }
    res.json({ success: true, patient: details });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 10. GitHubga hisobotni yuklash (Manual sync)
app.post('/api/github/sync', async (req, res) => {
  try {
    const result = await reportSync.syncToGitHub();
    res.json(result);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Socket.io Realtime Aloqa
io.on('connection', async (socket) => {
  console.log(`[Socket.io] Operator brauzeri ulandi: ${socket.id}`);

  // Dastlabki ma'lumotlarni yuboramiz
  socket.emit('STATS_UPDATED', db.getDailyStats());
  socket.emit('DRIVES_UPDATED', db.getAllDrives());
  socket.emit('RECENT_JOBS', db.getPrintJobs({ limit: 30 }));

  socket.on('disconnect', () => {
    console.log(`[Socket.io] Brauzer uzildi: ${socket.id}`);
  });
});

// Serverni ishga tushirish
async function startApplication() {
  try {
    // 1. Drayvlarni birinchi bor aniqlash
    await detectDrives();

    // 2. Statik hisobot sahifasini dastlabki generatsiya qilish
    reportSync.generateStaticReport();

    // 3. DICOM Print SCP serverni ishga tushirish (Port 5104)
    await printScpServer.start();

    // 4. Web serverni ishga tushirish (Port 3000)
    server.listen(config.server.port, config.server.host, () => {
      console.log(`\n============================================================`);
      console.log(`🏥 SIEMENS ALTEA & FUJI DRYPIX 2000 SPOOLER TIZIMI ISHGA TUSHDI`);
      console.log(`👉 Web Boshqaruv Paneli: http://localhost:${config.server.port}`);
      console.log(`🖨 Virtual DICOM Printer: Port ${config.dicomScp.port} (AET: ${config.dicomScp.aeTitle})`);
      console.log(`💿 CD/DVD Diskovodlar: 6 ta drayv faol`);
      console.log(`============================================================\n`);
    });
  } catch (err) {
    console.error('[App] Ishga tushirishda jiddiy xato:', err);
  }
}

startApplication();
