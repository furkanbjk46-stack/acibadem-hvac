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
for ad, ok, ek in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(ek)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
