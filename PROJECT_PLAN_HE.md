# ColdChain Guardian — תוכנית אב לפרויקט

## 1. מטרת הפרויקט

**ColdChain Guardian – IoT Monitoring and Control System for Temperature-Sensitive Shipments**

המערכת תדמה תא קירור של משלוח רגיש לטמפרטורה. אמולטורים יפיקו נתוני חיישנים ואירועים, יעבירו אותם דרך MQTT מקומי, ו־Data Manager יאמת, יעבד וישמור אותם ב־SQLite. מנוע חוקים ייצור הודעות `INFO`, `WARNING` ו־`ALARM`, ישלוט בממסר קירור, וה־GUI יציג נתונים, גרף, מצבים, התראות והיסטוריה בזמן אמת.

הפרויקט נבנה כך שכל דרישה בקורס ניתנת להוכחה במסך, בקוד, בבסיס הנתונים ובתרחיש הדגמה קצר וברור.

## 2. גבולות והנחות עבודה

- כל הפיתוח וההרצה יהיו מקומיים.
- מסלול ההדגמה הראשי לא יהיה תלוי באינטרנט או בשירות ענן.
- לא תתבצע מתוך העבודה הזו העלאה ל־GitHub, לאחסון וידאו או לשירות חיצוני. נכין Repository וקבצים מקומיים מוכנים לפרסום, והקישורים יתווספו רק בשלב שהמשתמש יבחר לבצע זאת.
- לא תתבצע גישה למערכות או למידע של NVIDIA.
- נבנה עבור משלוח אחד: `shipment01`. תמיכה במספר משלוחים אינה חלק מהגרסה הנדרשת.
- ערכי 2–8°C הם ספי הדגמה ניתנים לשינוי, ולא טענה רפואית או רגולטורית.
- שפת הקוד, המצגת ומסמכי ההגשה תהיה אנגלית; מסמכי תכנון פנימיים יכולים להיות בעברית.

## 3. Scope סופי

### בתוך הפרויקט

- ארבעה סוגי אמולטורים: DHT, Door Button, Temperature Knob ו־Cooling Relay.
- MQTT Broker מקומי.
- Data Manager עם validation, state management, rules, alerts, actuator commands ו־logging.
- SQLite עם readings, alerts ו־actuator events.
- GUI ראשי מלוטש עם Dashboard ו־History.
- AUTO/MANUAL, acknowledgement והתאוששות למצב דמו התחלתי.
- בדיקות יחידה, אינטגרציה ותרחיש end-to-end.
- README, תרשימי ארכיטקטורה, הוראות הרצה ותסריט דמו.
- מצגת PowerPoint בת 11 שקופיות.
- סרטון דמו קצר שיוטמע במצגת.
- תסריט והקלטת מצגת באורך 10–12 דקות.
- Project Summary בקובצי DOCX ו־PDF.

### מחוץ לפרויקט

- חומרה אמיתית, AI/ML, אפליקציה סלולרית, Web app, משתמשים והרשאות.
- Cloud DB, Docker, Kubernetes, microservices, GPS, מפות, SMS או אימייל.
- תמיכה ב־multi-shipment או analytics מתקדמים.

## 4. החלטות טכנולוגיות

| תחום | החלטה |
| --- | --- |
| שפה | Python 3.11+ |
| GUI | PySide6 |
| גרף | pyqtgraph |
| MQTT client | paho-mqtt |
| Broker | Mosquitto מקומי על `localhost:1883` |
| Database | SQLite דרך `sqlite3` |
| Configuration | YAML דרך PyYAML |
| Tests | pytest |
| Logging | מודול `logging` של Python |
| Time format | ISO 8601 עם timezone |
| Payload | JSON, `schema_version: 1` |

PySide6 נבחר כדי להימנע מערבוב בין PyQt5/PySide6 ולבנות GUI מודרני תחת רישיון LGPL. ה־broker יהיה מקומי; אפשרות host configurable תישמר, אבל חיבור ל־broker חיצוני אינו חלק ממסלול ההדגמה.

## 5. ארכיטקטורה ותהליכים

```text
Emulator Console
  ├─ DHT Emulator
  ├─ Door Button Emulator
  ├─ Temperature Knob Emulator
  └─ Cooling Relay Emulator
           │
           ▼
  Local Mosquitto Broker
           │
           ▼
      Data Manager
  validation → state → rules
       │         │        │
       ▼         ▼        ▼
    SQLite   MQTT state  MQTT commands/alerts
       │         │
       └────┬────┘
            ▼
         Main GUI
```

