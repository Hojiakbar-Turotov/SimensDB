/**
 * printScpServer.js - Siemens Magnetom Altea uchun Virtual DICOM Print SCP Server
 */
const net = require('net');
const fs = require('fs');
const path = require('path');
const { Jimp } = require('jimp');
const config = require('../../config/config');
const db = require('../db/database');
const karmedClient = require('../karmed/KarmedClient');

class PrintScpServer {
  constructor() {
    this.server = null;
    this.io = null;
    this.activeSessions = new Map(); // socket -> session state
  }

  setSocketIO(io) {
    this.io = io;
  }

  start() {
    return new Promise((resolve, reject) => {
      this.server = net.createServer((socket) => this._handleConnection(socket));

      this.server.on('error', (err) => {
        console.error(`[PrintSCP] Server xatosi (Port ${config.dicomScp.port}):`, err.message);
        reject(err);
      });

      this.server.listen(config.dicomScp.port, config.server.host, () => {
        console.log(`[PrintSCP] Virtual DICOM Print Server ishga tushdi: Port ${config.dicomScp.port}, AET: ${config.dicomScp.aeTitle}`);
        resolve(true);
      });
    });
  }

  _handleConnection(socket) {
    const clientIp = socket.remoteAddress;
    console.log(`[PrintSCP] Yangi DICOM ulanish qabul qilindi: ${clientIp}`);

    let buffer = Buffer.alloc(0);
    const sessionState = {
      filmSession: null,
      filmBox: null,
      imageBoxes: new Map()
    };

    socket.on('data', async (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      // DICOM PDU Type tekshiruvi
      if (buffer.length < 6) return;

      const pduType = buffer[0];
      const pduLength = buffer.readUInt32BE(2);

      if (buffer.length < pduLength + 6) return; // To'liq paket kelishini kutamiz

      const pduData = buffer.slice(0, pduLength + 6);
      buffer = buffer.slice(pduLength + 6);

      try {
        await this._processPdu(socket, pduType, pduData, sessionState);
      } catch (e) {
        console.warn('[PrintSCP] PDU qayta ishlashda xato:', e.message);
      }
    });

    socket.on('close', () => {
      console.log(`[PrintSCP] Ulanish yopildi: ${clientIp}`);
    });

    socket.on('error', (err) => {
      console.warn(`[PrintSCP] Socket xatosi:`, err.message);
    });
  }

  async _processPdu(socket, pduType, data, state) {
    // 0x01 = A-ASSOCIATE-RQ
    if (pduType === 0x01) {
      console.log('[PrintSCP] A-ASSOCIATE-RQ qabul qilindi, A-ASSOCIATE-AC javob qaytarilmoqda...');
      const response = this._buildAssociateAc(data);
      socket.write(response);
      return;
    }

    // 0x04 = P-DATA-TF (DIMSE buyruqlari)
    if (pduType === 0x04) {
      this._handleDimseData(socket, data, state);
      return;
    }

    // 0x05 = A-RELEASE-RQ
    if (pduType === 0x05) {
      console.log('[PrintSCP] A-RELEASE-RQ qabul qilindi, A-RELEASE-RP qaytarilmoqda...');
      const releaseRp = Buffer.from([0x06, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00]);
      socket.write(releaseRp);
      return;
    }
  }

  _buildAssociateAc(rqData) {
    // Standart A-ASSOCIATE-AC javobi
    const ac = Buffer.alloc(rqData.length);
    rqData.copy(ac);
    ac[0] = 0x02; // A-ASSOCIATE-AC
    return ac;
  }

  _handleDimseData(socket, data, state) {
    // DIMSE buyruqlariga success javoblarini tayyorlash
    // Haqiqiy MRT bilan ishlaganda N-CREATE, N-SET, N-ACTION buyruqlari o'qiladi
  }

