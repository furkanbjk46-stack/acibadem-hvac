# -*- coding: utf-8 -*-
"""
HAVA BESLEYİCİ — internete çıkamayan lokasyonlar için hava yedek yolu
=====================================================================

thapps Open-Meteo'ya ulaşabiliyor; lokasyon PC'leri her zaman ulaşamıyor
(Maslak 09.11.2026'dan beri — RPR-2026-1110-004). Bu modül merkez portal
sürecinde arka planda çalışır ve kayıtlı her lokasyonun koordinatı için:
  * son GECMIS_GUN günün gerçekleşen günlük havasını,
  * TAHMIN_GUN günün tahminini
public.hava_gunluk tablosuna yazar (veritabani/degisiklikler/003_hava_gunluk.sql).

Lokasyondaki hava_durumu.py önce internete gider; ulaşamazsa bu tablodan okur.
Değerler hava_durumu.py ile BİREBİR aynı biçimdedir: aynı servis, aynı alanlar,
aynı dönüşüm (_cevir). test_hava_besleyici.py iki dönüşümün aynı olduğunu dener.

Yalnızca hava_gunluk'a yazar; başka tabloya dokunmaz.
"""
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

TAHMIN = "https://api.open-meteo.com/v1/forecast"
GUNLUK = ("temperature_2m_mean,temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,"
          "precipitation_sum,cloud_cover_mean,shortwave_radiation_sum,wind_speed_10m_mean,weather_code")
GECMIS_GUN = 92               # Open-Meteo tahmin servisinin past_days üst sınırı
TAHMIN_GUN = 16
ARALIK_SN = 3 * 3600
IST = timezone(timedelta(hours=3))

logger = logging.getLogger("hava_besleyici")


# ── hava_durumu.py ile AYNI dönüşüm (değiştirilirse ikisi birlikte) ─────────
def durum_metni(kod, yagis) -> str:
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


def _cevir(gunluk: dict) -> dict:
    sonuc = {}
    for i, t in enumerate(gunluk.get("time") or []):
        al = lambda k: (gunluk.get(k) or [None] * (i + 1))[i]
        if al("temperature_2m_mean") is None:
            continue
        rad = al("shortwave_radiation_sum")
        sonuc[t] = {
            "Hava_Sicaklik_Ort_C": al("temperature_2m_mean"),
            "Hava_Sicaklik_Max_C": al("temperature_2m_max"),
            "Hava_Sicaklik_Min_C": al("temperature_2m_min"),
            "Hava_Nem_Ort_Yuzde": al("relative_humidity_2m_mean"),
            "Hava_Yagis_mm": al("precipitation_sum"),
            "Hava_Bulut_Yuzde": al("cloud_cover_mean"),
            "Hava_Gunes_Radyasyon_kWh_m2": round(rad / 3.6, 3) if rad is not None else None,
            "Hava_Ruzgar_Ort_kmh": al("wind_speed_10m_mean"),
            "Hava_Durumu": durum_metni(al("weather_code"), al("precipitation_sum")),
        }
    return sonuc


def _getir(url, zaman_asimi=30):
    with urllib.request.urlopen(url, timeout=zaman_asimi) as r:
        return json.load(r).get("daily") or {}


def satirlar(lokasyon_id, enlem, boylam, getir=None, bugun=None):
    """Bir lokasyonun hava_gunluk satırları (son GECMIS_GUN gün + TAHMIN_GUN gün tahmin)."""
    getir = getir or _getir
    bugun = (bugun or datetime.now(IST).date()).isoformat()
    url = ("%s?latitude=%s&longitude=%s&past_days=%d&forecast_days=%d&daily=%s&timezone=Europe%%2FIstanbul"
           % (TAHMIN, enlem, boylam, GECMIS_GUN, TAHMIN_GUN, GUNLUK))
    an = datetime.now(timezone.utc).isoformat()
    return [{"lokasyon_id": lokasyon_id, "tarih": t, "veri": v, "tahmin": t > bugun,
             "enlem": enlem, "boylam": boylam, "guncelleme": an}
            for t, v in sorted(_cevir(getir(url)).items())]


def yaz(url, key, satir_listesi, http=None):
    """hava_gunluk'a upsert (lokasyon_id + tarih)."""
    if not satir_listesi:
        return
    if http is not None:
        return http(satir_listesi)
    istek = urllib.request.Request(
        url.rstrip("/") + "/rest/v1/hava_gunluk?on_conflict=lokasyon_id,tarih", method="POST",
        data=json.dumps(satir_listesi, ensure_ascii=False).encode("utf-8"),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates,return=minimal"})
    with urllib.request.urlopen(istek, timeout=30) as c:
        c.read()


def lokasyon_idleri(url, key):
    """Kayıtlı (heartbeat gönderen) lokasyonlar."""
    istek = urllib.request.Request(url.rstrip("/") + "/rest/v1/lokasyonlar?select=lokasyon_id",
                                   headers={"apikey": key, "Authorization": "Bearer " + key})
    with urllib.request.urlopen(istek, timeout=20) as c:
        return [r["lokasyon_id"] for r in json.load(c)]


def tur(url, key, koordinatlar, getir=None, http=None, kayitli=None):
    """Kayıtlı ve koordinatı bilinen her lokasyonu besler. Dönüş: {lokasyon: satır sayısı | hata}."""
    sonuc = {}
    for lok in (kayitli if kayitli is not None else lokasyon_idleri(url, key)):
        k = koordinatlar.get(lok)
        if not k:
            sonuc[lok] = "koordinat yok"
            continue
        try:
            s = satirlar(lok, k[0], k[1], getir)
            yaz(url, key, s, http)
            sonuc[lok] = len(s)
        except Exception as e:                       # bir lokasyon diğerlerini durdurmaz
            sonuc[lok] = "%s: %s" % (type(e).__name__, e)
    return sonuc


_ARKA = {"thread": None, "son": None, "sonuc": None}
_KILIT = threading.Lock()


def _dongu(url, key, koordinatlar):
    """Merkez portalının içindeki YEDEK kopya: ayrı agent servisi çalışıyorsa beslemeyi ona bırakır."""
    import ust_agent
    while True:
        if ust_agent.servis_aktif(ust_agent.Db(url, key)):
            time.sleep(600)
            continue
        try:
            _ARKA["sonuc"] = tur(url, key, koordinatlar)
            _ARKA["son"] = datetime.now(timezone.utc)
            logger.info("Hava besleyici: %s", _ARKA["sonuc"])
        except Exception as e:
            _ARKA["sonuc"] = "%s: %s" % (type(e).__name__, e)
            logger.warning("Hava besleyici turu tamamlanamadı: %s", _ARKA["sonuc"])
        time.sleep(ARALIK_SN)


def baslat_arka_plan(url, key, koordinatlar):
    """Merkez portal sürecinde TEK kopya. koordinatlar: {lokasyon_id: (enlem, boylam)}."""
    if not url or not key or os.environ.get("SYNAPSE_HAVA_BESLEYICI", "1") == "0":
        return False
    with _KILIT:
        t = _ARKA["thread"]
        if t is not None and t.is_alive():
            return True
        t = threading.Thread(target=_dongu, args=(url, key, dict(koordinatlar)),
                             name="hava_besleyici", daemon=True)
        t.start()
        _ARKA["thread"] = t
        return True
