# -*- coding: utf-8 -*-
"""Enerji portalı — veri girişi, enerji diyagramı ve bildirim çubuğu.

Korunan davranışlar:
 1) Geçmiş bir güne su/doğalgaz girilince O GÜNÜN sayaç değerleri SİLİNMEZ.
    Eski kayıt, tarihin satırını tümüyle yenisiyle değiştiriyordu; formda
    bulunmayan MCC / Chiller / Kule sütunları NaN'a düşüyor, enerji
    diyagramında tarih duruyor ama bütün çipler "veri yok" görünüyordu.
 2) Enerji diyagramındaki gün listesi EN YENİ günden başlar.
 3) Bildirim çubuğunda "tümü okundu" ve hazır raporların indirmesi vardır;
    raporlar artık sayfanın üstünde yeşil kutu olarak durmaz.
"""
import ast
import datetime as dt
import os
import sys

import pandas as pd

BURASI = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
KAYNAK = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── _eski_degerleri_koru()'yu GERÇEK kaynaktan çalıştır ──────────────────
_agac = ast.parse(KAYNAK)
_fn = next((d for d in _agac.body
            if isinstance(d, ast.FunctionDef) and d.name == "_eski_degerleri_koru"), None)
c("_eski_degerleri_koru() bulundu", _fn is not None)
_ns = {"pd": pd}
exec(compile(ast.Module(body=[_fn], type_ignores=[]), "koru", "exec"), _ns)
koru = _ns["_eski_degerleri_koru"]

GUN = dt.date(2026, 6, 3)
SUTUNLAR = ["Tarih", "TRDP1_kWh", "Su_Tuketimi_m3", "Kazan_Dogalgaz_m3",
            "MCC1_kWh", "Chiller1_kWh", "Kule1_kWh"]


def eski():
    return pd.DataFrame([{"Tarih": GUN, "TRDP1_kWh": 8896.0, "Su_Tuketimi_m3": 0.0,
                          "Kazan_Dogalgaz_m3": 0.0, "MCC1_kWh": 1250.0,
                          "Chiller1_kWh": 3100.0, "Kule1_kWh": 420.0}])


def yeni(**kw):
    """Formun gönderdiği satır — şema NaN ile tamamlanmış gibi."""
    satir = {k: float("nan") for k in SUTUNLAR}
    satir["Tarih"] = GUN
    satir.update(kw)
    return pd.DataFrame([satir])


# 1) Su + doğalgaz girildi: sayaçlar duruyor mu?
_g = ["Su_Tuketimi_m3", "Kazan_Dogalgaz_m3"]
r = koru(yeni(Su_Tuketimi_m3=34.0, Kazan_Dogalgaz_m3=910.0), eski(), _g).iloc[0]
c("girilen su yazıldı", r["Su_Tuketimi_m3"] == 34.0, r["Su_Tuketimi_m3"])
c("girilen doğalgaz yazıldı", r["Kazan_Dogalgaz_m3"] == 910.0, r["Kazan_Dogalgaz_m3"])
c("MCC sayacı KORUNDU", r["MCC1_kWh"] == 1250.0, r["MCC1_kWh"])
c("chiller sayacı KORUNDU", r["Chiller1_kWh"] == 3100.0, r["Chiller1_kWh"])
c("kule sayacı KORUNDU", r["Kule1_kWh"] == 420.0, r["Kule1_kWh"])
c("trafo değeri KORUNDU", r["TRDP1_kWh"] == 8896.0, r["TRDP1_kWh"])

# 2) Gelen sütun BOŞ ise eski değer yedek olarak kalır
r = koru(yeni(), eski(), ["Su_Tuketimi_m3"]).iloc[0]
c("boş gelen alan eski değerini korur", r["Su_Tuketimi_m3"] == 0.0,
  r["Su_Tuketimi_m3"])

