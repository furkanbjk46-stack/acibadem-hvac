"""
BACnet Agent — Maslak PC'de çalışır (192.168.0.254).
Device 2099296 (MASLAK2'AS65) -> IP: 192.168.0.237
AI:1 ve AI:2 okur -> CSV + Supabase.

NOT: Desigo CC açıkken PXC direkt yanıt vermiyor.
     Bu script Desigo kapalıyken çalışır.

Çalıştırma: python bacnet_agent.py
"""

import socket
import struct
import time
import csv
import os
from datetime import datetime

LOCAL_IP    = "192.168.0.254"
LOCAL_PORT  = 47808
BROADCAST   = "192.168.0.255"
TIMEOUT     = 5.0
CSV_FILE    = "energy_data.csv"

TARGET_DEVICE    = 2099296
TARGET_DEVICE_IP = "192.168.0.237"   # I-Am ile keşfedildi — hardcode

# Okunacak noktalar: (obj_type, obj_instance, property_id, label)
POINTS = [
    (0, 1, 85, "FCU_IcSicaklikSP"),   # Analog Input 1 - FCUISISET
    (0, 2, 85, "FCU_SogutmaSP"),      # Analog Input 2 - FCUSOGSET
]


# ─── BACnet paket yardımcıları ────────────────────────────────────────────────

def _pack_length(packet):
    return packet[:2] + struct.pack(">H", len(packet)) + packet[4:]


def build_who_is(low=0, high=4194303):
    bvlc = bytes([0x81, 0x0b, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    apdu = bytes([0x10, 0x08])
    if low != 0 or high != 4194303:
        apdu += bytes([0x09, low & 0xFF, 0x19, (high >> 8) & 0xFF, high & 0xFF])
    return _pack_length(bvlc + npdu + apdu)


def build_read_property(obj_type, obj_inst, prop_id=85, invoke_id=1):
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    obj_id = (obj_type << 22) | obj_inst
    apdu  = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    return _pack_length(bvlc + npdu + apdu)


def parse_iam_device_id(data):
    """I-Am APDU'sundan device instance çıkarır."""
    try:
        # BVLC(4) + NPDU(en az 2) + APDU
        # Unconfirmed I-Am: 0x10 0x00 + BACnetObjectIdentifier
        idx = data.find(b'\x10\x00')
        if idx == -1:
            return None
        apdu = data[idx + 2:]
        # İlk 4 byte = object identifier (context 0 veya application tag)
        # Application tag 12 (object-id) = 0xC4
        for i in range(len(apdu) - 4):
            if apdu[i] == 0xC4:
                raw = struct.unpack(">I", apdu[i+1:i+5])[0]
                obj_type = (raw >> 22) & 0x3FF
                obj_inst = raw & 0x3FFFFF
                if obj_type == 8:  # Device
                    return obj_inst
    except Exception:
        pass
    return None


def parse_real_value(data):
    """ComplexACK ReadProperty yanıtından float değeri çıkarır."""
    try:
        # 0x4e = opening tag 14, 0x4f = closing tag 14
        start = data.find(b'\x4e')
        if start == -1:
            # Alternatif: application tag 4 (real) ara
            for i in range(len(data) - 4):
                if data[i] == 0x44:  # app tag 4, len 4
                    return round(struct.unpack(">f", data[i+1:i+5])[0], 3)
            return None
        payload = data[start+1:]
        for i in range(len(payload) - 4):
            if payload[i] == 0x44:  # application real
                return round(struct.unpack(">f", payload[i+1:i+5])[0], 3)
            # Unsigned int
            tag = payload[i]
            tag_num = (tag & 0xF0) >> 4
            tag_len = tag & 0x07
            if tag_num == 2 and 1 <= tag_len <= 4:  # Unsigned
                val = int.from_bytes(payload[i+1:i+1+tag_len], "big")
                return float(val)
    except Exception:
        pass
    return None


# ─── Cihaz keşfi ─────────────────────────────────────────────────────────────

def cihaz_ip_bul(device_instance, deneme=3):
    """Who-Is broadcast ile device_instance'ın IP adresini bulur."""
    for _ in range(deneme):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((LOCAL_IP, LOCAL_PORT))
        except OSError:
            sock.bind(("", LOCAL_PORT))
        sock.settimeout(5.0)

        pkt = build_who_is(device_instance, device_instance)
        sock.sendto(pkt, (BROADCAST, LOCAL_PORT))
        print(f"  Who-Is gönderildi (device={device_instance}) -> {BROADCAST}")

        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(1024)
                found = parse_iam_device_id(data)
                if found == device_instance:
                    print(f"  I-Am alındı: Device:{device_instance} @ {addr[0]}")
                    sock.close()
                    return addr[0]
            except socket.timeout:
                break
        sock.close()
        print("  Yeniden deneniyor...")
        time.sleep(2)

    print(f"  UYARI: Device:{device_instance} bulunamadı, 192.168.0.1 deneniyor")
    return "192.168.0.1"


# ─── Nokta okuma ──────────────────────────────────────────────────────────────

def nokta_oku(device_ip, obj_type, obj_inst, prop_id, label):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, 0))
    sock.settimeout(TIMEOUT)
    try:
        pkt = build_read_property(obj_type, obj_inst, prop_id)
        sock.sendto(pkt, (device_ip, LOCAL_PORT))
        data, _ = sock.recvfrom(1024)

        # Hata yanıtı kontrolü
        if len(data) > 6 and (data[6] & 0xF0) == 0x50:
            err_class = data[8] if len(data) > 8 else "?"
            err_code  = data[9] if len(data) > 9 else "?"
            print(f"  {label}: ERR class={err_class} code={err_code}")
            return None

        val = parse_real_value(data)
        return val
    except socket.timeout:
        return None
    except Exception as e:
        print(f"  {label} HATA: {e}")
        return None
    finally:
        sock.close()


