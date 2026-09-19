# -*- coding: utf-8 -*-
"""Mekanik Zeka kural tutarlılığı — ΔT mod birliği, talimat kapsamı, PDF koruması.

    python hvac/deneme/test_kural_tutarliligi.py

19.09 analizinde bulunan hatalar için regresyon testleri:
  1) MAS-1 Ahu-7: ısıtma vanası %100 (AUTO) iken ΔT SOĞUTMA formülüyle
     hesaplanıp ISITMA hedefiyle kıyaslanıyordu (+10.6 görünüyordu, gerçek −10.6).
  2) Talimat butonları: ön yüz listesi arka uçtan geri kalmıştı.
  3) Bakım kartı PDF'i: bölünen tablo satırında "reading 'badgeLabel'" hatası.
"""
import asyncio
import json
import os
import re
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)

import on_kosul as ok
import main_portal as mp

_tmp = tempfile.mkdtemp(prefix="kural_")
ok.DURUM_FILE = os.path.join(_tmp, "durum.json")
ok.CARDS_FILE = os.path.join(_tmp, "cards.json")
ok.AUDIT_FILE = os.path.join(_tmp, "audit.jsonl")
mp.get_maintenance_card = lambda n, loc=None: {}
az = mp.HVACAnalyzer()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def _prof(tip="AHU", mode="AUTO", **kw):
    t = mp.TemperatureData(sat=kw.get("sat"), supply=kw.get("supply"), return_=kw.get("ret"),
                           room=kw.get("room"), setpoint=kw.get("setp"),
                           inlet=kw.get("inlet"), outlet=kw.get("outlet"))
    v = mp.ValveData(cooling=kw.get("cv", 0), heating=kw.get("hv", 0))
    return mp.EquipmentProfile(type=tip, name=kw.get("ad", "T"), location="MAS-1",
                               mode=mode, temperatures=t, valves=v)


def _analiz(p):
    return az.analyze_equipment(p, None, None, None, 1.0, 3.0)


# ── 1) ΔT ve hedef AYNI moddan ──────────────────────────────────────────
# MAS-1 Ahu-7'nin birebir girdisi
_p7 = _prof(ad="Ahu-7", sat=13.0, ret=23.57, setp=23.0, hv=100, cv=0)
r = _analiz(_p7)
_sog_hedef = az.get_target_delta_t(_p7, None, effective_mode="COOLING")
c("[Ahu-7] AUTO + ısıtma vanası %100 → ısıtma hedefi (10.0, soğutma hedefinden farklı)",
  r.target_delta_t == 10.0 and r.target_delta_t != _sog_hedef, (r.target_delta_t, _sog_hedef))
c("[Ahu-7] ısıtmada üfleme emişten SOĞUK → ΔT NEGATİF (eskiden +10.6)",
  r.delta_t is not None and abs(r.delta_t - (13.0 - 23.57)) < 0.01, r.delta_t)
c("[Ahu-7] sapma = ΔT − hedef, negatif (eskiden +0.6 'hedefe yakın' görünüyordu)",
  r.departure is not None and r.departure < -15, r.departure)
c("[Ahu-7] kritik kural korunur (NOT_HEATING/HEAT_EFF_LOW)",
  r.rule in ("NOT_HEATING", "HEAT_EFF_LOW"), r.rule)

# Isıtma normal çalışıyorsa ΔT pozitif kalmalı
r = _analiz(_prof(sat=32.0, ret=22.0, setp=22.0, hv=80, cv=0))
c("AUTO ısıtma, üfleme sıcak → ΔT +10 (pozitif)", r.delta_t is not None and abs(r.delta_t - 10.0) < 0.01,
  r.delta_t)

# Soğutma davranışı DEĞİŞMEMELİ
r = _analiz(_prof(sat=13.0, ret=24.0, setp=23.0, hv=0, cv=100))
c("AUTO soğutma → ΔT +11 (değişmedi)", r.delta_t is not None and abs(r.delta_t - 11.0) < 0.01, r.delta_t)
r = _analiz(_prof(mode="COOLING", sat=13.0, ret=24.0, setp=23.0, cv=100))
c("açık COOLING modu → ΔT +11 (değişmedi)", r.delta_t is not None and abs(r.delta_t - 11.0) < 0.01, r.delta_t)
r = _analiz(_prof(mode="HEATING", sat=32.0, ret=22.0, setp=22.0, hv=80))
c("açık HEATING modu → ΔT +10 (değişmedi)", r.delta_t is not None and abs(r.delta_t - 10.0) < 0.01, r.delta_t)

