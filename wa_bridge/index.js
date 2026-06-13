/**
 * TING WhatsApp Bridge
 * =====================
 * Connects to WhatsApp (multi-device, like WhatsApp Web) with the company's
 * existing number, and forwards every text message (groups + DMs) to the
 * Customer-Success ingest API. Exposes a tiny local HTTP API for the CRM:
 *   GET /status  -> { status: connecting|qr|connected|logged_out, me }
 *   GET /qr      -> { qr: <data-url png> | null }
 *   GET /groups  -> [{ id, subject, size }]
 *
 * Pairing: open the CRM -> שירות לקוחות -> חיבורים, scan the QR.
 * Session persists in ./auth — survives restarts.
 */

const http = require('http');
const fs = require('fs');
const QRCode = require('qrcode');
const axios = require('axios');
const pino = require('pino');
const {
  default: makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
} = require('@whiskeysockets/baileys');

const PORT       = process.env.PORT || 3002;
const API_URL    = process.env.CS_API_URL || 'http://127.0.0.1:8001/api/cs/ingest';
const API_TOKEN  = process.env.TING_TEAM_SECRET || 'team-secret-change-me';

let sock = null;
let state = { status: 'starting', qrDataUrl: null, me: null };

// ── Chat index (searchable list of groups + DMs) ──────────────────────────────
const CHATS_FILE = './chats.json';
let chats = {};                         // jid -> { id, name, isGroup, lastTs }
try { chats = JSON.parse(fs.readFileSync(CHATS_FILE, 'utf8')); } catch (e) {}
let saveTimer = null;
function persistChats() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { fs.writeFileSync(CHATS_FILE, JSON.stringify(chats)); } catch (e) {}
  }, 2500);
}
function recordChat(jid, name, ts) {
  if (!jid || jid === 'status@broadcast' || jid.endsWith('@broadcast')) return;
  const isGroup = jid.endsWith('@g.us');
  const cur = chats[jid] || { id: jid, name: null, isGroup, lastTs: 0 };
  // Always refresh group subject; for DMs keep the first decent name we learn
  if (name && (isGroup || !cur.name)) cur.name = name;
  if (ts && ts > cur.lastTs) cur.lastTs = ts;
  cur.isGroup = isGroup;
  chats[jid] = cur;
  persistChats();
}
async function seedGroups() {
  try {
    const groups = await sock.groupFetchAllParticipating();
    for (const g of Object.values(groups)) recordChat(g.id, g.subject, chats[g.id]?.lastTs || 0);
    console.log('seeded', Object.keys(groups).length, 'groups into chat index');
  } catch (e) { console.error('seedGroups:', e.message); }
}

async function start() {
  const { state: authState, saveCreds } = await useMultiFileAuthState('./auth');
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: authState,
    logger: pino({ level: 'warn' }),
    syncFullHistory: false,
    markOnlineOnConnect: false,   // don't steal notifications from the phone
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (u) => {
    const { connection, lastDisconnect, qr } = u;
    if (qr) {
      state.status = 'qr';
      state.qrDataUrl = await QRCode.toDataURL(qr, { width: 280, margin: 1 });
      console.log('QR ready — scan from the CRM');
    }
    if (connection === 'open') {
      state.status = 'connected';
      state.qrDataUrl = null;
      state.me = sock.user?.id || null;
      console.log('✅ WhatsApp connected as', state.me);
      seedGroups();
    }
    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        state.status = 'logged_out';
        console.error('Logged out — delete ./auth and re-pair');
      } else {
        state.status = 'connecting';
        console.log('Connection closed (code ' + code + ') — reconnecting...');
        setTimeout(start, 3000);
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return;
    for (const m of messages) {
      try { await indexChatFromMessage(m); } catch (e) {}
      try { await forwardMessage(m); }
      catch (e) { console.error('forward error:', e.message); }
    }
  });

  // Keep the group index fresh on subject changes / new groups
  sock.ev.on('groups.upsert', gs => { for (const g of gs) recordChat(g.id, g.subject, Date.now()); });
  sock.ev.on('groups.update', gs => { for (const g of gs) if (g.id && g.subject) recordChat(g.id, g.subject, chats[g.id]?.lastTs || 0); });
}

