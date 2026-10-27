-- Siemens Altea Spooler & 6-Drive Burner Database Schema

CREATE TABLE IF NOT EXISTS print_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_uid TEXT UNIQUE NOT NULL,
  patient_id TEXT,
  patient_name TEXT,
  patient_dob TEXT,
  patient_gender TEXT,
  study_date TEXT,
  protocol_no TEXT,
  modality TEXT DEFAULT 'MR',
  film_format TEXT DEFAULT 'STANDARD\2,3',
  film_size TEXT DEFAULT '14INX17IN',
  orientation TEXT DEFAULT 'PORTRAIT',
  copies INTEGER DEFAULT 1,
  preview_image TEXT,
  raw_data_path TEXT,
  status TEXT DEFAULT 'QUEUED', -- QUEUED, APPROVED, PRINTING, PRINTED, CANCELLED
  karmed_synced INTEGER DEFAULT 0,
  creatinine_val TEXT,
  urea_val TEXT,
  diagnosis TEXT,
  department TEXT,
  doctor TEXT,
  created_at TEXT NOT NULL,
  printed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_print_jobs_patient ON print_jobs (patient_id);
CREATE INDEX IF NOT EXISTS idx_print_jobs_status ON print_jobs (status);
CREATE INDEX IF NOT EXISTS idx_print_jobs_created ON print_jobs (created_at);

CREATE TABLE IF NOT EXISTS dvd_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_uid TEXT UNIQUE NOT NULL,
  patient_id TEXT,
  patient_name TEXT,
  study_uid TEXT,
  drive_letter TEXT,
  status TEXT DEFAULT 'PENDING', -- PENDING, FETCHING, PREPARING, BURNING, COMPLETED, FAILED
  progress INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_dvd_jobs_status ON dvd_jobs (status);

CREATE TABLE IF NOT EXISTS dvd_drives (
  drive_letter TEXT PRIMARY KEY,
  caption TEXT,
  status TEXT DEFAULT 'IDLE', -- IDLE, BURNING, NO_MEDIA, OPEN
  current_job_id INTEGER,
  last_checked TEXT
);

CREATE TABLE IF NOT EXISTS statistics_daily (
  date TEXT PRIMARY KEY,
  total_patients INTEGER DEFAULT 0,
  films_queued INTEGER DEFAULT 0,
  films_printed INTEGER DEFAULT 0,
  films_saved INTEGER DEFAULT 0,
  disks_burned INTEGER DEFAULT 0,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT NOT NULL
);
