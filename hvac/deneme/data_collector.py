# data_collector.py
# Modbus (Janitza/Siemens analizorler) + BACnet (Desigo) veri toplayici
# Her 30 dakikada bir okuma yapar, sonuclari CSV'ye yazar.
# portal_watchdog.py tarafindan subprocess olarak baslatilir.

import yollar  # dosya yolları (ayar/ durum/ veri/; Faz 1)
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import socket
import struct
import time
import csv
import random
import threading
import logging
import os
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [COLLECTOR] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ================================================================
# MODBUS YAPILANDIRMASI
# ================================================================
# Analizör listesi KODDA DEĞİL: ayar/sayaclar.json (sayaclar.py; Faz 1 / C1, 12.11.2026).
# Lokasyon başına; teknik ekip düzenler, yama dokunmaz. Dosya yoksa ornek_ayar/<lokasyon>/
# sayaclar.json'dan kopyalanır. Biçim (data_collector için): {ip, name, brand[, uretim][, sebeke]}.
# Maslak listesindeki saha notları (bağlanma tarihleri, register kaynakları):
#   TRDP-2 (mekanik trafo) — 29.09.2026'da baglandi; dort trafo da artik
#   otomatik okunuyor, sebeke hesabi eksiksiz. ALL_ANALYZERS'a EKLENMEZ.
#   MCC-5 — 29.09.2026'da sahada devreye alindi, MCC kirilimi artik tam.
#   TRDP-4 (mekanik trafo) — Siemens PAC4200, 21.09.2026'da otomatik okumaya alındı.
#   data_bridge'de ALL_ANALYZERS'a EKLENMEZ: TRDP'ler şebeke tarafıdır, MCC/Chiller
#   alt sayaç toplamına girerse çift sayım olur.
#   KOJEN-1 / KOJEN-2 — Janitza UMG 512 PRO, 05.11.2026'da canlı izlemeye alındı.
#   ÜRETİM sayacıdır: KOJEN-3/4 ile aynı kural — ALL_ANALYZERS'a EKLENMEZ,
#   günlük farkı Kojen1/2_kWh'e yazılır (data_bridge kojen_n'i 1..4 jenerik
#   okuduğu için orada değişiklik gerekmedi).
#   
#   Enerji register'ı 05.11.2026'da ÜRETİCİ KILAVUZUNDAN alındı
#   (UMG 512-PRO, "Modbus address list" s.12) — bkz. URETIM_ENERJI_REG.
#   KOJEN-3 / KOJEN-4 — Siemens PAC3200, 27.10.2026'da canlı izlemeye alındı
#   (Synapse "KOJEN ÜRETİMİ"). ÜRETİM sayacıdır: data_bridge'de ALL_ANALYZERS'a
#   EKLENMEZ (tüketim toplamına girmez); günlük farkı Kojen3/4_kWh'e yazılır.
#   "uretim": güç ve enerji akım trafosu yönünden bağımsız okunur
#   (URETIM_ENERJI_REG, canli_guc.guc_oku).
#   ŞEBEKE — EDAŞ giriş sayacı, Siemens PAC3200 (OG, 3 telli bağlı), 02.11.2026'da
#   sahada denendi (sebeke_deneme.py: register 65 ile sayaç farkı uyumlu).
#   "sebeke": NET sayaç — kojen OG baraya bağlı olduğundan enerji iki yönlü
#   akar; enerji = GİREN − VERİLEN (SEBEKE_ENERJI_REG), güç işaretiyle okunur
#   (eksi = şebekeye veriliyor). data_bridge'de ALL_ANALYZERS'a EKLENMEZ;
#   günlük farkı Sebeke_Tuketim_kWh'e yazılır.
import sayaclar as _sayaclar  # noqa: E402
ANALYZERS = _sayaclar.analizorler(BASE_DIR)

