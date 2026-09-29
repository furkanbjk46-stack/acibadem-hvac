# -*- coding: utf-8 -*-
"""İzleme/alarm mantığı ve Yönetim ekranı bağlantıları — ağ bağlantısı YOK.

Eşikler configs/izleme_limitleri.json'dan okunur; burada sabit sayı
beklenmez, limit dosyası referans alınır (limit değişince test yanıltmasın).
"""
import ast
import json
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BURASI = os.path.join(KOK, "merkez")
sys.path.insert(0, BURASI)

import izleme as IZ

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


LIM = IZ.limitler()
GB = 1024 ** 3
MB = 1024 ** 2

# ── Limit dosyası ─────────────────────────────────────────────────────────
c("limitler okunuyor", isinstance(LIM, dict) and LIM)
c("acıklama anahtarları elenmiş", not any(k.startswith("_") for k in LIM))
for _z in ("plan_disk_gb", "disk_dikkat_yuzde", "disk_kritik_yuzde",
           "tablo_dikkat_mb", "tablo_kritik_mb", "onbellek_isabet_dikkat"):
    c("[%s] tanımlı" % _z, _z in LIM)
c("kritik eşik dikkat eşiğinin üstünde",
  LIM["disk_kritik_yuzde"] > LIM["disk_dikkat_yuzde"])
c("tablo kritik eşiği dikkatten büyük", LIM["tablo_kritik_mb"] > LIM["tablo_dikkat_mb"])


def kullanim(db_bayt=1 * GB, tablolar=None, saglik=None):
    return {"olculme": "2026-09-29T21:00:00+03:00",
            "veritabani_bayt": db_bayt,
            "tablolar": tablolar if tablolar is not None else [],
            "saglik": dict({"onbellek_isabet_yuzde": 99.5, "aktif_baglanti": 5,
                            "azami_baglanti": 100, "islem_commit": 1000,
                            "islem_rollback": 2, "kilitlenme": 0}, **(saglik or {}))}


def tablo(ad, toplam_mb, veri_mb=None, indeks_mb=0):
    veri_mb = toplam_mb if veri_mb is None else veri_mb
    return {"tablo": ad, "toplam_bayt": int(toplam_mb * MB),
            "veri_bayt": int(veri_mb * MB), "indeks_bayt": int(indeks_mb * MB),
            "satir_tahmin": 1000}


def seviyeler(k):
    return [s for s, _b, _a in IZ.alarmlar(k, LIM)]


# ── Disk kotası ───────────────────────────────────────────────────────────
_kota = LIM["plan_disk_gb"] * GB
c("düşük kullanımda alarm yok, 'iyi' döner",
  seviyeler(kullanim(db_bayt=int(_kota * 0.10))) == ["iyi"])
c("dikkat eşiğinde uyarı çıkar",
  "dikkat" in seviyeler(kullanim(db_bayt=int(_kota * (LIM["disk_dikkat_yuzde"] + 2) / 100))))
c("kritik eşikte kritik çıkar",
  "kritik" in seviyeler(kullanim(db_bayt=int(_kota * (LIM["disk_kritik_yuzde"] + 2) / 100))))
c("kritik eşikte 'dikkat' ile ÇİFT uyarı verilmez",
  seviyeler(kullanim(db_bayt=int(_kota * 0.99))).count("kritik") == 1,
  seviyeler(kullanim(db_bayt=int(_kota * 0.99))))
_t, _k, _o = IZ.disk_orani(kullanim(db_bayt=int(_kota / 2)), LIM)
c("disk oranı yüzde olarak hesaplanır", abs(_o - 50.0) < 0.01, _o)

# ── Tablo boyutu ──────────────────────────────────────────────────────────
c("küçük tablo uyarı üretmez",
  seviyeler(kullanim(tablolar=[tablo("ayarlar", 1)])) == ["iyi"])
c("dikkat eşiğini aşan tablo işaretlenir",
  "dikkat" in seviyeler(kullanim(tablolar=[tablo("x", LIM["tablo_dikkat_mb"] + 5)])))
c("kritik eşiği aşan tablo kritik olur",
  "kritik" in seviyeler(kullanim(tablolar=[tablo("x", LIM["tablo_kritik_mb"] + 5)])))
_bg = LIM.get("buyume_uyari_tablolari", [])
c("biriken tablo listesi tanımlı", bool(_bg), _bg)
_metin = " ".join(a for _s, _b, a in
                  IZ.alarmlar(kullanim(tablolar=[tablo(_bg[0], LIM["tablo_dikkat_mb"] + 5)]), LIM))
c("biriken tabloya 'temizlenebilir' notu düşer", "silinebilir" in _metin, _metin)
_metin2 = " ".join(a for _s, _b, a in
                   IZ.alarmlar(kullanim(tablolar=[tablo("energy_data", LIM["tablo_dikkat_mb"] + 5)]), LIM))
c("normal tabloya temizlik notu düşmez", "silinebilir" not in _metin2)

# ── İndeks / veri oranı ───────────────────────────────────────────────────
c("indeks veriden çok büyükse uyarılır",
  any("indeks" in b.lower() for _s, b, _a in
      IZ.alarmlar(kullanim(tablolar=[tablo("x", 30, veri_mb=10,
                                           indeks_mb=10 * LIM["indeks_oran_dikkat"] + 5)]), LIM)))
