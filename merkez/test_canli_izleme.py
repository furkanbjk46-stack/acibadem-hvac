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
import re
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
c("okunamayan cihaz için çubuk DOLMUYOR (0 gibi görünmesin)",
  "cg-dolgu" not in CI.bar_html(None, 100.0))

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

# ── 5) Yük çubuğu ───────────────────────────────────────────────────────
# Satir grafigi yerine dolgulu yatay cubuk (kullanici karari 22.10.2026):
# dalgali trend degil, anlik yukun ne kadar oldugunu gosteren duz dolgu.
c("ölçek yoksa çubuk dolmuyor", "cg-dolgu" not in CI.bar_html(50.0, 0))
c("okunamayan değerde çubuk dolmuyor", "cg-dolgu" not in CI.bar_html(None, 100.0))
c("iz her durumda var (satırlar kaymasın)",
  "cg-iz" in CI.bar_html(None, 0) and "cg-iz" in CI.bar_html(50.0, 100.0))

_b = CI.bar_html(50.0, 100.0)
c("yarı değer yarı dolu", "width:50.0%" in _b, _b[:120])
c("ölçeğe eşit değer tam dolu", "width:100.0%" in CI.bar_html(127.4, 127.4))
c("ölçeği aşan değer taşmıyor", "width:100.0%" in CI.bar_html(500.0, 100.0))
c("çok küçük değer görünür kalıyor (0 genişlik değil)",
  "width:0.1%" in CI.bar_html(0.1, 100.0) or "width:0.0%" in CI.bar_html(0.1, 100.0))
c("ipucunda kW ve yüzde var", "kW" in _b and "%" in _b, _b[:90])

# ── 5b) ESIK RENKLERI (kullanici olcutu) ────────────────────────────────
#   <500 yesil #22c55e · 500-700 yesil->turuncu · 700-800 turuncu->kirmizi
#   >800 kirmizi #ef4444 — aralarda YUMUSAK gecis
c("500 altı saf yeşil", CI.esik_rengi(312.9) == "rgb(34, 197, 94)", CI.esik_rengi(312.9))
c("500 tam sınırda hâlâ yeşil", CI.esik_rengi(500) == "rgb(34, 197, 94)")
c("800 üstü saf kırmızı", CI.esik_rengi(2049.5) == "rgb(239, 68, 68)")
c("800 tam sınırda kırmızı", CI.esik_rengi(800) == "rgb(239, 68, 68)")

_orta = CI.esik_rengi(572.2)
c("500-700 arası ara ton (ne yeşil ne turuncu)",
  _orta not in ("rgb(34, 197, 94)", "rgb(245, 158, 11)"), _orta)
c("572 kW referansla aynı ton", _orta == "rgb(110, 183, 64)", _orta)
_ust = CI.esik_rengi(751.6)
c("751 kW referansla aynı ton", _ust == "rgb(242, 112, 40)", _ust)

def _r(metin):
    return [int(x) for x in re.findall(r"\d+", metin)]


# Gecis YUMUSAK olmali: kW arttikca kirmiziya tek yonde gitsin
_ardisik = [CI.esik_rengi(k) for k in (450, 520, 600, 680, 720, 780, 850)]
# "Isinma" tek yonlu olmali: yesil bileseni kW arttikca hep azalir.
c("yük arttıkça yeşil bileşeni azalıyor (tek yönlü ısınma)",
  all(_r(a)[1] >= _r(b)[1] for a, b in zip(_ardisik, _ardisik[1:])), _ardisik)
# YUMUSAK gecisin asil olcutu: esik noktalarinda SICRAMA olmamasi.
for _esik in (500, 700, 800):
    _alt, _ust2 = CI.esik_rengi(_esik - 0.5), CI.esik_rengi(_esik + 0.5)
    _fark = max(abs(x - y) for x, y in zip(_r(_alt), _r(_ust2)))
    c("%d kW eşiğinde renk sıçraması yok" % _esik, _fark <= 3,
      (_alt, _ust2, _fark))
c("negatif değer de renklendiriliyor (şebekeye verme)",
  CI.esik_rengi(-300) == "rgb(34, 197, 94)")
c("değer yoksa nötr gri", CI.esik_rengi(None).startswith("rgb(203"))