MODBUS_PORT    = 502
MODBUS_CSV     = yollar.yol("analizor_guncel_veriler.csv", BASE_DIR)
# Sayaçlara aynı anda iki okuma gitmesin: günlük okuma ile canlı güç okuması
# (canli_guc.py) bu kilitleri paylaşır. Analizörlerin bir kısmı eşzamanlı TCP
# bağlantısında yanıt vermiyor.
#
# KİLİT CİHAZ BAZINDADIR, tek bir genel kilit DEĞİL: farklı sayaçlar farklı
# IP'lerde, birbirlerini beklemeleri için sebep yok. Tek kilitle canlı okuma
# 27 sayacı sırayla okumak zorunda kalır ve cevap vermeyen bir sayaç bütün
# turu geciktirir. Aynı sayaca iki okuma ise hâlâ sıraya girer.
_MODBUS_KILITLER = {}
_KILIT_SOZLUGU   = threading.Lock()


def cihaz_kilidi(dev):
    """Verilen cihazın kilidi (yoksa oluşturulur)."""
    ad = str(dev.get("name") or dev.get("ip") or "?")
    with _KILIT_SOZLUGU:
        kilit = _MODBUS_KILITLER.get(ad)
        if kilit is None:
            kilit = threading.Lock()
            _MODBUS_KILITLER[ad] = kilit
        return kilit
# 30.10.2026: SAYAÇ (Modbus) okuması 07:00'dan 23:59'a alındı — günlük
# tüketim takvim gününe (≈00:00–24:00) denk gelsin; data_bridge 00:05'te
# dünün (okumanın yapıldığı günün) satırını yazar.
# BACnet (dış hava, nem, chiller/kojen durumu, set) SABAH 07:05'te kalır
# (kullanıcı kararı): anlık değerler geçmişle aynı saatte kıyaslanabilsin.
# Köprü 00:05'te o günün 07:05 okumasını kullanır (data_bridge.BACNET_TAZELIK_SAAT).
READ_SAAT      = 23   # Günlük Modbus okuma saati
READ_DAKIKA    = 59   # Günlük Modbus okuma dakikası
BACNET_SAAT    = 7    # Günlük BACnet okuma saati
BACNET_DAKIKA  = 5    # Günlük BACnet okuma dakikası
KONTROL_SN     = 20   # Okuma saati kontrol aralığı: 23:59 tek dakikalık pencere, 60 sn kaçırabilirdi

# ================================================================
# BACNET YAPILANDIRMASI
# ================================================================
BACNET_PORT   = 47808
BACNET_TIMEOUT = 50.0
# Şablon önce configs/, yoksa kök klasör (ahu_collector ile AYNI sıra).
# 15.06.2026'daki bir düzenleme iki yolu da köke çevirmişti; Maslak'ta şablon
# configs/ altına alınınca BACnet günlük okuması hiç başlamadı (son okuma
# 21.09.2026 07:05) ve energy_data'ya 34 gün donmuş değer yazıldı.
# Mekanik Zeka configs/'u da aradığı için çalışmaya devam etti, fark edilmedi.
# Kanıt: saha_teshis 24.10.2026 — şablon configs'te, kökte yok, gateway 5/5 cevaplı.
_EXCEL_FILE_CONFIGS = yollar.yol("configs/hedefli_okuma_sablonu_2.xlsx", BASE_DIR)
_EXCEL_FILE_ROOT = yollar.yol("hedefli_okuma_sablonu_2.xlsx", BASE_DIR)
EXCEL_FILE = _EXCEL_FILE_CONFIGS if os.path.exists(_EXCEL_FILE_CONFIGS) else _EXCEL_FILE_ROOT
BACNET_CSV    = yollar.yol("hedefli_enerji_verileri.csv", BASE_DIR)
PROP_PRESENT_VALUE = 85

# ================================================================
# MODBUS FONKSİYONLARI
# ================================================================