תהליכי ההרצה יהיו:

1. Mosquitto broker מקומי.
2. Data Manager.
3. Emulator Console.
4. Main GUI.

`run_system.py` יבדוק שה־broker זמין ויפעיל את שלושת תהליכי Python. הוא לא יהרוג broker שלא הופעל על ידו.

## 6. ארבעת האמולטורים

### DHT Emulator

- מפרסם temperature ו־humidity במחזור קבוע, ברירת מחדל כל 2 שניות.
- מתחיל סביב 5°C ו־45%.
- תומך בשינוי איטי טבעי וב־manual override.

### Door Button Emulator

- כפתור Toggle בין `OPEN` ו־`CLOSED`.
- מפרסם רק בשינוי מצב וגם מפרסם initial state בעלייה.

### Temperature Knob Emulator

- Slider/Knob בטווח ‎-5°C עד 20°C.
- אינו מפרסם ישירות ל־topic של חיישן הטמפרטורה.
- מפרסם פקודת override ל־DHT דרך MQTT, וה־DHT הוא שמפרסם את הקריאה הסופית. כך אין שני publishers סותרים לאותו sensor.
- כולל `Release Override` לחזרה לסימולציה אוטומטית.

### Cooling Relay Emulator

- מאזין לפקודות `ON/OFF` דרך MQTT בלבד.
- מפרסם status בפועל לאחר קבלת פקודה.
- ה־GUI וה־Data Manager אינם משנים את מצב הממסר בזיכרון באופן ישיר.

ארבעת הרכיבים יוצגו בחלון Emulator Console אחד לנוחות הדמו, אך ימומשו כמחלקות/מודולים נפרדים וישתמשו ב־MQTT ביניהם.

## 7. MQTT Topics

Base topic: `coldchain/shipment01`

| Topic | Publisher | Subscriber | QoS/Retain | מטרה |
| --- | --- | --- | --- | --- |
| `/sensors/temperature` | DHT | Data Manager | 0 / no | קריאת טמפרטורה |
| `/sensors/humidity` | DHT | Data Manager | 0 / no | קריאת לחות |
| `/sensors/door` | Door | Data Manager | 1 / yes | מצב דלת |
| `/emulators/dht/override/set` | Knob | DHT | 1 / no | קביעת טמפרטורת דמו |
| `/emulators/dht/override/status` | DHT | Emulator Console | 1 / yes | מצב override |
| `/actuators/cooling/set` | Manager/GUI | Relay | 1 / no | פקודת ממסר |
| `/actuators/cooling/status` | Relay | Manager | 1 / yes | מצב ממסר בפועל |
| `/control/mode/set` | GUI | Manager | 1 / no | AUTO/MANUAL |
| `/state/snapshot` | Manager | GUI | 1 / yes | מצב מערכת מנורמל |
| `/alerts/events` | Manager | GUI | 1 / no | התראה חדשה |
| `/alerts/ack/set` | GUI | Manager | 1 / no | אישור התראה |
| `/demo/reset/set` | GUI | Manager/Emulators | 1 / no | חזרה למצב דמו בטוח |

Topics יוגדרו בקובץ מרכזי אחד ולא כמחרוזות מפוזרות בקוד. פקודות לא יהיו retained; מצבי sensor/actuator חשובים כן יהיו retained כשנדרש.

## 8. חוזי JSON

כל הודעה תכיל לפחות:

```json
{
  "schema_version": 1,
  "device_id": "temp_sensor_01",
  "shipment_id": "shipment01",
  "timestamp": "2026-09-09T21:30:00+03:00",
  "value": 5.4,
  "unit": "C"
}
```

הודעות state יכילו `state`; פקודות יכילו `command`; התראות יכילו `alert_id`, `severity`, `alert_type`, `message` ו־`acknowledged`.

Validation יבדוק JSON תקין, שדות חובה, shipment מתאים, timestamp תקין, value מספרי וטווחי safety סבירים. הודעה לא תקינה תירשם ללוג ותידחה בלי להפיל את המערכת.

## 9. מודל מצב ומנוע חוקים

### Temperature status

| תנאי | מצב |
| --- | --- |
| `2 <= temp <= 8` | NORMAL |
| `temp < 2` | WARNING_LOW |
| `8 < temp <= 10` | WARNING_HIGH |
| `temp > 10` | ALARM_HIGH |

### Cooling automation

