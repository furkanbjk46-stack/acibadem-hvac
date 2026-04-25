# belimo_reader.py
# 192.168.0.x agindaki tum Belimo Smart Port cihazlarini tarar ve veri okur.
# Gereksinim: pip install requests

import asyncio
import json
import logging
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

BELIMO_PORT   = 8080
SCAN_SUBNET   = "192.168.0"
SCAN_RANGE    = range(1, 255)
HTTP_TIMEOUT  = 3

BASE_DIR      = Path(__file__).parent
BELIMO_CACHE  = BASE_DIR / "configs" / "belimo_devices.json"


# ── Cihaz Tarama ─────────────────────────────────────────


def _check_belimo(ip: str) -> dict | None:
    """Verilen IP'de Belimo cihazi var mi kontrol eder."""
    url = f"http://{ip}:{BELIMO_PORT}/index.html"
    try:
        r = requests.get(url, timeout=HTTP_TIMEOUT)
        if r.status_code == 200 and "BELIMO" in r.text.upper():
            name = _parse_device_name(r.text)
            return {"ip": ip, "name": name}
    except Exception:
        pass
    return None


def _parse_device_name(html: str) -> str:
    """HTML'den cihaz adi / lokasyon bilgisini ceker."""
    match = re.search(r"Device location\s*</?\w*>?\s*([^<\n]+)", html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "Bilinmiyor"


def tarama_yap(subnet: str = SCAN_SUBNET, workers: int = 50) -> list[dict]:
    """Agdaki tum Belimo cihazlarini tarar. Sonuclari JSON'a kaydeder."""
    print(f"Ag taramasi basliyor: {subnet}.1 - {subnet}.254 (port {BELIMO_PORT})...")
    bulunanlar = []
    ips = [f"{subnet}.{i}" for i in SCAN_RANGE]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_check_belimo, ip): ip for ip in ips}
        for future in as_completed(futures):
            result = future.result()
            if result:
                print(f"  [OK] Belimo bulundu: {result['ip']} → {result['name']}")
                bulunanlar.append(result)

    bulunanlar.sort(key=lambda x: [int(p) for p in x["ip"].split(".")])

    BELIMO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(BELIMO_CACHE, "w", encoding="utf-8") as f:
        json.dump(bulunanlar, f, indent=2, ensure_ascii=False)

    print(f"\nToplam {len(bulunanlar)} Belimo cihazi bulundu → {BELIMO_CACHE.name}")
    return bulunanlar


# ── Veri Okuma ────────────────────────────────────────────


def _get_json_api(ip: str) -> dict | None:
    """Yeni firmware: JSON API'den veri okur."""
    for endpoint in ["/api/v1/datapoints", "/api/datapoints", "/api/"]:
        try:
            r = requests.get(f"http://{ip}:{BELIMO_PORT}{endpoint}", timeout=HTTP_TIMEOUT)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("application/json"):
                return r.json()
        except Exception:
            pass
    return None


def _parse_data_html(ip: str) -> dict:
    """Eski firmware: Data HTML sayfasindan deger ceker."""
    data = {}
    try:
        r = requests.get(
            f"http://{ip}:{BELIMO_PORT}/index.html?p=/data.html",
            timeout=HTTP_TIMEOUT
        )
        if r.status_code != 200:
            return data
        html = r.text
        # Tablo satirlarini ara: etiket - deger - birim
        rows = re.findall(
            r"<tr[^>]*>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>([^<]*)</td>.*?</tr>",
            html, re.DOTALL | re.IGNORECASE
        )
        for label, value, unit in rows:
            label = label.strip()
            value = value.strip()
            unit  = unit.strip()
            if label and value and label not in ("Label", "Value", "Unit"):
                try:
                    data[label] = {"value": float(value), "unit": unit}
                except ValueError:
                    data[label] = {"value": value, "unit": unit}
    except Exception as e:
        logger.debug(f"HTML parse hata ({ip}): {e}")
    return data


