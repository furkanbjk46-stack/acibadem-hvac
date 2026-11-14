# -*- coding: utf-8 -*-
"""Ayar değişikliği kaydı (Faz 1 / K1): lokasyonda değişen ayar alan alan kaydedilir ve merkeze gider."""
import json
import os
import sys
import tempfile
import time
import types

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import ayar_kaydi as A  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


def yaz(base, ad, veri):
    p = os.path.join(base, "ayar", ad)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        if isinstance(veri, (dict, list)):
            json.dump(veri, f)
        else:
            f.write(veri)
    time.sleep(0.01)


class SahteDb:
    def __init__(self, hata=False):
        self.hata, self.eklenen, self.anlik = hata, [], []

    def table(self, ad):
        db = self

        class S:
            def insert(self, satirlar, **kw):
                assert kw.get("returning") == "minimal", "ekleme satırı geri istememeli (tablo okunamaz)"
                self.islem = ("insert", ad, satirlar)
                return self

            def upsert(self, satirlar, **kw):
                self.islem = ("upsert", ad, satirlar)
                return self

            def execute(self):
                if db.hata:
                    raise RuntimeError("ağ yok")
                (db.eklenen if self.islem[0] == "insert" else db.anlik).extend(self.islem[2])
                return types.SimpleNamespace(data=[])
        return S()


d = tempfile.mkdtemp(prefix="ayar_kaydi_")
yaz(d, "hvac_settings.json", {"TARGET_DT_CHILLER": 5.0, "SAT_COOLING_MIN": 13.0})
yaz(d, "sayaclar.json", {"sayaclar": [{"ad": "TRDP-1", "ip": "1.1.1.1", "tur": "trafo"}]})
yaz(d, "supabase_config.json", {"supabase_key": "GİZLİ-ANAHTAR"})
yaz(d, "lokasyon_anahtari.json", {"jwt": "a.b.c"})
yaz(d, "bacnet_okuma_sablonu.xlsx", "ikili-dosya")

db = SahteDb()
r = A.tara_ve_gonder(db, "maslak", d)
c("ilk tur: değişiklik üretilmez, bütün ayarların hâli merkeze gider (gizliler hariç)",
  db.eklenen == [] and sorted(a["dosya"] for a in db.anlik) == ["bacnet_okuma_sablonu.xlsx", "hvac_settings.json", "sayaclar.json"])
c("bağlantı dosyası ve anahtar hiçbir yere gönderilmez",
  "GİZLİ-ANAHTAR" not in json.dumps(db.anlik, ensure_ascii=False) and "a.b.c" not in json.dumps(db.anlik))
c("JSON ayarın içeriği; xlsx base64 olarak gider (PC geri yüklemesi, F3)",
  [a for a in db.anlik if a["dosya"] == "hvac_settings.json"][0]["icerik"]["TARGET_DT_CHILLER"] == 5.0
  and [a for a in db.anlik if a["dosya"] == "bacnet_okuma_sablonu.xlsx"][0]["icerik"]
  == {"_ikili": __import__("base64").b64encode(b"ikili-dosya").decode("ascii")})
c("xlsx içeriği fark kaydına girmez",
  json.load(open(os.path.join(d, "durum", "ayar_ozet.json"), encoding="utf-8"))["bacnet_okuma_sablonu.xlsx"]["icerik"]
  is None)

# Alan değişikliği
db = SahteDb()
yaz(d, "hvac_settings.json", {"TARGET_DT_CHILLER": 6.0, "SAT_COOLING_MIN": 13.0, "YENI": 1})
A.tara_ve_gonder(db, "maslak", d)
alanlar = {x["alan"]: (x["eski"], x["yeni"]) for x in db.eklenen}
c("değişen alan eski / yeni değeriyle kaydedilir", alanlar.get("TARGET_DT_CHILLER") == ("5.0", "6.0"), alanlar)
c("eklenen alan da kaydedilir, değişmeyen alan kaydedilmez", "YENI" in alanlar and "SAT_COOLING_MIN" not in alanlar)
c("kayıtta lokasyon ve kullanıcı var", all(x["lokasyon_id"] == "maslak" and "kullanici" in x for x in db.eklenen))
c("yalnız değişen dosyanın hâli gönderilir", [a["dosya"] for a in db.anlik] == ["hvac_settings.json"])
c("yerel kalıcı kayıt (veri/ayar_degisiklikleri.jsonl)",
  sum(1 for _ in open(os.path.join(d, "veri", "ayar_degisiklikleri.jsonl"), encoding="utf-8")) == 2)

# Listede ada göre yol (sayaç eklendi)
db = SahteDb()
yaz(d, "sayaclar.json", {"sayaclar": [{"ad": "TRDP-1", "ip": "1.1.1.9", "tur": "trafo"},
                                      {"ad": "KULE-9", "ip": "2.2.2.2", "tur": "alt_sayac"}]})
A.tara_ve_gonder(db, "maslak", d)
alanlar = {x["alan"]: (x["eski"], x["yeni"]) for x in db.eklenen}
c("liste elemanı adıyla gösterilir (sayaclar[TRDP-1].ip)", alanlar.get("sayaclar[TRDP-1].ip") == ("1.1.1.1", "1.1.1.9"), alanlar)
c("yeni sayaç alanları kaydedilir", "sayaclar[KULE-9].ip" in alanlar)

# Değişiklik yoksa hiçbir şey gitmez
db = SahteDb()
r = A.tara_ve_gonder(db, "maslak", d)
c("değişiklik yoksa gönderim yok", db.eklenen == [] and db.anlik == [] and r["gonderilen"] == 0)

# Ağ yokken: sırada bekler, sonra gider
db = SahteDb(hata=True)
yaz(d, "hvac_settings.json", {"TARGET_DT_CHILLER": 7.0, "SAT_COOLING_MIN": 13.0, "YENI": 1})
r = A.tara_ve_gonder(db, "maslak", d)
c("gönderilemeyen değişiklik bekleyene alınır", r["bekleyen"] >= 1, r)
db = SahteDb()
A.tara_ve_gonder(db, "maslak", d)
c("sonraki turda bekleyen gönderilir", any(x["alan"] == "TARGET_DT_CHILLER" and x["yeni"] == "7.0" for x in db.eklenen))

# Dosya silme / ekleme
db = SahteDb()
os.remove(os.path.join(d, "ayar", "bacnet_okuma_sablonu.xlsx"))
yaz(d, "yeni_ayar.json", {"a": 1})
A.tara_ve_gonder(db, "maslak", d)
olaylar = {(x["dosya"], x["yeni"].split(" (")[0]) for x in db.eklenen}
c("silinen ve eklenen dosya kaydedilir",
  ("bacnet_okuma_sablonu.xlsx", "dosya silindi") in olaylar and ("yeni_ayar.json", "dosya eklendi") in olaylar, olaylar)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
