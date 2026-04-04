# מחולל קרוסלות אוטומטי — Carousel Auto-Generator

כלי Python שסורק את אתר המגזין, יוצר קרוסלות סושיאל 8-שקפים דרך Claude API, ומעלה את הפלטים ל-Google Drive.

---

## מה הכלי עושה

1. **סריקה אוטומטית** — מזהה כתבות חדשות באתר פעם אחת (או יותר) ביום
2. **עיבוד ידני** — הדבק URL של כתבה ספציפית לעיבוד מיידי
3. **יצירת קרוסלה** — 8 שקפים בעברית + 8 JSONs + תקציר סושיאל
4. **שמירה מסודרת** — תיקיות לפי תאריך/כותרת מקומית ובDrive
5. **ממשק ניהול** — דשבורד אינטרנטי נוח להפעלה ומעקב

---

## התקנה (שרת Linux/VPS)

```bash
# שיבוט / העתקת הקבצים לשרת
cd /opt/carousel_tool

# סביבת Python
python3 -m venv venv
source venv/bin/activate

# התקנת תלויות
pip install -r requirements.txt

# הגדרת משתני סביבה
cp .env.example .env
nano .env   # מלא את המפתחות
```

---

## הגדרת Google Drive (פעם אחת)

1. פתח [Google Cloud Console](https://console.cloud.google.com)
2. צור פרויקט חדש
3. הפעל **Google Drive API**
4. צור **Service Account** (IAM & Admin → Service Accounts)
5. צור מפתח JSON → הורד ושמור בשרת
6. ב-Google Drive: צור תיקייה `carousels`
7. שתף אותה עם כתובת הAימייל של ה-Service Account (עריכה)
8. העתק את ה-ID מה-URL לקובץ `.env`

---

## הרצה

```bash
# הפעל את האפליקציה
source venv/bin/activate
python app.py
```

הדשבורד יהיה נגיש בכתובת: **http://[server-ip]:5000**

### להרצה ברקע (מומלץ לשרת):

```bash
# עם nohup
nohup python app.py > logs/app.log 2>&1 &

# עם systemd (מומלץ יותר)
# ראה: /etc/systemd/system/carousel-tool.service
```

---

## מבנה הפלטים

```
output/
└── 2025-01-15/
    └── שם הכתבה/
        ├── slide_1.json
        ├── slide_2.json
        ├── ...
        ├── slide_8.json
        └── social_copy_brief.docx
```

אותו מבנה נוצר גם ב-Google Drive תחת תיקיית ה-root.

---

## קבצים עיקריים

| קובץ | תפקיד |
|------|--------|
| `app.py` | שרת Flask + ממשק אינטרנטי |
| `worker.py` | מעבד משימות + מתזמן |
| `scraper.py` | גרידת כתבות מהאתר |
| `carousel_generator.py` | קריאה ל-Claude API + פרסור תגובה |
| `output_manager.py` | יצירת JSON + DOCX |
| `drive_uploader.py` | העלאה ל-Google Drive |
| `config.py` | ניהול הגדרות מקובץ `.env` |
| `state_manager.py` | מעקב אחר כתבות שעובדו + היסטוריית משימות |

---

## פתרון בעיות

**הכלי לא מוצא כתבות חדשות:** בדוק שה-`SCAN_URL` מצביע לעמוד רשימת כתבות. אם האתר משתמש ב-JavaScript לטעינה, הוסף את הכלי `playwright` ועדכן את `scraper.py`.

**שגיאת Claude API:** ודא שה-`ANTHROPIC_API_KEY` תקין ויש לך קרדיטים.

**שגיאת Google Drive:** ודא שה-Service Account שיתף גישה לתיקייה ושהמפתח תקין.
