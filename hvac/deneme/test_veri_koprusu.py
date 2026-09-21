# -*- coding: utf-8 -*-
"""Veri köprüsü (data_bridge) + toplayıcı (data_collector) — trafo ve şebeke hesabı.

    python hvac/deneme/test_veri_koprusu.py

21.09.2026: TRDP-4 (Siemens PAC4200, 172.17.91.123) otomatik okumaya alındı.
Bu test, sayaç eklemenin hesapları BOZMADIĞINI garanti eder:

  - TRDP'ler şebeke tarafıdır; MCC/Chiller alt sayaç toplamına KARIŞMAZ
    (karışırsa aynı enerji iki kez sayılır)
  - Şebeke hesabı TRDP-2 ve TRDP-4'ün İKİSİNİ birden ister; yalnız biri
    doluyken alt sayaç (MCC+Chiller) yedeği korunur
  - İlk gün referans olmadığı için yeni sayaç boş kalır, çökme olmaz
"""
import os
import sys
from datetime import date, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)

import data_bridge as db
import data_collector as dc

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── 1) Toplayıcı yapılandırması ──────────────────────────────────────────
_ad = {a["name"]: a for a in dc.ANALYZERS}
c("TRDP-4 toplayıcıda tanımlı", "TRDP-4" in _ad)
c("TRDP-4 doğru adreste (172.17.91.123)", _ad.get("TRDP-4", {}).get("ip") == "172.17.91.123",
  _ad.get("TRDP-4"))
c("TRDP-4 Siemens okuyucusuyla okunur (PAC4200)", _ad.get("TRDP-4", {}).get("brand") == "siemens")
_ipler = [a["ip"] for a in dc.ANALYZERS]
c("iki cihaz aynı IP'yi paylaşmıyor", len(_ipler) == len(set(_ipler)),
  [ip for ip in _ipler if _ipler.count(ip) > 1])
_adlar = [a["name"] for a in dc.ANALYZERS]
c("iki cihaz aynı adı paylaşmıyor", len(_adlar) == len(set(_adlar)))
c("her cihazın markası okuyucusu olan bir marka",
  all(a["brand"] in ("janitza", "siemens") for a in dc.ANALYZERS))

# ── 2) TRDP'ler alt sayaç toplamına karışmaz (çift sayım koruması) ───────
for _t in ("TRDP-1", "TRDP-2", "TRDP-3", "TRDP-4"):
    c(f"{_t} MCC/Chiller toplamına girmez", _t not in db.ALL_ANALYZERS)
c("toplayıcıdaki her TRDP dışı cihaz bir gruba ait (sessizce kaybolmaz)",
  all(n in db.ALL_ANALYZERS for n in _adlar if not n.startswith("TRDP")),
  [n for n in _adlar if not n.startswith("TRDP") and n not in db.ALL_ANALYZERS])

# ── 3) Günlük satır: TRDP-4 dolar, şebeke hesabı doğru kalır ────────────
_gun = {n: 100.0 for n in db.ALL_ANALYZERS}      # her alt sayaç 100 kWh
_gun.update({"TRDP-1": 5000.0, "TRDP-3": 4000.0, "TRDP-4": 3000.0})
_mcc = sum(100.0 for n in db.ALL_ANALYZERS if n not in db.CHILLER_ANALYZERS)
_ch = sum(100.0 for n in db.CHILLER_ANALYZERS)

r = db.build_daily_row("2026-09-21", {}, _gun)
c("TRDP4_kWh sütunu dolar", r["TRDP4_kWh"] == 3000.0, r["TRDP4_kWh"])
c("TRDP-2 hâlâ boş (bağlı değil)", r["TRDP2_kWh"] == "", r["TRDP2_kWh"])
c("yalnız TRDP-4 doluyken şebeke ALT SAYAÇ yedeğiyle hesaplanır",
  r["Sebeke_Tuketim_kWh"] == round(5000 + 4000 + _mcc + _ch, 1),
  (r["Sebeke_Tuketim_kWh"], 5000 + 4000 + _mcc + _ch))
c("TRDP-4 şebekeye ayrıca EKLENMEZ (yedek zaten mekanik yükü içeriyor)",
  r["Sebeke_Tuketim_kWh"] != round(5000 + 4000 + _mcc + _ch + 3000, 1))
c("MCC toplamı TRDP-4 eklenmeden önceki ile aynı", r["MCC_Tuketim_kWh"] == round(_mcc, 1),
  (r["MCC_Tuketim_kWh"], _mcc))

# ── 4) İlk gün: referansta TRDP-4 yok → boş kalır, çökmez ──────────────
_dun = (date.today() - timedelta(days=1)).isoformat()
_ref_eski = {"date": _dun, "readings": {"TRDP-1": 1000, "TRDP-3": 2000}}   # TRDP-4 yok
_bugun = {"TRDP-1": 1500, "TRDP-3": 2600, "TRDP-4": 900000}
d = db.calc_daily_kwh(_bugun, _ref_eski)
c("ilk gün TRDP-4 günlük farkı hesaplanmaz (referans yok)", "TRDP-4" not in d, d)
c("ilk gün diğer trafolar etkilenmez", d.get("TRDP-1") == 500 and d.get("TRDP-3") == 600, d)
r0 = db.build_daily_row("2026-09-21", {}, d)
c("ilk gün TRDP4_kWh boş yazılır (0 değil — 0 gerçek tüketim sanılır)", r0["TRDP4_kWh"] == "",
  r0["TRDP4_kWh"])

# İkinci gün: referans artık TRDP-4'ü içeriyor
_ref2 = {"date": _dun, "readings": {"TRDP-1": 1000, "TRDP-3": 2000, "TRDP-4": 900000}}
d2 = db.calc_daily_kwh({"TRDP-1": 1500, "TRDP-3": 2600, "TRDP-4": 903200}, _ref2)
c("ertesi gün TRDP-4 günlük tüketimi hesaplanır", d2.get("TRDP-4") == 3200, d2)

# Sayaç sıfırlanırsa (değişim/bakım) negatif tüketim yazılmaz
d3 = db.calc_daily_kwh({"TRDP-4": 100}, {"date": _dun, "readings": {"TRDP-4": 900000}})
c("sayaç sıfırlanırsa negatif tüketim yazılmaz", d3.get("TRDP-4") == 0, d3)

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