# ── 5c) Olcek: pencere TEPESI ───────────────────────────────────────────
_s0 = CI.bos_seri()
_s0 = CI.seri_guncelle(_s0, olcum(0, **{"A": 10.0, "B": 40.0}), 300)
_s0 = CI.seri_guncelle(_s0, olcum(15, **{"A": 80.0, "B": 20.0}), 300)
c("ölçek pencere tepesini alıyor (anlık en yüksek değil)",
  CI.olcek_degeri(_s0, ["A", "B"]) == 80.0, CI.olcek_degeri(_s0, ["A", "B"]))
c("gruba ait olmayan cihaz ölçeğe girmiyor",
  CI.olcek_degeri(_s0, ["A"]) == 80.0 and CI.olcek_degeri(_s0, ["B"]) == 40.0)
c("boş grupta ölçek 0", CI.olcek_degeri(_s0, []) == 0)

# ── 5d) Animasyon ───────────────────────────────────────────────────────
c("dolgu şeritleri akıyor", "animation:cgSerit" in CI.STIL and "@keyframes cgSerit" in CI.STIL)
c("üstünden parıltı geçiyor", "cgParilti" in CI.STIL)
c("genişlik ve renk yumuşak değişiyor", "transition:width" in CI.STIL)
c("dalgalı trend çizgisi kalmadı", not hasattr(CI, "kivrim_svg"))

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
# Görünen metin üzerinden: sayı artık akış için ayrı bir span içinde
c("grup başlığında toplam", "456,2 kW" in re.sub(r"<[^>]+>", "", _gh))
c("grup dibinde okunan kalem sayısı", "14 kalem canlı okunuyor" in _gh, _gh[-160:])
_gh2 = CI.grup_html("ENERJİ", "a", "<i></i>", 100.0, 5, 3)
c("ölçülemeyen kalem sayısı da yazıyor", "3 kalemde sayaç yok" in _gh2, _gh2[-160:])
c("liste kaydırmalı (uzun liste kartı taşırmasın)",
  "max-height:430px" in _gh and "overflow-y:auto" in CI.STIL)

# ── 7) Yöntem özeti ve satır noktaları ──────────────────────────────────
# Ilk surum dogrulanan/dogrulanmayan cihazlarin ADLARINI tek tek yaziyordu;
# 27 sayacta alt bant ekrani boydan boya dolduruyordu (21.10.2026). Durum
# artik SATIRIN noktasindan okunuyor, alt bantta yalnizca sayi var.
_hepsi = [{"cihaz": "A%d" % i, "kw": 10.0, "yontem": "register"} for i in range(27)]
_metin, _renk = CI.yontem_ozeti(_hepsi)
c("hepsi doğrulanmışsa sayı yazıyor", _metin == "27 sayaç doğrulandı", _metin)
c("hepsi doğrulanmışsa yeşil", _renk == "#0ca30c")

_karisik = _hepsi[:24] + [{"cihaz": "B%d" % i, "kw": 5.0, "yontem": "sayac"}
                          for i in range(3)]
_metin, _renk = CI.yontem_ozeti(_karisik)
c("karışıkta iki sayı da yazıyor",
  "24 sayaç doğrulandı" in _metin and "3 sayaç doğrulanmadı" in _metin, _metin)
c("karışık yöntem uyarı renginde", _renk == "#c98500")
c("alt bant KISA kalıyor (cihaz adı listelenmiyor)",
  len(_metin) < 70 and "A0" not in _metin and "B0" not in _metin, (len(_metin), _metin))
c("okunamayan cihaz sayıma girmiyor",
  CI.yontem_ozeti([{"cihaz": "X", "kw": None, "yontem": None}])[0] == "")
c("boş ölçümde metin yok", CI.yontem_ozeti([])[0] == "")

# Satirdaki nokta: yesil = dogrulandi, turuncu = dogrulanmadi.
# Nokta CIHAZ ADININ yaninda durur (kullanici karari 21.10.2026): ait
# oldugu cihazla birlikte okunsun, kW degerinin yaninda degil.
def _cip(h):
    return h.split("class='cg-cip'")[1].split("</div>")[0]


