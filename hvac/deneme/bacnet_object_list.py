"""
Desigo CC'nin object-list property'sini okur (property 76).
Bulgu: Desigo CC sadece 1 objeye sahip (Device objesi kendisi).
LOCAL_IP = 192.168.0.254
"""

import socket
import struct

LOCAL_IP = "192.168.0.254"
LOCAL_PORT = 47808
DESIGO_IP = "192.168.0.1"
DESIGO_PORT = 47808

# Bilinen Desigo Device instance'ları (YABE'den görülen)
DEVICE_INSTANCES = [2099287, 2099291]


def build_read_property(device_inst, prop_id=76, invoke_id=1):
    """Device objesinin object-list'ini okur (prop 76)."""
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    # Device object type = 8
    obj_id = (8 << 22) | device_inst
    apdu = bytes([0x00, 0x04, invoke_id, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def parse_object_list(data):
    """APDU'daki object-list'i parse eder."""
    objects = []
    obj_type_names = {
        0: "AI", 1: "AO", 2: "AV", 3: "BI", 4: "BO", 5: "BV",
        8: "Device", 10: "File", 13: "MI", 14: "MO", 19: "MV",
    }
    i = 0
    while i < len(data) - 4:
        # 4-byte object identifier: üst 10 bit = type, alt 22 bit = instance
        if i + 4 <= len(data):
            raw = struct.unpack(">I", data[i:i+4])[0]
            obj_type = (raw >> 22) & 0x3FF
            obj_inst = raw & 0x3FFFFF
            type_name = obj_type_names.get(obj_type, f"type{obj_type}")
            objects.append(f"{type_name}:{obj_inst}")
            i += 4
        else:
            break
    return objects


def oku_object_list(device_inst):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, 0))
    sock.settimeout(5.0)

    pkt = build_read_property(device_inst)
    sock.sendto(pkt, (DESIGO_IP, DESIGO_PORT))
    print(f"Device:{device_inst} object-list isteği -> {DESIGO_IP}", end=" | ")

    try:
        data, _ = sock.recvfrom(4096)
        print(f"YANIT {len(data)} byte")
        print(f"  Ham: {data.hex()}")
        # Basit parse denemesi
        objs = parse_object_list(data[6:])
        print(f"  Bulunan objeler ({len(objs)}): {objs[:20]}")
        return objs
    except socket.timeout:
        print("YANIT YOK")
        return []
    finally:
        sock.close()


if __name__ == "__main__":
    print(f"Desigo object-list okuma — LOCAL_IP={LOCAL_IP}\n")
    for dev in DEVICE_INSTANCES:
        objs = oku_object_list(dev)
        print(f"  Device:{dev} toplam {len(objs)} obje\n")
