# -*- coding: utf-8 -*-
"""OTO-MOD mod hesabi testleri — kademesiz gecis + histerezis.
   python merkez/test_oto_mod.py

Kaynak: hvac/deneme/oto_set.py — yani SAHAYA SET GONDEREN kodun kendisi.
(01.10.2026'ya kadar app_merkez.py'deki kopyadan okunuyordu; o kopya
silindi, kural artik tek yerde.)"""
import os
import re
import sys

_KAYNAK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "hvac", "deneme", "oto_set.py")
_metin = open(_KAYNAK, encoding="utf-8").read()

# Sadece ilgili sabitleri ve saf fonksiyonlari calistir (Streamlit import etmeden)
_ns = {}
for _desen in [
    r"CH_SINIRLAR\s*=.*?\n", r"CH_MODLAR\s*=.*?\n", r"CH_SET\s*=.*?\n",
    r"CH_H\s*=.*?\n", r"DIG_SINIRLAR\s*=.*?\n", r"DIG_MODLAR\s*=.*?\n",
    r"DIG_H\s*=.*?\n",
    r"def _bolge\(.*?(?=\ndef )", r"def _bolgeli_mod.*?(?=\ndef )",
    r"def _hedef_bolge.*?(?=\ndef )", r"def ch_modu_hesapla.*?(?=\ndef )",
    r"def dig_modu_hesapla.*?(?=\ndef )",
]:
    m = re.search(_desen, _metin, re.DOTALL)
    if not m:
        print("BULUNAMADI:", _desen)
        sys.exit(1)
    exec(m.group(0), _ns)

ch = _ns["ch_modu_hesapla"]
dig = _ns["dig_modu_hesapla"]
SET = _ns["CH_SET"]

T = []
def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))

# Bolgeler: <7 koc_soguk(8.0) | 7-23 serin(7.5) | 23-26 ilimli(7.0) | >=26 sicak(6.5)
# Histerezis _CH_H = 2

# ── KADEMESIZ GECIS (kullanicinin istedigi) ──
# sicak(6.5) iken hava 15'e duserse: cikis kosulu 15 < 26-2=24 saglanir,
# hedef bolge 15 -> serin(7.5). Tek adimda gitmeli.
s = ch(15.0, "sicak")
c("sicak -> 15C -> serin (tek adimda, 6.5->7.5)", s == "serin", "sonuc=%s set=%s" % (s, SET[s]))

s = ch(5.0, "sicak")
c("sicak -> 5C -> koc_soguk (uc bolge birden)", s == "koc_soguk", "sonuc=%s" % s)

s = ch(30.0, "koc_soguk")
c("koc_soguk -> 30C -> sicak (uc bolge birden)", s == "sicak", "sonuc=%s" % s)

# ── HISTEREZIS KORUNUYOR MU ──
# serin bolgesi 7-23. Ustten cikmak icin >23+2=25 gerekir.
c("serin, 24C -> bolgede kalir (histerezis)", ch(24.0, "serin") == "serin")
c("serin, 25.5C -> ilimli'ye gecer", ch(25.5, "serin") == "ilimli")
# Alttan cikmak icin <7-2=5 gerekir
c("serin, 6C -> bolgede kalir (histerezis)", ch(6.0, "serin") == "serin")
c("serin, 4.5C -> koc_soguk'a gecer", ch(4.5, "serin") == "koc_soguk")

# ── SINIRDA GIDIP GELME (flapping) OLMAMALI ──
mod = "serin"
gecmis = []
for t in [23.5, 24.0, 23.2, 24.4, 23.8]:      # sinir civarinda salinim
    mod = ch(t, mod)
    gecmis.append(mod)
c("sinir civarinda salinimda mod degismez", all(m == "serin" for m in gecmis), str(gecmis))

# ── BILINMEYEN MOD ──
c("bilinmeyen mod -> dogrudan hesaplanir", ch(24.0, "") == "ilimli", ch(24.0, ""))
c("bilinmeyen mod (soguk)", ch(3.0, "yok") == "koc_soguk")

# ── STABILITE: ayni sicaklikta tekrar cagirinca degismemeli ──
m1 = ch(15.0, "sicak")
m2 = ch(15.0, m1)
c("hedefe varinca sabit kalir (tekrar komut yok)", m1 == m2 == "serin", "%s -> %s" % (m1, m2))

# ── DIGER (kollektor/FCU/AHU) — IKI ESIK (15 ve 23), histerezis 3 ──
# 01.10.2026'da 15 esigi eklenirken 23 esigi yanlislikla KALDIRILMISTI; mod
# ikiliye dustu ve 23 ustunde kollektor gunduz 10'da kaliyordu (tabloda 8).
# 16.10.2026'da iki esik birlikte geri kondu. Beklentiler esiklerden
# turetilir: esik degisirse test kuralin KENDISINI dogrular.
_S = _ns["DIG_SINIRLAR"]
_H = _ns["DIG_H"]
c("iki esik var (15 ve 23)", len(_S) == 2, _S)
_ALT, _UST = _S[0], _S[1]                       # 15, 23

# Mod yokken: dogrudan bolgesine duser
c("mod yokken alt esik alti -> isitma", dig(_ALT - 0.5, None) == "isitma")
c("mod yokken iki esik arasi -> sogutma", dig(_ALT + 0.5, None) == "sogutma")
c("mod yokken ust esik ustu -> yogun_sogutma",
  dig(_UST + 0.5, None) == "yogun_sogutma", dig(_UST + 0.5, None))

# Alt esik (15) histerezisi — chiller surekli calismasin diye eklenmisti
c("sogutma, alt esik-1 -> hala sogutma (histerezis tutuyor)",
  dig(_ALT - 1, "sogutma") == "sogutma")
c("sogutma, alt esik-H-1 -> isitma", dig(_ALT - _H - 1, "sogutma") == "isitma")
c("isitma, alt esik+1 -> hala isitma (histerezis tutuyor)",
  dig(_ALT + 1, "isitma") == "isitma")
c("isitma, alt esik+H+1 -> sogutma", dig(_ALT + _H + 1, "isitma") == "sogutma")

# Ust esik (23) histerezisi — 23 ustunde kollektor 8'e inmeli
c("sogutma, ust esik+1 -> hala sogutma (histerezis tutuyor)",
  dig(_UST + 1, "sogutma") == "sogutma")
c("sogutma, ust esik+H+1 -> yogun_sogutma",
  dig(_UST + _H + 1, "sogutma") == "yogun_sogutma",
  dig(_UST + _H + 1, "sogutma"))
c("yogun_sogutma, ust esik-1 -> hala yogun_sogutma",
  dig(_UST - 1, "yogun_sogutma") == "yogun_sogutma")
c("yogun_sogutma, ust esik-H-1 -> sogutma",
  dig(_UST - _H - 1, "yogun_sogutma") == "sogutma")

# Kademesiz: yaz ortasindan kisa tek adimda
c("yogun_sogutma -> alt esik alti -> isitma (kademesiz)",
  dig(_ALT - _H - 1, "yogun_sogutma") == "isitma",
  dig(_ALT - _H - 1, "yogun_sogutma"))

hata = sum(1 for _, ok, _ in T if not ok)
print()
for ad, ok, d in T:
    print(("PASS " if ok else "FAIL ") + ad + (("   [%s]" % d) if (d and not ok) else ""))
print("\n%d/%d PASS" % (len(T) - hata, len(T)))
sys.exit(1 if hata else 0)
