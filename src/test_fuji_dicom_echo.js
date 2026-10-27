const net = require('net');

function padAET(aet) {
  return (aet + '                ').slice(0, 16);
}

function buildAssociateRq(calledAet = 'DRYPIX2', callingAet = 'MRT1') {
  // 1. Application Context Item (0x10)
  const appCtxUid = '1.2.840.10008.3.1.1.1';
  const appCtxBuf = Buffer.concat([
    Buffer.from([0x10, 0x00]),
    Buffer.alloc(2), // length placeholder
    Buffer.from(appCtxUid, 'ascii')
  ]);
  appCtxBuf.writeUInt16BE(appCtxUid.length, 2);

  // Helper for Presentation Context Item (0x20)
  function makePresCtx(id, abstractSyntaxUid) {
    // Abstract Syntax Sub-Item (0x30)
    const absBuf = Buffer.concat([
      Buffer.from([0x30, 0x00]),
      Buffer.alloc(2),
      Buffer.from(abstractSyntaxUid, 'ascii')
    ]);
    absBuf.writeUInt16BE(abstractSyntaxUid.length, 2);

    // Transfer Syntax Sub-Item (0x40) - Implicit VR Little Endian
    const tsUid = '1.2.840.10008.1.2';
    const tsBuf = Buffer.concat([
      Buffer.from([0x40, 0x00]),
      Buffer.alloc(2),
      Buffer.from(tsUid, 'ascii')
    ]);
    tsBuf.writeUInt16BE(tsUid.length, 2);

    // Presentation Context (0x20)
    const totalSubLen = absBuf.length + tsBuf.length + 4;
    const pcBuf = Buffer.concat([
      Buffer.from([0x20, 0x00]),
      Buffer.alloc(2),
      Buffer.from([id, 0x00, 0x00, 0x00]), // ID, reserved
      absBuf,
      tsBuf
    ]);
    pcBuf.writeUInt16BE(totalSubLen, 2);
    return pcBuf;
  }

  // Presentation contexts for Print
  const pcList = [
    makePresCtx(1, '1.2.840.10008.5.1.1.9'),  // Basic Grayscale Print Management Meta SOP Class
    makePresCtx(3, '1.2.840.10008.5.1.1.1'),  // Basic Film Session SOP Class
    makePresCtx(5, '1.2.840.10008.5.1.1.2'),  // Basic Film Box SOP Class
    makePresCtx(7, '1.2.840.10008.5.1.1.4'),  // Basic Grayscale Image Box SOP Class
    makePresCtx(9, '1.2.840.10008.5.1.1.16')  // Printer SOP Class
  ];

  // User Information Item (0x50)
  // Max PDU length sub-item (0x51) -> 16384 bytes
  const maxPduSub = Buffer.from([0x51, 0x00, 0x00, 0x04, 0x00, 0x00, 0x40, 0x00]);
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

  // Total PDU length = 2 (protocol) + 2 (reserved) + 16 (called) + 16 (calling) + 32 (reserved) + variableItems.length
  const pduLength = 2 + 2 + 16 + 16 + 32 + variableItems.length;

  const header = Buffer.alloc(10);
  header[0] = 0x01; // A-ASSOCIATE-RQ
  header[1] = 0x00; // Reserved
  header.writeUInt32BE(pduLength, 2);
  header.writeUInt16BE(0x0001, 6); // Protocol version
  header.writeUInt16BE(0x0000, 8); // Reserved

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

async function testFujiPrintConnection() {
  const host = '10.34.14.12';
  const port = 104;
  const calledAet = 'DRYPIX2';
  const callingAet = 'MRT1';

  console.log(`[DICOM Test] Ulanish boshlanmoqda: ${host}:${port}`);
  console.log(`[DICOM Test] Called AE Title: "${calledAet}", Calling AE Title: "${callingAet}"`);

  const socket = new net.Socket();
  socket.setTimeout(6000);

  socket.connect(port, host, () => {
    console.log(`[DICOM Test] TCP Ulanish o'rnatildi! A-ASSOCIATE-RQ yuborilmoqda...`);
    const rq = buildAssociateRq(calledAet, callingAet);
    socket.write(rq);
  });

  socket.on('data', (data) => {
    const pduType = data[0];
    const pduLen = data.readUInt32BE(2);
    console.log(`[DICOM Test] Javob qabul qilindi! PDU Type: 0x${pduType.toString(16).padStart(2, '0')}, Uzunlik: ${pduLen} bayt`);

    if (pduType === 0x02) {
      console.log(`>>> TABRIKLAYMIZ! FUJIFILM DRYPIX 2000 A-ASSOCIATE-AC (QABUL QILINDI) JAVOBINI QAYTARDI! <<<`);
      console.log(`>>> Printer bilan DICOM Print assotsiatsiyasi 100% muvaffaqiyatli o'rnatildi! <<<`);

      // A-RELEASE-RQ yuboramiz
      const releaseRq = Buffer.from([0x05, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00]);
      socket.write(releaseRq);
    } else if (pduType === 0x03) {
      console.warn(`[DICOM Test] A-ASSOCIATE-RJ (Rad etildi). Result: ${data[6]}, Reason: ${data[8]}`);
    } else if (pduType === 0x06) {
      console.log(`[DICOM Test] A-RELEASE-RP (Assotsiatsiya toza yopildi).`);
      socket.end();
    }
  });

  socket.on('error', (err) => {
    console.error(`[DICOM Test] Xatolik:`, err.message);
  });

  socket.on('close', () => {
    console.log(`[DICOM Test] Aloqa yakunlandi.`);
  });
}

testFujiPrintConnection();