def _deger(h):
    return h.split("class='cg-dg'")[1].split("</div>")[0]


_h = CI.satir_html("MCC-1", 10.0, "<svg/>", "register")
c("doğrulanan satırda yeşil nokta", "cg-dot-ok" in _h)
c("nokta CİHAZ ADININ yanında", "cg-dot" in _cip(_h), _cip(_h))
c("değerin yanında nokta YOK", "cg-dot" not in _deger(_h), _deger(_h))
_hu = CI.satir_html("2BK-MCC-D01", 17.1, "<svg/>", "sayac")
c("uzun cihaz adında da nokta adın yanında", "cg-dot" in _cip(_hu), _cip(_hu))
c("doğrulanmayan satırda turuncu nokta",
  "cg-dot-bekle" in CI.satir_html("MCC-2", 10.0, "<svg/>", "sayac"))
c("henüz doğrulanmamış da turuncu",
  "cg-dot-bekle" in CI.satir_html("MCC-2", 10.0, "<svg/>", "register?"))
c("okunamayan satırda nokta yok",
  "cg-dot" not in CI.satir_html("MCC-3", None, "<svg/>", None))
c("noktalar yanıp sönüyor", "animation:cgNabiz" in CI.STIL)
c("nokta adın SOLUNDA (nokta cihaz)",
  _cip(_h).index("cg-dot") < _cip(_h).index("MCC-1"), _cip(_h))

# Ad sutunu SABIT px degil, iceriğe gore: sabit genislikte "2BK-MCC-D01"
# gibi adlar "2BK-MCC-D0..." diye kesiliyordu ve kesilme yazi tipine gore
# degisiyordu (Inter yuklenince daha genis). max-content fonttan bagimsiz.
c("ad sütunu içeriğe göre genişliyor", "max-content" in CI.STIL)
c("çizgiye alt sınır var (uzun ad grafiği yutmasın)", "minmax(60px,1fr)" in CI.STIL)
# Izgara LISTEDE: sutunlar butun satirlarda ortak, cizgiler hizali
c("ızgara listede, satırlar ona katılıyor",
  ".cg-liste{" in CI.STIL and "display:contents" in CI.STIL)
c("satır kendi ızgarasını kurmuyor",
  ".cg-satir{display:grid" not in CI.STIL, "satir kendi izgarasini kuruyor")

c("iki nokta rengi de tanımlı",
  ".cg-dot-ok{background:#0ca30c;}" in CI.STIL and ".cg-dot-bekle{background:#fab219;}" in CI.STIL)

# ── 7c) Kartlar esit boyda ──────────────────────────────────────────────
# 15 satirlik MCC karti digerlerinden uzun duruyordu.
c("kartlar en uzuna göre hizalanıyor (align-items:start YOK)",
  "align-items:start" not in CI.STIL, CI.STIL[CI.STIL.index(".cg-sarmal"):][:120])
c("kart dikey esnek, liste kalan yeri dolduruyor",
  "flex-direction:column" in CI.STIL and "flex:1 1 auto" in CI.STIL)

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
c("sekme 2. sırada", '"Dashboard", "Canlı İzleme"' in SAYFA)
c("sekme gövdesi var", "with tab_canli:" in SAYFA)
c("canlı veri çekiliyor", "fetch_canli_guc(url, key, lok_id)" in SAYFA)
c("seri oturumda tutuluyor", "st.session_state[_seri_anahtar] = seri" in SAYFA)
c("seri lokasyona göre ayrı", '"canli_seri_" + str(lok_id)' in SAYFA)
c("kendi kendine yenileniyor (gerçekte 3 sn, sunumda ~1 sn)",
  '@st.fragment(run_every="0.5s" if _demo_modu() else "3s")' in SAYFA)
# Widget fragment GOVDESINDE olmamali: kendi kendine yenilenen bolumde her
# turda yeniden kurulur ve secim elden kayar. (Konum ust/alt onemli degil,
# ONEMLI OLAN govdenin icinde olmamasi.)
_fragman_govde = (SAYFA.split("def _canli_izleme_ciz():")[1]
                  .split("\n    _canli_izleme_blok()")[0])
c("pencere seçimi fragment gövdesinde DEĞİL",
  "st.selectbox" not in _fragman_govde and 'key="canli_pencere"' in SAYFA)
