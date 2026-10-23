# -*- coding: utf-8 -*-
"""Animasyonlu simgeler — tek kaynak ve tutarlılık testleri.

    python merkez/test_ikonlar.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ikonlar  # noqa: E402

SONUC = []


def c(ad, kosul, ayrinti=""):
    SONUC.append(bool(kosul))
    print(("PASS " if kosul else "FAIL ") + ad + ("" if kosul else "   " + str(ayrinti)))


METRIKLER = ["enerji", "dogalgaz", "sogutma", "su", "kojen", "sebeke", "mcc", "kazan",
             "trdp", "verim", "takvim", "kollektor", "fcu", "ahu", "ariza", "bakim",
             "hvac", "alarm", "oto", "zeka", "oneri", "saglik", "gunduz", "gece", "saat",
             "kayit", "termometre", "tamam", "hata", "geri", "grafik", "ayar", "yonetim", "cikis"]

for m in METRIKLER:
    h = ikonlar.ikon(m)
    c("%s simgesi SVG uretir" % m, "<svg" in h and "ai-%s" % m in h, h[:80])
    c("%s rengi tanimli" % m, re.fullmatch(r"#[0-9a-f]{6}", ikonlar.RENK.get(m, "")))
    c("%s animasyonu CSS'te" % m, (".ai-%s " % m) in ikonlar.CSS)

c("takma ad: chiller = sogutma (her yerde ayni simge)",
  ikonlar.ikon("chiller") == ikonlar.ikon("sogutma"))
c("takma ad: tuketim = enerji", ikonlar.ikon("tuketim") == ikonlar.ikon("enerji"))
c("bilinmeyen ad sayfayi bozmaz", ikonlar.ikon("yok_boyle") == "")
c("sakin simge animasyonsuz isaretlenir", "ai-sakin" in ikonlar.ikon("ariza", sakin=True))
c("renk CSS degiskeniyle SVG'ye baglanir", "--ai-renk:" in ikonlar.ikon("su"))
c("hareketi azalt tercihine uyulur", "prefers-reduced-motion" in ikonlar.CSS)
c("ariza: ucgen icinde unlem", "ai-unlem" in ikonlar._SVG["ariza"] and "M10.3 3.6" in ikonlar._SVG["ariza"])
c("bakim: ingiliz anahtari ve sallanma",
  "ai-anahtar" in ikonlar.CSS and ".ai-bakim svg{animation:ai-anahtar" in ikonlar.CSS)

# Ana ekran ve Dashboard simgeyi AYNI kaynaktan alır
_d = os.path.dirname(os.path.abspath(__file__))
_m = open(os.path.join(_d, "app_merkez.py"), encoding="utf-8").read()
_l = open(os.path.join(_d, "pages", "lokasyon_detay.py"), encoding="utf-8").read()
c("ana ekran simge CSS'ini yukluyor", "st.markdown(_ik.CSS" in _m)
c("dashboard simge CSS'ini yukluyor", "st.markdown(_ik.CSS" in _l)
c("global ozet simgesi ikonlar'dan", "_ik.ikon(_ozet_key" in _m)
c("global ozet cercevesi kalemin rengi", "_ik.renk(_ozet_key)" in _m)
c("canli uyarilar alarm simgesi", '_ik.ikon("alarm"' in _m)
c("lokasyon karti cercevesi kendi renginde", "--lokrenk:{renk}" in _m and "var(--lokrenk" in _m)
c("dashboard ozet kartlari ikonlar'dan", "_ik.ikon(ikon, 28)" in _l)
c("kojen&kaynak kartlarinda emoji kalmadi",
  not re.search(r'_kaynak_item\("[^a-z]', _l))
for k in ("ariza", "bakim", "hvac"):
    c("HVAC karti: %s simgesi" % k, '_ik.ikon("%s", 34' % k in _l)
for k in ("chiller", "kollektor", "fcu", "ahu"):
    c("yururlukteki setler: %s simgesi" % k, '"%s", "' % k in _l)

# Düğme / sekme etiketleri (SVG konamayan yerler) için maske simgesi
_e = ikonlar.etiket_css(".x button p", "saat", 14)
c("etiket simgesi maske + animasyon", "mask:url(" in _e and "animation:" in _e and ".x button p::before" in _e)
c("modul surumu var (onbellek korumasi)", getattr(ikonlar, "SURUM", 0) >= 3)
c("atan nokta yardimcisi", "ai-nokta" in ikonlar.nokta())
c("ana ekran surum korumasi", '_ik = _il_ik.reload(_ik)' in _m)
c("dashboard surum korumasi", '_ik = _il_ik.reload(_ik)' in _l)
c("OTO SET simgeleri", '_ik.ikon("oto", 22)' in _m and 'etiket_css(".st-key-oto_saat_kart' in _m)
c("dis hava simgeleri", "_ik.ikon('termometre', 18)" in _m)
c("sabah analizi simgesi", '_ik.ikon("zeka", 22)' in _m)
c("OTO SET anahtari tasmaz (sabit sutun)", "flex:0 0 56px" in _m)
c("lokasyon kartlari daralinca tek sira", "repeat(auto-fill, minmax(178px, 1fr))" in _m)
c("sistem sagligi simgeleri", all(('_ik.ikon("%s", 16)' % k) in _l for k in ("oto", "zeka", "oneri")))
c("detay ust: geri / baslik / rozet", 'key="detay_geri"' in _l and "dz-baslik" in _l and '_ik.ikon("takvim", 13' in _l)
c("detay sekmeleri simgeli", "st-key-detay_sekmeler" in _l)
c("dashboard stili = canli izleme", ".dz-dg{font-size:26px;font-weight:700;color:#133273" in _l)

# 23.10.2026 ikinci tur
c("baslik: Canli Enerji Agi", "Canlı Enerji Ağı" in _m and "SYNAPSE // Merkezi" not in _m)
c("sag ust: Ayarlar/Yonetim/Cikis hareketli", all(('etiket_css(".st-key-%s button p"' % k) in _m
                                                  for k in ("ayarlar_btn", "yonetim_btn", "cikis_btn")))
c("ayarlar sayfa altinda degil, pencerede", "with st.expander(\"⚙️  Ayarlar\"" not in _m and "@st.dialog(\"Sistem Ayarları\"" in _m)
c("ayarlar penceresi acikken yenileme durur", 'not st.session_state.get("_ayarlar_acik")' in _m)
c("sutun hizalama betigi", "__synapseHizala" in _m and "aOrta + 220" in _m)
c("harita taban boyu kisaldi", "height=640, scrolling=False" in _m)
c("grafik listesi emojisiz + simgeli", '"Tüketim":               "tuketim"' in _l and "_GRAFIK_IKON" in _l)
c("KPI ozet satirlarinda tarih yok", "({_etiket})" not in _l)
c("trafolar yan yana", 'barmode="group", bargap=0.22' in _l)
c("grafik animasyonu", "dzBuyu" in _l and "dzCiz" in _l)
c("HVAC satirlari okunur + hareketli", "dz-satir" in _l and "rgb(253,211,77)" not in _l)

print("\n%d/%d PASS" % (sum(SONUC), len(SONUC)))
sys.exit(0 if all(SONUC) else 1)
