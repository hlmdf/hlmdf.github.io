const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { DailyQuota } = require('./daily-quota');

// ===== 可配置项 =====
const PORT = process.env.PORT || 3001;
const MAX_FILE_SIZE = 200 * 1024 * 1024; // 单文件上限 200MB
const EXPIRE_MS = 24 * 60 * 60 * 1000;   // 未取走的文件保留 24 小时
const QUOTA_LIMIT = 100;                 // 同一 IP 每天上传 100 次，下载不限（北京时间）
// ===================

const UPLOAD_DIR = path.join(__dirname, 'uploads');
const USAGE_PATH = path.join(__dirname, 'usage.json');
fs.mkdirSync(UPLOAD_DIR, { recursive: true });

const app = express();
app.use(express.static(path.join(__dirname, 'public')));

const storage = multer.diskStorage({
  destination: UPLOAD_DIR,
  filename: (req, file, cb) => cb(null, crypto.randomBytes(8).toString('hex'))
});
const upload = multer({ storage, limits: { fileSize: MAX_FILE_SIZE } });

const quota = new DailyQuota(USAGE_PATH, QUOTA_LIMIT);

function clientIp(req) {
  let ip = req.socket.remoteAddress || '';
  if (ip.startsWith('::ffff:')) ip = ip.slice(7);
  const loopback = ip === '127.0.0.1' || ip === '::1';
  if (loopback && req.headers['x-forwarded-for']) {
    // The one trusted loopback Nginx hop appends the actual peer last.
    const forwarded = String(req.headers['x-forwarded-for']).split(',').pop().trim();
    if (require('net').isIP(forwarded)) ip = forwarded;
  }
  if (ip === '::1' || ip === '::ffff:127.0.0.1') ip = '127.0.0.1';
  return ip || 'unknown';
}

function quotaInfo(ip) {
  return quota.info(ip);
}

function releaseQuota(req) {
  if (!req._quotaReserved) return;
  req._quotaReserved = false;
  quota.refund(req.clientIp, req._quotaDay);
}

function keepQuota(req) {
  req._quotaReserved = false;
}

function quotaGate(req, res, next) {
  const ip = clientIp(req);
  req.clientIp = ip;
  const reservedDay = quota.reserve(ip);
  if (!reservedDay) {
    return res.status(429).json({ error: '今日上传次数已用完，北京时间零点恢复', quota: quotaInfo(ip) });
  }
  req._quotaReserved = true;
  req._quotaDay = reservedDay;
  next();
}

// 生成不冲突的 6 位取件码
function genCode() {
  for (let i = 0; i < 100; i++) {
    const code = String(crypto.randomInt(0, 1000000)).padStart(6, '0');
    if (!fs.existsSync(path.join(UPLOAD_DIR, code + '.json'))) return code;
  }
  throw new Error('无法分配取件码');
}

function metaPath(code) {
  return path.join(UPLOAD_DIR, code + '.json');
}
function filePath(code) {
  return path.join(UPLOAD_DIR, code + '.bin');
}
// 取件码必须是 6 位数字，防止路径穿越
const CODE_RE = /^\d{6}$/;
const downloading = new Set();

function readMeta(code) {
  try {
    const meta = JSON.parse(fs.readFileSync(metaPath(code), 'utf8'));
    if (Date.now() > meta.expiresAt) return null;
    if (meta.taken) return meta;
    if (!fs.existsSync(filePath(code))) return null;
    return meta;
  } catch {
    return null;
  }
}

app.get('/api/quota', (req, res) => {
  res.json(quotaInfo(clientIp(req)));
});

// 上传
app.post('/api/upload', quotaGate, upload.single('file'), (req, res) => {
  if (!req.file) {
    releaseQuota(req);
    return res.status(400).json({ error: '没有收到文件', quota: quotaInfo(req.clientIp) });
  }
  try {
    const code = genCode();
    // multer 1.x 的 originalname 是 latin1，转回 utf8 以支持中文文件名
    const name = Buffer.from(req.file.originalname, 'latin1').toString('utf8');
    const meta = {
      code,
      name,
      size: req.file.size,
      createdAt: Date.now(),
      expiresAt: Date.now() + EXPIRE_MS
    };
    fs.renameSync(req.file.path, filePath(code));
    fs.writeFileSync(metaPath(code), JSON.stringify(meta));
    keepQuota(req);
    res.json({ ...meta, quota: quotaInfo(req.clientIp) });
  } catch (e) {
    releaseQuota(req);
    fs.unlink(req.file.path, () => {});
    res.status(500).json({ error: '保存失败', quota: quotaInfo(req.clientIp) });
  }
});

// 查询文件信息
app.get('/api/info/:code', (req, res) => {
  const code = req.params.code;
  if (!CODE_RE.test(code)) return res.status(400).json({ error: '取件码格式不正确' });
  const meta = readMeta(code);
  if (!meta) return res.status(404).json({ error: '文件不存在或已过期' });
  if (meta.taken) return res.status(410).json({ error: '文件已被取走' });
  res.json(meta);
});

// 下载文件。传完后删除源文件，取件码作废。
app.get('/api/download/:code', (req, res) => {
  const code = req.params.code;
  if (!CODE_RE.test(code)) return res.status(400).json({ error: '取件码格式不正确' });
  if (downloading.has(code)) return res.status(409).json({ error: '文件正在被取走' });

  const meta = readMeta(code);
  const fp = filePath(code);
  if (!meta || meta.taken || !fs.existsSync(fp)) {
    const taken = meta && meta.taken;
    return res.status(taken ? 410 : 404).json({ error: taken ? '文件已被取走' : '文件不存在或已过期' });
  }

  downloading.add(code);
  try {
    res.download(fp, meta.name, (err) => {
      downloading.delete(code);
      if (err) return;
      try {
        fs.unlinkSync(fp);
      } catch {}
      try {
        fs.writeFileSync(metaPath(code), JSON.stringify({
          code,
          name: meta.name,
          taken: true,
          expiresAt: meta.expiresAt
        }));
      } catch {}
      console.log(`已取走并删除: ${code} ${meta.name}`);
    });
  } catch (e) {
    downloading.delete(code);
    if (!res.headersSent) res.status(500).json({ error: '下载失败' });
  }
});

// 旧的分享路径只打开首页，页面不再提供分享链接
app.get('/f/:code', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.use((err, req, res, next) => {
  releaseQuota(req);
  if (err && err.code === 'LIMIT_FILE_SIZE') {
    return res.status(413).json({
      error: `文件超过 ${MAX_FILE_SIZE / 1024 / 1024}MB 限制`,
      quota: quotaInfo(req.clientIp || clientIp(req))
    });
  }
  if (res.headersSent) return next(err);
  res.status(500).json({ error: '上传失败' });
});

// 每 10 分钟清理过期文件
setInterval(() => {
  for (const f of fs.readdirSync(UPLOAD_DIR)) {
    if (!f.endsWith('.json')) continue;
    try {
      const meta = JSON.parse(fs.readFileSync(path.join(UPLOAD_DIR, f), 'utf8'));
      if (downloading.has(meta.code)) continue;
      if (Date.now() > meta.expiresAt) {
        fs.unlink(path.join(UPLOAD_DIR, f), () => {});
        fs.unlink(filePath(meta.code), () => {});
        console.log(`已清理过期文件: ${meta.code} ${meta.name || ''}`);
      }
    } catch {}
  }
}, 10 * 60 * 1000);

const HOST = process.env.HOST || "0.0.0.0";
app.listen(PORT, HOST, () => {
  console.log(`FileDrop running at http://${HOST}:${PORT}`);
});
