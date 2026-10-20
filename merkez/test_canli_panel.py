# -*- coding: utf-8 -*-
"""Detay penceresinin CANLI sütunu — ag baglantisi YOK.

Pencere ikiye ayrildi (20.10.2026): solda DONEM toplami (kWh), sagda ayni
sayaclarin O ANKI gucu (kW). Iki sey korunur:

  1) CANLI SUTUN UYDURMAZ. Veri yoksa nedenini yazar; eksik sayac varsa
     toplamin kac sayactan geldigini soyler; olcum bayatsa bunu gosterir.
     Ekranda "0 kW" ile "veri yok" ayni sey degildir.
  2) KENDI BASINA YENILENIR. Detay penceresi acikken sayfanin geneli
     bilerek yenilenmiyor (app_merkez.py'deki autorefresh kosulu; tam
     yenileme pencereyi kapatiyordu). Bu yuzden canli sutun st.fragment
     ile tazelenmek ZORUNDA — yoksa "canli" diye donmus sayi gosteririz.
"""
import os
import re
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import karsilastirma_panel as KP  # noqa: E402

PANEL = open(os.path.join(BURASI, "karsilastirma_panel.py"), encoding="utf-8").read()
MERKEZ = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
CANLI_SAYFA = open(os.path.join(BURASI, "pages", "ozet_karsilastirma.py"), encoding="utf-8").read()
DEMO_SAYFA = open(os.path.join(BURASI, "sunum", "ozet_karsilastirma_demo.py"), encoding="utf-8").read()
SIM = open(os.path.join(BURASI, "_sim_sunucu.py"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


ORNEK = [
    {"cihaz": "TRDP-1", "kw": 412.3, "yontem": "register", "aciklama": None},
    {"cihaz": "TRDP-2", "kw": 318.7, "yontem": "register", "aciklama": None},
    {"cihaz": "TRDP-3", "kw": 96.4, "yontem": "sayac", "aciklama": "güç register'ı okunamadı"},
    {"cihaz": "TRDP-4", "kw": 201.0, "yontem": "register?", "aciklama": None},
]

# ── 1) Veri yoksa uydurma yok ────────────────────────────────────────────
bos = KP.canli_blok([])
c("veri yokken neden yazılıyor", "Canlı veri yok" in bos, bos[:120])
c("veri yokken sayı gösterilmiyor", "kW" not in bos.replace("CANLI OKUMA (kW)", ""))
c("veri yokken 0 yazılmıyor", ">0<" not in bos and "0 kW" not in bos)

# ── 2) Dolu blok ─────────────────────────────────────────────────────────
h = KP.canli_blok(ORNEK, yas_sn=4)
for o in ORNEK:
    c("cihaz görünüyor: %s" % o["cihaz"], o["cihaz"] in h)
c("kW değeri yazılıyor", "412,3 kW" in h, h[:200])
c("toplam hesaplanıyor (412,3+318,7+96,4+201,0=1028,4)", "1.028,4 kW" in h,
  re.findall(r"[\d.,]+ kW", h))
c("son ölçüm yaşı yazılıyor", "4 sn önce" in h)

# ── 3) Yöntem görünür olmalı (tahmin, ölçüm gibi gösterilmesin) ──────────
c("doğrulanmış register etiketli", "sayaçla doğrulandı" in h)
c("sayaç farkı etiketli", "sayaç farkından" in h)
c("doğrulanmamış register etiketli", "henüz doğrulanmadı" in h)
c("açıklama ipucu olarak taşınıyor", "güç register'ı okunamadı" in h)
c("yöntem etiketleri tek yerde tanımlı",
  set(KP.YONTEM_ETIKET) == {"register", "register?", "sayac"}, set(KP.YONTEM_ETIKET))

# ── 4) Eksik/bayat veri saklanmıyor ──────────────────────────────────────
eksik = KP.canli_blok([ORNEK[0], {"cihaz": "TRDP-2", "kw": None, "yontem": None}], yas_sn=3)
c("okunamayan cihaz '—' ile gösteriliyor", "—" in eksik)
c("toplamın kaç sayaçtan geldiği yazılıyor", "(1/2 sayaç)" in eksik, eksik[-400:])
c("eksik sayaç uyarı rengiyle", "250,178,25" in eksik)

bayat = KP.canli_blok(ORNEK, yas_sn=KP.CANLI_BAYAT_SN + 30)
c("bayat ölçüm uyarıyor", "akış durmuş olabilir" in bayat, bayat[:200])
c("bayat ölçüm uyarı renginde", "rgb(250,178,25)" in bayat)
taze = KP.canli_blok(ORNEK, yas_sn=5)
c("taze ölçüm yeşil", "#0ca30c" in taze)
c("zaman bilinmiyorsa belirtiliyor",
  "ölçüm zamanı bilinmiyor" in KP.canli_blok(ORNEK, yas_sn=None))

# ── 5) Yerleşim: dönem solda, canlı sağda ────────────────────────────────
_govde = PANEL.split("def panel_govde(")[1]
_sol = _govde.split("with s2:")[0]
_sag = _govde.split("with s2:")[1]

c("iki sütun var", "s1, s2 = st.columns(" in _govde)
for blok in ("SİSTEM BAZLI ELEKTRİK DAĞILIMI", "ENERJİ KAYNAĞI",
             "TRAFOLAR (ŞEBEKE KIRILIMI)", "SİSTEM DURUMU"):
    c("solda: %s" % blok, blok in _sol, blok)
c("canlı blok sağda", "canli_blok(" in _sag)
c("dönem verisi sağa sızmamış", "ENERJİ KAYNAĞI" not in _sag and "dag[" not in _sag)

# ── 6) Kendi kendine yenileme ────────────────────────────────────────────
c("fragment kullanılıyor", "@st.fragment(run_every=" in _sag)
c("yenileme aralığı dışarıdan verilebiliyor", 'ctx.get("canli_aralik"' in _sag)
c("varsayılan aralık 10 sn", '"10s"' in _sag, _sag[:400])
c("panel veriyi kendi çekmiyor (çağıran veriyor)",
  'ctx.get("canli")' in _sag and "supabase" not in PANEL.lower())
c("canlı veri alınamazsa pencere çökmüyor", "except Exception as e:" in _sag)
# Pencere acikken sayfa geneli yenilenmiyor — fragment'in gerekcesi budur
c("sayfa geneli detay penceresinde yenilenmiyor (gerekçe)",
  'not st.session_state.get("detay_ozet")' in MERKEZ)

# ── 7) İki çağıran da canlı veriyi bağlamış ──────────────────────────────
for ad, metin in (("canlı sayfa", CANLI_SAYFA), ("sunum sürümü", DEMO_SAYFA)):
    c("%s canlı veriyi veriyor" % ad, '"canli": lambda: fetch_canli_guc(' in metin)
c("merkezde çekme fonksiyonu var", "def fetch_canli_guc(" in MERKEZ)
c("canli_guc tablosundan okunuyor", 'c.table("canli_guc")' in MERKEZ)
c("lokasyona göre filtreleniyor", '.eq("lokasyon_id", lokasyon_id)' in MERKEZ)
_fetch = MERKEZ.split("def fetch_canli_guc(")[0].strip().split("\n")[-1]
c("önbellek canlıyı dondurmuyor (kısa TTL)", "ttl=5" in _fetch, _fetch)
c("yaş sahadaki ölçüm zamanından hesaplanıyor", 'olcum_zamani' in MERKEZ)

# ── 8) Sunum sürümü de çalışır (sahte sunucu tabloyu veriyor) ────────────
c("sahte sunucuda canli_guc tablosu var", '"canli_guc": []' in SIM)
c("sahte sunucu her istekte tazeliyor",
  'if tablo == "canli_guc":' in SIM and "canli_guc_tazele()" in SIM)
c("sahte veri yalnızca sayacı bağlı lokasyonda",
  '"lokasyon_id": "maslak"' in SIM.split("def canli_guc_tazele")[1][:1200])
c("sahte veri dört trafoyu kapsıyor",
  all(t in SIM.split("def canli_guc_tazele")[1][:900]
      for t in ("TRDP-1", "TRDP-2", "TRDP-3", "TRDP-4")))

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
