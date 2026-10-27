/**
 * reportSync.js - Kunlik hisobotlarni generatsiya qilish va GitHub Pages ga avtomatik yuklash
 */
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const dayjs = require('dayjs');
const config = require('../../config/config');
const db = require('../db/database');

class ReportSync {
  /**
   * Statik hisobot sahifasini (docs/index.html) generatsiya qilish
   */
  generateStaticReport() {
    const allStats = db.getAllStats(30); // Oxirgi 30 kun statistikasi
    const today = db.getDailyStats();

    // Jami hisob-kitoblar
    let totalQueued = 0;
    let totalPrinted = 0;
    let totalSaved = 0;
    let totalDisks = 0;

    for (const s of allStats) {
      totalQueued += s.films_queued || 0;
      totalPrinted += s.films_printed || 0;
      totalSaved += s.films_saved || 0;
      totalDisks += s.disks_burned || 0;
    }

    const reportData = {
      generatedAt: new Date().toISOString(),
      today,
      totals: { totalQueued, totalPrinted, totalSaved, totalDisks },
      history: allStats
    };

    // JSON ma'lumotlarini saqlash
    const jsonPath = path.join(config.paths.docs, 'report_data.json');
    fs.writeFileSync(jsonPath, JSON.stringify(reportData, null, 2), 'utf-8');

    // Chiroyli HTML dashboard generatsiya qilish (GitHub Pages uchun)
    const htmlContent = `<!DOCTYPE html>
<html lang="uz">
<head>
  <meta charset="UTF-8">
  <title>MRT Radiologiya Hisobotlari — Onkologiya Markazi</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    body { background-color: #0b1120; color: #f1f5f9; font-family: system-ui, -apple-system, sans-serif; }
  </style>
</head>
<body class="min-h-screen p-4 md:p-8">
  <div class="max-w-6xl mx-auto space-y-6">
    <!-- Header -->
    <header class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3">
          <span class="p-3 bg-cyan-500/10 text-cyan-400 rounded-xl text-2xl"><i class="fa-solid fa-hospital"></i></span>
          <div>
            <h1 class="text-xl md:text-2xl font-bold tracking-tight text-white">Respublika Onkologiya Markazi</h1>
            <p class="text-slate-400 text-sm">Siemens Altea MRT, Fuji DryPix 2000 & 6-Diskovod Tizimi Hisoboti</p>
          </div>
        </div>
      </div>
      <div class="text-right">
        <span class="inline-flex items-center gap-2 px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs rounded-full font-medium">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> Jonli Hisobot
        </span>
        <div class="text-xs text-slate-500 mt-1">Yangilandi: ${dayjs().format('DD.MM.YYYY HH:mm')}</div>
      </div>
    </header>

    <!-- Asosiy Ko'rsatkichlar (KPI Cards) -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-slate-900/80 border border-slate-800 p-5 rounded-2xl">
        <div class="flex justify-between items-center text-slate-400 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Bugungi Plonkalar</span>
          <i class="fa-solid fa-film text-cyan-400"></i>
        </div>
        <div class="text-3xl font-extrabold text-white">${today.films_queued || 0}</div>
        <div class="text-xs text-slate-400 mt-1">Siemens Altea yuborgan</div>
      </div>

      <div class="bg-slate-900/80 border border-slate-800 p-5 rounded-2xl">
        <div class="flex justify-between items-center text-slate-400 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Chop Etildi</span>
          <i class="fa-solid fa-print text-indigo-400"></i>
        </div>
        <div class="text-3xl font-extrabold text-indigo-400">${today.films_printed || 0}</div>
        <div class="text-xs text-slate-400 mt-1">Fuji DryPix 2000 ga chiqqan</div>
      </div>

      <div class="bg-slate-900/80 border border-slate-800 p-5 rounded-2xl">
        <div class="flex justify-between items-center text-slate-400 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Tejab Qolindi</span>
          <i class="fa-solid fa-shield-halved text-emerald-400"></i>
        </div>
        <div class="text-3xl font-extrabold text-emerald-400">${today.films_saved || 0}</div>
        <div class="text-xs text-slate-400 mt-1">Ortiqcha xarajat oldi olindi</div>
      </div>

      <div class="bg-slate-900/80 border border-slate-800 p-5 rounded-2xl">
        <div class="flex justify-between items-center text-slate-400 mb-2">
          <span class="text-xs font-semibold uppercase tracking-wider">Yozilgan Disklar</span>
          <i class="fa-solid fa-compact-disc text-amber-400"></i>
        </div>
        <div class="text-3xl font-extrabold text-amber-400">${today.disks_burned || 0}</div>
        <div class="text-xs text-slate-400 mt-1">6 ta diskovod orqali</div>
      </div>
    </div>

    <!-- Tarixiy Jadval -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
      <div class="p-5 border-b border-slate-800 flex justify-between items-center">
        <h2 class="font-bold text-white text-base">📊 Oxirgi Kunlar Dinamikasi</h2>
        <span class="text-xs text-slate-400">${allStats.length} kunlik ma'lumot</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm text-slate-300">
          <thead class="bg-slate-800/50 text-xs uppercase text-slate-400 font-semibold">
            <tr>
              <th class="p-4">Sana</th>
              <th class="p-4">Siemens Plonkalari</th>
              <th class="p-4">DryPix 2000 Chop Etilgan</th>
              <th class="p-4">Tejab Qolingan Plonka</th>
              <th class="p-4">Yozilgan CD/DVD</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800/60">
            ${allStats.map(row => `
              <tr class="hover:bg-slate-800/30 transition-colors">
                <td class="p-4 font-mono font-medium text-white">${row.date}</td>
                <td class="p-4 text-cyan-400 font-semibold">${row.films_queued}</td>
                <td class="p-4 text-indigo-400 font-semibold">${row.films_printed}</td>
                <td class="p-4 text-emerald-400 font-semibold">${row.films_saved}</td>
                <td class="p-4 text-amber-400 font-semibold">${row.disks_burned}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Footer -->
    <footer class="text-center text-xs text-slate-500 py-4">
      Respublika Onkologiya Markazi Radiodiagnostika Bo'limi &bull; GitHub Pages Orqali Xavfsiz Xosting
    </footer>
  </div>
</body>
</html>`;

    const htmlPath = path.join(config.paths.docs, 'index.html');
    fs.writeFileSync(htmlPath, htmlContent, 'utf-8');
    return { htmlPath, jsonPath, reportData };
  }

  /**
   * Hisobotni GitHub repozitoriyga push qilish
   */
  async syncToGitHub() {
    this.generateStaticReport();

    return new Promise((resolve) => {
      const gitCmd = `git -C "${config.rootDir}" add docs/ && git -C "${config.rootDir}" commit -m "Auto-report: ${dayjs().format('YYYY-MM-DD HH:mm')}" && git -C "${config.rootDir}" push origin main`;

      exec(gitCmd, (error, stdout, stderr) => {
        if (error) {
          console.warn('[ReportSync] GitHubga push qilishda ogohlantirish (Internet yo\'q yoki git kalit o\'rnatilmagan):', error.message);
          return resolve({ success: false, error: error.message });
        }
        console.log('[ReportSync] Hisobot muvaffaqiyatli GitHubga yuklandi!');
        resolve({ success: true, stdout });
      });
    });
  }
}

const reportSync = new ReportSync();

module.exports = reportSync;
