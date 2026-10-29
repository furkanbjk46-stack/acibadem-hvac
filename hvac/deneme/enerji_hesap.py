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

KURAL (29.10.2026, kullanıcı kararı; 30.10.2026'da 01.06.2026'ya geri çekildi)
— YENI_KURAL_BASLANGIC ve sonrası:
  Şebeke       = elle girilen şebeke tüketimi (EDAŞ; trafodan HESAPLANMAZ)
  Toplam       = Şebeke + Kojen Üretim   (trafo toplamı yalnız bilgi)
  Şebeke yoksa Toplam = yalnız Kojen Üretim (ekranda "şebeke verisi eksik").
  Haziran 2026'dan önceki günler yukarıdaki kurallarla aynen kalır.
  Tarih sütunu olmayan veri (eski çağrılar, testler) eski kuralla hesaplanır.

GEÇİŞ (30.10.2026, tek sefer): 01.06–28.10.2026 arasında şebeke sütununda
TRAFODAN TÜRETİLMİŞ değer duruyordu (trafo − kojen ya da trafo toplamı); elle
girilmiş EDAŞ değeri değildi. sebeke_gecisi_uygula() bunları — yalnız türetilmiş
olduğu birebir eşitlikle kanıtlananları — boşaltır, eski değerleri yedeğe yazar.
Farklı (elle girilmiş) bir değere dokunmaz. Lokasyonda bir kez çalışır (işaret dosyası).
"""

TRDP_KOLONLARI = ["TRDP1_kWh", "TRDP2_kWh", "TRDP3_kWh", "TRDP4_kWh"]
# Kojen-1..4 üretim sayaçları (data_bridge KOJEN-n günlük farkı ya da form)
KOJEN_KOLONLARI = ["Kojen1_kWh", "Kojen2_kWh", "Kojen3_kWh", "Kojen4_kWh"]
# Şebeke elle girilir, Toplam = Şebeke + Kojen — bu tarihten itibaren (dahil)
YENI_KURAL_BASLANGIC = "2026-06-01"
# Türetilmiş şebeke değerlerinin temizleneceği aralık (dahil)
GECIS_ARALIK = ("2026-06-01", "2026-10-28")
GECIS_ISARET = "sebeke_gecisi_20261030.json"   # configs/ altında; varsa geçiş yapılmış


def yeni_kural_mi(tarih) -> bool:
    """Bu günün satırı yeni kuralla mı hesaplanır? (tarih: str / date / Timestamp)"""
    import pandas as pd
    t = pd.to_datetime(tarih, errors="coerce")
    return bool(pd.notna(t) and t >= pd.Timestamp(YENI_KURAL_BASLANGIC))


def _yeni_maske(df):
    import pandas as pd
    if "Tarih" not in df.columns:
        return pd.Series(False, index=df.index)
    t = pd.to_datetime(df["Tarih"], errors="coerce")
    return (t >= pd.Timestamp(YENI_KURAL_BASLANGIC)).fillna(False)


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

    import pandas as pd
    yeni = _yeni_maske(df)
    sebeke_girilen = pd.to_numeric(df["Sebeke_Tuketim_kWh"], errors="coerce")         if "Sebeke_Tuketim_kWh" in df.columns else pd.Series(float("nan"), index=df.index)

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

    # Yeni kural (YENI_KURAL_BASLANGIC ve sonrası): şebeke elle, toplam = şebeke + kojen
    if yeni.any():
        df.loc[yeni, "Sebeke_Tuketim_kWh"] = sebeke_girilen[yeni]
        df.loc[yeni, "Toplam_Hastane_Tuketim_kWh"] = sebeke_girilen[yeni].fillna(0).clip(lower=0) + kojen[yeni]

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


def turetilmis_sebeke(df):
    """GECIS_ARALIK içinde şebeke değeri trafodan TÜRETİLMİŞ satırların maskesi.

    Türetilmiş = trafo − kojen'e ya da trafo toplamına 1 kWh'ten az farkla eşit
    (eski kural bu ikisinden birini yazıyordu). Elle girilmiş farklı değer hariç."""
    import pandas as pd
    if "Tarih" not in df.columns or "Sebeke_Tuketim_kWh" not in df.columns:
        return pd.Series(False, index=df.index)
    t = pd.to_datetime(df["Tarih"], errors="coerce")
    aralik = (t >= pd.Timestamp(GECIS_ARALIK[0])) & (t <= pd.Timestamp(GECIS_ARALIK[1]))
    sb = pd.to_numeric(df["Sebeke_Tuketim_kWh"], errors="coerce")
    trafo = sum(_sut(df, k) for k in TRDP_KOLONLARI)
    kojen = _sut(df, "Kojen_Uretim_kWh")
    esit = ((sb - (trafo - kojen)).abs() < 1) | ((sb - trafo).abs() < 1)
    return (aralik & sb.notna() & (trafo > 0) & esit).fillna(False)


def sebeke_gecisi_uygula(csv_yolu: str, configs_dizini: str) -> int:
    """Tek seferlik geçiş: türetilmiş şebeke değerlerini boşaltır. Boşaltılan satır sayısı.

    İşaret dosyası (configs/GECIS_ISARET) varsa hiçbir şey yapmaz. Eski değerler
    işaret dosyasına yedeklenir (geri almak gerekirse elle). CSV atomik yazılır."""
    import json
    import os
    import pandas as pd
    isaret = os.path.join(configs_dizini, GECIS_ISARET)
    if os.path.exists(isaret) or not os.path.exists(csv_yolu):
        return 0
    try:
        import kilit
        _kl = kilit.kisa_kilit("sebeke_gecisi")
    except Exception:
        _kl = None
    from contextlib import nullcontext
    with (_kl or nullcontext(True)) as alindi:
        if not alindi or os.path.exists(isaret):
            return 0                       # başka süreç yapıyor / yaptı
        df = pd.read_csv(csv_yolu)
        m = turetilmis_sebeke(df)
        yedek = [{"Tarih": str(df.at[i, "Tarih"]), "Sebeke_Tuketim_kWh": float(df.at[i, "Sebeke_Tuketim_kWh"])}
                 for i in df.index[m]]
        if m.any():
            df.loc[m, "Sebeke_Tuketim_kWh"] = float("nan")
            gecici = csv_yolu + ".gecis_tmp"
            df.to_csv(gecici, index=False)
            os.replace(gecici, csv_yolu)
        os.makedirs(configs_dizini, exist_ok=True)
        with open(isaret, "w", encoding="utf-8") as f:
            json.dump({"aciklama": "Trafodan türetilmiş şebeke değerleri boşaltıldı (30.10.2026 kuralı). "
                                   "Elle girilmiş farklı değerlere dokunulmadı.",
                       "aralik": GECIS_ARALIK, "bosaltilan": yedek}, f, ensure_ascii=False, indent=1)
        return len(yedek)
