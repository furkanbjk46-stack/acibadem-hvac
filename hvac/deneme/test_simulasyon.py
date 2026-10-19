# -*- coding: utf-8 -*-
"""Sahte saha sunucusu doğru mu? (simulasyon_sunucu.py)

Test aracının kendisi sessizce bozulursa, ekranda gördüğümüz her şeyi
sorgularız — "kod mu yanlış, simülasyon mu?" diye saatler gider. Bu test
üç şeyi şarta bağlar:

  1) GÜVENLİK — saha PC'sinde çalışmayı reddetmeli ve Supabase'e tek bir
     şey bile yazmamalı. Sahte analiz buluta giderse Synapse kirlenir.
  2) TUTARLILIK — bir tur içinde aynı nokta iki kez okunduğunda AYNI değer
     dönmeli (kazanın girişi ile çıkışı farklı ana ait olamaz) ve arıza
     kurbanları turdan tura değişmemeli.
  3) FİZİK — kışın kazan çalışıp chiller durmalı, yazın tersi; üretim
     talebi kademeli olarak karşılamalı, ekipman kapasitesi aşılmamalı.
"""
import json
import os
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import simulasyon_sunucu as sim  # noqa: E402

KAYNAK = open(os.path.join(BURASI, "simulasyon_sunucu.py"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── 1) Güvenlik ──────────────────────────────────────────────────────────
c("saha kurulumunda çalışmayı reddediyor",
  'supabase_config.json' in KAYNAK and "DURDURULDU: burası bir LOKASYON kurulumu" in KAYNAK)
c("Supabase bildirimi susturuluyor",
  "_bildirim_gunde_bir_gonder = lambda" in KAYNAK)
# Dışarıya açılan TEK adres localhost olmalı: simülatör ne buluta yazar
# ne de internetten bir şey çeker (dış hava bile mevsim eğrisinden gelir).
import re  # noqa: E402

_adresler = re.findall(r'https?://[^\s"\']+', KAYNAK)
c("dışarıya açılan tek adres localhost",
  all("localhost" in u or "127.0.0.1" in u for u in _adresler), _adresler)
c("ağ çağrısı yalnızca portal sağlık kontrolü",
  KAYNAK.count("urlopen(") == 1)
c("ekrana 'sadece local test' uyarısı basıyor",
  "SADECE LOCAL TEST" in KAYNAK)

# Üretim dosyalarına dokunmuyor: yalnızca kendi süreci içinde yama yapıyor
c("üretim kodu değiştirilmiyor, yalnızca çalışma anında yamalanıyor",
  "def _yamala(" in KAYNAK and "ac._bacnet_oku =" in KAYNAK)
_yama_sayisi = sum(KAYNAK.count("ac.%s =" % f) for f in
                   ("_bacnet_oku", "_oat_cek", "_csv_tazelik_kontrol",
                    "_bildirim_gunde_bir_gonder"))
c("yalnızca dış dünyaya bakan 4 fonksiyon taklit ediliyor", _yama_sayisi == 4, _yama_sayisi)
# Hesap zinciri taklit EDİLMEMELİ — yoksa test ettiğimiz şey sahadaki kod olmaz
for _f in ("talep_hesapla", "talep_isitma_hesapla", "kazan_uretim_hesapla",
           "chiller_uretim_hesapla", "_ahu_row_olustur", "ek_ekipman_satirlari_olustur"):
    c("hesap fonksiyonu taklit edilmiyor: %s" % _f, ("ac.%s =" % _f) not in KAYNAK)

# ── 2) Tesis değerleri configs'ten geliyor ───────────────────────────────
saha = sim.Saha("kis", tohum=1, arizali=True)
_ayar = json.load(open(os.path.join(BURASI, "configs", "chiller_fcu_ayarlari.json"),
                       encoding="utf-8"))
c("kazan birim gücü ayarlardan", saha.kazan_birim == float(_ayar["kazan_birim_kw"]),
  saha.kazan_birim)
c("kazan adedi ayarlardan", saha.kazan_adedi == int(_ayar["kazan_adedi"]), saha.kazan_adedi)
c("chiller birim gücü ayarlardan", saha.chiller_birim == float(_ayar["chiller_birim_kw"]))
c("tasarım ΔT kural motorundan", saha.kazan_tasarim_dt == 8.0, saha.kazan_tasarim_dt)
c("ısıtma kapasiteleri yüklendi", len(saha.kapasite_isitma) >= 1 and
  sum(len(v) for v in saha.kapasite_isitma.values()) > 40)

# ── 3) Tur içi tutarlılık ────────────────────────────────────────────────
santraller = [(a, m) for m, v in saha.kapasite_isitma.items() for a in v]
saha.santralleri_tanit(santraller)

_ad, _mahal = santraller[0]
_bir = saha.ahu(_ad, _mahal)
_iki = saha.ahu(_ad, _mahal)
c("aynı tur içinde santral değeri değişmiyor", _bir == _iki)

_k1 = saha.kazanlar()
_k2 = saha.kazanlar()
c("aynı tur içinde kazan değeri değişmiyor", _k1 == _k2)
c("kolektör ısıtma gidişi çalışan kazanın çıkışıyla aynı",
  not [k for k in _k1 if k[0] == 1.0] or
  abs(saha.kolektor()["MAS-1 ISITMA SICAKLIK"] - [k for k in _k1 if k[0] == 1.0][0][2]) < 0.01)

_oat1 = saha.oat
saha.ilerle(10)
c("tur ilerleyince önbellek boşalıyor", saha._anlik == {})
c("saat ilerliyor", saha.saat.minute % 10 == 0)

# Arıza kurbanları SABİT kalmalı
_arizalar_once = dict(saha.arizalar)
saha.ilerle(10)
saha.kazanlar()
c("arıza kurbanları turdan tura değişmiyor", saha.arizalar == _arizalar_once)
c("üç arıza senaryosu da atanmış",
  sorted(saha.arizalar.values()) == ["basmiyor", "durdu", "sensor"], saha.arizalar)
_durdu = [k for k, v in saha.arizalar.items() if v == "durdu"][0]
c("duran santralin fanı kapalı", saha.ahu(*_durdu)["Start/Stop"] == 0.0)
_sensor = [k for k, v in saha.arizalar.items() if v == "sensor"][0]
c("sensör arızalı santralin üflemesi okunmuyor", saha.ahu(*_sensor)["SAT (°C)"] is None)

_temiz = sim.Saha("kis", tohum=1, arizali=False)
_temiz.santralleri_tanit(santraller)
c("--arizasiz ile arıza üretilmiyor", _temiz.arizalar == {})

# ── 4) Fizik: mevsim davranışı ───────────────────────────────────────────
def _tur_ozeti(mevsim, saat):
    s = sim.Saha(mevsim, tohum=7, arizali=False)
    s.santralleri_tanit(santraller)
    s.saat = s.saat.replace(hour=saat)
    s._anlik.clear()
    isitma_talep, sogutma_talep = s._talepler()
    kaz = [k for k in s.kazanlar() if k[0] == 1.0]
    ch = [x for x in s.chillerlar() if x[0] == 1.0]
    uretim_isitma = sum(s.kazan_birim * min(abs(k[2] - k[1]) / s.kazan_tasarim_dt, 1.0)
                        for k in kaz)
    uretim_sogutma = sum(s.chiller_birim * x[3] / 100.0 for x in ch)
    return dict(oat=s.oat, it=isitma_talep, st=sogutma_talep, kaz=len(kaz), ch=len(ch),
                ui=uretim_isitma, us=uretim_sogutma)


_kis = _tur_ozeti("kis", 6)
c("kışın ısıtma talebi var", _kis["it"] > 100, _kis)
c("kışın kazan çalışıyor", _kis["kaz"] >= 1, _kis)
c("kışın chiller durur", _kis["ch"] == 0, _kis)
c("kışın soğutma talebi yok", _kis["st"] == 0, _kis)
c("kış üretimi talebi karşılıyor", _kis["ui"] >= _kis["it"], _kis)
c("kış üretimi tesis kapasitesini aşmıyor",
  _kis["ui"] <= saha.kazan_birim * saha.kazan_adedi + 1, _kis)

_yaz = _tur_ozeti("yaz", 15)
c("yazın soğutma talebi var", _yaz["st"] > 100, _yaz)
c("yazın chiller çalışıyor", _yaz["ch"] >= 1, _yaz)
c("yazın kazan durur", _yaz["kaz"] == 0, _yaz)
c("yazın ısıtma talebi yok", _yaz["it"] == 0, _yaz)
c("yaz üretimi talebi karşılıyor", _yaz["us"] >= _yaz["st"], _yaz)
c("yaz üretimi tesis kapasitesini aşmıyor",
  _yaz["us"] <= saha.chiller_birim * saha.chiller_adedi + 1, _yaz)

c("kış dış havası soğuk", _kis["oat"] < 12, _kis["oat"])
c("yaz dış havası sıcak", _yaz["oat"] > 20, _yaz["oat"])


# ── 4b) Bütün bir gün: sistem ölü banda sıkışmamalı ──────────────────────
# İLK SÜRÜMDE OLAN HATA: mevsime dış hava eşiği de konunca (ör. "17°C
# üstünde ısıtma yok") ara mevsimde oda set'in altında kalıyor, ısıtma
# kapanıyor, soğutma da "oda zaten soğuk" diye açılmıyordu; sistem öğleden
# sonra sıfırda takılıp gün boyu orada kalıyordu. Ekranda kartlar boş
# görünüyor ve insan kodu suçluyor. Tek bir an yerine GÜNÜN TAMAMI ölçülür.
def _gun(mevsim, adim=60, tur=24):
    s = sim.Saha(mevsim, tohum=7, arizali=False)
    s.adim_dk = adim
    s.santralleri_tanit(santraller)
    s.saat = s.saat.replace(hour=0)
    isi = sog = bos = 0
    uretimsiz = []
    for _ in range(tur):
        it, st = s._talepler()
        kaz = [k for k in s.kazanlar() if k[0] == 1.0]
        ch = [x for x in s.chillerlar() if x[0] == 1.0]
        if it > 0:
            isi += 1
            if not kaz:
                uretimsiz.append(("ısıtma", s.saat.hour, it))
        if st > 0:
            sog += 1
            if not ch:
                uretimsiz.append(("soğutma", s.saat.hour, st))
        if it == 0 and st == 0:
            bos += 1
        s.ilerle(adim)
    return {"isi": isi, "sog": sog, "bos": bos, "uretimsiz": uretimsiz, "tur": tur}


_g_kis = _gun("kis")
c("kış günü boyunca ısıtma çalışıyor", _g_kis["isi"] >= 20, _g_kis)
c("kış gününde sistem sıfıra takılmıyor", _g_kis["bos"] <= 3, _g_kis)

_g_yaz = _gun("yaz")
c("yaz günü boyunca soğutma çalışıyor", _g_yaz["sog"] >= 12, _g_yaz)
c("yaz gününde ısıtma hiç açılmıyor", _g_yaz["isi"] == 0, _g_yaz)

_g_ara = _gun("ara")
c("ara mevsim ısıtmayı deniyor", _g_ara["isi"] >= 6, _g_ara)
c("ara mevsim soğutmayı da deniyor", _g_ara["sog"] >= 4, _g_ara)
c("ara mevsim gün boyu sıfıra takılmıyor", _g_ara["bos"] <= 8, _g_ara)

# Hatanın ASIL koşulu: dış hava 15-20 arasında gezinen DAR bir gün. Geniş
# bantta (ara mevsim) oda dışarıyla birlikte 26°C'ye çıkıp soğutmayı
# açtığı için kusur görünmez; asıl tuzak bu dar banttır. Tesis açıklığı
# dış havaya bağlanırsa bu gün baştan sona sıfırda geçer.
sim.MEVSIM["_test_dar_bant"] = {"oat_alt": 15.0, "oat_ust": 20.0,
                                "isitma": True, "sogutma": True}
_g_dar = _gun("_test_dar_bant")
c("dar dış hava bandında sistem ölü banda sıkışmıyor",
  _g_dar["bos"] <= 8 and _g_dar["isi"] >= 8, _g_dar)
del sim.MEVSIM["_test_dar_bant"]

# Mekanizmanın kendisi: tesisin açık olup olmadığı dış havaya BAKMAZ,
# vanaya mahal sıcaklığı karar verir.
import inspect  # noqa: E402

for _ad in ("isitma_var", "sogutma_var"):
    _kod = inspect.getsource(getattr(sim.Saha, _ad).fget)
    c("%s dış hava eşiğine bağlı değil" % _ad, "oat" not in _kod, _kod.strip())

# Talep varken üretim tarafı MUTLAKA devrede olmalı
for _ad, _g in (("kis", _g_kis), ("yaz", _g_yaz), ("ara", _g_ara)):
    c("%s: talep varken ekipman çalışıyor" % _ad, not _g["uretimsiz"], _g["uretimsiz"][:3])

# Bina tepkisi simüle adımla ölçeklenmeli: 10 dk'lık adımlarla 6 tur,
# 60 dk'lık adımla 1 tur kabaca aynı günü vermeli (aynı saate gelinmeli)
_ince = _gun("kis", adim=10, tur=144)
c("küçük adımda da gün dolu geçiyor", _ince["isi"] >= 120, _ince)

# Üretim talebin ÜSTÜNDE olmalı: kazanlar FCU/kar eritme/sıcak suyu da besler
c("ısıtmada üretim talepten yüksek (ölçülmeyen tüketiciler)",
  _kis["ui"] > _kis["it"], (_kis["ui"], _kis["it"]))

# ── 5) Kademeleme ────────────────────────────────────────────────────────
c("talep yoksa ekipman çalışmaz", sim.Saha._kademe(0, 1950, 3) == (0, 0.0))
_adet, _oran = sim.Saha._kademe(1000, 1950, 3)
c("küçük talep tek ekipmanla, kısmi yükte", _adet == 1 and 0.25 <= _oran <= 1.0, (_adet, _oran))
_adet, _oran = sim.Saha._kademe(3000, 1950, 3)
c("talep bir ekipmanı aşınca ikincisi devreye girer", _adet == 2, (_adet, _oran))
_adet, _oran = sim.Saha._kademe(99000, 1950, 3)
c("ekipman sayısı tesisle sınırlı", _adet == 3 and _oran == 1.0, (_adet, _oran))
_adet, _oran = sim.Saha._kademe(50, 1950, 3)
c("tek ekipman %25'in altına düşmez", _oran == 0.25, _oran)

# ── 6) Adres haritası gerçek konfigten ───────────────────────────────────
import ahu_collector as ac  # noqa: E402

if not os.path.exists(ac.AHU_CONFIG_FILE):
    ac.AHU_CONFIG_FILE = os.path.join(BURASI, "configs", "ahu_nokta_konfig.json")
harita, ahu_konfig, enerji_konfig, cakisma = sim.harita_kur(ac)
c("AHU nokta haritası okundu", len(ahu_konfig) > 300, len(ahu_konfig))
c("enerji nokta haritası okundu", len(enerji_konfig) > 30, len(enerji_konfig))
c("adres çakışması yok", cakisma == 0, cakisma)

_sahte = sim.sahte_bacnet_yap(saha, harita)
_bilinmeyen = _sahte("1.2.3.4", 0, "0x01", 0, 999999)
c("haritada olmayan adres None döner (sahada da öyle)", _bilinmeyen is None)

# Kazan noktaları gerçekten değer üretiyor mu
_kazan_noktalari = [n for n in enerji_konfig if n["point_name"].startswith("KAZAN-")]
c("kazan noktaları şablonda var", len(_kazan_noktalari) >= 9, len(_kazan_noktalari))
_degerler = {n["point_name"]: _sahte(n["gateway_ip"], n["dnet"], n["mac_hex"],
                                     n["obj_type"], n["obj_inst"])
             for n in _kazan_noktalari}
c("her kazan noktası değer üretiyor", all(v is not None for v in _degerler.values()),
  _degerler)
c("kazan ΔT tasarımı aşmıyor",
  all(abs(_degerler["KAZAN-%d OUTLET" % n] - _degerler["KAZAN-%d INLET" % n])
      <= saha.kazan_tasarim_dt + 0.5 for n in (1, 2, 3)), _degerler)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
