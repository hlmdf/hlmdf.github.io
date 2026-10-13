const fs = require('fs');
const path = require('path');
const dayFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'
});

function dayKey(now) {
  const parts = Object.fromEntries(dayFormatter.formatToParts(now).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

class DailyQuota {
  constructor(filename, limit = 100, clock = () => new Date()) {
    this.filename = filename;
    this.limit = limit;
    this.clock = clock;
    this.date = '';
    this.counts = Object.create(null);
    if (fs.existsSync(filename)) {
      const saved = JSON.parse(fs.readFileSync(filename, 'utf8'));
      // Legacy lifetime counts cannot identify today's uploads; start a fresh daily budget.
      if (saved && saved.version === 2 && typeof saved.date === 'string' && saved.counts) {
        this.date = saved.date;
        for (const [ip, used] of Object.entries(saved.counts)) {
          if (Number.isInteger(used) && used > 0) this.counts[ip] = used;
        }
      }
    }
  }

  save() {
    fs.mkdirSync(path.dirname(this.filename), { recursive: true });
    fs.writeFileSync(this.filename + '.tmp', JSON.stringify({ version: 2, date: this.date, counts: this.counts }), { mode: 0o600 });
    fs.renameSync(this.filename + '.tmp', this.filename);
  }

  today() {
    const date = dayKey(this.clock());
    if (date !== this.date) {
      this.date = date;
      this.counts = Object.create(null);
      this.save();
    }
    return date;
  }

  info(ip) {
    const date = this.today();
    const used = this.counts[ip] || 0;
    return { used, limit: this.limit, remaining: Math.max(0, this.limit - used), date, timeZone: 'Asia/Shanghai', period: 'daily' };
  }

  reserve(ip) {
    const date = this.today();
    const used = this.counts[ip] || 0;
    if (used >= this.limit) return false;
    this.counts[ip] = used + 1;
    try { this.save(); }
    catch (error) { this.counts[ip] = used; throw error; }
    return date;
  }

  refund(ip, reservedDay) {
    if (this.today() !== reservedDay) return;
    const used = this.counts[ip] || 0;
    if (!used) return;
    this.counts[ip] = used - 1;
    this.save();
  }
}

module.exports = { DailyQuota, dayKey };