  /**
   * Preview rasmini (Film Sheet Grid) generatsiya qilish
   */
  async generateFilmPreview(jobUid, patientInfo, grid = 'STANDARD\\2,3', cells = 6) {
    const width = 800;
    const height = 1100;

    // Qora fonli plonka varag'i
    const image = new Jimp({ width, height, color: 0x0a0f1dff });

    // Plonka sarlavhasi (Header text & Hospital info)
    const previewFileName = `preview_${jobUid}.png`;
    const previewFilePath = path.join(config.paths.previews, previewFileName);

    // Kadrlar to'r kataklari (Grid: 2x3 = 2 qator, 3 ustun)
    const parts = grid.replace('STANDARD\\', '').split(',');
    const cols = parseInt(parts[0], 10) || 2;
    const rows = parseInt(parts[1], 10) || 3;
    const totalCells = cols * rows;

    const cellMargin = 8;
    const headerHeight = 70;
    const availableWidth = width - (cellMargin * (cols + 1));
    const availableHeight = height - headerHeight - (cellMargin * (rows + 1));
    const cellW = Math.floor(availableWidth / cols);
    const cellH = Math.floor(availableHeight / rows);

    // Har bir katakka MRT simulyatsiya kadrini chizamiz
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const x = cellMargin + c * (cellW + cellMargin);
        const y = headerHeight + cellMargin + r * (cellH + cellMargin);

        // Kadr fonini to'ldirish
        for (let py = 0; py < cellH; py++) {
          for (let px = 0; px < cellW; px++) {
            // Kontrastli tibbiy MRI siluet gradienti
            const distFromCenter = Math.sqrt(
              Math.pow(px - cellW / 2, 2) + Math.pow(py - cellH / 2, 2)
            );
            const radius = Math.min(cellW, cellH) * 0.42;
            let val = 20;
            if (distFromCenter < radius) {
              val = Math.floor(80 + 120 * (1 - distFromCenter / radius));
            }
            const color = (((val << 24) | (val << 16) | (val << 8) | 0xff) >>> 0);
            image.setPixelColor(color, x + px, y + py);
          }
        }
      }
    }

    await image.write(previewFilePath);
    return `/storage/previews/${previewFileName}`;
  }

  /**
   * Yangi plonkani qabul qilish va bazaga kiritish (Haqiqiy yoki Simulyatsiya)
   */
  async registerIncomingFilmJob(filmData) {
    const jobUid = filmData.job_uid || `MR-${Date.now()}`;
    const previewUrl = await this.generateFilmPreview(
      jobUid,
      filmData,
      filmData.film_format || 'STANDARD\\2,3'
    );

    const job = db.createPrintJob({
      job_uid: jobUid,
      patient_id: filmData.patient_id || '52360',
      patient_name: filmData.patient_name || 'ALIMOV VALI KARIMOVICH',
      patient_dob: filmData.patient_dob || '1985-04-12',
      patient_gender: filmData.patient_gender || 'M',
      study_date: filmData.study_date || new Date().toISOString().split('T')[0],
      protocol_no: filmData.protocol_no || '10036',
      modality: 'MR',
      film_format: filmData.film_format || 'STANDARD\\2,3',
      film_size: filmData.film_size || '14INX17IN',
      orientation: filmData.orientation || 'PORTRAIT',
      copies: filmData.copies || 1,
      preview_image: previewUrl,
      status: 'QUEUED'
    });

    console.log(`[PrintSCP] Yangi plonka saqlandi: Job #${job.id} (Bemor: ${job.patient_name})`);

    // Karmed tizimidan bemor ma'lumotlarini orqa fonda yuklash
    this._enrichJobWithKarmed(job.patient_id);

    // Socket.io orqali brauzerlarga jonli xabar
    if (this.io) {
      this.io.emit('NEW_PRINT_JOB', job);
      this.io.emit('STATS_UPDATED', db.getDailyStats());
    }

    return job;
  }

  async _enrichJobWithKarmed(patientId) {
    try {
      const details = await karmedClient.getPatientDetailsByKimlik(patientId);
      if (details) {
        db.updatePrintJobKarmed(patientId, details);
        if (this.io) {
          this.io.emit('JOB_UPDATED', { patientId, karmed: details });
        }
      }
    } catch (e) {
      console.warn('[PrintSCP] Karmeddan to\'ldirishda xato:', e.message);
    }
  }
}

const printScpServer = new PrintScpServer();

module.exports = printScpServer;
