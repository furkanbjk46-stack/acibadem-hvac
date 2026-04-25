# belimo_collector.py
# Belimo vanalarından Modbus TCP ile periyodik veri toplar, CSV'ye kaydeder.
# Portal ile entegre çalışır; ayrıca standalone kullanılabilir.
# Gereksinim: pip install pymodbus

from __future__ import annotations

import csv
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "configs" / "belimo_config.json"
DATA_FILE   = BASE_DIR / "belimo_data.csv"

# ── Varsayılan yapılandırma ───────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "interval_seconds": 60,
    "data_file": str(DATA_FILE),
    "devices": [
        {
            "name": "AHU-03 Isitma Vanasi",
            "ip": "192.168.0.35",
            "port": 502,
            "slave": 1,
            "enabled": True,
            "holding_count": 10,
            "input_count": 10,
            "fields": {
                "holding": {
                    "0": {"label": "Setpoint",        "scale": 0.1, "unit": "%"},
                    "1": {"label": "Kontrol Modu",    "scale": 1,   "unit": ""},
                },
                "input": {
                    "0": {"label": "Vana Pozisyon",   "scale": 0.1, "unit": "%"},
                    "1": {"label": "Hacimsel Debi",   "scale": 1,   "unit": "l/h"},
                    "2": {"label": "T Giris",         "scale": 0.1, "unit": "°C"},
                    "3": {"label": "T Donus",         "scale": 0.1, "unit": "°C"},
                    "4": {"label": "DeltaT",          "scale": 0.1, "unit": "K"},
                    "5": {"label": "Is Gucu",         "scale": 0.1, "unit": "kW"},
                },
            },
        }
    ],
}

# CSV başlık sütunları (sabit + cihaz başına dinamik)
CSV_META_COLS = ["timestamp", "device_name", "ip", "baglanti"]

# ── Yardımcı fonksiyonlar ─────────────────────────────────


def _load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"belimo_config.json okunamadı, varsayılan kullanılıyor: {e}")
    return DEFAULT_CONFIG


def _save_default_config() -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        logger.info(f"Varsayılan yapılandırma oluşturuldu: {CONFIG_FILE}")


def _modbus_kwargs(major: int, slave: int) -> dict:
    return {"slave": slave} if major >= 3 else {"unit": slave}


def _pymodbus_major() -> int:
    try:
        import pymodbus
        return int(pymodbus.__version__.split(".")[0])
    except Exception:
        return 3


# ── Cihaz okuma ───────────────────────────────────────────


def oku_cihaz(device: dict[str, Any]) -> dict[str, Any]:
    """
    Tek bir Belimo cihazından Modbus TCP ile veri okur.
    Döndürdüğü dict: { "baglanti": bool, "degerler": {...} }
    """
    from pymodbus.client import ModbusTcpClient

    ip    = device["ip"]
    port  = device.get("port", 502)
    slave = device.get("slave", 1)
    fields = device.get("fields", {})
    h_count = device.get("holding_count", 10)
    i_count = device.get("input_count", 10)

    result: dict[str, Any] = {"baglanti": False, "degerler": {}, "ham": {}}

    client = ModbusTcpClient(ip, port=port)
    try:
        if not client.connect():
            return result

        major  = _pymodbus_major()
        kwargs = _modbus_kwargs(major, slave)
        result["baglanti"] = True

        # Holding registers
        hr = client.read_holding_registers(0, count=h_count, **kwargs)
        if not hr.isError():
            result["ham"]["holding"] = list(hr.registers)
            for idx_str, meta in fields.get("holding", {}).items():
                idx = int(idx_str)
                if idx < len(hr.registers):
                    raw = hr.registers[idx]
                    val = round(raw * meta.get("scale", 1), 3)
                    result["degerler"][meta["label"]] = {
                        "value": val, "unit": meta.get("unit", ""), "raw": raw
                    }

        # Input registers
        ir = client.read_input_registers(0, count=i_count, **kwargs)
        if not ir.isError():
            result["ham"]["input"] = list(ir.registers)
            for idx_str, meta in fields.get("input", {}).items():
                idx = int(idx_str)
                if idx < len(ir.registers):
                    raw = ir.registers[idx]
                    val = round(raw * meta.get("scale", 1), 3)
                    result["degerler"][meta["label"]] = {
                        "value": val, "unit": meta.get("unit", ""), "raw": raw
                    }

    except Exception as e:
        logger.error(f"Modbus okuma hatası ({ip}): {e}")
    finally:
        client.close()

    return result


