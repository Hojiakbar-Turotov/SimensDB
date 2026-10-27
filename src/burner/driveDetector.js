/**
 * driveDetector.js - Windows 10 da 6 ta CD/DVD diskovodni aniqlash va monitoring qilish
 */
const { exec } = require('child_process');
const db = require('../db/database');

function detectDrives() {
  return new Promise((resolve) => {
    // PowerShell orqali barcha optik drayvlarni so'raymiz
    const psCmd = `powershell -NoProfile -Command "Get-CimInstance Win32_CDROMDrive | Select-Object Drive, Caption, Status | ConvertTo-Json"`;

    exec(psCmd, (error, stdout, stderr) => {
      let physicalDrives = [];

      if (!error && stdout && stdout.trim()) {
        try {
          const parsed = JSON.parse(stdout.trim());
          const list = Array.isArray(parsed) ? parsed : [parsed];
          physicalDrives = list
            .filter(d => d && d.Drive)
            .map(d => ({
              drive_letter: d.Drive.toUpperCase(),
              caption: d.Caption || 'CD/DVD Writer',
              status: 'IDLE'
            }));
        } catch (e) {
          console.warn('[DriveDetector] JSON parse xatosi:', e.message);
        }
      }

      // Agar jismoniy drayvlar topilsa, bazani yangilaymiz
      if (physicalDrives.length > 0) {
        for (const drive of physicalDrives) {
          db.upsertDrive(drive);
        }
        return resolve(db.getAllDrives());
      }

      // Agar hozircha jismoniy drayv ulanmagan bo'lsa (test/dev rejimida),
      // 6 ta virtual drayv slotini yaratamiz: E:, F:, G:, H:, I:, J:
      const existingDrives = db.getAllDrives();
      if (existingDrives.length === 0) {
        const defaultLetters = ['E:', 'F:', 'G:', 'H:', 'I:', 'J:'];
        for (let i = 0; i < defaultLetters.length; i++) {
          const letter = defaultLetters[i];
          db.upsertDrive({
            drive_letter: letter,
            caption: `CD/DVD-RW Diskovod #${i + 1} (${letter})`,
            status: 'IDLE'
          });
        }
      }

      resolve(db.getAllDrives());
    });
  });
}

function ejectDrive(driveLetter) {
  return new Promise((resolve) => {
    const cleanLetter = driveLetter.replace(/[^A-Za-z:]/g, '');
    const psCmd = `powershell -NoProfile -Command "(New-Object -ComObject Shell.Application).Namespace(17).ParseName('${cleanLetter}').InvokeVerb('Eject')"`;
    exec(psCmd, (err) => {
      if (err) {
        console.warn(`[DriveDetector] ${cleanLetter} drayvini chiqarishda xato:`, err.message);
      } else {
        console.log(`[DriveDetector] ${cleanLetter} drayvi avtomatik chiqarildi (Ejected).`);
      }
      db.updateDriveStatus(cleanLetter, 'OPEN');
      resolve(true);
    });
  });
}

module.exports = {
  detectDrives,
  ejectDrive
};
