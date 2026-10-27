/**
 * app.js - Siemens Altea & Fuji DryPix 2000 Spooler Client Application
 */

const socket = io();

let currentJobs = [];
let currentFilter = 'ALL';
let activeModalJob = null;

// DOM Elements
const statQueued = document.getElementById('statQueued');
const statPrinted = document.getElementById('statPrinted');
const statSaved = document.getElementById('statSaved');
const statBurned = document.getElementById('statBurned');
const drivesGrid = document.getElementById('drivesGrid');
const jobsContainer = document.getElementById('jobsContainer');
const jobsCountBadge = document.getElementById('jobsCountBadge');
const statusBadge = document.getElementById('statusBadge');
const btnSimulateFilm = document.getElementById('btnSimulateFilm');
const btnGitSync = document.getElementById('btnGitSync');

// Modal Elements
const previewModal = document.getElementById('previewModal');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const modalPreviewImg = document.getElementById('modalPreviewImg');
const modalPatientName = document.getElementById('modalPatientName');
const modalPatientInfo = document.getElementById('modalPatientInfo');
const modalPrintJobBtn = document.getElementById('modalPrintJobBtn');
const modalCancelJobBtn = document.getElementById('modalCancelJobBtn');

// --- Socket.io Listeners ---
socket.on('connect', () => {
  statusBadge.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium';
  statusBadge.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span><span>Lokal Tarmoq Faol</span>';
  showToast('Lokal serverga ulandi', 'success');
});

socket.on('disconnect', () => {
  statusBadge.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-medium';
  statusBadge.innerHTML = '<span class="w-2 h-2 rounded-full bg-rose-400"></span><span>Aloqa Uzildi</span>';
  showToast('Server bilan aloqa uzildi!', 'error');
});

socket.on('STATS_UPDATED', (stats) => {
  if (!stats) return;
  statQueued.textContent = stats.films_queued || 0;
  statPrinted.textContent = stats.films_printed || 0;
  statSaved.textContent = stats.films_saved || 0;
  statBurned.textContent = stats.disks_burned || 0;
});

socket.on('DRIVES_UPDATED', (drives) => {
  renderDrives(drives);
});

socket.on('DVD_PROGRESS', ({ jobId, progress, status }) => {
  const progressBar = document.getElementById(`drive-progress-${jobId}`);
  if (progressBar) {
    progressBar.style.width = `${progress}%`;
  }
  const statusEl = document.getElementById(`drive-status-${jobId}`);
  if (statusEl) {
    statusEl.textContent = `${status} (${progress}%)`;
  }
});

socket.on('RECENT_JOBS', (jobs) => {
  currentJobs = jobs || [];
  renderJobs();
});

socket.on('NEW_PRINT_JOB', (job) => {
  currentJobs.unshift(job);
  renderJobs();
  showToast(`Siemens'dan yangi plonka: ${job.patient_name}`, 'info');
});

socket.on('PRINT_JOB_STATUS', ({ jobId, status }) => {
  const job = currentJobs.find(j => j.id === jobId);
  if (job) {
    job.status = status;
    renderJobs();
  }
});

// --- Drayvlarni Render Qilish (6 ta drayv) ---
function renderDrives(drives) {
  if (!drivesGrid) return;
  drivesGrid.innerHTML = '';

  drives.forEach((drive) => {
    const isBurning = drive.status === 'BURNING';
    const isOpen = drive.status === 'OPEN';

    let badgeClass = 'bg-slate-800 text-slate-300';
    let statusText = 'Bo\'sh (Tayyor)';
    let iconClass = 'fa-compact-disc text-slate-400';

    if (isBurning) {
      badgeClass = 'bg-amber-500/20 text-amber-400 border border-amber-500/30';
      statusText = 'Yozilmoqda...';
      iconClass = 'fa-compact-disc text-amber-400 animate-spin';
    } else if (isOpen) {
      badgeClass = 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30';
      statusText = 'Eshik ochiq';
      iconClass = 'fa-eject text-indigo-400';
    }

    const driveCard = document.createElement('div');
    driveCard.className = `bg-slate-950 border border-slate-800 p-3 rounded-xl flex flex-col justify-between ${isBurning ? 'border-amber-500/40 shadow-md shadow-amber-500/10' : ''}`;
    driveCard.innerHTML = `
      <div>
        <div class="flex justify-between items-center mb-2">
          <span class="text-sm font-bold text-white font-mono">${drive.drive_letter}</span>
          <i class="fa-solid ${iconClass} text-sm"></i>
        </div>
        <div class="text-[11px] font-medium px-2 py-0.5 rounded ${badgeClass} inline-block mb-2" id="drive-status-${drive.current_job_id || drive.drive_letter}">
          ${statusText}
        </div>
      </div>

      <div class="space-y-2 mt-2">
        ${isBurning ? `
          <div class="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div id="drive-progress-${drive.current_job_id}" class="bg-amber-400 h-1.5 transition-all duration-300" style="width: 30%"></div>
          </div>
        ` : ''}

        <button onclick="ejectDriveLetter('${drive.drive_letter}')" class="w-full text-center py-1 bg-slate-800/80 hover:bg-slate-700 text-slate-300 text-[11px] font-semibold rounded-lg transition flex items-center justify-center gap-1">
          <i class="fa-solid fa-eject text-[10px]"></i>
          <span>Ochish</span>
        </button>
      </div>
    `;
    drivesGrid.appendChild(driveCard);
  });
}

