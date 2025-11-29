#!/usr/bin/env python3
"""
Tendrill Demo MQTT Publisher

Simuliert realistische Sensordaten für Debugging und Demo-Zwecke.
Publiziert Daten im gleichen Format wie echte ESP32-Sensoren.

Usage:
    python tools/demo_publisher.py
    python tools/demo_publisher.py --broker localhost --port 1883
    python tools/demo_publisher.py --phase flowering_mid --fast
"""

import argparse
import json
import math
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("paho-mqtt nicht installiert. Installiere mit: pip install paho-mqtt")
    sys.exit(1)


# Realistische Basis-Werte pro Phase
PHASE_DEFAULTS = {
    "germination": {
        "temp_day": 23, "temp_night": 20,
        "humidity": 80, "co2": 400, "vpd": 0.5,
        "ph": 6.0, "ec": 0.0, "water_temp": 20,
        "light_hours": 0, "light_ppfd": 0
    },
    "seedling": {
        "temp_day": 24, "temp_night": 20,
        "humidity": 70, "co2": 500, "vpd": 0.6,
        "ph": 6.0, "ec": 0.6, "water_temp": 20,
        "light_hours": 18, "light_ppfd": 300
    },
    "vegetative_early": {
        "temp_day": 25, "temp_night": 20,
        "humidity": 62, "co2": 600, "vpd": 0.95,
        "ph": 6.0, "ec": 1.0, "water_temp": 20,
        "light_hours": 18, "light_ppfd": 500
    },
    "vegetative_late": {
        "temp_day": 26, "temp_night": 20,
        "humidity": 58, "co2": 800, "vpd": 1.0,
        "ph": 6.0, "ec": 1.4, "water_temp": 20,
        "light_hours": 18, "light_ppfd": 750
    },
    "transition": {
        "temp_day": 25, "temp_night": 19,
        "humidity": 55, "co2": 900, "vpd": 1.1,
        "ph": 6.0, "ec": 1.6, "water_temp": 20,
        "light_hours": 12, "light_ppfd": 750
    },
    "flowering_early": {
        "temp_day": 24, "temp_night": 19,
        "humidity": 50, "co2": 1000, "vpd": 1.15,
        "ph": 6.2, "ec": 1.8, "water_temp": 19,
        "light_hours": 12, "light_ppfd": 850
    },
    "flowering_mid": {
        "temp_day": 24, "temp_night": 18,
        "humidity": 45, "co2": 1200, "vpd": 1.3,
        "ph": 6.2, "ec": 2.1, "water_temp": 19,
        "light_hours": 12, "light_ppfd": 1000
    },
    "flowering_late": {
        "temp_day": 22, "temp_night": 17,
        "humidity": 40, "co2": 1000, "vpd": 1.35,
        "ph": 6.2, "ec": 1.6, "water_temp": 19,
        "light_hours": 12, "light_ppfd": 900
    },
    "flush": {
        "temp_day": 20, "temp_night": 16,
        "humidity": 35, "co2": 400, "vpd": 1.4,
        "ph": 6.2, "ec": 0.0, "water_temp": 18,
        "light_hours": 12, "light_ppfd": 500
    },
    "drying": {
        "temp_day": 19, "temp_night": 18,
        "humidity": 60, "co2": 400, "vpd": 0.8,
        "ph": 0, "ec": 0, "water_temp": 0,
        "light_hours": 0, "light_ppfd": 0
    },
    "curing": {
        "temp_day": 20, "temp_night": 19,
        "humidity": 60, "co2": 400, "vpd": 0.7,
        "ph": 0, "ec": 0, "water_temp": 0,
        "light_hours": 0, "light_ppfd": 0
    },
}


