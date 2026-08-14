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
        r"def _hedef_bolge.*?(?=\ndef )", r"def _ch_modu_hesapla.*?(?=\ndef )",
        r"def _dig_modu_hesapla.*?(?=\ndef )",
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


def calistir(ayarlar, tahmin=(30.0, 24.0)):
    """Tek bir _oto_set_kontrol cagrisi yapar, sahte supabase dondurur."""
    ns = kontrol_yukle()
    sb = SahteSupabase(ayarlar)
    sahte = sahte_urllib(sb)
    gercek = sys.modules.get("urllib.request")
    sys.modules["urllib.request"] = sahte
    ns["_fetch_yarin_tahmin"] = lambda: {"max": tahmin[0], "min": tahmin[1]}
    try:
        ns["_oto_set_kontrol"]("https://sahte", "anahtar")
    finally:
        if gercek is not None:
            sys.modules["urllib.request"] = gercek
    return sb


BUGUN = datetime.now(IST).strftime("%Y-%m-%d")
DUN = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
_saat = datetime.now(IST).hour
DONEM = "gunduz" if 6 <= _saat < 19 else "gece"
# gunduz -> max(30) => sicak ; gece -> min(24) => ilimli
BEKLENEN_CH = "sicak" if DONEM == "gunduz" else "ilimli"

# ── 1) Hicbir tetikleyici yok: mod ayni, donem ayni, bugun yenilenmis ──
sb = calistir({"oto_set_aktif": "true", "oto_mod_chiller": BEKLENEN_CH,
               "oto_mod_diger": "sogutma", "oto_donem": DONEM,
               "oto_son_yenileme": BUGUN})
c("tetikleyici yokken komut GONDERILMEZ", len(sb.komutlar) == 0, "%d komut" % len(sb.komutlar))
c("tetikleyici yokken log YAZILMAZ", len(sb.loglar) == 0, "%d log" % len(sb.loglar))

# ── 2) Gunluk yenileme: mod ayni ama dun yenilenmis ──
sb = calistir({"oto_set_aktif": "true", "oto_mod_chiller": BEKLENEN_CH,
               "oto_mod_diger": "sogutma", "oto_donem": DONEM,
               "oto_son_yenileme": DUN})
c("gunde bir kez yeniden gonderim yapilir", len(sb.komutlar) == 11,
  "%d komut" % len(sb.komutlar))
c("yenileme logu ayirt edilebilir (*_yenileme)",
  all(x["tip"].endswith("_yenileme") for x in sb.loglar),
  str([x["tip"] for x in sb.loglar]))
c("yenileme tarihi kaydedilir", sb.ayarlar.get("oto_son_yenileme") == BUGUN,
  str(sb.ayarlar.get("oto_son_yenileme")))

# ── 3) Ayni gun ikinci calisma: tekrar gondermez ──
sb2 = calistir(dict(sb.ayarlar))
c("ayni gun ikinci kez yeniden gondermez", len(sb2.komutlar) == 0,
  "%d komut" % len(sb2.komutlar))

# ── 4) Gercek mod degisimi: kademesiz + dogru tip ──
sb = calistir({"oto_set_aktif": "true", "oto_mod_chiller": "koc_soguk",
               "oto_mod_diger": "sogutma", "oto_donem": DONEM,
               "oto_son_yenileme": BUGUN}, tahmin=(30.0, 28.0))
ch_kom = [k for k in sb.komutlar if k["nokta_adi"].startswith("CH")]
c("mod degisiminde chiller komutlari gider", len(ch_kom) == 5, "%d" % len(ch_kom))
c("koc_soguk -> dogrudan sicak (kademesiz)",
  ch_kom and ch_kom[0]["hedef_deger"] == 6.5,
  str(ch_kom[0]["hedef_deger"]) if ch_kom else "-")
c("gercek gecis logu 'chiller' tipinde",
  any(x["tip"] == "chiller" for x in sb.loglar), str([x["tip"] for x in sb.loglar]))

# ── 5) OTO SET kapaliyken hicbir sey yapilmaz ──
sb = calistir({"oto_set_aktif": "false", "oto_mod_chiller": "koc_soguk",
               "oto_mod_diger": "isitma", "oto_donem": "", "oto_son_yenileme": DUN})
c("oto_set kapaliyken komut yok", len(sb.komutlar) == 0, "%d" % len(sb.komutlar))

# ── 6) ES ZAMANLI CALISMA: ikinci cagri kilitte durur ──
ns = kontrol_yukle()
ns["_OTO_KONTROL_LOCK"].acquire()          # birinci calisma surüyor gibi
sb = SahteSupabase({"oto_set_aktif": "true", "oto_mod_chiller": "koc_soguk",
                    "oto_mod_diger": "isitma", "oto_donem": "", "oto_son_yenileme": DUN})
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