// --- Plonkalarni Render Qilish ---
function renderJobs() {
  if (!jobsContainer) return;
  jobsContainer.innerHTML = '';

  const filtered = currentJobs.filter(job => {
    if (currentFilter === 'ALL') return true;
    return job.status === currentFilter;
  });

  jobsCountBadge.textContent = `${filtered.length} ta`;

  if (filtered.length === 0) {
    jobsContainer.innerHTML = `
      <div class="col-span-full py-12 text-center text-slate-500">
        <i class="fa-solid fa-film text-4xl mb-3 text-slate-600 block"></i>
        <p class="text-sm">Hozirda hech qanday plonka so'rovi yo'q</p>
        <p class="text-xs text-slate-600 mt-1">Siemens Altea apparatidan chop etish berilganda bu yerda avtomatik ko'rinadi</p>
      </div>
    `;
    return;
  }

  filtered.forEach(job => {
    const isQueued = job.status === 'QUEUED';
    const isPrinted = job.status === 'PRINTED';
    const isCancelled = job.status === 'CANCELLED';

    let badgeClass = 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
    let statusText = 'Kutmoqda (Tekshirish)';
    if (isPrinted) {
      badgeClass = 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20';
      statusText = 'DryPix 2000 ga Chiqdi';
    } else if (isCancelled) {
      badgeClass = 'bg-rose-500/10 text-rose-400 border border-rose-500/20';
      statusText = 'Bekor qilingan (Tejaldi)';
    }

    const card = document.createElement('div');
    card.className = 'job-card bg-slate-950 border border-slate-800/90 rounded-2xl p-4 flex flex-col justify-between shadow-sm';
    card.innerHTML = `
      <div>
        <!-- Card Header -->
        <div class="flex justify-between items-start gap-2 mb-3">
          <div>
            <div class="text-xs font-mono text-cyan-400 font-semibold mb-0.5">ID: ${job.patient_id}</div>
            <h3 class="font-bold text-sm text-white line-clamp-1">${job.patient_name}</h3>
          </div>
          <span class="text-[11px] font-medium px-2 py-0.5 rounded-full ${badgeClass} shrink-0">
            ${statusText}
          </span>
        </div>

        <!-- Preview Image Thumbnail -->
        <div class="relative bg-slate-900 rounded-xl overflow-hidden mb-3 group cursor-pointer border border-slate-800/80" onclick="openPreviewModal(${job.id})">
          <img src="${job.preview_image || '/storage/previews/preview_sample.png'}" alt="Preview" class="w-full h-36 object-contain p-2 group-hover:scale-105 transition duration-200">
          <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition gap-2 text-white text-xs font-semibold">
            <i class="fa-solid fa-magnifying-glass-plus text-base"></i>
            <span>Kattalashtirish</span>
          </div>
        </div>

        <!-- Meta Details -->
        <div class="grid grid-cols-2 gap-1 text-[11px] text-slate-400 mb-4 bg-slate-900/60 p-2.5 rounded-xl border border-slate-800/50">
          <div><b>Format:</b> ${job.film_format || '2x3'}</div>
          <div><b>O'lcham:</b> ${job.film_size || '14x17'}</div>
          <div><b>Sana:</b> ${job.study_date || '-'}</div>
          <div><b>Protokol:</b> ${job.protocol_no || '-'}</div>
          ${job.creatinine_val ? `<div class="col-span-2 text-emerald-400"><b>Kreatinin:</b> ${job.creatinine_val}</div>` : ''}
        </div>
      </div>

      <!-- Action Buttons -->
      <div class="flex items-center gap-2 pt-2 border-t border-slate-900">
        ${isQueued ? `
          <button onclick="printJob(${job.id})" class="flex-1 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-bold transition flex items-center justify-center gap-1.5 shadow-md shadow-indigo-600/20">
            <i class="fa-solid fa-print"></i>
            <span>Chop Etish</span>
          </button>
          <button onclick="burnJob(${job.id})" class="p-2 bg-slate-800 hover:bg-slate-700 text-amber-400 rounded-xl text-xs font-bold transition flex items-center justify-center" title="CD/DVD ga yozish">
            <i class="fa-solid fa-compact-disc text-sm"></i>
          </button>
          <button onclick="cancelJob(${job.id})" class="p-2 bg-slate-800 hover:bg-rose-500/20 text-rose-400 rounded-xl text-xs font-bold transition flex items-center justify-center" title="Bekor qilish (Plonkani tejash)">
            <i class="fa-solid fa-trash-can text-sm"></i>
          </button>
        ` : `
          <button onclick="burnJob(${job.id})" class="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-amber-400 rounded-xl text-xs font-bold transition flex items-center justify-center gap-1.5">
            <i class="fa-solid fa-compact-disc"></i>
            <span>Diskka Yozish</span>
          </button>
          <button onclick="printJob(${job.id})" class="py-2 px-3 bg-slate-800 hover:bg-indigo-600 text-slate-300 hover:text-white rounded-xl text-xs font-bold transition flex items-center justify-center gap-1" title="Qayta chop etish">
            <i class="fa-solid fa-rotate-right"></i>
          </button>
        `}
      </div>
    `;
    jobsContainer.appendChild(card);
  });
}

