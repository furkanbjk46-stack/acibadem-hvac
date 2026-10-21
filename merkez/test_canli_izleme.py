# -*- coding: utf-8 -*-
"""Canlı izleme sekmesi — seri yönetimi ve grafik (ag baglantisi YOK).

Sekme, sahadan gelen ANLIK kW degerini kayan bir pencerede biriktirir.
Geçmiş hiçbir yerde saklanmaz (kullanıcı kararı 20.10.2026: Supabase
şişmesin) — seri yalnızca merkezin oturumunda yaşar. Dolayısıyla serinin
doğruluğu tamamen buradaki saf fonksiyonlara bağlı:

  · aynı ölçüm iki kez eklenirse grafik yanlış yoğunluk gösterir
  · pencereden çıkan nokta atılmazsa bellek sınırsız büyür
  · okunamayan sayaç 0 sayılırsa "tüketim düştü" gibi görünür — oysa
    veri yoktur; çizgide BOŞLUK kalmalıdır
"""
import os
import sys
from datetime import datetime, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import canli_izleme as CI  # noqa: E402

SAYFA = open(os.path.join(BURASI, "pages", "lokasyon_detay.py"), encoding="utf-8").read()
PANEL = open(os.path.join(BURASI, "karsilastirma_panel.py"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


T0 = datetime(2026, 10, 20, 21, 0, 0)


def olcum(sn, **kw):
    """sn saniye sonraki ölçüm; kw = {cihaz: deger}"""
    t = (T0 + timedelta(seconds=sn)).isoformat()
    return [{"cihaz": ad, "kw": v, "olcum_zamani": t} for ad, v in kw.items()]


# ── 1) Seri birikmesi ────────────────────────────────────────────────────
s = CI.bos_seri()
c("boş seri", s["zamanlar"] == [] and s["cihazlar"] == {})

s = CI.seri_guncelle(s, olcum(0, **{"TRDP-1": 400.0, "TRDP-2": 300.0}), 300)
c("ilk ölçüm eklendi", len(s["zamanlar"]) == 1 and s["cihazlar"]["TRDP-1"] == [400.0])

s = CI.seri_guncelle(s, olcum(15, **{"TRDP-1": 410.0, "TRDP-2": 305.0}), 300)
c("ikinci ölçüm eklendi", len(s["zamanlar"]) == 2, s["zamanlar"])
c("değerler sırayla birikiyor", s["cihazlar"]["TRDP-1"] == [400.0, 410.0])

# AYNI ölçüm tekrar gelirse (ekran sahadan hızlı yeniliyor) eklenmemeli
s = CI.seri_guncelle(s, olcum(15, **{"TRDP-1": 410.0, "TRDP-2": 305.0}), 300)
c("aynı zaman damgası iki kez eklenmiyor", len(s["zamanlar"]) == 2, s["zamanlar"])

# Geriye giden zaman damgası da eklenmemeli
s = CI.seri_guncelle(s, olcum(5, **{"TRDP-1": 999.0}), 300)
c("eski zaman damgası eklenmiyor", len(s["zamanlar"]) == 2
  and 999.0 not in s["cihazlar"]["TRDP-1"], s["cihazlar"]["TRDP-1"])

# Boş ölçüm seriyi bozmamalı
s2 = CI.seri_guncelle(s, [], 300)
c("boş ölçüm seriyi bozmuyor", s2["zamanlar"] == s["zamanlar"])
s2 = CI.seri_guncelle(s, None, 300)
c("None ölçüm seriyi bozmuyor", s2["zamanlar"] == s["zamanlar"])

# ── 2) Okunamayan sayaç ──────────────────────────────────────────────────
s = CI.seri_guncelle(s, olcum(30, **{"TRDP-1": None, "TRDP-2": 310.0}), 300)
c("okunamayan değer None olarak giriyor (0 DEĞİL)",
  s["cihazlar"]["TRDP-1"][-1] is None, s["cihazlar"]["TRDP-1"])
c("diğer sayaç etkilenmiyor", s["cihazlar"]["TRDP-2"][-1] == 310.0)
c("grafik boşlukları birleştirmiyor (satır grafiğinde ölçüldü)",
  CI.kivrim_svg([10.0, 11.0, None, 14.0, 15.0]).count("polyline") == 2)

# Sonradan görünen cihaz: geçmişi uydurulmamalı, hizalama bozulmamalı
s = CI.seri_guncelle(s, olcum(45, **{"TRDP-1": 420.0, "TRDP-2": 315.0,
                                     "TRDP-3": 120.0}), 300)
n = len(s["zamanlar"])
c("tüm diziler aynı uzunlukta", all(len(v) == n for v in s["cihazlar"].values()),
  {k: len(v) for k, v in s["cihazlar"].items()})
c("yeni cihazın geçmişi boş (uydurulmadı)",
  s["cihazlar"]["TRDP-3"][:-1] == [None] * (n - 1), s["cihazlar"]["TRDP-3"])

# ── 3) Pencere — eskiler atılmalı ────────────────────────────────────────
s = CI.bos_seri()
for i in range(40):                       # 40 × 15 sn = 10 dakika
    s = CI.seri_guncelle(s, olcum(i * 15, **{"TRDP-1": 400.0 + i}), 300,
                         simdi=T0 + timedelta(seconds=i * 15))
sure = (s["zamanlar"][-1] - s["zamanlar"][0]).total_seconds()
c("pencere 5 dakikayı aşmıyor", sure <= 300, sure)
c("nokta sayısı sınırlı (bellek büyümüyor)", len(s["zamanlar"]) <= 21,
  len(s["zamanlar"]))
c("en yeni nokta korunuyor", s["cihazlar"]["TRDP-1"][-1] == 439.0)
c("tüm diziler pencereyle birlikte kısaldı",
  all(len(v) == len(s["zamanlar"]) for v in s["cihazlar"].values()))

# Pencere büyütülünce eski noktalar atılmaz
s_genis = CI.bos_seri()
for i in range(40):
    s_genis = CI.seri_guncelle(s_genis, olcum(i * 15, **{"TRDP-1": 400.0 + i}), 900,
                               simdi=T0 + timedelta(seconds=i * 15))
c("15 dakikalık pencere daha çok nokta tutuyor",
  len(s_genis["zamanlar"]) > len(s["zamanlar"]), len(s_genis["zamanlar"]))

# ── 4) Özet değerler ─────────────────────────────────────────────────────
s = CI.bos_seri()
s = CI.seri_guncelle(s, olcum(0, **{"TRDP-1": 400.0, "TRDP-2": 300.0}), 300)
s = CI.seri_guncelle(s, olcum(15, **{"TRDP-1": 410.5, "TRDP-2": None}), 300)
son = CI.son_degerler(s)
c("son değer okunuyor", son["TRDP-1"] == 410.5, son)
c("son değer None ise bir öncekine düşüyor", son["TRDP-2"] == 300.0, son)
c("toplam hesaplanıyor", CI.toplam(son) == 710.5, CI.toplam(son))
c("hiç değer yoksa toplam None", CI.toplam({"a": None}) is None)
c("boş sözlükte toplam None", CI.toplam({}) is None)

# ── 5) Satır grafiği (SVG) ───────────────────────────────────────────────
# 27 cihaz icin 27 Plotly grafigi agirdi; satir grafigi duz SVG uretilir.
bos = CI.kivrim_svg([])
c("veri yokken kesik çizgi (sahte değer yok)",
  "stroke-dasharray" in bos and "polyline" not in bos, bos[:90])
c("boş seride de yükseklik korunuyor (satırlar kaymasın)", "height:26px" in bos)

dolu = CI.kivrim_svg([10.0, 12.0, 11.0, 14.0])
c("dolu seri çizgi üretiyor", dolu.count("polyline") == 1, dolu[:120])
c("çizgi verilen renkte", CI.kivrim_svg([1.0, 2.0], renk="#abcdef").count("#abcdef") == 1)

c("boşluk çizgiyi KOPARIYOR (uydurma bağlantı yok)",
  CI.kivrim_svg([10.0, 11.0, None, 14.0, 15.0]).count("polyline") == 2)
c("tek nokta da görünür", CI.kivrim_svg([None, 12.0, None]).count("polyline") == 1)
c("düz seri çökmüyor (sıfıra bölme yok)",
  CI.kivrim_svg([7.0, 7.0, 7.0]).count("polyline") == 1)

# Her cihaz KENDI araligina olceklenir: kucuk sayacin hareketi de gorunur
k_buyuk = CI.kivrim_svg([800.0, 900.0, 850.0])
k_kucuk = CI.kivrim_svg([4.0, 5.0, 4.5])
c("küçük sayacın hareketi de görünüyor (kendi ölçeğinde)",
  k_buyuk.count("polyline") == 1 and k_kucuk.count("polyline") == 1)

# ── 6) Gruplama ──────────────────────────────────────────────────────────
_c = ["TRDP-1", "TRDP-4", "CHILLER-1", "KULE-2", "MCC-3", "2BK-MCC-D01",
      "CK-MCC-F01", "4BK-MCC-E02"]
_g = dict((a, c_) for a, _b, c_ in CI.gruplara_ayir(_c))
c("trafolar enerji grubunda", _g["enerji"] == ["TRDP-1", "TRDP-4"], _g.get("enerji"))
c("chiller ve kule soğutmada", _g["sogutma"] == ["CHILLER-1", "KULE-2"], _g.get("sogutma"))
c("ana ve blok panoları MCC'de", len(_g["mcc"]) == 4, _g.get("mcc"))
c("grup sırası sabit", [a for a, _, _ in CI.gruplara_ayir(_c)] == ["enerji", "sogutma", "mcc"])
c("boş grup gösterilmiyor", len(CI.gruplara_ayir(["TRDP-1"])) == 1)

# Tanimsiz cihaz KAYBOLMAZ — yeni sayac eklenince sessizce dusmesin
_gd = CI.gruplara_ayir(["TRDP-1", "YENI-SAYAC-9"])
c("gruplanmamış cihaz DİĞER'e düşüyor",
  any(a == "diger" and c_ == ["YENI-SAYAC-9"] for a, _b, c_ in _gd), _gd)
c("her cihaz bir gruba giriyor",
  sum(len(c_) for _a, _b, c_ in CI.gruplara_ayir(_c)) == len(_c))

# Sira: ana panolar once, bloklar sonra; sayilar SAYISAL sirada
_m = dict((a, c_) for a, _b, c_ in
          CI.gruplara_ayir(["CK-MCC-F01", "MCC-10", "MCC-2", "2BK-MCC-D01", "MCC-1"]))["mcc"]
c("ana panolar blok panolarından önce", _m[:3] == ["MCC-1", "MCC-2", "MCC-10"], _m)
c("MCC-10 MCC-2'den SONRA (sayısal sıra)", _m.index("MCC-10") > _m.index("MCC-2"), _m)
_sg = dict((a, c_) for a, _b, c_ in
           CI.gruplara_ayir(["CHILLER-5", "CH-1", "KULE-2"]))["sogutma"]
c("CH-1 ile CHILLER-5 aynı ailede sıralanıyor", _sg[:2] == ["CH-1", "CHILLER-5"], _sg)

# Cizgi renkleri DURUM rengi olmamali: bu portalda yesil/turuncu/kirmizi
# iyi/uyari/kritik demek. Saglam sayac sorunluymus gibi gorunmesin.
_durum_renkleri = {"#0ca30c", "#fab219", "#c98500", "#d03b3b", "#ec835a"}
c("satır çizgilerinde durum rengi kullanılmıyor",
  not (set(CI.CIZGI_RENKLERI) & _durum_renkleri), CI.CIZGI_RENKLERI)
c("renk cihaza göre sabit",
  CI.renk("MCC-3", ["MCC-1", "MCC-3"]) == CI.renk("MCC-3", ["MCC-1", "MCC-3"]))

c("CHILLER-1 ekranda CH-1", CI.kisa_ad("CHILLER-1") == "CH-1")
c("kısaltma veri adını değiştirmiyor", CI.kisa_ad("MCC-3") == "MCC-3")

# Grup toplami: yalnizca o grubun okunan cihazlari
_s = CI.bos_seri()
_s = CI.seri_guncelle(_s, olcum(0, **{"TRDP-1": 400.0, "TRDP-2": 300.0,
                                      "CHILLER-1": 50.0}), 300)
c("grup toplamı yalnız o grubu sayıyor",
  CI.grup_toplami(_s, ["TRDP-1", "TRDP-2"]) == 700.0,
  CI.grup_toplami(_s, ["TRDP-1", "TRDP-2"]))
c("okunamayan cihaz toplamı bozmuyor",
  CI.grup_toplami(_s, ["TRDP-1", "YOK"]) == 400.0)
c("hiç okunan yoksa toplam None", CI.grup_toplami(_s, ["YOK"]) is None)

# Satir ve grup govdesi
_sat = CI.satir_html("CHILLER-1", 117.4, "<svg/>", "register")
c("satırda kısa ad", ">CH-1<" in _sat, _sat[:120])
c("satırda değer", "117,4" in _sat)
c("satırda yöntem ipucu", "sayaçla doğrulandı" in _sat)
_sat_yok = CI.satir_html("MCC-5", None, "<svg/>", None)
c("okunamayan satır 0 YAZMIYOR", "okunamadı" in _sat_yok and "0,0" not in _sat_yok)

_gh = CI.grup_html("MCC YÜKÜ", "açıklama", "<i></i>", 456.2, 14, 15)
c("grup başlığında toplam", "456,2 kW" in _gh)
c("grup dibinde okunan sayaç", "14/15 sayaç okunuyor" in _gh)
c("liste kaydırmalı (uzun liste kartı taşırmasın)",
  "max-height:430px" in _gh and "overflow-y:auto" in CI.STIL)

# ── 7) Yöntem özeti — tahmin, ölçüm gibi gösterilmesin ───────────────────
metin, _ = CI.yontem_ozeti([{"cihaz": "TRDP-1", "yontem": "register"},
                            {"cihaz": "TRDP-2", "yontem": "register"}])
c("hepsi doğrulanmışsa tek satır", "sayaçla doğrulandı" in metin, metin)
metin, renk_ = CI.yontem_ozeti([{"cihaz": "TRDP-1", "yontem": "register"},
                                {"cihaz": "TRDP-2", "yontem": "sayac"}])
c("karışık yöntemde cihaz bazında yazıyor",
  "TRDP-2" in metin and "sayaç farkından" in metin, metin)
c("karışık yöntem uyarı renginde", renk_ == "#c98500")
c("boş ölçümde metin yok", CI.yontem_ozeti([])[0] == "")

# ── 8) Durum metni ───────────────────────────────────────────────────────
c("veri yokken beklendiği söyleniyor",
  "bekleniyor" in CI.durum_metni(CI.bos_seri()))
d = CI.durum_metni(s, yas_sn=4, pencere_sn=300)
c("pencere dolarken bu söyleniyor", "pencere doluyor" in d, d)
c("son ölçüm yaşı yazılıyor", "4 sn önce" in d, d)

s_dolu = CI.bos_seri()
for i in range(25):
    s_dolu = CI.seri_guncelle(s_dolu, olcum(i * 15, **{"TRDP-1": 400.0}), 300,
                              simdi=T0 + timedelta(seconds=i * 15))
c("pencere dolunca süre yazıyor", "son 5 dakika" in CI.durum_metni(s_dolu, 3, 300),
  CI.durum_metni(s_dolu, 3, 300))

# ── 9) Sayfaya bağlanma ──────────────────────────────────────────────────
c("sekme 2. sırada", '"📊 Dashboard", "⚡ Canlı İzleme"' in SAYFA)
c("sekme gövdesi var", "with tab_canli:" in SAYFA)
c("canlı veri çekiliyor", "fetch_canli_guc(url, key, lok_id)" in SAYFA)
c("seri oturumda tutuluyor", "st.session_state[_seri_anahtar] = seri" in SAYFA)
c("seri lokasyona göre ayrı", '"canli_seri_" + str(lok_id)' in SAYFA)
c("kendi kendine yenileniyor", '@st.fragment(run_every="3s")' in SAYFA)
c("pencere seçimi fragment DIŞINDA (seçim elden kaymasın)",
  SAYFA.index('key="canli_pencere"') < SAYFA.index('@st.fragment(run_every="3s")'))
c("sayaç yoksa açıklanıyor", "canlı sayaç okuması yok" in SAYFA)
c("satırlar modülden üretiliyor (sayfada kopya HTML yok)",
  "_CI.satir_html(" in SAYFA and "_CI.grup_html(" in SAYFA
  and "_CI.kivrim_svg(" in SAYFA)
c("gruplama modülden", "_CI.gruplara_ayir(" in SAYFA)
c("stil tek yerden", "_CI.STIL" in SAYFA and "cg-grup" not in SAYFA)

# Pencere (detay pop-up'ı) artık canlı veri göstermiyor — sıkışıklık giderildi
c("detay penceresinden canlı blok kaldırıldı", "canli" not in PANEL)
c("detay penceresi iki sütunu da dönem verisiyle kullanıyor",
  "ENERJİ KAYNAĞI" in PANEL and "SİSTEM DURUMU" in PANEL)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