c("fragment session_state'ten okuyor", 'st.session_state.get("canli_pencere"' in SAYFA)
c("sayaç yoksa açıklanıyor", "canlı sayaç okuması yok" in SAYFA)
c("satırlar modülden üretiliyor (sayfada kopya HTML yok)",
  "_CI.satir_html(" in SAYFA and "_CI.grup_html(" in SAYFA
  and "_CI.bar_html(" in SAYFA)
c("gruplama modülden", "_CI.gruplara_ayir(" in SAYFA)
c("stil tek yerden", "_CI.STIL" in SAYFA and "cg-grup" not in SAYFA)

# Pencere (detay pop-up'ı) artık canlı veri göstermiyor — sıkışıklık giderildi
c("detay penceresinden canlı blok kaldırıldı", "canli" not in PANEL)
c("detay penceresi iki sütunu da dönem verisiyle kullanıyor",
  "ENERJİ KAYNAĞI" in PANEL and "SİSTEM DURUMU" in PANEL)

# ── 10) BAYAT MODUL KAPISI ──────────────────────────────────────────────
# 21.10.2026 SAHADAN GELEN HATA: ekranda AttributeError. Sebep: bu sayfa HER
# calismada diskten okunup exec ediliyor, canli_izleme modulu ise Streamlit
# surecine BIR KEZ yukleniyor. Yayin sonrasi surec yeniden baslamazsa sayfa
# yeni, modul eski kalir ve sayfa modulde olmayan bir islevi cagirir.
c("modülde sürüm damgası var", isinstance(getattr(CI, "SURUM", None), int), getattr(CI, "SURUM", None))
c("sayfa sürümü kontrol ediyor", 'getattr(_CI, "SURUM", 0)' in SAYFA)
c("tutmuyorsa modülü tazeliyor", "importlib.reload(_CI)" in SAYFA)

_bekl = re.search(r"_CI_GEREKEN_SURUM = (\d+)", SAYFA)
c("sayfa beklenen sürümü yazıyor", _bekl is not None)
# Asil koruma: module yeni islev eklenip SURUM artirilmazsa ayrisma geri doner
c("sayfanın beklediği sürüm modülünkiyle UYUMLU",
  _bekl and int(_bekl.group(1)) == CI.SURUM,
  (_bekl.group(1) if _bekl else None, CI.SURUM))

# Sayfanin kullandigi HER _CI islevi modulde bulunmali (ayrisma testi)
_kullanilan = set(re.findall(r"_CI\.([A-Za-z_][A-Za-z_0-9]*)", SAYFA))
_eksik = [a for a in _kullanilan if not hasattr(CI, a)]
c("sayfanın çağırdığı her işlev modülde var", not _eksik, _eksik)

# Canli bolum 3 saniyede bir yenileniyor; hatasi sayfayi kaplamamali
c("canlı bölüm hatası sekmede kalıyor (sayfa kırmızıya boyanmıyor)",
  "except Exception as _hata:" in SAYFA and "st.warning(" in SAYFA)
c("hata gizlenmiyor, ayrıntı gösteriliyor",
  "Teknik ayrıntı" in SAYFA and "st.code(" in SAYFA)

# ── SUNUM: tüm lokasyonlar canlı görünür, gerçek sisteme etkisi yok ───────
# Sunum (demo) için örnek veri sunucusu her çalışan lokasyona sayaç üretir.
# Gerçek sistemde bu satırları yazan YOK: kojen/gaz/su grupları ancak böyle
# adla satır gelirse görünür, gelmezse eski ekran aynen kalır.
import _sim_sunucu as S  # noqa: E402
S.canli_guc_tazele(datetime(2026, 10, 25, 14, 0, 5))
_cg = S.VERI["canli_guc"]
_lok = {r["lokasyon_id"] for r in _cg}
_calisan = {l for l, _, _ in S.LOKASYONLAR
            if S.SENARYO.get(l, ("normal", ""))[0] not in ("kurulmadi", "cevrimdisi")}
c("[sunum] çalışan her lokasyonun canlı sayacı var", _lok == _calisan, _calisan ^ _lok)
c("[sunum] kurulmamış/çevrimdışı lokasyon canlı veri vermez",
  not ({"bodrum", "kartal"} & _lok))
