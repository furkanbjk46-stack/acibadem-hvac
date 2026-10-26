# -*- coding: utf-8 -*-
"""Lokasyon detay sayfasi — grafik secenekleri (ag baglantisi YOK).

Sayfa app_merkez'in globals()'i icinde exec edildigi icin butun olarak
calistirilamaz; bu yuzden secenek kurallari burada birebir kurulup
simulasyon verisiyle dogrulanir, sayfa metni de kontrol edilir.
"""
import ast
import os
import re
import sys

import pandas as pd

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BURASI = os.path.join(KOK, "merkez")
SAYFA = os.path.join(BURASI, "pages", "lokasyon_detay.py")
sys.path.insert(0, BURASI)

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


_metin = open(SAYFA, encoding="utf-8").read()
try:
    ast.parse(_metin)
    c("sayfa sozdizimi gecerli", True)
except SyntaxError as e:
    c("sayfa sozdizimi gecerli", False, str(e))

# ── Grafik listesinde trafo secenegi ──────────────────────────────────────
c("trafo secenegi listede", '"Trafolar (TRDP)"' in _metin)
c("trafo grafigi cizim dali var", 'grafik_tip == "trafo"' in _metin)
c("secenek KOSULA bagli (trafosuz lokasyonda olu link olmasin)",
  'if _trafo_kolonlar else []' in _metin)
c("lokasyon degisince eski secim temizlenir (Streamlit hatasi)",
  'st.session_state.get("grafik_sec") not in grafik_secenekler' in _metin)
# 23.10.2026: kullanıcı isteğiyle trafolar üst üste değil YAN YANA (gruplu) çizilir
c("trafolar yan yana (gruplu) cizilir",
  'barmode="group"' in _metin.split('grafik_tip == "trafo"')[1][:2000])
c("eksik sayac kullaniciya soylenir",
  "henüz bağlı değil" in _metin.split('grafik_tip == "trafo"')[1][:2500])


# ── Secenek kurali: SAYFADAKI ile ayni ────────────────────────────────────
def trafo_kolonlari(df):
    return sorted([c_ for c_ in df.columns if re.fullmatch(r"TRDP\d+_kWh", str(c_))
                   and pd.to_numeric(df[c_], errors="coerce").fillna(0).sum() > 0],
                  key=lambda c_: int(re.findall(r"\d+", c_)[0]))


c("kolonu olmayan lokasyonda secenek YOK",
  trafo_kolonlari(pd.DataFrame([{"Sebeke_Tuketim_kWh": 100}])) == [])
c("kolon var ama sayac bos ise secenek YOK",
  trafo_kolonlari(pd.DataFrame([{"TRDP1_kWh": 0, "TRDP2_kWh": None}])) == [])
c("dolu trafolar numara sirasinda",
  trafo_kolonlari(pd.DataFrame([{"TRDP10_kWh": 5, "TRDP2_kWh": 3, "TRDP1_kWh": 1}]))
  == ["TRDP1_kWh", "TRDP2_kWh", "TRDP10_kWh"])
c("bagli olmayan trafo (bos kolon) listeye girmez",
  trafo_kolonlari(pd.DataFrame([{"TRDP1_kWh": 5, "TRDP2_kWh": 0}])) == ["TRDP1_kWh"])

# ── HVAC analiz karti da acilir/kapanir olmali ────────────────────────────
# Onlarca AHU listelenince sayfa uzuyordu; arizali/bakimdaki kartlariyla
# ayni davranis: kapali gelir, tiklayinca acilir.
_hv_blok = _metin.split("HVAC ANALIZ DURUMU")[1][:1200]
c("HVAC analiz karti <details> ile acilir", "<details" in
  _metin.split("Sütun 3: HVAC Analiz")[1][:3000])
