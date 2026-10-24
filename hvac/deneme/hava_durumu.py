# -*- coding: utf-8 -*-
"""
GÜNLÜK HAVA DURUMU — her lokasyon KENDİ koordinatının havasını internetten alır
=============================================================================

NEDEN: energy_data'daki "Dis_Hava_Sicakligi_C" bina sensörünün sabah 07:05'teki
ANLIK değeridir (günlük ortalama değil). Nem, yağış, bulut, güneş radyasyonu
gibi bilgiler için sahada sensör yoktur. Bu modül lokasyonun kendi
koordinatıyla (configs/lokasyon_profili.json) Open-Meteo'dan günlük özeti
alır; her lokasyonun havası kendine özel olur.

Dışarıya giden tek bilgi koordinat ve tarihtir; anahtar/ücret yoktur.
Aynı servis oto_set.py ve ahu_collector.py tarafından zaten kullanılıyor.

SÜTUNLAR (tek kaynak — app_portal.SCHEMA ve data_bridge.ENERGY_SCHEMA buradan alır;
portal listede olmayan sütunu her açılışta SİLER, o yüzden liste tek yerde):
  Dis_Hava_Nem_Yuzde            bina sensörü (BACnet "DIS HAVA NEM", 07:05 anlık)
  Hava_Sicaklik_Ort/Max/Min_C   internet, günlük
  Hava_Nem_Ort_Yuzde            internet, günlük ortalama bağıl nem
  Hava_Yagis_mm, Hava_Bulut_Yuzde, Hava_Gunes_Radyasyon_kWh_m2, Hava_Ruzgar_Ort_kmh
  Hava_Durumu                   metin: güneşli / bulutlu / yağmurlu / karlı / sisli

İnternet yoksa hiçbir şey patlamaz: alanlar boş kalır, data_bridge bir
sonraki açılışta boş günleri geriye dönük doldurur.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import date, timedelta
from typing import Dict

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFIL = os.path.join(BASE_DIR, "configs", "lokasyon_profili.json")

SENSOR_NEM = "Dis_Hava_Nem_Yuzde"
INTERNET_SUTUNLARI = [
    "Hava_Sicaklik_Ort_C", "Hava_Sicaklik_Max_C", "Hava_Sicaklik_Min_C",
    "Hava_Nem_Ort_Yuzde", "Hava_Yagis_mm", "Hava_Bulut_Yuzde",
    "Hava_Gunes_Radyasyon_kWh_m2", "Hava_Ruzgar_Ort_kmh", "Hava_Durumu",
]
HAVA_SUTUNLARI = [SENSOR_NEM] + INTERNET_SUTUNLARI          # energy_data'ya eklenen hepsi
SAYISAL_SUTUNLAR = [c for c in HAVA_SUTUNLARI if c != "Hava_Durumu"]

ARSIV = "https://archive-api.open-meteo.com/v1/archive"
TAHMIN = "https://api.open-meteo.com/v1/forecast"
GUNLUK = ("temperature_2m_mean,temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,"
          "precipitation_sum,cloud_cover_mean,shortwave_radiation_sum,wind_speed_10m_mean,weather_code")
ARSIV_GECIKME_GUN = 5          # arşiv birkaç gün geriden gelir; yakın günler tahmin servisinden
ZAMAN_ASIMI = 20


def koordinat():
    """(enlem, boylam) — lokasyon_profili.json. Yoksa None."""
    try:
        with open(PROFIL, encoding="utf-8") as f:
            p = json.load(f)
        return float(p["enlem"]), float(p["boylam"])
    except Exception:
        return None


def durum_metni(kod, yagis) -> str:
    """WMO hava kodu → metin. 1 mm altı yağış 'yağmurlu' sayılmaz (çisenti)."""
    if kod is None:
        return ""
    k = int(kod)
    if k in (71, 73, 75, 77, 85, 86):
        return "karlı"
    if 51 <= k <= 67 or 80 <= k <= 82 or k >= 95:
        return "yağmurlu" if (yagis or 0) >= 1.0 else "bulutlu"
    if k in (45, 48):
        return "sisli"
    if k in (2, 3):
        return "bulutlu"
    return "güneşli"


def _getir(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=ZAMAN_ASIMI) as r:
        return json.load(r).get("daily") or {}


def _cevir(gunluk: dict) -> Dict[str, dict]:
    sonuc = {}
    for i, t in enumerate(gunluk.get("time") or []):
        al = lambda k: (gunluk.get(k) or [None] * (i + 1))[i]
        if al("temperature_2m_mean") is None:
            continue                                   # o gün için veri yok (arşiv gecikmesi)
        rad = al("shortwave_radiation_sum")
        sonuc[t] = {
            "Hava_Sicaklik_Ort_C": al("temperature_2m_mean"),
            "Hava_Sicaklik_Max_C": al("temperature_2m_max"),
            "Hava_Sicaklik_Min_C": al("temperature_2m_min"),
            "Hava_Nem_Ort_Yuzde": al("relative_humidity_2m_mean"),
            "Hava_Yagis_mm": al("precipitation_sum"),
            "Hava_Bulut_Yuzde": al("cloud_cover_mean"),
            "Hava_Gunes_Radyasyon_kWh_m2": round(rad / 3.6, 3) if rad is not None else None,  # MJ → kWh
            "Hava_Ruzgar_Ort_kmh": al("wind_speed_10m_mean"),
            "Hava_Durumu": durum_metni(al("weather_code"), al("precipitation_sum")),
        }
    return sonuc


def gunluk_hava(bas: str, son: str, bugun: date = None) -> Dict[str, dict]:
    """{ 'YYYY-AA-GG': {Hava_...: değer} }. Hata olursa boş sözlük (asla istisna atmaz).

    Eski günler arşivden, son ARSIV_GECIKME_GUN gün tahmin servisinin
    'past_days' alanından alınır (arşiv o günleri henüz yayımlamamıştır).
    """
    kd = koordinat()
    if not kd:
        logger.warning("Hava durumu: lokasyon_profili.json'da koordinat yok — atlandı")
        return {}
    enlem, boylam = kd
    bugun = bugun or date.today()
    sinir = bugun - timedelta(days=ARSIV_GECIKME_GUN)
    b, s = date.fromisoformat(bas), date.fromisoformat(son)
    sonuc: Dict[str, dict] = {}
    try:
        if b <= sinir:
            url = ("%s?latitude=%s&longitude=%s&start_date=%s&end_date=%s&daily=%s&timezone=Europe%%2FIstanbul"
                   % (ARSIV, enlem, boylam, b.isoformat(), min(s, sinir).isoformat(), GUNLUK))
            sonuc.update(_cevir(_getir(url)))
        if s > sinir:
            gecmis = min(92, (bugun - max(b, sinir)).days + 1)
            url = ("%s?latitude=%s&longitude=%s&past_days=%d&forecast_days=1&daily=%s&timezone=Europe%%2FIstanbul"
                   % (TAHMIN, enlem, boylam, gecmis, GUNLUK))
            for t, v in _cevir(_getir(url)).items():
                if b.isoformat() <= t <= s.isoformat():
                    sonuc.setdefault(t, v)
    except Exception as e:
        logger.warning("Hava durumu alınamadı (%s → %s): %s — alanlar boş kalacak", bas, son, e)
    return sonuc