# Soğutmada negatif hava ΔT değişmeden korunuyor (TERS_DT kararının girdisi)
r = _analiz(_prof(mode="COOLING", sat=26.0, ret=23.0, setp=23.0, cv=60))
c("soğutmada üfleme emişten sıcak → ΔT −3 (yön korunur)",
  r.delta_t is not None and abs(r.delta_t + 3.0) < 0.01, r.delta_t)

# Su tarafı ΔT (FCU coil) de aynı mod kaynağını kullanır
p = _prof(tip="FCU", sat=35.0, ret=22.0, inlet=60.0, outlet=50.0, hv=90, cv=0)
dt, _ = az.calculate_delta_t(p, az.determine_effective_mode(p))
c("FCU AUTO ısıtma su ΔT = giriş − çıkış (+10)", dt is not None and abs(dt - 10.0) < 0.01, dt)
dt_eski, _ = az.calculate_delta_t(p)            # mod verilmezse ESKİ davranış (geri uyum)
c("mod verilmezse eski davranış korunur (geri uyum)", dt_eski is not None and abs(dt_eski + 10.0) < 0.01,
  dt_eski)

# ── 2) Talimat kapsamı ──────────────────────────────────────────────────
kaynak = open(os.path.join(BURASI, "main_portal.py"), encoding="utf-8").read()
atanan = set(re.findall(r'\.rule\s*=\s*"([A-Z0-9_]+)"', kaynak))
atanan |= set(re.findall(r'"rule"\s*:\s*"([A-Z0-9_]+)"', kaynak))
# Değişkenle atanan ön koşul kodları (result.rule = _kapi["karar"])
atanan |= {"SKIP_SENSOR_ARIZA", "SKIP_BASINC_SENSOR_ARIZA"}
eksik = sorted(k for k in atanan if k not in mp.INSTRUCTION_GUIDE)
c("üretilen HER kuralın açıklaması var", not eksik, eksik)

bozuk = []
for k, v in mp.INSTRUCTION_GUIDE.items():
    if not all(a in v for a in ("title", "severity", "score", "description")) \
            or not isinstance(v.get("steps"), list) or not v["steps"]:
        bozuk.append(k)
c("her açıklamada başlık/önem/skor/açıklama/adımlar dolu (pencere çökmesin)", not bozuk, bozuk)
for k in ("SKIP_STOP", "SKIP_VERI_YOK", "SKIP_SENSOR_ARIZA", "SKIP_BASINC_SENSOR_ARIZA"):
    c(f"yeni açıklama: {k}", k in mp.INSTRUCTION_GUIDE)

# Kodda kullanılan skor/önem ile açıklamadaki değer çelişmesin
c("SKIP_STOP skoru koddaki ile aynı (0.0)", mp.INSTRUCTION_GUIDE["SKIP_STOP"]["score"] == 0.0)
c("SKIP_VERI_YOK skoru koddaki ile aynı (2.0)", mp.INSTRUCTION_GUIDE["SKIP_VERI_YOK"]["score"] == 2.0)

# API ucu
cevap = asyncio.run(mp.api_instruction_guide())
c("/api/instruction-guide tüm rehberi döner", cevap is mp.INSTRUCTION_GUIDE or cevap == mp.INSTRUCTION_GUIDE)
try:
    json.dumps(cevap, ensure_ascii=False)
    c("rehber JSON'a çevrilebiliyor", True)
except Exception as e:
    c("rehber JSON'a çevrilebiliyor", False, str(e))

# ── 3) Ön yüz ───────────────────────────────────────────────────────────
html = open(os.path.join(BURASI, "static", "index.html"), encoding="utf-8").read()
c("talimat penceresi arka uçtan yükler", "fetch('/api/instruction-guide')" in html)
c("showInstructions yüklemeyi bekler", re.search(r"async function showInstructions\(ruleCode\)\s*\{\s*await _talimatlariYukle\(\);", html) is not None)
c("adımı olmayan talimat pencereyi çökertmez", "(instruction.steps || []).forEach" in html)
c("PDF: iki hook da bölünmüş satıra karşı korumalı",
  len(re.findall(r"const s = summary\[data\.row\.index\];\s*if \(!s\) return;", html)) == 2)
c("PDF: korumasız summary[...] okuması kalmadı",
  len(re.findall(r"summary\[data\.row\.index\]", html)) == 2)
c("PDF: satır bölünmesi engellendi (rowPageBreak: 'avoid')", "rowPageBreak: 'avoid'" in html)

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
