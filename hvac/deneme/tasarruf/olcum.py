# -*- coding: utf-8 -*-
"""
ÖLÇÜM — uygulanan öneri gerçekten tasarruf ettirdi mi?
=====================================================

A3 (24.11.2026, tasarım: merkez/sunum/tasarruf_ogrenme_tasarimi.html §4).

"Uygulandı" denmesi tasarruf demek değildir. Ölçüm, Tüketim Tahmini'nin günlük
modelini (tuketim_tahmin/gunluk_model.py) kullanır:

  1) Model UYGULAMA TARİHİNE KADARKİ veriyle eğitilir (sonrasını görmez).
  2) Sonraki N günün (varsayılan 28) "öneri uygulanmasaydı" tüketimi, o günlerin
     ÖLÇÜLEN havasıyla (ısıtma gazında ayrıca gerçekleşen kojen üretimiyle)
     tahmin edilir.
  3) Tasarruf = beklenen − gerçekleşen (yalnız geçerli günler).

Hata payı: aynı yöntem, uygulamadan ÖNCEKİ 6 dönemde (hiçbir şey değişmemişken)
çalıştırılır; bu "plasebo" ölçümlerin hatasının kareler ortalamasının karekökü ×2,5 ya da
en büyük mutlak hatası (hangisi büyükse) hata payıdır (en az %2). Fark hata payının içindeyse sonuç "belirsiz"dir ve
tasarruf diye yazılmaz; pay %50'yi aşarsa "ölçülemez"dir. Hava ve takvim etkisi modelde; mevsim geçişindeki
olağan hata da plasebo ölçümlere yansıdığı için payın içinde kalır.

Modeli olmayan ölçütte (su) hava düzeltmesi yapılmaz: uygulama öncesi 8 hafta
ile sonrası gün tipine göre kıyaslanır, hata payı önceki haftaların dalgalanmasından.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

OLCUM_GUN = 28
PLASEBO_SAYI = 6
EN_AZ_PAY = 0.02
EN_AZ_GECERLI = 0.8        # ölçüm döneminde geçerli gün oranı
EN_AZ_GECMIS = 365         # modelin mevsimi öğrenmesi için

MODEL_HEDEF = {"toplam": "toplam", "sogutma": "sogutma", "gaz": "isitma_gaz"}
BIRIM = {"toplam": "kWh", "sogutma": "kWh", "gaz": "m³", "su": "m³"}


def _gunluk(df: pd.DataFrame, haric: Optional[List[Dict]] = None) -> pd.DataFrame:
    from tuketim_tahmin import portal_ozet
    g, _ = portal_ozet.birlestir(df, haric=haric)
    return g


def _model_dongusu(g: pd.DataFrame, hedef: str, bas: pd.Timestamp, gun: int) -> Optional[Dict]:
    """bas'a kadar eğit, [bas, bas+gun) tahmin et; gerçekleşenle kıyasla."""
    from tuketim_tahmin.gunluk_model import GunlukTahminModeli, ISTEGE_BAGLI
    son = bas + pd.Timedelta(days=gun - 1)
    gecerli_hedef = g[hedef].notna() & (g["hedef_gecerli"] if hedef == "toplam" else True)
    ilk = g.loc[gecerli_hedef, "tarih"].min()
    if pd.isna(ilk) or (bas - ilk).days < EN_AZ_GECMIS:
        return None
    donem = g[(g["tarih"] >= bas) & (g["tarih"] <= son)]
    gecerli = donem[donem[hedef].notna() & (donem["hedef_gecerli"] if hedef == "toplam" else True)]
    if len(gecerli) < EN_AZ_GECERLI * gun:
        return None
    m = GunlukTahminModeli(hedef=hedef)
    m.egit(g, bitis=bas)
    kol = ["T"] + [c for c in ISTEGE_BAGLI if c in donem.columns]
    if hedef == "isitma_gaz" and "kojen" in m.secilen:
        kol.append("kojen")
    hava = donem[kol].copy()
    hava.insert(0, "Tarih", donem["tarih"].values)
    tah = m.gunluk_tahmin(bas, son, hava=hava).set_index("tarih")["tuketim"]
    gercek = gecerli.set_index("tarih")[hedef]
    beklenen = tah.reindex(gercek.index)
    return {"beklenen": float(beklenen.sum()), "gercek": float(gercek.sum()), "gun": int(len(gercek)),
            "gunluk": pd.DataFrame({"beklenen": beklenen, "gercek": gercek})}


