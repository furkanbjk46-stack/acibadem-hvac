# -*- coding: utf-8 -*-
"""
GEÇMİŞ BAKIMI — AHU geçmişinin saklama kuralı ve günlük özeti (yol haritası N3, 12.11.2026)
=========================================================================================

Her 10 dakikada bir iki dosya yazılıyor ve hiç silinmiyordu:
  veri/ahu_okuma_gecmis/ahu_bacnet_YYYYMMDD_HHMM.csv     (~18 KB, yılda ~1 GB)
  veri/ahu_analiz_gecmis/hvac_analysis_YYYYMMDD_HHMM.csv (yılda ~350 MB)

Kural: SAKLA_GUN günden eski günlerin ham dosyaları önce GÜN BAŞINA ÖZETE çevrilir, özet kalıcı
dosyaya eklenir, ancak ondan SONRA ham dosyalar silinir (özet yazılamazsa silinmez):
  veri/ahu_okuma_gunluk.csv   Tarih, AHU, Lokasyon, Nokta_Tipi, Adet, Ort, Min, Max, Hatali
  veri/ahu_analiz_gunluk.csv  Tarih, Mahal, Ekipman, Analiz, Kritik, Uyari, Optimal, Diger, En_Sik_Kural, Ort_DeltaT

Son SAKLA_GUN gün ham hâliyle kalır (aylık alarm raporu, agent'ların donma kontrolü yalnız son günlere bakar).
cloud_sync günde bir kez gunluk_calistir() çağırır.
"""
import csv
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
SAKLA_GUN = 90
logger = logging.getLogger("gecmis_bakim")
_TARIH = re.compile(r"_(\d{8})_\d{4}\.csv$")
OKUMA_ALANLARI = ["Tarih", "AHU", "Lokasyon", "Nokta_Tipi", "Adet", "Ort", "Min", "Max", "Hatali"]
ANALIZ_ALANLARI = ["Tarih", "Mahal", "Ekipman", "Analiz", "Kritik", "Uyari", "Optimal", "Diger", "En_Sik_Kural",
                   "Ort_DeltaT"]


def _gunlere_ayir(klasor, sinir):
    """{YYYYMMDD: [dosya, ...]} — yalnız sınırdan ESKİ günler."""
    gunler = defaultdict(list)
    if not os.path.isdir(klasor):
        return gunler
    for ad in os.listdir(klasor):
        m = _TARIH.search(ad)
        if m and m.group(1) < sinir:
            gunler[m.group(1)].append(os.path.join(klasor, ad))
    return gunler