- במצב AUTO: `temp > 8` מפעיל קירור.
- במצב AUTO: `temp < 7` מכבה קירור.
- הפער הוא hysteresis מכוון.
- במצב MANUAL רק פקודות המשתמש קובעות את הממסר.

### Door

- מעבר ל־OPEN יוצר INFO פעם אחת.
- OPEN במשך יותר מ־10 שניות יוצר WARNING פעם אחת.
- סגירה מאפסת את timer הדלת ויוצרת INFO.

### Humidity

- `20% <= humidity <= 70%`: NORMAL.
- מחוץ לטווח: WARNING.

### Combined rule

אם הקירור ON, הטמפרטורה מעל 8°C ושלוש הקריאות האחרונות עולות ברצף, נוצרת:

```text
ALARM — Possible Cooling System Failure
```

### Alert lifecycle

- רמות ההתראה בקוד וב־GUI: `INFO`, `WARNING`, `ALARM`.
- `ALARM` יוצג גם כ־“Critical Alarm” כדי לקשור בין שני המונחים.
- מנגנון state transition/deduplication ימנע יצירת התראה חדשה בכל קריאה זהה.
- alert חדש נשמר ב־DB, מפורסם ב־MQTT ומופיע ב־GUI.
- ACK משנה את הרשומה ב־DB ומעדכן את ה־GUI; הוא אינו מוחק את ההתראה.

## 10. SQLite

### `sensor_readings`

`id, timestamp, shipment_id, device_id, sensor_type, value, unit`

### `alerts`

`id, timestamp, shipment_id, severity, alert_type, message, acknowledged, acknowledged_at`

### `actuator_events`

`id, timestamp, shipment_id, device_id, state, source`

`source` יהיה `AUTO`, `MANUAL` או `RESET`. יוגדרו indexes על timestamp ועל acknowledged. כל write יתבצע דרך שכבת DB אחת ועם parameterized SQL.

## 11. Main GUI

חלון אחד עם שני tabs:

### Dashboard

- Header: project name, shipment ID, MQTT/DB status ו־AUTO/MANUAL.
- ארבעה status cards: Temperature, Humidity, Door, Cooling.
- Temperature chart חי עם קווי 2°C, 8°C ו־10°C.
- טבלת alerts אחרונים: Time, Severity, Event, ACK.
- בורר AUTO/MANUAL.
- Cooling ON/OFF, פעיל רק ב־MANUAL.
- Acknowledge selected alert.
- Reset Demo.

### History

- קריאה אמיתית מ־SQLite, לא מהזיכרון של ה־GUI.
- readings אחרונים, alerts קודמים ו־actuator events.
- Refresh ו־time range בסיסי.

צבעים קבועים: ירוק NORMAL, כחול INFO, כתום WARNING, אדום ALARM ואפור DISCONNECTED/UNKNOWN.

## 12. משמעות Reset Demo

Reset Demo יבצע דרך MQTT:

- DHT override ל־5°C ו־45%.
- Door ל־CLOSED.
- Mode ל־AUTO.
- Cooling ל־OFF.
- איפוס timers ו־active-rule states.

הפעולה לא תמחק היסטוריה מה־DB. לפני הקלטה ניתן להריץ כלי מקומי נפרד ליצירת DB נקי; מחיקה לא תהיה כפתור רגיל ב־GUI.

## 13. מבנה Repository מתוכנן

```text
coldchain-guardian/
├── coldchain_guardian/
│   ├── config.py
│   ├── contracts.py
│   ├── topics.py
│   ├── mqtt_client.py
│   ├── emulators/
│   │   ├── dht.py
│   │   ├── door_button.py
│   │   ├── temperature_knob.py
│   │   ├── cooling_relay.py
│   │   └── console.py
│   ├── data_manager/
│   │   ├── manager.py
│   │   ├── validator.py
│   │   └── rules_engine.py
│   ├── database/
│   │   ├── db_manager.py
│   │   └── schema.sql
│   └── gui/
│       ├── main_window.py
│       ├── dashboard.py
│       └── history.py
├── config/
│   ├── config.yaml
│   └── mosquitto.conf
├── data/
├── logs/
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   ├── architecture.md
│   ├── mqtt-contracts.md
│   ├── demo-script.md
│   └── rubric-traceability.md
├── deliverables/
│   ├── presentation/
│   ├── videos/
│   └── summary/
├── run_system.py
├── requirements.txt
├── pyproject.toml
├── README.md
└── .gitignore
```

