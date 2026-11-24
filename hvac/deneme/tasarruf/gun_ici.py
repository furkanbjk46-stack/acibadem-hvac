# -*- coding: utf-8 -*-
"""
GÜN İÇİ PROFİL — 10 dakikalık AHU okumalarından santral alışkanlıkları
====================================================================

A4 (24.11.2026, tasarım: merkez/sunum/tasarruf_ogrenme_tasarimi.html §2, §7).

Günlük enerji verisi yalnız şüphe verir: "aynı gün kazan da soğutma da yüksek"
binada bir santralin ısıtıp diğerinin soğutmasıyla da olur (çevre / iç zon) — bu
normaldir. Asıl kayıp AYNI SANTRALDE ısıtma ve soğutma vanasının AYNI ANDA açık
olmasıdır. Bunu ancak 10 dakikalık okumalar gösterir
(veri/ahu_okuma_gecmis/ahu_bacnet_YYYYMMDD_HHMM.csv, lokasyon PC'sinde 90 gün saklanır).

Gün başına santral özeti (bir kez hesaplanıp veri/ahu_gun_ici_ozet.csv'ye eklenir;
13 bin dosya her raporda yeniden okunmaz):
  okuma        çalışma durumu bilinen okuma sayısı
  calisma      çalışan okuma oranı (Start/Stop = 1)
  gece         gece (22:00–06:00) okumalarında çalışma oranı
  cakisma_saat çalışırken ısıtma VE soğutma vanası > %10 olan süre (saat)
  isitma_saat / sogutma_saat  yalnız ısıtma / yalnız soğutma vanası açık süre
Bina düzeyi (aynı günde): en az bir santral ısıtırken başka bir santralin
soğuttuğu süre (karisik_saat) — bilgi amaçlı, kayıp sayılmaz.

Zaman aşımına uğramış okumalar (Durum != OK) kullanılmaz.
Ameliyathane / nem kontrollü santrallerde soğutup yeniden ısıtma (reheat) bilinçli
olabilir; bulgu metni bunu söyler, karar teknik ekibindir.
"""
from __future__ import annotations

import glob
import logging
import os
import re
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

VANA_ESIK = 10.0              # % — vana "açık" sayılır
OKUMA_DK = 10                 # okuma aralığı (dakika)
GECE_SAATLER = set(range(22, 24)) | set(range(0, 6))
ONEMLI_CAKISMA_SAAT = 1.0     # günde bu kadar saatten fazla çakışma "önemli gün"
SUREKLI_ORAN = 0.30           # santralin günlerinin bu kadarında önemli çakışma → bulgu
GECE_ORAN = 0.90              # gece okumalarının bu kadarında çalışıyor
GECE_GUN_ORAN = 0.80          # ve günlerin bu kadarında → "sürekli çalışıyor"
EN_AZ_GUN = 5
PENCERE_GUN = 90              # ham dosyalar lokasyonda 90 gün saklanır
_DOSYA = re.compile(r"ahu_bacnet_(\d{8})_(\d{4})\.csv$")
OZET_SUTUNLAR = ["Tarih", "Lokasyon", "AHU", "okuma", "calisma", "gece", "cakisma_saat",
                 "isitma_saat", "sogutma_saat"]
BINA_SUTUNLAR = ["Tarih", "karisik_saat", "okuma_zamani"]


def varsayilan_yollar():
    import yollar
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return (yollar.yol("veri/ahu_okuma_gecmis", kok), yollar.yol("veri/ahu_gun_ici_ozet.csv", kok),
            yollar.yol("veri/ahu_gun_ici_bina.csv", kok))


def _gun_dosyalari(klasor: str) -> Dict[str, List[str]]:
    gunler: Dict[str, List[str]] = {}
    for p in glob.glob(os.path.join(klasor, "ahu_bacnet_*.csv")):
        m = _DOSYA.search(os.path.basename(p))
        if m:
            gunler.setdefault(m.group(1), []).append(p)
    return gunler


