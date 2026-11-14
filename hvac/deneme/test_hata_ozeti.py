# -*- coding: utf-8 -*-
"""Uyarı / hata özeti (N5): şablon, gün gün sayım, 30 gün saklama, yalnız değişenlerin gönderimi. Ağ yok."""
import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import hata_ozeti as H  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


c("şablon: IP, sayı, tırnaklı değer ayıklanır",
  H.sablon("Modbus 172.17.91.121:502 zaman aşımı (3.5 sn), dosya 'C:/x/y.csv'")
  == "Modbus <ip> zaman aşımı (<n> sn), dosya '…'", H.sablon("Modbus 172.17.91.121:502 zaman aşımı (3.5 sn), dosya 'C:/x/y.csv'"))
c("şablon: aynı hata farklı sayılarla aynı şablon", H.sablon("TRDP-1 okunamadı 12 kez") == H.sablon("TRDP-1 okunamadı 7 kez"))

d = tempfile.mkdtemp(prefix="hata_ozeti_")
ZAMAN = [datetime(2026, 11, 12, 9, 0)]
t = H.Toplayici("sync", d, simdi=lambda: ZAMAN[0])
log = logging.getLogger("deneme_modul")
log.setLevel(logging.INFO)
log.addHandler(t)
log.propagate = False
log.info("bilgi satırı sayılmaz")
log.warning("Modbus 10.0.0.1 zaman aşımı")
ZAMAN[0] = datetime(2026, 11, 12, 9, 5)
log.warning("Modbus 10.0.0.2 zaman aşımı")
log.error("Supabase bağlantı hatası: %s", "timeout")
try:
    1 / 0
except ZeroDivisionError:
    log.exception("Hesap hatası")
t.yaz()
v = json.load(open(t.dosya(), encoding="utf-8"))["2026-11-12"]
modbus = [x for x in v.values() if x["sablon"].startswith("Modbus")]
c("INFO sayılmaz; aynı şablon tek satır", len(v) == 3 and len(modbus) == 1 and modbus[0]["adet"] == 2, v)
c("ilk / son zaman ve son örnek", modbus[0]["ilk"] == "2026-11-12T09:00:00" and modbus[0]["son"] == "2026-11-12T09:05:00"
  and modbus[0]["ornek"] == "Modbus 10.0.0.2 zaman aşımı", modbus[0])
c("istisna türü eklenir", any("[ZeroDivisionError]" in x["ornek"] for x in v.values()))

# Yeniden açılışta dosyadan devam eder; 30 günden eski günler silinir
t2 = H.Toplayici("sync", d, simdi=lambda: datetime(2026, 12, 20, 8, 0))
log.removeHandler(t)
log.addHandler(t2)
log.warning("Modbus 10.0.0.9 zaman aşımı")
t2.yaz()
v2 = json.load(open(t2.dosya(), encoding="utf-8"))
c("30 günden eski gün silinir, yeni gün eklenir", list(v2) == ["2026-12-20"], list(v2))
log.removeHandler(t2)

# Gönderim: iki kaynak, yalnız değişen satırlar
t3 = H.Toplayici("enerji", d, simdi=lambda: datetime(2026, 12, 20, 9, 0))
log.addHandler(t3)
log.warning("Portal grafiği çizilemedi")
t3.yaz()


class Ist:
    def __init__(self, hata=False):
        self.giden, self.hata = [], hata

    def table(self, ad):
        assert ad == "lokasyon_hatalari"
        return self

    def upsert(self, satir, **k):
        if self.hata:
            raise RuntimeError("bağlantı yok")
        self.giden.extend(satir)
        self.on_conflict = k.get("on_conflict")
        return self

    def execute(self):
        return self


SIMDI = datetime(2026, 12, 20, 10, 0)
i = Ist(hata=True)
r = H.gonder(i, "maslak", d, SIMDI)
c("bağlantı yoksa hata raporlanır, iz yazılmaz", "hata" in r)
i = Ist()
r = H.gonder(i, "maslak", d, SIMDI)
c("ilk gönderim: bütün kaynaklar", r["satir"] == 2 and {x["kaynak"] for x in i.giden} == {"sync", "enerji"}
  and i.on_conflict == "lokasyon_id,gun,anahtar", (r, i.giden))
c("satır biçimi", set(i.giden[0]) == {"lokasyon_id", "gun", "anahtar", "seviye", "kaynak", "modul", "sablon", "adet",
                                      "ilk", "son", "ornek"} and i.giden[0]["lokasyon_id"] == "maslak")
i = Ist()
c("değişiklik yoksa gönderim yok", H.gonder(i, "maslak", d, SIMDI)["satir"] == 0 and not i.giden)
log.warning("Portal grafiği çizilemedi")
t3.yaz()
i = Ist()
H.gonder(i, "maslak", d, SIMDI)
c("sayısı artan satır yeniden gider", len(i.giden) == 1 and i.giden[0]["adet"] == 2, i.giden)

# Yakalayıcı hatası programı durdurmaz
bozuk = H.Toplayici("bozuk", os.path.join(d, "yok", "\0"))
bozuk.emit(logging.LogRecord("x", logging.ERROR, "", 0, "m", None, None))
bozuk.yaz()
c("yakalayıcı hatası yutulur", True)
c("kur aynı kaynağı iki kez eklemez", H.kur("deneme_k", d) is H.kur("deneme_k", d))
logging.getLogger().removeHandler(H._KURULU.pop("deneme_k"))
log.removeHandler(t3)
shutil.rmtree(d, ignore_errors=True)
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