c("HVAC kartinda 'detay icin tikla' var", "detay için tıkla" in _hv_blok)
c("HVAC kartinda sorun sayisi ozeti var", "_hv_sorun" in _metin and "_hv_ozet" in _metin)
c("uc kartin ucu de acilir-kapanir", _metin.count("▼ detay için tıkla") == 3,
  _metin.count("▼ detay için tıkla"))

# ── KOJEN & KAYNAK kartlari ───────────────────────────────────────────────
# Maslak'in 4 trafosu bilindigi icin sabit listede kalir (TRDP-2 bagli degil,
# "—" gosterilir). Diger lokasyonlarda kart YALNIZCA dolu sayactan uretilir.
c("Maslak'in trafo kartlari sabit listede", 'TRDP-2 (Mek.)' in _metin)
c("diger lokasyonlarda kartlar veriden uretilir",
  "_trdp_kart" in _metin and 'f"TRDP-{_no}"' in _metin)
c("sutun sayisi kart sayisina gore ayarlanir",
  "len(_kaynak_items) > 6" in _metin)


def kaynak_kartlari(df, son_df):
    """Sayfadaki kuralin aynisi: hangi trafo icin kart uretilir."""
    out = []
    for c_ in trafo_kolonlari(df):
        no = re.findall(r"\d+", c_)[0]
        v = pd.to_numeric(son_df.get(c_), errors="coerce").fillna(0).sum() \
            if c_ in son_df.columns else 0
        out.append(("TRDP-%s" % no, v))
    return out


_bos = pd.DataFrame([{"Sebeke_Tuketim_kWh": 100}])
c("trafosuz lokasyonda kaynak karti eklenmez (ekran eskisi gibi)",
  kaynak_kartlari(_bos, _bos) == [])
_var = pd.DataFrame([{"TRDP1_kWh": 10, "TRDP2_kWh": 20}])
c("dolu trafolar icin kart uretilir",
  [a for a, _ in kaynak_kartlari(_var, _var)] == ["TRDP-1", "TRDP-2"])
_son_bos = pd.DataFrame([{"TRDP1_kWh": 0, "TRDP2_kWh": 0}])
c("trafo var ama o gun okuma yoksa deger 0 (kart kalir, '—' yazar)",
  [v for _, v in kaynak_kartlari(_var, _son_bos)] == [0, 0])

# ── Simulasyon: her lokasyonda secenek cikmali (sunum icin) ───────────────
import _sim_sunucu as S

_df = pd.DataFrame(S.veri_uret()["energy_data"])
_lokler = sorted(_df["lokasyon_id"].unique())
_adet = {l: len(trafo_kolonlari(_df[_df["lokasyon_id"] == l])) for l in _lokler}
c("simulasyonda her lokasyonda trafo grafigi acilir",
  all(v >= 2 for v in _adet.values()), {k: v for k, v in _adet.items() if v < 2})
c("simulasyonda trafo adedi lokasyona gore degisir",
  len(set(_adet.values())) > 1, sorted(set(_adet.values())))
_d = _df[_df["lokasyon_id"] == "atakent"]
_son = _d[_d["Tarih"] == _d["Tarih"].max()]
_kart = kaynak_kartlari(_d, _son)
c("simulasyonda kaynak bolumunde trafo kartlari dolu",
  len(_kart) >= 2 and all(v > 0 for _, v in _kart), _kart)

# ── Yururlukteki setler + hava konumu (lokasyona ozel) ───────────────────
# Setler her hastanede KENDI dis havasina gore belirlenir; degerler ana
# ekranda degil burada gosterilir. Konum da lokasyonun kendi profilinden
# gelir — profil girilmemisse Istanbul'a duser ve bu SESSIZ bir hatadir.
c("set bolumu heartbeat'ten okur",
  '.get("setler")' in _metin and 'bakim_ozet.get("oto")' in _metin)
c("dort set karti var (chiller/kollektor/FCU/AHU)",
  all(x in _metin for x in ("CHILLER", "KOLLEKTÖR", "FCU", "AHU")))