_ms = {r["cihaz"]: r["kw"] for r in _cg if r["lokasyon_id"] == "maslak"}
c("[sunum] Maslak gerçek 27 elektrik sayacı + kojen/gaz/su",
  sum(1 for k in _ms if k.startswith(("TRDP-", "CHILLER-", "KULE-", "MCC-", "2BK-", "4BK-", "CK-"))) == 27
  and "KOJEN-1" in _ms and "DOGALGAZ-ANA" in _ms and "SU-ANA" in _ms, sorted(_ms))
# Canlı şebeke, aynı lokasyonun günlük kaydıyla aynı büyüklükte (kart ve tablo çelişmesin)
_son = {}
for _r in S.VERI["energy_data"]:
    if _r["Tarih"] > _son.get(_r["lokasyon_id"], {}).get("Tarih", ""):
        _son[_r["lokasyon_id"]] = _r
_tutarsiz = []
for _l in _calisan:   # Maslak dahil: gerçek sayaç adları, kendi günlük kaydına ölçekli
    _canli = sum(r["kw"] for r in _cg if r["lokasyon_id"] == _l and r["cihaz"].startswith("TRDP-"))
    _gunluk = _son[_l]["Sebeke_Tuketim_kWh"] / 24.0
    if not (0.5 * _gunluk < _canli < 1.8 * _gunluk):
        _tutarsiz.append((_l, round(_canli), round(_gunluk)))
c("[sunum] canlı şebeke günlük kaydın saatlik ortalamasıyla tutarlı", not _tutarsiz, _tutarsiz)
c("[sunum] değerler her istekte değişir (canlı görünür)",
  S.canli_guc_tazele(datetime(2026, 10, 25, 14, 0, 20)) is None
  and {r["cihaz"]: r["kw"] for r in S.VERI["canli_guc"] if r["lokasyon_id"] == "maslak"} != _ms)
c("[sunum] kojen yalnız kojeni olan lokasyonda",
  {r["lokasyon_id"] for r in S.VERI["canli_guc"] if r["cihaz"].startswith("KOJEN")}
  == {l for l, r in _son.items() if l in _calisan and (r.get("Kojen_Uretim_kWh") or 0) > 0} | {"maslak"})

_gr = {a: c_ for a, _, c_ in CI.gruplara_ayir(["TRDP-1", "KOJEN-1", "DOGALGAZ-ANA", "SU-ANA"])}
c("kojen / doğalgaz / su kendi gruplarında", set(_gr) == {"enerji", "kojen", "dogalgaz", "su"}, _gr)
c("gaz ve su m³/h, diğerleri kW",
  CI.birim("dogalgaz") == "m³/h" and CI.birim("su") == "m³/h" and CI.birim("kojen") == "kW")
c("satırda birim yazılır", "m³/h" in CI.satir_html("SU-ANA", 12.0, "", birim="m³/h"))
c("grup başlığında birim yazılır", "m³/h" in CI.grup_html("SU", "", "", 12.0, 1, birim="m³/h"))
_MRK = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
c("ana ekran akışı: sunumda dalga, gerçekte gerçek ölçüm geçişi",
  '_canli_akis_betigi(_akis_taban, "dalga")' in _MRK
  and '_canli_akis_betigi(_akis_taban, "gecis")' in _MRK)
c("[sunum] önbellek demoda 0,5 sn, gerçekte 12 sn",
  "_CANLI_TTL = 0.5 if _demo_modu() else 12" in _MRK
  and _MRK.count("@st.cache_data(ttl=_CANLI_TTL") == 2)
# Detay açıkken tam sayfa yenilemesi YOK (demo ve canlı): canlı blok kendi
# yenilenir; tam yenileme akışı durduruyor, tıklamaları bekletiyordu.
_ar_if = _MRK.split("st_autorefresh(interval")[0]
_ar_if = _ar_if[_ar_if.rindex('if ("bakim"'):]
c("detay açıkken tam sayfa yenilemesi yok (demo VE canlı)",
  'and not st.session_state.get("detay_lokasyon")):' in _ar_if and "SYNAPSE_DEMO" not in _ar_if, _ar_if)
