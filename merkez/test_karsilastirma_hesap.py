# -*- coding: utf-8 -*-
"""karsilastirma_hesap.py testleri + demo sayfasi butunlugu — ag YOK.

    python merkez/test_karsilastirma_hesap.py
"""
import ast
import os
import re
import sys
from datetime import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import karsilastirma_hesap as KH
import _sim_sunucu as S

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── 1) Esik durumu: yon dogru mu ─────────────────────────────────────────
c("tuketim: esik ustu kotu", KH.esik_durumu(1.7, 1.6, False) == (True, "Eşik üstü"))
c("tuketim: esik alti normal", KH.esik_durumu(1.5, 1.6, False) == (False, "Normal"))
c("tuketim: tam esikte normal", KH.esik_durumu(1.6, 1.6, False)[0] is False)
c("uretim (kojen): hedef alti kotu", KH.esik_durumu(30, 33, True) == (True, "Hedef altı"))
c("uretim: hedef ustu normal", KH.esik_durumu(36, 33, True) == (False, "Normal"))
c("esik yoksa belirsiz", KH.esik_durumu(1.7, None, False) == (None, "—"))
c("deger yoksa belirsiz", KH.esik_durumu(None, 1.6, False) == (None, "—"))

# ── 2) Sistem dagilimi — GERCEK kolonlardan, uydurma kalem yok ───────────
satirlar = [
    {"Toplam_Hastane_Tuketim_kWh": 1000, "Chiller_Tuketim_kWh": 300, "Chiller1_kWh": 200,
     "Chiller2_kWh": 100, "Kule1_kWh": 30, "MCC_Tuketim_kWh": 220, "MCC1_kWh": 120,
     "MCC_CK_F01_kWh": 100, "VRF_Split_Tuketim_kWh": 50, "Sebeke_Tuketim_kWh": 650,
     "Kojen_Uretim_kWh": 350},
    {"Toplam_Hastane_Tuketim_kWh": 1000, "Chiller_Tuketim_kWh": 300, "Chiller1_kWh": 200,
     "Chiller2_kWh": 100, "Kule1_kWh": 30, "MCC_Tuketim_kWh": 220, "MCC1_kWh": 120,
     "MCC_CK_F01_kWh": 100, "VRF_Split_Tuketim_kWh": 50, "Sebeke_Tuketim_kWh": 650,
     "Kojen_Uretim_kWh": 350},
]
d = KH.sistem_dagilimi(satirlar)
kal = {a: (k, y) for a, k, y, _ in d["kalemler"]}
c("toplam 2000", d["toplam"] == 2000, d["toplam"])
c("chiller 600 (%30)", kal["Chiller grupları"] == (600, 30.0), kal.get("Chiller grupları"))
c("kule 60", kal["Soğutma kuleleri"][0] == 60, kal.get("Soğutma kuleleri"))
c("MCC 440", kal["MCC panoları (pompa, fan, AHU)"][0] == 440)
c("VRF 100", kal["VRF / split klimalar"][0] == 100)
c("olculmeyen kalan = toplam - olculenler (800)",
  kal["Diğer / ayrı sayaçla ölçülmeyen"][0] == 800, kal.get("Diğer / ayrı sayaçla ölçülmeyen"))
c("yuzdeler toplami 100", abs(sum(y for _, y in kal.values()) - 100) < 1e-6)
c("uydurma kalem YOK (aydinlatma/medikal/UPS/COP)",
  not any(re.search(r"aydınlat|medikal|ups|cop", a, re.I) for a in kal))
c("chiller bazinda CH-1 / CH-2", d["chiller"] == [("CH-1", 400), ("CH-2", 200)], d["chiller"])
c("kule bazinda Kule-1", d["kule"] == [("Kule-1", 60)], d["kule"])
c("MCC pano isimleri (Maslak formati dahil)",
  [a for a, _ in d["mcc"]] == ["MCC1", "MCC CK F01"], d["mcc"])
c("MCC_Tuketim_kWh pano listesinde tekrar sayilmaz",
  all("Tuketim" not in a for a, _ in d["mcc"]))
c("sebeke/kojen", (d["sebeke"], d["kojen"]) == (1300, 700))

d0 = KH.sistem_dagilimi([{"Toplam_Hastane_Tuketim_kWh": 500}])
c("kirilim kolonu yoksa yalniz 'olculmeyen' kalir",
  [a for a, *_ in d0["kalemler"]] == ["Diğer / ayrı sayaçla ölçülmeyen"], d0["kalemler"])
d_bos = KH.sistem_dagilimi([])
c("bos veri cokmez", d_bos["toplam"] == 0 and d_bos["kalemler"] == [])
d_nan = KH.sistem_dagilimi([{"Toplam_Hastane_Tuketim_kWh": float("nan"), "Chiller1_kWh": None}])
c("NaN/None degerler cokmez", d_nan["toplam"] == 0)

d_cakisma = KH.sistem_dagilimi([{"Toplam_Hastane_Tuketim_kWh": 100, "Chiller_Tuketim_kWh": 80,
                                 "MCC_Tuketim_kWh": 60}])