c("küçük tabloda indeks oranı sorgulanmaz (gürültü olmasın)",
  seviyeler(kullanim(tablolar=[tablo("x", 3, veri_mb=1, indeks_mb=2)])) == ["iyi"])

# ── Sağlık göstergeleri ───────────────────────────────────────────────────
c("önbellek isabeti eşiğin altındaysa uyarılır",
  "dikkat" in seviyeler(kullanim(saglik={"onbellek_isabet_yuzde":
                                         LIM["onbellek_isabet_dikkat"] - 5})))
c("bağlantı doygunluğu uyarılır",
  "dikkat" in seviyeler(kullanim(saglik={"aktif_baglanti": 95, "azami_baglanti": 100})))
c("deadlock uyarılır", "dikkat" in seviyeler(kullanim(saglik={"kilitlenme": 3})))
c("deadlock yoksa uyarı yok", seviyeler(kullanim(saglik={"kilitlenme": 0})) == ["iyi"])

# ── Bozuk/eksik veri çökertmemeli ────────────────────────────────────────
for _bozuk in (None, [], {}, "metin", 5, [{"tablo": "x"}]):
    c("bozuk ölçümde çökmez (%r)" % (_bozuk,), IZ.alarmlar(_bozuk, LIM) == [])
c("bozuk ölçümde disk oranı 0", IZ.disk_orani([], LIM)[2] == 0)
c("eksik alanlı ölçüm çökertmez",
  isinstance(IZ.alarmlar({"veritabani_bayt": None, "tablolar": [{"tablo": "y"}]}, LIM), list))

# ── Biçimleme ─────────────────────────────────────────────────────────────
c("boyut KB", IZ.boyut(2048) == "2 KB", IZ.boyut(2048))
c("boyut MB ondalıklı", IZ.boyut(int(1.5 * MB)) == "1.5 MB", IZ.boyut(int(1.5 * MB)))
c("boyut None ise tire", IZ.boyut(None) == "—")
c("sayı binlik ayracı", IZ.sayi(1234567) == "1.234.567", IZ.sayi(1234567))
c("sayi bozuk girdide tire", IZ.sayi("abc") == "—")
c("en kötü seviye kritik", IZ.en_kotu([("iyi", "", ""), ("kritik", "", "")]) == "kritik")
c("en kötü seviye dikkat", IZ.en_kotu([("iyi", "", ""), ("dikkat", "", "")]) == "dikkat")
c("alarm yoksa iyi", IZ.en_kotu([]) == "iyi")

# ── Yönetim ekranı bağlantıları ───────────────────────────────────────────
_yon = open(os.path.join(BURASI, "pages", "yonetim.py"), encoding="utf-8").read()
_mrk = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
_sema = open(os.path.join(BURASI, "sema_diyagram_uret.py"), encoding="utf-8").read()

c("yönetim sayfası sözdizimi geçerli", ast.parse(_yon) is not None)
c("app_merkez yönetim sayfasını çalıştırır", 'pages", "yonetim.py"' in _mrk)
c("yönetim düğmesi var", 'key="yonetim_btn"' in _mrk)
c("adres çubuğundan da açılır (?yonetim)", '"yonetim" in st.query_params' in _mrk)
c("geri düğmesi oturumu temizler", 'st.session_state.pop("yonetim", None)' in _yon)
c("yönetim ekranı ortak izleme modülünü kullanır", "import izleme as _IZ" in _yon)
c("statik sayfa da AYNI modülü kullanır", "import izleme" in _sema)
c("alarm mantığı sayfada TEKRARLANMIYOR",
  "disk_kritik_yuzde" not in _yon and "tablo_kritik_mb" not in _yon)
c("ölçüm okunamazsa sayfa çökmez, uyarı verir", "isinstance(_k, dict)" in _yon)
c("service_role anahtarı ortamdan/secrets'tan alınır",
  "SUPABASE_SERVICE_KEY" in _yon and "service_key" in _yon)
c("secrets dosyası yoksa st.secrets'e dokunulmaz", "secrets.toml" in _yon)
c("canlı okuma için önbellek kısa (60 sn)", "ttl=60" in _yon)
c("yenile düğmesi önbelleği temizler", "st.cache_data.clear()" in _yon)

# ── Kurulum SQL'i ─────────────────────────────────────────────────────────
_sql = open(os.path.join(BURASI, "izleme_kurulum.sql"), encoding="utf-8").read()
c("fonksiyon salt okur (STABLE)", "STABLE" in _sql)
c("fonksiyon service_role'a açılır", "GRANT EXECUTE" in _sql and "service_role" in _sql)
c("anon/authenticated yetkisi geri alınır",
  "REVOKE ALL" in _sql and "anon" in _sql and "authenticated" in _sql)
c("yalnızca public şema ölçülür", "nspname = 'public'" in _sql)
c("veri satırı döndürmez (yalnızca boyut/sağlık)",
  "pg_total_relation_size" in _sql and "SELECT *" not in _sql.upper().replace("SELECT * FROM PG", ""))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