# ── CSV kayıt ────────────────────────────────────────────


def _init_csv(path: Path, fieldnames: list[str]) -> None:
    """CSV yoksa başlık satırıyla oluşturur."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()


def _append_csv(path: Path, row: dict[str, Any]) -> None:
    fieldnames = list(row.keys())
    file_exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ── Tek toplama turu ─────────────────────────────────────


def topla_bir_tur(config: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Tüm aktif cihazları okur, CSV'ye yazar, satır listesi döndürür.
    """
    data_path = Path(config.get("data_file", str(DATA_FILE)))
    satirlar: list[dict[str, Any]] = []

    for device in config.get("devices", []):
        if not device.get("enabled", True):
            continue

        ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        name   = device.get("name", device["ip"])
        ip     = device["ip"]

        try:
            okunan = oku_cihaz(device)
        except ModuleNotFoundError:
            logger.error("pymodbus yüklü değil: pip install pymodbus")
            continue

        row: dict[str, Any] = {
            "timestamp":    ts,
            "device_name":  name,
            "ip":           ip,
            "baglanti":     int(okunan["baglanti"]),
        }

        # Her alan için value sütunu ekle
        for label, meta in okunan["degerler"].items():
            col = label.replace(" ", "_")
            row[col] = meta["value"]
            row[f"{col}_birim"] = meta["unit"]

        # Ham register özeti (debug)
        ham = okunan.get("ham", {})
        if ham.get("holding"):
            row["ham_holding_0_5"] = str(ham["holding"][:6])
        if ham.get("input"):
            row["ham_input_0_5"] = str(ham["input"][:6])

        _append_csv(data_path, row)
        satirlar.append(row)

        durum = "OK" if okunan["baglanti"] else "HATA"
        logger.info(f"[{durum}] {name} ({ip}) — {len(okunan['degerler'])} alan")
        _log_row(name, okunan)

    return satirlar


def _log_row(name: str, okunan: dict) -> None:
    if not okunan["baglanti"]:
        print(f"  [{name}] BAĞLANTI HATASI")
        return
    parts = []
    for label, meta in okunan["degerler"].items():
        parts.append(f"{label}={meta['value']}{meta['unit']}")
    print(f"  [{name}] " + "  ".join(parts))


# ── Arka plan daemon'u ───────────────────────────────────

_collector_thread: threading.Thread | None = None
_stop_event = threading.Event()


def baslat(interval: int | None = None) -> None:
    """
    Arka planda periyodik veri toplama döngüsü başlatır.
    Portal'dan import edilerek çağrılır.
    """
    global _collector_thread

    if _collector_thread and _collector_thread.is_alive():
        logger.debug("Belimo collector zaten çalışıyor.")
        return

    _save_default_config()
    config = _load_config()
    if interval is not None:
        config["interval_seconds"] = interval

    _stop_event.clear()

    def _loop():
        logger.info(f"Belimo collector başladı (interval={config['interval_seconds']}s)")
        while not _stop_event.is_set():
            try:
                topla_bir_tur(config)
            except Exception as e:
                logger.error(f"Collector döngü hatası: {e}")
            _stop_event.wait(config["interval_seconds"])
        logger.info("Belimo collector durdu.")

    _collector_thread = threading.Thread(target=_loop, daemon=True, name="belimo-collector")
    _collector_thread.start()


def durdur() -> None:
    _stop_event.set()


# ── Komut satırı ─────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    _save_default_config()
    config = _load_config()

    if "--tek" in sys.argv or "-t" in sys.argv:
        # Tek seferlik okuma
        print("\n=== Belimo Tek Okuma ===\n")
        rows = topla_bir_tur(config)
        print(f"\n{len(rows)} cihaz okundu → {config['data_file']}")
    else:
        # Sürekli döngü (Ctrl+C ile dur)
        interval = config["interval_seconds"]
        print(f"\nBelimo Collector başladı (her {interval}s). Durdurmak için Ctrl+C.\n")
        try:
            while True:
                topla_bir_tur(config)
                print(f"  → {datetime.now().strftime('%H:%M:%S')} bekleniyor ({interval}s)...")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nDurduruluyor...")