c("olculenler toplami asarsa oran >100 raporlanir", d_cakisma["olculen_oran"] > 105)

# ── 3) Teshis — yalnizca olculen degerlerden ─────────────────────────────
r = {"ikinci": 1.76, "degisim": 4.2, "gun": 10, "ort_chiller_yuk": 88}
grup = {"ort_ikinci": 1.52, "ort_sogutma_payi": 20.0}
dag = KH.sistem_dagilimi([{"Toplam_Hastane_Tuketim_kWh": 1000, "Chiller_Tuketim_kWh": 300,
                           "Chiller1_kWh": 220, "Chiller2_kWh": 40, "Chiller3_kWh": 40}])
sev, baslik, m = KH.teshis(r, grup, dag, 1.60, False, "kWh/m²/gün", beklenen_gun=15)
metin = " ".join(m)
c("esik ustu -> uyari", sev == "uyari" and "üzerinde" in baslik, (sev, baslik))
c("hedefe gore fark yuzdesi", "%10.0 üzerinde" in metin, metin)
c("grup ortalamasina gore", "Grup ortalamasının" in metin)
c("onceki donem", "▲%4.2" in metin)
c("chiller dengesizligi tespit", "CH-1" in metin and "dengesiz" in metin, metin)
c("yuksek chiller yuku", "%88" in metin)
c("eksik gun uyarisi", "15 günün 10'inde" in metin, metin)
sev2, _, m2 = KH.teshis({"ikinci": 1.40, "degisim": None, "gun": 15}, grup,
                        KH.sistem_dagilimi([]), 1.60, False, "kWh/m²/gün", beklenen_gun=15)
c("esik alti -> normal", sev2 == "normal")
c("dengeli/verisiz durumda gereksiz madde yok",
  not any(("dengesiz" in x) or ("eksik" in x) for x in m2), m2)
sev3, _, _ = KH.teshis({"ikinci": 30.0, "gun": 5}, {}, KH.sistem_dagilimi([]), 33.0, True, "%")
c("kojen hedef alti -> uyari", sev3 == "uyari")
sev4, baslik4, _ = KH.teshis({"ikinci": 1.5, "gun": 5}, {}, KH.sistem_dagilimi([]), None, False, "x")
c("esik tanimsiz -> bilgi", sev4 == "bilgi" and "tanımlı değil" in baslik4)

# ── 4) Lokasyon durumu ───────────────────────────────────────────────────
simdi = datetime(2026, 9, 16, 12, 0)
c("ping yok -> Kurulmadi", KH.lokasyon_durumu({}, simdi)["baglanti"] == "Kurulmadı")
c("2 dk once -> Cevrimici",
  KH.lokasyon_durumu({"ping_zamani": "2026-09-16T11:58:00+03:00"}, simdi)["baglanti"] == "Çevrimiçi")
c("UTC ping dogru cevrilir (08:58Z = 11:58 IST)",
  KH.lokasyon_durumu({"ping_zamani": "2026-09-16T08:58:00Z"}, simdi)["baglanti"] == "Çevrimiçi")
c("3 saat once -> Cevrimdisi (3 saat)",
  KH.lokasyon_durumu({"ping_zamani": "2026-09-16T09:00:00+03:00"}, simdi)["baglanti"]
  == "Çevrimdışı (3 saat)")
ld = KH.lokasyon_durumu({"ping_zamani": "2026-09-16T11:59:00+03:00",
                         "bakim_ozet": '{"toplam_ariza": 2, "toplam_bakim": 1, '
                                       '"oto": {"metin": "Bekliyor", "dogrulama": {"metin": "uyguladı"}}}'},
                        simdi)
c("bakim_ozet string JSON cozulur", (ld["ariza"], ld["bakim"]) == (2, 1), ld)
c("oto-set ve dogrulama metni", ld["oto_metin"] == "Bekliyor" and ld["dogrulama"] == "uyguladı", ld)
c("bozuk bakim_ozet cokmez", KH.lokasyon_durumu({"bakim_ozet": "{bozuk"}, simdi)["ariza"] == 0)

# ── 5) Simulasyon verisi: kirilim tutarliligi ────────────────────────────
V = S.veri_uret()
en = V["energy_data"]
c("tum satirlarda chiller kirilimi toplami = Chiller_Tuketim_kWh",
  all(sum(v for k, v in r.items() if re.match(r"^Chiller\d+_kWh$", k)) == r["Chiller_Tuketim_kWh"]
      for r in en))
c("tum satirlarda MCC panolari toplami = MCC_Tuketim_kWh",
  all(sum(v for k, v in r.items() if re.match(r"^MCC\d+_kWh$", k)) == r["MCC_Tuketim_kWh"]
      for r in en))
c("chiller + VRF + MCC + kule + diger = toplam (tasma yok)",
  all(r["Chiller_Tuketim_kWh"] + r["VRF_Split_Tuketim_kWh"] + r["MCC_Tuketim_kWh"]
      + sum(v for k, v in r.items() if k.startswith("Kule")) + r["Diger_Yuk_kWh"]
      <= r["Toplam_Hastane_Tuketim_kWh"] for r in en))
