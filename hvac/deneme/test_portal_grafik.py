# -*- coding: utf-8 -*-
"""Enerji portalı Grafik & Trend (29.10.2026): Synapse'teki açılır metrik listesi.

    python test_portal_grafik.py
"""
import os
import sys

import pandas as pd

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import portal_grafik as PG  # noqa: E402

PORTAL = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def gunler(ay, **kolonlar):
    t = pd.date_range(ay + "-01", periods=5, freq="D")
    return pd.DataFrame({"Tarih": t, **{k: [v] * 5 for k, v in kolonlar.items()}})


bu = gunler("2026-10", Toplam_Hastane_Tuketim_kWh=60000, Sebeke_Tuketim_kWh=20000, TRDP1_kWh=20000,
            TRDP2_kWh=15000, Toplam_Sogutma_Tuketim_kWh=4000, MCC_Tuketim_kWh=10000, Kojen3_kWh=11000)
once = gunler("2025-10", Toplam_Hastane_Tuketim_kWh=50000, Sebeke_Tuketim_kWh=20000, Su_Tuketimi_m3=300)

# ── Liste: tüm metrikler, kategorili ──
c("açılır listede tüm metrikler (15)", len(PG.SECENEKLER) == 15, len(PG.SECENEKLER))
c("her metriğin simgesi ve birimi var", all(PG.SIMGE.get(t) and PG.BIRIM.get(t) for t in PG.SECENEKLER.values()))
c("varsayılan Tüketim", "Tüketim" in PG.SECENEKLER and 'index=_g_adlar.index("Tüketim")' in PORTAL)
c("kategoriler: enerji, gaz & su, soğutma, özet", [g for g, _ in PG.GRUPLAR] ==
  ["ENERJİ & KAYNAK", "GAZ & SU", "SOĞUTMA & MEKANİK", "ÖZET & KARŞILAŞTIRMA"])
c("liste görünümü Streamlit 1.42 ve 1.5x için", 'ul[role="listbox"]' in PG.secici_css("tuketim")
  and "stSelectboxVirtualDropdown" in PG.secici_css("tuketim"))

# ── Çizim: veriden olduğu gibi ──
f, _ = PG.ciz("tuketim", bu, once, "Ekim 2026", "Ekim 2025")
c("tüketim grafiği günlük değerleri olduğu gibi çizer", f is not None and list(f.data[0].y) == [60000.0] * 5)
f, _ = PG.ciz("trafo", bu, once, "Ekim 2026", "Ekim 2025")
c("trafolar: yalnız verisi olan TRDP'ler çizilir (uydurma 0 yok)",
  f is not None and [d.name for d in f.data] == ["TRDP-1", "TRDP-2"], f and [d.name for d in f.data])
f, _ = PG.ciz("kojenler", bu, once, "Ekim 2026", "Ekim 2025")
c("kojenler: yalnız okunan kojen", f is not None and [d.name for d in f.data] == ["Kojen-3"])
f, b = PG.ciz("su", bu, once, "Ekim 2026", "Ekim 2025")
c("verisi olmayan metrik grafik yerine bilgi verir", f is None and "veri yok" in b)
f, _ = PG.ciz("karsilastir", bu, once, "Ekim 2026", "Ekim 2025")
c("karşılaştırma: iki ay yan yana", f is not None and [d.name for d in f.data] == ["Ekim 2025", "Ekim 2026"])
f, _ = PG.ciz("kirilim", bu, once, "Ekim 2026", "Ekim 2025")
c("enerji kırılımı: soğutma + MCC + diğer = toplam",
  f is not None and [round(sum(v)) for v in zip(*[d.y for d in f.data])] == [60000] * 5)
f, b = PG.ciz("verim", bu, once, "Ekim 2026", "Ekim 2025", 0)
c("kWh/m²: alan girilmemişse uyarır", f is None and "m²" in b)
c("boş dönem çökmez", PG.ciz("tuketim", bu.iloc[0:0], once, "a", "b")[0] is None)

# ── Rozet: karşılaştırılan aya göre, tüketimde artış kırmızı ──
r = PG.rozet("tuketim", bu, once, "Ekim 2025")
c("rozet artışı kırmızı ▲ gösterir", "▲ +%20,0" in r and "#d03b3b" in r, r)
c("rozet: bu ay verisi olmayan kalemde YOK (sahte -%100 yok)", PG.rozet("su", bu, once, "Ekim 2025") == "")
c("rozet: karşılaştırma ayında veri yoksa YOK", PG.rozet("tuketim", bu, once.iloc[0:0], "x") == "")

# ── Grafikler DÜZ (29.10.2026): akan desen / animasyon yok ──
_KAYNAK = open(os.path.join(BURASI, "portal_grafik.py"), encoding="utf-8").read()
c("grafiklerde akan desen yok", "animateTransform" not in _KAYNAK and "desen_html" not in PORTAL)
_HAREKET = open(os.path.join(BURASI, "portal_hareket.py"), encoding="utf-8").read()
c("grafiklerin giriş animasyonu kapalı",
  '[data-testid="stPlotlyChart"], [data-testid="stPlotlyChart"] * { animation: none !important; }' in _HAREKET)

# ── Portala bağlı ──
c("Dashboard grafiği portal_grafik ile", "_pg.ciz(_g_tip, df_period, _df_kiyas" in PORTAL)
c("eski Grafik detayı (Günlük/Aylık/Yıllık) kaldırıldı", 'key="dash_viewmode_radio"' not in PORTAL)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
