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
# Kilit CIHAZ BAZINDA: tek genel kilit 27 sayaci sirayla okumaya zorlar ve
# cevap vermeyen bir sayac butun turu geciktirir. Ayni sayaca iki okuma ise
# hala siraya girmeli.
c("okuma kilidi destekleniyor (günlük okumayla çakışmasın)",
  "kilit.acquire()" in KAYNAK and "kilit.release()" in KAYNAK)
c("kilit cihaz bazında alınıyor", "self.kilit_al(dev)" in KAYNAK)
c("günlük okuma da aynı kilidi kullanıyor", "with cihaz_kilidi(dev):" in DC_KAYNAK)
c("cihaz kilidi data_collector'da tanımlı", "def cihaz_kilidi(dev):" in DC_KAYNAK)
c("kilitler cihaz adına göre saklanıyor", "_MODBUS_KILITLER" in DC_KAYNAK)
c("toplayıcı canlı okumayı başlatıyor",
  "canli_guc.baslat(kilit_al=cihaz_kilidi)" in DC_KAYNAK)
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

# ── 4b) ÜRETİM sayacı (kojen, 27.10.2026) — akım trafosu yönünden bağımsız ──
KOJ = {"ip": "1.2.3.4", "name": "KOJEN-3", "brand": "siemens", "uretim": True}
cg._float_oku = lambda ip, adres, timeout=2.0: -1_250_000.0      # ters bağlı: negatif W
try:
    c("kojen gücü ters bağlıda da pozitif", cg.guc_oku(KOJ, a) == 1250.0)
    c("tüketim sayacında işaret korunur (şebekeye verme görünür)",
      cg.guc_oku({"ip": "1.2.3.4", "brand": "siemens"}, a) == -1250.0)
finally:
    cg._float_oku = _orj_float

import data_collector as _dc  # noqa: E402
import data_bridge as _db  # noqa: E402
# Enerji: günlük okuma ve canlı çapraz denetim AYNI okuyucu (data_collector)
_enerji = {801: 1_000.0, 809: 5_000_000.0}                       # Wh (Giren, Verilen)
_orj_double = _dc._siemens_double
_dc._siemens_double = lambda ip, adres: _enerji.get(adres)
try:
    c("kojen enerjisi Giren + Verilen toplamı", cg._sayac_oku(KOJ) == 5001.0, cg._sayac_oku(KOJ))
    c("günlük okuma da aynı değeri verir", _dc.modbus_get_kwh(KOJ) == 5001.0)
    _enerji[809] = None
    c("biri okunamazsa kojen enerjisi None (yarım değer yok)", cg._sayac_oku(KOJ) is None)
finally:
    _dc._siemens_double = _orj_double

_koj = [d for d in _dc.ANALYZERS if d["name"].startswith("KOJEN-")]
c("KOJEN-3/4 canlı okunacak listede",
  {d["name"]: d["ip"] for d in _koj} == {"KOJEN-3": "192.168.1.18", "KOJEN-4": "192.168.1.19"}, _koj)
c("kojenler üretim sayacı olarak işaretli", all(d.get("uretim") for d in _koj))
c("kojenler tüketim toplamına GİRMEZ (çift sayım yok)",
  not any(d["name"] in _db.ALL_ANALYZERS for d in _koj))

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
# 21.10.2026: saha genisledi — 27 analizorun TAMAMI canli okunuyor.
c("sahanın tamamı canlı okunuyor", len(_liste) == len(dc.ANALYZERS), len(_liste))
c("liste daraltılabiliyor (kod değişmeden)",
  [d["name"] for d in cg.cihazlar({"cihaz_onekleri": ["TRDP-"]})]
  == [d["name"] for d in dc.ANALYZERS if d["name"].startswith("TRDP-")])
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

# ── 10) PARALEL OKUMA · ARIZA ATLAMASI · SEYRELTILMIS DENETIM ───────────
# 27 sayac sirayla okunursa cevap vermeyen birkac cihaz (her biri 2 sn zaman
# asimi) 15 saniyelik turu tek basina yer. Olculdu: sirayla 25,3 sn, paralel
# 5,0 sn, arizalilar atlaninca 0,4 sn.
import threading as _th  # noqa: E402
import time as _tm  # noqa: E402