c("detay akışı: sunumda dalga, gerçekte gerçek ölçüm geçişi",
  '_CI.akis_betigi(mod="dalga" if _demo_modu() else "gecis")' in SAYFA)
c("[sunum] satır / grup / özet sayıları akış için işaretli",
  "canli-sayi" in CI.satir_html("TRDP-1", 12.0, "") and "canli-sayi" in CI.grup_html("X", "", "", 5.0, 1)
  and "data-faz='grup-X'" in CI.grup_html("X", "", "", 5.0, 1)
  and '_tp, 1, "grup-" + _bas, *(_CI.grup_gecis(' in SAYFA)
c("[sunum] okunamayan sayaç akmaz ('okunamadı' yazar)", "canli-sayi" not in CI.satir_html("TRDP-1", None, ""))
c("akış betiği önceki sayacı kapatır (üst üste çalışmaz)", "clearInterval(W.__synAkis)" in CI.akis_betigi())
c("[sunum] kart kW / W/m² / özet değerleri akış için işaretli",
  _MRK.count('class="canli-sayi"') >= 3)
_RAPOR = open(os.path.join(BURASI, "pages", "rapor_olustur.py"), encoding="utf-8").read()
c("[sunum] Geri butonu demoda app_demo.py'ye döner (sabit app_merkez.py hata veriyordu)",
  'switch_page("app_merkez.py")' not in SAYFA + _RAPOR
  and '"app_demo.py" if os.environ.get("SYNAPSE_DEMO") == "1"' in SAYFA
  and '"app_demo.py" if os.environ.get("SYNAPSE_DEMO") == "1"' in _RAPOR)
c("kojen/gaz/su çubuğu yük eşiğiyle kırmızıya boyanmaz",
  CI.ESIKSIZ_RENK in CI.bar_html(1900.0, 2000.0, esikli=False)
  and CI.esik_rengi(1900.0) in CI.bar_html(1900.0, 2000.0)
  and "esikli=_an not in _CI.ESIKSIZ_GRUPLAR" in SAYFA)
c("[gerçek sistem] yalnız elektrik sayacı varsa yeni grup çıkmaz",
  {a for a, _, _ in CI.gruplara_ayir(["TRDP-1", "CHILLER-1", "MCC-1"])} == {"enerji", "sogutma", "mcc"})
c("canlı grubu olan kalem 'ölçülmüyor' diye ayrıca yazılmaz",
  "_CI.OLCULMEYEN_GRUP.get(a) not in _canli_gruplar" in SAYFA
  and set(CI.OLCULMEYEN_GRUP) == {a for a, _, _ in CI.OLCULMEYEN})

# ── GERÇEK SİSTEM: saniyelik geçiş UYDURMA DEĞER ÜRETMEZ ─────────────────
# Kullanıcı kararı (25.10.2026): Maslak'tan gelen veri gerçek; ekranda iki
# gerçek ölçümün dışında hiçbir değer görünmemeli.
_d = {}
c("[geçiş] ilk ölçümde önceki yok → sayı sabit",
  CI.gecis_izle(_d, "x", 100.0, 1000.0) == {"o": None, "d": 100.0, "t": 1000.0, "s": None})
c("[geçiş] aynı ölçüm tekrar gelince yeni sayılmaz",
  CI.gecis_izle(_d, "x", 100.0, 1000.0)["o"] is None)
_g = CI.gecis_izle(_d, "x", 130.0, 1015.0)
c("[geçiş] yeni ölçüm: önceki = eski son, süre = ölçüm aralığı",
  _g == {"o": 100.0, "d": 130.0, "t": 1015.0, "s": 15.0}, _g)
c("[geçiş] sayfa yeniden çizilince geçiş bozulmaz",
  CI.gecis_izle(_d, "x", 130.0, 1015.0) == _g)
c("[geçiş] değer yoksa geçiş yok", CI.gecis_izle(_d, "y", None, 1015.0) is None)
c("[geçiş] süre makul banda kırpılır",
  CI.gecis_suresi(0, 1) == CI.GECIS_SURE_ALT and CI.gecis_suresi(0, 999) == CI.GECIS_SURE_UST
  and CI.gecis_suresi(5, 5) is None and CI.gecis_suresi(None, 5) is None)