YEREL_GUN = 56            # yerel model: uygulamadan önceki 8 hafta


def _yerel_dongusu(g: pd.DataFrame, hedef: str, bas: pd.Timestamp, gun: int) -> Optional[Dict]:
    """Yerel hava modeli: yalnız bas'tan önceki 8 haftaya kurulur (eski yılların
    rejimi karışmaz). hedef ~ CDD + HDD + cumartesi + pazar + tatil (+ kojen, gazda)."""
    from sklearn.linear_model import Ridge
    from tuketim_tahmin.takvim import tatil_serisi
    son = bas + pd.Timedelta(days=gun - 1)
    d = g[(g["tarih"] >= bas - pd.Timedelta(days=YEREL_GUN)) & (g["tarih"] <= son)].copy()
    d = d[d[hedef].notna() & d["T"].notna() & (d["hedef_gecerli"] if hedef == "toplam" else True)]
    if len(d) < 0.7 * YEREL_GUN:
        return None
    d["tatil_"] = tatil_serisi(d["tarih"]).values

    def X(x):
        o = pd.DataFrame({"CDD": (x["T"] - 18).clip(lower=0), "HDD": (16 - x["T"]).clip(lower=0),
                          "cmt": (x["tarih"].dt.dayofweek == 5).astype(float),
                          "pzr": (x["tarih"].dt.dayofweek == 6).astype(float), "tatil": x["tatil_"]})
        if hedef == "isitma_gaz" and x["kojen"].notna().all():
            o["kojen"] = x["kojen"].values
        return o
    egt, tst = d[d["tarih"] < bas], d[d["tarih"] >= bas]
    if len(egt) < 0.7 * YEREL_GUN or len(tst) < EN_AZ_GECERLI * gun:
        return None
    Xe, Xt = X(egt), X(tst)
    ortak = [c for c in Xe.columns if c in Xt.columns]
    m = Ridge(alpha=1.0).fit(Xe[ortak], egt[hedef])
    beklenen = pd.Series(np.clip(m.predict(Xt[ortak]), 0, None), index=tst["tarih"].values)
    gercek = tst.set_index("tarih")[hedef]
    return {"beklenen": float(beklenen.sum()), "gercek": float(gercek.sum()), "gun": int(len(gercek)),
            "gunluk": pd.DataFrame({"beklenen": beklenen.values, "gercek": gercek.values}, index=gercek.index)}


YONTEMLER = {"model": _model_dongusu, "yerel": _yerel_dongusu}


PAY_KATSAYI = 2.5
EN_FAZLA_PAY = 0.50
KOJEN_DEGISIM = 0.30        # kojen çalışan gün oranı bu kadar değiştiyse gaz ölçülmez


def hata_payi(plasebo: List[float]) -> float:
    """Plasebo hatalarından hata payı: 2,5 × RMS ya da en büyük mutlak hata (hangisi büyükse),
    en az %2.

    Sınama (Maslak, 05.2025–10.2026, 14 günde bir 39 tarih, bilinen değişiklik yok):
    2 × RMS ile yanlış "doğrulandı" toplamda 2, soğutmada 2, gazda 6 tarih; 2,5 × RMS ile
    1 / 0 / 4. Toplamda %10'luk eklenmiş etki 2,5 × RMS ile de yakalanıyor (pay ~%7)."""
    rms = float(np.sqrt(np.mean(np.square(plasebo))))
    return max(EN_AZ_PAY, PAY_KATSAYI * rms, float(np.max(np.abs(plasebo))))


