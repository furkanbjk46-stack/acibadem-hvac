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
c("grafik boşlukları birleştirmiyor", "connectgaps=False" in
  open(os.path.join(BURASI, "canli_izleme.py"), encoding="utf-8").read())

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

# ── 5) Eksen — çizginin akmasını sağlayan şey ────────────────────────────
bas, bit = CI.eksen_araligi(s, 300, simdi=T0 + timedelta(seconds=60))
c("eksen sonu şimdiki zaman", bit == T0 + timedelta(seconds=60), bit)
c("eksen başı pencere kadar geride", (bit - bas).total_seconds() == 300)
# Veri gelmese bile aralık ilerler → çizgi sola akar
bas2, bit2 = CI.eksen_araligi(s, 300, simdi=T0 + timedelta(seconds=120))
c("yeni veri olmasa da eksen ilerliyor (akış görüntüsü)", bit2 > bit)

# ── 6) Grafik ────────────────────────────────────────────────────────────
class _SahteGo:
    """plotly yerine: çağrıları kaydeder, kurulum doğru mu bakarız."""
    class Scatter(dict):
        def __init__(self, **kw):
            super().__init__(**kw)

    class Figure:
        def __init__(self):
            self.izler, self.yerlesim, self.x, self.y = [], {}, {}, {}

        def add_trace(self, iz):
            self.izler.append(iz)

        def update_layout(self, **kw):
            self.yerlesim.update(kw)

        def update_xaxes(self, **kw):
            self.x.update(kw)

        def update_yaxes(self, **kw):
            self.y.update(kw)


f = CI.grafik(_SahteGo, s, 300, simdi=T0 + timedelta(seconds=30))
c("her cihaz için bir çizgi", len(f.izler) == 2, len(f.izler))
c("çizgiler isimli", {i["name"] for i in f.izler} == {"TRDP-1", "TRDP-2"})
c("çizgi modunda (nokta yığını değil)", all(i["mode"] == "lines" for i in f.izler))
c("eksen aralığı uygulanmış", "range" in f.x, f.x)
c("y ekseni sıfırdan başlıyor", f.y.get("rangemode") == "tozero")
c("yenilemede kullanıcı görünümü korunuyor", f.yerlesim.get("uirevision") == "canli")
c("hover birleşik", f.yerlesim.get("hovermode") == "x unified")

_renkler = [i["line"]["color"] for i in f.izler]
c("her cihazın rengi farklı", len(set(_renkler)) == len(_renkler), _renkler)
c("renk cihaza sabit (yenilemede değişmiyor)",
  CI.renk("TRDP-2", ["TRDP-1", "TRDP-2"]) == CI.renk("TRDP-2", ["TRDP-1", "TRDP-2"]))

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
c("grafik tek yerden çiziliyor", "_CI.grafik(go, seri, pencere_sn)" in SAYFA)

# Pencere (detay pop-up'ı) artık canlı veri göstermiyor — sıkışıklık giderildi
c("detay penceresinden canlı blok kaldırıldı", "canli" not in PANEL)
c("detay penceresi iki sütunu da dönem verisiyle kullanıyor",
  "ENERJİ KAYNAĞI" in PANEL and "SİSTEM DURUMU" in PANEL)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
