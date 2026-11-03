# -*- coding: utf-8 -*-
"""Ay karşılaştırması ve grafik Excel paketi (ag baglantisi YOK).

Ay karşılaştırmasının iki eski hatası burada kilitli:
  · ayın 1'i dönem dışı kalıyordu (başlangıç tarihi şu anki saati taşıyordu)
  · ayın ilk günü, ayda henüz veri yokken pencere hata verip açılmıyordu
Excel dosyasının üretimi yalnız openpyxl kuruluysa denenir.
"""
import io
import os
import sys
from datetime import date, datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import grafik_veri as G  # noqa: E402

_gecen = _kalan = 0


def c(ad, kosul, ayrinti=""):
    global _gecen, _kalan
    if kosul:
        _gecen += 1
        print("PASS", ad)
    else:
        _kalan += 1
        print("FAIL", ad, ayrinti)


def k(t, v, kolon="Toplam_Hastane_Tuketim_kWh", **ek):
    return dict({"Tarih": t, kolon: v}, **ek)


# ── Ay karşılaştırması ──
_v = [k(datetime(2026, 9, 1), 100.0), k(datetime(2026, 9, 2), 200.0),
      k(datetime(2025, 9, 1), 80.0), k(datetime(2025, 9, 2), 120.0), k(datetime(2025, 9, 3), 999.0),
      k(datetime(2026, 10, 1), 7777.0), k(datetime(2025, 10, 1), 8888.0)]
_a = G.ay_kiyas(_v, 2026, 9)
c("seçilen ay gelir, başka ay karışmaz", _a["bu"] == {1: 100.0, 2: 200.0}, _a)
c("ayın 1'i dönem içinde", 1 in _a["bu"] and 1 in _a["gec"], _a)
c("geçen yılın aynı ayı tam gelir", _a["gec"] == {1: 80.0, 2: 120.0, 3: 999.0}, _a)
c("yüzde yalnız ortak günlerden", _a["ortak_gun"] == 2 and _a["bu_top"] == 300 and _a["gec_top"] == 200, _a)
c("fark yüzdesi doğru", abs(_a["fark_pct"] - 50) < 1e-9, _a)

_b = G.ay_kiyas(_v, 2026, 11)
c("ayda veri yokken hata vermez", _b["bu"] == {} and _b["fark_pct"] is None and _b["ortak_gun"] == 0, _b)
_c = G.ay_kiyas([k(datetime(2025, 11, 5), 50.0)], 2026, 11)
c("yalnız geçen yıl varsa yüzde üretilmez", _c["gec"] == {5: 50.0} and _c["fark_pct"] is None, _c)
_d = G.ay_kiyas([k(datetime(2026, 9, 1), float("nan")), k(datetime(2026, 9, 2), None),
                 k(datetime(2025, 9, 1), 10.0)], 2026, 9)
c("boş / NaN değer 0 sayılmaz", _d["bu"] == {}, _d)
_e = G.ay_kiyas([k(date(2024, 2, 29), 1.0), k(date(2023, 2, 28), 2.0)], 2024, 2)
c("artık yıl: 29 Şubat sorun çıkarmaz", _e["bu"] == {29: 1.0} and _e["fark_pct"] is None, _e)
_f = G.ay_kiyas([k("2026-09-01", 5.0)], 2026, 9)
c("metin tarih de çözülür", _f["bu"] == {1: 5.0}, _f)

# ── Excel paketi ──
_r = [{"Tarih": datetime(2026, 9, 1), "Toplam_Hastane_Tuketim_kWh": 100.0, "Sebeke_Tuketim_kWh": 60.0,
       "Kojen_Uretim_kWh": 40.0, "Su_Tuketimi_m3": 5.0, "Chiller_Set_Temp_C": 7.0, "Dis_Hava_Sicakligi_C": 20.0,
       "TRDP1_kWh": 30.0, "TRDP10_kWh": 1.0, "TRDP2_kWh": 20.0, "Chiller1_kWh": 9.0, "Kule1_kWh": 3.0,
       "Toplam_Sogutma_Tuketim_kWh": 12.0, "MCC_Tuketim_kWh": 8.0, "MCC1_kWh": 5.0, "MCC_CK_D01_kWh": 3.0,
       "Kazan_Dogalgaz_m3": 2.0, "Kojen_Dogalgaz_m3": 4.0},
      {"Tarih": datetime(2026, 9, 2), "Toplam_Hastane_Tuketim_kWh": 300.0, "Sebeke_Tuketim_kWh": float("nan"),
       "Kojen_Uretim_kWh": 60.0, "Su_Tuketimi_m3": 7.0, "Chiller_Set_Temp_C": 9.0, "Dis_Hava_Sicakligi_C": 22.0}]

