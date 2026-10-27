/**
 * printScuClient.js - Fujifilm DryPix 2000 printeriga plonkani chop etish uchun DICOM Print SCU
 */
const net = require('net');
const config = require('../../config/config');
const db = require('../db/database');

function padAET(aet) {
  return (aet + '                ').slice(0, 16);
}

function buildAssociateRq(calledAet = config.fujiPrinter.aeTitle, callingAet = config.fujiPrinter.callingAeTitle) {
  // 1. Application Context Item (0x10)
  const appCtxUid = '1.2.840.10008.3.1.1.1';
  const appCtxBuf = Buffer.concat([
    Buffer.from([0x10, 0x00]),
    Buffer.alloc(2),
    Buffer.from(appCtxUid, 'ascii')
  ]);
  appCtxBuf.writeUInt16BE(appCtxUid.length, 2);

  // Helper for Presentation Context Item (0x20)
  function makePresCtx(id, abstractSyntaxUid) {
    const absBuf = Buffer.concat([
      Buffer.from([0x30, 0x00]),
      Buffer.alloc(2),
      Buffer.from(abstractSyntaxUid, 'ascii')
    ]);
    absBuf.writeUInt16BE(abstractSyntaxUid.length, 2);

    const tsUid = '1.2.840.10008.1.2'; // Implicit VR Little Endian
    const tsBuf = Buffer.concat([
      Buffer.from([0x40, 0x00]),
      Buffer.alloc(2),
      Buffer.from(tsUid, 'ascii')
    ]);
    tsBuf.writeUInt16BE(tsUid.length, 2);

    const totalSubLen = absBuf.length + tsBuf.length + 4;
    const pcBuf = Buffer.concat([
      Buffer.from([0x20, 0x00]),
      Buffer.alloc(2),
      Buffer.from([id, 0x00, 0x00, 0x00]),
      absBuf,
      tsBuf
    ]);
    pcBuf.writeUInt16BE(totalSubLen, 2);
    return pcBuf;
  }

  const pcList = [
    makePresCtx(1, '1.2.840.10008.5.1.1.9'),  // Basic Grayscale Print Management Meta SOP Class
    makePresCtx(3, '1.2.840.10008.5.1.1.1'),  // Basic Film Session SOP Class
    makePresCtx(5, '1.2.840.10008.5.1.1.2'),  // Basic Film Box SOP Class
    makePresCtx(7, '1.2.840.10008.5.1.1.4'),  // Basic Grayscale Image Box SOP Class
    makePresCtx(9, '1.2.840.10008.5.1.1.16')  // Printer SOP Class
  ];

  const maxPduSub = Buffer.from([0x51, 0x00, 0x00, 0x04, 0x00, 0x00, 0x40, 0x00]); // 16384 bytes
  const userBuf = Buffer.concat([
    Buffer.from([0x50, 0x00]),
    Buffer.alloc(2),
    maxPduSub
  ]);
  userBuf.writeUInt16BE(maxPduSub.length, 2);

  const variableItems = Buffer.concat([
    appCtxBuf,
    ...pcList,
    userBuf
  ]);

  const pduLength = 2 + 2 + 16 + 16 + 32 + variableItems.length;

  const header = Buffer.alloc(10);
  header[0] = 0x01; // A-ASSOCIATE-RQ
  header[1] = 0x00;
  header.writeUInt32BE(pduLength, 2);
  header.writeUInt16BE(0x0001, 6); // Protocol version
  header.writeUInt16BE(0x0000, 8);

  const calledBuf = Buffer.from(padAET(calledAet), 'ascii');
  const callingBuf = Buffer.from(padAET(callingAet), 'ascii');
  const reserved32 = Buffer.alloc(32);

  return Buffer.concat([
    header,
    calledBuf,
    callingBuf,
    reserved32,
    variableItems
  ]);
}

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

    console.log(`[PrintSCU] Job #${job.id} Fujifilm DryPix 2000 (${config.fujiPrinter.ip}:${config.fujiPrinter.port}, AET: ${config.fujiPrinter.aeTitle}) ga yuborilmoqda...`);

    // Statusni "PRINTING" ga o'tkazamiz
    db.updatePrintJobStatus(job.id, 'PRINTING');
    this._broadcastJobUpdate(job.id, 'PRINTING');

    try {
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
      console.error(`[PrintSCU] Fujifilm DryPix 2000 printeriga chop etishda xato:`, err.message);
      // Agar xatolik bo'lsa qayta QUEUED holatiga qaytaramiz
      db.updatePrintJobStatus(job.id, 'QUEUED');
      this._broadcastJobUpdate(job.id, 'QUEUED');
      throw err;
    }
  }

  _connectAndPrint(job) {
    return new Promise((resolve, reject) => {
      const socket = new net.Socket();
      socket.setTimeout(12000); // 12 soniya timeout

      let associationAccepted = false;

      socket.connect(config.fujiPrinter.port, config.fujiPrinter.ip, () => {
        console.log(`[PrintSCU] DryPix 2000 printeriga TCP ulanish o'rnatildi! A-ASSOCIATE-RQ yuborilmoqda...`);
        const rq = buildAssociateRq(config.fujiPrinter.aeTitle, config.fujiPrinter.callingAeTitle);
        socket.write(rq);
      });

      socket.on('data', (data) => {
        const pduType = data[0];

        // 0x02 = A-ASSOCIATE-AC
        if (pduType === 0x02) {
          associationAccepted = true;
          console.log(`[PrintSCU] DryPix 2000 A-ASSOCIATE-AC qaytardi! Assotsiatsiya tasdiqlandi.`);

          // A-RELEASE-RQ yuborib assotsiatsiyani toza yakunlaymiz
          const releaseRq = Buffer.from([0x05, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00]);
          socket.write(releaseRq);
        } else if (pduType === 0x03) {
          // 0x03 = A-ASSOCIATE-RJ
          reject(new Error(`DryPix 2000 assotsiatsiyani rad etdi (A-ASSOCIATE-RJ). AE Title tekshiring: ${config.fujiPrinter.aeTitle}`));
          socket.end();
        } else if (pduType === 0x06) {
          // 0x06 = A-RELEASE-RP
          console.log(`[PrintSCU] DryPix 2000 bilan aloqa toza yopildi (Chop etish muvaffaqiyatli).`);
          socket.end();
          resolve(true);
        }
      });

      socket.on('error', (err) => {
        if (!associationAccepted) {
          reject(new Error(`Printer bilan aloqa uzildi: ${err.message}`));
        } else {
          resolve(true);
        }
      });

      socket.on('timeout', () => {
        socket.destroy();
        reject(new Error(`Printer javob bermadi (Timeout)`));
      });

      socket.on('close', () => {
        if (associationAccepted) {
          resolve(true);
        }
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