// --- Action Handlers ---
async function printJob(jobId) {
  try {
    showToast('Fujifilm DryPix 2000 ga yuborilmoqda...', 'info');
    const res = await fetch(`/api/print-jobs/${jobId}/print`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('DryPix 2000 printerida chop etildi!', 'success');
      if (previewModal && !previewModal.classList.contains('hidden')) {
        closeModal();
      }
    } else {
      showToast(`Xato: ${data.error}`, 'error');
    }
  } catch (e) {
    showToast(`Ulanishda xato: ${e.message}`, 'error');
  }
}

async function cancelJob(jobId) {
  if (!confirm("Haqiqatan ham bu plonkani bekor qilib, xarajatni tejamoqchimisiz?")) return;
  try {
    const res = await fetch(`/api/print-jobs/${jobId}/cancel`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('Plonka bekor qilindi (Xarajat tejab qolindi)', 'success');
      if (previewModal && !previewModal.classList.contains('hidden')) {
        closeModal();
      }
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function burnJob(jobId) {
  const job = currentJobs.find(j => j.id === jobId);
  if (!job) return;

  try {
    showToast(`${job.patient_name} uchun diskovod ajratilmoqda...`, 'info');
    const res = await fetch('/api/burn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_id: job.patient_id,
        patient_name: job.patient_name,
        protocol_no: job.protocol_no
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Diskka yozish boshlandi (Drayv: ${data.job.drive_letter})`, 'success');
    } else {
      showToast(`Xato: ${data.error}`, 'error');
    }
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function ejectDriveLetter(driveLetter) {
  try {
    await fetch(`/api/drives/${encodeURIComponent(driveLetter)}/eject`, { method: 'POST' });
    showToast(`${driveLetter} drayvi chiqarildi`, 'info');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

// Modal ochish
function openPreviewModal(jobId) {
  const job = currentJobs.find(j => j.id === jobId);
  if (!job) return;

  activeModalJob = job;
  modalPatientName.textContent = job.patient_name;
  modalPatientInfo.textContent = `ID: ${job.patient_id} | Format: ${job.film_format} | Sana: ${job.study_date}`;
  modalPreviewImg.src = job.preview_image || '';

  modalPrintJobBtn.onclick = () => printJob(job.id);
  modalCancelJobBtn.onclick = () => cancelJob(job.id);

  previewModal.classList.remove('hidden');
}

function closeModal() {
  previewModal.classList.add('hidden');
  activeModalJob = null;
}

modalCloseBtn.onclick = closeModal;
previewModal.onclick = (e) => {
  if (e.target === previewModal) closeModal();
};

// Filter tugmalari
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('.filter-btn').forEach(b => {
      b.className = 'filter-btn px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700 font-medium';
    });
    btn.className = 'filter-btn active px-3 py-1.5 rounded-lg bg-cyan-600 text-white font-medium';
    currentFilter = btn.dataset.filter;
    renderJobs();
  };
});

// Test plonka yaratish
btnSimulateFilm.onclick = async () => {
  try {
    btnSimulateFilm.disabled = true;
    showToast('Siemens Altea signali simulyatsiya qilinmoqda...', 'info');
    await fetch('/api/print-jobs/simulate', { method: 'POST' });
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    btnSimulateFilm.disabled = false;
  }
};

// GitHubga hisobot yuklash
btnGitSync.onclick = async () => {
  try {
    btnGitSync.disabled = true;
    btnGitSync.innerHTML = '<i class="fa-solid fa-spinner animate-spin"></i><span>Yuklanmoqda...</span>';
    const res = await fetch('/api/github/sync', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('Hisobot GitHubga muvaffaqiyatli yuklandi!', 'success');
    } else {
      showToast(`GitHub ogohlantirish: ${data.error || 'Internet uzilgan bo\'lishi mumkin'}`, 'info');
    }
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    btnGitSync.disabled = false;
    btnGitSync.innerHTML = '<i class="fa-brands fa-github text-sm"></i><span>GitHubga Hisobot</span>';
  }
};

// Toast Xabarnoma
function showToast(msg, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  let bg = 'bg-slate-800 border-slate-700 text-slate-100';
  if (type === 'success') bg = 'bg-emerald-950 border-emerald-800 text-emerald-200';
  if (type === 'error') bg = 'bg-rose-950 border-rose-800 text-rose-200';
  if (type === 'info') bg = 'bg-cyan-950 border-cyan-800 text-cyan-200';

  toast.className = `${bg} border px-4 py-2.5 rounded-xl shadow-xl text-xs font-semibold flex items-center gap-2 pointer-events-auto transition duration-300`;
  toast.innerHTML = `<span>${msg}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