_tp = G.grafik_tablosu("tuketim", _r)
_t = _tp["tablolar"][0]
c("tüketim: kolonlar", _t["sutunlar"][:2] == ["Tarih", "Toplam Hastane Tüketim (kWh)"], _t["sutunlar"])
c("tüketim: gün başına satır", [s[0] for s in _t["satirlar"]] == [date(2026, 9, 1), date(2026, 9, 2)], _t["satirlar"])
c("eksik değer boş kalır, 0 yazılmaz", _t["satirlar"][1][2] is None, _t["satirlar"])
c("özet: toplam/ortalama/min/max", _tp["ozet"][0][1:] == [400.0, 200.0, 100.0, 300.0], _tp["ozet"])

_ch = G.grafik_tablosu("chiller", _r)
c("sıcaklıkta dönem toplamı yazılmaz", _ch["ozet"][0][1] is None and _ch["ozet"][0][2] == 8.0, _ch["ozet"])

_tr = G.grafik_tablosu("trafo", _r)["tablolar"][0]["sutunlar"]
c("trafolar adından bulunur ve sayıya göre sıralı", _tr == ["Tarih", "TRDP1 (kWh)", "TRDP2 (kWh)", "TRDP10 (kWh)"], _tr)
_so = G.grafik_tablosu("sogutma", _r)["tablolar"][0]["sutunlar"]
c("soğutma: chiller ve kule detayı var", "Chiller1 (kWh)" in _so and "Kule1 (kWh)" in _so, _so)
_mc = G.grafik_tablosu("mcc", _r)["tablolar"][0]["sutunlar"]
c("mcc: alt panolar var, ana kolon iki kez yazılmaz",
  "MCC1 (kWh)" in _mc and "MCC CK D01 (kWh)" in _mc and _mc.count("MCC Tüketim (kWh)") == 1, _mc)
_ve = G.grafik_tablosu("verimlilik", _r, m2=100)
c("kWh/m² hesaplanır", _ve["tablolar"][0]["satirlar"][0][-1] == 1.0, _ve["tablolar"][0]["satirlar"])
_ki = G.grafik_tablosu("enerji_kirilim", _r)
c("kırılım: iki tablo", [t["ad"] for t in _ki["tablolar"]] == ["Kaynak", "Tüketim"], _ki)
_kp = G.grafik_tablosu("kpi_ozet", _r, m2=100)
c("KPI: kWh/m² satırı var", any(s[0] == "kWh/m²" for s in _kp["tablolar"][0]["satirlar"]), _kp)
_ay = G.grafik_tablosu("ay_karsilastir", [], tum_kayitlar=_v, yil=2026, ay=9, ay_adi="Eylül 2026", gec_ay_adi="Eylül 2025")
_ays = _ay["tablolar"][0]["satirlar"]
c("ay tablosu: fark ortak günde", _ays[0] == [1, 80.0, 100.0, 20.0, 25.0], _ays)
c("ay tablosu: tek yıldaki gün farksız", _ays[2] == [3, 999.0, None, None, None], _ays)
c("veri yoksa paket yok (buton çıkmaz)",
  G.grafik_tablosu("su", []) is None and G.grafik_tablosu("su", [{"Tarih": datetime(2026, 9, 1)}]) is None
  and G.grafik_tablosu("ay_karsilastir", [], tum_kayitlar=[], yil=2026, ay=9) is None)
c("bilinmeyen grafik paket üretmez", G.grafik_tablosu("yok", _r) is None)

try:
    import openpyxl
except ImportError:
    openpyxl = None
    print("ATLANDI: openpyxl kurulu değil, Excel dosyası üretimi denenmedi")
if openpyxl:
    for _tip in ("tuketim", "su", "sebeke", "trafo", "kojen", "kazan", "chiller", "sogutma", "mcc",
                 "verimlilik", "kpi_ozet", "enerji_kirilim", "ay_karsilastir"):
        _p = G.grafik_tablosu(_tip, _r, m2=100, tum_kayitlar=_v, yil=2026, ay=9,
                              ay_adi="Eylül 2026", gec_ay_adi="Eylül 2025")
        _x = G.xlsx_uret("Grafik", "Maslak", "01.09 → 02.09.2026", _p, "03.11.2026")
        _w = openpyxl.load_workbook(io.BytesIO(_x))
        c("xlsx açılır: %s" % _tip, _w.sheetnames[0] == "Özet" and len(_w.sheetnames) >= 2, _w.sheetnames)

print("\n%d/%d PASS" % (_gecen, _gecen + _kalan))
sys.exit(1 if _kalan else 0)
