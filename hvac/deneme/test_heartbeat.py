# -*- coding: utf-8 -*-
"""Heartbeat dayaniklilik testleri — ag baglantisi YOK.

NEDEN VAR: Oto-set durumunu heartbeat'e eklerken `_oto_set_ok` bayragina
bakilmisti; oysa o bayrak start_background_sync'in YEREL degiskeni.
send_heartbeat icinden erisilince NameError olustu, distaki try bunu yuttu
ve HEARTBEAT HIC GONDERILMEDI — lokasyon cevrimdisi gorunmeye basladi.
Heartbeat kritik: kesilirse Synapse lokasyonu 'cevrimdisi' sanir ve alarm
verir. Bu yuzden HICBIR kosulda kirilmamali.
"""
import os, sys, types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud_sync

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


class SahteSorgu:
    def __init__(self, kayit):
        self.kayit = kayit

    def upsert(self, payload, **kw):
        self.kayit.append(payload)
        return self

    def execute(self):
        return types.SimpleNamespace(data=[])


class SahteClient:
    def __init__(self):
        self.yazilanlar = []

    def table(self, ad):
        return SahteSorgu(self.yazilanlar)


# ── 1) Normal durum: heartbeat gonderilir ve oto alani DOLU olur ──────────
cli = SahteClient()
cloud_sync.send_heartbeat(cli, "test_lok")
c("heartbeat gonderildi", len(cli.yazilanlar) == 1, str(len(cli.yazilanlar)))
p = cli.yazilanlar[0] if cli.yazilanlar else {}
c("lokasyon_id dogru", p.get("lokasyon_id") == "test_lok")
c("durum online", p.get("durum") == "online")
c("ping_zamani var", bool(p.get("ping_zamani")))
oto = (p.get("bakim_ozet") or {}).get("oto")
c("oto alani var", isinstance(oto, dict), str(oto))
c("oto alani sonuc icerir", bool((oto or {}).get("sonuc")), str(oto))
c("oto alani okunur metin icerir", bool((oto or {}).get("metin")), str(oto))

# ── 2) oto_set modulu YOKSA heartbeat yine gider ve sebep bildirilir ──────
_gercek = sys.modules.get("oto_set")
sys.modules["oto_set"] = None          # import'u bozar
try:
    cli2 = SahteClient()
    cloud_sync.send_heartbeat(cli2, "test_lok")
    c("oto_set yokken heartbeat YINE gonderilir", len(cli2.yazilanlar) == 1,
      str(len(cli2.yazilanlar)))
    oto2 = (cli2.yazilanlar[0].get("bakim_ozet") or {}).get("oto") if cli2.yazilanlar else None
    c("oto_set yoksa sebep bildirilir", (oto2 or {}).get("sonuc") == "modul_yok", str(oto2))
finally:
    if _gercek is not None:
        sys.modules["oto_set"] = _gercek
    else:
        sys.modules.pop("oto_set", None)

# ── 3) durum_ozet patlarsa heartbeat yine gider ───────────────────────────
import oto_set as _os_mod
_eski = _os_mod.durum_ozet


def _patla():
    raise RuntimeError("bilerek hata")


_os_mod.durum_ozet = _patla
try:
    cli3 = SahteClient()
    cloud_sync.send_heartbeat(cli3, "test_lok")
    c("durum_ozet patlarsa heartbeat YINE gonderilir", len(cli3.yazilanlar) == 1,
      str(len(cli3.yazilanlar)))
    oto3 = (cli3.yazilanlar[0].get("bakim_ozet") or {}).get("oto") if cli3.yazilanlar else None
    c("hata sebebi bildirilir", (oto3 or {}).get("sonuc") == "modul_yok", str(oto3))
finally:
    _os_mod.durum_ozet = _eski

# ── 4) _oto_durum_topla ASLA istisna atmaz ────────────────────────────────
try:
    d = cloud_sync._oto_durum_topla()
    c("_oto_durum_topla sozluk doner", isinstance(d, dict), str(type(d)))
    c("_oto_durum_topla istisna atmaz", True)
except Exception as e:
    c("_oto_durum_topla istisna atmaz", False, str(e))

# ── 5) Merkez portal her sonuc kodu icin renk tanimlamis mi ───────────────
_mk = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "merkez", "app_merkez.py")
_metin = open(_mk, encoding="utf-8").read()
_kodlar = set(_os_mod.SONUC_METIN) | {"modul_yok"}
_eksik = [k for k in _kodlar if '"%s"' % k not in _metin]
c("merkez portal tum sonuc kodlarini taniyor", not _eksik, str(_eksik))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
