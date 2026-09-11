# -*- coding: utf-8 -*-
"""OTO-SET (lokasyon tarafi) testleri — SAHTE Supabase + SAHTE BACnet.
   python hvac/deneme/test_oto_set.py

Bu modul hastane BMS'ine DOGRUDAN setpoint yaziyor; tetikleyici mantigi,
deger dogrulama kapisi ve merkez ile kural esitligi test edilir.
AG BAGLANTISI YOK, GERCEK CIHAZA YAZILMAZ.
"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging
logging.disable(logging.CRITICAL)

import oto_set

# Durum dosyasi gecici klasore alinir — gercek yapilandirma bozulmasin
_tmp = tempfile.mkdtemp(prefix="otoset_")
oto_set.DURUM_FILE = os.path.join(_tmp, "durum.json")

T = []
def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


NOKTA_ALANLARI = {"gateway_ip": "10.0.0.1", "dnet": 1, "mac_hex": "0A",
                  "obj_type": 2, "obj_inst": 1}


class Sahte:
    """Supabase okumalarini ve BACnet yazmalarini taklit eder."""

    def __init__(self, ayarlar=None, noktalar=None, yazma_basarili=True,
                 saha=None, harita=None, ic=None):
        self.ayarlar = dict(ayarlar or {})
        self.noktalar = noktalar if noktalar is not None else (
            oto_set.CH_NOKTALAR + list(oto_set.DIG_SET["sogutma"].keys()))
        self.yazilan = []        # (nokta, deger)
        self.loglar = []
        self.yazma_basarili = yazma_basarili
        # Geri okuma davranışı:
        #   saha  : {nokta: deger | "OKUNAMADI"} — yoksa yazılan değer okunur
        #   harita: {nokta: okuma_noktasi_dict}  — chiller IC SET karşılıkları
        #   ic    : {obj_inst: deger}            — IC SET okuma değerleri
        self.saha = dict(saha or {})
        self.harita = dict(harita or {})
        self.ic = dict(ic or {})

    def istek(self, url, key, yol, veri=None, method="GET", timeout=10):
        if method == "GET":
            if "/ayarlar?key=like.oto_*" in yol:
                # RLS izni yoksa PostgREST bos liste doner -> kontrol atlanir.
                return [{"key": k} for k in self.ayarlar if k.startswith("oto_")]
            if "/ayarlar?key=eq." in yol:
                k = yol.split("key=eq.")[1].split("&")[0]
                return [{"value": self.ayarlar[k]}] if k in self.ayarlar else []
            if "/lokasyon_noktalar" in yol:
                return [dict(NOKTA_ALANLARI, nokta_adi=n) for n in self.noktalar]
            return []
        if "/oto_mod_log" in yol:
            self.loglar.extend(veri if isinstance(veri, list) else [veri])
        return []


def calistir(sb, tahmin=(30.0, 24.0), saat=12, lokasyon="maslak", dakika=0):
    """kontrol()'u sahte bagimliliklarla calistirir."""
    _y = {"istek": oto_set._istek, "tahmin": oto_set.tahmin_al, "dt": oto_set.datetime}
    oto_set._istek = sb.istek
    oto_set.tahmin_al = lambda zorla=False: ({"bugun_max": tahmin[0], "yarin_min": tahmin[1]}
                                             if tahmin else None)

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 8, 31, saat, dakika, 0)
    oto_set.datetime = _DT

    # Sahte BACnet — gercek cihaza yazilmaz
    sahte_bw = type(sys)("bacnet_writer")
    def _yaz(ip, dnet, mac, tip, inst, deger):
        sb.yazilan.append((deger, tip, inst))
        return (sb.yazma_basarili, "SimpleACK" if sb.yazma_basarili else "hata")

    def _yaz_dogrula_toplu(isler, geri_okuma=None):
        # Gerçek fonksiyonla aynı sözleşme: yaz → geri oku → durum
        sonuc = {}
        for ad, n, deger in isler:
            ok, mesaj = _yaz(n["gateway_ip"], n["dnet"], n["mac_hex"],
                             n["obj_type"], n["obj_inst"], deger)
            s = {"deger": deger, "yazma_ok": ok, "mesaj": mesaj,
                 "okunan": None, "ic_okunan": None}
            if not ok:
                s["durum"] = "yazma_hatasi"
            else:
                okunan = sb.saha.get(ad, deger)
                if okunan == "OKUNAMADI":
                    s["durum"] = "dogrulanamadi"
                elif abs(float(okunan) - float(deger)) <= 0.05:
                    s["durum"], s["okunan"] = "oturdu", okunan
                else:
                    s["durum"], s["okunan"] = "sahada_farkli", okunan
            sonuc[ad] = s
        return sonuc

    def _bacnet_oku(ip, dnet, mac, tip, inst, prop_id=85):
        if inst in sb.ic:
            return True, sb.ic[inst]
        return False, "Cevap yok"

    import bacnet_writer as _gercek_bw
    sahte_bw.bacnet_yaz = _yaz
    sahte_bw.yaz_dogrula_toplu = _yaz_dogrula_toplu
    sahte_bw.bacnet_oku = _bacnet_oku
    sahte_bw.geri_okuma_haritasi = lambda lok: sb.harita
    sahte_bw.komut_degeri_gecerli = _gercek_bw.komut_degeri_gecerli   # GERCEK kapi
    _eski_modul = sys.modules.get("bacnet_writer")
    sys.modules["bacnet_writer"] = sahte_bw
    try:
        oto_set.kontrol("https://sahte", "anahtar", lokasyon)
    finally:
        oto_set._istek, oto_set.tahmin_al, oto_set.datetime = _y["istek"], _y["tahmin"], _y["dt"]
        if _eski_modul is not None:
            sys.modules["bacnet_writer"] = _eski_modul


