"""
Desigo CC üzerinden BACnet routing testi.
DÜZELTME: LOCAL_IP = 192.168.0.254 (eskiden 172.17.91.210 idi — yanıt kayboluyordu)

Gateway IP'leri:
  OAT    -> 192.168.0.2
  Chiller -> 192.168.0.4
  AHU    -> 192.168.0.8
"""

import socket
import struct
import time

LOCAL_IP = "192.168.0.254"   # Siemens adaptörü — gateway'lerle aynı subnet
LOCAL_PORT = 47808

GATEWAYS = {
    "OAT":     "192.168.0.2",
    "Chiller": "192.168.0.4",
    "AHU":     "192.168.0.8",
}

# Her gateway için okuma noktaları: (obj_type, obj_instance, property_id, label)
POINTS = {
    "OAT": [
        (0, 1, 85, "Dış Hava Sıcaklığı"),
    ],
    "Chiller": [
        (0, 1, 85, "Chiller Çıkış Suyu Sıcaklığı"),
        (0, 2, 85, "Chiller Giriş Suyu Sıcaklığı"),
        (0, 3, 85, "Chiller Güç (kW)"),
    ],
    "AHU": [
        (0, 1, 85, "AHU Besleme Hava Sıcaklığı"),
        (0, 2, 85, "AHU Dönüş Hava Sıcaklığı"),
        (4, 1, 85, "AHU Fan Durumu"),
    ],
}


def build_read_property(obj_type, obj_inst, prop_id=85, invoke_id=1):
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    obj_id = (obj_type << 22) | obj_inst
    apdu = bytes([0x00, 0x04, invoke_id, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def parse_real_value(data):
    """APDU'dan float değeri çıkarır."""
    try:
        # ComplexACK -> ReadProperty -> application tag 4 (real)
        idx = data.index(0x4e) if 0x4e in data else -1
        if idx == -1:
            return None
        for i in range(idx, len(data) - 4):
            if (data[i] & 0xF0) == 0x40:  # application tag 4, len=4
                val = struct.unpack(">f", data[i+1:i+5])[0]
                return round(val, 3)
    except Exception:
        pass
    return None


def oku(gateway_name, obj_type, obj_inst, prop_id, label):
    ip = GATEWAYS[gateway_name]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, 0))
    sock.settimeout(5.0)

    pkt = build_read_property(obj_type, obj_inst, prop_id)
    sock.sendto(pkt, (ip, LOCAL_PORT))
    print(f"  [{gateway_name}] {label}: istek -> {ip}", end=" | ")
    try:
        data, _ = sock.recvfrom(1024)
        val = parse_real_value(data)
        if val is not None:
            print(f"DEGER = {val}")
        else:
            print(f"YANIT var ama parse edilemedi: {data.hex()}")
        return val
    except socket.timeout:
        print("YANIT YOK (timeout 5s)")
        return None
    finally:
        sock.close()


def tum_noktalari_oku():
    print(f"BACnet okuma başlıyor — LOCAL_IP={LOCAL_IP}\n")
    sonuclar = {}
    for cihaz, noktalar in POINTS.items():
        print(f"--- {cihaz} ({GATEWAYS[cihaz]}) ---")
        for obj_type, obj_inst, prop_id, label in noktalar:
            val = oku(cihaz, obj_type, obj_inst, prop_id, label)
            sonuclar[f"{cihaz}_{label}"] = val
        print()
    return sonuclar


if __name__ == "__main__":
    tum_noktalari_oku()
