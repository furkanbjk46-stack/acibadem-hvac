# -*- coding: utf-8 -*-
"""İnce sayaç tablosu (D1) ve merkezde olmayan sütunun gönderimi düşürmemesi. İnternete çıkmaz."""
import json
import os
import shutil
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import sayac_gunluk as SG  # noqa: E402
import cloud_sync as CS  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


class Sorgu:
    def __init__(self, ist, tablo):
        self.i, self.tablo, self.filtre = ist, tablo, {}

    def upsert(self, kayitlar, **k):
        if self.i.upsert_hata and self.i.upsert_say >= self.i.upsert_hata:
            raise RuntimeError("bağlantı koptu")
        self.i.upsert_say += 1
        self.i.upsert.extend(kayitlar)
        self.i.on_conflict = k.get("on_conflict")
        return self

    def delete(self):
        self.silme = True
        return self

    def eq(self, a, b):
        self.filtre[a] = b
        return self

    def in_(self, a, b):
        self.i.silinen.extend(b)
        return self

    def insert(self, kayitlar):
        for s in self.i.olmayan:
            if any(s in r for r in kayitlar):
                raise Exception({"code": "PGRST204", "message": "Could not find the '%s' column of 'energy_data' "
                                                                 "in the schema cache" % s})
        self.i.eklenen.extend(kayitlar)
        return self

    def execute(self):
        return type("Cevap", (), {"data": []})()


class Ist:
    def __init__(self, olmayan=(), upsert_hata=0):
        self.upsert, self.silinen, self.eklenen = [], [], []
        self.olmayan, self.upsert_hata, self.upsert_say, self.on_conflict = set(olmayan), upsert_hata, 0, None

    def table(self, ad):
        return Sorgu(self, ad)


d = tempfile.mkdtemp(prefix="sayac_gunluk_")
os.makedirs(os.path.join(d, "ayar"))
with open(os.path.join(d, "ayar", "sayaclar.json"), "w", encoding="utf-8") as f:
    json.dump({"sayaclar": [
        {"ad": "TRDP-1", "ip": "1.1.1.1", "marka": "janitza", "tur": "trafo", "sutun": "TRDP1_kWh"},
        {"ad": "MCC-1", "ip": "1.1.1.2", "marka": "janitza", "tur": "alt_sayac", "sutun": "MCC1_kWh"},
        {"ad": "Yeni-Kule", "ip": "1.1.1.3", "marka": "siemens", "tur": "alt_sayac", "sutun": "Yeni_Kule_kWh"},
        {"ad": "Sutunsuz", "ip": "1.1.1.4", "marka": "siemens", "tur": "alt_sayac"}]}, f)

gun = [{"Tarih": "2026-11-%02d" % g, "TRDP1_kWh": 1000.0 + g, "MCC1_kWh": float("nan") if g == 3 else 200.0,
        "Yeni_Kule_kWh": 50, "Toplam_Hastane_Tuketim_kWh": 9000, "lokasyon_id": "deneme"} for g in range(1, 6)]

ist = Ist()
r = SG.gonder(ist, gun, "deneme", d)
c("ilk tur: bütün günler, sütunu olan her sayaç bir satır", r["gun"] == 5 and r["satir"] == 15 and len(ist.upsert) == 15, r)
c("satır biçimi", ist.upsert[0] == {"lokasyon_id": "deneme", "tarih": "2026-11-01", "sayac": "TRDP-1", "deger": 1001.0,
                                    "birim": "kWh", "tur": "trafo"}, ist.upsert[0])
c("NaN değer boş gider (eski değer merkezde kalmasın)",
  [x["deger"] for x in ist.upsert if x["tarih"] == "2026-11-03" and x["sayac"] == "MCC-1"] == [None])
c("çakışma anahtarı lokasyon + tarih + sayaç", ist.on_conflict == "lokasyon_id,tarih,sayac")

ist = Ist()
r = SG.gonder(ist, gun, "deneme", d)
c("değişmeyen gün tekrar gönderilmez", r["satir"] == 0 and not ist.upsert, r)

gun[1]["MCC1_kWh"] = 250.0
ist = Ist()
r = SG.gonder(ist, gun[:4], "deneme", d)
c("yalnız değişen gün gider, sahada silinen gün merkezden silinir",
  r["gun"] == 1 and {x["tarih"] for x in ist.upsert} == {"2026-11-02"} and ist.silinen == ["2026-11-05"], (r, ist.silinen))

# Yarım CSV: geçmişin çoğu kaybolursa silme yok, özet korunur
cok = [{"Tarih": "2025-%02d-%02d" % (1 + i // 28, 1 + i % 28), "TRDP1_kWh": 1.0} for i in range(300)]
SG.gonder(Ist(), cok, "yarim", d)
ist = Ist()
r = SG.gonder(ist, cok[:20], "yarim", d)
c("çok gün birden kaybolursa silme yapılmaz", not ist.silinen and r.get("silme_atlandi"), r)
ist = Ist()
SG.gonder(ist, cok, "yarim", d)
c("CSV düzelince hiçbir şey yeniden gönderilmez", not ist.upsert and not ist.silinen, len(ist.upsert))

# Gönderim yarıda koparsa giden kısım işaretlenir, kalanı sonraki turda gider
SG.PARTI = 4
ist = Ist(upsert_hata=2)
r = SG.gonder(ist, [dict(x, TRDP1_kWh=5.0) for x in gun], "kopma", d)
c("kopma: hata raporlanır", "hata" in r and r["satir"] == 8, r)
ist = Ist()
SG.gonder(ist, [dict(x, TRDP1_kWh=5.0) for x in gun], "kopma", d)
c("kopma: sonraki tur yalnız gitmeyen günleri gönderir", {x["tarih"] for x in ist.upsert} == {"2026-11-03", "2026-11-04",
                                                                                              "2026-11-05"},
  sorted({x["tarih"] for x in ist.upsert}))
SG.PARTI = 500

# energy_data'da olmayan sütun: satırlar yine gider, yalnız o sütun düşer
ist = Ist(olmayan={"Yeni_Kule_kWh"})
dusen = set()
CS._ekle_bilinmeyen_sutunsuz(ist, "energy_data", [dict(x) for x in gun], dusen)
c("merkezde olmayan sütun gönderimi düşürmez", len(ist.eklenen) == 5 and dusen == {"Yeni_Kule_kWh"}
  and all("Yeni_Kule_kWh" not in x for x in ist.eklenen) and all("TRDP1_kWh" in x for x in ist.eklenen))
ist = Ist(olmayan={"A", "B"})
dusen = set()
CS._ekle_bilinmeyen_sutunsuz(ist, "energy_data", [{"Tarih": "2026-11-01", "A": 1, "B": 2}], dusen)
c("birden fazla eksik sütun", dusen == {"A", "B"} and ist.eklenen == [{"Tarih": "2026-11-01"}])


class Bozuk(Ist):
    def table(self, ad):
        s = Sorgu(self, ad)
        s.insert = lambda k: (_ for _ in ()).throw(Exception("permission denied for table energy_data"))
        return s


try:
    CS._ekle_bilinmeyen_sutunsuz(Bozuk(), "energy_data", [{"Tarih": "x"}], set())
    c("başka hata yutulmaz", False)
except Exception as e:
    c("başka hata yutulmaz", "permission" in str(e))

shutil.rmtree(d, ignore_errors=True)
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
