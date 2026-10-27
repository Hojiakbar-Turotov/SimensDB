const path = require('path');
const db = require('./db/database');
const printScpServer = require('./dicom/printScpServer');
const printScuClient = require('./dicom/printScuClient');
const burnerEngine = require('./burner/burnerEngine');
const { detectDrives } = require('./burner/driveDetector');
const reportSync = require('./github/reportSync');

async function testAll() {
  console.log('--- 1. Testing DB ---');
  const stats = db.getDailyStats();
  console.log('Daily stats:', stats);

  console.log('--- 2. Testing Drive Detection ---');
  const drives = await detectDrives();
  console.log('Detected optical drives count:', drives.length);
  drives.forEach(d => console.log(`  Drive: ${d.drive_letter} (${d.caption}) - Status: ${d.status}`));

  console.log('--- 3. Testing Incoming Print Job Simulation ---');
  const job = await printScpServer.registerIncomingFilmJob({
    patient_id: '52360',
    patient_name: 'ALIMOV VALI KARIMOVICH',
    patient_dob: '1985-04-12',
    film_format: 'STANDARD\\2,3',
    protocol_no: '10036'
  });
  console.log('Created Print Job ID:', job.id, 'Preview:', job.preview_image);

  console.log('--- 4. Testing Print SCU to Fuji DryPix 2000 ---');
  const printedJob = await printScuClient.sendJobToDryPix(job.id);
  console.log('Printed Job status:', printedJob.status, 'Printed at:', printedJob.printed_at);

  console.log('--- 5. Testing Burner Job Allocation ---');
  const burnJob = await burnerEngine.startBurnJob({
    patient_id: '52360',
    patient_name: 'ALIMOV VALI KARIMOVICH',
    protocol_no: '10036'
  });
  console.log('Allocated Burn Job ID:', burnJob.id, 'Assigned drive:', burnJob.drive_letter);

  console.log('--- 6. Testing Static GitHub Report Generation ---');
  const report = reportSync.generateStaticReport();
  console.log('Generated GitHub Report HTML at:', report.htmlPath);

  console.log('\n>>> BARCHA SINOVLAR MUVAFFAQIYATLI O\'TDI! <<<');
}

testAll().catch(console.error);
