# data_bridge.py
# Modbus (analizor_guncel_veriler.csv) + BACnet (hedefli_enerji_verileri.csv)
# verilerini otomatik olarak energy_data.csv formatina donusturur.
#
# CALISMA MANTIĞI (30.10.2026'dan beri):
#   Sayaclar her gece 23:59'da okunur (data_collector), kopru 00:05'te calisir.
#   BACnet (dis hava, durumlar, set) sabah 07:05'te okunur; kopru o gunun degerini kullanir.
#   Gunluk tuketim = dun 23:59 okumasi - onceki gun 23:59 okumasi
#   Hesaplanan tuketim DUN'un (okumanin yapildigi gunun) tarihi ile yazilir.
#
#   Ornek: 5 Mayis 00:05'te calisinca ->
#     - 4 Mayis 23:59 okumasi referans kaydedilir (yarinki hesap icin)
#     - 3 Mayis 23:59 - 4 Mayis 23:59 farki = 4 Mayis'in tuketimi
#     - energy_data.csv'ye "2026-05-04" satirini yazar
#   (Eskiden 07:00 okunup 07:10'da yaziliyordu; gun 07:00-07:00 idi.)
#
#   Telafi: PC 00:05'te kapaliysa, acilista dun'un satiri eksikse snapshot
#   hemen calistirilir (gun kaybi olmaz).

import yollar  # dosya yolları (ayar/ durum/ veri/; Faz 1)
import bacnet_esleme as _bacnet_esleme  # BACnet noktaları ve ısıtma hatları (ayar/bacnet_esleme.json)
import csv
import json
import os
import time
import logging
from datetime import datetime, date, timedelta

try:
    import hava_durumu
    from hava_durumu import HAVA_SUTUNLARI
except Exception:                     # modül yoksa köprü yine çalışır, hava alanları olmaz
    hava_durumu = None
    HAVA_SUTUNLARI = []

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BRIDGE] %(message)s")
logger = logging.getLogger(__name__)

# ================================================================
# YOL YAPILANDIRMASI
# Gemini scriptinin calistigi klasore gore ayarlayin
# ================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Gemini scriptinin urettigi CSV'ler (bu scriptle ayni klasorde olmali)
MODBUS_CSV = yollar.yol("analizor_guncel_veriler.csv", BASE_DIR)
BACNET_CSV = yollar.yol("hedefli_enerji_verileri.csv", BASE_DIR)

# Portalin energy_data.csv konumu (bu scriptla ayni klasorde ise degistirme)
ENERGY_CSV = yollar.yol("energy_data.csv", BASE_DIR)

# Gunluk Modbus referans degerleri (dun gece okuma)
REF_FILE = yollar.yol("modbus_daily_ref.json", BASE_DIR)

# Gunluk snapshot saati — her gece 00:05'te dunun (23:59 okumasi) satirini yazar
SNAPSHOT_HOUR   = 0
SNAPSHOT_MINUTE = 5

# ================================================================
# BACNET TAZELIK / DONMA KORUMASI (24.10.2026)
# Maslak'ta data_collector BACnet sablonunu bulamayinca hedefli_enerji_verileri.csv
# 21.09.2026'dan sonra hic guncellenmedi; bu kopru dosyanin tarihine BAKMADIGI
# icin ayni degerleri 34 gun boyunca her sabah yeniden yazdi (dis hava 19,88 C,
# chiller yuku, kazan sicakliklari...). Artik:
#   * dosya BACNET_TAZELIK_SAAT'ten eskiyse degerleri KULLANILMAZ — alanlar bos
#     kalir (yanlis veri yerine eksik veri; veri_alarm bunu KRITIK bildirir)
#   * acilista energy_data.csv'de gecmiste kalmis donmus bloklar bosaltilir
# ================================================================
# 30.10.2026: BACnet 07:05'te, kopru 00:05'te → normal yas ~17 saat. PC 00:05'te
# kapali kalip sabah 09:05'e kadar acilirsa telafi de dunun BACnet'ini kullanabilsin: 26 saat.
BACNET_TAZELIK_SAAT = 26
DONMA_GUN = 4                  # olcum bu kadar gun birebir ayniysa donmus sayilir
# energy_data'da BACnet'ten gelen (ya da ondan turetilen) tum sutunlar
BACNET_SUTUNLARI = [
    "Dis_Hava_Sicakligi_C", "Dis_Hava_Nem_Yuzde",
    "Chiller_Set_Temp_C", "Chiller_Adet", "Absorption_Chiller_Adet",
    "Kazan_Adet", "Kojen_Adet", "Chiller_Load_Percent",
] + _bacnet_esleme.hat_sutunlari(BASE_DIR)   # ısıtma hatları: ayar/bacnet_esleme.json (Maslak: Mas1_*, Mas2_*)
# Donma TESPITI yalniz ondalikli OLCUMLERLE yapilir: chiller set ve cihaz adedi
# haftalarca ayni kalabilir, bu normaldir.
DONMA_OLCUMLERI = [
    "Dis_Hava_Sicakligi_C", "Dis_Hava_Nem_Yuzde", "Chiller_Load_Percent",
] + _bacnet_esleme.hat_sutunlari(BASE_DIR)

# ================================================================
# ANALIZOR GRUPLARI
# ================================================================
# Gruplar KODDA DEĞİL: ayar/sayaclar.json (sayaclar.py; Faz 1 / C1, 12.11.2026).
#   chiller   → CHILLER_ANALYZERS (soğutma)
#   alt_sayac → MCC, kule, bina MCC'leri; chiller ile birlikte ALL_ANALYZERS (MCC + Chiller toplamı)
#   trafo / sebeke / uretim bu toplama GİRMEZ (şebeke ve kojen ayrı hesaplanır, çift sayım olur)
import sayaclar as _sayaclar  # noqa: E402


