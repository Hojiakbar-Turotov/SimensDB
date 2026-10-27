const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const rootDir = path.resolve(__dirname, '..');

module.exports = {
  rootDir,
  server: {
    port: parseInt(process.env.PORT, 10) || 3000,
    host: process.env.HOST || '0.0.0.0'
  },
  dicomScp: {
    port: parseInt(process.env.DICOM_SCP_PORT, 10) || 5104,
    aeTitle: process.env.DICOM_SCP_AET || 'ALTEA_SPOOLER'
  },
  fujiPrinter: {
    ip: process.env.FUJI_PRINTER_IP || '192.168.1.20',
    port: parseInt(process.env.FUJI_PRINTER_PORT, 10) || 104,
    aeTitle: process.env.FUJI_PRINTER_AET || 'DRYPIX2000'
  },
  pacs: {
    ip: process.env.PACS_IP || '192.168.150.111',
    port: parseInt(process.env.PACS_PORT, 10) || 104,
    aeTitle: process.env.PACS_AET || 'CENTRAL_PACS'
  },
  karmed: {
    lanHost: process.env.KARMED_LAN_HOST || '192.168.150.111',
    wanHost: process.env.KARMED_WAN_HOST || '213.230.91.59',
    port: parseInt(process.env.KARMED_PORT, 10) || 2025,
    keysPath: path.join(rootDir, 'keys.json')
  },
  paths: {
    db: path.join(rootDir, 'storage', 'data', 'print_spooler.db'),
    previews: path.join(rootDir, 'storage', 'previews'),
    spool: path.join(rootDir, 'storage', 'spool'),
    tempBurn: path.join(rootDir, 'storage', 'temp_burn'),
    docs: path.join(rootDir, 'docs')
  },
  github: {
    autoSync: process.env.GITHUB_AUTO_SYNC === 'true',
    intervalMins: parseInt(process.env.GITHUB_SYNC_INTERVAL_MINS, 10) || 60
  }
};