class SensorSimulator:
    """Simuliert realistische Sensordaten mit natürlichen Schwankungen."""

    def __init__(self, phase: str = "vegetative_early"):
        self.phase = phase
        self.defaults = PHASE_DEFAULTS.get(phase, PHASE_DEFAULTS["vegetative_early"])
        self.time_offset = random.uniform(0, 24)  # Simulated time offset

        # Aktuelle Werte mit leichtem Offset
        self._temp = self.defaults["temp_day"]
        self._humidity = self.defaults["humidity"]
        self._co2 = self.defaults["co2"]
        self._ph = self.defaults["ph"]
        self._ec = self.defaults["ec"]
        self._water_temp = self.defaults["water_temp"]

    def _get_hour(self) -> float:
        """Gibt simulierte Stunde zurück (0-24)."""
        now = datetime.now()
        return (now.hour + now.minute / 60 + self.time_offset) % 24

    def _is_lights_on(self) -> bool:
        """Prüft ob Licht an ist basierend auf Zeitplan."""
        hour = self._get_hour()
        light_hours = self.defaults["light_hours"]

        if light_hours == 0:
            return False
        if light_hours >= 24:
            return True

        # Licht von 6:00 bis 6:00 + light_hours
        light_on = 6
        light_off = (light_on + light_hours) % 24

        if light_on < light_off:
            return light_on <= hour < light_off
        else:
            return hour >= light_on or hour < light_off

    def _add_noise(self, value: float, noise_range: float) -> float:
        """Fügt natürliches Rauschen hinzu."""
        return value + random.uniform(-noise_range, noise_range)

    def _smooth_transition(self, current: float, target: float, rate: float = 0.1) -> float:
        """Sanfter Übergang zwischen Werten."""
        return current + (target - rate) * rate

    def get_temperature(self) -> float:
        """Berechnet aktuelle Temperatur."""
        base = self.defaults["temp_day"] if self._is_lights_on() else self.defaults["temp_night"]

        # Langsame Drift
        self._temp = self._temp * 0.95 + base * 0.05

        # Kleines Rauschen
        return round(self._add_noise(self._temp, 0.3), 1)

    def get_humidity(self) -> float:
        """Berechnet aktuelle Luftfeuchtigkeit."""
        base = self.defaults["humidity"]

        # Inverse Korrelation mit Temperatur
        temp_factor = (self._temp - 22) * -0.5

        # Tageszeit-Effekt (nachts höher)
        time_factor = -3 if self._is_lights_on() else 3

        self._humidity = self._humidity * 0.9 + (base + temp_factor + time_factor) * 0.1
        return round(self._add_noise(self._humidity, 1.5), 1)

    def get_vpd(self) -> float:
        """Berechnet VPD basierend auf Temp und Humidity."""
        temp = self._temp
        humidity = self._humidity

        # Tetens-Formel für Sättigungsdampfdruck
        svp = 0.6108 * math.exp((17.27 * temp) / (temp + 237.3))
        avp = svp * (humidity / 100)

        # Blatt ist ca. 2°C kühler
        leaf_temp = temp - 2
        svp_leaf = 0.6108 * math.exp((17.27 * leaf_temp) / (leaf_temp + 237.3))

        vpd = svp_leaf - avp
        return round(max(0.1, vpd), 2)

    def get_co2(self) -> float:
        """Berechnet CO2-Level."""
        base = self.defaults["co2"]

        # CO2 sinkt wenn Licht an (Photosynthese)
        light_factor = -50 if self._is_lights_on() else 30

        self._co2 = self._co2 * 0.95 + (base + light_factor) * 0.05
        return round(self._add_noise(self._co2, 20))

    def get_light_ppfd(self) -> int:
        """Berechnet Licht PPFD."""
        if not self._is_lights_on():
            return 0

        base = self.defaults["light_ppfd"]
        # Leichtes Flackern
        return round(self._add_noise(base, base * 0.02))

    def get_ph(self) -> float:
        """Berechnet pH-Wert."""
        if self.defaults["ph"] == 0:
            return 0

        base = self.defaults["ph"]
        # Langsame Drift (pH steigt tendenziell)
        self._ph = self._ph * 0.99 + (base + 0.05) * 0.01
        return round(self._add_noise(self._ph, 0.05), 2)

    def get_ec(self) -> float:
        """Berechnet EC-Wert."""
        if self.defaults["ec"] == 0:
            return 0

        base = self.defaults["ec"]
        # EC steigt durch Verdunstung
        self._ec = self._ec * 0.99 + (base + 0.02) * 0.01
        return round(self._add_noise(self._ec, 0.03), 2)

    def get_water_temp(self) -> float:
        """Berechnet Wassertemperatur."""
        if self.defaults["water_temp"] == 0:
            return 0

        base = self.defaults["water_temp"]
        # Folgt Raumtemperatur langsam
        self._water_temp = self._water_temp * 0.98 + (self._temp - 4) * 0.02
        return round(self._add_noise(self._water_temp, 0.2), 1)

    def get_all_readings(self) -> dict:
        """Holt alle Sensorwerte."""
        readings = {
            "temperature": self.get_temperature(),
            "humidity": self.get_humidity(),
            "vpd": self.get_vpd(),
            "co2": self.get_co2(),
            "light_ppfd": self.get_light_ppfd(),
        }

        # Nur wenn relevant für Phase
        if self.defaults["ph"] > 0:
            readings["ph"] = self.get_ph()
        if self.defaults["ec"] > 0:
            readings["ec"] = self.get_ec()
        if self.defaults["water_temp"] > 0:
            readings["water_temperature"] = self.get_water_temp()

        return readings


