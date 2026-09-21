# -*- coding: utf-8 -*-
"""Anlık saha okuması (merkezden "sahadan oku") — güvenlik ve doğruluk.

    python hvac/deneme/test_anlik_okuma.py

Okuma istekleri, BACnet'e YAZMA yapan komut kanalından (komutlar tablosu)
geçer. Bu test en çok şunu garanti eder: bir okuma isteği HİÇBİR koşulda
sahaya yazmaya dönüşmez.
"""
import os
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)

import anlik_okuma as ao
import bacnet_writer as bw
import data_collector as dc

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── 1) İzin listesi ──────────────────────────────────────────────────────
c("yalnızca TRDP-4 okunabilir", ao.IZINLI == {"TRDP-4"}, ao.IZINLI)
c("okuma isteği tanınır", ao.okuma_istegi_mi("OKUMA:TRDP-4"))
c("normal set noktası okuma isteği sayılmaz", not ao.okuma_istegi_mi("CH1_REM_SET"))
c("boş/None güvenli", not ao.okuma_istegi_mi(None) and not ao.okuma_istegi_mi(""))

d, m = ao.isle("OKUMA:MCC-1")
c("izin listesinde olmayan cihaz reddedilir", d == "hata" and "izni yok" in m, (d, m))
d, m = ao.isle("OKUMA:")
c("cihaz adı boşsa reddedilir", d == "hata", (d, m))

# ── 2) Okuma sonucu (sahte sayaç) ────────────────────────────────────────
_orj_oku = dc.modbus_get_kwh
_okunan_cihaz = []


def _sahte_oku(dev):
    _okunan_cihaz.append(dev["name"])
    return 1234567.891


dc.modbus_get_kwh = _sahte_oku
try:
    d, m = ao.isle("OKUMA:TRDP-4")
finally:
    dc.modbus_get_kwh = _orj_oku
c("okunursa 'tamamlandi'", d == "tamamlandi", (d, m))
c("mesajda değer var", "1,234,567.891 kWh" in m, m)
c("mesajda cihaz adresi var", "172.17.91.123" in m, m)
c("ÜRETİMDEKİ okuyucu, doğru cihazla çağrıldı", _okunan_cihaz == ["TRDP-4"], _okunan_cihaz)

dc.modbus_get_kwh = lambda dev: None
ao._tcp_acik_mi = lambda ip, port=502, sure=3.0: False
try:
    d, m = ao.isle("OKUMA:TRDP-4")
finally:
    dc.modbus_get_kwh = _orj_oku
c("okunamazsa 'hata'", d == "hata", (d, m))
c("erişilemiyorsa teşhis ağ/TCP der", "erişilemiyor" in m, m)

dc.modbus_get_kwh = lambda dev: None
ao._tcp_acik_mi = lambda ip, port=502, sure=3.0: True
try:
    d, m = ao.isle("OKUMA:TRDP-4")
finally:
    dc.modbus_get_kwh = _orj_oku
c("port açık ama yanıt yoksa teşhis adres/birim kimliği der", "register adresi" in m, m)

# ── 3) Komut kanalında: okuma isteği YAZMAYA DÖNÜŞMEZ ───────────────────
_yazma_cagrilari = []
_guncellemeler = []
_nokta_sorgusu = []
_orj = {k: getattr(bw, k) for k in ("_sb_get", "_komut_guncelle", "yaz_dogrula_toplu",
                                    "bacnet_yaz", "geri_okuma_haritasi", "komut_suresi_doldu")}


def _sahte_get(url, key, yol):
    if "/komutlar" in yol:
        return list(_bekleyen)
    if "/lokasyon_noktalar" in yol:
        _nokta_sorgusu.append(yol)
        return [{"nokta_adi": "CH1_REM_SET", "gateway_ip": "x", "dnet": 2, "mac_hex": "01",
                 "obj_type": 2, "obj_inst": 1}]
    return []


bw._sb_get = _sahte_get
bw._komut_guncelle = lambda u, k, kid, durum, mesaj="": _guncellemeler.append((kid, durum, mesaj))
bw.yaz_dogrula_toplu = lambda isler, geri=None: (_yazma_cagrilari.append(list(isler)) or
                                                  {kid: {"durum": "oturdu", "mesaj": "ok"}
                                                   for kid, _n, _h in isler})