# ÜRETİM sayaçları ("uretim": True — kojen), 27.10.2026:
# Jeneratör çıkışındaki analizörde akım trafosu yönü sahada doğrulanmadı;
# ters bağlıysa enerji "Giren" (801) yerine "Verilen" (809) sayacında birikir.
# Yön varsayılmaz: Giren + Verilen toplamı alınır (ikisi de ölçülen değer;
# boştaki kojenin çektiği küçük iç tüketim bu toplamda ihmal edilebilir).
# Adresler: SENTRON PAC3200 Modbus tablosu — Aktif enerji Giren/Verilen T1, Double, Wh.
#
# JANITZA (UMG 512-PRO), 05.11.2026 — aynı kural, kılavuzdaki adreslerle
# ("Modbus address list", s.12; güç için kullandığımız 19026 da bu tablodan,
# sahada çalışıyor). Float, birim Wh:
#     19062/19064/19066  _G_WH_V[0..2]  Real energy L1/L2/L3, consumed
#     19070/19072/19074  _G_WH_Z[0..2]  Real energy L1/L2/L3, delivered
# NEDEN TOPLAM SAYAÇ (19060) DEĞİL: 19060 (_G_WH_SUML13) NET enerjidir —
# consumed − delivered. KOJEN-1'in kendi ekranı bunu -10.325.301 kWh
# gösteriyor, yani akım trafosu yönü ters ve sayaç EKSİYE doğru büyüyor.
# Günlük fark o sayaçtan alınsaydı eksi çıkar, calc_daily_kwh bunu "sayaç
# sıfırlandı" sayıp her gün 0 yazardı. consumed ve delivered ayrı ayrı
# birikir ve İKİSİ DE ARTAR: toplamları yönden bağımsızdır (Siemens'teki
# Giren+Verilen ile birebir aynı mantık).
# TARİFE: 19068 "consumed, rate 1" olduğu için KULLANILMAZ; faz bazlı
# 19062/64/66'da tarife ayrımı yoktur, ileride tarife geçişi açılırsa enerji
# kaybolmaz.
URETIM_ENERJI_REG = {
    "siemens": (801, 809),
    "janitza": (19062, 19064, 19066, 19070, 19072, 19074),
}

# ŞEBEKE sayacı ("sebeke": True), 02.11.2026: NET enerji = GİREN − VERİLEN.
# Kojen OG baraya bağlı: üretim tüketimi aşınca enerji şebekeye verilir ve
# "Verilen" sayacında birikir (sahada 29.689 kWh). Tarife-2 sayaçları da
# katılır (sahada 0; ileride tarife geçişi açılırsa enerji kaybolmasın).
# Adresler: SENTRON PAC3200 Modbus tablosu, Double, Wh.
SEBEKE_ENERJI_REG = {"siemens": ((801, 805), (809, 813))}


def _siemens_double(ip, adres):
    """Siemens PAC: tek double (4 register) oku. Hata → None."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        s.connect((ip, MODBUS_PORT))
        s.send(struct.pack(">HHHBBHH", 1, 0, 6, 1, 3, int(adres), 4))
        resp = s.recv(1024)
        if len(resp) >= 17 and resp[7] == 3:
            return struct.unpack('>d', resp[9:17])[0]
    except Exception:
        pass
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass
    return None


def _janitza_float(ip, adres):
    """Janitza UMG: tek float (2 register) oku. Hata → None."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        s.connect((ip, MODBUS_PORT))
        s.send(struct.pack(">HHHBBHH", 1, 0, 6, 1, 3, int(adres), 2))
        resp = s.recv(1024)
        if len(resp) >= 13 and resp[7] == 3:
            return struct.unpack(">f", resp[9:13])[0]
    except Exception:
        pass
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass
    return None


def _enerji_oku(device, adres):
    """Üretim sayacından tek enerji register'ı (Wh). Markaya göre biçim:
    Siemens PAC double (4 register), Janitza UMG float (2 register)."""
    if device.get("brand") == "janitza":
        return _janitza_float(device["ip"], adres)
    return _siemens_double(device["ip"], adres)


def modbus_get_kwh(device):
    net = SEBEKE_ENERJI_REG.get(device.get("brand")) if device.get("sebeke") else None
    if net:
        giren = [_siemens_double(device["ip"], r) for r in net[0]]
        verilen = [_siemens_double(device["ip"], r) for r in net[1]]
        if any(v is None for v in giren + verilen):
            return None                      # yarım değer yazılmaz
        return round((sum(giren) - sum(verilen)) / 1000, 3)  # Wh → kWh (net)
    regler = URETIM_ENERJI_REG.get(device.get("brand")) if device.get("uretim") else None
    if regler:
        okunan = [_enerji_oku(device, r) for r in regler]
        if any(v is None for v in okunan):
            return None                      # yarım değer yazılmaz
        return round(sum(okunan) / 1000, 3)  # Wh → kWh
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5) # Donmaları engellemek için timeout süresi
        s.connect((device["ip"], MODBUS_PORT))

        if device["brand"] == "janitza":
            packet = b'\x00\x01\x00\x00\x00\x06\x01\x03\x4a\x74\x00\x02'
            s.send(packet)
            resp = s.recv(1024)
            s.close()
            if len(resp) >= 13:
                val = struct.unpack('>f', resp[9:13])[0]
                return round(val / 1000, 3)  # Wh → kWh

        elif device["brand"] == "siemens":
            # Hem PAC3200 hem PAC4200 için çalışan evrensel paket
            packet = b'\x00\x01\x00\x00\x00\x06\x01\x03\x03\x21\x00\x04'
            s.send(packet)
            resp = s.recv(1024)
            s.close()
            if len(resp) >= 17:
                val = struct.unpack('>d', resp[9:17])[0]
                return round(val / 1000, 3)  # Wh → kWh
    except Exception:
        pass
    return None  # Baglanti hatasi