def _sayi(v):
    try:
        f = float(str(v).replace(",", "."))
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _okuma_ozeti(gun, dosyalar):
    grup = defaultdict(lambda: {"d": [], "hatali": 0})
    for p in dosyalar:
        with open(p, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                g = grup[(r.get("AHU_Adi", ""), r.get("Lokasyon", ""), r.get("Nokta_Tipi", ""))]
                v = _sayi(r.get("Deger"))
                if v is None or (r.get("Durum") or "OK") != "OK":
                    g["hatali"] += 1
                else:
                    g["d"].append(v)
    satirlar = []
    for (ahu, lok, tip), g in sorted(grup.items()):
        d = g["d"]
        satirlar.append({"Tarih": "%s-%s-%s" % (gun[:4], gun[4:6], gun[6:]), "AHU": ahu, "Lokasyon": lok,
                         "Nokta_Tipi": tip, "Adet": len(d), "Ort": round(sum(d) / len(d), 2) if d else "",
                         "Min": round(min(d), 2) if d else "", "Max": round(max(d), 2) if d else "",
                         "Hatali": g["hatali"]})
    return satirlar


def _analiz_ozeti(gun, dosyalar):
    grup = defaultdict(lambda: {"n": 0, "sid": Counter(), "kural": Counter(), "dt": []})
    for p in dosyalar:
        with open(p, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                g = grup[(r.get("Mahal", ""), r.get("Ekipman", ""))]
                g["n"] += 1
                sid = next((v for k, v in r.items() if k and k.startswith("Sidd")), "") or ""
                g["sid"][sid.upper()] += 1
                if r.get("Kural"):
                    g["kural"][r["Kural"]] += 1
                v = _sayi(r.get("Delta_T_C"))
                if v is not None:
                    g["dt"].append(v)
    satirlar = []
    for (mahal, ekip), g in sorted(grup.items()):
        s = g["sid"]
        satirlar.append({"Tarih": "%s-%s-%s" % (gun[:4], gun[4:6], gun[6:]), "Mahal": mahal, "Ekipman": ekip,
                         "Analiz": g["n"], "Kritik": s.get("CRITICAL", 0), "Uyari": s.get("WARNING", 0),
                         "Optimal": s.get("OPTIMAL", 0),
                         "Diger": g["n"] - s.get("CRITICAL", 0) - s.get("WARNING", 0) - s.get("OPTIMAL", 0),
                         "En_Sik_Kural": g["kural"].most_common(1)[0][0] if g["kural"] else "",
                         "Ort_DeltaT": round(sum(g["dt"]) / len(g["dt"]), 2) if g["dt"] else ""})
    return satirlar


def _ozetle(klasor, ozet_dosya, alanlar, ozetci, sinir):
    gunler = _gunlere_ayir(klasor, sinir)
    if not gunler:
        return {"gun": 0, "silinen": 0}
    var_olan = set()
    if os.path.exists(ozet_dosya):
        with open(ozet_dosya, newline="", encoding="utf-8") as f:
            var_olan = {r.get("Tarih", "").replace("-", "") for r in csv.DictReader(f)}
    yeni = not os.path.exists(ozet_dosya)
    gun_sayisi = silinen = 0
    for gun in sorted(gunler):
        if gun not in var_olan:
            satirlar = ozetci(gun, gunler[gun])
            with open(ozet_dosya, "a", newline="", encoding="utf-8") as f:   # önce özet...
                w = csv.DictWriter(f, fieldnames=alanlar)
                if yeni:
                    w.writeheader()
                    yeni = False
                w.writerows(satirlar)
            gun_sayisi += 1
        for p in gunler[gun]:                                                 # ...sonra ham dosya
            try:
                os.remove(p)
                silinen += 1
            except OSError as e:
                logger.warning("Ham geçmiş dosyası silinemedi (%s): %s", p, e)
    return {"gun": gun_sayisi, "silinen": silinen}


def calistir(base: str = None, bugun: datetime = None, sakla_gun: int = SAKLA_GUN) -> dict:
    base = base or BURASI
    sinir = ((bugun or datetime.now()) - timedelta(days=sakla_gun)).strftime("%Y%m%d")
    sonuc = {}
    for ad, klasor, ozet, alanlar, ozetci in (
            ("okuma", "ahu_okuma_gecmis", "veri/ahu_okuma_gunluk.csv", OKUMA_ALANLARI, _okuma_ozeti),
            ("analiz", "ahu_analiz_gecmis", "veri/ahu_analiz_gunluk.csv", ANALIZ_ALANLARI, _analiz_ozeti)):
        try:
            sonuc[ad] = _ozetle(yollar.yol(klasor, base), yollar.dosya_icin(ozet, base), alanlar, ozetci, sinir)
        except Exception as e:                 # özet yazılamadıysa ham dosyalara dokunulmadı
            logger.warning("AHU geçmiş bakımı (%s) tamamlanamadı: %s", ad, e)
            sonuc[ad] = {"hata": str(e)}
    if any(v.get("silinen") for v in sonuc.values()):
        logger.info("AHU geçmişi: %s", sonuc)
    return sonuc


def gunluk_calistir(base: str = None, simdi: datetime = None) -> dict:
    """Günde bir kez (durum/gecmis_bakim_son.txt); aynı gün tekrar çağrılırsa hiçbir şey yapmaz."""
    base = base or BURASI
    simdi = simdi or datetime.now()
    isaret = yollar.dosya_icin("durum/gecmis_bakim_son.txt", base)
    bugun = simdi.strftime("%Y-%m-%d")
    try:
        if open(isaret, encoding="utf-8").read().strip() == bugun:
            return {}
    except OSError:
        pass
    sonuc = calistir(base, simdi)
    with open(isaret, "w", encoding="utf-8") as f:
        f.write(bugun)
    return sonuc
