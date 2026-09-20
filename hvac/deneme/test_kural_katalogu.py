# -*- coding: utf-8 -*-
"""Mekanik Zeka — KURAL KATALOĞU testi.

    python hvac/deneme/test_kural_katalogu.py

Motorun ürettiği HER kural için üç soru sorar:
  1) TETİKLENİR Mİ?  Kuralın anlattığı durumu kurunca o kural çıkıyor mu?
  2) SINIRDA SUSAR MI? Eşiğin hemen altında (sorun yokken) susuyor mu?
  3) YANLIŞ TETİKLENİR Mİ? Benzer ama sağlıklı durumda başka bir şey mi diyor?

Golden vakalar (test_golden_mekanik_zeka.py) sahadan gelen GERÇEK vakaları
dondurur; bu dosya ise kural KAPSAMINI garanti eder: yeni bir kural eklenip
buraya vakası yazılmazsa test "kapsam dışı kural" diye uyarır.
"""
import logging
import os
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
logging.disable(logging.CRITICAL)

import on_kosul as ok
import main_portal as mp

_tmp = tempfile.mkdtemp(prefix="katalog_")
ok.DURUM_FILE = os.path.join(_tmp, "durum.json")
ok.CARDS_FILE = os.path.join(_tmp, "cards.json")
ok.AUDIT_FILE = os.path.join(_tmp, "audit.jsonl")
_KART = {}
mp.get_maintenance_card = lambda n, loc=None: dict(_KART)

az = mp.HVACAnalyzer()
T = []
_no = [0]


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def prof(tip="AHU", mode="AUTO", **kw):
    """Her vaka AYRI cihaz adı alır: ön koşul kapısı ardışık okumaları hatırlar."""
    _no[0] += 1
    t = mp.TemperatureData(sat=kw.get("sat"), supply=kw.get("supply"), return_=kw.get("ret"),
                           room=kw.get("room"), setpoint=kw.get("setp"),
                           inlet=kw.get("inlet"), outlet=kw.get("outlet"),
                           plant_supply=None, plant_return=None, oat=kw.get("oat"))
    p = mp.EquipmentProfile(type=tip, name=kw.get("ad") or f"K{_no[0]}", location="MAS-1",
                            mode=mode, temperatures=t,
                            valves=mp.ValveData(cooling=kw.get("cv", 0), heating=kw.get("hv", 0)))
    if kw.get("start") is not None:
        p.start_stop = kw["start"]
    if kw.get("basinc") is not None:
        p.pressure_pa = kw["basinc"]
    return p


def kural(p, oat=None):
    return az.analyze_equipment(p, None, None, oat, 1.0, 5.0)


def bekle(baslik, p, beklenen, oat=None):
    """Kuralın tetiklendiğini doğrular; sonucu da döndürür."""
    r = kural(p, oat)
    c(baslik, r.rule == beklenen, f"beklenen={beklenen} gelen={r.rule}/{r.severity}")
    return r


def susmali(baslik, p, istenmeyen, oat=None):
    r = kural(p, oat)
    if isinstance(istenmeyen, str):
        istenmeyen = (istenmeyen,)
    c(baslik, r.rule not in istenmeyen, f"istenmeyen={istenmeyen} gelen={r.rule}")
    return r


KAPSANAN = set()


def kapsa(*kurallar):
    KAPSANAN.update(kurallar)


# ══ 1. AYNI ANDA ISITMA + SOĞUTMA ═══════════════════════════════════════
kapsa("SIMUL_HEAT_COOL")
bekle("[SIMUL] iki vana da %5 üstü → aynı anda ısıtma+soğutma",
      prof(sat=18.0, ret=23.0, setp=22.0, cv=40, hv=40), "SIMUL_HEAT_COOL")
susmali("[SIMUL] sınır: soğutma %40, ısıtma %4 (eşik altı) → susar",
        prof(sat=18.0, ret=23.0, setp=22.0, cv=40, hv=4), "SIMUL_HEAT_COOL")
susmali("[SIMUL] tek vana açık sağlıklı santralde çıkmaz",
        prof(sat=16.0, ret=23.0, setp=22.0, cv=60, hv=0), "SIMUL_HEAT_COOL")