def durum_sifirla():
    if os.path.exists(oto_set.DURUM_FILE):
        os.remove(oto_set.DURUM_FILE)


TEMEL = {"oto_set_aktif": "true", "oto_gunduz_saat": "8", "oto_gece_saat": "23"}

# ── 1) Donem hesabi ──
dh = oto_set.donem_hesapla
c("05-22: 05'te gunduz baslar", dh(5, 5, 22) == "gunduz")
c("05-22: 04 gece", dh(4, 5, 22) == "gece")
c("05-22: 22 gece", dh(22, 5, 22) == "gece")
c("gece yarisini asan aralik (22->5)", dh(23, 22, 5) == "gunduz" and dh(10, 22, 5) == "gece")

# ── 2) Chiller modu ──
ch = oto_set.ch_modu_hesapla
c("sicak -> 15C -> serin (kademesiz)", ch(15.0, "sicak") == "serin")
c("serin, 24C bolgede kalir (histerezis)", ch(24.0, "serin") == "serin")
c("serin, 25.5C -> ilimli", ch(25.5, "serin") == "ilimli")

# ── 3) Ilk calisma: gecis algilanir ve setler YAZILIR ──
durum_sifirla()
sb = Sahte(TEMEL)
calistir(sb, tahmin=(30.0, 24.0), saat=12)     # gunduz, ref = bugun_max 30 -> sicak
c("ilk calismada 11 nokta yazilir", len(sb.yazilan) == 11, "%d" % len(sb.yazilan))
c("gunduz referansi BUGUNUN max'i (30 -> 6.5)",
  sum(1 for d, _, _ in sb.yazilan if d == 6.5) == 5,
  str(sorted({d for d, _, _ in sb.yazilan})))
c("durum dosyasi yazildi", os.path.exists(oto_set.DURUM_FILE))
_d = oto_set.durum_oku()
c("durum: donem gunduz", _d.get("donem") == "gunduz", str(_d.get("donem")))
c("durum: chiller sicak", _d.get("chiller_mod") == "sicak", str(_d.get("chiller_mod")))
# Ilk calistirmada onceki mod BILINMIYOR; bunu "mod degisimi" diye kaydetmek
# uydurma olurdu. Dogru davranis: yenileme olarak isaretlemek.
c("ilk calismada log 'yenileme' tipinde (onceki mod yok)",
  all(l["tip"].endswith("_yenileme") for l in sb.loglar),
  str([l["tip"] for l in sb.loglar]))

