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

DEFAULT_CONFIG = {
    "_aciklama": "device_ips: BACnet cihaz instance -> IP adresi eslemesi.",
    "device_ips": {
        "2099287": "192.168.0.254",
        "2099291": "192.168.0.254",
        "2098211": "192.168.0.254"
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


def _load_config() -> dict:
    _ensure_config()
    with open(POINTS_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


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


async def _async_oku_ve_analiz_et() -> int:
    """Tüm BACnet okuma ve analiz işlemini async olarak çalıştırır."""
    import BAC0

    cfg         = _load_config()
    device_ips  = cfg.get("device_ips", {})
    ortak       = cfg.get("ortak", {})
    ahu_listesi = cfg.get("ahu_listesi", {})

    bos = [k for k, v in device_ips.items() if not v]
    if bos:
        logger.warning(f"IP tanimli olmayan cihazlar: {bos}")
        return 0

    if not ahu_listesi:
        logger.warning("bacnet_points.json icinde AHU tanimli degil.")
        return 0

    local_ip    = cfg.get("local_ip", "")
    local_port  = cfg.get("local_port", 47809)
    desigo_port = cfg.get("desigo_port", 47808)

    try:
        if local_ip:
            bacnet = BAC0.lite(ip=local_ip, port=local_port)
        else:
            bacnet = BAC0.lite(port=local_port)
        await asyncio.sleep(3)
    except Exception as e:
        logger.error(f"BAC0 baslatılamadi: {e}")
        return 0

    def oku_nokta(nokta_def: dict):
        ip = device_ips.get(str(nokta_def["device"]))
        if not ip:
            return None
        # Desigo'nun BACnet portunu (47808) hedefle
        adres = f"{ip}:{desigo_port} {nokta_def['type']} {nokta_def['instance']} presentValue"
        try:
            return float(bacnet.read(adres))
        except Exception as e:
            logger.warning(f"Okuma hatasi ({adres}): {e}")
            return None

    plant_supply = oku_nokta(ortak["plant_supply"]) if "plant_supply" in ortak else None
    plant_return = oku_nokta(ortak["plant_return"]) if "plant_return" in ortak else None
    oat          = oku_nokta(ortak["oat"])          if "oat"          in ortak else None

    logger.info(f"Ortak: PlantSupply={plant_supply} PlantReturn={plant_return} OAT={oat}")

    rows = []
    for ahu_adi, noktalar in ahu_listesi.items():
        sat           = oku_nokta(noktalar["sat"])           if "sat"           in noktalar else None
        room          = oku_nokta(noktalar["room"])          if "room"          in noktalar else None
        cooling_valve = oku_nokta(noktalar["cooling_valve"]) if "cooling_valve" in noktalar else None
        heating_valve = oku_nokta(noktalar["heating_valve"]) if "heating_valve" in noktalar else None

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

        result = await analyze_data(
            rows=rows,
            oat=str(oat) if oat is not None else "",
            engine="auto",
            tol_crit="3.0",
            tol_norm="1.5",
        )

        sonuclar = result.get("results", [])
        for row in sonuclar:
            row["Tarih"] = tarih

        _kaydet(sonuclar)
        return len(sonuclar)

    except Exception as e:
        logger.error(f"Analiz motoru hatasi: {e}")
        return 0


def oku_ve_analiz_et() -> int:
    """Thread içinden çağrılır. Kendi event loop'unu oluşturur."""
    try:
        import BAC0  # noqa: kontrol
    except ImportError:
        logger.error("BAC0 yuklu degil! Komut: pip install BAC0")
        return 0

    # Yeni event loop oluştur — thread içinde çalışmak için gerekli
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_oku_ve_analiz_et())
    except Exception as e:
        logger.error(f"BACnet okuma hatasi: {e}")
        return 0
    finally:
        loop.close()
        asyncio.set_event_loop(None)