# 3) Bilerek sıfırlama: gelen 0 yazılır, eskiye dönmez
_e = eski()
_e.loc[0, "Su_Tuketimi_m3"] = 55.0
r = koru(yeni(Su_Tuketimi_m3=0.0), _e, ["Su_Tuketimi_m3"]).iloc[0]
c("elle sıfırlanan alan 0 kalır (eskiye dönmez)", r["Su_Tuketimi_m3"] == 0.0,
  r["Su_Tuketimi_m3"])

# 4) Yeni tarih / eşleşmeyen tarih: eski satır karışmaz
_baska = pd.DataFrame([dict(eski().iloc[0], Tarih=dt.date(2026, 6, 2))])
r = koru(yeni(Su_Tuketimi_m3=12.0), _baska, ["Su_Tuketimi_m3"]).iloc[0]
c("başka tarihin değeri kopyalanmaz", pd.isna(r["MCC1_kWh"]), r["MCC1_kWh"])

# 5) Eski tabloda aynı tarih birden çok kez varsa sonuncusu geçerli
_cift = pd.concat([eski(), pd.DataFrame([dict(eski().iloc[0], MCC1_kWh=9999.0)])],
                  ignore_index=True)
r = koru(yeni(Su_Tuketimi_m3=1.0), _cift, ["Su_Tuketimi_m3"]).iloc[0]
c("mükerrer tarihte son satır esas alınır", r["MCC1_kWh"] == 9999.0, r["MCC1_kWh"])

# ── upsert_by_date gerçekten bu korumayı çağırıyor mu? ───────────────────
_up = next((d for d in _agac.body
            if isinstance(d, ast.FunctionDef) and d.name == "upsert_by_date"), None)
_up_src = ast.get_source_segment(KAYNAK, _up) or ""
c("upsert_by_date korumayı çağırır", "_eski_degerleri_koru(" in _up_src)
c("gelen sütunlar ensure_schema'dan ÖNCE saklanır",
  _up_src.index("_gelen_sutunlar =") < _up_src.index("ensure_schema("))
c("aynı tarihin eski satırı korumaya verilir", "_ayni_tarih" in _up_src)

# ── Enerji diyagramı: en yeni gün üstte ──────────────────────────────────
c("gün listesi tersten sıralanır", 'dt.date.unique(), reverse=True)' in KAYNAK)
c("açılışta en yeni gün seçili",
  '"📅 Gün", options=_tarihler, index=0,' in KAYNAK)
c("eski 'en son index' kalıbı kalmadı",
  "options=_tarihler, index=len(_tarihler) - 1" not in KAYNAK)

# ── Bildirim çubuğu ──────────────────────────────────────────────────────
c("tümü okundu düğmesi var", '"✓✓ Tümü okundu"' in KAYNAK)
c("toplu okundu tek istekte yapılır", "okundu=eq.false" in KAYNAK and
  "_okundu_yap()" in KAYNAK)
c("tek tek okundu da aynı yardımcıyı kullanır", "_okundu_yap(_k[\"id\"])" in KAYNAK)
c("raporlar bildirim kaydına dönüşür", "def _rapor_kayitlari(" in KAYNAK)
c("rapor indirmesi çubuğun içinde", '"⬇️ İndir"' in KAYNAK)
c("indirilen otomatik rapor okundu işaretlenir",
  "_rapor_okundu_isaretle(_k.get(\"notif_anahtar\"))" in KAYNAK)
c("rapor rozeti şeritte sayılır", '"rapor": ("#1b7a3e"' in KAYNAK)
c("sayfa üstündeki yeşil rapor kutuları kaldırıldı",
  "auto-report-ready" not in KAYNAK
  and "Günlük rapor otomatik oluşturuldu!" not in KAYNAK
  and "özel PDF'iniz gönderilmek üzere" not in KAYNAK)
c("elle üretimde kullanıcı çubuğa yönlendirilir", "_rapor_toast" in KAYNAK)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g2 = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g2, len(T)))
raise SystemExit(1 if _g2 != len(T) else 0)
