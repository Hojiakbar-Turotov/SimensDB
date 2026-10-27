const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');
const dayjs = require('dayjs');
const config = require('../../config/config');

// Ensure database directory exists
const dbDir = path.dirname(config.paths.db);
if (!fs.existsSync(dbDir)) {
  fs.mkdirSync(dbDir, { recursive: true });
}

const db = new Database(config.paths.db);
db.pragma('journal_mode = WAL');
db.pragma('synchronous = NORMAL');

// Initialize schema
const schemaSql = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf-8');
db.exec(schemaSql);

// Helper for today date string (YYYY-MM-DD)
function getTodayString() {
  return dayjs().format('YYYY-MM-DD');
}

// Ensure today's stats row exists
function ensureDailyStats(dateStr = getTodayString()) {
  const existing = db.prepare('SELECT date FROM statistics_daily WHERE date = ?').get(dateStr);
  if (!existing) {
    db.prepare(`
      INSERT INTO statistics_daily (date, total_patients, films_queued, films_printed, films_saved, disks_burned, updated_at)
      VALUES (?, 0, 0, 0, 0, 0, ?)
    `).run(dateStr, new Date().toISOString());
  }
}

// --- Print Jobs ---
function createPrintJob(job) {
  ensureDailyStats();
  const stmt = db.prepare(`
    INSERT INTO print_jobs (
      job_uid, patient_id, patient_name, patient_dob, patient_gender,
      study_date, protocol_no, modality, film_format, film_size,
      orientation, copies, preview_image, raw_data_path, status, created_at
    ) VALUES (
      @job_uid, @patient_id, @patient_name, @patient_dob, @patient_gender,
      @study_date, @protocol_no, @modality, @film_format, @film_size,
      @orientation, @copies, @preview_image, @raw_data_path, @status, @created_at
    )
  `);

  const info = stmt.run({
    job_uid: job.job_uid || `JOB-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    patient_id: job.patient_id || 'UNKNOWN',
    patient_name: job.patient_name || 'UNKNOWN',
    patient_dob: job.patient_dob || '',
    patient_gender: job.patient_gender || '',
    study_date: job.study_date || dayjs().format('YYYY-MM-DD'),
    protocol_no: job.protocol_no || '',
    modality: job.modality || 'MR',
    film_format: job.film_format || 'STANDARD\\2,3',
    film_size: job.film_size || '14INX17IN',
    orientation: job.orientation || 'PORTRAIT',
    copies: job.copies || 1,
    preview_image: job.preview_image || '',
    raw_data_path: job.raw_data_path || '',
    status: job.status || 'QUEUED',
    created_at: job.created_at || new Date().toISOString()
  });

  incrementDailyStat('films_queued');
  return getPrintJobById(info.lastInsertRowid);
}

function getPrintJobs(options = {}) {
  let query = 'SELECT * FROM print_jobs';
  const conditions = [];
  const params = [];

  if (options.status) {
    conditions.push('status = ?');
    params.push(options.status);
  }
  if (options.patient_id) {
    conditions.push('patient_id LIKE ?');
    params.push(`%${options.patient_id}%`);
  }
  if (options.date) {
    conditions.push('created_at LIKE ?');
    params.push(`${options.date}%`);
  }

  if (conditions.length > 0) {
    query += ' WHERE ' + conditions.join(' AND ');
  }

  query += ' ORDER BY id DESC LIMIT ? OFFSET ?';
  params.push(options.limit || 50);
  params.push(options.offset || 0);

  return db.prepare(query).all(...params);
}

function getPrintJobById(id) {
  return db.prepare('SELECT * FROM print_jobs WHERE id = ?').get(id);
}

function getPrintJobByUid(jobUid) {
  return db.prepare('SELECT * FROM print_jobs WHERE job_uid = ?').get(jobUid);
}

function updatePrintJobStatus(id, status, extra = {}) {
  const current = getPrintJobById(id);
  if (!current) return null;

  let query = 'UPDATE print_jobs SET status = ?';
  const params = [status];

  if (status === 'PRINTED') {
    query += ', printed_at = ?';
    params.push(new Date().toISOString());
    incrementDailyStat('films_printed');
  } else if (status === 'CANCELLED' && current.status === 'QUEUED') {
    incrementDailyStat('films_saved');
  }

  query += ' WHERE id = ?';
  params.push(id);

  db.prepare(query).run(...params);
  return getPrintJobById(id);
}

function updatePrintJobKarmed(patientId, karmedData) {
  const stmt = db.prepare(`
    UPDATE print_jobs 
    SET karmed_synced = 1,
        creatinine_val = COALESCE(?, creatinine_val),
        urea_val = COALESCE(?, urea_val),
        diagnosis = COALESCE(?, diagnosis),
        department = COALESCE(?, department),
        doctor = COALESCE(?, doctor),
        patient_name = CASE WHEN patient_name = 'UNKNOWN' AND ? IS NOT NULL THEN ? ELSE patient_name END
    WHERE patient_id = ?
  `);

  stmt.run(
    karmedData.creatinine || null,
    karmedData.urea || null,
    karmedData.diagnosis || null,
    karmedData.department || null,
    karmedData.doctor || null,
    karmedData.patientName || null,
    karmedData.patientName || null,
    patientId
  );
}

// --- DVD / CD Burning Jobs ---
function createDvdJob(job) {
  ensureDailyStats();
  const stmt = db.prepare(`
    INSERT INTO dvd_jobs (
      job_uid, patient_id, patient_name, study_uid, drive_letter,
      status, progress, created_at
    ) VALUES (
      @job_uid, @patient_id, @patient_name, @study_uid, @drive_letter,
      @status, @progress, @created_at
    )
  `);

  const info = stmt.run({
    job_uid: job.job_uid || `BURN-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
    patient_id: job.patient_id || 'UNKNOWN',
    patient_name: job.patient_name || 'UNKNOWN',
    study_uid: job.study_uid || '',
    drive_letter: job.drive_letter || '',
    status: job.status || 'PENDING',
    progress: job.progress || 0,
    created_at: new Date().toISOString()
  });

  return getDvdJobById(info.lastInsertRowid);
}

