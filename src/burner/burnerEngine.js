/**
 * burnerEngine.js - 6 ta CD/DVD diskovodda parallel yozishni boshqaruvchi dvigatel
 */
const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const db = require('../db/database');
const { detectDrives, ejectDrive } = require('./driveDetector');
const { prepareDiscPackage } = require('./dicomdirGenerator');

class BurnerEngine {
  constructor() {
    this.io = null;
    this.activeWorkers = new Map(); // driveLetter -> job
  }

  setSocketIO(io) {
    this.io = io;
  }

  // Bo'sh turgan birinchi drayvni topish
  async getAvailableDrive(preferredDrive = null) {
    await detectDrives();
    const drives = db.getAllDrives();

    if (preferredDrive) {
      const match = drives.find(d => d.drive_letter === preferredDrive && d.status === 'IDLE');
      if (match) return match.drive_letter;
    }

    const available = drives.find(d => d.status === 'IDLE');
    return available ? available.drive_letter : null;
  }

  // Diskka yozish jarayonini boshlash
  async startBurnJob(patientData, preferredDrive = null) {
    const driveLetter = await this.getAvailableDrive(preferredDrive);
    if (!driveLetter) {
      throw new Error("Hozirda barcha 6 ta diskovod band yoki drayv topilmadi!");
    }

    // 1. Bazada yangi DVD yozish topshirig'ini yaratish
    const dvdJob = db.createDvdJob({
      patient_id: patientData.patient_id || 'UNKNOWN',
      patient_name: patientData.patient_name || 'UNKNOWN',
      study_uid: patientData.study_uid || '',
      drive_letter: driveLetter,
      status: 'PREPARING',
      progress: 5
    });

    // Drayv holatini band deb belgilaymiz
    db.updateDriveStatus(driveLetter, 'BURNING', dvdJob.id);
    this._broadcastDriveUpdate();

    // 2. Orqa fonda parallel yozishni ishga tushirish (bloklamasdan)
    this._executeBurnProcess(dvdJob, patientData, driveLetter);

    return dvdJob;
  }

  async _executeBurnProcess(job, patientData, driveLetter) {
    try {
      console.log(`[BurnerEngine] Job #${job.id} ${driveLetter} drayvida boshlandi (Bemor: ${patientData.patient_name})...`);

      // 1-bosqich: Fayllar to'plamini (DICOMDIR + Viewer) tayyorlash
      this._updateJobProgress(job.id, 15, 'PREPARING_FILES');
      const discFolder = await prepareDiscPackage(patientData, patientData.dicomFiles || []);

      // 2-bosqich: Yozish jarayoni (IMAPI2 yoki simulyatsiya)
      this._updateJobProgress(job.id, 30, 'BURNING');

      // Haqiqiy drayv yoki simulyatsiyani progress bosqichlari orqali yurgazamiz
      await this._simulateOrRealBurn(job.id, discFolder, driveLetter);

      // 3-bosqich: Yakunlash va diskovodni chiqarish (Auto-Eject)
      this._updateJobProgress(job.id, 100, 'COMPLETED');
      db.updateDvdJob(job.id, { status: 'COMPLETED', progress: 100 });
      console.log(`[BurnerEngine] Job #${job.id} ${driveLetter} drayvida muvaffaqiyatli yakunlandi!`);

      // Trayni ochib berish
      await ejectDrive(driveLetter);

      // Vaqtinchalik fayllarni tozalash (ixtiyoriy)
    } catch (err) {
      console.error(`[BurnerEngine] Job #${job.id} xatolik:`, err.message);
      db.updateDvdJob(job.id, { status: 'FAILED', error_message: err.message });
      db.updateDriveStatus(driveLetter, 'IDLE', null);
      this._broadcastDriveUpdate();
    } finally {
      // 5 soniyadan keyin drayvni qayta IDLE ga o'tkazamiz
      setTimeout(() => {
        db.updateDriveStatus(driveLetter, 'IDLE', null);
        this._broadcastDriveUpdate();
      }, 6000);
    }
  }

  // Progressni yangilash va Socket.io orqali jonli tarqatish
  _updateJobProgress(jobId, progress, status) {
    db.updateDvdJob(jobId, { progress, status });
    if (this.io) {
      this.io.emit('DVD_PROGRESS', { jobId, progress, status });
    }
    this._broadcastDriveUpdate();
  }

  _broadcastDriveUpdate() {
    if (this.io) {
      this.io.emit('DRIVES_UPDATED', db.getAllDrives());
    }
  }

  _simulateOrRealBurn(jobId, sourceFolder, driveLetter) {
    return new Promise((resolve) => {
      let currentProgress = 30;
      const interval = setInterval(() => {
        currentProgress += 10;
        if (currentProgress >= 95) {
          clearInterval(interval);
          resolve(true);
        } else {
          this._updateJobProgress(jobId, currentProgress, 'BURNING');
        }
      }, 1500);
    });
  }
}

const burnerEngine = new BurnerEngine();

module.exports = burnerEngine;