# ── 4) Ayni donemde tekrar calisirsa YAZMAZ ──
sb2 = Sahte(TEMEL)
calistir(sb2, tahmin=(30.0, 24.0), saat=14)    # hala gunduz
c("ayni donemde tekrar yazma yok", len(sb2.yazilan) == 0, "%d" % len(sb2.yazilan))
c("ayni donemde log yok", len(sb2.loglar) == 0)

# ── 5) Gece gecisi: YARININ min'i referans ──
sb3 = Sahte(TEMEL)
calistir(sb3, tahmin=(30.0, 20.0), saat=23)    # gece, ref = yarin_min 20 -> serin
c("gece gecisinde yazilir", len(sb3.yazilan) == 11, "%d" % len(sb3.yazilan))
c("gece referansi YARININ min'i (20 -> 7.5)",
  sum(1 for d, _, _ in sb3.yazilan if d == 7.5) == 5,
  str(sorted({d for d, _, _ in sb3.yazilan})))

# ── 5b) GERCEK mod degisimi 'chiller' tipinde loglanir ──
# Durum dosyasinda onceki mod VARSA ve degisiyorsa gercek gecistir.
durum_sifirla()
oto_set.durum_yaz({"donem": "gece", "chiller_mod": "koc_soguk", "diger_mod": "sogutma"})
sb4 = Sahte(TEMEL)
calistir(sb4, tahmin=(30.0, 24.0), saat=12)    # gunduz, 30 -> sicak (koc_soguk'tan farkli)
c("gercek mod degisimi 'chiller' tipinde",
  any(l["tip"] == "chiller" for l in sb4.loglar), str([l["tip"] for l in sb4.loglar]))
c("gercek degisimde eski mod dogru kaydedilir",
  any(l.get("eski_mod") == "koc_soguk" for l in sb4.loglar),
  str([l.get("eski_mod") for l in sb4.loglar]))
c("koc_soguk -> sicak tek adimda (kademesiz)",
  sum(1 for d, _, _ in sb4.yazilan if d == 6.5) == 5,
  str(sorted({d for d, _, _ in sb4.yazilan})))

# ── 6) OTO-SET kapaliyken hicbir sey yapilmaz ──
durum_sifirla()
sb = Sahte(dict(TEMEL, oto_set_aktif="false"))
calistir(sb, saat=12)
c("oto_set kapaliyken yazma yok", len(sb.yazilan) == 0)

# ── 6b) Kural okunamiyorsa (RLS izni yok) hicbir sey yapilmaz ──
# Varsayilan saatlerle calisip yanlis saatte set gondermek YASAK.
durum_sifirla()
sb = Sahte({})
calistir(sb, saat=12)
c("kural okunamazsa yazma yok", len(sb.yazilan) == 0)
c("kural okunamazsa durum yazilmaz", not os.path.exists(oto_set.DURUM_FILE))

# ── 7) Nokta yoksa yazma yok ──
durum_sifirla()
sb = Sahte(TEMEL, noktalar=[])
calistir(sb, saat=12)
c("nokta yoksa yazma yok", len(sb.yazilan) == 0)
c("nokta yoksa durum da yazilmaz (tekrar denenebilsin)",
  not os.path.exists(oto_set.DURUM_FILE))

# ── 8) Yalnizca TANIMLI noktalara yazilir ──
durum_sifirla()
sb = Sahte(TEMEL, noktalar=["CH1_REM_SET", "A_BLOK_FCU_SET"])
calistir(sb, saat=12)
c("tanimsiz noktaya yazilmaz", len(sb.yazilan) == 2, "%d" % len(sb.yazilan))

# ── 9) Tahmin alinamazsa gecis ERTELENIR ──
durum_sifirla()
sb = Sahte(TEMEL)
calistir(sb, tahmin=None, saat=12)
c("tahmin yoksa yazma YOK", len(sb.yazilan) == 0, "%d" % len(sb.yazilan))
c("tahmin yoksa durum yazilmaz", not os.path.exists(oto_set.DURUM_FILE))

# ── 10) BACnet yazma hatasi durumu bozmamali ama kayit altina alinmali ──
durum_sifirla()
sb = Sahte(TEMEL, yazma_basarili=False)
calistir(sb, saat=12)
_d = oto_set.durum_oku()
c("yazma hatasinda hatali sayaci dolu", _d.get("hatali", 0) == 11, str(_d.get("hatali")))
c("yazma hatasinda yazilan sifir", _d.get("yazilan", -1) == 0, str(_d.get("yazilan")))

