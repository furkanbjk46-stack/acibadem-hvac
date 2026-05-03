# data_bridge.py
# Modbus (analizor_guncel_veriler.csv) + BACnet (hedefli_enerji_verileri.csv)
# verilerini otomatik olarak energy_data.csv formatina donusturur.
#
# CALISMA MANTIĞI:
#   Her sabah 08:30'da sayac okumasi yapilir.
#   Gunluk tuketim = bugun 08:30 okumasi - dun 08:30 okumasi
#   Hesaplanan tuketim DUN'un tarihi ile energy_data.csv'ye yazilir.
#
#   Ornek: 4 Mayis 08:30'da calisinca ->
#     - 4 Mayis 08:30 okumasi kaydedilir (yarinki hesap icin)
#     - 3 Mayis 08:30 - 4 Mayis 08:30 farki = 3 Mayis'in tuketimi
#     - energy_data.csv'ye "2026-05-03" satirini yazar

import csv
import json
import os
import time
import logging
from datetime import datetime, date, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BRIDGE] %(message)s")
logger = logging.getLogger(__name__)

# ================================================================
# YOL YAPILANDIRMASI
# Gemini scriptinin calistigi klasore gore ayarlayin
# ================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Gemini scriptinin urettigi CSV'ler (bu scriptle ayni klasorde olmali)
MODBUS_CSV = os.path.join(BASE_DIR, "analizor_guncel_veriler.csv")
BACNET_CSV = os.path.join(BASE_DIR, "hedefli_enerji_verileri.csv")

# Portalin energy_data.csv konumu (bu scriptla ayni klasorde ise degistirme)
ENERGY_CSV = os.path.join(BASE_DIR, "energy_data.csv")

# Gunluk Modbus referans degerleri (dun gece okuma)
REF_FILE = os.path.join(BASE_DIR, "modbus_daily_ref.json")

# Gunluk snapshot saati — her sabah 08:30'da dun'un verisini yazar
SNAPSHOT_HOUR   = 8
SNAPSHOT_MINUTE = 30

# ================================================================
# ANALIZOR GRUPLARI
# ================================================================
CHILLER_ANALYZERS = {
    "CHILLER-1", "CHILLER-2", "CHILLER-3", "CHILLER-4", "CHILLER-5"
}

ALL_ANALYZERS = {
    "MCC-1", "MCC-2", "MCC-4", "MCC-6", "MCC-7",
    "CHILLER-1", "CHILLER-2", "CHILLER-3", "CHILLER-4", "CHILLER-5",
    "KULE-1", "KULE-2", "KULE-3",
    "2BK-MCC-D01", "2BK-MCC-D02",
    "4BK-MCC-E01", "4BK-MCC-E02", "4BK-MCC-F01",
    "CK-MCC-D01", "CK-MCC-E01", "CK-MCC-F01",
}

# ================================================================
# BACNET POINT -> energy_data.csv SUTUN ESLESTIRMESI
# Point Name (hedefli_enerji_verileri.csv) -> dahili anahtar
# "_" ile baslayanllar gecici, son satirda kullanilmaz
# ================================================================
BACNET_MAP = {
    "DIS HAVA":                "Dis_Hava_Sicakligi_C",
    "CH SET":                  "Chiller_Set_Temp_C",
    "MAS-1 ISITMA SICAKLIK":   "Mas1_Isitma_Temp",
    "MAS-2 ISITMA SICAKLIK":   "Mas2_Isitma_Temp",
    "MAS-1 SOGUTMA SICAKLIK":  "Mas1_Sogutma_Temp",
    "MAS-2 SOGUTMA SICAKLIK":  "Mas2_Sogutma_Temp",
    "MAS-1 KAZAN SICAKLIK":    "Mas1_Kazan_Temp",
    "MAS-2 KAZAN SICAKLIK":    "Mas2_Kazan_Temp",
    # Durum bilgileri (0.0=KAPALI, 1.0=ACIK)
    "CH-1 DURUM BILGISI":      "_ch_dur_1",
    "CH-2 DURUM BILGISI":      "_ch_dur_2",
    "CH-3 DURUM BILGISI":      "_ch_dur_3",
    "CH-4 DURUM BILGISI":      "_ch_dur_4",
    "CH-5 DURUM BILGISI":      "_ch_dur_5",
    "ABS DURUM BILGISI":       "_abs_dur",
    "KAZAN-1 DURUM BILGISI":   "_kaz_dur_1",
    "KAZAN-2 DURUM BILGISI":   "_kaz_dur_2",
    "KAZAN-3 DURUM BILGISI":   "_kaz_dur_3",
    # Chiller calisma yuzdesi
    "CH-1 CALISMA YUZDELIK":   "_ch_yuz_1",
    "CH-2 CALISMA YUZDELIK":   "_ch_yuz_2",
    "CH-3 CALISMA YUZDELIK":   "_ch_yuz_3",
    "CH-4 CALISMA YUZDELIK":   "_ch_yuz_4",
    "CH-5 CALISMA YUZDELIK":   "_ch_yuz_5",
}

