# 🚀 מדריך התקנה מלא - WhatsApp + Gmail Agent

## 📋 סטטוס כרגע

✅ **סיים:**
- Gmail OAuth 2.0 מוגדר בהצלחה
- credentials.json בנקום הנכון
- כל הקוד בדוק ופועל
- Flask Dashboard מוכן
- Database Schema מוגדר

⏳ **צריך עכשיו:**
1. **Anthropic API Key** (חובה)
2. **WhatsApp Business API** (אופציונאלי - כדי לקרוא הודעות מ-WhatsApp)

---

## 1️⃣ קבלת Anthropic API Key (5 דקות)

### צעדים:
1. עבור ל: https://console.anthropic.com/api/keys
2. התחבר עם חשבונך (או צור חשבון)
3. לחץ "Create Key" או "Generate API Key"
4. העתק את המפתח
5. עדכן את `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
```

---

## 2️⃣ WhatsApp Business API (אופציונאלי - 15 דקות)

אם אתה רוצה לקרוא הודעות מ-WhatsApp:

### צעדים:
1. עבור ל: https://developers.facebook.com/
2. לחץ "My Apps" → "Create App"
3. בחר "Business" app type
4. קראו "WhatsApp" product
5. בחרו את מספר הטלפון שלך
6. העתק:
   - Access Token → `WHATSAPP_API_TOKEN`
   - Phone Number ID → `WHATSAPP_PHONE_NUMBER_ID`
   - Business Account ID → `WHATSAPP_BUSINESS_ACCOUNT_ID`

7. עדכן את `.env`:

```bash
WHATSAPP_API_TOKEN=EAA...
WHATSAPP_PHONE_NUMBER_ID=1234567890
WHATSAPP_BUSINESS_ACCOUNT_ID=9876543210
```

---

## 3️⃣ הרצת הסוכן

### Windows:
```bash
cd whatsapp_agent
run.bat
```

### Mac/Linux:
```bash
cd whatsapp_agent
bash run.sh
```

### Manual:
```bash
cd whatsapp_agent
python main.py
```

אתה אמור לראות:
```
 * Running on http://0.0.0.0:5000
```

---

## 4️⃣ בדיקת הדאשבורד

פתח דפדפן:
```
http://localhost:5000
```

אתה אמור לראות:
- 📊 Dashboard עברי
- 📬 סטטוסטיקה
- 📝 רשימת משימות
- 📧 הודעות

---

## 🧪 בדיקות

```bash
# בדוק שהכל עובד
python test_basic.py

# אם כל עברו: ✅ All tests passed!
```

---

## 🆘 בעיות נפוצות

### "ModuleNotFoundError"
```bash
pip install -r requirements.txt
```

### "ANTHROPIC_API_KEY not set"
```bash
# וודא שהערך למלא ב-.env
# אל תשאיר ריק!
ANTHROPIC_API_KEY=sk-ant-...שלך...
```

### "Gmail OAuth error"
```bash
# הסר טוקן ישן
rm token.pickle

# הרץ שוב - יבקש אישור
python main.py
```

---

## 📝 קבצים חשובים

```
whatsapp_agent/
├── .env                      ← עדכן זה עם מפתחות API
├── gmail_credentials.json     ← ✅ כבר מוגדר
├── main.py                   ← הרץ זה
├── config.py                 ← הגדרות
├── agent.py                  ← לוגיקת הסוכן
├── state_manager.py          ← מסד הנתונים
└── templates/
    └── dashboard.html        ← ה-UI
```

---

## 🎯 המטרה

כל שעה, הסוכן:
1. ✅ קורא הודעות מ-Gmail
2. ⏳ קורא הודעות מ-WhatsApp (אם מוגדר)
3. 📊 מחשב זמני מענה
4. 🔗 מחברת משימות שוות
5. 💾 שומר בדטהבייס
6. 📈 מעדכן דאשבורד

---

## ⚡ הפעלה בענן (אופציונאלי)

### Heroku:
```bash
heroku create myapp
heroku config:set ANTHROPIC_API_KEY=sk-ant-...
git push heroku main
heroku open
```

### Google Cloud:
```bash
gcloud functions deploy whatsapp_agent \
  --runtime python310 \
  --trigger-topic hourly-sync
```

---

**צריך עזרה? בדוק README.md או הוראות_התחלה.md**
