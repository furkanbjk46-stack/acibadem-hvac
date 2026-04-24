# bacnet_reader.py
# BACnet/IP üzerinden Siemens Desigo'dan otomatik HVAC verisi okuma.
# Gereksinim: pip install BAC0

import asyncio
import csv
import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
POINTS_CONFIG = BASE_DIR / "configs" / "bacnet_points.json"
HVAC_HISTORY  = BASE_DIR / "hvac_analysis_history.csv"

# ── Varsayılan nokta yapılandırması ───────────────────────────────
DEFAULT_CONFIG = {
    "_aciklama": "device_ips: BACnet cihaz instance -> IP adresi eslemesi. Bos birakilan IP'ler atlanir.",
    "device_ips": {
        "2099287": "",
        "2099291": "",
        "2098211": ""
    },
    "ortak": {
        "plant_supply": {"device": "2099291", "type": "analogInput",  "instance": 22},
        "plant_return": {"device": "2099291", "type": "analogInput",  "instance": 23},
        "oat":          {"device": "2098211", "type": "analogInput",  "instance": 33}
    },
    "ahu_listesi": {
        "AHU-01": {
            "sat":           {"device": "2099287", "type": "analogInput",  "instance": 254},
            "room":          {"device": "2099287", "type": "analogInput",  "instance": 251},
            "cooling_valve": {"device": "2099287", "type": "analogOutput", "instance": 150},
            "heating_valve": {"device": "2099287", "type": "analogOutput", "instance": 148}
        }
    }
}


def _ensure_config():
    if not POINTS_CONFIG.exists():
        POINTS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        with open(POINTS_CONFIG, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        logger.info(f"bacnet_points.json olusturuldu: {POINTS_CONFIG}")
        logger.info("Lutfen configs/bacnet_points.json dosyasina device IP adreslerini girin.")


def _load_config() -> dict:
    _ensure_config()
    with open(POINTS_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_point(bacnet, ip: str, obj_type: str, instance: int):
    try:
        return float(bacnet.read(f"{ip} {obj_type} {instance} presentValue"))
    except Exception as e:
        logger.warning(f"Okuma hatasi ({ip} {obj_type} {instance}): {e}")
        return None


def _kaydet(sonuclar: list):
    if not sonuclar:
        return
    file_exists = HVAC_HISTORY.exists()
    with open(HVAC_HISTORY, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=sonuclar[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(sonuclar)
    logger.info(f"✅ {len(sonuclar)} AHU kaydedildi → {HVAC_HISTORY.name}")


def oku_ve_analiz_et() -> int:
    """BACnet'ten veri oku, analiz yap, CSV'ye kaydet. Okunan AHU sayısını döndürür."""
    try:
        import BAC0
    except ImportError:
        logger.error("BAC0 yuklu degil! Komut: pip install BAC0")
        return 0

    cfg         = _load_config()
    device_ips  = cfg.get("device_ips", {})
    ortak       = cfg.get("ortak", {})
    ahu_listesi = cfg.get("ahu_listesi", {})

    bos = [k for k, v in device_ips.items() if not v]
    if bos:
        logger.warning(f"Asagidaki cihazlar icin IP tanimli degil: {bos}")
        logger.warning("configs/bacnet_points.json → device_ips alanini doldurun.")
        return 0

    if not ahu_listesi:
        logger.warning("bacnet_points.json icinde AHU tanimli degil.")
        return 0

    try:
        bacnet = BAC0.lite()
        time.sleep(2)
    except Exception as e:
        logger.error(f"BAC0 baslatılamadi: {e}")
        return 0

    def oku(nokta_def: dict):
        ip = device_ips.get(str(nokta_def["device"]))
        if not ip:
            return None
        return _read_point(bacnet, ip, nokta_def["type"], nokta_def["instance"])

    plant_supply = oku(ortak["plant_supply"]) if "plant_supply" in ortak else None
    plant_return = oku(ortak["plant_return"]) if "plant_return" in ortak else None
    oat          = oku(ortak["oat"])          if "oat"          in ortak else None

    logger.info(f"Ortak: PlantSupply={plant_supply} PlantReturn={plant_return} OAT={oat}")

    rows = []
    for ahu_adi, noktalar in ahu_listesi.items():
        sat           = oku(noktalar["sat"])           if "sat"           in noktalar else None
        room          = oku(noktalar["room"])          if "room"          in noktalar else None
        cooling_valve = oku(noktalar["cooling_valve"]) if "cooling_valve" in noktalar else None
        heating_valve = oku(noktalar["heating_valve"]) if "heating_valve" in noktalar else None

        if sat is None:
            logger.warning(f"{ahu_adi}: SAT okunamadi, atlandi")
            continue

        rows.append({
            "Name":              ahu_adi,
            "Type":              "AHU",
            "SAT (°C)":          sat,
            "Room (°C)":         room,
            "Cool Valve (%)":    cooling_valve,
            "Heat Valve (%)":    heating_valve,
            "Plant Supply (°C)": plant_supply,
            "Plant Return (°C)": plant_return,
            "OAT (°C)":          oat,
        })
        logger.info(f"{ahu_adi}: SAT={sat}°C Oda={room}°C SogV={cooling_valve}% IsV={heating_valve}%")

    try:
        bacnet.disconnect()
    except Exception:
        pass

    if not rows:
        logger.warning("Hic AHU verisi okunamadi.")
        return 0

    try:
        from main_portal import analyze_data
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M")

        result = asyncio.run(analyze_data(
            rows=rows,
            oat=str(oat) if oat is not None else "",
            engine="auto",
            tol_crit="3.0",
            tol_norm="1.5",
        ))

        sonuclar = result.get("results", [])
        for row in sonuclar:
            row["Tarih"] = tarih

        _kaydet(sonuclar)
        return len(sonuclar)

    except Exception as e:
        logger.error(f"Analiz motoru hatasi: {e}")
        return 0
