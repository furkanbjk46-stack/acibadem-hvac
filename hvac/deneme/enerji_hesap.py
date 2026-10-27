# -*- coding: utf-8 -*-
"""
ENERJİ TÜRETİM HESABI — TEK KAYNAK
==================================

Şebeke / toplam hastane / soğutma / diğer yük sütunları burada hesaplanır.
İki yer kullanır:
  * app_portal.recalc()  → portal açıldığında CSV'yi düzeltir
  * cloud_sync           → Supabase'e GÖNDERMEDEN ÖNCE uygular

İkincisi şart: eskiden hesap yalnızca portal açılınca çalışıyordu, kimse
portalı açmazsa eski (yanlış) değerler buluta gitmeye devam ediyordu.

KURAL (27.09.2026):
  Şebeke = girilen TRDP'lerin toplamı — bir tanesi bile olsa.
           Alt kırılımlar (MCC / Chiller) yedek olarak KULLANILMAZ.
  Toplam = Şebeke + Kojen Üretim

Neden alt sayaç yedeği yok: MCC ve Chiller analizörleri kaynağa bakmadan
TÜKETİMİ ölçer; kojen çalışırken o yükleri kojen besler. Yedek bunu
"şebekeden çekildi" sayıp üstüne Kojen Üretim de eklenince aynı enerji iki
kez toplanıyordu (Ağustos 2026: günde ~16.000 kWh, ayda ~448.000 kWh fazla).
Eksik trafo varsa değer DÜŞÜK kalır — şişirmek yerine eksik ölçülür.

KURAL (27.10.2026) — kojen orta gerilimden (step-up) beslenir:
  EDAŞ ─┐
        ├─ OG bara ─► TRDP-1..4 ─► hastane yükleri
  Kojen ┘
  Trafolar şebeke ve kojen enerjisini KARIŞIK taşır; trafo toplamı hastanenin
  genel tüketimidir, kojen de içindedir. Dört trafo ölçülen günde:
    Kojen Üretim = Kojen-1 + Kojen-2 + Kojen-3 + Kojen-4 (girilen/okunanlar)
    Şebeke       = trafo toplamı − kojen üretimi   (eksi = şebekeye verildi)
    Toplam       = şebeke + kojen = trafo toplamı
  Eski "Toplam = Şebeke(=trafo) + Kojen" kojeni iki kez sayıyordu (Eylül 2026:
  günde ~58 MWh yerine ~100 MWh). Trafolardan biri eksikse trafo toplamı
  hastane tüketimi değildir — o günlerde (Ağustos–Eylül 2026) eski kural
  korunur, "trafo − kojen" eksi ve anlamsız çıkardı. Trafo verisi hiç olmayan
  2023–2025 günlerinde şebeke elle girilmiş EDAŞ değeridir: Toplam = Şebeke + Kojen.
"""

TRDP_KOLONLARI = ["TRDP1_kWh", "TRDP2_kWh", "TRDP3_kWh", "TRDP4_kWh"]
# Kojen-1..4 üretim sayaçları (data_bridge KOJEN-n günlük farkı ya da form)
KOJEN_KOLONLARI = ["Kojen1_kWh", "Kojen2_kWh", "Kojen3_kWh", "Kojen4_kWh"]


def _sut(df, ad):
    """Sütun yoksa sıfır serisi döndür (eski/eksik şemalarda çökmesin)."""
    import pandas as pd
    if ad in df.columns:
        return pd.to_numeric(df[ad], errors="coerce").fillna(0)
    return pd.Series(0.0, index=df.index)


def yeniden_hesapla(df):
    """Türetilmiş enerji sütunlarını yeniden hesaplar. df'i DEĞİŞTİRİR ve döner."""
    if df is None or len(df) == 0:
        return df

    # Soğutma = chiller + VRF
    df["Toplam_Sogutma_Tuketim_kWh"] = _sut(df, "Chiller_Tuketim_kWh") + _sut(df, "VRF_Split_Tuketim_kWh")

    # Kojen üretim = kojen sayaçlarının toplamı; hiçbiri girilmemişse mevcut
    # (eskiden elle girilen toplam) değer korunur.
    kojen_n = [_sut(df, k) for k in KOJEN_KOLONLARI]
    kojen_toplam = kojen_n[0] + kojen_n[1] + kojen_n[2] + kojen_n[3]
    kojen_girildi = (kojen_n[0] > 0) | (kojen_n[1] > 0) | (kojen_n[2] > 0) | (kojen_n[3] > 0)
    df["Kojen_Uretim_kWh"] = kojen_toplam.where(kojen_girildi, _sut(df, "Kojen_Uretim_kWh"))
    kojen = _sut(df, "Kojen_Uretim_kWh")

    trdp = [_sut(df, k) for k in TRDP_KOLONLARI]
    trdp_toplam = trdp[0] + trdp[1] + trdp[2] + trdp[3]
    girildi = (trdp[0] > 0) | (trdp[1] > 0) | (trdp[2] > 0) | (trdp[3] > 0)
    tam = (trdp[0] > 0) & (trdp[1] > 0) & (trdp[2] > 0) & (trdp[3] > 0)

    # Şebeke: dört trafo varsa trafo − kojen; eksik trafoda ölçülen trafoların
    # toplamı (eski kural); hiç trafo yoksa mevcut (elle girilmiş) değer.
    sebeke = trdp_toplam.where(girildi, _sut(df, "Sebeke_Tuketim_kWh"))
    df["Sebeke_Tuketim_kWh"] = (trdp_toplam - kojen).where(tam, sebeke)

    # Toplam: dört trafo varsa trafo toplamı; değilse Şebeke + Kojen
    # (şebeke de yoksa son çare alt sayaç toplamı).
    mcc_sogutma = _sut(df, "MCC_Tuketim_kWh") + _sut(df, "Toplam_Sogutma_Tuketim_kWh")
    eski_toplam = sebeke.where(sebeke > 0, mcc_sogutma) + kojen
    df["Toplam_Hastane_Tuketim_kWh"] = trdp_toplam.where(tam, eski_toplam)

    # Diğer yük = toplam - MCC - soğutma (negatif olmaz)
    df["Diger_Yuk_kWh"] = (_sut(df, "Toplam_Hastane_Tuketim_kWh")
                           - _sut(df, "MCC_Tuketim_kWh")
                           - _sut(df, "Toplam_Sogutma_Tuketim_kWh")).clip(lower=0)
    return df


def eksik_trafolar(satir):
    """Bir satırdaki (dict ya da Series) ölçülmeyen trafoların adları."""
    eksik = []
    for k in TRDP_KOLONLARI:
        try:
            v = float(satir.get(k) if hasattr(satir, "get") else satir[k])
        except (TypeError, ValueError):
            v = 0.0
        if not (v > 0):
            eksik.append("TRDP-" + k[4])
    return eksik