async function indexChatFromMessage(msg) {
  const jid = msg.key?.remoteJid || '';
  if (!jid) return;
  const isGroup = jid.endsWith('@g.us');
  const ts = msg.messageTimestamp ? Number(msg.messageTimestamp) * 1000 : Date.now();
  let name = null;
  if (isGroup) {
    name = chats[jid]?.name || null;
    if (!name) { try { name = (await sock.groupMetadata(jid)).subject; } catch (e) {} }
  } else {
    name = msg.key.fromMe ? chats[jid]?.name : (msg.pushName || chats[jid]?.name || null);
  }
  recordChat(jid, name, ts);
}

function extractText(msg) {
  const m = msg.message;
  if (!m) return null;
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    m.documentMessage?.caption ||
    null
  );
}

async function forwardMessage(msg) {
  const text = extractText(msg);
  if (!text) return;                                   // skip media-only / system
  const jid = msg.key.remoteJid || '';
  if (jid === 'status@broadcast') return;              // skip statuses
  const isGroup = jid.endsWith('@g.us');
  const fromMe = !!msg.key.fromMe;

  let threadName = null;
  if (isGroup) {
    try { threadName = (await sock.groupMetadata(jid)).subject; } catch (e) {}
  }

  await axios.post(API_URL, {
    channel: 'whatsapp',
    thread_id: jid,
    thread_name: threadName,
    sender_id: fromMe ? 'me' : (msg.key.participant || jid),
    sender_name: fromMe ? 'אנחנו' : (msg.pushName || null),
    direction: fromMe ? 'out' : 'in',
    text,
    sent_at: msg.messageTimestamp
      ? new Date(Number(msg.messageTimestamp) * 1000).toISOString()
      : new Date().toISOString(),
  }, { headers: { 'X-Team-Token': API_TOKEN }, timeout: 10000 });
}

// ── Local HTTP API ────────────────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  try {
    if (req.url === '/status') {
      res.end(JSON.stringify({ status: state.status, me: state.me }));
    } else if (req.url === '/qr') {
      res.end(JSON.stringify({ status: state.status, qr: state.qrDataUrl }));
    } else if (req.url === '/groups') {
      if (state.status !== 'connected') { res.end(JSON.stringify([])); return; }
      const groups = await sock.groupFetchAllParticipating();
      const list = Object.values(groups).map(g => ({
        id: g.id, subject: g.subject, size: (g.participants || []).length,
      })).sort((a, b) => a.subject.localeCompare(b.subject, 'he'));
      res.end(JSON.stringify(list));
    } else if (req.url.startsWith('/chats')) {
      const u = new URL(req.url, 'http://x');
      const q = (u.searchParams.get('q') || '').toLowerCase().trim();
      const type = u.searchParams.get('type') || 'all';     // all | group | dm
      const limit = Math.min(parseInt(u.searchParams.get('limit') || '300', 10), 1000);
      let list = Object.values(chats);
      if (type === 'group') list = list.filter(c => c.isGroup);
      else if (type === 'dm') list = list.filter(c => !c.isGroup);
      if (q) list = list.filter(c => (c.name || '').toLowerCase().includes(q) || c.id.toLowerCase().includes(q));
      list.sort((a, b) => (b.lastTs || 0) - (a.lastTs || 0));
      res.end(JSON.stringify(list.slice(0, limit)));
    } else {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: 'not found' }));
    }
  } catch (e) {
    res.statusCode = 500;
    res.end(JSON.stringify({ error: e.message }));
  }
});

server.listen(PORT, '127.0.0.1', () => console.log(`bridge http on :${PORT}`));
start().catch(e => { console.error('fatal:', e); process.exit(1); });