# ── 11) Deger dogrulama kapisi devrede mi (5-40 C) ──
durum_sifirla()
_eski_set = dict(oto_set.CH_SET)
oto_set.CH_SET["sicak"] = 500.0                # bilerek bozuk deger
sb = Sahte(TEMEL)
calistir(sb, tahmin=(30.0, 24.0), saat=12)
oto_set.CH_SET.update(_eski_set)
c("aralik disi setpoint SAHAYA GITMEZ",
  all(d != 500.0 for d, _, _ in sb.yazilan), str([d for d, _, _ in sb.yazilan][:3]))

# ── 11b) GORUNURLUK: her cikis yolu SEBEP birakmali ──
# Sistem 10 gun boyunca sessizce durdu ve kimse fark etmedi; sessiz return
# yok artik. Her senaryodan sonra durum_ozet() ne oldugunu soylemeli.
def sonuc():
    return oto_set.durum_ozet()["sonuc"]


durum_sifirla()
calistir(Sahte({}), saat=12)
c("[gorunurluk] kural okunamadi bildirilir", sonuc() == "kural_okunamadi", sonuc())

durum_sifirla()
calistir(Sahte(dict(TEMEL, oto_set_aktif="false")), saat=12)
c("[gorunurluk] oto-set kapali bildirilir", sonuc() == "kapali", sonuc())

durum_sifirla()
calistir(Sahte(TEMEL), tahmin=None, saat=12)
c("[gorunurluk] tahmin yok bildirilir", sonuc() == "tahmin_yok", sonuc())

durum_sifirla()
calistir(Sahte(TEMEL), saat=12)
c("[gorunurluk] setler yazildi bildirilir", sonuc() == "yazildi", sonuc())
calistir(Sahte(TEMEL), saat=12)          # ayni donem — gecis yok
c("[gorunurluk] gecis yok bildirilir", sonuc() == "gecis_yok", sonuc())

durum_sifirla()
calistir(Sahte(TEMEL, yazma_basarili=False), saat=12)
c("[gorunurluk] BACnet hatasi bildirilir", sonuc() == "yazma_hatasi", sonuc())

durum_sifirla()
calistir(Sahte(TEMEL, noktalar=[]), saat=12)
c("[gorunurluk] nokta yok bildirilir", sonuc() == "nokta_yok", sonuc())

_ozet = oto_set.durum_ozet()
c("[gorunurluk] ozet zaman ve okunur metin icerir",
  bool(_ozet.get("zaman")) and bool(_ozet.get("metin")), str(_ozet))
c("[gorunurluk] her sonuc kodunun Turkce karsiligi var",
  all(k in oto_set.SONUC_METIN for k in
      ("kural_okunamadi", "kapali", "gecis_yok", "tahmin_yok",
       "nokta_yok", "yazildi", "yazma_hatasi", "hata", "henuz_calismadi")))

# bacnet_writer yuklenemezse bu "nokta yok" gibi gorunmemeli — gercek sebep
# kaybolursa teshis yine imkansiz hale gelir.
durum_sifirla()
_gercek_uygula = oto_set._setleri_uygula


def _patlat(*a, **k):
    raise RuntimeError("bacnet_writer yuklenemedi: test")


oto_set._setleri_uygula = _patlat
calistir(Sahte(TEMEL), saat=12)
oto_set._setleri_uygula = _gercek_uygula
c("[gorunurluk] bacnet_writer yoksa 'hata' olarak bildirilir", sonuc() == "hata", sonuc())

# ── 11c) SAHADA DOGRULAMA — "yazildi" artik ACK'a degil GERI OKUMAYA dayanir ──
# Sikayet: log "gonderildi" diyor ama sahada set degismiyor. Cihaz yazmayi
# kabul edip (ACK) degeri uygulamayabilir (daha yuksek oncelikli yazma).
durum_sifirla()
sb = Sahte(TEMEL)
calistir(sb, saat=12)
_oz = oto_set.durum_ozet()
c("[saha] hepsi geri okundu -> yazildi", _oz["sonuc"] == "yazildi", _oz["sonuc"])
c("[saha] dogrulanan sayisi 11", (_oz.get("saha") or {}).get("dogrulandi") == 11, _oz.get("saha"))