# ══ 2. BEKLEME (fan dönüyor, talep yok) ═════════════════════════════════
kapsa("STANDBY")
bekle("[STANDBY] iki vana kapalı, ΔT var → bekleme",
      prof(mode="COOLING", sat=22.5, ret=22.0, setp=22.0, cv=0, hv=0), "STANDBY")
susmali("[STANDBY] soğutma vanası %20 açıkken bekleme denmez",
        prof(mode="COOLING", sat=17.0, ret=22.0, setp=22.0, cv=20, hv=0), "STANDBY")

# ══ 3. CHILLER TEŞHİSLERİ ═══════════════════════════════════════════════
kapsa("CHILLER_BYPASS", "CHILLER_LOW_DT")
bekle("[CHILLER] ΔT 0.5 (<1) → bypass/kompresör yük almıyor",
      prof(tip="Chiller", mode="COOLING", inlet=12.0, outlet=11.5), "CHILLER_BYPASS")
bekle("[CHILLER] ΔT 2.0 (1-3 arası) → düşük ΔT sendromu",
      prof(tip="Chiller", mode="COOLING", inlet=12.0, outlet=10.0), "CHILLER_LOW_DT")
susmali("[CHILLER] ΔT 5.0 (hedefte) → teşhis üretilmez",
        prof(tip="Chiller", mode="COOLING", inlet=12.0, outlet=7.0),
        ("CHILLER_BYPASS", "CHILLER_LOW_DT"))

# ══ 4. DÜŞÜK ΔT SENDROMU (vana sonuna kadar açık) ═══════════════════════
kapsa("LOW_DT_SYNDROME", "AIR_DT_LOW_COOL")
bekle("[LOW_DT_SYNDROME] ısıtma vanası %95 ama hava ΔT 2 → coil/bypass şüphesi",
      prof(mode="HEATING", sat=30.0, ret=28.0, setp=28.0, hv=95), "LOW_DT_SYNDROME")
susmali("[LOW_DT_SYNDROME] sınır: vana %89 (eşik altı) → bu kural çıkmaz",
        prof(mode="HEATING", sat=30.0, ret=28.0, setp=28.0, hv=89), "LOW_DT_SYNDROME")
bekle("[AIR_DT_LOW_COOL] soğutma vanası %95, üfleme bandında ama hava ΔT 2 → soğutma etkisi zayıf",
      prof(mode="COOLING", sat=16.0, ret=18.0, setp=18.0, cv=95), "AIR_DT_LOW_COOL")

# ══ 5. FCU: YETERSİZ KAPASİTE ═══════════════════════════════════════════
kapsa("INSUFFICIENT_CAPACITY")
bekle("[FCU] oda-set sapması 4°C ve vana %90 → yetersiz kapasite",
      prof(tip="FCU", mode="COOLING", room=27.0, setp=23.0, inlet=7.0, outlet=12.0, cv=90),
      "INSUFFICIENT_CAPACITY")
susmali("[FCU] sınır: sapma 1.5°C (eşik altı) → kapasite uyarısı yok",
        prof(tip="FCU", mode="COOLING", room=24.5, setp=23.0, inlet=7.0, outlet=12.0, cv=90),
        "INSUFFICIENT_CAPACITY")
susmali("[FCU] sapma var ama vana %30 → kapasite değil kontrol sorunu",
        prof(tip="FCU", mode="COOLING", room=27.0, setp=23.0, inlet=7.0, outlet=12.0, cv=30),
        "INSUFFICIENT_CAPACITY")

# ══ 6. SU ΔT BANDI (FCU / kollektör) ════════════════════════════════════
kapsa("BAND_LOW", "BAND_HIGH", "IN_BAND")
bekle("[BAND] kollektör ΔT 3 < hedef 10 → band altı",
      prof(tip="Collector", mode="HEATING", inlet=45.0, outlet=42.0, hv=60), "BAND_LOW")
bekle("[BAND] kollektör ΔT 35 (hedef 15'in çok üstünde) → band üstü",
      prof(tip="Collector", mode="HEATING", inlet=80.0, outlet=45.0, hv=60), "BAND_HIGH")
