# Deterministic Demo Script

Target duration: 2–3 minutes for the short embedded video.

## Preparation

1. Run `python run_system.py --check`.
2. Run `python run_system.py`.
3. Place the Emulator Console and Main GUI side by side.
4. Press **RESET DEMO** and wait for all four emulators to report connected.

## Recording sequence

| Time | Action | Visible proof |
| --- | --- | --- |
| 0:00–0:15 | Show both windows | Four emulator types and connected system |
| 0:15–0:30 | Show 5°C, 45%, CLOSED, OFF | Normal baseline |
| 0:30–0:50 | Set Knob to 9°C | WARNING, graph change, cooling command and Relay ON |
| 0:50–1:05 | Set Knob to 11°C | Critical high-temperature ALARM |
| 1:05–1:25 | Open Door and wait 10 seconds | INFO followed by Door Open Too Long WARNING |
| 1:25–1:45 | Apply 9, 10, 11, 12°C while cooling ON | Possible Cooling System Failure ALARM |
| 1:45–2:00 | ACK one alert | Alert changes to acknowledged |
| 2:00–2:20 | Switch to MANUAL and send OFF then ON | Commands travel through MQTT; confirmed Relay changes |
| 2:20–2:40 | Open History | SQLite readings, alerts, and actuator events |
| 2:40–2:50 | Return to dashboard | Final working system view |

## Recording checklist

- Use 1080p or higher.
- Keep text at a readable scale.
- Hide unrelated applications and notifications.
- Show no credentials or personal data.
- Use MP4 with H.264 video for PowerPoint compatibility.
- Keep the cursor movement deliberate and avoid editing code during the recording.
- Perform the full sequence once without recording before capturing the final take.