def _numaralar(data, onek):
    """Veride bulunan '<onek>N' anahtarlarının N'leri (sıralı). Chiller/kazan/kojen sayısı lokasyona göre değişir;
    eskiden 5 chiller / 3 kazan / 4 kojen sabitti."""
    return sorted(int(k[len(onek):]) for k in data if k.startswith(onek) and k[len(onek):].isdigit())
CHILLER_ANALYZERS = set(_sayaclar.adlar("chiller", BASE_DIR))
ALL_ANALYZERS = set(_sayaclar.adlar(("chiller", "alt_sayac"), BASE_DIR))

# MCC tüketimi = Chiller HARİÇ geri kalan tüm analizörler
MCC_ONLY_ANALYZERS = ALL_ANALYZERS - CHILLER_ANALYZERS

# ================================================================
# BACNET POINT -> energy_data.csv SUTUN ESLESTIRMESI
# Point Name (hedefli_enerji_verileri.csv) -> dahili anahtar
# "_" ile baslayanllar gecici, son satirda kullanilmaz
# ================================================================
# Eşleme KODDA DEĞİL: ayar/bacnet_esleme.json (bacnet_esleme.py; Faz 1 / C2, 12.11.2026).
# Maslak eşlemesindeki saha notları (ornek_ayar/maslak/bacnet_esleme.json'a taşındı):
#   * "CH SET" kaldırıldı (28.10.2026): şablondaki adres (0103 / AV 12) kollektör denetleyicisinin
#     set noktasıydı; chiller seti çalışan chiller'ların CH-x IC SET değerlerinden hesaplanır.
#   * DIS HAVA NEM 24.10.2026: AI 32 (cihaz 2098211). KOJEN-n DURUM 24.10.2026: BI 52-55 (cihaz 2098215);
#     kojen çalışınca atık ısısı kazanın yerini tutar — ısıtma gazı tahmininde en güçlü girdi.
BACNET_MAP = _bacnet_esleme.noktalar(BASE_DIR)

ENERGY_SCHEMA = [
    "Tarih", "Chiller_Set_Temp_C", "Chiller_Adet", "Absorption_Chiller_Adet",
    "Kazan_Adet", "Kojen_Adet",
] + _bacnet_esleme.hat_sutunlari(BASE_DIR) + [   # ısıtma hatları (ayar/bacnet_esleme.json)
    "Kar_Eritme_Aktif",
    "TRDP1_kWh", "TRDP2_kWh", "TRDP3_kWh", "TRDP4_kWh",
    "Sebeke_Tuketim_kWh", "Kojen_Uretim_kWh",
    "Kojen1_kWh", "Kojen2_kWh", "Kojen3_kWh", "Kojen4_kWh",   # 27.10.2026 kojen sayaçları
    "Kazan_Dogalgaz_m3", "Kojen_Dogalgaz_m3", "Su_Tuketimi_m3",
    "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh", "VRF_Split_Tuketim_kWh",
    "Dis_Hava_Sicakligi_C", "Chiller_Load_Percent",
    "Toplam_Hastane_Tuketim_kWh", "Toplam_Sogutma_Tuketim_kWh", "Diger_Yuk_kWh",
    # --- Soğutma kırılımı (Chiller bazında) ---
    "Chiller1_kWh", "Chiller2_kWh", "Chiller3_kWh", "Chiller4_kWh", "Chiller5_kWh",
    # --- MCC kırılımı (analizör bazında) ---
    "MCC1_kWh", "MCC2_kWh", "MCC3_kWh", "MCC4_kWh", "MCC5_kWh", "MCC6_kWh", "MCC7_kWh",
    "Kule1_kWh", "Kule2_kWh", "Kule3_kWh",
    "MCC_2BK_D01_kWh", "MCC_2BK_D02_kWh",
    "MCC_4BK_E01_kWh", "MCC_4BK_E02_kWh", "MCC_4BK_F01_kWh",
    "MCC_CK_D01_kWh", "MCC_CK_E01_kWh", "MCC_CK_F01_kWh",
] + HAVA_SUTUNLARI   # bina nem sensörü + internetten günlük hava (hava_durumu.py)
# Lokasyonun sayaç sütunları (ayar/sayaclar.json): listede olmayanlar sona eklenir (yeni lokasyon / yeni sayaç)
ENERGY_SCHEMA += [c for c in _sayaclar.sutunlar(base_dir=BASE_DIR) if c not in ENERGY_SCHEMA]

# ================================================================
# YARDIMCI FONKSIYONLAR
# ================================================================