def _plasebo(g, hedef, uyg, gun, dongu) -> List[float]:
    hatalar = []
    for k in range(1, PLASEBO_SAYI + 1):
        p = dongu(g, hedef, uyg - pd.Timedelta(days=gun * k), gun)
        if p and p["beklenen"] > 0:
            hatalar.append((p["beklenen"] - p["gercek"]) / p["beklenen"])
    return hatalar


def olc(df: pd.DataFrame, olcut: str, uygulama, gun: int = OLCUM_GUN,
        haric: Optional[List[Dict]] = None, g: Optional[pd.DataFrame] = None) -> Dict:
    """Uygulama tarihinden sonraki `gun` günün tasarrufu.

    Döner: durum ('dogrulandi' | 'artis' | 'belirsiz' | 'olculemez' | 'bekliyor'),
    beklenen, gercek, tasarruf, oran, hata_payi, plasebo listesi, aciklama.
    """
    uyg = pd.Timestamp(uygulama).normalize()
    if olcut == "su":
        return _olc_su(df, uyg, gun)
    if olcut not in MODEL_HEDEF:
        return {"durum": "olculemez", "aciklama": f"{olcut} için ölçüm yöntemi yok."}
    hedef = MODEL_HEDEF[olcut]
    if g is None:
        g = _gunluk(df, haric=haric)
    son_veri = g.loc[g[hedef].notna(), "tarih"].max()
    if pd.isna(son_veri) or son_veri < uyg + pd.Timedelta(days=gun - 1):
        kalan = gun if pd.isna(son_veri) else max(0, (uyg + pd.Timedelta(days=gun - 1) - son_veri).days)
        return {"durum": "bekliyor", "aciklama": f"Ölçüm için {kalan} gün daha veri gerekiyor."}

    # Kazan gazı kojen atık ısısına bağlı: kojen düzeni ölçüm döneminde değiştiyse gaz farkı
    # öneriye değil kojene aittir (Maslak 07.2026: kojen dönünce gaz 2.400 → 300 m³/gün).
    if hedef == "isitma_gaz" and g["kojen"].notna().any():
        kj = g.set_index("tarih")["kojen"]
        once = (kj[uyg - pd.Timedelta(days=YEREL_GUN): uyg - pd.Timedelta(days=1)] > 1000).mean()
        sonra = (kj[uyg: uyg + pd.Timedelta(days=gun - 1)] > 1000).mean()
        if pd.notna(once) and pd.notna(sonra) and abs(sonra - once) > KOJEN_DEGISIM:
            return {"durum": "olculemez", "olcut": olcut, "birim": BIRIM[olcut], "uygulama": str(uyg.date()),
                    "aciklama": (f"Kojen düzeni değişti (çalışan gün oranı %{once * 100:.0f} → %{sonra * 100:.0f}); "
                                 "kazan gazındaki fark öneriye bağlanamaz.")}

    # Yöntem seçimi ÖLÇÜM DÖNEMİNE BAKMADAN yapılır: uygulama öncesi plasebo
    # ölçümlerinde hata payı en küçük olan yöntem kullanılır.
    adaylar = []
    for ad, dongu in YONTEMLER.items():
        pl = _plasebo(g, hedef, uyg, gun, dongu)
        if len(pl) >= 3:
            adaylar.append((hata_payi(pl), ad, pl))
    if adaylar:
        pay, yontem, plasebo = min(adaylar)
    else:
        pay, yontem, plasebo = None, "model", []
    ana = YONTEMLER[yontem](g, hedef, uyg, gun)
    if ana is None and yontem != "model":
        yontem, ana = "model", _model_dongusu(g, hedef, uyg, gun)
    if ana is None:
        return {"durum": "olculemez",
                "aciklama": "Uygulamadan önce en az 1 yıl veri ya da ölçüm döneminde yeterli geçerli gün yok."}

    tasarruf = ana["beklenen"] - ana["gercek"]
    oran = tasarruf / ana["beklenen"] if ana["beklenen"] > 0 else 0.0
    if pay is None:
        durum, acik = "belirsiz", "Hata payı hesaplanamadı (uygulama öncesi yeterli dönem yok)."
    elif pay > EN_FAZLA_PAY:
        # Maslak kazan gazı: pay %60–96 — günlük model bu kalemi ölçemez (kojen etkileşimi);
        # bu payla çıkan "doğrulandı" rastlantıdır (sınamada 39 tarihin 4'ü).
        durum, acik = "olculemez", (f"Bu kalemde günlük ölçümün hata payı %{pay * 100:.0f}; "
                                    "bu kadar gürültülü veriden tasarruf ya da artış sonucu çıkarılmaz.")
    elif oran > pay:
        durum, acik = "dogrulandi", "Tüketim, hava ve takvim düzeltmeli beklentinin hata payından fazla altında."
    elif oran < -pay:
        durum, acik = "artis", "Tüketim beklentinin hata payından fazla üstünde."
    else:
        durum, acik = "belirsiz", "Fark modelin olağan hata payı içinde; tasarruf diye yazılmaz."
    return {"durum": durum, "olcut": olcut, "birim": BIRIM[olcut], "uygulama": str(uyg.date()),
            "gun": ana["gun"], "beklenen": ana["beklenen"], "gercek": ana["gercek"],
            "tasarruf": tasarruf, "oran": oran, "hata_payi": pay,
            "plasebo": [round(x, 4) for x in plasebo], "yontem": yontem, "aciklama": acik,
            "gunluk": ana["gunluk"]}


