# -*- coding: utf-8 -*-
"""ÖRNEK ENERJİ VERİSİ ÜRETECİ — YALNIZCA GELİŞTİRME MAKİNESİ.

Enerji ve Verimlilik portalını (diyagram, dashboard, karşılaştırma, aylık
rapor, tahmin & trend) dolu veriyle denemek için 2 yıllık günlük veri üretir.

    python ornek_veri_uret.py                  # 2 yıl, dünde biter
    python ornek_veri_uret.py --yil 3
    python ornek_veri_uret.py --hedef dene.csv # başka dosyaya yaz
    python ornek_veri_uret.py --geri-al        # son yedeği geri yükle

SAHADA ÇALIŞTIRILMAZ. Yanına supabase_config.json konmuş bir kurulum (yani
gerçek bir lokasyon PC'si) görürse çalışmayı reddeder; o makinede üretilen
sahte veri buluta ve Synapse'e giderdi. Dosya lokasyon yamalarına da
eklenmez.

Üretilen veri gerçekçi olsun diye:
  · Dış hava İstanbul mevsim eğrisi (yaz ~28 °C, kış ~6 °C) + günlük gürültü
  · Mekanik trafolar (TRDP-2/4) soğutma ve ısıtma derece-günüyle büyür
  · Bina trafoları (TRDP-1/3) daha düz; hafta sonu biraz düşük
  · Kojen çoğu gün çalışır, ayda bir iki gün durur (bakım)
  · Kazan doğalgazı kışa, chiller/kule tüketimi yaza biner
  · Yılda birkaç gün analizör arızası: alt sayaçlar boş kalır ("veri yok")
Türetilmiş sütunlar (şebeke, toplam, soğutma, diğer yük) elle yazılmaz;
portalın kullandığı enerji_hesap.yeniden_hesapla ile hesaplanır.
"""
import argparse
import ast
import datetime as dt
import math
import os
import random
import shutil
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:                                   # konsol cp1254 ise ekran yazısı çökmesin
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

VARSAYILAN_HEDEF = os.path.join(BURASI, "energy_data.csv")
# Tek ve kalıcı yedek: ÖRNEK VERİDEN ÖNCEKİ dosya. Her çalıştırmada yenisi
# açılsaydı ikinci çalıştırmada yedek de sahte veri olur, --geri-al işe
# yaramazdı.
YEDEK = os.path.join(BURASI, "energy_data_ilk_yedek.csv")


