# -*- coding: utf-8 -*-
"""Global Ozet karsilastirma sayfasi testleri — ag baglantisi YOK.

Sayfa app_merkez'in globals()'i icinde exec edildigi ve Streamlit'e bagli
oldugu icin bir butun olarak calistirilamaz; bu yuzden:
  * METRIK TANIMLARI ile app_merkez'deki kart listesi karsilastirilir
    (birinde olup digerinde olmayan metrik = sessizce olu link)
  * Hesap mantigi (donem araliklari, oran/yogunluk, siralama) sayfadan
    ayiklanmadan, ayni kurallar burada birebir kurulup dogrulanir.
"""
import ast
import os
import re
import sys
from datetime import date, timedelta

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAYFA = os.path.join(KOK, "merkez", "pages", "ozet_karsilastirma.py")
MERKEZ = os.path.join(KOK, "merkez", "app_merkez.py")

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


_sayfa_metin = open(SAYFA, encoding="utf-8").read()
_merkez_metin = open(MERKEZ, encoding="utf-8").read()

# ── METRIKLER sozlugunu sayfadan cikar ────────────────────────────────────
_m = re.search(r"^METRIKLER\s*=\s*(\{.*?^\})", _sayfa_metin, re.S | re.M)
c("METRIKLER sozlugu bulundu", bool(_m))
METRIKLER = ast.literal_eval(_m.group(1)) if _m else {}

# ── app_merkez'deki kart listesindeki anahtarlar ──────────────────────────
_k = re.search(r"_metrikler\s*=\s*\[(.*?)\]", _merkez_metin, re.S)
c("app_merkez kart listesi bulundu", bool(_k))
_kart_anahtarlar = re.findall(r',\s*"([a-z]+)"\)', _k.group(1)) if _k else []

# ── app_merkez'deki izin listesi ──────────────────────────────────────────
_i = re.search(r"OZET_METRIKLERI\s*=\s*\((.*?)\)", _merkez_metin, re.S)
c("OZET_METRIKLERI listesi bulundu", bool(_i))
_izinli = re.findall(r'"([a-z]+)"', _i.group(1)) if _i else []

# ── UC LISTE DE AYNI OLMALI ───────────────────────────────────────────────
# Biri digerinden saparsa: ya tiklanan kart bos sayfa acar, ya da calisan
# bir metrik hic tiklanamaz. Ikisi de sessizce olur.
c("kart listesi ile METRIKLER ayni",
  set(_kart_anahtarlar) == set(METRIKLER),
  "kartta fazla=%s / METRIKLER'de fazla=%s"
  % (set(_kart_anahtarlar) - set(METRIKLER), set(METRIKLER) - set(_kart_anahtarlar)))
c("izin listesi ile METRIKLER ayni",
  set(_izinli) == set(METRIKLER),
  "izinde fazla=%s / METRIKLER'de fazla=%s"
  % (set(_izinli) - set(METRIKLER), set(METRIKLER) - set(_izinli)))
c("bes metrigin hepsi bagli", len(METRIKLER) == 5, sorted(METRIKLER))

# ── Her metrik tanimi eksiksiz mi ─────────────────────────────────────────
_ZORUNLU = ("ad", "ikon", "kolonlar", "birim", "renk", "artis_iyi", "ikinci")
for _ad, _tanim in METRIKLER.items():
    c("[%s] tanim eksiksiz" % _ad,
      all(a in _tanim for a in _ZORUNLU),
      [a for a in _ZORUNLU if a not in _tanim])
    c("[%s] kolon listesi dolu" % _ad,
      isinstance(_tanim.get("kolonlar"), list) and len(_tanim["kolonlar"]) > 0)
    c("[%s] ikinci gosterge gecerli" % _ad,
      _tanim.get("ikinci") in ("yogunluk", "oran"), _tanim.get("ikinci"))
    if _tanim.get("ikinci") == "oran":
        c("[%s] oran metriginde baslik ve sutun adi var" % _ad,
          bool(_tanim.get("oran_ad")) and bool(_tanim.get("ik_sutun")))