c("gomulu set degeri yok (kural yalnizca oto_set.py'de)",
  not any(v in _metin for v in ("7.5°C", "8.0°C", "7.0°C", "6.5°C")))
c("varsayilan konum kullaniciya uyari olarak cikar",
  'kaynak") == "varsayilan"' in _metin and "profili girilmemiş" in _metin)
c("konum profilden geliyorsa koordinat gosterilir",
  "Hava konumu" in _metin)

def _ozet_coz(l):
    """bakim_ozet Supabase'de JSONB; simulasyon metin olarak uretir."""
    import json as _j
    b = l.get("bakim_ozet") or {}
    if isinstance(b, str):
        try:
            b = _j.loads(b)
        except Exception:
            b = {}
    return (b or {}).get("oto") or {}


_lok_ozet = {l["lokasyon_id"]: _ozet_coz(l) for l in S.veri_uret()["lokasyonlar"]}
_konumlu = {k: v["konum"] for k, v in _lok_ozet.items() if v.get("konum")}
c("simulasyonda her aktif lokasyon konum bildirir", len(_konumlu) >= 19, len(_konumlu))
c("simulasyonda konumlar lokasyona gore farkli",
  len({(k["enlem"], k["boylam"]) for k in _konumlu.values()}) >= 5,
  len({(k["enlem"], k["boylam"]) for k in _konumlu.values()}))
c("simulasyonda profili girilmemis bir kurulum da var (uyari gorunsun)",
  any(k.get("kaynak") == "varsayilan" for k in _konumlu.values()))
# ── Lokasyona ozel gecis saatleri ────────────────────────────────────────
# Saat anahtarlari tek takimdi; bir hastanenin saatini degistirmek hepsini
# degistiriyordu. Artik lokasyon detayindan `oto_*_<lokasyon>` yazilir, bos
# deger genel kurala dondurur.
c("lokasyonun kendi saat ayari var",
  '"oto_gunduz_saat_%s" % lok_id' in _metin and '"oto_gece_saat_%s" % lok_id' in _metin)
c("genel kurala donus BOS deger yazar (satir silinmez, RLS)",
  '_ayar_yaz("oto_gunduz_saat_%s" % lok_id, "")' in _metin)
c("ozel saat mi genel kural mi oldugu yazar",
  "bu lokasyona özel" in _metin and "genel kural" in _metin)
c("sunum modunda kontroller pasif (ornek veriye yazilmaz)",
  "Sunum modu — ayar yazılmaz" in _metin and "disabled=_demo" in _metin)
c("ayni saat secilirse kaydedilemez", "_yg == _yge" in _metin)

_mrk = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
c("ana ekran genel saati 'genel' diye isaretler",
  "Geçiş saatleri (genel)" in _mrk)
c("ana ekran kendi saatiyle calisan lokasyonlari sayar",
  "_ozel_saatli" in _mrk and "%d özel" in _mrk
  and "Kendi geçiş saatiyle çalışan lokasyonlar" in _mrk)
# Gecis saatleri ve gecis kayitlari asagi dogru liste acmak yerine modal
# pencerede acilir: kart boyu sabit kalsin, yanindaki kartlarla hizasi bozulmasin.
c("gecis saatleri pop-up olarak acilir", "@st.dialog" in _mrk
  and "_oto_saat_popup" in _mrk)
c("gecis kayitlari da pop-up", "_oto_liste_popup" in _mrk)
c("pop-up acikken otomatik yenileme durur",
  'not st.session_state.get("_oto_popup")' in _mrk)
c("senaryo anahtari Apple tarzi (acik yesil / kapali kirmizi)",
  "st-key-oto_switch_on" in _mrk and "#30d158" in _mrk and "#ff453a" in _mrk)
c("kart basliginin altindaki durum metni kaldirildi (bilgi anahtarin renginde)",
  "_alt_txt" not in _mrk and "_st_txt" not in _mrk)
