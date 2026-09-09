# ColdChain Guardian

ColdChain Guardian is a local-first IoT monitoring and control system for a simulated temperature-sensitive shipment.

The project is currently under active development. Its planned data path is:

```text
IoT emulators → MQTT → Data Manager → Rules → SQLite → Main GUI
```

The deterministic demonstration runs against a local Mosquitto broker and does not require a cloud service.

See [PROJECT_PLAN_HE.md](PROJECT_PLAN_HE.md) for the complete implementation and delivery plan.

