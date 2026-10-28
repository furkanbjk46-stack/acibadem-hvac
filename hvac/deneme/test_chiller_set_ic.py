# -*- coding: utf-8 -*-
"""Chiller seti CH-x IC SET'lerden hesaplanır; "CH SET" (0103/AV12) kullanılmaz.

28.10.2026 hatası: şablondaki "CH SET" kollektör denetleyicisinin set noktasını
okuyordu (12 °C) → energy_data 27.10 Chiller_Set_Temp_C = 12, yanlış alarm.

    python test_chiller_set_ic.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402
import data_bridge as B  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# Sahadaki 28.10.2026 07:05 okuması (özet): CH-1/3/5 çalışıyor, CH-5 IC SET 3,3
SAHA = {"CH SET": 12.0, "DIS HAVA": 14.23,
        "CH-1 DURUM BILGISI": 1.0, "CH-2 DURUM BILGISI": 0.0, "CH-3 DURUM BILGISI": 1.0,
        "CH-4 DURUM BILGISI": 0.0, "CH-5 DURUM BILGISI": 1.0,
        "CH-1 IC SET": 7.5, "CH-2 IC SET": 7.5, "CH-3 IC SET": 7.5, "CH-4 IC SET": 7.5, "CH-5 IC SET": 3.3}
satir = B.build_daily_row("2026-10-28", SAHA, {})
c("CH SET (12) artik kullanilmiyor", satir["Chiller_Set_Temp_C"] != 12.0, satir["Chiller_Set_Temp_C"])
c("calisanlarin cogunlugu: 7,5 (CH-5'in 3,3'u yazilmaz)", satir["Chiller_Set_Temp_C"] == 7.5, satir["Chiller_Set_Temp_C"])
c("CH SET esleme haritasinda yok", "CH SET" not in B.BACNET_MAP)
c("bes IC SET haritada", all(("CH-%d IC SET" % i) in B.BACNET_MAP for i in range(1, 6)))


def hesap(ic, dur):
    d = {"_ch_ic_%d" % i: v for i, v in ic.items()}
    d.update({"_ch_dur_%d" % i: v for i, v in dur.items()})
    return B.chiller_set_hesapla(d)


c("hepsi ayni → o deger", hesap({1: 7.0, 2: 7.0, 3: 7.0}, {1: 1, 2: 1, 3: 0}) == 7.0)
c("yalniz calisanlar sayilir", hesap({1: 6.5, 2: 9.0}, {1: 1, 2: 0}) == 6.5)
c("hicbiri calismiyorsa okunanlarin hepsi", hesap({1: 8.0, 2: 8.0, 3: 6.0}, {}) == 8.0)
c("esitlikte ortanca", hesap({1: 7.5, 5: 3.3}, {1: 1, 5: 1}) == 5.4)
c("IC SET okunamadiysa bos (0 yazilmaz)", hesap({}, {1: 1}) == "")
c("BACnet hic yoksa bos", B.build_daily_row("2026-10-28", {}, {})["Chiller_Set_Temp_C"] == "")

sb = pd.read_excel(os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", "hedefli_okuma_sablonu_2.xlsx"))
c("depodaki sablonda CH SET satiri yok", not (sb["Point Name"].astype(str).str.strip() == "CH SET").any())
c("sablonda bes IC SET var", all(((sb["Point Name"] == "CH-%d IC SET" % i).any()) for i in range(1, 6)))

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:200]))
print("%d/%d PASS" % (sum(1 for x in T if x[1]), len(T)))
sys.exit(0 if all(x[1] for x in T) else 1)
