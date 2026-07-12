// usage-api — Karlz AI "AI Usage" backend.
// Gort owns the API and refreshes server-readable providers directly. Karl's
// laptop may still push richer browser/OAuth-backed values; those are merged as
// last-known data instead of being the single point of freshness.
const https = require('https');
const fs = require('fs');
const url = require('url');
const path = require('path');
const { spawnSync } = require('child_process');

const PORT = 7811;
const TLS_KEY = '/Users/gort/.openclaw/workspace/gort.pitta-crested.ts.net.key';
const TLS_CERT = '/Users/gort/.openclaw/workspace/gort.pitta-crested.ts.net.crt';
const DATA = path.join(__dirname, 'usage.json');
const MIRROR_DATA = '/Users/gort/.openclaw/apps/usage-api/usage.json';
const TITLE = 'AI Usage API';
const REFRESH_MS = 60_000;

function nowSec() {
  return Math.floor(Date.now() / 1000);
}

function stamp() {
  return new Date().toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: 'America/Los_Angeles',
  });
}

function sendJSON(res, code, obj) {
  res.writeHead(code, {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(JSON.stringify(obj));
}

function readJSON(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

function writeJSON(file, blob) {
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(blob, null, 2)}\n`);
  fs.renameSync(tmp, file);
}

function withAge(blob) {
  const copy = JSON.parse(JSON.stringify(blob));
  copy.ok = true;
  copy.ageSec = copy.ts ? Math.max(0, nowSec() - copy.ts) : null;
  if (Array.isArray(copy.providers)) {
    for (const p of copy.providers) {
      if (p.serverTs) p.ageSec = Math.max(0, nowSec() - p.serverTs);
      else if (p.cacheTs) p.ageSec = Math.max(0, nowSec() - p.cacheTs);
      else if (copy.laptopTs) p.ageSec = Math.max(0, nowSec() - copy.laptopTs);
      else if (copy.ts) p.ageSec = Math.max(0, nowSec() - copy.ts);
      if (!p.source) p.source = 'laptop-cache';
      if (p.source === 'laptop-cache' && p.ageSec != null && p.ageSec > 180) p.stale = true;
    }
  }
  return copy;
}

function normalizeCachedProviders(blob) {
  const laptopTs = blob.laptopTs || (!blob.serverCollector ? blob.ts : null) || nowSec();
  if (!Array.isArray(blob.providers)) blob.providers = [];
  for (const provider of blob.providers) {
    if (!provider.source) provider.source = 'laptop-cache';
    if (provider.source === 'laptop-cache' && !provider.cacheTs) provider.cacheTs = laptopTs;
  }
  if (!blob.laptopTs) blob.laptopTs = laptopTs;
  return blob;
}

function mergeProviders(base, updates) {
  const byId = new Map();
  for (const provider of base.providers || []) byId.set(provider.id, provider);
  for (const provider of updates) {
    if (!provider || !provider.id) continue;
    const merged = {
      ...(byId.get(provider.id) || {}),
      ...provider,
      serverTs: nowSec(),
      stale: false,
    };
    if (merged.source !== 'laptop-cache') delete merged.cacheTs;
    byId.set(provider.id, merged);
  }
  const order = ['claude', 'codex', 'ollama', 'zai'];
  return order.map((id) => byId.get(id)).filter(Boolean);
}

function resetLabel(epochSec) {
  if (!epochSec) return '';
  const d = new Date(epochSec * 1000);
  return d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: 'America/Los_Angeles',
  });
}

function collectCodex() {
  const script = `
const fs=require('fs'), path=require('path'), os=require('os');
function walk(d,out=[]){try{for(const e of fs.readdirSync(d,{withFileTypes:true})){const p=path.join(d,e.name); if(e.isDirectory()) walk(p,out); else if(e.isFile()&&p.endsWith('.jsonl')) out.push(p)}}catch{} return out}
let best=null;
for(const f of walk(path.join(os.homedir(),'.codex','sessions'))){
  let st; try{st=fs.statSync(f)}catch{continue}
  if(Date.now()-st.mtimeMs>14*86400e3) continue;
  const lines=fs.readFileSync(f,'utf8').split(/\\n/);
  for(const line of lines){
    if(!line.includes('rate_limits')) continue;
    try{
      const o=JSON.parse(line);
      const r=o.rate_limits || o.payload?.rate_limits;
      if(r?.primary || r?.secondary) best={timestamp:o.timestamp,rate_limits:r};
    }catch{}
  }
}
console.log(JSON.stringify(best));
`;
  const encoded = Buffer.from(script).toString('base64');
  const result = spawnSync('/usr/bin/ssh', ['coder', 'node', '-'], {
    encoding: 'utf8',
    timeout: 15_000,
    input: Buffer.from(encoded, 'base64').toString('utf8'),
  });
  if (result.status !== 0 || !result.stdout.trim()) {
    throw new Error(`codex collector failed: ${result.stderr || result.status}`);
  }
  const parsed = JSON.parse(result.stdout);
  const limits = parsed?.rate_limits;
  if (!limits?.primary && !limits?.secondary) throw new Error('codex collector found no rate_limits');
  return {
    id: 'codex',
    name: 'Codex',
    label: limits.plan_type ? String(limits.plan_type).replace(/^./, (c) => c.toUpperCase()) : 'Pro',
    pct: limits.primary?.used_percent ?? null,
    reset: resetLabel(limits.primary?.resets_at),
    resetAt: limits.primary?.resets_at ?? null,     // raw epoch (sec) for device-local formatting
    weeklyPct: limits.secondary?.used_percent ?? null,
    weeklyReset: resetLabel(limits.secondary?.resets_at),
    weeklyResetAt: limits.secondary?.resets_at ?? null,
    ok: true,
    source: 'coder-codex-sessions',
  };
}

function launchctlEnv(name) {
  const result = spawnSync('/bin/launchctl', ['getenv', name], {
    encoding: 'utf8',
    timeout: 5_000,
  });
  return result.status === 0 ? result.stdout.trim() : '';
}

function getZaiKey() {
  if (process.env.ZAI_API_KEY) return process.env.ZAI_API_KEY.trim();
  const fromLaunchd = launchctlEnv('ZAI_API_KEY');
  if (fromLaunchd) return fromLaunchd;
  for (const file of [
    path.join(process.env.HOME || '/Users/gort', '.config/ai-usage-bar/zai.key'),
    path.join(process.env.HOME || '/Users/gort', '.config/claude-glm/zai.env'),
    path.join(process.env.HOME || '/Users/gort', '.openclaw/.env'),
    path.join(process.env.HOME || '/Users/gort', '.openclaw/openclaw.json'),
  ]) {
    try {
      const raw = fs.readFileSync(file, 'utf8').trim();
      const match = raw.match(/(?:ZAI_API_KEY|GLM_API_KEY)[^A-Za-z0-9._-]+([A-Za-z0-9._-]{20,})/);
      if (match) return match[1];
    } catch {}
  }
  return '';
}

function getClaudeToken() {
  if (process.env.CLAUDE_OAUTH_TOKEN) return process.env.CLAUDE_OAUTH_TOKEN.trim();
  try {
    const raw = fs.readFileSync(
      path.join(process.env.HOME || '/Users/gort', '.config/ai-usage-bar/claude-oauth.token'),
      'utf8'
    ).trim();
    if (raw) return raw;
  } catch {}
  return '';
}

// Ping api.anthropic.com/v1/messages and read the anthropic-ratelimit-unified-*
// headers. Only requires the user:inference scope on the OAuth token.
async function collectClaude() {
  const token = getClaudeToken();
  if (!token) throw new Error('no Claude OAuth token available');
  const headers = await new Promise((resolve, reject) => {
    const req = https.request({
      method: 'POST',
      hostname: 'api.anthropic.com',
      path: '/v1/messages',
      headers: {
        'Authorization': `Bearer ${token}`,
        'anthropic-beta': 'oauth-2025-04-20',
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
        'User-Agent': 'usage-api/1.0',
      },
      timeout: 15_000,
    }, (res) => {
      // drain body but ignore it — we only care about response headers
      res.on('data', () => {});
      res.on('end', () => resolve(res.headers));
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
    req.end(JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 1,
      messages: [{ role: 'user', content: '.' }],
    }));
  });
  const numHeader = (name) => {
    const v = headers[name];
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const pctHeader = (name) => {
    const v = numHeader(name);
    return v == null ? null : Math.round(v * 1000) / 10;   // 0..1 -> 0..100 (1 dp)
  };
  const p5h = pctHeader('anthropic-ratelimit-unified-5h-utilization');
  const pwk = pctHeader('anthropic-ratelimit-unified-7d-utilization');
  const r5h = numHeader('anthropic-ratelimit-unified-5h-reset');
  const rwk = numHeader('anthropic-ratelimit-unified-7d-reset');
  if (p5h == null && pwk == null) throw new Error('no ratelimit headers in Claude response');
  return {
    id: 'claude',
    name: 'Claude',
    label: 'Max 20x',
    pct: p5h,
    reset: resetLabel(r5h),
    resetAt: r5h ?? null,
    weeklyPct: pwk,
    weeklyReset: resetLabel(rwk),
    weeklyResetAt: rwk ?? null,
    ok: true,
    source: 'gort-claude-api',
  };
}

// Hit ollama.com/settings with the Mac-shipped session cookies and regex the
// live Session/Weekly percentages out of the server-rendered HTML. Ollama has
// no public usage API — the numbers only exist in this HTML page behind auth.
// Cookies are refreshed by Karl's Mac every ~60s (long-lived; survive weeks
// when the Mac is offline).
function collectOllama() {
  return new Promise((resolve, reject) => {
    let ck;
    try {
      const raw = fs.readFileSync(
        path.join(process.env.HOME || '/Users/gort', '.config/ai-usage-bar/ollama-cookies.json'),
        'utf8'
      );
      ck = JSON.parse(raw);
    } catch (e) {
      reject(new Error('no shipped ollama cookies yet'));
      return;
    }
    if (!ck.aid || !ck.session) {
      reject(new Error('cookie file missing aid or session'));
      return;
    }
    const cookieHdr = `aid=${ck.aid}; __Secure-session=${ck.session}`;
    const req = https.get('https://ollama.com/settings', {
      headers: {
        Cookie: cookieHdr,
        'User-Agent': 'Mozilla/5.0',
        Accept: 'text/html',
      },
      timeout: 15_000,
    }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        if (!body.includes('Session usage')) {
          reject(new Error('not logged in (cookie expired?)'));
          return;
        }
        const pctMatch = (label) => {
          const m = body.match(new RegExp(label + '[\\s\\S]{0,200}?([\\d.]+)%\\s*used'));
          return m ? Number(m[1]) : null;
        };
        const resets = [...body.matchAll(/Resets in ([^<.]+)/g)].map((m) => m[1].trim());
        const sPct = pctMatch('Session usage');
        const wPct = pctMatch('Weekly usage');
        const bal = (body.match(/Balance remaining[\s\S]{0,120}?(\$[\d.,]+)/) || [])[1];
        if (sPct == null && wPct == null) {
          reject(new Error('no usage percents in Ollama settings HTML'));
          return;
        }
        const extra = bal ? `bal ${bal}` : null;
        resolve({
          id: 'ollama',
          name: 'Ollama Cloud',
          label: '',
          pct: sPct,
          reset: resets[0] || '',
          weeklyPct: wPct,
          weeklyReset: resets[1] || '',
          ok: true,
          source: 'gort-ollama-scrape',
          ...(extra ? { extra } : {}),
        });
      });
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
  });
}

function fetchJSON(target, headers = {}) {
  return new Promise((resolve, reject) => {
    const req = https.get(target, { headers, timeout: 15_000 }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          fetchJSON(new URL(res.headers.location, target).toString(), headers).then(resolve, reject);
          return;
        }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch {
          reject(new Error('non-JSON response'));
        }
      });
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
  });
}

function findLimits(payload) {
  const found = [];
  function visit(value) {
    if (Array.isArray(value)) {
      for (const item of value) visit(item);
      return;
    }
    if (!value || typeof value !== 'object') return;
    const keys = Object.keys(value).map((k) => k.toLowerCase());
    const hasUsage = keys.some((k) => k.includes('percent') || k.includes('usage') || k.includes('used'));
    const hasWindow = keys.some((k) => k.includes('window') || k.includes('cycle') || k.includes('period') || k.includes('limit'));
    if (hasUsage && (hasWindow || keys.includes('type') || keys.includes('unit'))) found.push(value);
    for (const item of Object.values(value)) visit(item);
  }
  visit(payload?.data ?? payload);
  return found;
}

function numFrom(obj, names) {
  for (const name of names) {
    const value = obj?.[name];
    if (typeof value === 'number') return value;
    if (typeof value === 'string' && value.trim() !== '' && !Number.isNaN(Number(value))) return Number(value);
  }
  return null;
}

function stringBlob(obj) {
  return JSON.stringify(obj).toLowerCase();
}

function pctFromLimit(obj) {
  if (typeof obj?.percentage === 'number') return Math.round(obj.percentage * 10) / 10;
  if (typeof obj?.percentage === 'string' && obj.percentage.trim() !== '' && !Number.isNaN(Number(obj.percentage))) {
    return Math.round(Number(obj.percentage) * 10) / 10;
  }
  const direct = numFrom(obj, [
    'percent', 'usedPercent', 'used_percent', 'usagePercent',
    'usage_percentage', 'rate', 'usageRate', 'usedRate',
  ]);
  if (direct != null) return direct <= 1 ? Math.round(direct * 1000) / 10 : Math.round(direct * 10) / 10;
  const used = numFrom(obj, ['used', 'usedTokens', 'usage', 'current', 'value']);
  const limit = numFrom(obj, ['limit', 'total', 'quota', 'max']);
  if (used != null && limit > 0) return Math.round((used / limit) * 1000) / 10;
  return null;
}

function resetFromLimit(obj) {
  const raw = numFrom(obj, ['resetAt', 'reset_at', 'resetsAt', 'resets_at', 'nextResetTime', 'endTime', 'end_time', 'periodEnd']);
  if (!raw) return '';
  const ms = raw > 10_000_000_000 ? raw : raw * 1000;
  return new Date(ms).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: 'America/Los_Angeles',
  });
}

// Return the raw epoch (seconds) so clients can format in their own timezone.
function resetEpochFromLimit(obj) {
  const raw = numFrom(obj, ['resetAt', 'reset_at', 'resetsAt', 'resets_at', 'nextResetTime', 'endTime', 'end_time', 'periodEnd']);
  if (!raw) return null;
  return raw > 10_000_000_000 ? Math.floor(raw / 1000) : raw;
}

async function collectZai() {
  const key = getZaiKey();
  if (!key) throw new Error('no z.ai key available');
  const quota = await fetchJSON('https://api.z.ai/api/monitor/usage/quota/limit', {
    Authorization: `Bearer ${key}`,
    Accept: 'application/json',
  });
  const directLimits = Array.isArray(quota?.data?.limits) ? quota.data.limits : [];
  const limits = directLimits.length ? directLimits : findLimits(quota);
  const tokenLimits = limits.filter((limit) => limit?.type === 'TOKENS_LIMIT');
  const session = tokenLimits.find((limit) => Number(limit.unit) === 3 && Number(limit.number) === 5)
    || tokenLimits[0]
    || limits[0];
  const weekly = tokenLimits.find((limit) => Number(limit.unit) === 6)
    || tokenLimits.find((limit) => limit !== session)
    || null;
  const sessionPct = pctFromLimit(session);
  const weeklyPct = pctFromLimit(weekly);
  if (sessionPct == null && weeklyPct == null) throw new Error('z.ai quota response had no usable percentages');
  return {
    id: 'zai',
    name: 'z.ai',
    label: String(quota?.data?.level || 'PRO').toUpperCase(),
    pct: sessionPct,
    reset: resetFromLimit(session),
    resetAt: resetEpochFromLimit(session),
    weeklyPct,
    weeklyReset: resetFromLimit(weekly),
    weeklyResetAt: resetEpochFromLimit(weekly),
    ok: true,
    source: 'gort-zai-api',
  };
}

async function refreshUsage() {
  const prior = normalizeCachedProviders(readJSON(DATA) || readJSON(MIRROR_DATA) || { providers: [] });
  const updates = [];
  const errors = {};
  try {
    updates.push(await collectClaude());
  } catch (err) {
    errors.claude = err.message;
  }
  try {
    updates.push(collectCodex());
  } catch (err) {
    errors.codex = err.message;
  }
  try {
    updates.push(await collectZai());
  } catch (err) {
    errors.zai = err.message;
  }
  try {
    updates.push(await collectOllama());
  } catch (err) {
    errors.ollama = err.message;
  }
  const next = {
    ...prior,
    ts: nowSec(),
    laptopTs: prior.laptopTs,
    updated: stamp(),
    providers: mergeProviders(prior, updates),
    serverCollector: {
      host: 'gort',
      ts: nowSec(),
      updated: stamp(),
      refreshed: updates.map((p) => p.id),
      errors,
    },
  };
  writeJSON(DATA, next);
  try {
    writeJSON(MIRROR_DATA, next);
  } catch {}
  return next;
}

const server = https.createServer(
  { key: fs.readFileSync(TLS_KEY), cert: fs.readFileSync(TLS_CERT) },
  async (req, res) => {
    const parsed = url.parse(req.url, true);
    if (parsed.pathname === '/health') {
      sendJSON(res, 200, { ok: true, service: TITLE, port: PORT });
      return;
    }
    if (parsed.pathname === '/api/usage') {
      const blob = readJSON(DATA);
      if (!blob) {
        sendJSON(res, 503, { ok: false, error: 'no usage data yet' });
        return;
      }
      sendJSON(res, 200, withAge(blob));
      return;
    }
    if (parsed.pathname === '/api/refresh') {
      try {
        sendJSON(res, 200, withAge(await refreshUsage()));
      } catch (err) {
        sendJSON(res, 500, { ok: false, error: err.message });
      }
      return;
    }
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(`<!doctype html><meta charset="utf-8"><title>${TITLE}</title><body style="font-family:system-ui;background:#111;color:#eee;padding:2rem"><h1>${TITLE}</h1><p>GET /api/usage · GET /api/refresh · GET /health</p></body>`);
  }
);

server.listen(PORT, () => {
  console.log(`${TITLE} on :${PORT}`);
  refreshUsage().catch((err) => console.error(`initial refresh failed: ${err.message}`));
  setInterval(() => {
    refreshUsage().catch((err) => console.error(`scheduled refresh failed: ${err.message}`));
  }, REFRESH_MS).unref();
});
