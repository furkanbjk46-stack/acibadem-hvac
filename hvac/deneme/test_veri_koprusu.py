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
# 29.09.2026: TRDP-2 ve MCC-5 sahada devreye alındı.
c("TRDP-2 toplayıcıda tanımlı", "TRDP-2" in _ad)
c("TRDP-2 doğru adreste (172.17.91.119)", _ad.get("TRDP-2", {}).get("ip") == "172.17.91.119",
  _ad.get("TRDP-2"))
c("TRDP-2 Janitza okuyucusuyla okunur", _ad.get("TRDP-2", {}).get("brand") == "janitza")
c("MCC-5 toplayıcıda tanımlı", "MCC-5" in _ad)
c("MCC-5 doğru adreste (172.17.91.104)", _ad.get("MCC-5", {}).get("ip") == "172.17.91.104",
  _ad.get("MCC-5"))
c("MCC-5 Janitza okuyucusuyla okunur", _ad.get("MCC-5", {}).get("brand") == "janitza")
c("MCC-5 alt sayaç toplamına GİRER (tüketim kalemi)", "MCC-5" in db.ALL_ANALYZERS)
c("MCC-5 chiller sayılmaz", "MCC-5" not in db.CHILLER_ANALYZERS)
c("MCC-5 MCC grubunda", "MCC-5" in db.MCC_ONLY_ANALYZERS)
c("MCC5_kWh şemada var", "MCC5_kWh" in db.ENERGY_SCHEMA)
c("MCC1-7 arası hiçbir pano atlanmadı",
  all("MCC%d_kWh" % i in db.ENERGY_SCHEMA for i in range(1, 8)),
  [i for i in range(1, 8) if "MCC%d_kWh" % i not in db.ENERGY_SCHEMA])
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
# Üretim sayaçları (kojen, "uretim": True) da tüketim toplamına girmez
_tuketim = [a["name"] for a in dc.ANALYZERS if not a["name"].startswith("TRDP") and not a.get("uretim")]
c("toplayıcıdaki her TRDP/üretim dışı cihaz bir gruba ait (sessizce kaybolmaz)",
  all(n in db.ALL_ANALYZERS for n in _tuketim),
  [n for n in _tuketim if n not in db.ALL_ANALYZERS])
c("üretim sayaçları tüketim toplamına girmez",
  not any(a["name"] in db.ALL_ANALYZERS for a in dc.ANALYZERS if a.get("uretim")))

# (tarihler Haziran öncesi: bu bölüm ESKİ şebeke kuralını sınar — yeni kural 01.06.2026'dan)
# ── 3) Günlük satır: TRDP-4 dolar, şebeke hesabı doğru kalır ────────────
_gun = {n: 100.0 for n in db.ALL_ANALYZERS}      # her alt sayaç 100 kWh
_gun.update({"TRDP-1": 5000.0, "TRDP-3": 4000.0, "TRDP-4": 3000.0})
_mcc = sum(100.0 for n in db.ALL_ANALYZERS if n not in db.CHILLER_ANALYZERS)
_ch = sum(100.0 for n in db.CHILLER_ANALYZERS)

r = db.build_daily_row("2026-05-21", {}, _gun)
c("TRDP4_kWh sütunu dolar", r["TRDP4_kWh"] == 3000.0, r["TRDP4_kWh"])
c("TRDP-2 okunamadıysa boş kalır (0 yazılmaz)", r["TRDP2_kWh"] == "", r["TRDP2_kWh"])
_dort_trafo = db.build_daily_row("2026-05-29", {}, {
    "TRDP-1": 5000.0, "TRDP-2": 6000.0, "TRDP-3": 4000.0, "TRDP-4": 3000.0})
c("dört trafo da okunuyor", [_dort_trafo["TRDP%d_kWh" % i] for i in (1, 2, 3, 4)]
  == [5000.0, 6000.0, 4000.0, 3000.0])
c("şebeke DÖRT trafonun toplamı (eksik ölçüm bitti)",
  _dort_trafo["Sebeke_Tuketim_kWh"] == 18000.0, _dort_trafo["Sebeke_Tuketim_kWh"])
c("MCC-5 günlük satıra yazılır",
  db.build_daily_row("2026-05-29", {}, {"MCC-5": 777.0})["MCC5_kWh"] == 777.0)
c("şebeke = ÖLÇÜLEN trafoların toplamı (alt sayaç yedeği YOK)",
  r["Sebeke_Tuketim_kWh"] == round(5000 + 4000 + 3000, 1),
  (r["Sebeke_Tuketim_kWh"], 5000 + 4000 + 3000))
# Çift sayım koruması: MCC/Chiller analizörleri kaynağa bakmadan tüketimi
# ölçer; kojen çalışırken o yükleri kojen besler. Şebekeye eklenirlerse
# kojen bir kez orada, bir kez "Kojen Üretim" olarak sayılıyordu.
c("MCC/Chiller şebekeye KARIŞMAZ (kojen çift sayılmasın)",
  r["Sebeke_Tuketim_kWh"] != round(5000 + 4000 + _mcc + _ch, 1)
  and r["Sebeke_Tuketim_kWh"] != round(5000 + 4000 + 3000 + _mcc + _ch, 1))
c("eksik trafo şebekeyi ŞİŞİRMEZ, eksik bırakır (TRDP-2 yok)",
  r["Sebeke_Tuketim_kWh"] < round(5000 + 4000 + 3000 + _mcc + _ch, 1))

# Tek trafo bile gelse o trafo şebekeye yazılır (kullanıcı kuralı).
_tek = db.build_daily_row("2026-05-21", {}, {"TRDP-3": 4200.0})
c("tek trafo doluysa şebeke o trafodur", _tek["Sebeke_Tuketim_kWh"] == 4200.0,
  _tek["Sebeke_Tuketim_kWh"])