def oku_cihaz(ip: str, name: str = "") -> dict:
    """Tek bir Belimo cihazindan veri okur. JSON API veya HTML fallback."""
    result = {"ip": ip, "name": name, "timestamp": datetime.now().isoformat(), "data": {}}

    # Once JSON API dene
    json_data = _get_json_api(ip)
    if json_data:
        result["source"] = "json_api"
        result["data"] = json_data
        return result

    # HTML fallback
    html_data = _parse_data_html(ip)
    if html_data:
        result["source"] = "html"
        result["data"] = html_data
        return result

    result["source"] = "none"
    return result


def _extract_vana_pozisyon(data: dict) -> float | None:
    """Veri sozlugundan vana pozisyonunu (%) ceker."""
    for key in data:
        if any(k in key.lower() for k in ["position", "pos", "vana", "valve", "stroke"]):
            val = data[key]
            if isinstance(val, dict):
                val = val.get("value")
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


def _extract_sicaklik(data: dict, anahtar_kelimeler: list[str]) -> float | None:
    """Veri sozlugundan sicaklik degerini ceker."""
    for key in data:
        if any(k in key.lower() for k in anahtar_kelimeler):
            val = data[key]
            if isinstance(val, dict):
                val = val.get("value")
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None


# ── Ana Okuma Fonksiyonu ──────────────────────────────────


def oku_tum_belimolar(kayitli_cihazlar: list[dict] | None = None) -> list[dict]:
    """
    Kayitli Belimo cihazlarindan veri okur.
    kayitli_cihazlar None ise belimo_devices.json'dan yukler.
    """
    if kayitli_cihazlar is None:
        if BELIMO_CACHE.exists():
            with open(BELIMO_CACHE, encoding="utf-8") as f:
                kayitli_cihazlar = json.load(f)
        else:
            logger.warning("Belimo cihaz listesi yok. Once tarama_yap() calistirin.")
            return []

    sonuclar = []
    for cihaz in kayitli_cihazlar:
        ip   = cihaz["ip"]
        name = cihaz.get("name", "")
        raw  = oku_cihaz(ip, name)
        data = raw.get("data", {})

        vana_pos  = _extract_vana_pozisyon(data)
        t_giris   = _extract_sicaklik(data, ["inlet", "supply", "giris", "t1", "flow"])
        t_donus   = _extract_sicaklik(data, ["outlet", "return", "donus", "t2", "return"])

        row = {
            "IP":            ip,
            "Cihaz":         name,
            "Vana Pos (%)":  vana_pos,
            "T Giris (°C)":  t_giris,
            "T Donus (°C)":  t_donus,
            "Kaynak":        raw.get("source"),
            "Ham Veri":      json.dumps(data, ensure_ascii=False) if data else "",
        }
        sonuclar.append(row)
        durum = f"{vana_pos}%" if vana_pos is not None else "okunamadi"
        print(f"  {name or ip}: Vana={durum}  T_giris={t_giris}  T_donus={t_donus}")

    return sonuclar


# ── Komut Satiri Kullanimi ────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.WARNING)

    if len(sys.argv) > 1 and sys.argv[1] == "tara":
        # python belimo_reader.py tara
        cihazlar = tarama_yap()
    else:
        # python belimo_reader.py
        print("Kayitli Belimo cihazlari okunuyor...")
        if not BELIMO_CACHE.exists():
            print("Cihaz listesi bulunamadi, once ag taramasi yapiliyor...")
            cihazlar = tarama_yap()
        else:
            with open(BELIMO_CACHE, encoding="utf-8") as f:
                cihazlar = json.load(f)

        print(f"\n{len(cihazlar)} cihazdan veri okunuyor...\n")
        sonuclar = oku_tum_belimolar(cihazlar)
        print(f"\nToplam {len(sonuclar)} cihaz okundu.")

        # Ham veriyi goster (ilk cihaz)
        if cihazlar:
            print("\n--- Ilk cihazin ham verisi ---")
            raw = oku_cihaz(cihazlar[0]["ip"], cihazlar[0].get("name", ""))
            print(json.dumps(raw["data"], indent=2, ensure_ascii=False))
