"""
AHU Alarm Takip Sistemi
========================
Her gunluk HVAC AHU analizi sonrasi calistirilir:
  - Bugunun analiz CSV'sini (ahu_analiz_gecmis/hvac_analysis_YYYYMMDD_HHMM.csv) okur
  - OPTIMAL olmayan (Ekipman, Kural) ciftlerini cikarir
  - Aylik sayac dosyasina (ahu_alarm_sayaclari_YYYYMM.csv) gun bazinda +1 ekler
  - Onceki gunle karsilastirip yeni/devam eden/duzelen alarmlari raporlar

Ay sonu: ay_sonu_raporu(yil, ay) -> ozet DataFrame (en cok tekrar eden kurallar)
"""

import os
import glob
import pandas as pd
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # hvac/deneme
GECMIS_DIR = os.path.join(BASE_DIR, "ahu_analiz_gecmis")
SAYAC_DIR = os.path.dirname(os.path.abspath(__file__))  # monthly_report

# Ay icinde kac gunden fazla tekrar eden kurallar "muhtemel ariza" sayilsin
TEKRAR_ESIK = 5

# Sayaca sadece bu skorun UZERINDEKI alarmlar girsin (normal/hafif uyarilar sayilmasin)
SKOR_ESIK = 7.0


def _gunluk_csv_oku(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # "Siddet" kolonu bazen bozuk encoding ile gelebilir (Siddет) - pozisyona gore al
    cols = list(df.columns)
    if "Siddet" not in cols and len(cols) > 11:
        df = df.rename(columns={cols[11]: "Siddet"})
    return df


def gunluk_alarm_listesi(csv_path: str) -> set:
    """OPTIMAL olmayan VE skoru SKOR_ESIK'in uzerinde olan (Mahal, Ekipman, Kural) uclulerini dondurur.
    Normal/hafif (dusuk skorlu) uyarilar sayaca girmez, sadece gercek saha arizasi adayi
    olabilecek yuksek skorlu alarmlar takip edilir."""
    df = _gunluk_csv_oku(csv_path)
    alarmlar = set()
    for _, row in df.iterrows():
        durum = str(row.get("Durum", "")).strip()
        kural = str(row.get("Kural", "")).strip()
        ekipman = str(row.get("Ekipman", "")).strip()
        mahal = str(row.get("Mahal", "")).strip()
        try:
            skor = float(row.get("Skor", row.get("Score", 0)) or 0)
        except (TypeError, ValueError):
            skor = 0.0
        if durum and durum != "OPTIMAL" and durum != "nan" and skor > SKOR_ESIK:
            # Kural bos olabilir, o zaman Durum kodu kural gibi davranir
            kural_key = kural if (kural and kural != "nan") else durum
            alarmlar.add((mahal, ekipman, kural_key))
    return alarmlar


def _sayac_dosyasi(tarih: datetime) -> str:
    return os.path.join(SAYAC_DIR, f"ahu_alarm_sayaclari_{tarih.strftime('%Y%m')}.csv")


def guncelle_aylik_sayac(tarih: datetime, alarmlar: set) -> pd.DataFrame:
    """Bugunun alarmlarini aylik sayac dosyasina isler, guncel dataframe'i dondurur."""
    sayac_path = _sayac_dosyasi(tarih)
    gun_str = tarih.strftime("%Y-%m-%d")

    if os.path.exists(sayac_path):
        df = pd.read_csv(sayac_path)
        if "Mahal" not in df.columns:
            df.insert(0, "Mahal", "")
    else:
        df = pd.DataFrame(columns=["Mahal", "Ekipman", "Kural", "Gun_Sayisi", "Ilk_Gorulme", "Son_Gorulme", "Son_Islenen_Gun"])

    for mahal, ekipman, kural in alarmlar:
        mask = (df["Mahal"] == mahal) & (df["Ekipman"] == ekipman) & (df["Kural"] == kural)
        if mask.any():
            idx = df[mask].index[0]
            # Aynı gun icin tekrar islenmesin (mukerrer calistirma korumasi)
            if df.at[idx, "Son_Islenen_Gun"] != gun_str:
                df.at[idx, "Gun_Sayisi"] += 1
                df.at[idx, "Son_Gorulme"] = gun_str
                df.at[idx, "Son_Islenen_Gun"] = gun_str
        else:
            df = pd.concat([df, pd.DataFrame([{
                "Mahal": mahal, "Ekipman": ekipman, "Kural": kural, "Gun_Sayisi": 1,
                "Ilk_Gorulme": gun_str, "Son_Gorulme": gun_str, "Son_Islenen_Gun": gun_str
            }])], ignore_index=True)

    df.to_csv(sayac_path, index=False)
    return df


def gunluk_karsilastirma(bugun_csv: str, dun_csv: str | None) -> dict:
    """Bugun/dun alarm setlerini karsilastirir."""
    bugun_set = gunluk_alarm_listesi(bugun_csv)
    dun_set = gunluk_alarm_listesi(dun_csv) if dun_csv and os.path.exists(dun_csv) else set()

    return {
        "yeni": bugun_set - dun_set,
        "devam_eden": bugun_set & dun_set,
        "duzelen": dun_set - bugun_set,
        "bugun_toplam": bugun_set,
    }


def _onceki_gunun_csv(bugun_csv: str) -> str | None:
    """ahu_analiz_gecmis klasorundeki en yakin onceki tarihli dosyayi bulur."""
    tum_dosyalar = sorted(glob.glob(os.path.join(GECMIS_DIR, "hvac_analysis_*.csv")))
    if bugun_csv not in tum_dosyalar:
        tum_dosyalar.append(bugun_csv)
        tum_dosyalar.sort()
    idx = tum_dosyalar.index(bugun_csv)
    return tum_dosyalar[idx - 1] if idx > 0 else None


def gunluk_analiz_isle(bugun_csv: str, tarih: datetime | None = None) -> dict:
    """Ana giris noktasi: bugunun CSV'sini isler, sayaci guncelleer, karsilastirma dondurur."""
    if tarih is None:
        # Dosya adindan tarih cikar: hvac_analysis_YYYYMMDD_HHMM.csv
        ad = os.path.basename(bugun_csv)
        tarih_str = ad.replace("hvac_analysis_", "").split("_")[0]
        tarih = datetime.strptime(tarih_str, "%Y%m%d")

    dun_csv = _onceki_gunun_csv(bugun_csv)
    karsilastirma = gunluk_karsilastirma(bugun_csv, dun_csv)

    guncelle_aylik_sayac(tarih, karsilastirma["bugun_toplam"])

    return karsilastirma


def ay_sonu_raporu(yil: int, ay: int) -> pd.DataFrame:
    """Ay icin sayac dosyasini okur, en cok tekrar eden kurallari siralar."""
    sayac_path = os.path.join(SAYAC_DIR, f"ahu_alarm_sayaclari_{yil:04d}{ay:02d}.csv")
    if not os.path.exists(sayac_path):
        return pd.DataFrame(columns=["Mahal", "Ekipman", "Kural", "Gun_Sayisi", "Ilk_Gorulme", "Son_Gorulme", "Durum"])

    df = pd.read_csv(sayac_path)
    if "Mahal" not in df.columns:
        df.insert(0, "Mahal", "")
    df = df.sort_values(["Gun_Sayisi"], ascending=False).reset_index(drop=True)
    df["Durum"] = df["Gun_Sayisi"].apply(
        lambda x: "MUHTEMEL ARIZA - SAHA KONTROLU ONERILIR" if x >= TEKRAR_ESIK else "Takip ediliyor"
    )
    return df[["Mahal", "Ekipman", "Kural", "Gun_Sayisi", "Ilk_Gorulme", "Son_Gorulme", "Durum"]]


if __name__ == "__main__":
    # Test: mevcut tek dosya ile calistir
    test_dosyalar = sorted(glob.glob(os.path.join(GECMIS_DIR, "hvac_analysis_*.csv")))
    print(f"Bulunan analiz dosyalari: {test_dosyalar}")

    for f in test_dosyalar:
        sonuc = gunluk_analiz_isle(f)
        print(f"\n--- {os.path.basename(f)} ---")
        print(f"Yeni alarmlar:      {sonuc['yeni']}")
        print(f"Devam eden alarmlar: {sonuc['devam_eden']}")
        print(f"Duzelen alarmlar:    {sonuc['duzelen']}")

    if test_dosyalar:
        ilk_tarih_str = os.path.basename(test_dosyalar[0]).replace("hvac_analysis_", "").split("_")[0]
        tarih = datetime.strptime(ilk_tarih_str, "%Y%m%d")
        print(f"\n--- Ay sonu ozet ({tarih.year}-{tarih.month:02d}) ---")
        print(ay_sonu_raporu(tarih.year, tarih.month).to_string(index=False))