## 14. שלבי ביצוע וקריטריוני קבלה

| שלב | עבודה | קריטריון קבלה | הערכה |
| --- | --- | --- | ---: |
| 0 | קיבוע מפרט ותלויות | אין החלטות ארכיטקטורה פתוחות | 1–2 ש׳ |
| 1 | skeleton, config, topics, contracts, schema | imports עובדים ו־DB נוצר | 2–3 ש׳ |
| 2 | MQTT wrapper וארבעת האמולטורים | כל payload נראה ב־broker המקומי | 4–5 ש׳ |
| 3 | DB, validator, rules ו־Data Manager | readings/alerts/events נשמרים נכון | 4–6 ש׳ |
| 4 | Dashboard GUI וגרף | נתונים וסטטוסים מתעדכנים בזמן אמת | 5–7 ש׳ |
| 5 | Relay flow, AUTO/MANUAL, ACK, reset, history | שתי שרשראות ה־Definition of Done עובדות | 4–6 ש׳ |
| 6 | Unit/integration/E2E tests ותיקוני יציבות | כל הבדיקות ותרחיש הדמו עוברים | 3–5 ש׳ |
| 7 | README, diagrams, cleanup | התקנה והרצה ברורות ממחשב נקי | 2–4 ש׳ |
| 8 | צילום סרטון דמו קצר | MP4 של 2–3 דקות, קריא וללא תקלות | 2–3 ש׳ |
| 9 | מצגת, הקלטה וסיכום | PPTX, recording 10–12 min, DOCX ו־PDF | 6–9 ש׳ |

סה״כ משוער: 33–50 שעות, כולל ליטוש, תיעוד והקלטות. אין לעבור שלב לפני שקריטריון הקבלה של השלב הקודם עובד.

## 15. תוכנית בדיקות

### Unit

- גבולות temperature: 1.9, 2.0, 8.0, 8.1, 10.0, 10.1.
- humidity בתוך ומחוץ לטווח.
- door timer ו־deduplication.
- combined rule עם רצף עולה ושאינו עולה.
- validation של JSON תקין, חסר ומושחת.
- insert/query/ack לכל טבלאות ה־DB.

### Integration

- Sensor MQTT → Manager → SQLite → state/alert MQTT.
- Manager/GUI command → Relay → status → Manager → SQLite/GUI.
- restart של רכיב וחזרה לעבודה בלי crash.

### End-to-end

תרחיש ההדגמה המלא יתבצע שלוש פעמים רצופות ללא שינוי ידני בקוד וללא ניקוי כפוי באמצע.

## 16. תרחיש הדגמה קצר

1. Reset: 5°C, 45%, door closed, cooling off, AUTO.
2. Knob ל־9°C: WARNING + cooling ON + DB record.
3. Knob ל־11°C: ALARM + relay status ON.
4. Door OPEN: INFO; לאחר 10 שניות WARNING.
5. כאשר cooling ON, הזנת 9→10→11→12: cooling failure ALARM.
6. ACK להתראה.
7. מעבר ל־MANUAL ושליחת OFF/ON דרך MQTT.
8. History: הצגת readings, alerts ו־actuator events מתוך SQLite.

## 17. מצגת — 11 שקופיות

1. Title, student details, project links.
2. Problem statement and project goal.
3. Course requirements and solution mapping.
4. System architecture and data flow.
5. Four IoT emulators.
6. MQTT topics and JSON messages.
7. Data Manager and rules engine.
8. SQLite schema and persistence.
9. Main GUI and alert levels.
10. Tests, deterministic demo and embedded 2–3 minute code-running video.
11. Results, limitations, conclusion, GitHub link and presentation-recording link.

יש להטמיע את הסרטון הקצר בתוך ה־PPTX ולבדוק אותו במחשב אחר. קישור ההקלטה יוצג גם כ־hyperlink וגם כ־QR code, לאחר שהמשתמש יפרסם אותו מחוץ לתהליך המקומי.

## 18. חלוקת הקלטת המצגת — 10–12 דקות

| זמן | תוכן |
| --- | --- |
| 0:00–0:45 | פתיחה, הבעיה והמטרה |
| 0:45–1:40 | דרישות הקורס והמיפוי |
| 1:40–3:00 | ארכיטקטורה וזרימת מידע |
| 3:00–4:10 | ארבעת האמולטורים ו־MQTT |
| 4:10–5:30 | Data Manager, validation וחוקים |
| 5:30–6:20 | SQLite ו־history |
| 6:20–9:20 | סרטון/דמו עובד |
| 9:20–10:20 | בדיקות, יציבות ותוצאות |
| 10:20–11:10 | סיכום וקישורים |

