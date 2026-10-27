/**
 * KarmedClient.js - Karmed LBYS/RBYS bilan integratsiya klienti
 * Respublika Onkologiya va Radiologiya Ilmiy-Amaliy Tibbiyot Markazi
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const config = require('../../config/config');

class KarmedClient {
  constructor(options = {}) {
    this.hosts = [config.karmed.lanHost, config.karmed.wanHost];
    this.port = config.karmed.port;
    this.username = 'R5';
    this.password = '17720';
    this.loadKeys();

    this.token = null;
    this.cookie = '';
    this.activeHost = this.hosts[0];
    this.isLoggingIn = false;
  }

  loadKeys() {
    try {
      if (fs.existsSync(config.karmed.keysPath)) {
        const raw = fs.readFileSync(config.karmed.keysPath, 'utf-8');
        const parsed = JSON.parse(raw);
        if (parsed.username) this.username = parsed.username;
        if (parsed.password) this.password = parsed.password;
      }
    } catch (e) {
      console.warn('[KarmedClient] keys.json ni o\'qishda ogohlantirish:', e.message);
    }
  }

  _rawRequest(host, pathStr, method, headers, postData = null, timeoutMs = 25000) {
    return new Promise((resolve, reject) => {
      const req = http.request({
        hostname: host,
        port: this.port,
        path: pathStr,
        method: method,
        headers: headers
      }, res => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          // Tokenni tutib olish (Harvesting)
          const m = data.match(/App\.hdnKrmdLoginBilgi\.setValue\([\\\"\']*([A-Za-z0-9%_+\-\/=]{40,})[\\\"\']*\)/);
          if (m && m[1]) this.token = m[1];

          // Cookie-larni saqlash
          if (res.headers['set-cookie']) {
            const newCookies = res.headers['set-cookie'].map(c => c.split(';')[0]).join('; ');
            this.cookie = this.cookie ? (this.cookie + '; ' + newCookies) : newCookies;
          }

          resolve({ statusCode: res.statusCode, headers: res.headers, body: data });
        });
      });

      req.on('error', reject);
      req.setTimeout(timeoutMs, () => {
        req.destroy(new Error(`Timeout (${timeoutMs}ms) host: ${host}`));
      });
      if (postData) req.write(postData);
      req.end();
    });
  }

  safeParse(str) {
    if (!str) return null;
    try {
      return JSON.parse(str);
    } catch (e) {
      try {
        const clean = str
          .replace(/new Date\(([-+]?\d+)\)/g, (m, p) => `"${new Date(parseInt(p, 10)).toISOString()}"`)
          .replace(/new Date\([^)]+\)/g, '"2026-01-01T00:00:00.000Z"')
          .replace(/\\"/g, '"');
        return JSON.parse(clean);
      } catch (e2) {
        return null;
      }
    }
  }

  async login() {
    if (this.isLoggingIn) return;
    this.isLoggingIn = true;
    this.loadKeys();

    try {
      for (const host of this.hosts) {
        try {
          console.log(`[KarmedClient] Karmedga ulanilmoqda: http://${host}:${this.port} (${this.username})...`);

          // 1. GET Login.aspx
          const r1 = await this._rawRequest(host, `/Login/Login.aspx?returnUrl=http://${host}:${this.port}/Radiology/Rbys.aspx`, 'GET', {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
          });
          const m1 = r1.body.match(/value='([^']+)'/);
          if (!m1) continue;

          // 2. POST /Karmed/Default.aspx
          const r2 = await this._rawRequest(host, '/Karmed/Default.aspx', 'POST', {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': this.cookie,
            'User-Agent': 'Mozilla/5.0'
          }, '=' + m1[1]);
          const m2 = r2.body.match(/name='token'\s+value='([^']+)'/);
          if (!m2) continue;
          const tokenVal = m2[1];

          // 3. POST Login.aspx (Token bilan)
          const r3 = await this._rawRequest(host, `/Login/Login.aspx?returnUrl=http://${host}:${this.port}/Radiology/Rbys.aspx`, 'POST', {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': this.cookie,
            'User-Agent': 'Mozilla/5.0'
          }, 'token=' + encodeURIComponent(tokenVal));
          const mIndex = r3.body.match(/id="hdnDataIndexInfo"[^>]*value="([^"]+)"/);
          const dataIndex = mIndex ? mIndex[1] : '';

          // 4. POST MakeLogin
          const p = new URLSearchParams();
          p.set('submitDirectEventConfig', JSON.stringify({ config: { extraParams: { dataIndex: null } } }));
          p.set('HdnBaseYazdirmaTuru', '-1');
          p.set('__VIEWSTATEGENERATOR', '5E7FB4E4');
          p.set('hdnDataIndexInfo', decodeURIComponent(dataIndex));
          p.set('hdToken', tokenVal);
          p.set('hdReferer', host);
          p.set('hdCaptchaVisible', 'False');
          p.set('CmbCulture', 'uz-UZ');
          p.set('txtUsername', this.username);
          p.set('txtPassword', this.password);
          p.set('__EVENTTARGET', 'ResLogin');
          p.set('__EVENTARGUMENT', '-|public|MakeLogin');

          const r4 = await this._rawRequest(host, '/Login/Login.aspx?action=MakeLogin', 'POST', {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Ext-Net': 'delta=true',
            'action': 'MakeLogin',
            'X-Requested-With': 'XMLHttpRequest',
            'Cookie': this.cookie
          }, p.toString());

          const mUser = r4.body.match(/name='userInfo'\s+value='([^']+)'/);
          if (!mUser) throw new Error("Login yoki parol noto'g'ri!");

          // 5. POST /Radiology/Rbys.aspx
          const r5 = await this._rawRequest(host, '/Radiology/Rbys.aspx', 'POST', {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': this.cookie
          }, 'userInfo=' + encodeURIComponent(mUser[1]));

          // 6. extnet-init-js
          const mScript = r5.body.match(/src="(\/Radiology\/extnet\/extnet-init-js\/ext\.axd\?[^"]+)"/);
          if (mScript) {
            const r6 = await this._rawRequest(host, mScript[1], 'GET', { 'Cookie': this.cookie });
            const mTok = r6.body.match(/id:"hdnKrmdLoginBilgi"[^}]*value:"([^"]+)"/);
            if (mTok && mTok[1]) this.token = mTok[1];
          }

          this.activeHost = host;
          console.log(`[KarmedClient] Karmedga muvaffaqiyatli ulandi! Host: ${this.activeHost}`);
          return true;
        } catch (err) {
          console.warn(`[KarmedClient] ${host} orqali ulanishda xatolik:`, err.message);
        }
      }
      throw new Error("Karmed serverlariga ulanib bo'lmadi!");
    } finally {
      this.isLoggingIn = false;
    }
  }

  async searchPatients(searchVal = '', startDate = '', endDate = '') {
    try {
      if (!this.token) await this.login();

      const todayFormatted = new Date().toLocaleDateString('ru-RU'); // DD.MM.YYYY
      const sDate = startDate || todayFormatted;
      const eDate = endDate || todayFormatted;

      const params = new URLSearchParams();
      params.set('submitDirectEventConfig', JSON.stringify({ config: { extraParams: { aDosyaDurumu: null, aHizliAra: false } } }));
      params.set('cbYil', '2026');
      params.set('BaslangicDt', sDate);
      params.set('BitisDt', eDate);
      params.set('cbBolum', 'MRT'); // MRT bo'limi
      params.set('tfHizliAramaDeger', searchVal);
      params.set('cbKayitSayisiSecim', '500');
      params.set('btnTumu_Pressed', 'true');
      params.set('hdnKrmdLoginBilgi', this.token);
      params.set('__EVENTTARGET', 'ctl00$ResourceManagerX');
      params.set('__EVENTARGUMENT', '-|public|HastaSorgula');

      const res = await this._rawRequest(this.activeHost, '/Radiology/Rbys.aspx?action=HastaSorgula', 'POST', {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Ext-Net': 'delta=true',
        'action': 'HastaSorgula',
        'X-Requested-With': 'XMLHttpRequest',
        'Cookie': this.cookie
      }, params.toString());

      if (res.body.includes('/Login/Login.aspx') || !res.body.includes('grdHastalarStore')) {
        console.log('[KarmedClient] Sessiya yangilanmoqda...');
        await this.login();
        return await this.searchPatients(searchVal, startDate, endDate);
      }

      const match = res.body.match(/App\.grdHastalarStore\.proxy\.data\s*=\s*(\[.*?\]);/s);
      return match ? (this.safeParse(match[1]) || []) : [];
    } catch (err) {
      console.warn('[KarmedClient] Qidiruvda xatolik:', err.message);
      return [];
    }
  }

  async getPatientDetailsByKimlik(kimlikId) {
    try {
      if (!this.token) await this.login();

      // Qidirib topamiz
      const patients = await this.searchPatients(String(kimlikId));
      const p = patients.find(x => String(x.KimlikNo) === String(kimlikId) || String(x.Id) === String(kimlikId));
      if (!p) return null;

      // Tashxis va xizmatlarni olish (TaniHizmetBilgisiGetir)
      const params = new URLSearchParams();
      params.set('submitDirectEventConfig', JSON.stringify({
        config: {
          extraParams: {
            aLabDosyaId: p.Id || p.LabDosyaId,
            aOnkayitSiraNo: p.OnkayitSiraNo || 0,
            aYatPol: p.YatPol || 'P',
            aProtokolNo: p.ProtokolNo || 0,
            aKimlikId: p.KimlikNo || kimlikId,
            aHastaAdi: p.AdSoyad || p.HastaAdi || '',
            aBolumId: 1, // MRT
            mrrsProtokolNo: null
          }
        }
      }));
      params.set('hdnKrmdLoginBilgi', this.token);
      params.set('__EVENTTARGET', 'ctl00$ResourceManagerX');
      params.set('__EVENTARGUMENT', '-|public|TaniHizmetBilgisiGetir');

      const res = await this._rawRequest(this.activeHost, '/Radiology/Rbys.aspx?action=TaniHizmetBilgisiGetir', 'POST', {
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Ext-Net': 'delta=true',
        'action': 'TaniHizmetBilgisiGetir',
        'X-Requested-With': 'XMLHttpRequest',
        'Cookie': this.cookie
      }, params.toString());

      let diagnosis = '';
      const mDiag = res.body.match(/lblTanilar\.setText\((.*?)\);/);
      if (mDiag && mDiag[1]) {
        diagnosis = mDiag[1].split(',')[0].replace(/^"|"$/g, '').replace(/\\"/g, '"').trim();
      }

      return {
        patientId: String(p.KimlikNo || kimlikId),
        patientName: p.AdSoyad || p.HastaAdi,
        protocolNo: String(p.ProtokolNo || ''),
        diagnosis: diagnosis,
        department: p.ServisAdi || '',
        doctor: p.DoktorAdi || p.DosyaDoktoru || '',
        date: p.KayitTarihi || ''
      };
    } catch (e) {
      console.warn('[KarmedClient] Bemor tafsilotlarini olishda xato:', e.message);
      return null;
    }
  }
}

// Singleton instansiya
const karmedClient = new KarmedClient();

module.exports = karmedClient;
