# -*- coding: utf-8 -*-
"""_oto_set_kontrol akis testleri — SAHTE Supabase ile, ag baglantisi YOK.
   python merkez/test_oto_kontrol.py

Bu kod hastane BMS'ine setpoint komutu yazdigi icin tetikleyici mantigi
(mod degisimi / gunluk yenileme / es zamanli calisma) test edilir.
"""
import json
import os
import re
import sys
import threading
import types
from datetime import datetime, timedelta, timezone

_KAYNAK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_merkez.py")
_metin = open(_KAYNAK, encoding="utf-8").read()

IST = timezone(timedelta(hours=3))


class SahteSupabase:
    """Supabase REST'i taklit eder; gonderilen komut ve loglari biriktirir."""

    def __init__(self, ayarlar):
        self.ayarlar = dict(ayarlar)
        self.komutlar = []
        self.loglar = []

    def _get(self, url):
        if "/ayarlar?key=eq." in url:
            k = url.split("key=eq.")[1].split("&")[0]
            v = self.ayarlar.get(k)
            return [{"value": v}] if v is not None else []
        if "/lokasyon_noktalar" in url:
            return [{"lokasyon": "maslak"}]
        return []

    def _post(self, url, govde):
        d = json.loads(govde.decode())
        if "/komutlar" in url:
            self.komutlar.extend(d)
        elif "/oto_mod_log" in url:
            self.loglar.extend(d)
        elif "/ayarlar" in url:
            self.ayarlar[d["key"]] = d["value"]
        return []


def sahte_urllib(sb):
    m = types.ModuleType("urllib.request")

    class Request:
        def __init__(self, url, data=None, headers=None, method=None):
            self.url, self.data = url, data
            self.method = method or ("POST" if data else "GET")

    class Yanit:
        def __init__(self, govde):
            self._g = json.dumps(govde).encode()

        def read(self):
            return self._g

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        if req.method == "GET":
            return Yanit(sb._get(req.url))
        return Yanit(sb._post(req.url, req.data))

    m.Request, m.urlopen = Request, urlopen
    return m


def kontrol_yukle():
    """app_merkez.py'den saf parcalari cikarip calistirilabilir ad alani dondurur."""
    ns = {"logging": __import__("logging"), "_threading": threading,
          "_OTO_KONTROL_LOCK": threading.Lock()}
    desenler = [
        r"_CH_SINIRLAR\s*=.*?\n", r"_CH_MODLAR\s*=.*?\n", r"_CH_SET\s*=.*?\n",
        r"_CH_H\s*=.*?\n", r"_DIG_ESIK\s*=.*?\n", r"_DIG_H\s*=.*?\n",
        r"_DIG_SET\s*=\s*\{.*?\n\}\n", r"_CH_NOKTALAR\s*=.*?\n",
        r"_OTO_GUNDUZ_VARSAYILAN\s*=.*?\n", r"_OTO_GECE_VARSAYILAN\s*=.*?\n",
        r"def _hedef_bolge.*?(?=\ndef )", r"def _ch_modu_hesapla.*?(?=\ndef )",
        r"def _dig_modu_hesapla.*?(?=\n_OTO_GUNDUZ)",
        r"def _donem_hesapla.*?(?=\ndef )",
        r"def _oto_set_kontrol.*?(?=\n# ─── Arka plan)",
    ]
    for d in desenler:
        m = re.search(d, _metin, re.DOTALL)
        if not m:
            raise SystemExit("BULUNAMADI: " + d)
        exec(m.group(0), ns)
    return ns


T = []
def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def calistir(ayarlar, tahmin=(30.0, 24.0), bugun_min=20.0, yarin_max=31.0):
    """Tek bir _oto_set_kontrol cagrisi yapar, sahte supabase dondurur.
    tahmin = (bugun_max, yarin_min) — kodun gercekten kullandigi iki deger."""
    ns = kontrol_yukle()
    sb = SahteSupabase(ayarlar)
    sahte = sahte_urllib(sb)
    gercek = sys.modules.get("urllib.request")
    sys.modules["urllib.request"] = sahte
    ns["_fetch_tahmin"] = lambda: {"bugun_max": tahmin[0], "yarin_min": tahmin[1],
                                   "bugun_min": bugun_min, "yarin_max": yarin_max}
    try:
        ns["_oto_set_kontrol"]("https://sahte", "anahtar")
    finally:
        if gercek is not None:
            sys.modules["urllib.request"] = gercek
    return sb


ns0 = kontrol_yukle()
_dh = ns0["_donem_hesapla"]

# ── 0) Donem hesabi (yapılandirilabilir saatler) ──
c("05:00-22:00 -> 05'te gunduz baslar", _dh(5, 5, 22) == "gunduz")
c("04:59 hala gece", _dh(4, 5, 22) == "gece")
c("21 gunduz", _dh(21, 5, 22) == "gunduz")
c("22 gece baslar", _dh(22, 5, 22) == "gece")
c("gece yarisini asan aralik (22->5) desteklenir",
  _dh(23, 22, 5) == "gunduz" and _dh(3, 22, 5) == "gunduz" and _dh(10, 22, 5) == "gece")

