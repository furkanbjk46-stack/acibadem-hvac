# data_collector.py
# Modbus (Janitza/Siemens analizorler) + BACnet (Desigo) veri toplayici
# Her 30 dakikada bir okuma yapar, sonuclari CSV'ye yazar.
# portal_watchdog.py tarafindan subprocess olarak baslatilir.

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
ANALYZERS = [
    {"ip": "172.17.91.100", "name": "MCC-1",        "brand": "janitza"},
    {"ip": "172.17.91.101", "name": "MCC-2",        "brand": "janitza"},
    {"ip": "172.17.91.103", "name": "MCC-4",        "brand": "janitza"},
    {"ip": "172.17.91.105", "name": "MCC-6",        "brand": "janitza"},
    {"ip": "172.17.91.106", "name": "MCC-7",        "brand": "janitza"},
    {"ip": "172.17.91.107", "name": "CHILLER-1",    "brand": "janitza"},
    {"ip": "172.17.91.108", "name": "CHILLER-2",    "brand": "janitza"},
    {"ip": "172.17.91.109", "name": "CHILLER-3",    "brand": "janitza"},
    {"ip": "172.17.91.110", "name": "KULE-2",       "brand": "siemens"},
    {"ip": "172.17.91.111", "name": "KULE-3",       "brand": "siemens"},
    {"ip": "172.17.91.117", "name": "CHILLER-4",    "brand": "siemens"},
    {"ip": "172.17.91.118", "name": "CHILLER-5",    "brand": "siemens"},
    {"ip": "172.17.91.122", "name": "KULE-1",       "brand": "siemens"},
    {"ip": "172.18.91.130", "name": "2BK-MCC-D01",  "brand": "siemens"},
    {"ip": "172.18.91.131", "name": "2BK-MCC-D02",  "brand": "siemens"},
    {"ip": "172.18.91.132", "name": "4BK-MCC-E01",  "brand": "siemens"},
    {"ip": "172.18.91.133", "name": "4BK-MCC-E02",  "brand": "siemens"},
    {"ip": "172.18.91.134", "name": "4BK-MCC-F01",  "brand": "siemens"},
    {"ip": "172.18.91.135", "name": "CK-MCC-D01",   "brand": "siemens"},
    {"ip": "172.18.91.136", "name": "CK-MCC-E01",   "brand": "siemens"},
    {"ip": "172.18.91.137", "name": "CK-MCC-F01",   "brand": "siemens"},
]

MODBUS_PORT    = 502
MODBUS_CSV     = os.path.join(BASE_DIR, "analizor_guncel_veriler.csv")
READ_INTERVAL  = 1800  # 30 dakika (saniye)

# ================================================================
# BACNET YAPILANDIRMASI
# ================================================================
BACNET_PORT   = 47808
BACNET_TIMEOUT = 4.0
EXCEL_FILE    = os.path.join(BASE_DIR, "hedefli_okuma_sablonu_2.xlsx.xlsx")
BACNET_CSV    = os.path.join(BASE_DIR, "hedefli_enerji_verileri.csv")
PROP_PRESENT_VALUE = 85

# ================================================================
# MODBUS FONKSİYONLARI
# ================================================================

def modbus_get_kwh(device):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        s.connect((device["ip"], MODBUS_PORT))

        if device["brand"] == "janitza":
            packet = b'\x00\x01\x00\x00\x00\x06\x01\x03\x4a\x74\x00\x02'
            s.send(packet)
            resp = s.recv(1024)
            s.close()
            if len(resp) >= 13:
                val = struct.unpack('>f', resp[9:13])[0]
                return round(val, 1)

        elif device["brand"] == "siemens":
            packet = b'\x00\x01\x00\x00\x00\x06\x01\x03\x03\x21\x00\x04'
            s.send(packet)
            resp = s.recv(1024)
            s.close()
            if len(resp) >= 17:
                val = struct.unpack('>d', resp[9:17])[0]
                return round(val, 1)
    except Exception:
        pass
    return None  # Baglanti hatasi


def modbus_thread():
    logger.info("Modbus thread baslatildi (%d analizor, %d dk aralik)",
                len(ANALYZERS), READ_INTERVAL // 60)
    while True:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info("Modbus okuma turu basliyor: %s", ts)
        current_data = []
        ok_count = 0

        for dev in ANALYZERS:
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

        logger.info("Modbus turu tamamlandi: %d/%d OK -> %s",
                    ok_count, len(ANALYZERS), MODBUS_CSV)
        time.sleep(READ_INTERVAL)


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


def bacnet_thread():
    # Excel dosyasi yoksa thread baslamaz
    if not os.path.exists(EXCEL_FILE):
        logger.warning("BACnet Excel dosyasi bulunamadi: %s", EXCEL_FILE)
        logger.warning("BACnet thread baslatilmadi. Dosyayi bu klasore kopyalayin.")
        return

    try:
        import pandas as pd
        df = pd.read_excel(EXCEL_FILE)
        df['Gateway IP']      = df['Gateway IP'].ffill()
        df['Network (DNET)']  = df['Network (DNET)'].ffill()
    except ImportError:
        logger.error("pandas/openpyxl yuklu degil: pip install pandas openpyxl")
        return
    except Exception as e:
        logger.error("BACnet Excel okunamadi: %s", e)
        return

    logger.info("BACnet thread baslatildi (%d nokta, %d dk aralik)",
                len(df), READ_INTERVAL // 60)

    fieldnames = ["Timestamp", "Device_ID", "Point_Name", "Value", "Status"]

    while True:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info("BACnet okuma turu basliyor: %s", ts)
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

        logger.info("BACnet turu tamamlandi: %d/%d OK -> %s",
                    ok_count, len(df), BACNET_CSV)
        time.sleep(READ_INTERVAL)


# ================================================================
# ANA BASLATI
# ================================================================

def start():
    t1 = threading.Thread(target=modbus_thread, daemon=True, name="modbus")
    t1.start()

    t2 = threading.Thread(target=bacnet_thread, daemon=True, name="bacnet")
    t2.start()

    return t1, t2


if __name__ == "__main__":
    logger.info("=" * 55)
    logger.info("  Veri Toplayici baslatiliyor")
    logger.info("  Modbus: %d analizor | BACnet: Excel'den", len(ANALYZERS))
    logger.info("  Okuma araligi: %d dakika", READ_INTERVAL // 60)
    logger.info("=" * 55)

    start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Veri toplayici durduruldu.")