יעד ההקלטה: כ־11 דקות, כדי להשאיר מרווח בטוח בתוך 10–12 דקות.

## 19. Project Summary — DOCX ו־PDF

מסמך של כ־5–7 עמודים:

1. Cover page.
2. Abstract, problem and objectives.
3. Architecture and components.
4. MQTT contracts, Data Manager and rules.
5. Database and GUI.
6. Testing and demonstration results.
7. Conclusions, limitations and repository link.

ה־DOCX יהיה מסמך המקור וה־PDF ייוצר ממנו. שניהם יעברו בדיקת render חזותית לפני הגשה.

## 20. Rubric Traceability

| דרישה | מימוש | הוכחה בהגשה |
| --- | --- | --- |
| 3+ emulator types — 6 | DHT, Door Button, Knob, Relay | Emulator Console + קוד + שקופית 5 |
| Data Manager — 8 | MQTT, validation, DB, processing, warnings/alarms | לוג, DB, שקופית 7 ודמו |
| Main GUI — 10 | cards, graph, alert panel, controls, history | שקופית 9 וסרטון |
| Local/Cloud DB — 3 | SQLite עם 3 טבלאות | History + schema + שקופית 8 |
| Project code — 30 | repo מסודר, README, tests, launcher | Repository link |
| Presentation — 9 | 11 שקופיות + סרטון מוטמע | PPTX |
| Recording — 8 | הקלטה באורך 10–12 דקות | link בשקופיות 1 ו־11 |
| Summary — 3 | אותו תוכן ב־DOCX וב־PDF | שני קבצים |

תתי־הסעיפים המפורטים של הקוד מסתכמים ב־27 מתוך 30. שלוש הנקודות שאינן מפורטות יכוסו ככל האפשר באמצעות README איכותי, מבנה repository נקי, בדיקות, launcher ותיעוד.

## 21. סיכונים והפחתה

| סיכון | טיפול |
| --- | --- |
| Mosquitto לא מותקן או port 1883 תפוס | preflight check והודעת שגיאה ברורה |
| תלות באינטרנט בזמן הדמו | localhost בלבד וכל הקבצים נשמרים מקומית |
| כפילות alerts בכל reading | state transitions ו־deduplication |
| race בין timers ל־MQTT | state lock ו־timer מרכזי ב־Manager |
| DHT ו־Knob מפרסמים ערכים סותרים | Knob שולח override ל־DHT; רק DHT מפרסם reading |
| GUI קופא בגלל callbacks | Qt signals/queue; ללא שינוי widgets מתוך MQTT thread |
| Reset מוחק היסטוריה בטעות | reset תפעולי אינו מוחק DB |
| הסרטון לא מתנגן ב־PowerPoint | MP4 H.264, embed ובדיקה במחשב נוסף |
| אין עדיין URLs להגשה | placeholders ברורים; המשתמש מוסיף links לאחר פרסום עצמאי |

## 22. Definition of Done

הפרויקט גמור רק כאשר:

- כל ארבעת האמולטורים נראים ועובדים דרך MQTT.
- השרשרת `Emulator → MQTT → Manager → Rules → SQLite → Alert → GUI` הוכחה.
- השרשרת `GUI/Rules → MQTT command → Relay → MQTT status → Manager → SQLite → GUI` הוכחה.
- AUTO/MANUAL, ACK, Reset ו־History עובדים.
- אין crash על payload לא תקין או על ניתוק/חיבור מחדש.
- unit, integration ותרחיש end-to-end עוברים.
- README מאפשר התקנה והרצה ברורות.
- הסרטון הקצר מוטמע ונבדק במצגת.
- המצגת מכילה 10–12 שקופיות וההקלטה באורך 10–12 דקות.
- DOCX ו־PDF תואמים ונבדקו חזותית.
- GitHub והקלטה מופיעים כקישורים תקינים לאחר שהמשתמש מפרסם אותם.

## 23. סדר העבודה המחייב

הצעד הבא הוא Phase 1 בלבד: ליצור את שלד ה־repository, config, topic registry, JSON contracts, schema וסט בדיקות ראשוני. אין להתחיל ב־GUI לפני שה־MQTT contracts, ה־DB ומנוע החוקים יציבים.
