"""
BACnet üretim okuyucusu.
OAT, Chiller ve AHU verilerini okur -> energy_data.csv -> Supabase.

Gateway IP'leri:
  OAT    -> 192.168.0.2
  Chiller -> 192.168.0.4
  AHU    -> 192.168.0.8

LOCAL_IP = 192.168.0.254 (Siemens adaptörü, gateway'lerle aynı subnet)
"""

import socket
import struct
import csv
import time
import os
from datetime import datetime

LOCAL_IP = "192.168.0.254"
BACNET_PORT = 47808
TIMEOUT = 5.0
OUTPUT_CSV = "energy_data.csv"

# Okuma noktaları tanımı
# Format: (gateway_ip, obj_type, obj_instance, property_id, alan_adi, birim)
POINTS = [
    # OAT Gateway
    ("192.168.0.2", 0, 1, 85, "oat_sicaklik",        "°C"),
    # Chiller Gateway
    ("192.168.0.4", 0, 1, 85, "chiller_cikis_suyu",  "°C"),
    ("192.168.0.4", 0, 2, 85, "chiller_giris_suyu",  "°C"),
    ("192.168.0.4", 0, 3, 85, "chiller_guc_kw",      "kW"),
    ("192.168.0.4", 0, 4, 85, "chiller_akis",        "m3/h"),
    # AHU Gateway
    ("192.168.0.8", 0, 1, 85, "ahu_besleme_hava",    "°C"),
    ("192.168.0.8", 0, 2, 85, "ahu_donus_hava",      "°C"),
    ("192.168.0.8", 4, 1, 85, "ahu_fan_durumu",      "bool"),
    ("192.168.0.8", 0, 3, 85, "ahu_nem",             "%"),
]


def build_read_property(obj_type, obj_inst, prop_id=85, invoke_id=1):
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    obj_id = (obj_type << 22) | obj_inst
    apdu = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def parse_value(data):
    """BACnet APDU'dan değer çıkarır (real, boolean, unsigned)."""
    try:
        # ComplexACK: 0x30 xx 0x0c 0x4e ... 0x4f
        if len(data) < 8:
            return None
        apdu_start = 4  # BVLC(4) + NPDU(2) = 6, ama değişebilir
        for offset in range(4, min(len(data), 20)):
            tag = data[offset]
            tag_num = (tag & 0xF0) >> 4
            tag_class = (tag & 0x08) >> 3
            length = tag & 0x07

            if tag_class == 0:  # Application tag
                if tag_num == 4 and length == 4:  # Real
                    if offset + 5 <= len(data):
                        val = struct.unpack(">f", data[offset+1:offset+5])[0]
                        return round(val, 3)
                elif tag_num == 1 and length == 1:  # Boolean
                    return bool(data[offset+1])
                elif tag_num == 2:  # Unsigned int
                    if length <= 4 and offset + 1 + length <= len(data):
                        val = int.from_bytes(data[offset+1:offset+1+length], "big")
                        return val
    except Exception:
        pass
    return None


def oku_nokta(gw_ip, obj_type, obj_inst, prop_id, alan_adi):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, 0))
    sock.settimeout(TIMEOUT)
    try:
        pkt = build_read_property(obj_type, obj_inst, prop_id)
        sock.sendto(pkt, (gw_ip, BACNET_PORT))
        data, _ = sock.recvfrom(1024)
        val = parse_value(data)
        return val
    except socket.timeout:
        return None
    except Exception as e:
        print(f"  HATA [{alan_adi}]: {e}")
        return None
    finally:
        sock.close()


def okuma_yap():
    """Tüm noktaları okur, dict döner."""
    ts = datetime.now().isoformat(timespec="seconds")
    row = {"timestamp": ts}

    for gw_ip, obj_type, obj_inst, prop_id, alan, birim in POINTS:
        val = oku_nokta(gw_ip, obj_type, obj_inst, prop_id, alan)
        row[alan] = val
        durum = f"{val} {birim}" if val is not None else "YANIT YOK"
        print(f"  {alan:30s}: {durum}")

    return row


def csv_yaz(row):
    """Satırı CSV'ye ekler, ilk satırda başlık yazar."""
    fieldnames = ["timestamp"] + [p[4] for p in POINTS]
    yeni_dosya = not os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if yeni_dosya:
            writer.writeheader()
        writer.writerow(row)


def supabase_gonder(row):
    """Supabase'e gönderim (entegrasyon için placeholder)."""
    try:
        from supabase import create_client
        import os as _os
        url = _os.environ.get("SUPABASE_URL")
        key = _os.environ.get("SUPABASE_KEY")
        if not url or not key:
            return False
        supabase = create_client(url, key)
        supabase.table("energy_data").insert(row).execute()
        return True
    except Exception as e:
        print(f"  Supabase hatası: {e}")
        return False


def main(aralik_saniye=60):
    print(f"BACnet Reader başlatıldı — LOCAL_IP={LOCAL_IP}")
    print(f"Okuma aralığı: {aralik_saniye}s  |  CSV: {OUTPUT_CSV}\n")

    while True:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{ts}] Okuma yapılıyor...")

        row = okuma_yap()
        csv_yaz(row)

        okunan = sum(1 for k, v in row.items() if k != "timestamp" and v is not None)
        print(f"  => {okunan}/{len(POINTS)} nokta okundu, CSV'ye yazıldı")

        supabase_ok = supabase_gonder(row)
        if supabase_ok:
            print("  => Supabase gönderildi")

        time.sleep(aralik_saniye)


if __name__ == "__main__":
    main(aralik_saniye=60)