bw.bacnet_yaz = lambda *a, **k: (_yazma_cagrilari.append(a) or (True, "ACK"))
bw.geri_okuma_haritasi = lambda lok: {}
bw.komut_suresi_doldu = lambda created_at, simdi=None: (False, 0.5)
dc.modbus_get_kwh = lambda dev: 1000.0
ao._tcp_acik_mi = lambda ip, port=502, sure=3.0: True
try:
    # Yalnız okuma isteği
    _bekleyen = [{"id": "k1", "nokta_adi": "OKUMA:TRDP-4", "hedef_deger": 0,
                  "created_at": "2026-09-21T12:00:00+00:00"}]
    bw.komutlari_isle("u", "k", "maslak")
    c("okuma isteği BACnet'e HİÇ YAZMAZ", _yazma_cagrilari == [], _yazma_cagrilari)
    c("okuma isteği sonuçlandırılır (tamamlandi)",
      _guncellemeler and _guncellemeler[-1][:2] == ("k1", "tamamlandi"), _guncellemeler)
    c("sonuç mesajı komut satırına yazılır", "TRDP-4 okundu" in _guncellemeler[-1][2],
      _guncellemeler[-1])

    # Okuma + gerçek set birlikte: set yazılır, okuma yazılmaz
    _yazma_cagrilari.clear(); _guncellemeler.clear()
    _bekleyen = [
        {"id": "k1", "nokta_adi": "OKUMA:TRDP-4", "hedef_deger": 0, "created_at": "x"},
        {"id": "k2", "nokta_adi": "CH1_REM_SET", "hedef_deger": 7.0, "created_at": "x"},
    ]
    bw.komutlari_isle("u", "k", "maslak")
    _yazilan_idler = [kid for grup in _yazma_cagrilari for kid, _n, _h in grup]
    c("karışık listede YALNIZCA gerçek set yazılır", _yazilan_idler == ["k2"], _yazilan_idler)
    c("okuma isteği yine sonuçlandırılır",
      any(g[0] == "k1" and g[1] == "tamamlandi" for g in _guncellemeler), _guncellemeler)

    # İzinsiz cihaz: hata ile kapanır, yazma yok
    _yazma_cagrilari.clear(); _guncellemeler.clear()
    _bekleyen = [{"id": "k3", "nokta_adi": "OKUMA:CHILLER-1", "hedef_deger": 0, "created_at": "x"}]
    bw.komutlari_isle("u", "k", "maslak")
    c("izinsiz cihaz isteği 'hata' ile kapanır", _guncellemeler and _guncellemeler[-1][1] == "hata",
      _guncellemeler)
    c("izinsiz cihaz isteği de yazmaya dönüşmez", _yazma_cagrilari == [])

    # Süresi dolmuş okuma isteği okunmaz
    _yazma_cagrilari.clear(); _guncellemeler.clear()
    _okunan_cihaz.clear()
    dc.modbus_get_kwh = _sahte_oku
    bw.komut_suresi_doldu = lambda created_at, simdi=None: (True, 45.0)
    _bekleyen = [{"id": "k4", "nokta_adi": "OKUMA:TRDP-4", "hedef_deger": 0, "created_at": "x"}]
    bw.komutlari_isle("u", "k", "maslak")
    c("süresi dolmuş okuma isteği sayacı OKUMAZ", _okunan_cihaz == [], _okunan_cihaz)
    c("süresi dolmuş istek 'suresi_doldu' ile kapanır",
      _guncellemeler and _guncellemeler[-1][1] == "suresi_doldu", _guncellemeler)

    # Okuyucu patlarsa: istek hata ile kapanır, döngü çökmez
    _guncellemeler.clear()
    bw.komut_suresi_doldu = lambda created_at, simdi=None: (False, 0.5)

    def _patla(dev):
        raise RuntimeError("bilerek")
    dc.modbus_get_kwh = _patla
    _bekleyen = [{"id": "k5", "nokta_adi": "OKUMA:TRDP-4", "hedef_deger": 0, "created_at": "x"}]
    bw.komutlari_isle("u", "k", "maslak")
    c("okuyucu hata verirse istek 'hata' ile kapanır (döngü çökmez)",
      _guncellemeler and _guncellemeler[-1][1] == "hata", _guncellemeler)
finally:
    for k, v in _orj.items():
        setattr(bw, k, v)
    dc.modbus_get_kwh = _orj_oku

# ── 4) Merkez tarafı ────────────────────────────────────────────────────
_detay = open(os.path.join(os.path.dirname(os.path.dirname(BURASI)), "merkez", "pages",
                           "lokasyon_detay.py"), encoding="utf-8").read()
c("merkez okuma isteğini doğru önekle yazar", '"OKUMA:"' in _detay or "'OKUMA:'" in _detay
  or "OKUMA:{" in _detay)
c("merkez okuma isteğini 'bekliyor' olarak yazar (lokasyon yalnız bunu işler)",
  '"durum":       "bekliyor"' in _detay or '"durum": "bekliyor"' in _detay)
c("merkezde okunabilecek cihaz listesi lokasyondakiyle aynı",
  '"maslak": ["TRDP-4"]' in _detay)

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
