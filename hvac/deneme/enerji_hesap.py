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
"""

TRDP_KOLONLARI = ["TRDP1_kWh", "TRDP2_kWh", "TRDP3_kWh", "TRDP4_kWh"]


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

    # Şebeke = ölçülen trafoların toplamı; hiç trafo yoksa mevcut değer korunur
    # (2023-2025 satırlarında şebeke elle giriliyordu, onlara dokunulmaz).
    trdp = [_sut(df, k) for k in TRDP_KOLONLARI]
    trdp_toplam = trdp[0] + trdp[1] + trdp[2] + trdp[3]
    girildi = (trdp[0] > 0) | (trdp[1] > 0) | (trdp[2] > 0) | (trdp[3] > 0)
    df["Sebeke_Tuketim_kWh"] = trdp_toplam.where(girildi, _sut(df, "Sebeke_Tuketim_kWh"))

    # Toplam = Şebeke + Kojen. Şebeke de yoksa son çare alt sayaç toplamı.
    sebeke = _sut(df, "Sebeke_Tuketim_kWh")
    mcc_sogutma = _sut(df, "MCC_Tuketim_kWh") + _sut(df, "Toplam_Sogutma_Tuketim_kWh")
    df["Toplam_Hastane_Tuketim_kWh"] = sebeke.where(sebeke > 0, mcc_sogutma) + _sut(df, "Kojen_Uretim_kWh")

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
