# Tendrill

Hybrid-Supervisor für automatisiertes Grow-Monitoring. Kombiniert regelbasierte Logik mit ML-Erweiterbarkeit.

## Was ist Tendrill?

Ein System das Sensordaten (Temperatur, Luftfeuchtigkeit, CO2, Licht) entgegennimmt, gegen definierte Wachstumsphasen-Parameter prüft und Entscheidungen trifft oder Aktoren steuert.

**Phase 1:** Regelwerk + strukturierte Wissensdatenbank  
**Phase 2:** ML-Layer für Anomalie-Erkennung und Optimierung

## Features (geplant)

- [ ] Phasen-Management (Vegetativ, Blüte, Flush, etc.)
- [ ] Parameterdefinition pro Phase (Licht, Temp, Humidity, Nährstoffe)
- [ ] Sensor-Ingestion (MQTT, REST)
- [ ] Regel-Engine für Alarme und Aktionen
- [ ] Aktor-Steuerung (Pumpen, Ventile, Dimmer, Lüfter)
- [ ] Dashboard / API
- [ ] ML-basierte Anomalie-Erkennung (Phase 2)

## Tech Stack

- **Backend:** Python (FastAPI)
- **Datenbank:** PostgreSQL + TimescaleDB (Zeitreihen)
- **Message Broker:** MQTT (Mosquitto)
- **ML:** scikit-learn / PyTorch (später)
- **Deployment:** Docker Compose

## Projektstruktur

```
tendrill/
├── README.md
├── LICENSE
├── .gitignore
├── docker-compose.yml
├── pyproject.toml
│
├── src/
│   └── tendrill/
│       ├── __init__.py
│       ├── main.py              # FastAPI Entry
│       ├── config.py            # Settings
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── phases.py        # Wachstumsphasen-Logik
│       │   ├── rules.py         # Regel-Engine
│       │   └── scheduler.py     # Zeitbasierte Trigger
│       │
│       ├── sensors/
│       │   ├── __init__.py
│       │   ├── mqtt.py          # MQTT Client
│       │   ├── models.py        # Sensor-Datenmodelle
│       │   └── ingestion.py     # Daten-Eingang
│       │
│       ├── actuators/
│       │   ├── __init__.py
│       │   ├── controller.py    # Aktor-Steuerung
│       │   └── devices.py       # Geräte-Definitionen
│       │
│       ├── knowledge/
│       │   ├── __init__.py
│       │   ├── schemas.py       # Pydantic Schemas
│       │   └── defaults.py      # Standard-Parameter
│       │
│       ├── ml/                  # Phase 2
│       │   ├── __init__.py
│       │   ├── anomaly.py
│       │   └── training.py
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── routes.py
│       │   └── websocket.py
│       │
│       └── db/
│           ├── __init__.py
│           ├── models.py        # SQLAlchemy Models
│           └── repository.py
│
├── data/
│   └── knowledge/
│       ├── phases.yaml          # Phasen-Definitionen
│       ├── nutrients.yaml       # Nährstoff-Profile
│       └── strains.yaml         # Sorten-spezifische Params
│
├── tests/
│   └── ...
│
└── docs/
    └── ...
```

## Quickstart

```bash
git clone https://github.com/DEIN-USERNAME/tendrill.git
cd tendrill
docker-compose up -d
```

## Lizenz

Proprietary – All rights reserved.

---

*Tendrill – Die Ranke die alles im Griff hat.*