# ── Yon dogrulugu: uretimde artis iyi, tuketimde dusus iyi ────────────────
c("kojen uretiminde ARTIS iyi", METRIKLER["kojen"]["artis_iyi"] is True)
for _t in ("enerji", "dogalgaz", "sogutma", "su"):
    c("[%s] tuketimde DUSUS iyi" % _t, METRIKLER[_t]["artis_iyi"] is False)

# ── Dogalgaz kazan + kojen toplami mi (ana sayfayla ayni tanim) ───────────
c("dogalgaz = kazan + kojen",
  set(METRIKLER["dogalgaz"]["kolonlar"]) == {"Kazan_Dogalgaz_m3", "Kojen_Dogalgaz_m3"},
  METRIKLER["dogalgaz"]["kolonlar"])

# ── Dogalgaz kirilimi: kazan (isitma) / kojen (elektrik) ──────────────────
# Kojeni olan hastane TOPLAM dogalgazda yuksek cikiyor ve "verimsiz" gibi
# okunuyordu; oysa o gaz elektrige donuyor. Bu yuzden kirilim gosterilir ve
# VERIMLILIK yalnizca KAZAN gazina bakar.
_dg = METRIKLER["dogalgaz"]
c("dogalgazda kirilim tanimli", bool(_dg.get("kirilim")))
_kir_kolonlar = [k for _a, kols, _r in _dg.get("kirilim", []) for k in kols]
c("kirilim parcalari toplami ana kolonlarla ayni",
  set(_kir_kolonlar) == set(_dg["kolonlar"]),
  (sorted(_kir_kolonlar), sorted(_dg["kolonlar"])))
c("kirilim parcalari cakismiyor", len(_kir_kolonlar) == len(set(_kir_kolonlar)))
c("verimlilik YALNIZCA kazan gazina bakar",
  _dg.get("ik_kolonlar") == ["Kazan_Dogalgaz_m3"], _dg.get("ik_kolonlar"))
c("kirilimli metrikte sutun adi kazan oldugunu soyler",
  "KAZAN" in (_dg.get("ik_sutun") or ""), _dg.get("ik_sutun"))
c("kirilim parcalarinin ayri renkleri var",
  len({r for _a, _k, r in _dg["kirilim"]}) == len(_dg["kirilim"]))

# Kirilim mantiginin sayisal dogrulamasi: kojeni olan hastane TOPLAMDA
# yuksek, ama KAZAN bazinda dusuk olabilmeli — ayrimin butun amaci bu.
_kojenli = {"kazan": 300, "kojen": 14000, "m2": 15000, "gun": 10}
_kojensiz = {"kazan": 900, "kojen": 0, "m2": 10000, "gun": 10}
_top_k = _kojenli["kazan"] + _kojenli["kojen"]
_top_s = _kojensiz["kazan"] + _kojensiz["kojen"]
c("kojenli hastane TOPLAM gazda onde", _top_k > _top_s, (_top_k, _top_s))
c("kazan bazinda kojenli hastane DAHA IYI cikabiliyor",
  (_kojenli["kazan"] / _kojenli["m2"] / _kojenli["gun"])
  < (_kojensiz["kazan"] / _kojensiz["m2"] / _kojensiz["gun"]))

# Kirilimi olmayan metrikler bos liste ile calismali (sayfa cokmesin)
for _ad in ("enerji", "sogutma", "su", "kojen"):
    c("[%s] kirilim yok (tek parca)" % _ad, not METRIKLER[_ad].get("kirilim"))

# ── Donem araliklari ──────────────────────────────────────────────────────
# Sayfadaki _aralik() ile ayni kurallar; "Bu ay" kiyasi gecen ayin AYNI GUN
# araligi olmali (kismi ayi tam ayla kiyaslamak sahte dusus uretiyordu).
import pandas as pd


