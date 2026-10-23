# -*- coding: utf-8 -*-
"""Animasyonlu simgeler — tek kaynak ve tutarlılık testleri.

    python merkez/test_ikonlar.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ikonlar  # noqa: E402

SONUC = []


def c(ad, kosul, ayrinti=""):
    SONUC.append(bool(kosul))
    print(("PASS " if kosul else "FAIL ") + ad + ("" if kosul else "   " + str(ayrinti)))


METRIKLER = ["enerji", "dogalgaz", "sogutma", "su", "kojen", "sebeke", "mcc", "kazan",
             "trdp", "verim", "takvim", "kollektor", "fcu", "ahu", "ariza", "bakim",
             "hvac", "alarm"]

for m in METRIKLER:
    h = ikonlar.ikon(m)
    c("%s simgesi SVG uretir" % m, "<svg" in h and "ai-%s" % m in h, h[:80])
    c("%s rengi tanimli" % m, re.fullmatch(r"#[0-9a-f]{6}", ikonlar.RENK.get(m, "")))
    c("%s animasyonu CSS'te" % m, (".ai-%s " % m) in ikonlar.CSS)

c("takma ad: chiller = sogutma (her yerde ayni simge)",
  ikonlar.ikon("chiller") == ikonlar.ikon("sogutma"))
c("takma ad: tuketim = enerji", ikonlar.ikon("tuketim") == ikonlar.ikon("enerji"))
c("bilinmeyen ad sayfayi bozmaz", ikonlar.ikon("yok_boyle") == "")
c("sakin simge animasyonsuz isaretlenir", "ai-sakin" in ikonlar.ikon("ariza", sakin=True))
c("renk CSS degiskeniyle SVG'ye baglanir", "--ai-renk:" in ikonlar.ikon("su"))
c("hareketi azalt tercihine uyulur", "prefers-reduced-motion" in ikonlar.CSS)
c("ariza: ucgen icinde unlem", "ai-unlem" in ikonlar._SVG["ariza"] and "M10.3 3.6" in ikonlar._SVG["ariza"])
c("bakim: ingiliz anahtari ve sallanma",
  "ai-anahtar" in ikonlar.CSS and ".ai-bakim svg{animation:ai-anahtar" in ikonlar.CSS)

# Ana ekran ve Dashboard simgeyi AYNI kaynaktan alır
_d = os.path.dirname(os.path.abspath(__file__))
_m = open(os.path.join(_d, "app_merkez.py"), encoding="utf-8").read()
_l = open(os.path.join(_d, "pages", "lokasyon_detay.py"), encoding="utf-8").read()
c("ana ekran simge CSS'ini yukluyor", "st.markdown(_ik.CSS" in _m)
c("dashboard simge CSS'ini yukluyor", "st.markdown(_ik.CSS" in _l)
c("global ozet simgesi ikonlar'dan", "_ik.ikon(_ozet_key" in _m)
c("global ozet cercevesi kalemin rengi", "_ik.renk(_ozet_key)" in _m)
c("canli uyarilar alarm simgesi", '_ik.ikon("alarm"' in _m)
c("lokasyon karti cercevesi kendi renginde", "--lokrenk:{renk}" in _m and "var(--lokrenk" in _m)
c("dashboard ozet kartlari ikonlar'dan", "_ik.ikon(ikon, 26)" in _l)
c("kojen&kaynak kartlarinda emoji kalmadi",
  not re.search(r'_kaynak_item\("[^a-z]', _l))
for k in ("ariza", "bakim", "hvac"):
    c("HVAC karti: %s simgesi" % k, '_ik.ikon("%s", 34' % k in _l)
for k in ("chiller", "kollektor", "fcu", "ahu"):
    c("yururlukteki setler: %s simgesi" % k, '"%s", "' % k in _l)

print("\n%d/%d PASS" % (sum(SONUC), len(SONUC)))
sys.exit(0 if all(SONUC) else 1)
