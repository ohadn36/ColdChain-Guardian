# Rubric Traceability

| Course requirement | Implementation | Code evidence | Demo evidence |
| --- | --- | --- | --- |
| At least three emulator types | DHT, Door Button, Temperature Knob, Cooling Relay | `coldchain_guardian/emulators/` | Four panels in Emulator Console |
| Collect data from broker | Managed Paho subscriber | `mqtt_client.py`, `manager.py` | Live values arrive in dashboard |
| Write to local/cloud DB | SQLite persistence layer | `database/schema.sql`, `db_manager.py` | History tab loads stored rows |
| Process messages | Schema, shipment, timestamp, type, range validation | `validator.py` | Malformed data does not crash manager |
| Warning/Alarm messages | Transition-based rules and combined failure rule | `rules_engine.py` | 9°C WARNING, 11°C ALARM, failure ALARM |
| Main GUI live data | Cards and temperature chart | `gui/dashboard.py` | Values and graph update live |
| Info/Warning/Alarm status window | Color-coded alert table with ACK | `gui/dashboard.py` | Door INFO/WARNING and temperature ALARM |
| Local/Cloud DB | Three SQLite tables and indexes | `schema.sql` | Readings, alerts, actuator events |
| Project repository | Structured Python package, tests, launcher, README | entire repository | GitHub link in presentation |
| Short running-code video | Deterministic 2–3 minute script | `docs/demo-script.md` | Embedded MP4 in slide 10 |
| 10–12 minute presentation recording | 11-minute presentation plan | `PROJECT_PLAN_HE.md` | Recording link in presentation |
| DOCX and PDF summary | 5–7 page outline | `PROJECT_PLAN_HE.md` | Submitted DOCX and PDF |

The enumerated code sub-items total 27 points although the Project Code heading states 30. Repository quality, tests, configuration, logging, and one-command startup provide explicit evidence for the remaining unspecified quality points.

