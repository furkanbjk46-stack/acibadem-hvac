# -*- coding: utf-8 -*-
"""Yama dağıtımı testleri (yol haritası A1, A2) — ağ YOK, gerçek program klasörüne yazılmaz.

NEDEN VAR: guncellemeler'de yama başına tek satır / tek durum vardı. hedef='all'
yamasını ilk alan lokasyon 'tamamlandi' yapıyor, diğer lokasyonlar hiç görmüyordu.
Artık her lokasyon yama_uygulamalari'na kendi satırını yazar; 'all' satırına dokunmaz.
"""
import json
import logging
import os
import sys
import tempfile
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud_sync  # noqa: E402

# Test, repodaki cloud_sync.log'a yazmasın
for _h in list(logging.getLogger().handlers):
    if _h.__class__.__name__ == "RotatingFileHandler":
        logging.getLogger().removeHandler(_h)
        _h.close()
logging.getLogger().setLevel(logging.CRITICAL)

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


class SahteDb:
    """supabase-py zincirinin kullanılan kısmı: table().select().eq().in_().order().execute(),
    insert().execute(), update().eq().execute(). Tablolar bellekte."""

    def __init__(self, guncellemeler, uygulamalar=None, uygulama_hatasi=False):
        self.t = {"guncellemeler": guncellemeler, "yama_uygulamalari": list(uygulamalar or [])}
        self.uygulama_hatasi = uygulama_hatasi
        self.yazilan = []

    def table(self, ad):
        return Sorgu(self, ad)


class Sorgu:
    def __init__(self, db, ad):
        self.db, self.ad, self.filtre, self.islem, self.veri = db, ad, [], "select", None

    def select(self, *_):
        return self

    def eq(self, k, v):
        self.filtre.append(lambda r: r.get(k) == v)
        return self

    def in_(self, k, v):
        self.filtre.append(lambda r: r.get(k) in v)
        return self

    def order(self, *_, **__):
        return self

    def insert(self, veri):
        self.islem, self.veri = "insert", veri
        return self

    def update(self, veri):
        self.islem, self.veri = "update", veri
        return self

    def execute(self):
        if self.ad == "yama_uygulamalari" and self.db.uygulama_hatasi:
            raise RuntimeError("relation yama_uygulamalari does not exist")
        tablo = self.db.t[self.ad]
        if self.islem == "insert":
            if any(r["yama_id"] == self.veri["yama_id"] and r["lokasyon_id"] == self.veri["lokasyon_id"]
                   for r in tablo):
                raise RuntimeError("duplicate key")
            tablo.append(dict(self.veri))
            self.db.yazilan.append((self.ad, "insert", dict(self.veri)))
            return types.SimpleNamespace(data=[])
        satirlar = [r for r in tablo if all(f(r) for f in self.filtre)]
        if self.islem == "update":
            for r in satirlar:
                r.update(self.veri)
            self.db.yazilan.append((self.ad, "update", dict(self.veri)))
            return types.SimpleNamespace(data=[])
        return types.SimpleNamespace(data=[dict(r) for r in satirlar])


def yama(i, hedef, dosyalar, durum="bekliyor"):
    return {"id": "y%d" % i, "versiyon": "13.%d" % i, "hedef": hedef, "dosyalar": dosyalar,
            "durum": durum, "created_at": "2026-11-12T10:%02d:00" % i}


def klasor():
    d = tempfile.mkdtemp(prefix="yama_test_")
    return d


def oku(d, ad):
    with open(os.path.join(d, ad), encoding="utf-8") as f:
        return f.read()


# 1) 'all' yaması iki lokasyona da gider; satırın durumuna lokasyon dokunmaz
ortak = [yama(1, "all", {"a.py": "A1"})]
db = SahteDb(ortak)
d_m, d_a = klasor(), klasor()
cloud_sync.check_and_apply_update(db, "maslak", base_dir=d_m)
c("maslak 'all' yamasını uygular", oku(d_m, "a.py") == "A1")
c("'all' satırının durumu lokasyon tarafından değiştirilmez", ortak[0]["durum"] == "bekliyor", ortak[0])
c("maslak uygulama kaydı yazılır", {"yama_id": "y1", "lokasyon_id": "maslak", "durum": "tamamlandi",
                                    "versiyon": "13.1", "hatali_dosyalar": []} in db.t["yama_uygulamalari"],
  db.t["yama_uygulamalari"])
cloud_sync.check_and_apply_update(db, "atasehir", base_dir=d_a)
c("ataşehir de aynı 'all' yamasını alır (eski hata: hiç almıyordu)", oku(d_a, "a.py") == "A1")
c("iki lokasyonun ayrı uygulama kaydı var",
  sorted(r["lokasyon_id"] for r in db.t["yama_uygulamalari"]) == ["atasehir", "maslak"])

