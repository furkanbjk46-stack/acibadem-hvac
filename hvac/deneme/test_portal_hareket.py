# -*- coding: utf-8 -*-
"""Enerji portalı hareketleri (28.10.2026): YALNIZ tasarım, değerlere dokunmaz.

    python test_portal_hareket.py
"""
import os
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import portal_hareket as PH  # noqa: E402

KAYNAK = open(os.path.join(BURASI, "portal_hareket.py"), encoding="utf-8").read()
PORTAL = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


c("kartlar süzülerek gelir", "@keyframes synGelis" in PH.CSS and 'st-key-kart_' in PH.CSS)
c("üzerine gelince yükselme var", ":hover" in PH.CSS and "translateY(-2px)" in PH.CSS)
c("enerji diyagramında canlılık (rozet nabzı)", "#ed-root .badge" in PH.CSS and "synNabiz" in PH.CSS)
c("hareket azaltma tercihi saygı görür", "prefers-reduced-motion" in PH.CSS)
# Kullanıcı kararı: sayılar sabit — sayma / akan değer YOK
c("betik yok (sayıları değiştiren JavaScript yok)", "<script" not in KAYNAK.lower())
c("metin/sayı değiştirme yok", not any(k in KAYNAK for k in ("nodeValue", "textContent", "innerText")))
c("portal hareket CSS'ini yükler", "portal_hareket" in PORTAL and "_portal_hareket.uygula(" in PORTAL)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
