# -*- coding: utf-8 -*-
"""Portal açılışı — tarayıcı NE ZAMAN açılıyor (ag baglantisi YOK).

11.11.2026'da sahadan gelen sikayet: "mekanik zeka ve enerji portali cok
gec aciliyor". Portlar degismiyordu; PORTAL_BASLAT.bat 5 saniye bekleyip
tarayiciyi aciyordu ama sunucular bat'in SONUNDA (portal_watchdog.py ile)
basliyordu. Tarayici bos sayfa acip kaliyor, kullanici elle yeniliyordu.

Bu testler iki seyi tutar:
  · bat tarayiciyi ERKEN ACMAZ (acma isi watchdog'da),
  · watchdog tarayiciyi port CEVAP VERMEDEN acmaz.
"""
import io
import os
import socket
import sys
import threading
import time

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import portal_watchdog as pw  # noqa: E402

BAT = io.open(os.path.join(BURASI, "..", "PORTAL_BASLAT.bat"),
              encoding="utf-8", newline="").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── 1) PORTAL_BASLAT.bat ────────────────────────────────────────────────
# cmd'de "&" komut ayiracidir: "title HVAC & Enerji ..." once "title HVAC"
# calistirir, sonra "Enerji" KOMUT sanilip ekrana hata basilir.
c("bat: title satirindaki & kacisli (^&)",
  "title HVAC ^& Enerji" in BAT and "title HVAC & Enerji" not in BAT)
c("bat: tarayiciyi KENDI acmaz (erken acilma yok)",
  'start "" "http://127.0.0.1:8005"' not in BAT, BAT[:0])
c("bat: 5 saniyelik sahte bekleme kaldirildi", "timeout /t 5" not in BAT)
c("bat: watchdog yine calistiriliyor", "python portal_watchdog.py" in BAT)
c("bat: portal adresleri degismedi (8005 / 8501)",
  "127.0.0.1:8005" in BAT and "localhost:8501" in BAT)

# ── 2) Port dinleme kontrolu ────────────────────────────────────────────
_bos = socket.socket()
_bos.bind(("127.0.0.1", 0))
_kapali_port = _bos.getsockname()[1]
_bos.close()                      # kimse dinlemiyor
c("kapali port 'dinlemiyor' der", pw._port_dinliyor_mu(_kapali_port) is False)

_srv = socket.socket()
_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
_srv.bind(("127.0.0.1", 0))
_srv.listen(5)
_acik_port = _srv.getsockname()[1]
try:
    c("dinleyen port 'dinliyor' der", pw._port_dinliyor_mu(_acik_port) is True)

    # ── 3) _hazir_bekle ─────────────────────────────────────────────────
    _t0 = time.time()
    _hazir, _gecen = pw._hazir_bekle(_acik_port, "TEST", _t0, _t0 + 5)
    c("acik port hemen hazir sayilir", _hazir is True and _gecen < 2, (_hazir, _gecen))

    _t0 = time.time()
    _hazir, _gecen = pw._hazir_bekle(_kapali_port, "TEST", _t0, _t0 + 1.5)
    c("cevap vermeyen port sure dolunca hazir SAYILMAZ (ama kilitlemez)",
      _hazir is False and 1.0 <= _gecen < 4, (_hazir, _gecen))
finally:
    _srv.close()

# ── 4) Tarayici port hazir OLMADAN acilmaz ──────────────────────────────
_acilan = []
_orj_open, _orj_hvac = pw.webbrowser.open, pw.HVAC_PORT
_gec_srv = socket.socket()
_gec_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
_gec_srv.bind(("127.0.0.1", 0))
_gec_port = _gec_srv.getsockname()[1]
try:
    pw.webbrowser.open = lambda u: _acilan.append((u, time.time()))
    pw.HVAC_PORT = _gec_port
    pw.ENERJI_PORT = _gec_port

    _bas = time.time()
    _t = pw.tarayici_hazir_olunca("http://test", bekle_sn=8)
    time.sleep(1.5)
    c("port kapaliyken tarayici ACILMAZ", _acilan == [], _acilan)

    _gec_srv.listen(5)                      # sunucu simdi ayaga kalkti
    _t.join(timeout=8)
    c("port acilinca tarayici acilir", len(_acilan) == 1, _acilan)
    c("tarayici portun acilmasindan SONRA acildi",
      bool(_acilan) and _acilan[0][1] - _bas >= 1.4, _acilan)
    c("verilen adres kullanilir", bool(_acilan) and _acilan[0][0] == "http://test", _acilan)
finally:
    pw.webbrowser.open = _orj_open
    pw.HVAC_PORT = _orj_hvac
    pw.ENERJI_PORT = 8501
    _gec_srv.close()

# ── 5) Yeniden baslatmada tarayici tekrar ACILMAZ ───────────────────────
# start_portals guncelleme sonrasi tekrar tekrar cagriliyor; acma cagrisi
# orada DEGIL main'de olmali, yoksa her guncellemede yeni sekme acilir.
_KAYNAK = io.open(os.path.join(BURASI, "portal_watchdog.py"), encoding="utf-8").read()
_govde = _KAYNAK.split("def start_portals(")[1].split("\ndef ")[0]
c("start_portals tarayici acmaz (her restartta sekme acilmasin)",
  "tarayici_hazir_olunca" not in _govde)
c("main ilk acilista tarayiciyi acar",
  "tarayici_hazir_olunca()" in _KAYNAK.split("def main(")[1])
c("portlar sabit: 8005 / 8501",
  pw.HVAC_PORT == 8005 and pw.ENERJI_PORT == 8501 and '"--server.port", "8501"' in _KAYNAK
  and '"--port", "8005"' in _KAYNAK)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