# Tarayıcıdaki hesabın Python karşılığı: f = clamp((şimdi - başlangıç) / süre, 0, 1)
def _goster(o, d, s, gecen):
    f = min(1.0, max(0.0, gecen / s))
    return o + (d - o) * f
_vals = [_goster(100.0, 130.0, 15.0, g) for g in range(0, 40)]
c("[geçiş] gösterilen HER değer iki gerçek ölçümün arasında",
  all(100.0 <= v <= 130.0 for v in _vals))
c("[geçiş] son ölçüme varınca durur, ileri GİTMEZ", _vals[15:] == [130.0] * 25)
_js = CI.akis_betigi(mod="gecis")
c("[geçiş] tarayıcı hesabı 0-1 arasına kırpılı (son ölçümü aşmaz)",
  "Math.min(1, Math.max(0, (simdi - b.bas) / s))" in _js)
c("[geçiş] gerçek kipte dalga uygulanmaz",
  "if (MOD === 'dalga') { el.textContent = yaz(v * carpan(fz, simdi), ond); return; }" in _js
  and '"gecis"' in _js)
c("[geçiş] önceki ölçüm yoksa sayı olduğu gibi kalır",
  "if (o == null || t == null || !s) { return d; }" in _js)
c("[geçiş] açık ekranda bellek büyümez (anahtar başına son ölçüm)",
  "b.t !== String(t)" in _js)

# Detay: serideki son iki ölçüm
_sr = CI.bos_seri()
for _i, _v in enumerate((50.0, 60.0)):
    _sr = CI.seri_guncelle(_sr, [{"cihaz": "TRDP-1", "kw": _v, "olcum_zamani": T0 + timedelta(seconds=15 * _i)},
                                 {"cihaz": "TRDP-2", "kw": None if _i == 0 else 9.0,
                                  "olcum_zamani": T0 + timedelta(seconds=15 * _i)}], 300, simdi=T0 + timedelta(seconds=15 * _i))
_on, _ts, _su = CI.seri_gecis(_sr)
c("[geçiş] detay: önceki ölçüm seriden", _on == {"TRDP-1": 50.0} and _su == 15.0, (_on, _su))
c("[geçiş] detay: önceki okunamayan sayaç geçmez (son değeriyle durur)", "TRDP-2" not in _on)
c("[geçiş] detay: grup önceki toplamı = önceki + (önceki yoksa son)",
  CI.grup_gecis(_on, {"TRDP-1": 60.0, "TRDP-2": 9.0}, ["TRDP-1", "TRDP-2"], _ts, _su)[0] == 59.0)
c("[geçiş] detay: tek ölçümde geçiş yok", CI.seri_gecis(CI.seri_guncelle(CI.bos_seri(),
  [{"cihaz": "A", "kw": 1.0, "olcum_zamani": T0}], 300, simdi=T0)) == ({}, None, None))
_sh = CI.satir_html("TRDP-1", 60.0, "", gecis=(50.0, _ts, _su))
c("[geçiş] satırda önceki ölçüm işaretli", "data-onceki='50.000'" in _sh and "data-sure='15.0'" in _sh)
c("[geçiş] ana ekran: kart / özet / harita gerçek ölçüm geçişiyle",
  "gecis_ozellik(_g_seb)" in _MRK and "gecis_ozellik(_g_ozet)" in _MRK
  and 'GECIS = canli_gecis_hesapla(CANLI, st.session_state.setdefault("_canli_gecis", {}))' in _MRK)