ENERGY_SCHEMA = [
    "Tarih", "Chiller_Set_Temp_C", "Chiller_Adet", "Absorption_Chiller_Adet",
    "Kazan_Adet",
    "Mas1_Isitma_Temp", "Mas1_Kazan_Temp", "Mas1_Sogutma_Temp",
    "Mas2_Isitma_Temp", "Mas2_Kazan_Temp", "Mas2_Sogutma_Temp",
    "Kar_Eritme_Aktif",
    "Sebeke_Tuketim_kWh", "Kojen_Uretim_kWh",
    "Kazan_Dogalgaz_m3", "Kojen_Dogalgaz_m3", "Su_Tuketimi_m3",
    "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh", "VRF_Split_Tuketim_kWh",
    "Dis_Hava_Sicakligi_C", "Chiller_Load_Percent",
    "Toplam_Hastane_Tuketim_kWh", "Toplam_Sogutma_Tuketim_kWh", "Diger_Yuk_kWh",
]

# ================================================================
# YARDIMCI FONKSIYONLAR
# ================================================================

def read_modbus_csv():
    """analizor_guncel_veriler.csv -> {cihaz_adi: kwh_float}"""
    result = {}
    if not os.path.exists(MODBUS_CSV):
        logger.warning("Modbus CSV bulunamadi: %s", MODBUS_CSV)
        return result
    try:
        with open(MODBUS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row.get("Cihaz_Adi", "").strip()
                try:
                    result[name] = float(row.get("Enerji_kWh", ""))
                except (ValueError, TypeError):
                    logger.warning("Modbus %s baglanti hatasi — atlaniyor", name)
    except Exception as e:
        logger.error("Modbus CSV okuma hatasi: %s", e)
    return result


def read_bacnet_csv():
    """hedefli_enerji_verileri.csv -> {point_name: float_value}"""
    result = {}
    if not os.path.exists(BACNET_CSV):
        logger.warning("BACnet CSV bulunamadi: %s", BACNET_CSV)
        return result
    try:
        with open(BACNET_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
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


def calc_daily_kwh(today_readings, ref):
    """
    Gunluk tuketim = bugunun okumasi - dunku okumasi.
    Sayac sifirlama veya negatif deger durumunda 0 kabul edilir.
    """
    if ref is None:
        return None  # Ilk calistirma, referans yok
    yesterday = ref.get("readings", {})
    daily = {}
    for name, today_val in today_readings.items():
        yest_val = yesterday.get(name)
        if yest_val is None:
            logger.warning("%s icin dunku referans yok — atlaniyor", name)
            continue
        diff = today_val - yest_val
        if diff < 0:
            logger.warning("%s sayac sifirlandi veya hata (diff=%.1f) — 0 kabul edildi", name, diff)
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
    """energy_data.csv'ye yeni satir ekle (dosya yoksa olustur)"""
    file_exists = os.path.exists(ENERGY_CSV)
    with open(ENERGY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ENERGY_SCHEMA, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row_dict)
    logger.info("energy_data.csv -> yazildi: %s", row_dict.get("Tarih"))


# ================================================================
# ANA ROW BUILDER
# ================================================================

def build_daily_row(today_str, bacnet, daily_kwh):
    """BACnet + Modbus verilerinden gunluk energy_data satirini olustur"""

    # Tum BACnet noktalarini dahili dict'e al (gecici "_" anahtarlar dahil)
    data = {}
    for point_name, col_key in BACNET_MAP.items():
        val = bacnet.get(point_name)
        if val is not None:
            data[col_key] = round(val, 2)

    # --- Hesaplamalar ---

    # Kac chiller calisiyor
    ch_adet = sum(1 for i in range(1, 6) if data.get(f"_ch_dur_{i}", 0) >= 1.0)

    # Absorption chiller
    abs_adet = int(data.get("_abs_dur", 0) or 0)

    # Kac kazan calisiyor
    kaz_adet = sum(1 for i in range(1, 4) if data.get(f"_kaz_dur_{i}", 0) >= 1.0)

    # Chiller yukleme yuzdesi: sadece calisan chillerlerin ortalamasi
    ch_yuz_vals = [
        data[f"_ch_yuz_{i}"] for i in range(1, 6)
        if f"_ch_yuz_{i}" in data and data.get(f"_ch_dur_{i}", 0) >= 1.0
    ]
    ch_load = round(sum(ch_yuz_vals) / len(ch_yuz_vals), 1) if ch_yuz_vals else ""

    # Modbus gunluk kWh farklari
    chiller_kwh = safe_sum(daily_kwh, CHILLER_ANALYZERS) if daily_kwh else ""
    all_kwh     = safe_sum(daily_kwh, ALL_ANALYZERS)     if daily_kwh else ""

    diger_kwh = ""
    if isinstance(all_kwh, (int, float)) and isinstance(chiller_kwh, (int, float)):
        diger_kwh = round(all_kwh - chiller_kwh, 1)

    # --- Son satir (sadece ENERGY_SCHEMA sutunlari) ---
    row = {
        "Tarih":                      today_str,
        "Chiller_Set_Temp_C":         data.get("Chiller_Set_Temp_C", ""),
        "Chiller_Adet":               ch_adet,
        "Absorption_Chiller_Adet":    abs_adet,
        "Kazan_Adet":                 kaz_adet,
        "Mas1_Isitma_Temp":           data.get("Mas1_Isitma_Temp", ""),
        "Mas1_Kazan_Temp":            data.get("Mas1_Kazan_Temp", ""),
        "Mas1_Sogutma_Temp":          data.get("Mas1_Sogutma_Temp", ""),
        "Mas2_Isitma_Temp":           data.get("Mas2_Isitma_Temp", ""),
        "Mas2_Kazan_Temp":            data.get("Mas2_Kazan_Temp", ""),
        "Mas2_Sogutma_Temp":          data.get("Mas2_Sogutma_Temp", ""),
        "Kar_Eritme_Aktif":           0,
        # --- Manuel girilecek (sayac altyapisi hazir degil) ---
        "Sebeke_Tuketim_kWh":         "",
        "Kojen_Uretim_kWh":           "",
        "Kazan_Dogalgaz_m3":          "",
        "Kojen_Dogalgaz_m3":          "",
        "Su_Tuketimi_m3":             "",
        # --- Otomatik ---
        "Chiller_Tuketim_kWh":        chiller_kwh,
        "MCC_Tuketim_kWh":            all_kwh,
        "VRF_Split_Tuketim_kWh":      0,       # Sahada henuz yok
        "Dis_Hava_Sicakligi_C":       data.get("Dis_Hava_Sicakligi_C", ""),
        "Chiller_Load_Percent":       ch_load,
        "Toplam_Hastane_Tuketim_kWh": all_kwh,     # Tum analizorler = toplam olculen
        "Toplam_Sogutma_Tuketim_kWh": chiller_kwh,
        "Diger_Yuk_kWh":              diger_kwh,
    }
    return row


# ================================================================
# GUNLUK SNAPSHOT
# ================================================================

def run_daily_snapshot():
    today     = date.today()
    yesterday = today - timedelta(days=1)

    today_str     = today.isoformat()      # referans olarak kaydedilecek
    yesterday_str = yesterday.isoformat()  # energy_data.csv'ye yazilacak tarih

    logger.info("=== Gunluk snapshot basliyor ===")
    logger.info("Bugun 08:30 okumasi: %s | Yazilacak tarih: %s", today_str, yesterday_str)

    # 1. CSV'leri oku (data_collector'in en son yazdigi degerler)
    modbus_now = read_modbus_csv()
    bacnet_now = read_bacnet_csv()
    logger.info("Modbus: %d cihaz | BACnet: %d nokta", len(modbus_now), len(bacnet_now))

    # 2. Dunku referansi yukle (dun 08:30'daki okumalar)
    ref = load_ref()
    daily_kwh = calc_daily_kwh(modbus_now, ref)

    # 3. Bugunun 08:30 okumalarini yarin icin referans olarak kaydet
    if modbus_now:
        save_ref(today_str, modbus_now)

    # 4. Ilk calistirma — referans kaydedildi, dun icin veri yazilamaz
    if daily_kwh is None:
        logger.info("Ilk calistirma: bugunun referansi kaydedildi.")
        logger.info("Yarin 08:30'da dun'un (%s) verisi otomatik yazilacak.", today_str)
        return

    # 5. Dunku tarih zaten energy_data.csv'de var mi?
    if date_exists_in_csv(yesterday_str):
        logger.warning("Tarih zaten mevcut: %s — atlanıyor.", yesterday_str)
        return

    # 6. Satiri olustur (dun'un tarihi ile) ve yaz
    row = build_daily_row(yesterday_str, bacnet_now, daily_kwh)
    write_to_energy_csv(row)

    logger.info("Otomatik: MCC=%.1f kWh | Chiller=%.1f kWh | Dis Hava=%.1f C",
                row.get("MCC_Tuketim_kWh") or 0,
                row.get("Chiller_Tuketim_kWh") or 0,
                row.get("Dis_Hava_Sicakligi_C") or 0)
    logger.info("Manuel tamamlanacak (portal): Sebeke, Kojen, Dogalgaz, Su")
    logger.info("=== Snapshot tamamlandi: %s ===", yesterday_str)


# ================================================================
# ANA DONGU
# ================================================================

def bridge_loop():
    logger.info("Data Bridge baslatildi — her gun %02d:%02d'de calisacak",
                SNAPSHOT_HOUR, SNAPSHOT_MINUTE)
    last_run_date = None

    while True:
        now = datetime.now()
        today = now.date()

        if (now.hour == SNAPSHOT_HOUR
                and now.minute == SNAPSHOT_MINUTE
                and last_run_date != today):
            run_daily_snapshot()
            last_run_date = today

        time.sleep(30)  # 30 saniyede bir saat kontrolu


if __name__ == "__main__":
    bridge_loop()