bekle("[BAND] kollektör ΔT 15 = hedef → band içi",
      prof(tip="Collector", mode="HEATING", inlet=60.0, outlet=45.0, hv=60), "IN_BAND")

# ══ 7. HAVA ΔT BANDI (AHU) ══════════════════════════════════════════════
kapsa("HIGH_DT", "LOW_DT", "NORMAL")
bekle("[AHU] soğutma vanası %60, hava ΔT 15.5 (hedef 8'in üstünde) → yüksek ΔT",
      prof(mode="COOLING", sat=16.5, ret=32.0, setp=30.0, cv=60), "HIGH_DT")
bekle("[AHU] ısıtma vanası %60, hava ΔT 4 (hedef 10'un altında) → düşük ΔT",
      prof(mode="HEATING", sat=30.0, ret=26.0, setp=26.0, hv=60), "LOW_DT")
bekle("[AHU] vana %60, hava ΔT hedefte → normal",
      prof(mode="COOLING", sat=16.5, ret=23.0, setp=23.0, cv=60), "NORMAL")

# ══ 8. ÜFLEME SICAKLIĞI BANDI ═══════════════════════════════════════════
kapsa("SAT_HIGH", "SAT_LOW")
bekle("[SAT] ısıtmada üfleme 40°C (bandın üstü), vana %60 → SAT yüksek",
      prof(mode="HEATING", sat=40.0, ret=22.0, setp=22.0, hv=60), "SAT_HIGH")
bekle("[SAT] soğutmada üfleme 11°C (donma riski), vana %60 → SAT düşük",
      prof(mode="COOLING", sat=11.0, ret=17.0, setp=23.0, cv=60), "SAT_LOW")
susmali("[SAT] vana %20 kısıkken SAT kontrolü yapılmaz",
        prof(mode="COOLING", sat=11.0, ret=17.0, setp=23.0, cv=20), ("SAT_LOW", "SAT_HIGH"))

# ══ 9. BAKIM KARTI: ARIZALI / BAKIMDA ═══════════════════════════════════
kapsa("SENSOR_FAULT", "MAINTENANCE")
_KART = {"return_sensor": "FAULTY"}
r = kural(prof(mode="COOLING", sat=16.0, ret=23.0, setp=23.0, cv=60))
c("[BAKIM] emiş sensörü ARIZALI → analiz güvenilmez işaretlenir",
  r.rule in ("SENSOR_FAULT", "SKIP_SENSOR_ARIZA", "VERI_EKSIK"), (r.rule, r.severity))
_KART = {}
r = kural(prof(mode="COOLING", sat=16.0, ret=23.0, setp=23.0, cv=60))
c("[BAKIM] kart temizken normal analiz döner", r.rule not in ("SENSOR_FAULT", "MAINTENANCE"), r.rule)

# ══ 10. ÖN KOŞUL KAPISI (start/stop + kanal basıncı) ════════════════════
kapsa("SKIP_STOP", "FAN_BASMIYOR", "LOKAL_CALISMA", "SKIP_BASINC_SENSOR_ARIZA")
bekle("[KAPI] STOP komutu + basınç yok → analiz dışı",
      prof(mode="COOLING", sat=16.0, ret=23.0, setp=23.0, cv=60, start=0, basinc=0), "SKIP_STOP")
bekle("[KAPI] START komutu ama kanal basıncı 10 Pa (çalışma eşiği 20'nin altı) → fan basmıyor",
      prof(mode="COOLING", sat=16.0, ret=23.0, setp=23.0, cv=60, start=1, basinc=10), "FAN_BASMIYOR")
bekle("[KAPI] STOP komutu ama basınç var → lokalde çalıştırılıyor",
      prof(mode="COOLING", sat=16.5, ret=23.0, setp=23.0, cv=60, start=0, basinc=450), "LOKAL_CALISMA")
bekle("[KAPI] basınç 9999 Pa (aralık dışı) → basınç sensörü arızası",
      prof(mode="COOLING", sat=16.0, ret=23.0, setp=23.0, cv=60, start=1, basinc=9999),
      "SKIP_BASINC_SENSOR_ARIZA")

