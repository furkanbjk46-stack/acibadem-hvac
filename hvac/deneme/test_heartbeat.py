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

# ── 6) Mekanik Zeka oz testi heartbeat'e eklenir ─────────────────────────
import oz_test

cli6 = SahteClient()
cloud_sync.send_heartbeat(cli6, "test_lok")
_hb = (cli6.yazilanlar[0].get("bakim_ozet") or {}) if cli6.yazilanlar else {}
c("heartbeat oz_test alani tasir", "oz_test" in _hb, str(list(_hb)))

_ozet = cloud_sync._oz_test_ozet()
c("_oz_test_ozet sozluk doner", isinstance(_ozet, dict), str(type(_ozet)))

# Sonuc dosyasi yoksa heartbeat BOZULMAZ (v7.1'de benzer import hatasi
# heartbeat'i kesmisti) — dosya gecici olarak yeniden adlandirilir.
_yol = oz_test.SONUC_DOSYASI
_yedek = _yol + ".test_yedek"
_vardi = os.path.exists(_yol)
if _vardi:
    os.rename(_yol, _yedek)
try:
    cli7 = SahteClient()
    cloud_sync.send_heartbeat(cli7, "test_lok")
    c("oz test sonucu yokken heartbeat YINE gonderilir", len(cli7.yazilanlar) == 1,
      str(len(cli7.yazilanlar)))
    c("oz test sonucu yoksa bos sozluk doner", cloud_sync._oz_test_ozet() == {})
finally:
    if _vardi:
        os.rename(_yedek, _yol)

# Portal acilisinda oz test baslatiliyor mu (watchdog kaynagi)
_wd = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "portal_watchdog.py"), encoding="utf-8").read()
c("watchdog acilista oz testi baslatir", "_oz_test_baslat()" in _wd and "oz_test.py" in _wd)

# Merkez portal oz test sonucunu gosteriyor mu
c("merkez portal oz test sonucunu okur", '"oz_test"' in _metin or "'oz_test'" in _metin)

# ── 7) Tasarruf onerisi geri bildirim sayaci ─────────────────────────────
# Ogrenme dongusu kurulmadan once sahada ne kadar veri oldugunu gormek icin.
import json as _json
import tempfile as _tempfile

cli8 = SahteClient()
cloud_sync.send_heartbeat(cli8, "test_lok")
_hb8 = (cli8.yazilanlar[0].get("bakim_ozet") or {}) if cli8.yazilanlar else {}
c("heartbeat geri_bildirim alani tasir", "geri_bildirim" in _hb8, str(list(_hb8)))

# Sayim dogru mu: bilinen bir veri dosyasiyla dogrulanir
_gecici = _tempfile.mkdtemp(prefix="gb_")
_veri_yolu = os.path.join(_gecici, "ml_training_data.json")


def _kayit(kural, durum):
    return {"id": f"{kural}_{durum}", "recommendation": {"rule_id": kural},
            "feedback": ({"status": durum} if durum else None)}


_ornek = (
    [_kayit("CHILLER_SET_DYNAMIC", "not_applied") for _ in range(5)] +
    [_kayit("FREE_COOLING_POTENTIAL", "applied") for _ in range(2)] +
    [_kayit("MAS_IMBALANCE", "partially_applied")] +
    [_kayit("WATER_ANOMALY", "pending")] +      # beklemede = geri bildirim SAYILMAZ
    [_kayit("WATER_ANOMALY", None)]             # isaretlenmemis = sayilmaz
)
with open(_veri_yolu, "w", encoding="utf-8") as f:
    _json.dump(_ornek, f)

_eski_lm = sys.modules.get("location_manager")


class _SahteLM:
    @staticmethod
    def get_manager():
        class _M:
            @staticmethod
            def get_data_path(ad):
                return _veri_yolu if ad == "ml_training_data.json" else ad
        return _M()


sys.modules["location_manager"] = _SahteLM
try:
    _o = cloud_sync._geri_bildirim_ozet()
    c("toplam kayit dogru sayiliyor", _o.get("kayit") == 10, str(_o.get("kayit")))
    c("yalnizca isaretlenmisler geri bildirim sayilir (beklemede/bos haric)",
      _o.get("geri_bildirim") == 8, str(_o.get("geri_bildirim")))
    c("uygulandi/uygulanmadi ayrimi dogru",
      _o.get("uygulandi") == 2 and _o.get("uygulanmadi") == 5 and _o.get("kismi") == 1, str(_o))
    c("5 geri bildirime ulasan kural ogrenmeye hazir sayilir",
      _o.get("ogrenmeye_hazir_kural") == ["CHILLER_SET_DYNAMIC"], str(_o.get("ogrenmeye_hazir_kural")))
    c("en cok reddedilen kural raporlanir",
      (_o.get("en_cok_red") or [{}])[0].get("kural") == "CHILLER_SET_DYNAMIC", str(_o.get("en_cok_red")))
    c("ozet KUCUK tutulur (heartbeat 2 dakikada bir gider)",
      len(_json.dumps(_o)) < 400, str(len(_json.dumps(_o))))

    # Bozuk dosya heartbeat'i BOZMAMALI
    with open(_veri_yolu, "w", encoding="utf-8") as f:
        f.write("{bozuk json")
    c("bozuk veri dosyasinda ozet bos doner, cokmez", cloud_sync._geri_bildirim_ozet() == {})
    cli9 = SahteClient()
    cloud_sync.send_heartbeat(cli9, "test_lok")
    c("bozuk veri dosyasinda heartbeat YINE gonderilir", len(cli9.yazilanlar) == 1)
finally:
    if _eski_lm is not None:
        sys.modules["location_manager"] = _eski_lm
    else:
        sys.modules.pop("location_manager", None)

# Lokasyona OZGU gostergeler detay sayfasinda gosterilir (genel ozet kartinda
# degil): lokasyon sayisi arttikca genel kart okunamaz hale geliyordu.
_detay_yol = os.path.join(os.path.dirname(_mk), "pages", "lokasyon_detay.py")
_detay = open(_detay_yol, encoding="utf-8").read()
c("lokasyon detay sayfasi geri bildirim sayacini gosterir",
  'bakim_ozet.get("geri_bildirim")' in _detay and "ÖNERİ GERİ BİLDİRİMİ" in _detay)
c("lokasyon detay sayfasi oz test sonucunu gosterir",
  'bakim_ozet.get("oz_test")' in _detay and "ÖZ TESTİ" in _detay)
c("lokasyon detay sayfasi oto-set durumunu gosterir",
  'bakim_ozet.get("oto")' in _detay and "OTO-SET" in _detay)
c("genel ozet karti lokasyona ozgu sayaclarla doldurulmuyor",
  "ÖNERİ GERİ BİLDİRİMİ" not in _metin)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
