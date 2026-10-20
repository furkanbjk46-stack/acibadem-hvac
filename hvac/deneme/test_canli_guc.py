# -*- coding: utf-8 -*-
"""Canlı güç okuması — sayı doğru mu, saha güvende mi? (canli_guc.py)

Bu modül sahadaki sayaçlara 15 saniyede bir gider ve merkezde "şu an ne
çekiyoruz" diye gösterilen sayıyı üretir. İki şeyi şarta bağlıyoruz:

  1) GÜVENLİK — yalnızca OKUR, hiçbir cihaza yazmaz; günlük tüketim
     hesabının dosyalarına dokunmaz; günlük okumayla aynı kilidi paylaşır.
  2) DOĞRULUK — güç register'ının adresi cihaz modeline göre değişir ve
     yanlış adres "makul ama yanlış" bir sayı döndürebilir (tek faz
     okunursa gerçeğin üçte biri, gerilim register'ına denk gelinirse
     sabit ~230). Bu yüzden register değeri kWh sayacının farkıyla
     karşılaştırılır; çelişirse register'a GÜVENİLMEZ. Test, bu denetimin
     sessizce kaldırılmasını engeller.
"""
import json
import os
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import canli_guc as cg  # noqa: E402

KAYNAK = open(os.path.join(BURASI, "canli_guc.py"), encoding="utf-8").read()
DC_KAYNAK = open(os.path.join(BURASI, "data_collector.py"), encoding="utf-8").read()
CS_KAYNAK = open(os.path.join(BURASI, "cloud_sync.py"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def kod_metni(kaynak: str) -> str:
    """Yorumları ve metin sabitlerini ATAR — "dokunulmuyor" gibi kontroller
    açıklama satırındaki kelimeye takılmasın, gerçek KOD'a baksın."""
    import io
    import tokenize
    parcalar = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(kaynak).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            parcalar.append(tok.string)
    except Exception:
        return kaynak
    return " ".join(parcalar)


KOD = kod_metni(KAYNAK)
CS_KOD = kod_metni(CS_KAYNAK)


# ── 1) Güvenlik ──────────────────────────────────────────────────────────
c("modül yazma fonksiyonu içermiyor",
  "write_register" not in KAYNAK and "write_single" not in KAYNAK
  and "\\x10" not in KAYNAK and "\\x06" not in KAYNAK)
# Modbus fonksiyon kodu 3 = oku. 6/16 yazma kodlarıdır, paket üreticide olmamalı.
c("yalnızca 'read holding registers' (fonksiyon 3) kullanılıyor",
  KAYNAK.count("1, 0, 6, birim, 3,") == 1)
c("günlük tüketim referansına dokunulmuyor",
  "modbus_daily_ref" not in KOD and "analizor_guncel_veriler" not in KOD)
c("günlük okuma CSV'si yazılmıyor", "MODBUS_CSV" not in KOD)
c("okuma kilidi destekleniyor (günlük okumayla çakışmasın)",
  "self.kilit.acquire()" in KAYNAK and "self.kilit.release()" in KAYNAK)
c("günlük okuma da aynı kilidi kullanıyor", "with MODBUS_KILIT:" in DC_KAYNAK)
c("kilit data_collector'da tanımlı", "MODBUS_KILIT   = threading.Lock()" in DC_KAYNAK)
c("toplayıcı canlı okumayı başlatıyor", "canli_guc.baslat(kilit=MODBUS_KILIT)" in DC_KAYNAK)
c("canlı okuma başlamazsa toplayıcı çalışmaya devam ediyor",
  "Canli guc okumasi baslatilamadi" in DC_KAYNAK)

# ── 2) Modbus paketi ─────────────────────────────────────────────────────
p = cg._istek_paketi(19026, 2)
c("paket 12 bayt", len(p) == 12, len(p))
c("fonksiyon kodu 3 (oku)", p[7] == 3, p[7])
c("adres pakette doğru", int.from_bytes(p[8:10], "big") == 19026)
c("register sayısı 2 (float32)", int.from_bytes(p[10:12], "big") == 2)
c("birim kimliği 1", p[6] == 1)

# ── 3) Ayarlar ───────────────────────────────────────────────────────────
a = cg.ayar_oku()
for alan in ("periyot_sn", "sayac_her_n_tur", "tolerans_oran", "tolerans_kw",
             "makul_alt_kw", "makul_ust_kw", "guc_register"):
    c("ayar alanı: %s" % alan, alan in a)
c("iki marka için de register tanımlı",
  set(a["guc_register"]) >= {"janitza", "siemens"}, a["guc_register"])

_gecici = os.path.join(tempfile.gettempdir(), "canli_guc_ayar_test.json")
with open(_gecici, "w", encoding="utf-8") as f:
    json.dump({"periyot_sn": 30, "guc_register": {"janitza": 12345}}, f)
_orj = cg.AYAR_DOSYA
cg.AYAR_DOSYA = _gecici
try:
    b = cg.ayar_oku()
finally:
    cg.AYAR_DOSYA = _orj
    os.remove(_gecici)
c("ayar dosyası değeri eziyor", b["periyot_sn"] == 30, b["periyot_sn"])
c("eksik alanlar varsayılandan tamamlanıyor", b["tolerans_kw"] == a["tolerans_kw"])
c("register kısmi olarak değiştirilebiliyor",
  b["guc_register"]["janitza"] == 12345 and b["guc_register"]["siemens"] ==
  cg.VARSAYILAN_AYAR["guc_register"]["siemens"], b["guc_register"])
# Adres kod yerine AYARDAN gelmeli: saha farklı cihaz koyarsa yama gerekmesin
c("register adresi ayardan okunuyor", '(ayar.get("guc_register") or {}).get' in KAYNAK)

# ── 4) W → kW ve adres seçimi ────────────────────────────────────────────
_cagrilar = []


def _sahte_float(ip, adres, timeout=2.0):
    _cagrilar.append((ip, adres))
    return 412_300.0          # W


_orj_float = cg._float_oku
cg._float_oku = _sahte_float
try:
    kw = cg.guc_oku({"ip": "1.2.3.4", "brand": "janitza"}, a)
    kw_ozel = cg.guc_oku({"ip": "1.2.3.4", "brand": "siemens"}, a, adres=99)
finally:
    cg._float_oku = _orj_float

c("W → kW çevriliyor", kw == 412.3, kw)
c("markanın register adresi kullanılıyor",
  _cagrilar[0][1] == a["guc_register"]["janitza"], _cagrilar)
c("verilen adres ayarın önüne geçiyor (saha denemesi)", _cagrilar[1][1] == 99, _cagrilar)

cg._float_oku = lambda ip, adres, timeout=2.0: None
try:
    c("okunamazsa None", cg.guc_oku({"ip": "1.2.3.4", "brand": "janitza"}, a) is None)
    c("tanımsız marka None", cg.guc_oku({"ip": "1.2.3.4", "brand": "yok"}, a) is None)
finally:
    cg._float_oku = _orj_float

# ── 5) Sayaç farkından güç ───────────────────────────────────────────────
o = cg.Olcer(a)
c("ilk okumada sayaç gücü yok", o._sayac_gucu("TRDP-1", 1000.0, 1000.0) is None)
# 15 sn'de 1.5 kWh → 360 kW
c("sayaç farkı doğru kW veriyor",
  o._sayac_gucu("TRDP-1", 1001.5, 1015.0) == 360.0,
  o._sayac_gucu("TRDP-1", 1003.0, 1030.0))
o2 = cg.Olcer(a)
o2._sayac_gucu("TRDP-2", 500.0, 1000.0)
c("sayaç geriye saydıysa değer üretilmez (sıfırlanma)",
  o2._sayac_gucu("TRDP-2", 10.0, 1015.0) is None)
o3 = cg.Olcer(a)
o3._sayac_gucu("TRDP-3", 500.0, 1000.0)
c("çok kısa aralıkta değer üretilmez", o3._sayac_gucu("TRDP-3", 500.1, 1002.0) is None)

# ── 6) ÇAPRAZ DENETİM — asıl koruma ──────────────────────────────────────
o = cg.Olcer(a)
k = o._karar("TRDP-1", 400.0, 408.0, 123.0)
c("register sayaçla uyuşuyorsa register gösterilir",
  k["kw"] == 400.0 and k["yontem"] == "register", k)

k = o._karar("TRDP-2", 140.0, 420.0, 123.0)      # tek faz okunmuş gibi
c("register sayaçla çelişirse SAYAÇ gösterilir",
  k["kw"] == 420.0 and k["yontem"] == "sayac", k)
c("çelişki gerekçesi yazılıyor", k["not"] and "uyuşmadı" in k["not"], k["not"])

k = o._karar("TRDP-3", 230.0, None, None)
c("doğrulanmamış register soru işaretli", k["yontem"] == "register?", k)

o._son_karar["TRDP-4"] = {"yontem": "register"}
k = o._karar("TRDP-4", 300.0, None, None)
c("bir kez doğrulanmış cihaz damgasını korur", k["yontem"] == "register", k)

k = o._karar("TRDP-1", None, 380.0, 55.0)
c("register yoksa sayaç kullanılır", k["kw"] == 380.0 and k["yontem"] == "sayac", k)
c("register yokluğu not ediliyor", "register" in (k["not"] or ""), k["not"])

k = o._karar("TRDP-1", None, None, None)
c("hiçbiri yoksa değer uydurulmaz", k["kw"] is None and k["yontem"] is None, k)

# Küçük yüklerde oransal tolerans anlamsız — mutlak pay devreye girmeli
k = o._karar("TRDP-1", 12.0, 5.0, 1.0)
c("küçük yükte mutlak tolerans uygulanıyor", k["yontem"] == "register", k)

# Makul aralık
k = o._karar("TRDP-1", 999999.0, None, None)
c("saçma büyük değer reddedilir", k["kw"] is None, k)
k = o._karar("TRDP-1", -9000.0, None, None)
c("saçma negatif değer reddedilir", k["kw"] is None, k)
k = o._karar("TRDP-1", -20.0, -19.0, 5.0)
c("şebekeye verme (küçük negatif) kabul edilir", k["kw"] == -20.0, k)

# ── 7) Cihaz listesi tek kaynaktan ───────────────────────────────────────
import data_collector as dc  # noqa: E402

_liste = cg.cihazlar()
c("cihazlar ANALYZERS'tan geliyor",
  all(any(x["name"] == d["name"] for x in dc.ANALYZERS) for d in _liste), len(_liste))
c("yalnızca trafolar canlı okunuyor",
  _liste and all(d["name"].startswith("TRDP-") for d in _liste),
  [d["name"] for d in _liste])
c("canli_guc'ta ayrı cihaz listesi tutulmuyor",
  "172.17.91" not in KAYNAK)

# ── 8) Dosya alışverişi ──────────────────────────────────────────────────
_dosya = os.path.join(tempfile.gettempdir(), "canli_guc_son_test.json")
cg.dosyaya_yaz([{"cihaz": "TRDP-1", "kw": 400.0, "yontem": "register"}], _dosya)
c("sonuç dosyası yazıldı", os.path.exists(_dosya))
_v = cg.son_olcum(_dosya)
c("taze ölçüm okunuyor", _v and _v["olcumler"][0]["kw"] == 400.0, _v)
c("yaş bilgisi dönüyor", _v and _v.get("yas_sn") is not None)
c("bayat ölçüm None döner (merkeze eski değer gitmesin)",
  cg.son_olcum(_dosya, azami_yas_sn=-1) is None)
os.remove(_dosya)
c("eksik dosyada çökmüyor", cg.son_olcum(_dosya) is None)
c("dosya atomik yazılıyor (yarım dosya okunmasın)", "os.replace(gecici, dosya)" in KAYNAK)

# ── 9) Buluta taşıma cloud_sync'te, ayrı ve hızlı döngüde ────────────────
c("cloud_sync canlı güç döngüsü var", "def _canli_guc_loop()" in CS_KAYNAK)
c("döngü ayrı thread'te", 'name="canli-guc-sync"' in CS_KAYNAK)
c("canli_guc tablosuna yazıyor", 'client.table("canli_guc").upsert' in CS_KAYNAK)
c("lokasyon+cihaz anahtarıyla upsert", 'on_conflict="lokasyon_id,cihaz"' in CS_KAYNAK)
c("egress için minimal dönüş", 'returning="minimal"' in CS_KAYNAK)
c("aynı ölçüm iki kez yazılmıyor", "_son_yazilan" in CS_KAYNAK)
c("modül yoksa senkron bozulmuyor", "Canlı güç taşıma kapalı" in CS_KAYNAK)
c("taşıma Modbus'a gitmiyor (yalnız dosya okur)",
  "son_olcum ( )" in CS_KOD.replace("son_olcum()", "son_olcum ( )")
  and "modbus" not in CS_KOD.split("_canli_guc_loop")[1][:1500].lower())

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