c("negatif kirilim yok",
  all(v >= 0 for r in en for k, v in r.items() if re.match(r"^(Chiller|Kule|MCC)\d+_kWh$", k)))
_adet = {r["lokasyon_id"]: r["Chiller_Adet"] for r in en}
c("kucuk hastane (Adana Ort. 5000 m2) 2 chiller", _adet.get("adana_ortopedia") == 2, _adet.get("adana_ortopedia"))
c("buyuk hastane (Atakent 20000 m2) 5 chiller", _adet.get("atakent") == 5, _adet.get("atakent"))
import json as _j
_hedef = _j.loads(next(a["value"] for a in V["ayarlar"] if a["key"] == "hedef_esikleri"))
c("hedef esikleri 5 metrigin hepsi icin var",
  set(_hedef) == {"enerji", "dogalgaz", "sogutma", "su", "kojen"}, _hedef)

# ── 6) Demo sayfasi butunlugu ve CANLI SAYFANIN DOKUNULMAZLIGI ───────────
_demo = open(os.path.join(BURASI, "sunum", "ozet_karsilastirma_demo.py"), encoding="utf-8").read()
# Streamlit pages/ altindaki her dosyayi kenar menusune ekler; demo sayfasi
# orada olursa CANLI portalin menusunde gorunur.
c("demo sayfasi pages/ altinda DEGIL (canli menude gorunmez)",
  not os.path.exists(os.path.join(BURASI, "pages", "ozet_karsilastirma_demo.py")))
_canli = open(os.path.join(BURASI, "pages", "ozet_karsilastirma.py"), encoding="utf-8").read()
_merkez = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
ast.parse(_demo)
c("demo sayfasi sozdizimi gecerli", True)


def _metrikler(metin):
    m = re.search(r"^METRIKLER\s*=\s*(\{.*?^\})", metin, re.S | re.M)
    return ast.literal_eval(m.group(1)) if m else None


c("demo ve canli sayfa AYNI metrik tanimlarini kullanir", _metrikler(_demo) == _metrikler(_canli))
# Detay penceresi artik CANLIDA DA var (once yalnizca demodaydi); ikisi de
# ayni ortak modulu kullanmali, govdesi kopyalanmamali.
for _tur, _metin in (("canli", _canli), ("demo", _demo)):
    c("[%s] tiklama/detay penceresi bagli" % _tur,
      "on_select" in _metin and "st.dialog" in _metin and "karsilastirma_hesap" in _metin)
    c("[%s] pencere govdesi ortak modulden" % _tur,
      "karsilastirma_panel" in _metin and _metin.count("panel_govde") == 1)
c("merkez demo sayfasini YALNIZCA demo modunda secer",
  re.search(r'"sunum", "ozet_karsilastirma_demo\.py"\)\s*if _demo_modu\(\) else\s*'
            r'os\.path\.join\(os\.path\.dirname\(__file__\), "pages", "ozet_karsilastirma\.py"\)',
            _merkez) is not None)
# Detay penceresi canliya da geldigi icin 10 sn'lik yenileme karsilastirma
# sayfasinda DEMO/CANLI ayrimi olmadan durdurulur; yoksa pencere kendiliginden
# kapaniyor (kullanici: "10 sn sonra kayboluyor").
_ar_kosul = _merkez.split("st_autorefresh(interval")[0].split("from streamlit_autorefresh")[-1]
c("karsilastirma sayfasinda otomatik yenileme durur",
  'not st.session_state.get("detay_ozet")' in _ar_kosul, _ar_kosul[-200:])
c("yenileme durdurma demo moduna bagli DEGIL",
  "SYNAPSE_DEMO" not in _ar_kosul, _ar_kosul[-200:])
c("giris ekraninda yenileme yok (yazilan parola silinmesin)",
  'st.session_state.get("giris_ok")' in _ar_kosul)
c("QR bakim sayfasinda yenileme yok", '"bakim" not in st.query_params' in _ar_kosul)
_rapor = open(os.path.join(BURASI, "pages", "rapor_olustur.py"), encoding="utf-8").read()
c("rapor sayfasi demo modunda ornek veri sunucusunu kullanir", "_sim_sunucu.sunucu_baslat" in _rapor)
# Aciklama (docstring) ve yorum satirlari haric tutulur: orada "bilerek
# eklenmedi" diye ANILIYORLAR; aranan, ekranda GOSTERILIP gosterilmedigi.
_kod = re.sub(r'^""".*?"""', "", _demo, count=1, flags=re.S | re.M)
_kod = "\n".join(s for s in _kod.splitlines() if not s.lstrip().startswith("#"))
c("demo sayfasi Gemini'deki UYDURMA kalemleri ekranda GOSTERMEZ",
  not re.search(r"OSOS|BEDA|WeasyPrint|Medikal|COP\b|Aydınlatma", _kod),
  re.findall(r"OSOS|BEDA|WeasyPrint|Medikal|COP\b|Aydınlatma", _kod))

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d_ in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d_,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