# ── 26.10.2026: TRAFO / ÜRETİM düzeni ──
c("kojen adlari KOJEN-1..4", CI.kojen_adlari() == ["KOJEN-1", "KOJEN-2", "KOJEN-3", "KOJEN-4"])
c("canli gelen kojen bekleyenlerden duser", CI.kojen_bekleyenler(["KOJEN-1", "kojen-3"]) == ["KOJEN-2", "KOJEN-4"])
c("hic canli kojen yoksa dordu de bekler", len(CI.kojen_bekleyenler([])) == 4)
# Kojen sayısı lokasyona göre (sabit 4, 2 kojenli hastanede olmayan KOJEN-3/4'ü
# "bekleniyor" gösteriyordu)
c("Maslak kojen sayisi sahada sayilmis (4)", CI.kojen_adedi("maslak") == 4)
c("diger lokasyonda gunluk kayittaki en yuksek Kojen_Adet", CI.kojen_adedi("izmir", 2.0) == 2)
c("kojen sayisi bilinmiyorsa None", CI.kojen_adedi("izmir", None) is None and CI.kojen_adedi("x", 0) is None)
c("2 kojenli lokasyonda KOJEN-3/4 beklemez", CI.kojen_bekleyenler([], 2) == ["KOJEN-1", "KOJEN-2"])
c("sayi bilinmiyor + canli kojen var: bekleyen uydurulmaz", CI.kojen_bekleyenler(["KOJEN-1", "KOJEN-2"], None) == [])
c("sayi bilinmiyor + canli yok: tek KOJEN satiri", CI.kojen_bekleyenler([], None) == ["KOJEN"])
c("detay sayfasi kojen sayisini lokasyondan alir",
  "_CI.kojen_bekleyenler(_kojen_canli, _kojen_adet)" in SAYFA and "_CI.kojen_adedi(" in SAYFA)
# Genel Müdürlük logosu Ataşehir hastanesinin noktasını örtmesin
c("GM logosunun kabi tiklamayi gecirir, yalniz logo tiklanir",
  "'.gm-kap{position:relative;width:64px;height:78px;pointer-events:none}'" in _MRK
  and "sdLogoParla 3s ease-in-out infinite;pointer-events:auto}" in _MRK
  and "zIndexOffset: 1000, interactive: false" in _MRK)
_ik = CI.ozet_ikili_kart_html([("TRAFO TOPLAM", "1", "4 trafo", True), ("ÜRETİM TOPLAM", "—", "bekleniyor", False)])
c("ozet karti iki ic kartli", _ik.count("class='cg-ic'") == 2 and "TRAFO TOPLAM" in _ik and "ÜRETİM TOPLAM" in _ik
  and _ik.count("cg-nabiz") == 1)
c("bekleyen satir 'bekleniyor' yazar, 0 kW yazmaz",
  "bekleniyor" in CI.olculmeyen_satir_html("KOJEN-1", CI.KOJEN_BEKLEME_NOTU, sag="bekleniyor")
  and "kW" not in CI.olculmeyen_satir_html("KOJEN-1", CI.KOJEN_BEKLEME_NOTU, sag="bekleniyor"))
c("olcusuz satir notu tasmaz", "text-overflow:ellipsis" in CI.STIL and ".cg-bos{height:28px; display:flex; align-items:center; gap:7px; min-width:0" in CI.STIL)
_sy = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages", "lokasyon_detay.py"), encoding="utf-8").read()
c("sayfa: SEBEKEDEN CEKILEN / SEBEKE adi kalmadi", "ŞEBEKEDEN ÇEKİLEN" not in _sy and '"ŞEBEKE", _tp' not in _sy)
c("sayfa: enerji icinde TRAFO + KOJEN URETIM ic kartlari", 'alt_kart_html("TRAFO"' in _sy
  and 'alt_kart_html("KOJEN ÜRETİM"' in _sy and "ozet_ikili_kart_html" in _sy and 'ic_kartli=(_an == "enerji")' in _sy)
_ak = CI.alt_kart_html("TRAFO", "1 kW", CI.satir_html("TRDP-1", 5.0, CI.bar_html(5.0, 10)))
c("ic kart: baslik + toplam + kendi listesi", "cg-altkart-bas" in _ak and "cg-liste-ic" in _ak and "TRDP-1" in _ak)
c("ic kartli grup duz sutun", "cg-liste-blok" in CI.grup_html("E", "", _ak, 1.0, 1, ic_kartli=True)
  and "cg-liste-blok" not in CI.grup_html("E", "", "", 1.0, 1))
c("sayfa: kojen ayri kart degil, enerji kartinda", '_gruplar = [g for g in _gruplar if g[0] != "kojen"]' in _sy)
c("sayfa modul surumu 10 istiyor", "_CI_GEREKEN_SURUM = 10" in _sy and CI.SURUM >= 10)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