# Kart sadelestirildi: SETLER ozet seridi ve "N komut gonderildi" satiri
# kaldirildi; ayrisma/konum uyarilari SAHA DURUMU listesine tasindi.
c("SETLER ozet seridi karttan kaldirildi", "_set_html" not in _mrk)
c("komut sayisi satiri karttan kaldirildi", "_cnt_html" not in _mrk)
c("set ayrismasi SAHA DURUMU listesine dusuyor",
  "_saha_satirlar.insert" in _mrk and "farklı set" in _mrk)
c("varsayilan konum uyarisi da listede", "varsayılan konumda" in _mrk)
c("saha durumu kendi kartinda", "_saglik_html" in _mrk
  and "SAHA DURUMU" in _mrk and "border-radius:10px" in _mrk)
c("5 satirdan sonrasi kaydirmaya girer",
  "_SAHA_GORUNUR = 5" in _mrk and "_SAHA_SATIR_PX" in _mrk
  and "overflow-y:auto" in _mrk)
# Sag kolondaki kartlar AYNI kalibi kullanir (Enerji Zekasi 22.10.2026'da kaldirildi): cerceve kabin kendisinde,
# baslik ortak fonksiyondan. Her kart kendi kutusunu cizdiginde kenarlik,
# kose yaricapi ve baslik puntolari (8 px / 15 px) tutmuyordu.
for _k in ("oto_set_karti", "dis_hava_karti", "sabah_analiz_karti"):
    c("%s ortak kart kalibinda" % _k,
      ('st.container(key="%s")' % _k) in _mrk and (".st-key-%s" % _k) in _mrk)
c("Enerji Zekasi karti kaldirildi", 'key="enerji_zekasi_karti"' not in _mrk)
c("kart basligi TEK fonksiyondan uretilir",
  _mrk.count("def _kart_basligi") == 1 and _mrk.count("_kart_basligi(") >= 4)
c("kartlar ayri kutu cizmiyor (eski 8 px cerceve kalmadi)",
  "border-radius:8px;padding:14px 16px" not in _mrk)
c("yeniden analiz dugmesi kartin icinde (negatif margin hilesi yok)",
  "margin-top:-32px" not in _mrk)
c("kartlarin son satiri dibe yapismasin (alt bosluk)",
  "padding-bottom:18px" in _mrk and "_KART_ALT" in _mrk)

# NOT: 11.10.2026'da harita mobil icin akisa alinmis (st-key-harita_kabi +
# medya sorgusu), gorunum kullanici tarafindan KOTU bulundugu icin GERI
# ALINMISTIR. Harita yine sutun sirasina bagli tam ekran kaliptadir;
# mobil duzeni degistirilecekse once sahada gorsel onay alinmali.
c("harita tam ekran kalibinda (geri alindi)",
  '[data-testid="column"]:nth-child(2) iframe' in _mrk
  and "harita_kabi" not in _mrk)

c("zaman damgasi gecis saatleri kartinin altinda",
  "_os_zaman" in _mrk.split('key="oto_saat_kart"')[1][:600])

_kurallar = {k: (v.get("kural") or {}) for k, v in _lok_ozet.items() if v}
c("simulasyonda lokasyonlar yururlukteki kurali bildirir",
  all(isinstance(k.get("gunduz_saat"), int) for k in _kurallar.values()), _kurallar)
c("simulasyonda kendi saatiyle calisan lokasyon var",
  any(k.get("ozel") for k in _kurallar.values()))
c("simulasyonda cogu lokasyon genel kuralda",
  sum(1 for k in _kurallar.values() if not k.get("ozel")) > 10)

c("simulasyonda tahmin referansi bildirilir",
  all(isinstance((v.get("tahmin") or {}).get("ref"), (int, float))
      for v in _lok_ozet.values() if v))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