function getDvdJobById(id) {
  return db.prepare('SELECT * FROM dvd_jobs WHERE id = ?').get(id);
}

function getDvdJobs(limit = 20) {
  return db.prepare('SELECT * FROM dvd_jobs ORDER BY id DESC LIMIT ?').all(limit);
}

function updateDvdJob(id, updates) {
  const fields = [];
  const params = [];

  for (const [key, val] of Object.entries(updates)) {
    fields.push(`${key} = ?`);
    params.push(val);
  }

  if (updates.status === 'COMPLETED') {
    fields.push('completed_at = ?');
    params.push(new Date().toISOString());
    incrementDailyStat('disks_burned');
  }

  params.push(id);
  db.prepare(`UPDATE dvd_jobs SET ${fields.join(', ')} WHERE id = ?`).run(...params);
  return getDvdJobById(id);
}

// --- DVD Optical Drives ---
function upsertDrive(drive) {
  const stmt = db.prepare(`
    INSERT INTO dvd_drives (drive_letter, caption, status, current_job_id, last_checked)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(drive_letter) DO UPDATE SET
      caption = excluded.caption,
      status = excluded.status,
      current_job_id = excluded.current_job_id,
      last_checked = excluded.last_checked
  `);
  stmt.run(
    drive.drive_letter,
    drive.caption || '',
    drive.status || 'IDLE',
    drive.current_job_id || null,
    new Date().toISOString()
  );
}

function getAllDrives() {
  return db.prepare('SELECT * FROM dvd_drives ORDER BY drive_letter ASC').all();
}

function updateDriveStatus(driveLetter, status, currentJobId = null) {
  db.prepare(`
    UPDATE dvd_drives 
    SET status = ?, current_job_id = ?, last_checked = ?
    WHERE drive_letter = ?
  `).run(status, currentJobId, new Date().toISOString(), driveLetter);
}

// --- Statistics & Metrics ---
function incrementDailyStat(columnName, dateStr = getTodayString()) {
  ensureDailyStats(dateStr);
  const allowed = ['total_patients', 'films_queued', 'films_printed', 'films_saved', 'disks_burned'];
  if (!allowed.includes(columnName)) return;

  db.prepare(`
    UPDATE statistics_daily 
    SET ${columnName} = ${columnName} + 1, updated_at = ?
    WHERE date = ?
  `).run(new Date().toISOString(), dateStr);
}

function getDailyStats(dateStr = getTodayString()) {
  ensureDailyStats(dateStr);
  return db.prepare('SELECT * FROM statistics_daily WHERE date = ?').get(dateStr);
}

function getAllStats(limit = 30) {
  return db.prepare('SELECT * FROM statistics_daily ORDER BY date DESC LIMIT ?').all(limit);
}

// --- Settings ---
function getSetting(key, defaultValue = null) {
  const row = db.prepare('SELECT value FROM app_settings WHERE key = ?').get(key);
  return row ? row.value : defaultValue;
}

function setSetting(key, value) {
  db.prepare(`
    INSERT INTO app_settings (key, value, updated_at)
    VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
  `).run(key, String(value), new Date().toISOString());
}

module.exports = {
  db,
  createPrintJob,
  getPrintJobs,
  getPrintJobById,
  getPrintJobByUid,
  updatePrintJobStatus,
  updatePrintJobKarmed,
  createDvdJob,
  getDvdJobById,
  getDvdJobs,
  updateDvdJob,
  upsertDrive,
  getAllDrives,
  updateDriveStatus,
  incrementDailyStat,
  getDailyStats,
  getAllStats,
  getSetting,
  setSetting
};