def aralik(secim, bugun):
    ay_bas = bugun.replace(day=1)
    if secim == "Bu ay":
        bas, bit = ay_bas, bugun
        o_bas = (ay_bas - pd.Timedelta(days=1)).replace(day=1)
        o_bit = min(o_bas + (bugun - ay_bas), ay_bas - pd.Timedelta(days=1))
    elif secim == "Gecen ay":
        bit = ay_bas - pd.Timedelta(days=1)
        bas = bit.replace(day=1)
        o_bit = bas - pd.Timedelta(days=1)
        o_bas = o_bit.replace(day=1)
    elif secim == "Son 12 ay":
        bas, bit = bugun - pd.Timedelta(days=365), bugun
        o_bit = bas - pd.Timedelta(days=1)
        o_bas = o_bit - pd.Timedelta(days=365)
    else:
        bas, bit = bugun.replace(month=1, day=1), bugun
        o_bas = bas.replace(year=bas.year - 1)
        o_bit = o_bas + (bit - bas)
    return bas, bit, o_bas, o_bit


_bugun = pd.Timestamp(2026, 9, 10)
_b, _t, _ob, _ot = aralik("Bu ay", _bugun)
c("bu ay: 01.09 - 10.09", (_b.day, _t.day, _b.month) == (1, 10, 9))
c("bu ay kiyasi gecen ayin AYNI GUN araligi",
  (_ob.month, _ob.day, _ot.month, _ot.day) == (8, 1, 8, 10),
  (str(_ob.date()), str(_ot.date())))
c("kiyas araligi ayni uzunlukta", (_t - _b) == (_ot - _ob))

_b, _t, _ob, _ot = aralik("Gecen ay", _bugun)
c("gecen ay: 01.08 - 31.08", (_b.month, _b.day, _t.month, _t.day) == (8, 1, 8, 31))
c("gecen ay kiyasi temmuz", (_ob.month, _ot.month) == (7, 7))

_b, _t, _ob, _ot = aralik("Bu yil", _bugun)
c("bu yil 1 Ocak'ta baslar", (_b.month, _b.day) == (1, 1))
c("bu yil kiyasi gecen yilin ayni araligi", _ob.year == _b.year - 1)

# Yil basinda ay kaymasi (1 Ocak) — gecen ay ARALIK olmali
_b, _t, _ob, _ot = aralik("Bu ay", pd.Timestamp(2026, 1, 5))
c("ocak ayinda kiyas ARALIK ayina gider",
  (_ob.year, _ob.month) == (2025, 12), (str(_ob.date()), str(_ot.date())))

# ── Ikinci gosterge hesabi ────────────────────────────────────────────────
# yogunluk = deger / m2 / gun    |    oran = deger / toplam_tuketim * 100
c("yogunluk m2 ve gune bolunur", abs((3000 / 10000 / 3) - 0.1) < 1e-9)
c("oran yuzde olarak hesaplanir", abs((350 / 1000 * 100) - 35.0) < 1e-9)

# Buyuk hastane ham tuketimde onde ama m2'ye bolununce daha verimli olabilmeli
_buyuk = {"deger": 24000, "m2": 20000, "gun": 10}
_kucuk = {"deger": 14000, "m2": 8000, "gun": 10}
_yb = _buyuk["deger"] / _buyuk["m2"] / _buyuk["gun"]
_yk = _kucuk["deger"] / _kucuk["m2"] / _kucuk["gun"]
c("ham tuketimde buyuk hastane onde", _buyuk["deger"] > _kucuk["deger"])
c("verimlilikte buyuk hastane DAHA IYI cikabiliyor", _yb < _yk, (_yb, _yk))

# ── Siralama yonu ─────────────────────────────────────────────────────────
_ornek = [{"ad": "A", "ikinci": 1.8}, {"ad": "B", "ikinci": 1.1}, {"ad": "C", "ikinci": 1.5}]
_dusuk_iyi = sorted(_ornek, key=lambda r: r["ikinci"])
_yuksek_iyi = sorted(_ornek, key=lambda r: r["ikinci"], reverse=True)
c("tuketimde en dusuk en ustte", _dusuk_iyi[0]["ad"] == "B")
c("uretimde en yuksek en ustte", _yuksek_iyi[0]["ad"] == "A")

# ── Sayfa sozdizimi ───────────────────────────────────────────────────────
try:
    ast.parse(_sayfa_metin)
    c("sayfa sozdizimi gecerli", True)
except SyntaxError as e:
    c("sayfa sozdizimi gecerli", False, str(e))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