# 2) Aynı lokasyon ikinci turda 'all' yamasını yeniden uygulamaz
open(os.path.join(d_m, "a.py"), "w", encoding="utf-8").write("SAHADA DEĞİŞTİ")
os.remove(os.path.join(d_m, "_restart.flag"))
cloud_sync.check_and_apply_update(db, "maslak", base_dir=d_m)
c("uygulanmış 'all' yaması tekrar yazılmaz", oku(d_m, "a.py") == "SAHADA DEĞİŞTİ")
c("yeni bir şey yoksa yeniden başlatma bayrağı yazılmaz", not os.path.exists(os.path.join(d_m, "_restart.flag")))

# 3) Lokasyona özel yama eskisi gibi kapanır; başka lokasyonun yaması alınmaz
ozel = [yama(2, "maslak", {"b.py": "B"}), yama(3, "atasehir", {"c.py": "C"})]
db = SahteDb(ozel)
d = klasor()
cloud_sync.check_and_apply_update(db, "maslak", base_dir=d)
c("maslak'a özel yama uygulanır ve satırı kapanır", oku(d, "b.py") == "B" and ozel[0]["durum"] == "tamamlandi")
c("başka lokasyonun yaması uygulanmaz", not os.path.exists(os.path.join(d, "c.py")) and ozel[1]["durum"] == "bekliyor")

# 4) Kronolojik sıra: aynı dosyada en yeni kazanır; tek yeniden başlatma
db = SahteDb([yama(4, "maslak", {"x.py": "eski"}), yama(5, "all", {"x.py": "yeni"})])
d = klasor()
cloud_sync.check_and_apply_update(db, "maslak", base_dir=d)
c("aynı dosyada son yama kazanır", oku(d, "x.py") == "yeni")
c("son yama sürümü son_yama.json'a yazılır (A2)", json.load(open(os.path.join(d, "durum", "son_yama.json")))["versiyon"] == "13.5")
c("normal dosyada yalnız portal yeniden başlatma", os.path.exists(os.path.join(d, "_restart.flag"))
  and not os.path.exists(os.path.join(d, "_full_restart.flag")))

db = SahteDb([yama(6, "maslak", {"cloud_sync.py": "# yeni"})])
d = klasor()
cloud_sync.check_and_apply_update(db, "maslak", base_dir=d)
c("cloud_sync değişince tam yeniden başlatma", os.path.exists(os.path.join(d, "_full_restart.flag")))

# 5) Güvenlik: program klasörünün dışına yazılmaz
dis = klasor()
hedef_dis = os.path.join(dis, "kotu.py")
db = SahteDb([yama(7, "maslak", {"../" + os.path.basename(dis) + "/kotu.py": "X", "C:/Windows/kotu.py": "X",
                                 os.path.join(dis, "mutlak.py"): "X", "iyi.py": "ok"})])
d = klasor()
cloud_sync.check_and_apply_update(db, "maslak", base_dir=d)
c("../ ile dışarı yazılmaz", not os.path.exists(hedef_dis))
c("mutlak yol yazılmaz", not os.path.exists(os.path.join(dis, "mutlak.py")))
c("geçerli dosya yine yazılır", oku(d, "iyi.py") == "ok")
k = [r for r in db.t["yama_uygulamalari"] if r["yama_id"] == "y7"][0]
c("dışarıyı gösteren yama 'hata' olarak kaydedilir, hatalı dosyalar listelenir",
  k["durum"] == "hata" and len(k["hatali_dosyalar"]) == 3, k)
c("alt klasöre yazmaya izin var", cloud_sync._guvenli_yol(d, "static/vendor/a.js") is not None)

# 5b) Geri alma için yedek (A4): değişen / silinen dosyanın eski hâli durum/yama_yedek/<sürüm>/ altında
d = klasor()
os.makedirs(os.path.join(d, "static"), exist_ok=True)
open(os.path.join(d, "main_portal.py"), "w", encoding="utf-8").write("ESKİ KOD")
open(os.path.join(d, "static", "index.html"), "w", encoding="utf-8").write("ESKİ ARAYÜZ")
open(os.path.join(d, "silinecek.py"), "w", encoding="utf-8").write("SİLİNEN")
db = SahteDb([yama(20, "maslak", {"main_portal.py": "YENİ KOD", "static/index.html": "YENİ", "silinecek.py": "",
                                  "yeni_dosya.py": "x"})])