# Testler saatten bagimsiz olsun diye: mevcut saate gore donem hesaplanir
_saat = datetime.now(IST).hour
SIMDI = _dh(_saat, 5, 22)
DIGER = "gece" if SIMDI == "gunduz" else "gunduz"
# gunduz -> max ; gece -> min referans alinir
BEKLENEN_CH = "sicak" if SIMDI == "gunduz" else "ilimli"   # 30 / 24 ile

TEMEL = {"oto_set_aktif": "true", "oto_mod_chiller": BEKLENEN_CH,
         "oto_mod_diger": "sogutma", "oto_gunduz_saat": "5", "oto_gece_saat": "22"}

# ── 1) DONEM AYNI: mod degisse bile komut GITMEZ (kullanici karari) ──
sb = calistir(dict(TEMEL, oto_donem=SIMDI, oto_mod_chiller="koc_soguk"))
c("donem ayniyken komut GONDERILMEZ (mod farkli olsa da)",
  len(sb.komutlar) == 0, "%d komut" % len(sb.komutlar))
c("donem ayniyken log YAZILMAZ", len(sb.loglar) == 0, "%d log" % len(sb.loglar))
c("donem ayniyken durum yine de guncellenir",
  "oto_set_son_kontrol" in sb.ayarlar)

# ── 2) DONEM GECISI: setler gider ──
sb = calistir(dict(TEMEL, oto_donem=DIGER))
c("donem gecisinde 11 komut gider", len(sb.komutlar) == 11, "%d" % len(sb.komutlar))
c("donem gecisinde donem kaydedilir", sb.ayarlar.get("oto_donem") == SIMDI,
  str(sb.ayarlar.get("oto_donem")))

# ── 3) Gecis + mod DEGISMEMIS: log '*_yenileme' olarak isaretlenir ──
c("mod degismediyse log yenileme tipinde",
  all(x["tip"].endswith("_yenileme") for x in sb.loglar),
  str([x["tip"] for x in sb.loglar]))

# ── 4) Gecis + GERCEK mod degisimi: kademesiz + dogru tip ──
sb = calistir(dict(TEMEL, oto_donem=DIGER, oto_mod_chiller="koc_soguk"),
              tahmin=(30.0, 28.0))
ch_kom = [k for k in sb.komutlar if k["nokta_adi"].startswith("CH")]
c("mod degisiminde chiller komutlari gider", len(ch_kom) == 5, "%d" % len(ch_kom))
c("koc_soguk -> dogrudan sicak/ilimli (kademesiz)",
  ch_kom and ch_kom[0]["hedef_deger"] in (6.5, 7.0),
  str(ch_kom[0]["hedef_deger"]) if ch_kom else "-")
c("gercek gecis logu 'chiller' tipinde",
  any(x["tip"] == "chiller" for x in sb.loglar), str([x["tip"] for x in sb.loglar]))

# ── 5) OTO SET kapaliyken hicbir sey yapilmaz ──
sb = calistir(dict(TEMEL, oto_set_aktif="false", oto_donem=DIGER))
c("oto_set kapaliyken komut yok", len(sb.komutlar) == 0, "%d" % len(sb.komutlar))

# ── 5b) DOGRU REFERANS: gunduz->BUGUN max, gece->YARIN min ──
# Bugun sicak (30) ama yarin serin (15). Gunduz setinde BUGUNUN degeri
# kullanilmalidir; yarininki kullanilsaydi sicak bir gune yanlis set giderdi.
sb = calistir(dict(TEMEL, oto_donem=DIGER, oto_mod_chiller="serin"),
              tahmin=(30.0, 24.0), yarin_max=15.0)
_ch = [k for k in sb.komutlar if k["nokta_adi"].startswith("CH")]
_ref_log = sb.loglar[0]["tahmin_ort"] if sb.loglar else None
if SIMDI == "gunduz":
    c("gunduz referansi BUGUNUN max'i (30) — yarininki (15) degil",
      _ref_log == 30.0, "referans=%s" % _ref_log)
    c("gunduz setinde sicak bolge (6.5) gider",
      _ch and _ch[0]["hedef_deger"] == 6.5, str(_ch[0]["hedef_deger"]) if _ch else "-")
else:
    c("gece referansi YARININ min'i (24)", _ref_log == 24.0, "referans=%s" % _ref_log)

# ── 6) ES ZAMANLI CALISMA: ikinci cagri kilitte durur ──
ns = kontrol_yukle()
ns["_OTO_KONTROL_LOCK"].acquire()          # birinci calisma surüyor gibi
sb = SahteSupabase(dict(TEMEL, oto_donem=DIGER))
sahte = sahte_urllib(sb)
gercek = sys.modules.get("urllib.request")
sys.modules["urllib.request"] = sahte
ns["_fetch_yarin_tahmin"] = lambda: {"max": 30.0, "min": 24.0}
try:
    ns["_oto_set_kontrol"]("https://sahte", "anahtar")
finally:
    sys.modules["urllib.request"] = gercek
c("es zamanli ikinci calisma komut GONDERMEZ (yaris korumasi)",
  len(sb.komutlar) == 0, "%d komut" % len(sb.komutlar))

hata = sum(1 for _, ok, _ in T if not ok)
print()
for ad, ok, d in T:
    print(("PASS " if ok else "FAIL ") + ad + (("   [%s]" % d) if (d and not ok) else ""))
print("\n%d/%d PASS" % (len(T) - hata, len(T)))
sys.exit(1 if hata else 0)
