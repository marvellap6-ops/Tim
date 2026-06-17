const days = ['MINGGU', 'SENIN', 'SELASA', 'RABU', 'KAMIS', 'JUMAT', 'SABTU'];
const months = ['JAN', 'FEB', 'MAR', 'APR', 'MEI', 'JUN', 'JULI', 'AGU', 'SEP', 'OKT', 'NOV', 'DES'];
const monthsFull = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'];

const times = ['10:30', '13.15', '15.50', '18.45', '21.30'];

let selectedDate = null;
let selectedTime = null;

// Generate 7 dates starting from July 25 2026
const dates = [];
const base = new Date(2026, 6, 25);
for (let i = 0; i < 7; i++) {
  const d = new Date(base);
  d.setDate(base.getDate() + i);
  dates.push(d);
}

const AVAILABLE_DAYS = 2; // hanya 2 hari pertama yang tersedia

// Render date buttons
const dateGrid = document.getElementById('dateGrid');
dates.forEach((d, i) => {
  const btn = document.createElement('button');
  const isAvailable = i < AVAILABLE_DAYS;
  btn.className = 'date-btn' + (isAvailable ? '' : ' disabled');
  btn.innerHTML = `
    <span class="month-label">${months[d.getMonth()]}</span>
    <span class="day-num">${d.getDate()}</span>
    <span class="day-name">${days[d.getDay()]}</span>
  `;
  if (isAvailable) {
    btn.addEventListener('click', () => selectDate(i, btn, d));
  } else {
    btn.disabled = true;
    btn.title = 'Jadwal belum tersedia';
  }
  dateGrid.appendChild(btn);
});

// Render time buttons
const timeGrid = document.getElementById('timeGrid');
times.forEach(t => {
  const btn = document.createElement('button');
  btn.className = 'time-btn';
  btn.textContent = t;
  btn.addEventListener('click', () => selectTime(t, btn));
  timeGrid.appendChild(btn);
});

function selectDate(i, btn, d) {
  document.querySelectorAll('.date-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  selectedDate = d;
  selectedTime = null;

  document.getElementById('sectionTitle').textContent = '1.  Pilih Tanggal & Waktu';
  document.getElementById('timeGrid').style.display = 'flex';
  document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('actionRow').classList.remove('visible');
}

function selectTime(t, btn) {
  document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  selectedTime = t;
  updateActionRow();
}

function updateActionRow() {
  if (!selectedDate || !selectedTime) return;
  const label = `${days[selectedDate.getDay()]}, ${selectedDate.getDate()} ${monthsFull[selectedDate.getMonth()]} ${selectedDate.getFullYear()} ${selectedTime}`;
  document.getElementById('selectedLabel').textContent = label;
  document.getElementById('actionRow').classList.add('visible');
}

function pilihKursi() {
  alert(`Melanjutkan ke pemilihan kursi:\n${document.getElementById('selectedLabel').textContent}`);
}