def _olc_su(df: pd.DataFrame, uyg: pd.Timestamp, gun: int) -> Dict:
    from tuketim_tahmin.takvim import tatil_serisi
    d = pd.DataFrame({"tarih": pd.to_datetime(df["Tarih"], errors="coerce"),
                      "su": pd.to_numeric(df.get("Su_Tuketimi_m3"), errors="coerce")}).dropna()
    d = d[~(tatil_serisi(d["tarih"]).values > 0)]
    d["tip"] = np.where(d["tarih"].dt.dayofweek >= 5, "hafta_sonu", "hafta_ici")
    once = d[(d["tarih"] >= uyg - pd.Timedelta(days=56)) & (d["tarih"] < uyg)]
    sonra = d[(d["tarih"] >= uyg) & (d["tarih"] < uyg + pd.Timedelta(days=gun))]
    if d["tarih"].max() < uyg + pd.Timedelta(days=gun - 1):
        return {"durum": "bekliyor", "aciklama": "Ölçüm dönemi henüz dolmadı."}
    if len(once) < 30 or len(sonra) < EN_AZ_GECERLI * gun * 5 / 7:
        return {"durum": "olculemez", "aciklama": "Su verisi yetersiz."}
    beklenen = float(sum(once.loc[once["tip"] == t, "su"].mean() * (sonra["tip"] == t).sum()
                         for t in ("hafta_ici", "hafta_sonu")))
    gercek = float(sonra["su"].sum())
    haftalik = once.groupby(once["tarih"].dt.isocalendar().week)["su"].mean()
    pay = max(EN_AZ_PAY, 2 * float(haftalik.std() / haftalik.mean())) if len(haftalik) >= 4 else 0.1
    oran = (beklenen - gercek) / beklenen if beklenen > 0 else 0.0
    durum = "dogrulandi" if oran > pay else ("artis" if oran < -pay else "belirsiz")
    return {"durum": durum, "olcut": "su", "birim": "m³", "uygulama": str(uyg.date()),
            "gun": int(len(sonra)), "beklenen": beklenen, "gercek": gercek, "tasarruf": beklenen - gercek,
            "oran": oran, "hata_payi": pay, "plasebo": [], "yontem": "once_sonra",
            "aciklama": "Su modeli yok: önceki 8 hafta ile gün tipine göre kıyas (hava düzeltmesiz)."}
