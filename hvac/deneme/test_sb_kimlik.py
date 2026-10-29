# -*- coding: utf-8 -*-
"""Lokasyon anahtarı (sb_kimlik.py) — 29.10.2026, denetim kritik madde 2.

    python test_sb_kimlik.py
"""
import json
import os
import re
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import sb_kimlik as K  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


_orj = K.ANAHTAR_DOSYA
tmp = tempfile.mkdtemp()
try:
    # Dosya yok → bugünkü davranış (ortak anahtar)
    K.ANAHTAR_DOSYA = os.path.join(tmp, "yok.json")
    c("anahtar yoksa ortak anahtar kullanılır", K.yetki("ORTAK") == "Bearer ORTAK")
    c("başlıklarda apikey her zaman ortak anahtar", K.basliklar("ORTAK")["apikey"] == "ORTAK")

    # Dosya var → lokasyon anahtarı
    K.ANAHTAR_DOSYA = os.path.join(tmp, "lokasyon_anahtari.json")
    json.dump({"jwt": "aaa.bbb.ccc"}, open(K.ANAHTAR_DOSYA, "w", encoding="utf-8"))
    c("anahtar varsa Authorization onunla", K.yetki("ORTAK") == "Bearer aaa.bbb.ccc")
    h = K.basliklar("ORTAK", {"Prefer": "return=minimal"})
    c("ek başlıklar korunur, apikey ortak", h["apikey"] == "ORTAK" and h["Prefer"] == "return=minimal")

    # Bozuk dosya → ortak anahtara düşer (saha kesilmez)
    open(K.ANAHTAR_DOSYA, "w", encoding="utf-8").write("{bozuk")
    c("bozuk anahtar dosyası ortak anahtara düşer", K.yetki("ORTAK") == "Bearer ORTAK")
    json.dump({"jwt": "jwt-degil"}, open(K.ANAHTAR_DOSYA, "w", encoding="utf-8"))
    c("JWT biçiminde olmayan değer kullanılmaz", K.yetki("ORTAK") == "Bearer ORTAK")

    # supabase-py istemcisi anahtarla imzalanır
    json.dump({"jwt": "aaa.bbb.ccc"}, open(K.ANAHTAR_DOSYA, "w", encoding="utf-8"))
    try:
        cl = K.istemci("https://ornek.supabase.co", "sb_publishable_ornek")
        _h = {k.lower(): v for k, v in cl.postgrest.session.headers.items()}
        c("supabase istemcisi lokasyon anahtarıyla imzalı", _h.get("authorization") == "Bearer aaa.bbb.ccc", _h.get("authorization"))
    except Exception as e:
        c("supabase istemcisi oluşturulabildi", False, e)
finally:
    K.ANAHTAR_DOSYA = _orj

# Supabase'e bağlanan HER yer sb_kimlik'ten geçer (ortak anahtar doğrudan Authorization'a yazılmaz)
for dosya in ("ahu_collector.py", "app_portal.py", "bacnet_writer.py", "oto_set.py", "veri_alarm.py"):
    s = open(os.path.join(BURASI, dosya), encoding="utf-8").read()
    c("%s lokasyon anahtarını kullanır" % dosya,
      "_sb_yetki(" in s and not re.search(r'"Authorization":\s*"Bearer "\s*\+', s))
for dosya in ("cloud_sync.py", "lisans.py"):
    s = open(os.path.join(BURASI, dosya), encoding="utf-8").read()
    c("%s istemcisi sb_kimlik.istemci ile" % dosya, "sb_kimlik.istemci(url, key)" in s)

# Anahtar dosyası yamayla gönderilmez / repoya girmez
_gi = open(os.path.join(BURASI, "..", "..", ".gitignore"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(BURASI, "..", "..", ".gitignore")) else None
if _gi is not None:
    c("anahtar dosyası .gitignore'da", "lokasyon_anahtari.json" in _gi)
c("anahtar configs/ altında (yama ve USB güncellemesi configs'e dokunmaz)",
  K.ANAHTAR_DOSYA.replace("\\", "/").endswith("configs/lokasyon_anahtari.json"))

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