durum_sifirla()
sb = Sahte(TEMEL, saha={"CH1_REM_SET": 7.5})          # 6.5 yazildi, cihazda 7.5
calistir(sb, tahmin=(30.0, 24.0), saat=12)
_oz = oto_set.durum_ozet()
c("[saha] cihazda farkli deger -> sahada_farkli", _oz["sonuc"] == "sahada_farkli", _oz["sonuc"])
c("[saha] farkli sayisi 1", (_oz.get("saha") or {}).get("farkli") == 1, _oz.get("saha"))
# Bir dakika sonra tur sonucu "gecis_yok" olur — ama sorun KAYBOLMAMALI
calistir(sb, tahmin=(30.0, 24.0), saat=12, dakika=1)
_oz = oto_set.durum_ozet()
c("[saha] sonraki turda anlik sonuc gecis_yok", _oz["sonuc"] == "gecis_yok", _oz["sonuc"])
c("[saha] ama son gecisin sorunu KALICI", _oz.get("son_yazim_sonuc") == "sahada_farkli",
  _oz.get("son_yazim_sonuc"))

durum_sifirla()
sb = Sahte(TEMEL, saha={"A_BLOK_FCU_SET": "OKUNAMADI"})
calistir(sb, saat=12)
c("[saha] geri okunamadi -> dogrulanamadi",
  oto_set.durum_ozet()["sonuc"] == "dogrulanamadi", oto_set.durum_ozet()["sonuc"])

durum_sifirla()
sb = Sahte(TEMEL, yazma_basarili=False, saha={"CH1_REM_SET": 99})
calistir(sb, saat=12)
c("[saha] yazma hatasi farkli degerden once gelir",
  oto_set.durum_ozet()["sonuc"] == "yazma_hatasi", oto_set.durum_ozet()["sonuc"])

# ── 11d) CHILLER IC SET IZLEMESI ──
# REM SET oturmus olsa bile chiller onu uygulamayabilir (yerel mod vb.).
# Gecisten sonraki dakikalarda IC SET okunur; beklemeye kilitlenmez.
HARITA = {f"CH{i}_REM_SET": {"gateway_ip": "10.0.0.1", "dnet": 2, "mac_hex": "011F",
                             "obj_type": 1, "obj_inst": 100 + i} for i in range(1, 6)}
IC_UYGULADI = {100 + i: 6.5 for i in range(1, 6)}      # sicak -> 6.5
IC_ESKI = {100 + i: 7.5 for i in range(1, 6)}          # hala eski set

durum_sifirla()
sb = Sahte(TEMEL, harita=HARITA, ic=IC_ESKI)
calistir(sb, tahmin=(30.0, 24.0), saat=12, dakika=0)
_dg = oto_set.durum_ozet().get("dogrulama") or {}
c("[ic] gecisten hemen sonra izleme 'bekliyor'", _dg.get("sonuc") == "bekliyor", _dg)

calistir(sb, tahmin=(30.0, 24.0), saat=12, dakika=5)          # 5 dk: hala eski
_dg = oto_set.durum_ozet().get("dogrulama") or {}
c("[ic] 5. dakikada uymuyor ama sure dolmadi -> bekliyor", _dg.get("sonuc") == "bekliyor", _dg)
c("[ic] okunan degerler kaydedildi", (_dg.get("okunan") or {}).get("CH1_REM_SET") == 7.5, _dg)

sb.ic = dict(IC_UYGULADI)                                      # chiller uyguladi
calistir(sb, tahmin=(30.0, 24.0), saat=12, dakika=6)
_dg = oto_set.durum_ozet().get("dogrulama") or {}
c("[ic] chiller uygulayinca 'uygulandi'", _dg.get("sonuc") == "uygulandi", _dg)
c("[ic] ozet metni okunur", "uyguladı" in (_dg.get("metin") or ""), _dg.get("metin"))

