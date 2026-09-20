# -*- coding: utf-8 -*-
"""Mekanik Zeka — MOD ÇÖZÜMÜ testi (determine_effective_mode).

    python hvac/deneme/test_mod_cozumu.py

Motorun ilk ve en belirleyici kararı: "bu santral şu an ısıtıyor mu soğutuyor mu?"
Bu karar yanlışsa ΔT yönü, hedef, üfleme bandı ve tüm teşhisler yanlış olur
(MAS-1 Ahu-26 vakası: yalnız ısıtma vanası %9 açıkken dış hava sıcaklığından
SOĞUTMA çıkarılıyor, hedef 6.17 hesaplanıyordu).

Karar sırası — üsttekiler alttakileri ezer:
  1) Açık mod bilgisi (COOLING/HEATING/Sogutma/Isitma...)
  2) AUTO + iki vana da ≥%15 → AMBIGUOUS (çelişki, tahmin edilmez)
  3) AUTO + baskın vana ≥%15
  4) AUTO + yalnız bir vana açık (≥%0.5, diğeri ~0)
  5) Üfleme-emiş farkı ±2°C
  6) Dış hava sıcaklığı (≤12 ısıtma, ≥20 soğutma)
  7) Hiçbiri → UNKNOWN (SAT analizi atlanır)
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

_tmp = tempfile.mkdtemp(prefix="mod_")
ok.DURUM_FILE = os.path.join(_tmp, "durum.json")
ok.CARDS_FILE = os.path.join(_tmp, "cards.json")
ok.AUDIT_FILE = os.path.join(_tmp, "audit.jsonl")
mp.get_maintenance_card = lambda n, loc=None: {}
az = mp.HVACAnalyzer()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def mod(mode="AUTO", sat=None, ret=None, oat=None, cv=0, hv=0, tip="AHU"):
    t = mp.TemperatureData(sat=sat, supply=None, return_=ret, room=None, setpoint=None,
                           inlet=None, outlet=None, plant_supply=None, plant_return=None, oat=oat)
    p = mp.EquipmentProfile(type=tip, name="M", location="MAS-1", mode=mode, temperatures=t,
                            valves=mp.ValveData(cooling=cv, heating=hv))
    return az.determine_effective_mode(p)


def esit(ad, gelen, beklenen):
    c(ad, gelen == beklenen, f"beklenen={beklenen} gelen={gelen}")


def icerir(ad, gelen, parca):
    c(ad, parca in (gelen or "").upper(), f"'{parca}' bekleniyordu, gelen={gelen}")


# ── 1) Açık mod bilgisi her şeyi ezer ───────────────────────────────────
esit("açık COOLING modu", mod("COOLING", cv=0, hv=100), "COOLING")
esit("açık HEATING modu", mod("HEATING", cv=100, hv=0), "HEATING")
icerir("Türkçe 'Sogutma' modu tanınır", mod("Sogutma"), "COOL")
icerir("Türkçe 'Isitma' modu tanınır", mod("Isitma"), "HEAT")
c("açık mod, vanalara/dış havaya bakmaz (mod bilgisi otoritedir)",
  mod("COOLING", cv=0, hv=100, oat=-5) == "COOLING")

# ── 2) AUTO: iki vana da yüksek → çelişki ───────────────────────────────
esit("AUTO + iki vana da %15 üstü → AMBIGUOUS (tahmin edilmez)",
     mod("AUTO", cv=40, hv=40), "AMBIGUOUS")
esit("AUTO + tam eşikte (ikisi de %15) → AMBIGUOUS", mod("AUTO", cv=15, hv=15), "AMBIGUOUS")

# ── 3) AUTO: baskın vana ────────────────────────────────────────────────
icerir("AUTO + ısıtma %60 / soğutma %14 → ISITMA", mod("AUTO", hv=60, cv=14), "HEAT")
icerir("AUTO + soğutma %60 / ısıtma %14 → SOGUTMA", mod("AUTO", cv=60, hv=14), "COOL")

# ── 4) AUTO: yalnız bir vana açık (Ahu-26 vakası) ───────────────────────
icerir("[Ahu-26] yalnız ısıtma %9.44 açık → ISITMA (dış havaya düşmez)",
       mod("AUTO", hv=9.44, cv=0, oat=21.7), "HEAT")
icerir("yalnız soğutma %3 açık → SOGUTMA", mod("AUTO", cv=3, hv=0, oat=5.0), "COOL")
esit("iki vana da fiilen kapalı (%0.3) → vanadan karar çıkmaz, dış havaya düşer",
     mod("AUTO", cv=0.3, hv=0.3, oat=25.0), "COOLING (OAT-Inferred)")

# ── 5) Üfleme-emiş farkı ────────────────────────────────────────────────
esit("vana yok + üfleme emişten 5°C sıcak → ısıtma (sensörden)",
     mod("AUTO", sat=27.0, ret=22.0), "HEATING (Auto-Detected)")
esit("vana yok + üfleme emişten 5°C soğuk → soğutma (sensörden)",
     mod("AUTO", sat=17.0, ret=22.0), "COOLING (Auto-Detected)")
esit("sınır: fark tam 2°C (eşiğe eşit) → karar çıkmaz", mod("AUTO", sat=24.0, ret=22.0), "UNKNOWN")
c("sensör kararı dış havayı ezer (daha güvenilir kaynak)",
  mod("AUTO", sat=27.0, ret=22.0, oat=30.0) == "HEATING (Auto-Detected)")

# ── 6) Dış hava son çare ────────────────────────────────────────────────
esit("veri yok + dış hava 5°C → ısıtma varsayılır", mod("AUTO", oat=5.0), "HEATING (OAT-Inferred)")
esit("veri yok + dış hava 30°C → soğutma varsayılır", mod("AUTO", oat=30.0), "COOLING (OAT-Inferred)")
esit("ara mevsim: dış hava 16°C → karar verilmez", mod("AUTO", oat=16.0), "UNKNOWN")
esit("sınır: dış hava tam 12°C → ısıtma", mod("AUTO", oat=12.0), "HEATING (OAT-Inferred)")
esit("sınır: dış hava tam 20°C → soğutma", mod("AUTO", oat=20.0), "COOLING (OAT-Inferred)")

# ── 7) Hiçbir kaynak yok ────────────────────────────────────────────────
esit("hiç veri yok → UNKNOWN (üfleme analizi atlanır)", mod("AUTO"), "UNKNOWN")
esit("boş mod da AUTO gibi çözümlenir", mod("", cv=60), "COOLING (Auto)")

# ── 8) Modun sonuca etkisi: ΔT yönü ve hedefi ───────────────────────────
def _prof(mode, sat, ret, cv=0, hv=0):
    t = mp.TemperatureData(sat=sat, supply=None, return_=ret, room=None, setpoint=ret,
                           inlet=None, outlet=None, plant_supply=None, plant_return=None, oat=None)
    return mp.EquipmentProfile(type="AHU", name="MD", location="MAS-1", mode=mode,
                               temperatures=t, valves=mp.ValveData(cooling=cv, heating=hv))

p = _prof("AUTO", sat=13.0, ret=23.57, hv=100)          # MAS-1 Ahu-7
dt = az.calculate_air_delta_t(p, az.determine_effective_mode(p))
c("[Ahu-7] mod ISITMA çözülür → ΔT negatif (üfleme emişten soğuk)", dt is not None and dt < 0, dt)
hedef = az.get_target_delta_t(p, None, effective_mode=az.determine_effective_mode(p))
c("[Ahu-7] hedef ısıtma hedefidir (10.0)", hedef == 10.0, hedef)

p = _prof("AUTO", sat=16.0, ret=23.0, cv=80)
dt = az.calculate_air_delta_t(p, az.determine_effective_mode(p))
c("soğutmada ΔT pozitif (emiş − üfleme)", dt is not None and abs(dt - 7.0) < 0.01, dt)

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
