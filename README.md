# 🏥 Siemens Altea DICOM Spooler & FUJIFILM DRYPIX Lite (DRYPIX2) Driver Server

**Respublika Onkologiya va Radiologiya Ilmiy-Amaliy Tibbiyot Markazi**  
Magnit-Rezonans Tomografiya (MRT) Bo'limi uchun ishlab chiqilgan maxsus oraliq server.

---

## 📌 Tizimning Vazifasi va Ishlash Mexanizmi

1. **Siemens MRT apparatidan so'rovlarni qabul qilish**:
   - Siemens Magnetom Altea konsolidan pechat qilish so'rovi ushbu server kompyuterning **`10.34.14.33`** IP manziliga **`1005`** portida yuboriladi.
   - Server DICOM Print SCP sifatida so'rovni to'liq qabul qiladi (`C-ECHO`, `N-GET`, `N-CREATE`, `N-SET`, `N-ACTION`).
2. **So'rovni to'liq saqlash va arxivlash**:
   - Har bir kadrning xom piksel ma'lumotlari mustaqil standart **DICOM (`.dcm`)** fayllari sifatida saqlanadi.
   - Har bir kadr yuqori sifatli **PNG** formatida render qilinadi.
   - Butun 14x17 dyuymli fizik rentgen/MRT plonkasi simulyatsiyasi (Header bar, bemor ma'lumotlari va kataklar to'ri bilan) **`preview_sheet.png`** shaklida arxivlanadi.
   - Barcha ma'lumotlar **`metadata.json`** va **SQLite (`print_spooler.db`)** bazasiga qayd etiladi.
3. **FUJIFILM DRYPIX Lite (DRYPIX2) printeriga avtomatik yuborish**:
   - Saqlangan plonka DICOM Print SCU orqali **`10.34.14.12:104`** manzilidagi termoprinterga yuboriladi.
   - Veb paneldan turib avto-chop etishni yoqish/o'chirish va xohlagan plonkani istalgan vaqtda qayta chop etish (Re-print) mumkin.
4. **Veb Boshqaruv Paneli (Port 3000)**:
   - Brauzer orqali `http://10.34.14.33:3000` yoki `http://localhost:3000` manzilida jonli monitoring.

---

## 🚀 Ishga Tushirish (Bir Klik Bilan)

Papka ichidagi **`Ishga_Tushirish.bat`** faylini ikki marta bosing yoki to'g'ridan-to'g'ri:
👉 **`Siemens_Fuji_DICOM_Print_Server.exe`** faylini ishga tushiring!

Brauzeringizda avtomatik boshqaruv paneli ochiladi:  
🌐 **`http://localhost:3000`**

---

## ⚙️ Qurilmalar Tarmoq Sozlamalari

### 1. Oraliq Server Kompyuter (Ushbu kompyuter):
* **IP Manzili**: `10.34.14.33`
* **DICOM Qabul Porti**: `1005`
* **Veb Boshqaruv Porti**: `3000`
* **Called AE Title**: `DRYPIX2` (har qanday AE Title-ni qabul qiladi)

### 2. Siemens Magnetom Altea Konsolida Sozlash:
* **Node Type**: Camera / DICOM Print SCP
* **IP Address**: `10.34.14.33`
* **Port**: `1005`
* **Called AE Title**: `DRYPIX2` (yoki `ALTEA_SPOOLER`)
* **Calling AE Title**: `ALTEA_MRT1` (yoki `MRT1`)

### 3. Fujifilm DryPix Lite Printeri:
* **Printer Modeli**: FUJIFILM DRYPIX Lite
* **IP Manzili**: `10.34.14.12`
* **Port**: `104` (DICOM Basic Grayscale Print Management)
* **Called AE Title**: `DRYPIX2`
* **Calling AE Title**: `MRT1`
* **Web PC-Utility**: `http://10.34.14.12:20051/USER/Login.htm`

---

## 📂 Saqlash va Arxiv Strukturasi

Barcha yuborilgan so'rovlar quyidagi tartibda to'liq saqlanadi:
```
D:\SimensDB\
├── Siemens_Fuji_DICOM_Print_Server.exe   <-- Tayyor mustaqil dastur (.exe)
├── config.json                           <-- Tarmoq va printer sozlamalari
├── Ishga_Tushirish.bat                   <-- Dasturni ishga tushirish tugmasi
└── storage/
    ├── data/
    │   └── print_spooler.db              <-- SQLite jurnali va statistikasi
    └── archive/
        └── YYYY-MM-DD/
            └── YYYYMMDD_HHMMSS_PatientID_Name/
                ├── metadata.json         <-- Barcha bemor va plonka parametrlari
                ├── preview_sheet.png     <-- Yuqori aniqlikdagi to'liq plonka ko'rinishi
                └── images/
                    ├── frame_01.dcm      <-- 1-kadr xom DICOM fayli
                    ├── frame_01.png      <-- 1-kadr tasviri
                    ├── frame_02.dcm
                    ├── frame_02.png
                    └── ...
```
