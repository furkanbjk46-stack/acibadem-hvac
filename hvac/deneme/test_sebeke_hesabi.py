# -*- coding: utf-8 -*-
"""Şebeke + kojen hesabı — app_portal.recalc() GERÇEK kodu üzerinde.

app_portal.py Streamlit'e bağlı olduğu için bütün olarak import edilemez;
recalc() fonksiyonunun kaynağı dosyadan ayıklanıp burada çalıştırılır.
Böylece test, sayfadaki kodun kopyası değil KENDİSİ üzerinde koşar.

Neyi koruyoruz: MCC/Chiller analizörleri kaynağa bakmadan tüketimi ölçer.
Kojen çalışırken o yükleri kojen besler. Bunlar şebekeye eklenip üstüne
"Kojen Üretim" de toplanınca aynı enerji İKİ KEZ sayılıyordu — Ağustos
2026'da günde ~16.000 kWh, ayda ~448.000 kWh fazla.
"""
import ast
import os

import pandas as pd

BURASI = os.path.dirname(os.path.abspath(__file__))
KAYNAK = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── recalc()'i dosyadan ayıkla ────────────────────────────────────────────
_agac = ast.parse(KAYNAK)
_fn = next((d for d in _agac.body
            if isinstance(d, ast.FunctionDef) and d.name == "recalc"), None)
c("recalc() fonksiyonu bulundu", _fn is not None)
_ns = {"pd": pd}
exec(compile(ast.Module(body=[_fn], type_ignores=[]), "recalc", "exec"), _ns)
recalc = _ns["recalc"]

_KOLONLAR = ["TRDP1_kWh", "TRDP2_kWh", "TRDP3_kWh", "TRDP4_kWh",
             "Sebeke_Tuketim_kWh", "Kojen_Uretim_kWh", "MCC_Tuketim_kWh",
             "Chiller_Tuketim_kWh", "VRF_Split_Tuketim_kWh",
             "Toplam_Sogutma_Tuketim_kWh", "Toplam_Hastane_Tuketim_kWh",
             "Diger_Yuk_kWh"]


def satir(**kw):
    d = {k: 0.0 for k in _KOLONLAR}
    d.update(kw)
    return recalc(pd.DataFrame([d])).iloc[0]


# ── 1) Şebeke = ölçülen trafoların toplamı ───────────────────────────────
r = satir(TRDP1_kWh=20000, TRDP2_kWh=12000, TRDP3_kWh=8000, TRDP4_kWh=12000)
c("dört trafo: şebeke toplamları", r["Sebeke_Tuketim_kWh"] == 52000,
  r["Sebeke_Tuketim_kWh"])
r = satir(TRDP1_kWh=20000, TRDP3_kWh=8000)
c("iki trafo: şebeke yalnız o ikisi", r["Sebeke_Tuketim_kWh"] == 28000,
  r["Sebeke_Tuketim_kWh"])
r = satir(TRDP3_kWh=8000)
c("tek trafo bile olsa şebekeye yazılır", r["Sebeke_Tuketim_kWh"] == 8000,
  r["Sebeke_Tuketim_kWh"])

# ── 2) ÇİFT SAYIM KORUMASI — asıl düzeltme ───────────────────────────────
# Ağustos 2026 günü: mekanik trafolar (TRDP-2/4) okunamıyor, kojen çalışıyor.
ag = satir(TRDP1_kWh=19783, TRDP3_kWh=8139, MCC_Tuketim_kWh=13603,
           Chiller_Tuketim_kWh=10635, Kojen_Uretim_kWh=44411)
c("eksik trafo gününde MCC/Chiller şebekeye EKLENMEZ",
  ag["Sebeke_Tuketim_kWh"] == 19783 + 8139, ag["Sebeke_Tuketim_kWh"])
c("eksik trafo gününde toplam = ölçülen trafolar + kojen",
  ag["Toplam_Hastane_Tuketim_kWh"] == 19783 + 8139 + 44411,
  ag["Toplam_Hastane_Tuketim_kWh"])
_eski_yedek = 19783 + 8139 + 13603 + 10635 + 44411        # eski fallback sonucu
c("eski fallback'in ürettiği şişkin toplam ARTIK ÇIKMIYOR",
  ag["Toplam_Hastane_Tuketim_kWh"] < _eski_yedek - 20000,
  (ag["Toplam_Hastane_Tuketim_kWh"], _eski_yedek))

# ── 3) Toplam = şebeke + kojen ───────────────────────────────────────────
r = satir(TRDP1_kWh=19030, TRDP2_kWh=12606, TRDP3_kWh=7694, TRDP4_kWh=12532,
          Kojen_Uretim_kWh=41737)
c("dört trafo + kojen toplamı", r["Toplam_Hastane_Tuketim_kWh"] == 51862 + 41737,
  r["Toplam_Hastane_Tuketim_kWh"])
r0 = satir(TRDP1_kWh=19030, TRDP2_kWh=12606, TRDP3_kWh=7694, TRDP4_kWh=12532)
c("kojen yokken toplam yalnız şebeke", r0["Toplam_Hastane_Tuketim_kWh"] == 51862,
  r0["Toplam_Hastane_Tuketim_kWh"])
c("kojen çalışan gün, duran günden kojen kadar fazla",
  round(r["Toplam_Hastane_Tuketim_kWh"] - r0["Toplam_Hastane_Tuketim_kWh"]) == 41737)

# ── 4) Trafo hiç yoksa eski davranış korunur (2023-2025 satırları) ───────
r = satir(Sebeke_Tuketim_kWh=40000, Kojen_Uretim_kWh=36000)
c("trafo yoksa elle girilen şebeke korunur", r["Sebeke_Tuketim_kWh"] == 40000,
  r["Sebeke_Tuketim_kWh"])
c("trafo yoksa toplam = elle girilen şebeke + kojen",
  r["Toplam_Hastane_Tuketim_kWh"] == 76000, r["Toplam_Hastane_Tuketim_kWh"])
r = satir(MCC_Tuketim_kWh=13000, Chiller_Tuketim_kWh=10000, Kojen_Uretim_kWh=30000)
c("şebeke de trafo da yoksa alt sayaçlar son çare olarak kalır",
  r["Toplam_Hastane_Tuketim_kWh"] == 13000 + 10000 + 30000,
  r["Toplam_Hastane_Tuketim_kWh"])

# ── 5) Soğutma ve diğer yük ──────────────────────────────────────────────
r = satir(TRDP1_kWh=30000, TRDP3_kWh=20000, Chiller_Tuketim_kWh=8000,
          VRF_Split_Tuketim_kWh=2000, MCC_Tuketim_kWh=12000)
c("soğutma = chiller + VRF", r["Toplam_Sogutma_Tuketim_kWh"] == 10000)
c("diğer yük = toplam - MCC - soğutma", r["Diger_Yuk_kWh"] == 50000 - 12000 - 10000,
  r["Diger_Yuk_kWh"])
c("diğer yük negatif olmaz",
  satir(TRDP1_kWh=1000, MCC_Tuketim_kWh=9000)["Diger_Yuk_kWh"] == 0)

# ── 6) Kaynakta eski yedek kalmadı ───────────────────────────────────────
c("app_portal'da MCC+Chiller şebeke yedeği kaldırıldı",
  "mekanik_fallback" not in KAYNAK and "trdp_fallback" not in KAYNAK)
c("giriş ekranı eksik trafoyu uyarır", "şebeke eksik ölçülüyor" in KAYNAK)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