cloud_sync.check_and_apply_update(db, "maslak", base_dir=d)
yd = os.path.join(d, "durum", "yama_yedek", "13.20")
c("üzerine yazılan dosyanın eski hâli yedekte", oku(yd, "main_portal.py") == "ESKİ KOD" and oku(d, "main_portal.py") == "YENİ KOD")
c("alt klasördeki dosya da yedeklenir", oku(os.path.join(yd, "static"), "index.html") == "ESKİ ARAYÜZ")
c("silinen dosyanın eski hâli yedekte", oku(yd, "silinecek.py") == "SİLİNEN" and not os.path.exists(os.path.join(d, "silinecek.py")))
c("yeni eklenen dosya için yedek yok (eskisi yoktu)", not os.path.exists(os.path.join(yd, "yeni_dosya.py")))
for i in range(30, 43):                      # 13 yama daha: yalnız son 10 sürümün yedeği kalır
    open(os.path.join(d, "main_portal.py"), "w", encoding="utf-8").write("kod %d" % i)
    cloud_sync.check_and_apply_update(SahteDb([yama(i, "maslak", {"main_portal.py": "kod %d+" % i})]), "maslak", base_dir=d)
    time.sleep(0.02)
c("en çok 10 sürümün yedeği tutulur", len(os.listdir(os.path.join(d, "durum", "yama_yedek"))) == 10)

# 6) Uygulama kayıtları okunamazsa 'all' atlanır, lokasyona özel sürer
db = SahteDb([yama(8, "all", {"t.py": "T"}), yama(9, "maslak", {"u.py": "U"})], uygulama_hatasi=True)
d = klasor()
cloud_sync.check_and_apply_update(db, "maslak", base_dir=d)
c("kayıt tablosu yoksa 'all' yaması uygulanmaz (her turda yeniden yazmasın)", not os.path.exists(os.path.join(d, "t.py")))
c("kayıt tablosu yoksa da lokasyona özel yama uygulanır ve kapanır",
  oku(d, "u.py") == "U" and db.t["guncellemeler"][1]["durum"] == "tamamlandi")

# 7) A2: heartbeat ve lokasyon bilgisi uygulanan sürümü taşır
kayit = []


class HbSorgu:
    def upsert(self, payload, **kw):
        kayit.append(payload)
        return self

    def execute(self):
        return types.SimpleNamespace(data=[])


eski = cloud_sync.SON_YAMA_FILE
eski_ys = cloud_sync.YAMA_SURUMU_FILE
d = klasor()
cloud_sync.SON_YAMA_FILE = os.path.join(d, "son_yama.json")
cloud_sync.YAMA_SURUMU_FILE = os.path.join(d, "yama_surumu.json")
try:
    cloud_sync.send_heartbeat(types.SimpleNamespace(table=lambda ad: HbSorgu()), "maslak")
    c("son yama yoksa heartbeat sürüm alanı göndermez (mevcut değeri ezmez)", "versiyon" not in kayit[-1], kayit[-1])
    # İlk büyük yamayı eski program uygular: son_yama.json yazılmaz, yamanın sürüm dosyası gelir (yayın provası)
    json.dump({"versiyon": "14.0+abc1234"}, open(cloud_sync.YAMA_SURUMU_FILE, "w", encoding="utf-8"))
    cloud_sync.send_heartbeat(types.SimpleNamespace(table=lambda ad: HbSorgu()), "maslak")
    c("son_yama.json yoksa yamanın sürüm dosyasındaki sürüm gider", kayit[-1].get("versiyon") == "14.0+abc1234",
      kayit[-1])
    json.dump({"versiyon": "13.9"}, open(cloud_sync.SON_YAMA_FILE, "w", encoding="utf-8"))
    cloud_sync.send_heartbeat(types.SimpleNamespace(table=lambda ad: HbSorgu()), "maslak")
    c("heartbeat uygulanan son yama sürümünü gönderir (önce son_yama.json)", kayit[-1].get("versiyon") == "13.9",
      kayit[-1])
finally:
    cloud_sync.SON_YAMA_FILE = eski
    cloud_sync.YAMA_SURUMU_FILE = eski_ys

# 8) Veritabanı değişikliği dosyası
_sql = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "veritabani", "degisiklikler",
                         "004_yama_uygulamalari.sql"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "veritabani")) else None
if _sql is not None:
    c("004: tablo, anahtar (yama_id, lokasyon_id) ve 'all' kapatma tetiği var",
      "PRIMARY KEY (yama_id, lokasyon_id)" in _sql and "yama_all_kapat_trg" in _sql and "SECURITY DEFINER" in _sql)
    c("004: saha yalnızca ekler (güncelleme/silme yok)", "REVOKE UPDATE, DELETE, TRUNCATE ON public.yama_uygulamalari" in _sql)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
