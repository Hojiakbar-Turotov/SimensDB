# 🏥 Siemens Altea Virtual DICOM Print Spooler, Fujifilm DryPix 2000 Driver & 6-Diskovod Burner Tizimi

**Respublika Onkologiya va Radiologiya Ilmiy-Amaliy Tibbiyot Markazi**  
Magnit-Rezonans Tomografiya (MRT) Bo'limi uchun ishlab chiqilgan.

---

## 📌 Asosiy Imkoniyatlar

1. **Virtual DICOM Print Spooler (Port 5104)**:
   - Siemens Magnetom Altea apparatidan yuborilgan barcha plonkalarni to'g'ridan-to'g'ri printerga yubormasdan keshda yig'adi.
   - Har bir plonkani monitor orqali oldindan yuqori sifatli ko'rish (Preview) imkoniyati.
2. **Fujifilm DryPix 2000 Tanlab Chop Etish**:
   - Faqat operator tasdiqlagan plonkalar haqiqiy termoplonkaga chiqariladi.
   - Natijada plonka behuda sarflanmaydi va katta iqtisodiy tejamkorlik ta'minlanadi.
3. **6 ta Jismoniy CD/DVD Diskovodni Parallel Boshqarish**:
   - Bir vaqtda bir nechta bemor uchun disk yozish (Parallel Burning Queue).
   - Har bir diskka **DICOMDIR**, mustaqil **Portable DICOM Viewer** va `autorun.inf` avtomatik yoziladi.
   - Yozish tugagach diskovod troykasi avtomatik chiqariladi (Auto-Eject).
4. **Karmed LBYS/RBYS Integratsiyasi (`karmed_read.md`)**:
   - Bemor ID si orqali uning to'liq F.I.SH, yo'llanma tashxisi va kontrast MRT uchun muhim **Kreatinin/Mochevina** tahlillari avtomatik yuklanadi.
5. **Lokal Tarmoq & Realtime (Socket.io)**:
   - Tizim 100% internetsiz ishlaydi.
   - Yangi plonkalar va drayvlar holati sahifani yangilamasdan (F5 siz) jonli yangilanadi.
6. **GitHub Pages Masofaviy Hisobot Xostingi**:
   - Kunlik statistika avtomatik `docs/index.html` ga yoziladi va GitHub repozitoriyga push qilinadi.
   - Rahbariyat uydan yoki telefondan turib kunlik ko'rsatkichlarni onlayn ko'ra oladi.

---

## 🚀 Dasturni Ishga Tushirish

### 1-usul: Qulay tugma orqali
Asosiy papkadagi **`Ishga_Tushirish.bat`** faylini ikki marta bosing. Brauzeringizda avtomatik ochiladi:
👉 **`http://localhost:3000`**

### 2-usul: Buyruqlar satri orqali
```bash
npm start
```

---

## ⚙️ Qurilmalar Sozlamalari (DICOM Configuration)

### 1. Siemens Magnetom Altea Konsolida:
* **Node Type**: DICOM Print SCP (Camera / Printer)
* **IP Address**: Oraliq kompyuterning lokal IP si (masalan, `192.168.1.50`)
* **Port**: `5104`
* **AE Title**: `ALTEA_SPOOLER`

### 2. Fujifilm DryPix 2000 Printerida:
* **IP Address**: `192.168.1.20` (yoki `.env` dagi `FUJI_PRINTER_IP`)
* **Port**: `104`
* **AE Title**: `DRYPIX2000`

---

## 📂 Papkalar Strukturasi

```
SimensDB/
├── config/             # Tizim konfiguratsiyasi (config.js)
├── src/
│   ├── db/             # SQLite bazasi (schema.sql, database.js)
│   ├── dicom/          # DICOM Print SCP server va DryPix SCU
│   ├── burner/         # 6-diskovodli drayver va DICOMDIR generator
│   ├── karmed/         # KarmedClient.js (6 bosqichli kirish)
│   ├── github/         # GitHub hisobotlar avtomatik sinxronizatori
│   └── server.js       # Asosiy Express & Socket.io serveri
├── public/             # Web Boshqaruv Paneli (index.html, app.js, style.css)
├── storage/
│   ├── previews/       # Plonkalar yuqori aniqlikdagi rasmlari
│   ├── spool/          # Xom DICOM print buyruqlari
│   ├── temp_burn/      # Diskka yoziladigan vaqtinchalik paketlar
│   └── data/           # print_spooler.db (SQLite fayli)
├── docs/               # GitHub Pages hisoboti (index.html, report_data.json)
├── keys.json           # Karmed kirish parollari (R5 / 17720)
├── .env                # Tarmoq IP va Port sozlamalari
├── package.json
└── Ishga_Tushirish.bat # Bir klik bilan ishga tushirish
```
