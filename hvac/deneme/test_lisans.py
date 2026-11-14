# -*- coding: utf-8 -*-
"""lisans.py testi: bağlantı hatasında yeniden deneme, önbellek, alt süreç davranışı. Ağ yok."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import lisans as L  # noqa: E402

T = []


def c(ad, kosul, ek=""):
    T.append((ad, bool(kosul), ek))


def sira(*cevaplar):
    kalan = list(cevaplar)
    sayac = {"n": 0}

    def tek():
        sayac["n"] += 1
        return dict(kalan.pop(0) if len(kalan) > 1 else kalan[0])
    return tek, sayac


BAG = {"gecerli": False, "hata": "Lisans sunucusuna baglanılamadi: [Errno 11001] getaddrinfo failed"}
YOK = {"gecerli": False, "hata": "Bu cihaz icin lisans tanimli degil veya pasif."}
TAMAM = {"gecerli": True, "hata": None, "makine_id": "x"}
bekleme = []
os.environ.pop("HVAC_WATCHDOG", None)


def sifirla():
    L._SON_GECERLI.update({"zaman": 0.0, "sonuc": None})
    bekleme.clear()


sifirla()
L._lisans_kontrol_tek, s = sira(BAG, BAG, TAMAM)
r = L.lisans_kontrol(_bekle=bekleme.append)
c("açılışta ağ hazır değilse yeniden dener ve 3. denemede açılır", r["gecerli"] and s["n"] == 3 and bekleme == [10, 10], (r, s, bekleme))
sifirla()
L._lisans_kontrol_tek, s = sira(BAG)
r = L.lisans_kontrol(_bekle=bekleme.append)
c("hep bağlantı hatası: 6 deneme sonra kapalı kalır (fail-closed)", not r["gecerli"] and s["n"] == 6 and len(bekleme) == 5)
sifirla()
L._lisans_kontrol_tek, s = sira(YOK)
r = L.lisans_kontrol(_bekle=bekleme.append)
c("'lisans yok/pasif' cevabı yeniden denenmez", not r["gecerli"] and s["n"] == 1 and bekleme == [])
sifirla()
L._lisans_kontrol_tek, s = sira(TAMAM)
L.lisans_kontrol(_bekle=bekleme.append)
L.lisans_kontrol(_bekle=bekleme.append)
c("geçerli sonuç önbellekten döner (Enerji portalının her tıklaması ağa gitmez)", s["n"] == 1)
L._SON_GECERLI["zaman"] -= L.GECERLI_ONBELLEK_SN + 1
L.lisans_kontrol(_bekle=bekleme.append)
c("önbellek süresi dolunca yeniden sorar", s["n"] == 2)
sifirla()
L._lisans_kontrol_tek, s = sira(BAG)
L.lisans_kontrol(_bekle=bekleme.append)
L.lisans_kontrol(_bekle=bekleme.append)
c("hatalı sonuç önbelleğe alınmaz", s["n"] == 12)
sifirla()
os.environ["HVAC_WATCHDOG"] = "1"
L._lisans_kontrol_tek, s = sira(BAG)
r = L.lisans_kontrol(_bekle=bekleme.append)
c("watchdog alt sürecinde (Enerji portalı) yeniden deneme yok, beklemez", s["n"] == 1 and bekleme == [])
os.environ.pop("HVAC_WATCHDOG", None)

hata = [x for x in T if not x[1]]
# ── Makine kimliği: wmic yoksa PowerShell'den aynı UUID; ağ kartı adresi ikinci kimlik ──
import uuid as _uuid  # noqa: E402
_eski_co = L.subprocess.check_output


def _sahte(cevaplar):
    def co(komut, **k):
        for anahtar, cevap in cevaplar.items():
            if anahtar in komut:
                if isinstance(cevap, Exception):
                    raise cevap
                return cevap
        raise FileNotFoundError(komut)
    return co


UID = "4C4C4544-0042-3510-8051-B4C04F4B4B32"
try:
    L.subprocess.check_output = _sahte({"wmic": ("UUID  \r\n%s  \r\n" % UID).encode()})
    c("wmic varsa UUID ondan", L.makine_kimlikleri() == [UID, str(_uuid.getnode())], L.makine_kimlikleri())
    L.subprocess.check_output = _sahte({"wmic": FileNotFoundError("wmic yok"), "powershell": (UID + "\r\n").encode()})
    c("wmic yoksa aynı UUID PowerShell'den (lisans değişmez)", L.get_makine_id() == UID, L.get_makine_id())
    L.subprocess.check_output = _sahte({})
    c("ikisi de yoksa ağ kartı adresi", L.makine_kimlikleri() == [str(_uuid.getnode())])
finally:
    L.subprocess.check_output = _eski_co

# ── Lisans sorgusu iki kimliği de sorar (ağ kartı adresiyle lisanslanmış PC bozulmasın) ──
import tempfile  # noqa: E402
import types  # noqa: E402
from pathlib import Path  # noqa: E402

_sorgu = {}


class _Sb:
    def __init__(self, satirlar):
        self.s = satirlar

    def table(self, ad):
        return self

    def select(self, *a):
        return self

    def in_(self, alan, degerler):
        _sorgu["in"] = (alan, list(degerler))
        return self

    def eq(self, *a):
        return self

    def execute(self):
        return types.SimpleNamespace(data=self.s)


import importlib  # noqa: E402
L = importlib.reload(L)          # yukarıdaki testler _lisans_kontrol_tek'i sahtesiyle değiştirdi
_d = tempfile.mkdtemp()
_cfg = Path(_d) / "supabase_config.json"
_cfg.write_text('{"supabase_url": "http://x", "supabase_key": "k", "lokasyon_id": "maslak"}', encoding="utf-8")
_eski = (L.CONFIG_PATH, L.makine_kimlikleri)
import sb_kimlik  # noqa: E402
_eski_ist = sb_kimlik.istemci
try:
    L.CONFIG_PATH = _cfg
    L.makine_kimlikleri = lambda: [UID, "123456789"]
    sb_kimlik.istemci = lambda u, k: _Sb([{"aktif": True, "makine_id": "123456789", "makine_adi": "Maslak PC"}])
    r = L._lisans_kontrol_tek()
    c("lisans iki kimlikle sorulur; ağ kartı adresiyle kayıtlı PC geçerli",
      r["gecerli"] and r["makine_id"] == "123456789" and _sorgu["in"] == ("makine_id", [UID, "123456789"]), (r, _sorgu))
    sb_kimlik.istemci = lambda u, k: _Sb([])
    r = L._lisans_kontrol_tek()
    c("kayıt yoksa geçersiz, gösterilen kimlik UUID", not r["gecerli"] and r["makine_id"] == UID and "tanimli degil" in r["hata"], r)
    sb_kimlik.istemci = lambda u, k: _Sb([{"aktif": False, "makine_id": UID}])
    c("pasif lisans geçersiz", not L._lisans_kontrol_tek()["gecerli"])
finally:
    L.CONFIG_PATH, L.makine_kimlikleri = _eski
    sb_kimlik.istemci = _eski_ist

for ad, ok, ek in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(ek)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
