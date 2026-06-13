# סוכן ניהול צ'ט וקבלות (WhatsApp + Gmail Agent)

סוכן אוטונומי לניהול התכתבויות בקבוצות WhatsApp ודוא"ל Gmail, עם יכולת סיכום משימות וקישור בין הפלטפורמות.

## 🎯 תכונות

- ✅ **סנכרון שעתי** - קריאת הודעות כל שעה מ-WhatsApp ו-Gmail
- ✅ **חישוב זמני מענה** - עקוב אחרי כמה זמן נענו להודעות
- ✅ **סיכום משימות** - זיהוי ופילוח משימות בשתי הפלטפורמות
- ✅ **קישור משימות** - חיבור משימות דומות בין WhatsApp לGmail
- ✅ **דאשבורד ווב** - צפייה בכל הנתונים בממשק אחיד
- ✅ **סטטיסטיקות** - ניתוח ודוחות על פעילות וביצועים

## 🚀 התחלה

### 1. התקנה

```bash
cd whatsapp_agent
pip install -r requirements.txt
```

### 2. הגדרת Credentials

#### Gmail API

1. לך ל-[Google Cloud Console](https://console.cloud.google.com/)
2. צור פרויקט חדש
3. הפעל Gmail API
4. צור OAuth 2.0 credentials (Desktop Application)
5. הורד את ה-JSON וחفוץ כ-`gmail_credentials.json` בתיקיית הפרויקט

#### WhatsApp Business API

1. הירשם ל-[Meta for Developers](https://developers.facebook.com/)
2. צור Business App
3. הוסף WhatsApp product
4. קבל Access Token
5. שמור את המידע בקובץ `.env`

### 3. הגדרות .env

```bash
cp .env.example .env
```

עדכן את ה-.env עם הערכים שלך:

```
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# WhatsApp
WHATSAPP_API_TOKEN=EAA...
WHATSAPP_PHONE_NUMBER_ID=1234567890123456
WHATSAPP_BUSINESS_ACCOUNT_ID=987654321098765
MONITORED_WHATSAPP_GROUPS=1234567890123456

# Flask
FLASK_PORT=5000
SCHEDULER_INTERVAL_MINUTES=60

# Debug
DEBUG=False
```

### 4. הרצה מקומית

```bash
python main.py
```

הדאשבורד יהיה זמין בכתובת: `http://localhost:5000`

### 5. הרצה עם סנכרון ידני לבדיקה

```bash
python main.py --test-sync
```

## 🔧 שימוש בדאשבורד

### עמוד ראשי
- צפה בסטטיסטיקות של משימות והודעות
- הפעל סנכרון ידני
- בדוק עדכונים אחרונים

### משימות
- ראה את כל המשימות הפתוחות
- סווג לפי עדיפות וסטטוס
- עדכן סטטוס של משימה

### הודעות
- צפה בהודעות אחרונות מ-WhatsApp ו-Gmail
- בדוק זמני מענה
- חפש הודעות

### אנליטיקה
- סטטיסטיקות כללית
- זמני מענה ממוצעים
- התפלגות לפי פלטפורמה

## 📡 API Endpoints

```
GET  /api/dashboard-data      - כל הנתונים לדאשבורד
GET  /api/tasks               - רשימת משימות
GET  /api/messages            - רשימת הודעות
GET  /api/analytics           - סטטיסטיקות
POST /api/sync-now            - הפעל סנכרון ידני
PUT  /api/task/<id>/status    - עדכן סטטוס משימה
```

## 🌐 Deployment

### Heroku

```bash
# Login
heroku login

# Create app
heroku create whatsapp-gmail-agent

# Set environment variables
heroku config:set ANTHROPIC_API_KEY=sk-ant-...
heroku config:set WHATSAPP_API_TOKEN=EAA...

# Deploy
git push heroku main

# View logs
heroku logs --tail
```

### Google Cloud Run

```bash
# Build and deploy
gcloud run deploy whatsapp-agent \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### AWS Lambda + EventBridge

1. Create Lambda function with Python 3.12
2. Upload zip of project
3. Set environment variables
4. Create EventBridge rule to trigger every hour
5. Set Lambda as target

## 📊 Database Schema

הסוכן משתמש ב-SQLite לפיתוח וניתן להמיר ל-PostgreSQL בעיבוד.

```
Messages:
- id, platform, sender, content, timestamp, response_time_minutes

Tasks:
- id, title, description, status, priority, created_at, due_date

TaskLinks:
- id, task_id_1, task_id_2, link_type, confidence

SyncRuns:
- id, start_time, end_time, messages_fetched, tasks_created
```

## 🔐 אבטחה

- **לעולם אל תשמור API keys בקוד** - השתמש ב-.env
- **השמור credentials בזהירות** - הם נתונים רגישים
- **בדוק הרשאות** - פחות הרשאות אפשריות = פחות סיכוני
- **אל תשתף קבצי .env** - הוסף ל-.gitignore

## 🛠️ פתרון בעיות

### "Gmail authentication failed"
```bash
rm token.pickle
# הפעל שוב להתחבר מחדש
```

### "WhatsApp API error"
- בדוק שה-API token תקף
- בדוק את ה-phone number ID
- וודא שהיוםן לו הרשאות נכונות

### "Database locked"
```bash
rm database/agent.db
# תוקן חדש יווצר בריצה הבאה
```

## 📝 עדכונים

### v1.1 (טוביואני)
- [ ] WebSocket real-time updates
- [ ] Webhook support for WhatsApp
- [ ] Multi-language support
- [ ] Export to Excel/PDF
- [ ] Custom task templates

## 📧 Support

לשאלות ובעיות, צור issue בגיט או בדוק את ה-logs.

---

**Made with ❤️ by Claude Code**