def _sayi(seri: pd.Series) -> pd.Series:
    return pd.to_numeric(seri.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def gun_ozeti(dosyalar: List[str]):
    """Bir günün 10 dk dosyaları → (santral özeti, bina özeti)."""
    parcalar = []
    for p in sorted(dosyalar):
        try:
            d = pd.read_csv(p, dtype=str, encoding="utf-8", encoding_errors="replace")
        except Exception as e:
            logger.debug(f"{p} okunamadı: {e}")
            continue
        if {"Timestamp", "AHU_Adi", "Nokta_Tipi", "Deger"} - set(d.columns):
            continue
        parcalar.append(d)
    if not parcalar:
        return None, None
    d = pd.concat(parcalar, ignore_index=True)
    if "Durum" in d.columns:
        d = d[d["Durum"].fillna("OK").str.upper() == "OK"]
    d["deger"] = _sayi(d["Deger"])
    d["Lokasyon"] = d.get("Lokasyon", pd.Series("", index=d.index)).fillna("")
    tip = d["Nokta_Tipi"].fillna("")
    d["nokta"] = np.select([tip.str.startswith("Cool Valve"), tip.str.startswith("Heat Valve"),
                            tip.str.startswith("Start")], ["sog", "isi", "calis"], "")
    d = d[d["nokta"] != ""]
    if d.empty:
        return None, None
    g = d.pivot_table(index=["Timestamp", "Lokasyon", "AHU_Adi"], columns="nokta", values="deger",
                      aggfunc="last").reset_index()
    for c in ("sog", "isi", "calis"):
        if c not in g.columns:
            g[c] = np.nan
    zaman = pd.to_datetime(g["Timestamp"], format="%Y%m%d %H%M", errors="coerce")
    g["saat"] = zaman.dt.hour
    g = g[g["calis"].notna()]
    if g.empty:
        return None, None
    calis = g["calis"] >= 0.5
    sog = (g["sog"] > VANA_ESIK) & calis
    isi = (g["isi"] > VANA_ESIK) & calis
    g["cakisma"] = sog & isi
    g["yalniz_isi"] = isi & ~sog
    g["yalniz_sog"] = sog & ~isi
    g["calis_b"] = calis
    g["gece_b"] = g["saat"].isin(GECE_SAATLER)
    adim = OKUMA_DK / 60.0
    grp = g.groupby(["Lokasyon", "AHU_Adi"])
    oz = pd.DataFrame({
        "okuma": grp.size(),
        "calisma": grp["calis_b"].mean(),
        "gece": g[g["gece_b"]].groupby(["Lokasyon", "AHU_Adi"])["calis_b"].mean(),
        "cakisma_saat": grp["cakisma"].sum() * adim,
        "isitma_saat": grp["yalniz_isi"].sum() * adim,
        "sogutma_saat": grp["yalniz_sog"].sum() * adim,
    }).reset_index().rename(columns={"AHU_Adi": "AHU"})
    # Bina: aynı okumada bir santral ısıtıyor, başka biri soğutuyor
    z = g.groupby("Timestamp").agg(i=("yalniz_isi", "any"), s=("yalniz_sog", "any"))
    bina = {"karisik_saat": float((z["i"] & z["s"]).sum() * adim), "okuma_zamani": int(len(z))}
    return oz, bina


def ozetleri_guncelle(klasor: Optional[str] = None, ozet_yol: Optional[str] = None,
                      bina_yol: Optional[str] = None, bugun: Optional[str] = None):
    """Özetlenmemiş (ve bugünden önceki) günleri işler. Döner: (santral özeti, bina özeti) tabloları."""
    vk, vo, vb = varsayilan_yollar() if not (klasor and ozet_yol and bina_yol) else (None, None, None)
    klasor, ozet_yol, bina_yol = klasor or vk, ozet_yol or vo, bina_yol or vb
    bugun = bugun or pd.Timestamp.now().strftime("%Y%m%d")
    oz = pd.read_csv(ozet_yol, dtype={"Tarih": str}) if os.path.exists(ozet_yol) else pd.DataFrame(columns=OZET_SUTUNLAR)
    bn = pd.read_csv(bina_yol, dtype={"Tarih": str}) if os.path.exists(bina_yol) else pd.DataFrame(columns=BINA_SUTUNLAR)
    var = set(oz["Tarih"].astype(str)) | set(bn["Tarih"].astype(str))
    yeni_oz, yeni_bn = [], []
    for gun, dosyalar in sorted(_gun_dosyalari(klasor).items()):
        if gun >= bugun or gun in var:
            continue                     # bugün henüz bitmedi; işlenmiş gün tekrar işlenmez
        o, b = gun_ozeti(dosyalar)
        if o is None:
            continue
        o.insert(0, "Tarih", gun)
        yeni_oz.append(o)
        yeni_bn.append({"Tarih": gun, **b})
    if yeni_oz:
        oz = pd.concat([oz] + yeni_oz, ignore_index=True)[OZET_SUTUNLAR]
        bn = pd.concat([bn, pd.DataFrame(yeni_bn)], ignore_index=True)[BINA_SUTUNLAR]
        try:
            os.makedirs(os.path.dirname(ozet_yol), exist_ok=True)
            for tablo, yol in ((oz, ozet_yol), (bn, bina_yol)):
                gecici = yol + ".tmp"
                tablo.to_csv(gecici, index=False, encoding="utf-8")
                os.replace(gecici, yol)
        except Exception as e:
            logger.error(f"Gün içi özet yazılamadı: {e}")
    oz["Tarih"] = pd.to_datetime(oz["Tarih"].astype(str), format="%Y%m%d")
    bn["Tarih"] = pd.to_datetime(bn["Tarih"].astype(str), format="%Y%m%d")
    return oz, bn


def profil(oz: pd.DataFrame, bn: pd.DataFrame, bas=None, son=None,
           supheli_gunler: Optional[List[str]] = None) -> Dict:
    """Pencere içindeki gün içi alışkanlıklar."""
    if bas is not None:
        oz, bn = oz[oz["Tarih"] >= pd.Timestamp(bas)], bn[bn["Tarih"] >= pd.Timestamp(bas)]
    if son is not None:
        oz, bn = oz[oz["Tarih"] <= pd.Timestamp(son)], bn[bn["Tarih"] <= pd.Timestamp(son)]
    gunler = sorted(oz["Tarih"].dt.date.unique())
    sonuc = {"gun": len(gunler), "ilk": str(gunler[0]) if gunler else None,
             "son": str(gunler[-1]) if gunler else None, "santral": [], "supheli": None}
    if not gunler:
        return sonuc
    oz = oz.copy()
    oz["onemli"] = oz["cakisma_saat"] > ONEMLI_CAKISMA_SAAT
    oz["sabah_gece"] = oz["gece"] >= GECE_ORAN
    for (lok, ahu), s in oz.groupby(["Lokasyon", "AHU"]):
        n = len(s)
        sonuc["santral"].append({
            "lokasyon": lok, "ahu": ahu, "gun": n,
            "cakisma_gun_orani": float(s["onemli"].mean()),
            "cakisma_saat_gun": float(s["cakisma_saat"].mean()),
            "calisma": float(s["calisma"].mean()),
            "gece_calisan_gun_orani": float(s["sabah_gece"].mean()) if s["gece"].notna().any() else None,
        })
    sonuc["santral"].sort(key=lambda x: -x["cakisma_saat_gun"])
    sonuc["toplam_cakisma_saat_gun"] = float(oz.groupby("Tarih")["cakisma_saat"].sum().mean())
    sonuc["karisik_saat_gun"] = float(bn["karisik_saat"].mean()) if len(bn) else None

    if supheli_gunler:
        gun_cak = oz.groupby(oz["Tarih"].dt.date)["cakisma_saat"].sum()
        on = oz[oz["onemli"]]
        gun_cak_ad = on.groupby(on["Tarih"].dt.date).apply(
            lambda x: sorted(f"{l} {a}".strip() for l, a in zip(x["Lokasyon"], x["AHU"]))).to_dict()
        ayrim = {"veri_var": 0, "santralde_cakisma": 0, "yalniz_zon": 0, "veri_yok": 0, "gunler": []}
        for t in supheli_gunler:
            gd = pd.Timestamp(t).date()
            if gd not in gun_cak.index:
                ayrim["veri_yok"] += 1
                continue
            ayrim["veri_var"] += 1
            adlar = gun_cak_ad.get(gd, [])
            tur = "santralde_cakisma" if adlar else "yalniz_zon"
            ayrim[tur] += 1
            ayrim["gunler"].append({"tarih": str(gd), "tur": tur, "santral": len(adlar), "santraller": adlar,
                                    "cakisma_saat": round(float(gun_cak[gd]), 1)})
        sonuc["supheli"] = ayrim
    return sonuc


def bulgular(gp: Dict, carpan: float = 1.0) -> List[Dict]:
    """Gün içi profilden bulgu adayları (aliskanlik bulgu biçiminde).
    carpan (A5): vana çakışması bu lokasyonda tutmadıysa sürekli sayılma oranı yükselir."""
    from tasarruf.aliskanlik import tr_sayi
    b = []
    if gp.get("gun", 0) < EN_AZ_GUN:
        return b
    oran_esik = min(0.9, SUREKLI_ORAN * carpan)
    surekli = [s for s in gp["santral"] if s["gun"] >= EN_AZ_GUN and s["cakisma_gun_orani"] >= oran_esik]
    if surekli:
        liste = ", ".join(f"{s['lokasyon']} {s['ahu']} ({tr_sayi(s['cakisma_saat_gun'], 1)} sa/gün, "
                          f"gün oranı %{s['cakisma_gun_orani'] * 100:.0f})"
                          for s in surekli[:8])
        b.append({
            "kod": "VANA_CAKISMASI", "baslik": "Aynı santralde ısıtma ve soğutma vanası birlikte açık",
            "kanit": (f"Son {gp['gun']} günün 10 dakikalık okumalarında {len(surekli)} santral, çalıştığı günlerin "
                      f"en az %{oran_esik * 100:.0f} kadarında günde 1 saatten fazla ısıtma ve soğutma vanası aynı anda "
                      f"%{VANA_ESIK:.0f} üzerinde açık: {liste}."),
            "oneri": ("Bu santrallerde vana sıralamasını (ısıtma ve soğutma arasında ölü bant), set değerlerini ve "
                      "vana/aktüatör arızasını kontrol edin. Ameliyathane veya nem kontrollü santrallerde "
                      "soğutup yeniden ısıtma bilinçli olabilir; bunlar için 'uygulanamaz' seçin."),
            "tasarruf": None, "durum": "aday", "supheli_olcutler": [],
            "not": "Tasarruf hesaplanmadı: santral hava debisi ve batarya gücü bilinmiyor.",
            "santraller": [f"{s['lokasyon']} {s['ahu']}".strip() for s in surekli]})
    gece = [s for s in gp["santral"] if s["gun"] >= EN_AZ_GUN and (s["gece_calisan_gun_orani"] or 0) >= GECE_GUN_ORAN]
    if gece:
        b.append({
            "kod": "GECE_SUREKLI_CALISMA", "baslik": "Santraller gece de sürekli çalışıyor",
            "kanit": (f"{len(gece)} santral, son {gp['gun']} günün en az %{GECE_GUN_ORAN * 100:.0f} kadarında gece "
                      f"22:00–06:00 arasında neredeyse kesintisiz (okumaların %{GECE_ORAN * 100:.0f} ve fazlası) çalışıyor: "
                      + ", ".join(f"{s['lokasyon']} {s['ahu']}" for s in gece[:12])
                      + (f" ve {len(gece) - 12} santral daha" if len(gece) > 12 else "") + "."),
            "oneri": ("7/24 hizmet vermeyen alanlara (poliklinik, idari, eğitim) bakan santraller için gece ve hafta "
                      "sonu çalışma programı ya da düşük devir tanımlayın. Yoğun bakım, ameliyathane, acil gibi "
                      "alanlar için 'uygulanamaz' seçin."),
            "tasarruf": None, "durum": "aday", "supheli_olcutler": [],
            "not": "Tasarruf hesaplanmadı: santral fan gücü bilinmiyor.",
            "santraller": [f"{s['lokasyon']} {s['ahu']}".strip() for s in gece]})
    return b


def metin_satirlari(gp: Dict) -> List[str]:
    """Rapordaki 'Gün içi' satırları."""
    from tasarruf.aliskanlik import tr_sayi, tr_tarih
    if not gp.get("gun"):
        return ["Gün içi (10 dakikalık) santral verisi yok."]
    s = [f"Gün içi santral verisi: {tr_tarih(gp['ilk'])} – {tr_tarih(gp['son'])} ({gp['gun']} gün, "
         f"{len(gp['santral'])} santral)."]
    s.append(f"Aynı santralde ısıtma ve soğutma vanası birlikte açık: bina toplamı günde ortalama "
             f"{tr_sayi(gp['toplam_cakisma_saat_gun'], 1)} santral-saat.")
    if gp.get("karisik_saat_gun") is not None:
        s.append(f"Binada bir santral ısıtırken başkasının soğuttuğu süre: günde ortalama "
                 f"{tr_sayi(gp['karisik_saat_gun'], 1)} saat (zonlar arası; tek başına kayıp değildir).")
    sp = gp.get("supheli")
    if sp and sp["veri_var"]:
        s.append(f"Günlük veride 'aynı gün ısıtma ve soğutma yüksek' görünen günlerden {sp['veri_var']} tanesinin "
                 f"gün içi verisi var: {sp['santralde_cakisma']} gün aynı santralde vana çakışması, "
                 f"{sp['yalniz_zon']} gün yalnız zonlar arası (farklı santraller)."
                 + (f" {sp['veri_yok']} günün gün içi verisi yok." if sp["veri_yok"] else ""))
    elif sp:
        s.append(f"Günlük veride 'aynı gün ısıtma ve soğutma yüksek' görünen {sp['veri_yok']} günün hiçbirinde "
                 f"gün içi santral verisi yok; bu şüphe henüz doğrulanamadı.")
    return s


# ── ölçüm: uygulama öncesi / sonrası (santral davranışı, kWh değil) ──────
OLCUM_GUN = 14
OLCUM_EN_AZ_GUN = 7
OLCUM_HEDEF_AZALMA = 0.50     # çakışma süresi / gece çalışması en az yarıya inmeli


def _olcu_serisi(oz: pd.DataFrame, kod: str, santraller: Optional[List[str]] = None) -> Optional[pd.Series]:
    if santraller:
        ad = (oz["Lokasyon"].fillna("").astype(str) + " " + oz["AHU"].astype(str)).str.strip()
        oz = oz[ad.isin(santraller)]
    if kod in ("VANA_CAKISMASI", "ES_ZAMANLI_ISITMA_SOGUTMA"):
        return oz.groupby("Tarih")["cakisma_saat"].sum()
    if kod == "GECE_SUREKLI_CALISMA":
        return oz.groupby("Tarih")["gece"].mean()
    return None


def olc(oz: pd.DataFrame, kod: str, uygulama, gun: int = OLCUM_GUN,
        santraller: Optional[List[str]] = None) -> Dict:
    """Gün içi bulgusu: uygulamadan önceki ve sonraki 'gun' gün karşılaştırılır."""
    from tasarruf.aliskanlik import tr_sayi, tr_yuzde
    cakisma = kod != "GECE_SUREKLI_CALISMA"
    birim = "santral-saat/gün" if cakisma else "gece çalışma oranı"
    sonuc = {"durum": "bekliyor", "olcut": "gun_ici", "birim": birim,
             "uygulama": str(pd.Timestamp(uygulama).date()), "gun": gun, "beklenen": None, "gercek": None,
             "tasarruf": None, "oran": None, "hata_payi": None, "yontem": "gun_ici_once_sonra", "aciklama": ""}
    seri = _olcu_serisi(oz, kod, santraller) if len(oz) else None
    if seri is None:
        sonuc.update(durum="olculemez", aciklama="Bu bulgu için gün içi ölçü yok.")
        return sonuc
    u = pd.Timestamp(uygulama)
    once = seri[(seri.index < u) & (seri.index >= u - pd.Timedelta(days=gun))].dropna()
    sonra = seri[(seri.index > u) & (seri.index <= u + pd.Timedelta(days=gun))].dropna()
    if len(once) < OLCUM_EN_AZ_GUN:
        sonuc.update(durum="olculemez",
                     aciklama=f"Uygulamadan önceki {gun} günde yalnız {len(once)} günlük santral verisi var.")
        return sonuc
    if len(sonra) < OLCUM_EN_AZ_GUN:
        sonuc["aciklama"] = f"Uygulamadan sonra {len(sonra)} gün veri var; en az {OLCUM_EN_AZ_GUN} gün gerekiyor."
        return sonuc
    o, s = float(once.mean()), float(sonra.mean())
    sonuc.update(gercek=s, oran=(s / o - 1) if o > 0 else None)
    if cakisma:
        def fmt(x):
            return f"{tr_sayi(x, 1)} santral-saat/gün"
    else:
        def fmt(x):
            return f"%{tr_sayi(x * 100)}"
    ozet = f"önce {fmt(o)}, sonra {fmt(s)}" + (f" ({tr_yuzde(sonuc['oran'])})" if sonuc["oran"] is not None else "")
    if o <= 0:
        sonuc.update(durum="belirsiz", aciklama=f"Uygulamadan önce de ölçü sıfırdı ({ozet}).")
    elif s <= o * (1 - OLCUM_HEDEF_AZALMA):
        sonuc.update(durum="dogrulandi", aciklama=f"Santral davranışı değişti: {ozet}.")
    elif s >= o:
        sonuc.update(durum="artis", aciklama=f"Santral davranışı değişmedi: {ozet}.")
    else:
        sonuc.update(durum="belirsiz", aciklama=f"Azalma var ama yarıya inmedi: {ozet}.")
    return sonuc