class DemoPublisher:
    """MQTT Publisher für Demo-Sensordaten."""

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        device_id: str = "demo-sensor-01",
        zone_id: str = "demo-zone",
        phase: str = "vegetative_early",
    ):
        self.broker = broker
        self.port = port
        self.device_id = device_id
        self.zone_id = zone_id
        self.phase = phase

        self.simulator = SensorSimulator(phase)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.connected = False

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"[MQTT] Verbunden mit {self.broker}:{self.port}")
            self.connected = True
        else:
            print(f"[MQTT] Verbindung fehlgeschlagen: {reason_code}")

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        print(f"[MQTT] Verbindung getrennt")
        self.connected = False

    def connect(self) -> bool:
        """Verbindet mit MQTT Broker."""
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()

            # Warte auf Verbindung
            for _ in range(50):  # 5 Sekunden
                if self.connected:
                    return True
                time.sleep(0.1)

            print(f"[MQTT] Timeout beim Verbinden")
            return False

        except Exception as e:
            print(f"[MQTT] Fehler: {e}")
            return False

    def disconnect(self):
        """Trennt MQTT Verbindung."""
        self.client.loop_stop()
        self.client.disconnect()

    def publish_reading(self):
        """Publiziert einen Sensor-Reading."""
        readings = self.simulator.get_all_readings()

        # Standard-Format (wie echte ESP32)
        payload = {
            "device_id": self.device_id,
            "zone_id": self.zone_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "readings": [
                {"type": k, "value": v, "unit": self._get_unit(k)}
                for k, v in readings.items()
            ],
            "status": "online",
            "firmware_version": "demo-1.0.0"
        }

        topic = f"tendrill/sensors/{self.device_id}/data"
        self.client.publish(topic, json.dumps(payload), qos=1)

        return readings

    def _get_unit(self, sensor_type: str) -> str:
        """Gibt die Einheit für einen Sensortyp zurück."""
        units = {
            "temperature": "°C",
            "humidity": "%",
            "vpd": "kPa",
            "co2": "ppm",
            "light_ppfd": "µmol/m²/s",
            "ph": "pH",
            "ec": "mS/cm",
            "water_temperature": "°C",
        }
        return units.get(sensor_type, "")


def main():
    parser = argparse.ArgumentParser(description="Tendrill Demo MQTT Publisher")
    parser.add_argument("--broker", default="localhost", help="MQTT Broker Host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT Broker Port")
    parser.add_argument("--device", default="demo-sensor-01", help="Device ID")
    parser.add_argument("--zone", default="demo-zone", help="Zone ID")
    parser.add_argument("--phase", default="vegetative_early",
                        choices=list(PHASE_DEFAULTS.keys()), help="Grow Phase")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Publish Interval in Sekunden")
    parser.add_argument("--fast", action="store_true",
                        help="Schneller Modus (1 Sekunde)")
    args = parser.parse_args()

    interval = 1.0 if args.fast else args.interval

    print(f"""
========================================================
           TENDRILL DEMO PUBLISHER
========================================================
  Broker:   {args.broker}:{args.port}
  Device:   {args.device}
  Zone:     {args.zone}
  Phase:    {args.phase}
  Interval: {interval}s
========================================================
    """)

    publisher = DemoPublisher(
        broker=args.broker,
        port=args.port,
        device_id=args.device,
        zone_id=args.zone,
        phase=args.phase,
    )

    if not publisher.connect():
        print("\n[ERROR] Konnte nicht mit MQTT Broker verbinden.")
        print("        Stelle sicher dass Mosquitto läuft:")
        print("        docker run -d -p 1883:1883 eclipse-mosquitto:2")
        sys.exit(1)

    print("\n[INFO] Starte Publishing... (Ctrl+C zum Beenden)\n")

    try:
        count = 0
        while True:
            readings = publisher.publish_reading()
            count += 1

            # Kompakte Ausgabe
            temp = readings.get("temperature", 0)
            hum = readings.get("humidity", 0)
            vpd = readings.get("vpd", 0)
            co2 = readings.get("co2", 0)

            print(f"[{count:4}] T:{temp:5.1f}°C  H:{hum:5.1f}%  "
                  f"VPD:{vpd:4.2f}kPa  CO2:{co2:4.0f}ppm")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n[INFO] Beende Publisher...")
    finally:
        publisher.disconnect()
        print("[INFO] Fertig.")


if __name__ == "__main__":
    main()
