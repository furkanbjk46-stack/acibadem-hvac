#!/usr/bin/env python3
"""hava_besleyici.py testi — ağ yok; servis cevabı ve veritabanı yazımı taklit edilir."""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import hava_besleyici as H  # noqa: E402

gecti = kaldi = 0


def c(ad, kosul, ek=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓ " + ad)
    else:
        kaldi += 1
        print("  ✗ %s   %s" % (ad, ek))


BUGUN = date(2026, 11, 10)
istenen = []


def getir(url):
    istenen.append(url)
    gunler = [(BUGUN - timedelta(days=2) + timedelta(days=i)).isoformat() for i in range(5)]
    n = len(gunler)
    return {"time": gunler, "temperature_2m_mean": [8.0, None, 9.0, 10.0, 11.0],
            "temperature_2m_max": [12.0] * n, "temperature_2m_min": [4.0] * n,
            "relative_humidity_2m_mean": [70] * n, "precipitation_sum": [0.2] * n,
            "cloud_cover_mean": [80] * n, "shortwave_radiation_sum": [3.6] * n,
            "wind_speed_10m_mean": [9.0] * n, "weather_code": [3] * n}


s = H.satirlar("maslak", 41.1273, 29.0246, getir, BUGUN)
c("veri olmayan gün atlanır, diğerleri satır olur", [x["tarih"] for x in s] ==
  ["2026-11-08", "2026-11-10", "2026-11-11", "2026-11-12"], [x["tarih"] for x in s])
c("bugünden sonrası tahmin, bugün ve öncesi gerçekleşen",
  [x["tahmin"] for x in s] == [False, False, True, True])
c("veri alanları lokasyon biçiminde (radyasyon kWh, durum metni)",
  s[0]["veri"]["Hava_Gunes_Radyasyon_kWh_m2"] == 1.0 and s[0]["veri"]["Hava_Durumu"] == "bulutlu")
c("istek: lokasyon koordinatı, 92 gün geçmiş, 16 gün tahmin, İstanbul saati",
  "latitude=41.1273" in istenen[0] and "past_days=92" in istenen[0] and "forecast_days=16" in istenen[0]
  and "Europe%2FIstanbul" in istenen[0], istenen[0])

yazilan = []
r = H.tur("http://db", "k", {"maslak": (41.1273, 29.0246)}, getir=getir, http=yazilan.append,
          kayitli=["maslak", "bodrum"])
c("kayıtlı ve koordinatı bilinen lokasyon beslenir; koordinatsız atlanır",
  r == {"maslak": 4, "bodrum": "koordinat yok"} and len(yazilan) == 1 and len(yazilan[0]) == 4, r)


def bozuk(url):
    raise OSError("servis yok")


r = H.tur("http://db", "k", {"maslak": (41.1, 29.0), "kartal": (40.9, 29.2)}, getir=bozuk,
          http=yazilan.append, kayitli=["maslak", "kartal"])
c("bir lokasyonun hatası diğerlerini durdurmaz, hata metni döner",
  all(str(v).startswith("OSError") for v in r.values()) and len(r) == 2, r)
os.environ["SYNAPSE_HAVA_BESLEYICI"] = "0"
c("ortam değişkeniyle kapatılabilir", H.baslat_arka_plan("http://db", "k", {}) is False)

import json as _json  # noqa: E402
import re as _re  # noqa: E402
_dz = os.path.dirname(os.path.abspath(__file__))
import hastaneler as _HS  # noqa: E402
_m = open(os.path.join(_dz, "app_merkez.py"), encoding="utf-8").read()
c("hastane listesi tek kaynakta (configs/hastaneler.json, 20 hastane); sayfalarda kopya yok",
  len(_HS.yukle()) == 20 and "HASTANELER = _hastaneler.yukle()" in _m and not any(
      'HASTANELER = {' in open(os.path.join(_dz, f), encoding="utf-8").read()
      for f in ("app_merkez.py", "pages/lokasyon_detay.py", "pages/rapor_olustur.py")))
import agent_servisi as _AS  # noqa: E402
c("agent servisi koordinatları hastane listesinden okur (maslak)",
  _AS.koordinatlar()["maslak"] == (41.1273, 29.0246) and _AS.koordinatlar() == _HS.koordinatlar())
c("rapor sayfası adları Türkçe karaktersiz (PDF yedek yazı tipi)",
  _HS.yukle_ascii()["atasehir"]["isim"] == "Acibadem Atasehir" and _HS.yukle_ascii()["izmir"]["kisa"] == "IZMIR")
_kaynak = open(os.path.join(_dz, "agent_servisi.py"), encoding="utf-8").read()
_ithal = set(_re.findall(r"^(?:import|from) (\w+)", _kaynak, _re.M))
c("agent servisi yalnızca stdlib + kendi modüllerini kullanır (yeni paket yok)",
  _ithal <= {"json", "logging", "os", "sys", "threading", "time", "hava_besleyici", "ust_agent", "synapse_agent", "hastaneler"}, _ithal)
c("agent servisi diske yazmaz", not _re.search(r"open\([^)]*['\"]w", _kaynak))
_ua = open(os.path.join(_dz, "ust_agent.py"), encoding="utf-8").read()
_hb = open(os.path.join(_dz, "hava_besleyici.py"), encoding="utf-8").read()
_sql = "".join(open(os.path.join(_dz, "..", "veritabani", f), encoding="utf-8").read()
               for f in ("06_ust_agent_rolu.sql", "07_synapse_agent_yetkisi.sql",
                         os.path.join("degisiklikler", "004_yama_uygulamalari.sql"),
                         os.path.join("degisiklikler", "005_lokasyon_ayarlari.sql")))
_sa = open(os.path.join(_dz, "synapse_agent.py"), encoding="utf-8").read()
_eris = set(_re.findall(r'(?:rest/v1/|")(agent_turlar|agent_bulgular|agent_raporlar|lokasyonlar|hava_gunluk|'
                        r'energy_data|komutlar|guncellemeler|ayarlar|canli_guc|yama_uygulamalari|ayar_degisiklikleri)[?"]', _ua + _hb + _sa))
c("servisin eriştiği her tablo kısıtlı rolde (06 + 07) tanımlı, ayarlar tablosu yok",
  _eris and all(("ON public.%s " % t) in _sql for t in _eris) and "ayarlar" not in _eris,
  _eris)

print("\n%d geçti, %d kaldı" % (gecti, kaldi))
sys.exit(1 if kaldi else 0)