def _sema():
    """Sütun listesini app_portal.py'den okur — şema tek yerde kalsın."""
    import location_manager

    kaynak = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
    agac = ast.parse(kaynak)
    secilen = []
    for d in agac.body:
        if isinstance(d, ast.If) and "_TEMP_COLS_SCHEMA" in ast.dump(d):
            secilen.append(d)
        elif isinstance(d, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SCHEMA" for t in d.targets):
            secilen.append(d)
    cfg = location_manager.get_manager().get_location_config()
    ns = {"_has_dual_lines": bool(cfg.get("energy_schema", {}).get("heating_lines"))}
    exec(compile(ast.Module(body=secilen, type_ignores=[]), "sema", "exec"), ns)
    return ns["SCHEMA"], ns["_TEMP_COLS_SCHEMA"]


def _dis_hava(gun, rnd):
    """İstanbul günlük ortalama sıcaklığı: yıllık sinüs + gürültü."""
    gun_no = gun.timetuple().tm_yday
    taban = 15.5 - 9.5 * math.cos(2 * math.pi * (gun_no - 20) / 365.0)
    return round(taban + rnd.gauss(0, 2.2), 1)


def _dagit(toplam, paylar, rnd, sapma=0.06):
    """Toplamı verilen oranlara göre böler, her parçaya küçük gürültü ekler."""
    ham = [max(0.0, p * toplam * (1 + rnd.gauss(0, sapma))) for p in paylar]
    olcek = (toplam / sum(ham)) if sum(ham) > 0 else 0
    return [round(x * olcek, 1) for x in ham]


def gun_satiri(gun, rnd, temp_kolonlari, analizor_ariza=False, kojen_durdu=False):
    t = _dis_hava(gun, rnd)
    sogutma_dg = max(0.0, t - 18.0)          # soğutma derece-günü
    isitma_dg = max(0.0, 16.0 - t)           # ısıtma derece-günü
    hafta_sonu = gun.weekday() >= 5
    gun_katsayi = 0.94 if hafta_sonu else 1.0

    # ── Trafolar ──
    # Taban yükler Maslak'ın gerçek mertebesine göre seçildi: hastane günlük
    # toplamı ~55-80 bin kWh, 106.000 m² için ~0,55-0,70 kWh/m².
    mekanik = (27500 + 1900 * sogutma_dg + 360 * isitma_dg) * gun_katsayi
    mekanik *= 1 + rnd.gauss(0, 0.035)
    trdp2 = round(mekanik * rnd.uniform(0.49, 0.51), 1)
    trdp4 = round(mekanik - trdp2, 1)

    bina = (20000 + 190 * sogutma_dg + 80 * isitma_dg) * gun_katsayi
    bina *= 1 + rnd.gauss(0, 0.03)
    trdp1 = round(bina * rnd.uniform(0.49, 0.52), 1)
    trdp3 = round(bina - trdp1, 1)

    # ── Kojenerasyon ──
    if kojen_durdu:
        kojen, kojen_gaz = 0.0, 0.0
    else:
        kojen = round(12500 * (1 + rnd.gauss(0, 0.07)) + 90 * isitma_dg, 1)
        kojen_gaz = round(kojen / (3.6 * (1 + rnd.gauss(0, 0.02))), 1)

    # ── Yakıt, su ──
    kazan_gaz = round((330 + 215 * isitma_dg) * (1 + rnd.gauss(0, 0.08)), 1)
    su = round(520 + 9 * sogutma_dg + rnd.gauss(0, 28), 1)

    # ── Soğutma ──
    # Kışın bile taban yük var: ameliyathane, görüntüleme, sunucu odası.
    chiller = round((900 + 1420 * sogutma_dg) * (1 + rnd.gauss(0, 0.05)), 1)
    vrf = round(640 + 95 * sogutma_dg * (1 + rnd.gauss(0, 0.06)), 1)
    mcc = round((10800 + 240 * sogutma_dg + 60 * isitma_dg) * gun_katsayi
                * (1 + rnd.gauss(0, 0.04)), 1)

    satir = {
        "Tarih": gun.strftime("%Y-%m-%d"),
        "TRDP1_kWh": trdp1, "TRDP2_kWh": trdp2, "TRDP3_kWh": trdp3, "TRDP4_kWh": trdp4,
        "Kojen_Uretim_kWh": kojen, "Kojen_Dogalgaz_m3": kojen_gaz,
        "Kazan_Dogalgaz_m3": kazan_gaz, "Su_Tuketimi_m3": su,
        "Chiller_Tuketim_kWh": chiller, "MCC_Tuketim_kWh": mcc,
        "VRF_Split_Tuketim_kWh": vrf, "Dis_Hava_Sicakligi_C": t,
        "Chiller_Set_Temp_C": 6.5 if sogutma_dg > 4 else 7.5,
        "Chiller_Adet": min(4, 1 + int(sogutma_dg / 3.2)),
        "Absorption_Chiller_Adet": 1 if sogutma_dg > 8 else 0,
        "Kazan_Adet": min(3, int(isitma_dg / 4.5) + (1 if isitma_dg > 0 else 0)),
        "Chiller_Load_Percent": round(min(95.0, 14 + 6.1 * sogutma_dg), 1),
        "Kar_Eritme_Aktif": bool(t < 1.5 and gun.month in (1, 2, 12)),
    }

    # ── Sıcaklıklar (lokasyon şemasına göre) ──
    isitma_set = 72.0 if isitma_dg > 0 else 0.0
    kazan_set = 60.0 if isitma_dg > 0 else 0.0
    sogutma_set = 8.0 if sogutma_dg > 0 else 0.0
    for k in temp_kolonlari:
        if "Isitma" in k:
            satir[k] = round(isitma_set + rnd.uniform(-2, 3), 1)
        elif "Kazan" in k:
            satir[k] = round(kazan_set + rnd.uniform(-2, 2), 1)
        else:
            satir[k] = round(sogutma_set + rnd.uniform(-1, 1.5), 1)

    # ── Alt sayaçlar (analizörler) ──
    if analizor_ariza:
        return satir                                  # sütunlar boş kalır
    ch_paylar = [0.28, 0.26, 0.2, 0.16, 0.10]
    for ad, deger in zip(["Chiller%d_kWh" % i for i in range(1, 6)],
                         _dagit(chiller, ch_paylar, rnd)):
        satir[ad] = deger
    kule = chiller * 0.085
    for ad, deger in zip(["Kule1_kWh", "Kule2_kWh", "Kule3_kWh"],
                         _dagit(kule, [0.4, 0.35, 0.25], rnd)):
        satir[ad] = deger
    janitza = ["MCC%d_kWh" % i for i in range(1, 8)]
    siemens = ["MCC_2BK_D01_kWh", "MCC_2BK_D02_kWh", "MCC_4BK_E01_kWh",
               "MCC_4BK_E02_kWh", "MCC_4BK_F01_kWh", "MCC_CK_D01_kWh",
               "MCC_CK_E01_kWh", "MCC_CK_F01_kWh"]
    for ad, deger in zip(janitza, _dagit(mcc * 0.58, [1 / 7] * 7, rnd, 0.12)):
        satir[ad] = deger
    for ad, deger in zip(siemens, _dagit(mcc * 0.42, [1 / 8] * 8, rnd, 0.12)):
        satir[ad] = deger
    return satir


def uret(yil=2, bitis=None, tohum=20261012):
    import pandas as pd
    import enerji_hesap

    sema, temp_kolonlari = _sema()
    bitis = bitis or (dt.date.today() - dt.timedelta(days=1))
    gun_sayisi = int(round(yil * 365.25))
    baslangic = bitis - dt.timedelta(days=gun_sayisi - 1)

    rnd = random.Random(tohum)
    # Yılda ~4 analizör arızası, ayda ~1 kojen duruşu
    arizali = set(rnd.sample(range(gun_sayisi), max(1, gun_sayisi // 90)))
    duruslar = set(rnd.sample(range(gun_sayisi), max(1, gun_sayisi // 30)))

    satirlar = []
    for i in range(gun_sayisi):
        gun = baslangic + dt.timedelta(days=i)
        satirlar.append(gun_satiri(gun, rnd, temp_kolonlari,
                                   analizor_ariza=(i in arizali),
                                   kojen_durdu=(i in duruslar)))

    df = pd.DataFrame(satirlar)
    for k in sema:
        if k not in df.columns:
            df[k] = None
    df = enerji_hesap.yeniden_hesapla(df)      # şebeke/toplam/soğutma/diğer yük
    return df[sema], baslangic, bitis, len(arizali), len(duruslar)


def _yedekle(hedef):
    """İlk çalıştırmada mevcut dosyayı saklar; sonrakilerde dokunmaz."""
    if not os.path.exists(hedef) or os.path.exists(YEDEK):
        return None
    shutil.copy2(hedef, YEDEK)
    return YEDEK


def _geri_al(hedef):
    if not os.path.exists(YEDEK):
        print("Yedek bulunamadı: %s" % os.path.basename(YEDEK))
        return 1
    shutil.copy2(YEDEK, hedef)
    print("Geri yüklendi: %s -> %s" % (os.path.basename(YEDEK), os.path.basename(hedef)))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Örnek enerji verisi üreteci (yalnızca geliştirme)")
    ap.add_argument("--yil", type=float, default=2.0)
    ap.add_argument("--hedef", default=VARSAYILAN_HEDEF)
    ap.add_argument("--tohum", type=int, default=20261012)
    ap.add_argument("--geri-al", action="store_true", dest="geri_al")
    ap.add_argument("--zorla", action="store_true",
                    help="Lokasyon kurulumu uyarısını yok say (önerilmez)")
    a = ap.parse_args()

    if os.path.exists(os.path.join(BURASI, "supabase_config.json")) and not a.zorla:
        print("DURDURULDU: burası bir LOKASYON kurulumu (supabase_config.json var).\n"
              "Sahte veri buluta ve Synapse'e giderdi. Geliştirme makinesinde çalıştırın.")
        return 2

    if a.geri_al:
        return _geri_al(a.hedef)

    df, bas, bit, ariza, durus = uret(a.yil, tohum=a.tohum)
    yedek = _yedekle(a.hedef)
    df.to_csv(a.hedef, index=False)

    print("Örnek veri yazıldı: %s" % a.hedef)
    print("  %d gün  |  %s → %s" % (len(df), bas.strftime("%d.%m.%Y"), bit.strftime("%d.%m.%Y")))
    print("  analizör arızalı gün: %d  |  kojen duran gün: %d" % (ariza, durus))
    print("  günlük toplam: en az %.0f / ortalama %.0f / en çok %.0f kWh"
          % (df["Toplam_Hastane_Tuketim_kWh"].min(),
             df["Toplam_Hastane_Tuketim_kWh"].mean(),
             df["Toplam_Hastane_Tuketim_kWh"].max()))
    if yedek:
        print("  önceki dosya yedeklendi: %s" % os.path.basename(yedek))
    if os.path.exists(YEDEK):
        print("  geri almak için: python ornek_veri_uret.py --geri-al")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