# ─── CSV ──────────────────────────────────────────────────────────────────────

def csv_yaz(row, fieldnames):
    yeni = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if yeni:
            w.writeheader()
        w.writerow(row)


def supabase_gonder(row):
    try:
        from supabase import create_client
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            return False
        sb = create_client(url, key)
        sb.table("energy_data").insert(row).execute()
        return True
    except Exception as e:
        print(f"  Supabase hatası: {e}")
        return False


# ─── Ana döngü ────────────────────────────────────────────────────────────────

def main(aralik=60):
    print("=" * 55)
    print(f"BACnet Agent — LOCAL_IP={LOCAL_IP}")
    print(f"Device: {TARGET_DEVICE} @ {TARGET_DEVICE_IP}  |  Aralık: {aralik}s")
    print("=" * 55)

    fieldnames = ["timestamp"] + [p[3] for p in POINTS]
    device_ip  = TARGET_DEVICE_IP

    while True:
        ts  = datetime.now().isoformat(timespec="seconds")
        row = {"timestamp": ts}

        print(f"[{ts}] Okuma yapılıyor...")
        tumu_ok = True

        for obj_type, obj_inst, prop_id, label in POINTS:
            val = nokta_oku(device_ip, obj_type, obj_inst, prop_id, label)
            row[label] = val
            if val is None:
                durum = "YANIT YOK"
                tumu_ok = False
            else:
                durum = str(val)
            print(f"  {label:25s}: {durum}")

        csv_yaz(row, fieldnames)
        print(f"  -> CSV'ye yazıldı ({CSV_FILE})")

        if supabase_gonder(row):
            print("  -> Supabase OK")

        # Cihaz kaybolursa Who-Is ile yeniden keşfet
        if not tumu_ok:
            print("  Bazı noktalar okunamadı, cihaz yeniden aranıyor...")
            device_ip = cihaz_ip_bul(TARGET_DEVICE)

        time.sleep(aralik)


if __name__ == "__main__":
    main(aralik=60)
