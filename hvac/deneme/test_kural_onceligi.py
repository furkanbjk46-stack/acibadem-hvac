# -*- coding: utf-8 -*-
"""Mekanik Zeka — ÖNCELİK MATRİSİ testi.

    python hvac/deneme/test_kural_onceligi.py

Bir santralde aynı anda birden fazla kural geçerli olabilir. Bu dosya
"hangisi ekrana yazılır" sorusunu sabitler. Tarihteki hatalar hep buradaydı:
  - Ters ΔT (KRİTİK), üfleme uyarısı (UYARI) tarafından eziliyordu.
  - Düşük ΔT kritiği, konfor uyarısı tarafından maskeleniyordu.
Bu tür bir gerileme bir daha sessizce geçmesin diye her çift yazılıdır.

ÖNCELİK SIRASI (üstteki alttakini ezer):
  1) ÖN KOŞUL KAPISI — cihaz durmuş / fan basmıyor / sensör arızalı:
     analiz yapılmaz, teşhis üretilmez.
  2) TALEP KAPISI — iki vana da kapalı: hava ΔT'si tanısal değildir (BEKLEME).
  3) KÖK NEDEN — aynı anda ısıtma+soğutma, sonucu (ters ΔT) ezer.
  4) KRİTİK TEŞHİS — soğutmuyor/ısıtmıyor, ters ΔT.
  5) UYARI — üfleme bandı, konfor, band dışı ΔT.
  6) NORMAL.
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

_tmp = tempfile.mkdtemp(prefix="oncelik_")
ok.DURUM_FILE = os.path.join(_tmp, "durum.json")
ok.CARDS_FILE = os.path.join(_tmp, "cards.json")
ok.AUDIT_FILE = os.path.join(_tmp, "audit.jsonl")
_KART = {}
mp.get_maintenance_card = lambda n, loc=None: dict(_KART)
az = mp.HVACAnalyzer()

T = []
_no = [0]
SIDDET = {"OPTIMAL": 0, "INFO": 1, "WARNING": 2, "CRITICAL": 3}


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def prof(tip="AHU", mode="AUTO", **kw):
    _no[0] += 1
    t = mp.TemperatureData(sat=kw.get("sat"), supply=kw.get("supply"), return_=kw.get("ret"),
                           room=kw.get("room"), setpoint=kw.get("setp"),
                           inlet=kw.get("inlet"), outlet=kw.get("outlet"),
                           plant_supply=None, plant_return=None, oat=kw.get("oat"))
    p = mp.EquipmentProfile(type=tip, name=f"O{_no[0]}", location="MAS-1", mode=mode,
                            temperatures=t,
                            valves=mp.ValveData(cooling=kw.get("cv", 0), heating=kw.get("hv", 0)))
    if kw.get("start") is not None:
        p.start_stop = kw["start"]
    if kw.get("basinc") is not None:
        p.pressure_pa = kw["basinc"]
    return p


def kural(p):
    return az.analyze_equipment(p, None, None, None, 1.0, 5.0)


def kazanan(baslik, p, beklenen, kaybeden=""):
    """İki durum aynı anda geçerliyken hangi kuralın ekrana yazıldığını sabitler."""
    r = kural(p)
    ek = f" ({kaybeden} ezilmemeli)" if kaybeden else ""
    c(baslik + ek, r.rule == beklenen, f"beklenen={beklenen} gelen={r.rule}/{r.severity}")
    return r


# ══ 1) ÖN KOŞUL KAPISI, her teşhisi ezer ════════════════════════════════
# Girdi soğutmuyor (kritik) görünümünde ama cihaz DURMUŞ.
kazanan("[KAPI] cihaz STOP iken 'soğutmuyor' teşhisi üretilmez",
        prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=90, start=0, basinc=0),
        "SKIP_STOP", "NOT_COOLING")
kazanan("[KAPI] fan basmıyorken ΔT teşhisi değil fan bulgusu yazılır",
        prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=90, start=1, basinc=10),
        "FAN_BASMIYOR", "TERS_DT")
kazanan("[KAPI] basınç sensörü arızalıyken analiz yapılmaz",
        prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=90, start=1, basinc=9999),
        "SKIP_BASINC_SENSOR_ARIZA", "NOT_COOLING")

# ══ 2) TALEP KAPISI: iki vana kapalı → hava ΔT'si tanısal değil ═════════
kazanan("[TALEP] vanalar kapalıyken ters ΔT teşhisi üretilmez (fan ısısı)",
        prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=0, hv=0),
        "STANDBY", "TERS_DT")

# ══ 3) KÖK NEDEN sonucu ezer ════════════════════════════════════════════
kazanan("[KÖK NEDEN] ısıtma+soğutma birlikte açıkken ters ΔT değil, çakışma yazılır",
        prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=60, hv=60),
        "SIMUL_HEAT_COOL", "TERS_DT")

# ══ 4) KRİTİK TEŞHİS, uyarıyı ezer ══════════════════════════════════════
# Dün düzeltilen vaka: üfleme uyarısı, ters ΔT kritiğini eziyordu.
for _cv in (45, 60, 69):
    r = kazanan(f"[KRİTİK] soğutmada üfleme emişten sıcak, vana %{_cv} → ters ΔT korunur",
                prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=_cv),
                "TERS_DT", "SAT_WARNING")
    c(f"  └ vana %{_cv}: önem KRİTİK kalır", r.severity == "CRITICAL", r.severity)

kazanan("[KRİTİK] vana %90 + üfleme sıcak → 'soğutmuyor' (üfleme uyarısı değil)",
        prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=90),
        "NOT_COOLING", "SAT_WARNING")

# Konfor sapması yüksek AMA aynı anda kritik bir teşhis de var → kritik kazanır
r = kural(prof(mode="COOLING", sat=30.0, ret=23.0, room=30.0, setp=23.0, cv=90))
c("[KRİTİK] konfor sapması yüksekken bile kritik teşhis maskelenmez",
  r.severity == "CRITICAL" and r.rule != "COMFORT_OVERRIDE", (r.rule, r.severity))

# ══ 5) SENSÖR ARIZASI, o sensöre dayanan teşhisi bastırır ══════════════
_KART = {"supply_sensor": "FAULTY"}
r = kural(prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=90))
c("[BAKIM] üfleme sensörü arızalıyken üflemeye dayanan kritik teşhis üretilmez",
  r.rule not in ("NOT_COOLING", "COOL_EFF_LOW"), (r.rule, r.severity))
_KART = {}

# ══ 6) KONFOR: uyarı ağır kuralı ezmez, kritik konfor ΔT'yi ezer ═══════
r = kural(prof(mode="HEATING", sat=30.0, ret=26.0, room=26.5, setp=23.0, hv=60))
c("[KONFOR] sapma 3.5°C (uyarı) düşük ΔT bulgusunu maskeleyebilir ama önem uyarıdır",
  SIDDET[r.severity] <= 2, (r.rule, r.severity))
kazanan("[KONFOR] sapma 10°C + vana %50 → kontrol sorunu (kritik) yazılır",
        prof(mode="COOLING", sat=16.0, ret=33.0, room=33.0, setp=23.0, cv=50),
        "COMFORT_CONTROL_FAULT", "COMFORT_OVERRIDE")

# ══ 7) GENEL KURAL: sonuç, eşzamanlı geçerli en ağır bulgudan hafif olamaz
# Her satır için: kritik bir koşul kuruluyken sonuç KRİTİK'ten düşükse hata.
_kritik_senaryolar = [
    ("aynı anda ısıtma+soğutma", prof(mode="COOLING", sat=18.0, ret=23.0, setp=23.0, cv=60, hv=60)),
    ("vana %90 ama soğutmuyor", prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=90)),
    ("vana %90 ama ısıtmıyor", prof(mode="HEATING", sat=18.0, ret=23.0, setp=23.0, hv=90)),
    ("soğutmada ters ΔT", prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=60)),
    ("çalışan cihazdan veri yok", prof(mode="COOLING", cv=60)),
]
for _ad, _p in _kritik_senaryolar:
    _r = kural(_p)
    c(f"[GENEL] kritik koşul '{_ad}' → sonuç KRİTİK", _r.severity == "CRITICAL",
      (_r.rule, _r.severity))

# ══ 8) Kapı kararı ile analiz bulgusu birlikte: bilgi kaybolmamalı ═════
r = kural(prof(mode="COOLING", sat=16.5, ret=23.0, setp=23.0, cv=60, start=0, basinc=450))
c("[KAPI] lokal çalışmada analiz yapılır, bulgu satırda kalır",
  r.rule == "LOKAL_CALISMA" or (r.atlama_nedeni or "") != "", (r.rule, r.atlama_nedeni))

# ══ 9) RASTGELE ÇAKIŞMA TARAMASI ═══════════════════════════════════════
# Elle yazılan çiftler yalnızca aklımıza gelen çakışmaları kapsar. Burada
# motor, KRİTİK bir koşulun kurulu olduğu binlerce rastgele senaryoda
# sınanır: koşul varken sonuç kritikten hafifse öncelik bozulmuş demektir.
import random

_rnd = random.Random(20260920)


def _rt(a, b):
    return round(_rnd.uniform(a, b), 1)


_ihlal = []
_sayim = {"simul": 0, "ters": 0, "sogutmuyor": 0, "isitmiyor": 0}
for _i in range(4000):
    _senaryo = _rnd.choice(("simul", "ters", "sogutmuyor", "isitmiyor"))
    _ret = _rt(20, 28)
    if _senaryo == "simul":                       # iki vana birden açık
        p = prof(mode=_rnd.choice(("AUTO", "COOLING", "HEATING")), sat=_rt(10, 35), ret=_ret,
                 setp=_ret, cv=_rt(5, 100), hv=_rt(5, 100), start=1, basinc=450)
    elif _senaryo == "ters":                      # soğutmada üfleme emişten sıcak
        p = prof(mode="COOLING", sat=_ret + _rt(1.5, 8), ret=_ret, setp=_ret,
                 cv=_rt(0.5, 69), hv=0, start=1, basinc=450)
    elif _senaryo == "sogutmuyor":                # vana TAM açık (≥%90) ama soğutmuyor
        p = prof(mode="COOLING", sat=_ret + _rt(0.5, 6), ret=_ret, setp=_ret,
                 cv=_rt(90, 100), hv=0, start=1, basinc=450)
    else:                                         # vana TAM açık (≥%90) ama ısıtmıyor
        p = prof(mode="HEATING", sat=_ret - _rt(0.5, 6), ret=_ret, setp=_ret,
                 cv=0, hv=_rt(90, 100), start=1, basinc=450)
    _sayim[_senaryo] += 1
    _r = kural(p)
    if _r.severity != "CRITICAL":
        _ihlal.append((_senaryo, _r.rule, _r.severity,
                       f"sat={p.temperatures.sat} ret={p.temperatures.return_} "
                       f"cv={p.valves.cooling} hv={p.valves.heating}"))

c("[TARAMA] 4000 rastgele çakışmada kritik koşul kritik sonuç verir",
  not _ihlal, _ihlal[:3])
c("[TARAMA] dört çakışma türü de üretildi", all(v > 0 for v in _sayim.values()), _sayim)

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
