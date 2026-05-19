/**
 * TING MEDIA CRM — Agent Webhook Server
 * WhatsApp Cloud API (Meta) + Claude AI for task analysis
 *
 * Setup on server:
 *   cd /var/www/ting-agent
 *   npm install express axios @anthropic-ai/sdk firebase-admin
 *   node webhook.js
 */

const express = require('express');
const axios   = require('axios');
const Anthropic = require('@anthropic-ai/sdk');
const admin   = require('firebase-admin');

const app = express();
app.use(express.json());

// ── Firebase Admin init ──────────────────────────────────────────────────────
// serviceAccount.json should be placed in same folder (download from Firebase Console)
let db;
try {
  const serviceAccount = require('./serviceAccount.json');
  admin.initializeApp({ credential: admin.credential.cert(serviceAccount) });
  db = admin.firestore();
  console.log('✅ Firebase connected');
} catch(e) {
  console.error('❌ Firebase init failed:', e.message);
}

// ── Helpers ──────────────────────────────────────────────────────────────────
async function getConfig(userId) {
  if (!db) return null;
  const snap = await db.collection('agentConfig').doc(userId).get();
  return snap.exists ? snap.data() : null;
}

async function getAllContacts(userId) {
  if (!db) return [];
  const snap = await db.collection('clients').where('userId','==',userId).get();
  const contacts = [];
  snap.docs.forEach(doc => {
    const c = doc.data();
    const cname = c.name || '';
    (c.contacts||[]).forEach(ct => {
      const phone = (ct.phone||'').replace(/\D/g,'');
      if (phone) contacts.push({ phone, email:ct.email||'', name:ct.name||'', role:ct.role||'', clientName:cname, clientId:doc.id });
    });
    // Legacy
    if (c.contactPhone) {
      const phone = (c.contactPhone||'').replace(/\D/g,'');
      if (phone && !contacts.find(x=>x.phone===phone)) {
        contacts.push({ phone, email:c.contactEmail||'', name:c.contactName||'', role:'', clientName:cname, clientId:doc.id });
      }
    }
    // WhatsApp groups
    (c.whatsappGroups||[]).forEach(grp => {
      if (grp.groupId) contacts.push({ phone:grp.groupId, name:grp.name||'', role:'קבוצה', clientName:cname, clientId:doc.id, isGroup:true });
    });
  });
  return contacts;
}

async function getOpenTasks(userId) {
  if (!db) return [];
  const snap = await db.collection('tasks').where('userId','==',userId).where('archived','!=',true).get();
  return snap.docs.map(d => ({ id:d.id, ...d.data() })).filter(t => (t.stage||1) < 7);
}

// ── Claude AI analysis ────────────────────────────────────────────────────────
async function analyzeMessage({ message, clientName, contactName, openTasks, claudeKey }) {
  if (!claudeKey || !message?.trim()) return null;

  const client = new Anthropic({ apiKey: claudeKey });

  const taskList = openTasks.slice(0,20).map((t,i) => `${i+1}. "${t.title||'ללא שם'}" (לקוח: ${t.client||'?'})`).join('\n');

  const prompt = `אתה סוכן CRM חכם של סוכנות תוכן בישראל.
קיבלת הודעת WhatsApp מ: ${contactName||'לא ידוע'} (לקוח: ${clientName||'לא ידוע'}).

הודעה:
"${message}"

משימות פתוחות קיימות:
${taskList || '(אין משימות פתוחות)'}

משימה שלך:
1. זהה כמה נושאי עבודה/action items יש בהודעה (יכולים להיות כמה)
2. לכל נושא — בדוק אם יש משימה קיימת שמתאימה לו
3. החזר JSON בפורמט הבא:

{
  "topics": [
    {
      "title": "כותרת קצרה לנושא",
      "confidence": 85,
      "isActionItem": true,
      "matchingTaskIndex": 2,
      "matchReason": "ההודעה מדברת על שליחת קובץ שקשורה למשימה 2"
    }
  ],
  "shouldCreateTasks": [
    {
      "title": "כותרת משימה חדשה",
      "confidence": 78,
      "snippet": "חלק רלוונטי מההודעה"
    }
  ],
  "summary": "תקציר קצר של ההודעה"
}

כללים:
- confidence מעל 65 = כדאי להציע
- אם יש משימה קיימת שמתאימה → אל תצור חדשה, רק קשר
- הודעה חברותית/שאלה כללית → shouldCreateTasks ריק
- ענה JSON בלבד, ללא טקסט נוסף`;

  try {
    const resp = await client.messages.create({
      model: 'claude-3-haiku-20240307',
      max_tokens: 800,
      messages: [{ role: 'user', content: prompt }]
    });
    const text = resp.content[0]?.text || '{}';
    const cleaned = text.replace(/```json\n?|\n?```/g,'').trim();
    return JSON.parse(cleaned);
  } catch(e) {
    console.error('Claude error:', e.message);
    return null;
  }
}

