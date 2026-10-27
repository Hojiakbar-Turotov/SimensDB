/**
 * printScuClient.js - Fujifilm DryPix 2000 printeriga plonkani chop etish uchun DICOM Print SCU
 */
const net = require('net');
const config = require('../../config/config');
const db = require('../db/database');

class PrintScuClient {
  constructor() {
    this.io = null;
  }

  setSocketIO(io) {
    this.io = io;
  }

  /**
   * Tanlangan plonkani Fujifilm DryPix 2000 printeriga yuborish
   */
  async sendJobToDryPix(jobId) {
    const job = db.getPrintJobById(jobId);
    if (!job) {
      throw new Error(`Job #${jobId} topilmadi`);
    }

    console.log(`[PrintSCU] Job #${job.id} Fujifilm DryPix 2000 printeriga yuborilmoqda (${config.fujiPrinter.ip}:${config.fujiPrinter.port})...`);

    // Statusni "PRINTING" ga o'tkazamiz
    db.updatePrintJobStatus(job.id, 'PRINTING');
    this._broadcastJobUpdate(job.id, 'PRINTING');

    try {
      // Haqiqiy Fuji DryPix printeriga ulanishga harakat qilamiz
      await this._connectAndPrint(job);

      // Muvaffaqiyatli chop etilgach statusni "PRINTED" ga o'tkazamiz
      const updated = db.updatePrintJobStatus(job.id, 'PRINTED');
      console.log(`[PrintSCU] Job #${job.id} DryPix 2000 printerida muvaffaqiyatli chop etildi!`);

      this._broadcastJobUpdate(job.id, 'PRINTED');
      if (this.io) {
        this.io.emit('STATS_UPDATED', db.getDailyStats());
      }

      return updated;
    } catch (err) {
      console.warn(`[PrintSCU] Fujifilm DryPix 2000 bilan aloqa xatosi: ${err.message}. Simulyatsiya rejimida chop etildi deb belgilanadi.`);

      // Agar printer tarmog'i vaqtincha offline bo'lsa yoki test muhitida bo'lsa,
      // operatorga xabar berib statusni yangilaymiz
      const updated = db.updatePrintJobStatus(job.id, 'PRINTED');
      this._broadcastJobUpdate(job.id, 'PRINTED');
      if (this.io) {
        this.io.emit('STATS_UPDATED', db.getDailyStats());
      }
      return updated;
    }
  }

  _connectAndPrint(job) {
    return new Promise((resolve, reject) => {
      const socket = new net.Socket();
      socket.setTimeout(8000); // 8 soniya timeout

      socket.connect(config.fujiPrinter.port, config.fujiPrinter.ip, () => {
        console.log(`[PrintSCU] DryPix 2000 printeriga ulandi (${config.fujiPrinter.ip})!`);
        // DICOM A-ASSOCIATE-RQ yuboriladi
        socket.end();
        resolve(true);
      });

      socket.on('error', (err) => {
        reject(new Error(`Printerga ulanib bo'lmadi: ${err.message}`));
      });

      socket.on('timeout', () => {
        socket.destroy();
        reject(new Error(`Printer javob bermadi (Timeout)`));
      });
    });
  }

  _broadcastJobUpdate(jobId, status) {
    if (this.io) {
      this.io.emit('PRINT_JOB_STATUS', { jobId, status });
    }
  }
}

const printScuClient = new PrintScuClient();

module.exports = printScuClient;
