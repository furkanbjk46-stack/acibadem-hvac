# -*- coding: utf-8 -*-
"""Aylık rapor bölümü: profil + bulgu defteri + ölçüm → ekran ve PDF'in ortak metni.

A3 (24.11.2026). app_portal ve pdf_generator yalnız bu modülün çıktısını gösterir.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from tasarruf import aliskanlik as A
from tasarruf.bulgular import BulguDefteri, DURUM_ETIKET, RET_NEDENLERI, olculebilirlik_hesaplayici

OLCUT_ADI = {"toplam": "toplam tüketim", "sogutma": "soğutma", "gaz": "kazan gazı", "su": "su",
             "gun_ici": "santral davranışı"}
OLCUM_ETIKET = {"dogrulandi": "Tasarruf doğrulandı", "belirsiz": "Belirsiz (hata payı içinde)",
                "artis": "Tüketim arttı", "olculemez": "Ölçülemez", "bekliyor": "Ölçüm dönemi doluyor"}
# A4: gün içi bulgularda kWh değil santral davranışı ölçülür
OLCUM_ETIKET_GUN_ICI = {"dogrulandi": "Uygulandığı doğrulandı", "belirsiz": "Kısmen değişti",
                        "artis": "Değişiklik görülmedi", "olculemez": "Ölçülemez", "bekliyor": "Ölçüm dönemi doluyor"}


def olculebilirlik_metni(o: Optional[Dict], olcut: Optional[str]) -> Optional[str]:
    if not olcut:
        return "Ölçüm yöntemi yok (santral okumalarıyla doğrulama gerekiyor)."
    if olcut == "gun_ici":
        return ("Ölçülebilir: uygulamadan önceki ve sonraki 14 günün santral okumaları karşılaştırılır "
                "(kWh değil, santralin davranışı ölçülür).")
    if not o or o.get("sonuc") == "bilinmiyor" or o.get("pay") is None:
        return None
    ad = OLCUT_ADI.get(olcut, olcut)
    pay = A.tr_sayi(o["pay"] * 100)
    bek = A.tr_sayi((o.get("beklenen_oran") or 0) * 100, 1)
    if o["pay"] > 0.5:
        return (f"Ölçülemez: {ad} günlük verisinde ölçüm hata payı %{pay}. Uygulansa da sonucu "
                "günlük sayaçlardan doğrulanamaz.")
    if o["sonuc"] == "olculemez":
        return (f"Ölçülemez: tahmini tasarruf {ad} tüketiminin %{bek}'i, ölçüm hata payı %{pay}. "
                "Uygulansa da sonucu günlük sayaçlardan doğrulanamaz.")
    return f"Ölçülebilir: tahmini tasarruf %{bek}, ölçüm hata payı %{pay}."


def olcum_metni(o: Optional[Dict]) -> str:
    if not o:
        return "Ölçüm dönemi doluyor"
    d = o.get("durum")
    if o.get("olcut") == "gun_ici":
        return f"{OLCUM_ETIKET_GUN_ICI.get(d, d)}: {o.get('aciklama', '')}"
    if d in ("dogrulandi", "belirsiz", "artis") and o.get("beklenen"):
        return (f"{OLCUM_ETIKET[d]}: beklenen {A.tr_sayi(o['beklenen'])}, gerçekleşen {A.tr_sayi(o['gercek'])} "
                f"{o.get('birim', '')} ({A.tr_yuzde(o['oran'])}, hata payı ±%{A.tr_sayi(o['hata_payi'] * 100)})")
    return f"{OLCUM_ETIKET.get(d, d)}: {o.get('aciklama', '')}"


def aylik_bolum(df: pd.DataFrame, yil: int, ay: int, defter: Optional[BulguDefteri] = None,
                olculebilirlik: bool = True, gun_ici=None) -> Dict:
    """gun_ici: (santral özeti, bina özeti) — tasarruf.gun_ici.ozetleri_guncelle(); yoksa gün içi bölüm boş."""
    from tasarruf import ogrenme as OG
    defter = defter or BulguDefteri()
    # A5: önce ölçümler güncellenir ki bu raporun güveni/eşiği son sonuçları içersin
    defter.olcumleri_guncelle(df, gun_ici=gun_ici)
    ogr = defter.ogrenme()
    s = A.profil(df, yil, ay, gun_ici=gun_ici, esik_carpani=OG.esik_carpanlari(ogr))
    m = A.rapor_metni(s)
    m["alt_bulgular"] = []
    m["ogrenme"] = []
    if s.get("yetersiz"):
        m["sonuclar"] = []
        return m
    hesapla = olculebilirlik_hesaplayici(df) if olculebilirlik else None
    gosterilecek = set(defter.profilden_guncelle(s, olculebilirlik_hesapla=hesapla))

    bulgular = []
    for b in m["bulgular"]:
        if b["kod"] not in gosterilecek:
            continue
        r = defter.kayitlar.get(b["kod"], {})
        b["kayit_durum"] = DURUM_ETIKET.get(r.get("durum"), r.get("durum"))
        b["olculebilirlik"] = olculebilirlik_metni(r.get("olculebilirlik"), r.get("olcut"))
        k = r.get("karar") or {}
        if k.get("karar") == "reddedildi":
            b["kayit_durum"] += f" — {RET_NEDENLERI.get(k.get('neden'), '')}"
        b["guven"] = OG.guven_metni(ogr, b["kod"])
        bulgular.append(b)
    bulgular = OG.sirala(bulgular, ogr)
    m["bulgular"] = bulgular[:OG.EN_FAZLA_BULGU]
    m["alt_bulgular"] = bulgular[OG.EN_FAZLA_BULGU:]

    # Öğrenme notları: susturulan kurallar, 'veri yanlış' reddi (veri kontrolüne gider)
    sus = OG.susturulan_kurallar(ogr)
    if sus:
        m["ogrenme"].append("Bu lokasyonda ölçümde tekrar tekrar tutmadığı için susturulan kurallar: "
                            + ", ".join(sus) + ".")
    for r in defter.kayitlar.values():
        for kg in r.get("karar_gecmisi") or []:
            if kg.get("karar") == "reddedildi" and kg.get("neden") == "veri_yanlis":
                m["kalite"].append(f"[KULLANICI] '{r.get('baslik', r.get('kod'))}' bulgusu {A.tr_tarih(kg.get('tarih'))} "
                                   f"tarihinde 'veri yanlış' diye reddedildi; ilgili sayaç verisini kontrol edin"
                                   + (f" ({kg['notlar']})" if kg.get("notlar") else "") + ".")
    es = s.get("esikler") or {}
    hs = es.get("hafta_sonu") or {}
    if hs.get("dogal") is not None:
        m["ogrenme"].append(f"Hafta sonu ısıtma eşiği bu lokasyon için %{hs['esik'] * 100:.0f} (hafta içi günler arası "
                            f"olağan fark %{hs['dogal'] * 100:.0f}"
                            + (f", geçmiş sonuçlarla {A.tr_sayi(hs['carpan'], 2)} kat" if hs.get("carpan", 1) > 1 else "")
                            + ").")

    sonuclar = []
    for r in defter.sonuclar():
        k = r.get("karar") or {}
        sonuclar.append({"Öneri": r.get("baslik"), "Uygulama": A.tr_tarih(k.get("uygulama_tarihi")),
                         "Tahmin edilen": (f"{A.tr_sayi(r['tasarruf']['deger'])} {r['tasarruf']['birim']}"
                                           if r.get("tasarruf") else "-"),
                         "Sonuç": olcum_metni(r.get("olcum"))})
    m["sonuclar"] = sonuclar
    return m