// ── Process incoming WhatsApp message ────────────────────────────────────────
async function processWhatsAppMessage({ userId, from, message, timestamp, msgId }) {
  const [config, contacts, openTasks] = await Promise.all([
    getConfig(userId),
    getAllContacts(userId),
    getOpenTasks(userId)
  ]);

  const fromClean = (from||'').replace(/\D/g,'');
  const contact = contacts.find(c => (c.phone||'').replace(/\D/g,'') === fromClean);

  const logData = {
    userId, from, message, type:'whatsapp',
    clientName: contact?.clientName || null,
    contactName: contact?.name || null,
    status: 'no_action',
    topics: [],
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    msgId
  };

  // AI analysis
  const analysis = await analyzeMessage({
    message, clientName: contact?.clientName, contactName: contact?.name,
    openTasks, claudeKey: config?.claudeKey
  });

  if (analysis) {
    logData.topics   = (analysis.topics||[]).map(t=>t.title);
    logData.summary  = analysis.summary;

    // Create suggestions for new tasks
    const toCreate = (analysis.shouldCreateTasks||[]).filter(t=>t.confidence>=65);
    if (toCreate.length > 0) {
      logData.status = 'suggested';
    }

    // Save log first
    const logRef = await db.collection('agentLogs').add(logData);

    // Save suggestions
    for (const item of toCreate) {
      await db.collection('agentSuggestions').add({
        userId, logId: logRef.id,
        taskTitle: item.title,
        messageSnippet: item.snippet || message.slice(0,200),
        clientName: contact?.clientName || null,
        contactName: contact?.name || null,
        source: 'whatsapp',
        from,
        confidence: item.confidence,
        topics: logData.topics,
        status: 'pending',
        createdAt: admin.firestore.FieldValue.serverTimestamp()
      });
    }
  } else {
    await db.collection('agentLogs').add(logData);
  }

  console.log(`📱 Processed WA msg from ${from} → ${contact?.clientName||'unknown'} | status: ${logData.status}`);
}

// ── Find userId from WhatsApp phone number ────────────────────────────────────
async function findUserId(phone) {
  // Match based on agentConfig collection
  if (!db) return null;
  const snap = await db.collection('agentConfig').where('phoneNumber','==',phone).limit(1).get();
  if (!snap.empty) return snap.docs[0].data().userId;
  return null;
}

// ── Meta Webhook verification ────────────────────────────────────────────────
app.get('/agent/webhook', async (req, res) => {
  const mode      = req.query['hub.mode'];
  const token     = req.query['hub.verify_token'];
  const challenge = req.query['hub.challenge'];

  // Find config that matches this token
  let matched = false;
  if (db) {
    const snap = await db.collection('agentConfig').where('webhookToken','==',token).limit(1).get();
    matched = !snap.empty;
  }

  if (mode === 'subscribe' && matched) {
    console.log('✅ Webhook verified');
    res.status(200).send(challenge);
  } else {
    res.sendStatus(403);
  }
});

// ── Incoming WhatsApp messages ────────────────────────────────────────────────
app.post('/agent/webhook', async (req, res) => {
  res.sendStatus(200); // Always respond 200 immediately

  try {
    const body = req.body;
    if (body.object !== 'whatsapp_business_account') return;

    for (const entry of (body.entry||[])) {
      for (const change of (entry.changes||[])) {
        if (change.field !== 'messages') continue;
        const value = change.value || {};
        const businessPhone = value.metadata?.display_phone_number || '';
        const userId = await findUserId(businessPhone.replace(/\D/g,''));
        if (!userId) { console.log('No userId for phone:', businessPhone); continue; }

        for (const msg of (value.messages||[])) {
          if (msg.type !== 'text') continue; // Only process text for now
          await processWhatsAppMessage({
            userId,
            from: msg.from,
            message: msg.text?.body || '',
            timestamp: msg.timestamp,
            msgId: msg.id
          });
        }
      }
    }
  } catch(e) {
    console.error('Webhook processing error:', e);
  }
});

// ── Health check ──────────────────────────────────────────────────────────────
app.get('/agent/health', (req,res) => res.json({ status:'ok', time:new Date().toISOString() }));

// ── Start ─────────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 3001;
app.listen(PORT, () => console.log(`🤖 Agent webhook running on port ${PORT}`));