_dort = db.build_daily_row("2026-05-21", {},
                           {"TRDP-1": 1000.0, "TRDP-3": 2000.0, "TRDP-4": 3000.0})
c("dört trafodan üçü doluysa toplamı yazılır",
  _dort["Sebeke_Tuketim_kWh"] == 6000.0, _dort["Sebeke_Tuketim_kWh"])
_yok = db.build_daily_row("2026-05-21", {}, {n: 100.0 for n in db.ALL_ANALYZERS})
c("hiç trafo yoksa şebeke BOŞ bırakılır (uydurma toplam yok)",
  _yok["Sebeke_Tuketim_kWh"] == "", _yok["Sebeke_Tuketim_kWh"])
c("MCC toplamı TRDP-4 eklenmeden önceki ile aynı", r["MCC_Tuketim_kWh"] == round(_mcc, 1),
  (r["MCC_Tuketim_kWh"], _mcc))

# ── 3b) Kojen sayaçları (27.10.2026): trafo toplamı kojeni içerir ────────
# Haziran 2026 öncesi gün: eski kural (trafo toplamı) — 30.10.2026'dan beri yeni kural 01.06'dan başlar
_kj = db.build_daily_row("2026-05-28", {}, {
    "TRDP-1": 22000.0, "TRDP-2": 16000.0, "TRDP-3": 8000.0, "TRDP-4": 12000.0,
    "KOJEN-3": 11000.0, "KOJEN-4": 10500.0, **{n: 100.0 for n in db.ALL_ANALYZERS}})
c("Kojen3/4 günlük satıra yazılır", (_kj["Kojen3_kWh"], _kj["Kojen4_kWh"]) == (11000.0, 10500.0))
c("bağlı olmayan Kojen1/2 BOŞ kalır (0 yazılmaz)", (_kj["Kojen1_kWh"], _kj["Kojen2_kWh"]) == ("", ""))
c("kojen üretim = okunan kojenlerin toplamı", _kj["Kojen_Uretim_kWh"] == 21500.0, _kj["Kojen_Uretim_kWh"])
c("dört trafo: toplam hastane = trafo toplamı", _kj["Toplam_Hastane_Tuketim_kWh"] == 58000.0,
  _kj["Toplam_Hastane_Tuketim_kWh"])
c("dört trafo: şebeke = trafo − kojen", _kj["Sebeke_Tuketim_kWh"] == 58000.0 - 21500.0,
  _kj["Sebeke_Tuketim_kWh"])
c("kojen sayaçları ENERGY_SCHEMA'da (satırdan düşmez)",
  all("Kojen%d_kWh" % i in db.ENERGY_SCHEMA for i in range(1, 5)))
import enerji_hesap as _eh  # noqa: E402
import pandas as _pd  # noqa: E402
_eh_r = _eh.yeniden_hesapla(_pd.DataFrame([_kj])).iloc[0]
c("köprü ile enerji_hesap AYNI sonucu verir",
  (_eh_r["Sebeke_Tuketim_kWh"], _eh_r["Toplam_Hastane_Tuketim_kWh"], _eh_r["Kojen_Uretim_kWh"])
  == (_kj["Sebeke_Tuketim_kWh"], _kj["Toplam_Hastane_Tuketim_kWh"], _kj["Kojen_Uretim_kWh"]))

# ── 3c) 29.10.2026 kuralı: köprü yeni günde şebekeyi BOŞ bırakır (elle girilecek) ──
_yk = db.build_daily_row("2026-10-29", {}, {
    "TRDP-1": 22000.0, "TRDP-2": 16000.0, "TRDP-3": 8000.0, "TRDP-4": 12000.0,
    "KOJEN-3": 11000.0, "KOJEN-4": 10500.0})
c("yeni günde şebeke trafodan hesaplanmaz, boş kalır", _yk["Sebeke_Tuketim_kWh"] == "", _yk["Sebeke_Tuketim_kWh"])
c("yeni günde toplam şimdilik yalnız kojen", _yk["Toplam_Hastane_Tuketim_kWh"] == 21500.0,
  _yk["Toplam_Hastane_Tuketim_kWh"])
c("trafolar yine yazılır (bilgi olarak)", _yk["TRDP1_kWh"] == 22000.0)

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

# ── 6) Günlük okuma takvimi (30.10.2026: 07:00 → 23:59) ─────────────────
_mb = (dc.READ_SAAT, dc.READ_DAKIKA)
_bn = (dc.BACNET_SAAT, dc.BACNET_DAKIKA)
_kp = (db.SNAPSHOT_HOUR, db.SNAPSHOT_MINUTE)
c("Modbus okuması 23:59", _mb == (23, 59), _mb)
c("BACnet sabah 07:05'te kalır (kullanıcı kararı, B seçeneği)", _bn == (7, 5), _bn)
c("köprü gece yarısından SONRA, okumadan önce değil (00:05)", _kp == (0, 5), _kp)
c("köprü 00:05'te: dünün 23:59 sayaç ve 07:05 BACnet okuması aynı takvim gününe ait",
  _kp < _bn < _mb)
_yas = (24 - _bn[0]) + _kp[0] + (_kp[1] - _bn[1]) / 60.0   # 07:05 → ertesi 00:05
c("BACnet tazelik sınırı köprünün normal okumasını kapsar (~17 sa) ve telafiye pay bırakır",
  _yas < db.BACNET_TAZELIK_SAAT and db.BACNET_TAZELIK_SAAT >= 26, (_yas, db.BACNET_TAZELIK_SAAT))
c("tek dakikalık 23:59 penceresi kaçmasın: kontrol aralığı < 60 sn", dc.KONTROL_SN < 60, dc.KONTROL_SN)

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