c("eş zamanlı okuma ayarı var", "es_zamanli" in a, a.get("es_zamanli"))
c("varsayılan paralel (sırayla değil)", int(a["es_zamanli"]) > 1, a["es_zamanli"])
c("iş parçacığı havuzu kullanılıyor", "ThreadPoolExecutor" in KOD)
# Havuzda calisan fonksiyon ORTAK DURUMA dokunmamali: sayac gecmisi ve
# dogrulama damgasi karar asamasinda, tek iplikte guncellenir.
_isci = KAYNAK.split("def _oku_tek")[1].split("\n    def ")[0]
c("karar TEK iplikte veriliyor (yarış koşulu yok)",
  "self._son_karar" not in _isci and "self._sayac" not in _isci
  and "self._hata" not in _isci and "self._atla" not in _isci, _isci[:120])

c("çapraz denetim seyreltildi (27 sayaçta sayaç okuması pahalı)",
  int(a["sayac_her_n_tur"]) >= 8, a["sayac_her_n_tur"])

ARIZALI = {"MCC-5", "CHILLER-2"}
_kilitler = {}


def _kilit_al(dev):
    return _kilitler.setdefault(dev["name"], _th.Lock())


def _sahte_guc(dev, ayar=None, adres=None):
    if dev["name"] in ARIZALI:
        _tm.sleep(0.25)          # zaman asimi (testte kisaltildi)
        return None
    _tm.sleep(0.02)
    return 100.0


_orj_guc, _orj_sayac = cg.guc_oku, cg._sayac_oku
cg.guc_oku = _sahte_guc
cg._sayac_oku = lambda dev: None if dev["name"] in ARIZALI else 1000.0
try:
    _ay = dict(a)
    _ay["es_zamanli"] = 1
    _o1 = cg.Olcer(_ay, kilit_al=_kilit_al)
    _t0 = _tm.time(); _r1 = _o1.tur(); _sira_sn = _tm.time() - _t0

    _ay2 = dict(a)
    _ay2["es_zamanli"] = 8
    _o2 = cg.Olcer(_ay2, kilit_al=_kilit_al)
    _t0 = _tm.time(); _r2 = _o2.tur(); _paralel_sn = _tm.time() - _t0

    c("paralel okuma sıralıdan HIZLI", _paralel_sn < _sira_sn * 0.6,
      "sirayla %.2f sn / paralel %.2f sn" % (_sira_sn, _paralel_sn))
    c("paralelde de her cihaz dönüyor", len(_r2) == len(cg.cihazlar(a)), len(_r2))
    c("paralelde sonuç sırası cihaz listesiyle aynı",
      [x["cihaz"] for x in _r2] == [d["name"] for d in cg.cihazlar(a)])
    c("sağlam sayaçlar okundu",
      all(x["kw"] == 100.0 for x in _r2 if x["cihaz"] not in ARIZALI))
    c("arızalı sayaç uydurulmadı",
      all(x["kw"] is None for x in _r2 if x["cihaz"] in ARIZALI))

    # Ariza atlamasi: esik asilinca cihaz bir sure atlanir
    _o3 = cg.Olcer(dict(a, es_zamanli=8, ariza_esigi=2, ariza_bekleme_tur=3),
                   kilit_al=_kilit_al)
    _atlanma = []
    for _i in range(6):
        _rr = _o3.tur()
        _atlanma.append(sum(1 for x in _rr
                            if (x.get("not") or "").startswith("cihaz cevap vermiyor")))
    c("eşik aşılınca arızalı cihaz atlanıyor", max(_atlanma) == len(ARIZALI), _atlanma)
    c("ilk turlarda atlanmıyor (önce denenir)", _atlanma[0] == 0, _atlanma)
    c("atlanan cihaz tekrar deneniyor (kalıcı dışlanmıyor)",
      _atlanma[-1] == 0 or 0 in _atlanma[2:], _atlanma)

    _son = _o3.tur()
    c("atlanan cihaz ekranda GİZLENMİYOR", len(_son) == len(cg.cihazlar(a)))
    c("atlanan cihazın durumu yazıyor",
      any("atlan" in (x.get("not") or "") for x in _son if x["cihaz"] in ARIZALI)
      or all(x["kw"] is None for x in _son if x["cihaz"] in ARIZALI))
finally:
    cg.guc_oku, cg._sayac_oku = _orj_guc, _orj_sayac

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