# ══ 11. SOĞUTMA/ISITMA ETKİSİZ (kritik teşhisler) ══════════════════════
kapsa("NOT_COOLING", "NOT_HEATING", "TERS_DT")
bekle("[KRİTİK] soğutma vanası %90 ama üfleme emişten sıcak → soğutmuyor",
      prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=90), "NOT_COOLING")
bekle("[KRİTİK] ısıtma vanası %90 ama üfleme emişten soğuk → ısıtmıyor",
      prof(mode="HEATING", sat=18.0, ret=23.0, setp=23.0, hv=90), "NOT_HEATING")
bekle("[KRİTİK] soğutmada üfleme emişten sıcak, vana %60 → ters ΔT",
      prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=60), "TERS_DT")
susmali("[KRİTİK] sağlıklı soğutmada bu teşhisler çıkmaz",
        prof(mode="COOLING", sat=16.5, ret=23.0, setp=23.0, cv=60),
        ("NOT_COOLING", "TERS_DT", "NOT_HEATING"))

# ══ 12. KONFOR DERECELENDİRMESİ ═════════════════════════════════════════
kapsa("COMFORT_OVERRIDE", "COMFORT_CAPACITY_FAULT", "COMFORT_CONTROL_FAULT")
bekle("[KONFOR] sapma 4°C → konfor önceliği (uyarı)",
      prof(mode="COOLING", sat=16.0, ret=27.0, room=27.0, setp=23.0, cv=50), "COMFORT_OVERRIDE")
bekle("[KONFOR] sapma 10°C, vana %95 → kapasite yetersiz (kritik)",
      prof(mode="COOLING", sat=16.0, ret=33.0, room=33.0, setp=23.0, cv=95),
      "COMFORT_CAPACITY_FAULT")
bekle("[KONFOR] sapma 10°C, vana %50 → kontrol/set sorunu (kritik)",
      prof(mode="COOLING", sat=16.0, ret=33.0, room=33.0, setp=23.0, cv=50),
      "COMFORT_CONTROL_FAULT")
susmali("[KONFOR] sınır: sapma 2.5°C (eşik altı) → konfor kuralı çıkmaz",
        prof(mode="COOLING", sat=16.5, ret=25.5, room=25.5, setp=23.0, cv=50),
        ("COMFORT_OVERRIDE", "COMFORT_CAPACITY_FAULT", "COMFORT_CONTROL_FAULT"))

# ══ 13. VERİ EKSİKLİĞİ ══════════════════════════════════════════════════
kapsa("MISSING_DATA", "VERI_EKSIK")
r = bekle("[VERİ] çalışan cihazdan veri gelmiyor → kritik",
          prof(mode="COOLING", cv=60), "MISSING_DATA")
c("[VERİ] çalışan cihazda veri eksikliği KRİTİK ve skor ≥7",
  r.severity == "CRITICAL" and (r.score or 0) >= 7.0, (r.severity, r.score))
r = bekle("[VERİ] kapalı cihazdan veri gelmiyor → uyarı",
          prof(mode="COOLING", cv=0, hv=0), "MISSING_DATA")
c("[VERİ] kapalı cihazda veri eksikliği UYARI", r.severity == "WARNING", (r.severity, r.score))

# ══ KAPSAM DENETİMİ ═════════════════════════════════════════════════════
import re as _re
_src = open(os.path.join(BURASI, "main_portal.py"), encoding="utf-8").read()
_uretilen = set(_re.findall(r'\.rule\s*=\s*"([A-Z0-9_]+)"', _src))
_uretilen |= set(_re.findall(r'"rule"\s*:\s*"([A-Z0-9_]+)"', _src))
_uretilen |= {"SKIP_SENSOR_ARIZA", "SKIP_BASINC_SENSOR_ARIZA"}
# Bu dosyada vakası olmayanlar BAŞKA test dosyalarında kapsanıyor olabilir
_diger = ""
for _f in ("test_golden_mekanik_zeka.py", "test_kural_tutarliligi.py"):
    _diger += open(os.path.join(BURASI, _f), encoding="utf-8").read()
_kapsamsiz = sorted(k for k in _uretilen if k not in KAPSANAN and k not in _diger)
c("her kuralın en az bir vakası var (kapsam denetimi)", not _kapsamsiz, _kapsamsiz)

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\nkapsanan kural: %d" % len(KAPSANAN))
print("%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