def modbus_thread():
    logger.info("Modbus thread baslatildi (%d analizor, gunluk saat %02d:%02d)",
                len(ANALYZERS), READ_SAAT, READ_DAKIKA)
    _son_gun = None
    while True:
        now = datetime.now()
        bugun = now.date()
        saat_tamam = (now.hour == READ_SAAT and READ_DAKIKA <= now.minute < READ_DAKIKA + 5)   # 23:59 → yalnız 59. dk

        # Orijinal günlük okuma kilidi aktif edildi
        if saat_tamam and _son_gun != bugun:
            _son_gun = bugun
            ts = now.strftime('%Y-%m-%d %H:%M:%S')
            logger.info("Modbus gunluk okuma basliyor: %s", ts)
            current_data = []
            ok_count = 0

            for dev in ANALYZERS:
                # Canlı güç okuması aynı sayaçlara gidiyor; kilit ikisinin
                # aynı anda aynı cihaza bağlanmasını önler (günlük okuma
                # ÖNCELİKLİ değildir, sadece çakışmaz).
                with cihaz_kilidi(dev):
                    val = modbus_get_kwh(dev)
                if val is not None:
                    ok_count += 1
                    status = f"{val} kWh"
                else:
                    status = "[Baglanti Hatasi]"
                current_data.append([ts, dev['name'], dev['ip'],
                                      val if val is not None else "", status])
                logger.debug("  %s: %s", dev['name'], status)

            # CSV'ye yaz (her turde uzerine yaz — en guncel veri)
            with open(MODBUS_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Okuma_Zamani", "Cihaz_Adi", "IP", "Enerji_kWh", "Durum"])
                for row in current_data:
                    writer.writerow(row)

            logger.info("Modbus gunluk okuma tamamlandi: %d/%d OK -> %s",
                        ok_count, len(ANALYZERS), MODBUS_CSV)

        time.sleep(KONTROL_SN)  # 23:59 penceresi tek dakika — sık kontrol

# ================================================================
# BACNET FONKSİYONLARI
# ================================================================

def _pack_length(packet):
    return packet[:2] + struct.pack(">H", len(packet)) + packet[4:]

def build_read_property(obj_type, obj_inst, prop_id=85,
                        invoke_id=1, dnet=None, dadr=None):
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    if dnet is not None and dadr is not None:
        npdu = struct.pack(">BBH B", 0x01, 0x20, dnet, len(dadr)) + dadr + b'\xff'
    else:
        npdu = bytes([0x01, 0x00])
    obj_id = (obj_type << 22) | obj_inst
    apdu  = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    return _pack_length(bvlc + npdu + apdu)

def parse_real_value(data):
    try:
        for i in range(4, min(15, len(data))):
            apdu_type = data[i] & 0xF0
            if apdu_type == 0x50:
                return "[Hata: Adres YOK]"
            if apdu_type in [0x60, 0x70]:
                return "[Hata: Reddedildi]"
            if apdu_type == 0x30:
                break

        prop_idx = data.find(b'\x19\x55')
        if prop_idx != -1:
            start = data.find(b'\x3e', prop_idx)
            end   = data.find(b'\x3f', start)
            payload = data[start+1:end] if (start != -1 and end != -1) else data[prop_idx+2:]
        else:
            start = data.rfind(b'\x3e')
            end   = data.rfind(b'\x3f')
            payload = data[start+1:end] if (start != -1 and end != -1) else data[-10:]

        if not payload:
            return "[Bos Cevap]"

        tag = payload[0]
        tag_class = (tag & 0xF0) >> 4
        tag_len   = tag & 0x0F
        idx = 1
        if tag_len == 5:
            if len(payload) > 1:
                tag_len = payload[1]
                idx = 2
            else:
                return "[Bozuk Veri]"

        if tag_class == 4 and len(payload) >= idx + 4:    # REAL
            return round(struct.unpack(">f", payload[idx:idx+4])[0], 3)
        elif tag_class == 1:                               # BOOLEAN
            return 1.0 if tag == 0x11 else 0.0
        elif tag_class in [2, 9] and len(payload) >= idx + tag_len:  # UINT/ENUM
            return float(int.from_bytes(payload[idx:idx+tag_len], "big", signed=False))
        elif tag_class == 3 and len(payload) >= idx + tag_len:       # SINT
            return float(int.from_bytes(payload[idx:idx+tag_len], "big", signed=True))
        elif tag_class == 5 and len(payload) >= idx + 8:             # DOUBLE
            return round(struct.unpack(">d", payload[idx:idx+8])[0], 3)

    except Exception as e:
        return f"[Hata: {e}]"
    return "[Format Bilinmiyor]"

def bacnet_nokta_oku(gateway_ip, dnet, dadr_hex, obj_type, obj_inst, prop_id):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(BACNET_TIMEOUT)
    try:
        mac_str = str(dadr_hex).replace("0x", "").split('.')[0].strip()
        if len(mac_str) % 2 != 0:
            mac_str = "0" + mac_str
        mac_bytes = bytes.fromhex(mac_str)
        pkt = build_read_property(
            int(obj_type), int(obj_inst), prop_id,
            invoke_id=random.randint(1, 255),
            dnet=int(dnet), dadr=mac_bytes
        )
        sock.sendto(pkt, (gateway_ip, BACNET_PORT))
        data, _ = sock.recvfrom(1024)
        return parse_real_value(data)
    except socket.timeout:
        return "[Zaman Asimi]"
    except Exception as e:
        return f"[Baglanti Hatasi: {e}]"
    finally:
        sock.close()

def bacnet_sablon_yolu() -> str:
    """Şablonun GÜNCEL yolu: önce configs/, yoksa kök (her çağrıda yeniden bakılır)."""
    return _EXCEL_FILE_CONFIGS if os.path.exists(_EXCEL_FILE_CONFIGS) else _EXCEL_FILE_ROOT


def bacnet_sablonu_oku():
    """Okuma şablonunu diskten okur → DataFrame; okunamazsa None.

    27.10.2026: Şablon eskiden yalnızca program AÇILIRKEN bir kez okunuyordu.
    Maslak'ta şablona DIS HAVA NEM ve KOJEN-1..4 DURUM eklendi, program yeniden
    başlatılmadığı için bu 5 nokta hiç okunmadı; hedefli_enerji_verileri.csv eski
    48 noktayla yazılmaya devam etti, energy_data'da Kojen_Adet ve
    Dis_Hava_Nem_Yuzde boş kaldı (ahu_collector şablonu her turda okuduğu için
    bacnet_ham_veriler.xlsx'te değerler görünüyordu). Artık her günlük okumadan
    hemen önce çağrılır: şablona eklenen nokta ertesi sabah kendiliğinden okunur.
    """
    yol = bacnet_sablon_yolu()
    if not os.path.exists(yol):
        logger.warning("BACnet Excel dosyasi bulunamadi: %s", yol)
        return None
    try:
        import pandas as pd
        df = pd.read_excel(yol)
        df['Gateway IP']      = df['Gateway IP'].ffill()
        df['Network (DNET)']  = df['Network (DNET)'].ffill()
        return df
    except ImportError:
        logger.error("pandas/openpyxl yuklu degil: pip install pandas openpyxl")
    except Exception as e:
        logger.error("BACnet Excel okunamadi (%s): %s", yol, e)
    return None


def bacnet_thread():
    df = bacnet_sablonu_oku()
    if df is not None:
        logger.info("BACnet thread baslatildi (%d nokta, gunluk saat %02d:%02d)",
                    len(df), BACNET_SAAT, BACNET_DAKIKA)
    else:
        # Şablon şu an yoksa da thread bekler: dosya sonradan konursa
        # bir sonraki günlük okumada bulunur (program yeniden başlatılmadan).
        logger.warning("BACnet sablonu su an yok — gunluk okuma saatinde tekrar aranacak.")

    fieldnames = ["Timestamp", "Device_ID", "Point_Name", "Value", "Status"]
    _son_gun = None

    while True:
        now = datetime.now()
        bugun = now.date()
        saat_tamam = (now.hour == BACNET_SAAT and BACNET_DAKIKA <= now.minute < BACNET_DAKIKA + 5)

        if not (saat_tamam and _son_gun != bugun):
            time.sleep(KONTROL_SN)
            continue

        # Şablon her günlük okumadan ÖNCE yeniden okunur. Okunamazsa (Excel o
        # anda açık/kilitli, bozuk) son başarılı şablonla devam edilir.
        _yeni = bacnet_sablonu_oku()
        if _yeni is not None:
            if df is not None and len(_yeni) != len(df):
                logger.info("BACnet sablonu degisti: %d -> %d nokta", len(df), len(_yeni))
            df = _yeni
        elif df is not None:
            logger.warning("BACnet sablonu okunamadi — onceki sablonla (%d nokta) devam ediliyor", len(df))
        if df is None:
            logger.warning("BACnet sablonu yok — bugunku okuma atlandi.")
            _son_gun = bugun
            continue

        _son_gun = bugun
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        logger.info("BACnet gunluk okuma basliyor: %s", ts)
        results = []
        ok_count = 0

        for _, row in df.iterrows():
            try:
                gateway_ip = str(row['Gateway IP']).strip()
                dnet       = int(float(row['Network (DNET)']))
                mac_hex    = str(row['MAC (DADR)'])
                dev_id     = row['Device Instance ID']
                obj_type   = int(float(row['Object Type']))
                obj_inst   = int(float(row['Object Instance']))
                point_name = str(row['Point Name'])
            except Exception:
                continue

            val = bacnet_nokta_oku(gateway_ip, dnet, mac_hex,
                                   obj_type, obj_inst, PROP_PRESENT_VALUE)

            if isinstance(val, (float, int)):
                ok_count += 1
                results.append({"Timestamp": ts, "Device_ID": dev_id,
                                 "Point_Name": point_name,
                                 "Value": val, "Status": "OK"})
                logger.debug("  %s: %s", point_name, val)
            else:
                results.append({"Timestamp": ts, "Device_ID": dev_id,
                                 "Point_Name": point_name,
                                 "Value": None, "Status": val})
                logger.debug("  %s: %s", point_name, val)

        with open(BACNET_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

        logger.info("BACnet gunluk okuma tamamlandi: %d/%d OK -> %s",
                    ok_count, len(df), BACNET_CSV)
        time.sleep(60)

# ================================================================
# ANA BASLATI
# ================================================================

def start():
    t1 = threading.Thread(target=modbus_thread, daemon=True, name="modbus")
    t1.start()

    t2 = threading.Thread(target=bacnet_thread, daemon=True, name="bacnet")
    t2.start()

    # Canlı güç okuması (TRDP trafoları, ~15 sn). Modbus erişimi TEK süreçte
    # kalsın diye buradan başlatılır; sonucu configs/canli_guc_son.json'a
    # yazar, buluta taşımayı cloud_sync yapar. Modül yoksa/başlamazsa
    # toplayıcı normal çalışmaya devam eder — günlük okuma etkilenmez.
    try:
        import canli_guc
        canli_guc.baslat(kilit_al=cihaz_kilidi)
    except Exception as e:
        logger.warning("Canli guc okumasi baslatilamadi: %s", e)

    return t1, t2

if __name__ == "__main__":
    logger.info("=" * 55)
    logger.info("  Veri Toplayici baslatiliyor")
    logger.info("  Modbus: %d analizor | BACnet: Excel'den", len(ANALYZERS))
    logger.info("  Gunluk okuma: Modbus %02d:%02d, BACnet %02d:%02d", READ_SAAT, READ_DAKIKA, BACNET_SAAT, BACNET_DAKIKA)
    logger.info("=" * 55)

    start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Veri toplayici durduruldu.")