durum_sifirla()
sb = Sahte(TEMEL, harita=HARITA, ic=IC_ESKI)
calistir(sb, tahmin=(30.0, 24.0), saat=12, dakika=0)
calistir(sb, tahmin=(30.0, 24.0), saat=12, dakika=oto_set.IC_IZLEME_DK)   # sure doldu
_dg = oto_set.durum_ozet().get("dogrulama") or {}
c("[ic] sure dolunca hala uymuyorsa 'uygulanmadi'", _dg.get("sonuc") == "uygulanmadi", _dg)
c("[ic] uymayan chiller'lar listelenir", len(_dg.get("uymayan") or []) == 5, _dg.get("uymayan"))
_yazilan_once = len(sb.yazilan)
calistir(sb, tahmin=(30.0, 24.0), saat=12, dakika=oto_set.IC_IZLEME_DK + 1)
c("[ic] sonuclanan izleme tekrar YAZMA yapmaz", len(sb.yazilan) == _yazilan_once,
  (len(sb.yazilan), _yazilan_once))
c("[ic] sonuc kalici", (oto_set.durum_ozet().get("dogrulama") or {}).get("sonuc") == "uygulanmadi")

durum_sifirla()
sb = Sahte(TEMEL, harita={}, ic=IC_ESKI)
calistir(sb, saat=12)
c("[ic] harita yoksa izleme baslatilmaz", oto_set.durum_ozet().get("dogrulama") is None,
  oto_set.durum_ozet().get("dogrulama"))

durum_sifirla()
sb = Sahte(TEMEL, harita=HARITA, ic=IC_ESKI, yazma_basarili=False)
calistir(sb, saat=12)
c("[ic] yazilamayan noktanin IC'si izlenmez", oto_set.durum_ozet().get("dogrulama") is None,
  oto_set.durum_ozet().get("dogrulama"))

# ── 12) Merkez ile kural esitligi (sapma olmasin) ──
try:
    _mk = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "merkez", "app_merkez.py")
    _metin = open(_mk, encoding="utf-8").read()
    _ns = {}
    for _d2 in [r"_CH_SINIRLAR\s*=.*?\n", r"_CH_MODLAR\s*=.*?\n", r"_CH_SET\s*=.*?\n",
                r"_CH_H\s*=.*?\n", r"_DIG_ESIK\s*=.*?\n", r"_DIG_H\s*=.*?\n",
                r"_DIG_SET\s*=\s*\{.*?\n\}\n",
                r"def _hedef_bolge.*?(?=\ndef )", r"def _ch_modu_hesapla.*?(?=\ndef )",
                r"def _dig_modu_hesapla.*?(?=\n_OTO_GUNDUZ)",
                r"def _donem_hesapla.*?(?=\ndef )"]:
        _m = re.search(_d2, _metin, re.DOTALL)
        if _m:
            exec(_m.group(0), _ns)
    _fark = [(t, m) for t in [-5, 0, 5, 6.9, 7.1, 15, 22.9, 23.1, 25, 26.1, 30, 35]
             for m in ["", "koc_soguk", "serin", "ilimli", "sicak"]
             if _ns["_ch_modu_hesapla"](t, m) != oto_set.ch_modu_hesapla(t, m)]
    c("chiller kurallari merkez ile AYNI", not _fark, str(_fark[:4]))
    c("setpoint tablosu merkez ile AYNI", _ns["_CH_SET"] == oto_set.CH_SET)
    c("sinirlar/histerezis merkez ile AYNI",
      _ns["_CH_SINIRLAR"] == oto_set.CH_SINIRLAR and _ns["_CH_H"] == oto_set.CH_H)
    c("kollektor/FCU tablosu merkez ile AYNI", _ns["_DIG_SET"] == oto_set.DIG_SET)
    _fark2 = [(s, g, ge) for s in range(24) for g, ge in [(5, 22), (8, 23), (22, 5)]
              if _ns["_donem_hesapla"](s, g, ge) != oto_set.donem_hesapla(s, g, ge)]
    c("donem hesabi merkez ile AYNI", not _fark2, str(_fark2[:4]))
except Exception as e:
    c("merkez karsilastirmasi", False, "yapilamadi: %s" % e)

hata = sum(1 for _, ok, _ in T if not ok)
print()
for ad, ok, d in T:
    print(("PASS " if ok else "FAIL ") + ad + (("   [%s]" % d) if (d and not ok) else ""))
print("\n%d/%d PASS" % (len(T) - hata, len(T)))
sys.exit(1 if hata else 0)