def read_modbus_csv():
    """analizor_guncel_veriler.csv -> {cihaz_adi: kwh_int}
    CSV Python tarafindan yazilir → her zaman standart float format (nokta=ondalik).
    """
    result = {}
    if not os.path.exists(MODBUS_CSV):
        logger.warning("Modbus CSV bulunamadi: %s", MODBUS_CSV)
        return result
    try:
        with open(MODBUS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row.get("Cihaz_Adi", "").strip()
                try:
                    raw = row.get("Enerji_kWh", "").strip()
                    result[name] = int(float(raw))
                except (ValueError, TypeError) as e:
                    logger.warning("Modbus %s parse hatasi (%s) — atlaniyor", name, e)
    except Exception as e:
        logger.error("Modbus CSV okuma hatasi: %s", e)
    return result


def read_bacnet_csv(simdi=None):
    """hedefli_enerji_verileri.csv -> {point_name: float_value}

    Dosyadaki EN YENI okuma BACNET_TAZELIK_SAAT'ten eskiyse bos sozluk doner:
    eski degeri bugunun degeri gibi yazmak, eksik birakmaktan kotudur.
    """
    result = {}
    if not os.path.exists(BACNET_CSV):
        logger.warning("BACnet CSV bulunamadi: %s", BACNET_CSV)
        return result
    try:
        with open(BACNET_CSV, newline="", encoding="utf-8") as f:
            satirlar = list(csv.DictReader(f))
        zamanlar = [r.get("Timestamp", "") for r in satirlar if r.get("Timestamp")]
        son = datetime.strptime(max(zamanlar), "%Y-%m-%d %H:%M:%S") if zamanlar else None
        if son is None or ((simdi or datetime.now()) - son).total_seconds() / 3600 > BACNET_TAZELIK_SAAT:
            logger.warning("BACnet verisi BAYAT (son okuma: %s) — degerler KULLANILMIYOR, "
                           "BACnet alanlari bos yazilacak. data_collector BACnet okumasini kontrol edin.",
                           son.strftime("%d.%m.%Y %H:%M") if son else "yok")
            return {}
        for row in satirlar:
            name = row.get("Point_Name", "").strip()
            status = row.get("Status", "")
            if status != "OK":
                continue
            try:
                result[name] = float(row.get("Value", ""))
            except (ValueError, TypeError):
                pass
    except Exception as e:
        logger.error("BACnet CSV okuma hatasi: %s", e)
    return result


def load_ref():
    """Dunku Modbus referans degerlerini yukle"""
    if not os.path.exists(REF_FILE):
        return None
    try:
        with open(REF_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Referans dosyasi okunamadi: %s", e)
        return None


def save_ref(today_str, readings):
    """Bugunku Modbus okumalarini referans olarak kaydet (yarin kullanilacak)"""
    data = {"date": today_str, "readings": readings}
    with open(REF_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Modbus referans kaydedildi: %s (%d cihaz)", today_str, len(readings))


MAX_DAILY_KWH_PER_DEVICE = 50_000  # Bir cihazin gunluk max makul tuketimi

# NET sayaclar (GIREN - VERILEN): sebekeye enerji verilen gun farki EKSI
# olabilir — sayac sifirlanmasi sayilmaz. Sebeke girisi hastanenin tamamini
# tasir (kojen dururken ~3 MW x 24 sa = ~75.000 kWh): genel sinir ona dar.
NET_SAYACLAR = set(_sayaclar.adlar("sebeke", BASE_DIR))
MAX_DAILY_KWH_NET = 200_000


def calc_daily_kwh(today_readings, ref):
    """
    Gunluk tuketim = bugunun okumasi - dunku okumasi.
    Sayac sifirlama, stale ref veya mantıksız büyük değerlerde 0 kabul edilir.
    Donus degerleri:
      None  → ilk calistirma (ref hic yok), energy_data yazilmaz
      False → tarih uyumsuzlugu, Modbus alanlari bos ama satir yine yazilir
      dict  → normal hesaplama
    """
    if ref is None:
        return None  # Ilk calistirma, referans yok

    # Referans tarihi dun olmalı — eski ref varsa sıfırdan başla
    ref_date_str = ref.get("date", "")
    expected_yesterday = (date.today() - timedelta(days=1)).isoformat()
    if ref_date_str != expected_yesterday:
        logger.warning(
            "Referans tarihi uyumsuz (beklenen=%s, mevcut=%s) — Modbus alanlari bos birakılacak, BACnet verisi yazilacak",
            expected_yesterday, ref_date_str
        )
        return False  # Tarih uyumsuz: satiri yaz ama Modbus alanlari bos

    yesterday = ref.get("readings", {})
    daily = {}
    for name, today_val in today_readings.items():
        yest_val = yesterday.get(name)
        if yest_val is None:
            logger.warning("%s icin dunku referans yok — atlaniyor", name)
            continue
        diff = today_val - yest_val
        if name in NET_SAYACLAR:
            if abs(diff) > MAX_DAILY_KWH_NET:
                logger.error("%s gunluk net fark makul degil (%.1f kWh) — bos birakildi", name, diff)
                continue
            daily[name] = round(diff, 1)
            continue
        if diff < 0:
            logger.warning("%s sayac sifirlandi veya hata (diff=%.1f) — 0 kabul edildi", name, diff)
            diff = 0.0
        if diff > MAX_DAILY_KWH_PER_DEVICE:
            logger.error(
                "%s gunluk fark cok buyuk (%.1f kWh) — referans sifir ya da format hatasi. 0 kullanildi.",
                name, diff
            )
            diff = 0.0
        daily[name] = round(diff, 1)
    return daily


def safe_sum(values_dict, keys):
    """Belirtilen anahtarlarin toplamini al (None veya eksik olanlari atla)"""
    total = 0.0
    any_valid = False
    for k in keys:
        v = values_dict.get(k)
        if isinstance(v, (int, float)):
            total += v
            any_valid = True
    return round(total, 1) if any_valid else None


def date_exists_in_csv(target_date_str):
    """energy_data.csv'de bu tarih zaten var mi?"""
    if not os.path.exists(ENERGY_CSV):
        return False
    try:
        with open(ENERGY_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Tarih", "").startswith(target_date_str):
                    return True
    except Exception:
        pass
    return False


def write_to_energy_csv(row_dict):
    """
    energy_data.csv'ye yeni satir ekle. Yazildiysa True, yazilamadiysa False.
    Mevcut dosyada eksik sutun varsa (schema degisikligi) pandas ile guncelle.
    """
    import pandas as pd

    if os.path.exists(ENERGY_CSV):
        try:
            df = pd.read_csv(ENERGY_CSV)
            # Eksik sütunları ekle (schema genişledi)
            for col in ENERGY_SCHEMA:
                if col not in df.columns:
                    df[col] = None
                    logger.info("energy_data.csv sutun eklendi: %s", col)
            # Yeni satırı ekle
            new_row_df = pd.DataFrame([{k: row_dict.get(k, None) for k in ENERGY_SCHEMA}])
            df = pd.concat([df[ENERGY_SCHEMA], new_row_df], ignore_index=True)
            # Atomik yazım: gecici dosya + os.replace (eszamanli erisimde bozulma olmasin)
            import tempfile
            _dizin = os.path.dirname(os.path.abspath(ENERGY_CSV)) or "."
            _fd, _gecici = tempfile.mkstemp(suffix=".tmp", prefix="energy_", dir=_dizin)
            os.close(_fd)
            df.to_csv(_gecici, index=False)
            os.replace(_gecici, ENERGY_CSV)
        except Exception as e:
            logger.error("energy_data.csv guncelleme hatasi: %s", e)
            return False
    else:
        try:
            with open(ENERGY_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=ENERGY_SCHEMA, extrasaction="ignore")
                writer.writeheader()
                writer.writerow(row_dict)
        except Exception as e:
            logger.error("energy_data.csv olusturma hatasi: %s", e)
            return False

    logger.info("energy_data.csv -> yazildi: %s", row_dict.get("Tarih"))
    return True


# ================================================================
# ANA ROW BUILDER
# ================================================================

def yuzde_kirp(v):
    """Bağıl nem %0-100 aralığına kırpılır; boş → boş.

    31.10.2026: sensör yağmur/sis doygunluğunda 100,64 gönderdi; portal formu
    (en fazla 100) bu değerle açılırken StreamlitValueAboveMaxError verdi.
    Fiziksel olarak %100 üstü nem yoktur — kalibrasyon payıdır.
    """
    if v in ("", None):
        return v
    try:
        return round(min(100.0, max(0.0, float(v))), 2)
    except (TypeError, ValueError):
        return ""


def chiller_set_hesapla(data):
    """Chiller seti = CH-1..5 IC SET (chiller'ın o an KULLANDIĞI set).

    OTO SET hepsine aynı değeri gönderir; normalde hepsi eşittir. Çalışan
    chiller'ların değeri alınır (hiçbiri çalışmıyorsa okunanların hepsi).
    Değerler ayrışırsa ÇOĞUNLUĞUN değeri yazılır, eşitlikte ortanca; ayrışan
    chiller kayda uyarı olarak düşer (ör. 28.10.2026: CH-5 IC SET 3,3 —
    OTO SET'in 7,5'ini uygulamıyor). Hiç IC SET okunamadıysa boş.
    """
    okunan = {i: data[f"_ch_ic_{i}"] for i in _numaralar(data, "_ch_ic_")}
    if not okunan:
        return ""
    calisan = {i: v for i, v in okunan.items() if data.get(f"_ch_dur_{i}", 0) >= 1.0}
    kume = calisan or okunan
    from collections import Counter
    from statistics import median
    sayim = Counter(round(v, 1) for v in kume.values()).most_common()
    if len(sayim) > 1 and sayim[0][1] == sayim[1][1]:
        deger = round(median(kume.values()), 2)
    else:
        deger = sayim[0][0]
    ayrisan = {i: v for i, v in kume.items() if abs(v - deger) > 0.25}
    if ayrisan:
        logger.warning("Chiller IC SET'ler ayrisiyor: ortak %.1f C, farkli: %s",
                       deger, ", ".join("CH-%d=%.1f" % (i, v) for i, v in sorted(ayrisan.items())))
    return round(deger, 2)


def build_daily_row(today_str, bacnet, daily_kwh):
    """BACnet + Modbus verilerinden gunluk energy_data satirini olustur"""

    # Tum BACnet noktalarini dahili dict'e al (gecici "_" anahtarlar dahil)
    data = {}
    for point_name, col_key in BACNET_MAP.items():
        val = bacnet.get(point_name)
        if val is not None:
            data[col_key] = round(val, 2)

    # --- Hesaplamalar ---

    # Kac chiller / kazan calisiyor. BACnet verisi YOKSA (bayat/okunamadi)
    # adetler BOS kalir — eskiden 0 yaziliyordu, yani "hic chiller calismiyor"
    # gibi yanlis bir bilgi uretiliyordu.
    if data:
        ch_adet = sum(1 for i in _numaralar(data, "_ch_dur_") if data.get(f"_ch_dur_{i}", 0) >= 1.0)
        abs_adet = int(data.get("_abs_dur", 0) or 0)
        kaz_adet = sum(1 for i in _numaralar(data, "_kaz_dur_") if data.get(f"_kaz_dur_{i}", 0) >= 1.0)
        # Kojen noktaları şablonda yoksa (eski kurulum) adet BOŞ kalır, 0 yazılmaz
        kojen_okunan = [data[f"_kojen_dur_{i}"] for i in _numaralar(data, "_kojen_dur_")]
        kojen_adet = sum(1 for v in kojen_okunan if v >= 1.0) if kojen_okunan else ""
    else:
        ch_adet = abs_adet = kaz_adet = kojen_adet = ""

    ch_set = chiller_set_hesapla(data)

    # Chiller yukleme yuzdesi: sadece calisan chillerlerin ortalamasi
    ch_yuz_vals = [
        data[f"_ch_yuz_{i}"] for i in _numaralar(data, "_ch_yuz_")
        if data.get(f"_ch_dur_{i}", 0) >= 1.0
    ]
    ch_load = round(sum(ch_yuz_vals) / len(ch_yuz_vals), 1) if ch_yuz_vals else ""

    # Modbus gunluk kWh farklari
    chiller_kwh = safe_sum(daily_kwh, CHILLER_ANALYZERS)    if daily_kwh else ""  # Soğutma
    mcc_kwh     = safe_sum(daily_kwh, MCC_ONLY_ANALYZERS)   if daily_kwh else ""  # MCC (Chiller hariç)
    total_kwh   = safe_sum(daily_kwh, ALL_ANALYZERS)         if daily_kwh else ""  # Toplam

    diger_kwh = ""
    if (isinstance(total_kwh, (int, float))
            and isinstance(mcc_kwh, (int, float))
            and isinstance(chiller_kwh, (int, float))):
        diger_kwh = round(total_kwh - mcc_kwh - chiller_kwh, 1)

    # --- Trafo sayaçları (ayar/sayaclar.json tur=trafo; Maslak: TRDP-1..4) ---
    # Saha notları: TRDP-4 Siemens PAC4200, 21.09.2026'dan otomatik (ilk gün referans yok, boş);
    # TRDP-2 Janitza, 29.09.2026'da bağlandı — dört trafo da otomatik okunuyor.
    _trafo_adlari = _sayaclar.adlar("trafo", BASE_DIR)
    trafo_deger = {ad: (daily_kwh.get(ad, "") if daily_kwh else "") for ad in _trafo_adlari}

    # --- Sebeke hesabi: YALNIZCA TRDP sayaclarinin toplami ---
    # Eskiden TRDP-2/4 bosken "MCC + Chiller" yedegi kullaniliyordu. O yedek
    # CIFT SAYIM uretiyordu: MCC/Chiller analizorleri kaynaga bakmadan tuketimi
    # olcer, kojen calisirken o yukleri kojen besler; yedek bunu "sebekeden
    # cekildi" sayip ustune kojen eklenince ayni enerji iki kez toplaniyordu
    # (Agustos 2026: gunde ~16.000 kWh fazla). Artik kac trafo olculuyorsa
    # onlarin toplami yazilir; eksik trafo varsa deger DUSUK kalir.
    def _to_num(v):
        try:
            return float(v) if v != "" else 0.0
        except (TypeError, ValueError):
            return 0.0

    _trafolar = [_to_num(trafo_deger[ad]) for ad in _trafo_adlari]

    # --- Kojen uretim sayaclari (KOJEN-n, "uretim" analizorleri) ---
    # KOJEN-1/2 sahada henuz bagli degil: okunmayan kojen BOS kalir (0 yazilmaz),
    # formdan elle girilebilir. Kural enerji_hesap.py'de (27.10.2026).
    kojen_n = {ad: (daily_kwh.get(ad, "") if daily_kwh else "") for ad in _sayaclar.adlar("uretim", BASE_DIR)}
    _okunan_kojen = [_to_num(v) for v in kojen_n.values() if v != ""]
    kojen_kwh = round(sum(_okunan_kojen), 1) if _okunan_kojen else ""

    _trdp_toplam = round(sum(_trafolar), 1)
    if _trafolar and all(v > 0 for v in _trafolar):
        # Dort trafo: trafo toplami = hastane geneli (kojen de icinde);
        # sebeke = trafo - kojen (eksi = sebekeye verildi)
        toplam_hastane_kwh = _trdp_toplam
        sebeke_kwh = round(_trdp_toplam - _to_num(kojen_kwh), 1)
    elif any(v > 0 for v in _trafolar):
        sebeke_kwh = _trdp_toplam   # Eksik trafo: olculenlerin toplami (eski kural)
        toplam_hastane_kwh = round(sebeke_kwh + _to_num(kojen_kwh), 1)
    else:
        sebeke_kwh = ""  # TRDP verisi yok, bos birak
        toplam_hastane_kwh = total_kwh

    # 29.10.2026 kurali (enerji_hesap.YENI_KURAL_BASLANGIC ve sonrasi): sebeke
    # trafodan HESAPLANMAZ; toplam = sebeke + kojen.
    # 02.11.2026: sebeke EDAS giris sayacindan (SEBEKE, PAC3200) otomatik —
    # gunluk NET fark (giren - verilen; eksi = sebekeye verildi). Sayac o gun
    # okunamadiysa BOS kalir, toplam simdilik yalniz kojen; portaldan elle
    # girilirse recalc tamamlar.
    try:
        import enerji_hesap as _eh
        if _eh.yeni_kural_mi(today_str):
            _sebeke_adi = (_sayaclar.adlar("sebeke", BASE_DIR) or [None])[0]
            _sb = daily_kwh.get(_sebeke_adi, "") if (daily_kwh and _sebeke_adi) else ""
            sebeke_kwh = _sb
            if _sb != "":
                toplam_hastane_kwh = round(_to_num(_sb) + _to_num(kojen_kwh), 1)
            else:
                toplam_hastane_kwh = kojen_kwh
    except Exception as e:
        logger.warning("Yeni sebeke kurali uygulanamadi: %s", e)

    # --- Son satir (sadece ENERGY_SCHEMA sutunlari) ---
    row = {
        "Tarih":                      today_str,
        "Chiller_Set_Temp_C":         ch_set,   # CH-x IC SET (çalışanların ortak değeri)
        "Chiller_Adet":               ch_adet,
        "Absorption_Chiller_Adet":    abs_adet,
        "Kazan_Adet":                 kaz_adet,
        "Kar_Eritme_Aktif":           0,
        "Sebeke_Tuketim_kWh":         sebeke_kwh,  # Otomatik (SEBEKE sayaci, net)
        "Kojen_Uretim_kWh":           kojen_kwh,   # Okunan kojenlerin toplami
        "Kazan_Dogalgaz_m3":          "",
        "Kojen_Dogalgaz_m3":          "",
        "Su_Tuketimi_m3":             "",
        # --- Otomatik ---
        "Chiller_Tuketim_kWh":        chiller_kwh,  # Sadece CH analizörleri
        "MCC_Tuketim_kWh":            mcc_kwh,      # CH HARİÇ tüm analizörler
        "VRF_Split_Tuketim_kWh":      0,            # Sahada henuz yok
        "Dis_Hava_Sicakligi_C":       data.get("Dis_Hava_Sicakligi_C", ""),
        "Dis_Hava_Nem_Yuzde":         yuzde_kirp(data.get("Dis_Hava_Nem_Yuzde", "")),
        "Kojen_Adet":                 kojen_adet,
        "Chiller_Load_Percent":       ch_load,
        "Toplam_Hastane_Tuketim_kWh": toplam_hastane_kwh,  # Dort trafo: trafo toplami (enerji_hesap)
        "Toplam_Sogutma_Tuketim_kWh": chiller_kwh,  # CH analizörleri = soğutma
        "Diger_Yuk_kWh":              diger_kwh,    # Toplam - MCC - Soğutma
    }
    # Isıtma hatlarının sıcaklıkları (ayar/bacnet_esleme.json)
    for _c in _bacnet_esleme.hat_sutunlari(BASE_DIR):
        row[_c] = data.get(_c, "")
    # Sayaç başına günlük kWh (trafo, kojen, chiller, alt sayaçlar) — ayar/sayaclar.json'daki
    # 'sutun' alanına. Şebeke sütunu yukarıda kurala göre hesaplanır (ham değer yazılmaz).
    for _s in _sayaclar.yukle(BASE_DIR):
        if _s["tur"] != "sebeke" and _s.get("sutun"):
            row[_s["sutun"]] = daily_kwh.get(_s["ad"], "") if daily_kwh else ""
    return row


def hava_doldur(yol=None, bugun=None) -> dict:
    """energy_data.csv'de internet hava alanlari BOS olan gunleri doldurur.

    Ilk calismada butun gecmisi (arsiv tek istekte), sonra yalniz eksik kalan
    gunleri (internet kesildigi gunler) tamamlar. Yalniz Hava_* sutunlarina yazar;
    bina sensoru ve tuketim sutunlarina dokunmaz. Atomik yazim.
    """
    import pandas as pd
    import tempfile
    if hava_durumu is None:
        return {"doldurulan": 0}
    yol = yol or ENERGY_CSV
    if not os.path.exists(yol):
        return {"doldurulan": 0}
    df = pd.read_csv(yol, dtype=str, keep_default_na=False)
    if "Tarih" not in df.columns or df.empty:
        return {"doldurulan": 0}
    for c in hava_durumu.INTERNET_SUTUNLARI:
        if c not in df.columns:
            df[c] = ""
    dun = ((bugun or date.today()) - timedelta(days=1)).isoformat()
    tarih = df["Tarih"].str[:10]
    bos = (df["Hava_Sicaklik_Ort_C"].astype(str).str.strip() == "") & (tarih <= dun) & (tarih != "")
    if not bos.any():
        return {"doldurulan": 0}
    veri = hava_durumu.gunluk_hava(tarih[bos].min(), tarih[bos].max(), bugun=bugun)
    say = 0
    for i in df.index[bos]:
        v = veri.get(tarih[i])
        if v:
            for c, x in v.items():
                df.at[i, c] = "" if x is None else str(x)
            say += 1
    if say == 0:
        return {"doldurulan": 0, "eksik": int(bos.sum())}
    _fd, _gecici = tempfile.mkstemp(suffix=".tmp", prefix="energy_",
                                    dir=os.path.dirname(os.path.abspath(yol)) or ".")
    os.close(_fd)
    df.to_csv(_gecici, index=False)
    os.replace(_gecici, yol)
    logger.info("Hava verisi dolduruldu: %d gun (%s -> %s)", say, tarih[bos].min(), tarih[bos].max())
    return {"doldurulan": say, "eksik": int(bos.sum()) - say}


def donmus_bacnet_temizle(yol=None, yedek_dizin=None) -> dict:
    """energy_data.csv'de BACnet degerlerinin DONMUS kaldigi gunleri bosaltir.

    Donmus blok: dis hava DONMA_GUN+ gun birebir ayni VE (baska olcum varsa)
    ayni gunlerde en az bir baska olcum de ayni. Blogun ILK gunu gercek
    okumadir, korunur; sonraki gunlerin BACNET_SUTUNLARI bosaltilir.
    TEK BIR TAKVIM AYI icinde kalan bloklara DOKUNULMAZ, yalniz raporlanir:
    Maslak'ta 2023-06 ve 2026-04 sonundaki kisa bloklar elle girilmis veri
    (aylik ortalama) — silinseydi gercek kayit kaybolurdu. Ileriye donuk yeni
    donma zaten olusmaz (read_bacnet_csv bayat dosyayi kullanmiyor); bu temizlik
    GECMISTE kalmis, ay sinirini asan BACnet donmalari icindir.
    Degisiklik varsa once yedek alinir, yazim atomiktir. Tekrar calistirilirsa
    bir sey bulamaz. kWh / tuketim sutunlarina DOKUNMAZ.
    """
    import pandas as pd
    import shutil
    import tempfile
    yol = yol or ENERGY_CSV
    if not os.path.exists(yol):
        return {"temizlenen_gun": 0}
    df = pd.read_csv(yol, dtype=str, keep_default_na=False)   # bicim aynen korunur
    if "Tarih" not in df.columns or df.empty:
        return {"temizlenen_gun": 0}
    tarih = pd.to_datetime(df["Tarih"].str[:10], errors="coerce")
    sira = tarih.sort_values(kind="stable").index
    supheli = []          # tek ay icinde kalan bloklar: dokunulmaz, raporlanir

    def donmus_satirlar(sutun):
        """sutun icin donmus bloklarin ILK GUN HARIC satir indeksleri"""
        if sutun not in df.columns:
            return set()
        bulunan, blok = set(), []

        def bitir():
            if len(blok) >= DONMA_GUN:
                t = tarih.loc[blok]
                if t.dt.to_period("M").nunique() > 1:
                    bulunan.update(blok[1:])
                elif sutun == "Dis_Hava_Sicakligi_C":
                    # Ayin tamami tek degerse beklenen durum (elle girilmis aylik
                    # ortalama) — rapora bile yazilmaz; ayin bir PARCASI ise yazilir.
                    tam_ay = t.min().day == 1 and t.max().day >= t.max().days_in_month - 1
                    if not tam_ay and len(supheli) < 10:
                        supheli.append("%s..%s" % (t.min().date(), t.max().date()))

        for i in sira:
            v = str(df.at[i, sutun]).strip()
            if v and blok and v == str(df.at[blok[-1], sutun]).strip():
                blok.append(i)
            else:
                bitir()
                blok = [i] if v else []
        bitir()
        return bulunan

    bloklar = {c: donmus_satirlar(c) for c in DONMA_OLCUMLERI}
    dolu = [c for c in DONMA_OLCUMLERI if c in df.columns and (df[c].astype(str).str.strip() != "").any()]
    ana = bloklar.get("Dis_Hava_Sicakligi_C", set())
    diger = [c for c in dolu if c != "Dis_Hava_Sicakligi_C"]
    hedef = sorted(ana & set().union(*(bloklar[c] for c in diger))) if diger else sorted(ana)
    if not hedef:
        return {"temizlenen_gun": 0, "dokunulmayan": supheli}

    tarihler = sorted(df.loc[hedef, "Tarih"].str[:10])
    try:
        yedek_dizin = yedek_dizin or yollar.klasor("veri/eski_yedekler", BASE_DIR)
        os.makedirs(yedek_dizin, exist_ok=True)
        shutil.copy2(yol, os.path.join(yedek_dizin, "energy_data_yedek_bacnet_donma_%s.csv"
                                       % datetime.now().strftime("%Y%m%d_%H%M%S")))
    except Exception as e:
        logger.error("Donma temizligi: yedek alinamadi (%s) — temizlik YAPILMADI", e)
        return {"temizlenen_gun": 0, "hata": "yedek alinamadi"}
    for c in BACNET_SUTUNLARI:
        if c in df.columns:
            df.loc[hedef, c] = ""
    _fd, _gecici = tempfile.mkstemp(suffix=".tmp", prefix="energy_",
                                    dir=os.path.dirname(os.path.abspath(yol)) or ".")
    os.close(_fd)
    df.to_csv(_gecici, index=False)
    os.replace(_gecici, yol)
    sonuc = {"temizlenen_gun": len(hedef), "bas": tarihler[0], "son": tarihler[-1],
             "dokunulmayan": supheli, "zaman": datetime.now().isoformat(timespec="seconds")}
    logger.warning("Donmus BACnet verisi temizlendi: %d gun (%s -> %s), yedek configs/ altinda",
                   len(hedef), tarihler[0], tarihler[-1])
    try:
        with open(os.path.join(yedek_dizin, "bacnet_donma_temizlik.json"), "w", encoding="utf-8") as f:
            json.dump(sonuc, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return sonuc


# ================================================================
# GUNLUK SNAPSHOT
# ================================================================

def run_daily_snapshot():
    today     = date.today()
    yesterday = today - timedelta(days=1)

    today_str     = today.isoformat()      # referans olarak kaydedilecek
    yesterday_str = yesterday.isoformat()  # energy_data.csv'ye yazilacak tarih

    logger.info("=== Gunluk snapshot basliyor ===")
    logger.info("Bugun %02d:%02d okumasi: %s | Yazilacak tarih: %s",
                SNAPSHOT_HOUR, SNAPSHOT_MINUTE, today_str, yesterday_str)

    # 1. CSV'leri oku (data_collector'in en son yazdigi degerler)
    modbus_now = read_modbus_csv()
    bacnet_now = read_bacnet_csv()
    logger.info("Modbus: %d cihaz | BACnet: %d nokta", len(modbus_now), len(bacnet_now))

    # 2. Dunku referansi yukle (dun SNAPSHOT saatindeki okumalar)
    ref = load_ref()
    daily_kwh = calc_daily_kwh(modbus_now, ref)

    # 3. Bugunun okumalari yarin icin referans olarak kaydedilir — ama SADECE
    #    dunun satiri yazildiktan (veya zaten var oldugu goruldukten) SONRA.
    #    Eskiden once kaydediliyordu: yazma basarisiz olursa referans bugune
    #    kaymis oluyor, telafi calismasi "tarih uyumsuz" deyip dunun kWh'ini
    #    bos yaziyordu — o gunun tuketimi kalici kayboluyordu (H-02).
    def _referansi_kaydet():
        if modbus_now:
            save_ref(today_str, modbus_now)

    # 4. Ilk calistirma — referans kaydedildi, dun icin veri yazilamaz
    if daily_kwh is None:
        _referansi_kaydet()
        logger.info("Ilk calistirma: bugunun referansi kaydedildi.")
        logger.info("Yarin %02d:%02d'da dun'un (%s) verisi otomatik yazilacak.",
                    SNAPSHOT_HOUR, SNAPSHOT_MINUTE, today_str)
        return

    # daily_kwh=False → tarih uyumsuzlugu, Modbus alanlari bos ama BACnet yazilacak
    modbus_data = daily_kwh if daily_kwh is not False else None

    # 5. Dunku tarih zaten energy_data.csv'de var mi?
    if date_exists_in_csv(yesterday_str):
        logger.warning("Tarih zaten mevcut: %s — atlanıyor.", yesterday_str)
        _referansi_kaydet()
        return

    # 6. Satiri olustur (dun'un tarihi ile) ve yaz
    row = build_daily_row(yesterday_str, bacnet_now, modbus_data)
    # Lokasyonun kendi koordinatından dünün günlük hava özeti (internet yoksa boş
    # kalır; hava_doldur bir sonraki açılışta tamamlar)
    if hava_durumu is not None:
        row.update(hava_durumu.gunluk_hava(yesterday_str, yesterday_str).get(yesterday_str, {}))
    if not write_to_energy_csv(row):
        logger.error("%s satiri yazilamadi — referans KORUNDU, sonraki acilista telafi "
                     "ayni farkla tekrar deneyecek.", yesterday_str)
        return
    _referansi_kaydet()

    logger.info("Otomatik: MCC=%.1f kWh | Chiller=%.1f kWh | Dis Hava=%.1f C",
                row.get("MCC_Tuketim_kWh") or 0,
                row.get("Chiller_Tuketim_kWh") or 0,
                row.get("Dis_Hava_Sicakligi_C") or 0)
    logger.info("Sebeke=%s kWh (sayac) | Manuel tamamlanacak (portal): Dogalgaz, Su",
                row.get("Sebeke_Tuketim_kWh") if row.get("Sebeke_Tuketim_kWh") != "" else "okunamadi")

    # 7. Veri toplama alarmlari: baglanti hatasi / bos gunluk veri
    #    Tespit veri_alarm.py'de (tek kaynak); buradan yalnizca tetiklenir.
    #    Sonuc configs/veri_alarmlari.json'a yazilir -> portal bildirim cubugu
    #    ve heartbeat uzerinden Synapse canli uyarilari ayni listeyi gosterir.
    try:
        import veri_alarm
        _cfg = {}
        try:
            with open(yollar.yol("supabase_config.json", BASE_DIR), encoding="utf-8") as _f:
                _cfg = json.load(_f)
        except Exception:
            pass
        _ozet = veri_alarm.kontrol_et(
            modbus_data, yesterday_str,
            sb_url=_cfg.get("supabase_url"), sb_key=_cfg.get("supabase_key"),
            lokasyon_id=__import__("location_manager").lokasyon_id(BASE_DIR, _cfg.get("lokasyon_id")))
        if _ozet.get("toplam"):
            logger.warning("Veri alarmi: %d uyari (%d kritik) — %s",
                           _ozet.get("toplam"), _ozet.get("kritik"),
                           "; ".join(_ozet.get("mesajlar", [])[:2]))
        else:
            logger.info("Veri alarmi yok: tum analizorler okundu.")
    except Exception as _e:
        logger.error("Veri alarm kontrolu yapilamadi: %s", _e)

    logger.info("=== Snapshot tamamlandi: %s ===", yesterday_str)


# ================================================================
# ANA DONGU
# ================================================================

def bridge_loop():
    logger.info("Data Bridge baslatildi — her gun %02d:%02d'de calisacak",
                SNAPSHOT_HOUR, SNAPSHOT_MINUTE)

    # 30.10.2026 sebeke gecisi: 01.06-28.10 arasi trafodan TURETILMIS sebeke
    # degerleri bosaltilir (tek sefer, yedekli; elle girilmis degere dokunmaz)
    try:
        import enerji_hesap as _eh
        _n = _eh.sebeke_gecisi_uygula(ENERGY_CSV, yollar.klasor("veri/eski_yedekler", BASE_DIR))
        if _n:
            logger.info("Sebeke gecisi: %d gunun turetilmis sebeke degeri bosaltildi", _n)
    except Exception as e:
        logger.error("Sebeke gecisi yapilamadi: %s", e)

    # Baslarken ref dosyasi yoksa hemen olustur (8:30'u bekleme)
    if not os.path.exists(REF_FILE):
        logger.info("Ref dosyasi yok — baslangic referansi olusturuluyor...")
        modbus_now = read_modbus_csv()
        if modbus_now:
            save_ref(date.today().isoformat(), modbus_now)
        else:
            logger.warning("Modbus CSV bos veya okunamadi — ref olusturulamadi.")

    last_run_date = None

    # Gecmiste donmus kalmis BACnet gunlerini bosalt (bir kez bulur; sonra bos doner)
    try:
        donmus_bacnet_temizle()
    except Exception as e:
        logger.error("Donmus BACnet temizligi yapilamadi: %s", e)

    # Hava alani bos kalmis gecmis gunleri internetten doldur (ilk calismada tum gecmis)
    try:
        hava_doldur()
    except Exception as e:
        logger.error("Hava verisi doldurulamadi: %s", e)

    # E-3 fix: Kacirilan gun telafisi — acilista saat 00:05'i gecmisse ve dun'un
    # satiri energy_data.csv'de yoksa snapshot'i hemen calistir (PC o saatte
    # kapali kaldiginda gun tamamen atlaniyordu).
    _now = datetime.now()
    _dun_str = (date.today() - timedelta(days=1)).isoformat()
    if ((_now.hour, _now.minute) >= (SNAPSHOT_HOUR, SNAPSHOT_MINUTE)
            and not date_exists_in_csv(_dun_str)):
        logger.info("Kacirilan gun telafisi: %s icin snapshot calistiriliyor...", _dun_str)
        try:
            run_daily_snapshot()
            last_run_date = date.today()
        except Exception as e:
            logger.error("Telafi snapshot hatasi: %s", e)

    while True:
        now = datetime.now()
        today = now.date()

        if (now.hour == SNAPSHOT_HOUR
                and now.minute == SNAPSHOT_MINUTE
                and last_run_date != today):
            # Hata dongu thread'ini oldurmesin (referans korunur, telafi acilista dener)
            try:
                run_daily_snapshot()
            except Exception as e:
                logger.error("Gunluk snapshot hatasi: %s", e)
            last_run_date = today

        time.sleep(30)  # 30 saniyede bir saat kontrolu


if __name__ == "__main__":
    bridge_loop()
