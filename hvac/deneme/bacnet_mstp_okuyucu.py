"""
BACnet Who-Is broadcast + MS/TP routing testi.
NPDU ctrl=0x00 kullanılır (0x20 HATA yaratır).
LOCAL_IP = 192.168.0.254
"""

import socket
import struct
import time

LOCAL_IP = "192.168.0.254"
LOCAL_PORT = 47808
BROADCAST = "192.168.0.255"

def build_who_is(low=0, high=4194303):
    """BACnet Who-Is broadcast paketi."""
    bvlc = bytes([0x81, 0x0b, 0x00, 0x00])   # 0x0b = Original-Broadcast-NPDU
    npdu = bytes([0x01, 0x00])                 # ctrl=0x00 (önemli!)
    apdu = bytes([0x10, 0x08])                 # Unconfirmed Who-Is
    if low != 0 or high != 4194303:
        apdu += bytes([0x09, low & 0xFF, 0x19, (high >> 8) & 0xFF, high & 0xFF])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def build_read_property_routed(net, mac, obj_type, obj_inst, prop_id=85, invoke_id=1):
    """MS/TP routing üzerinden ReadProperty (NPDU routing bilgisiyle)."""
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    # NPDU ctrl=0x20: DNET mevcut, unicast
    dnet = struct.pack(">H", net)    # Destination network
    dlen = 1
    dadr = bytes([mac])
    npdu = bytes([0x01, 0x20]) + dnet + bytes([dlen]) + dadr + bytes([0xFF])
    # APDU
    obj_id = (obj_type << 22) | obj_inst
    apdu = bytes([0x00, 0x04, invoke_id, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def who_is_scan():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((LOCAL_IP, LOCAL_PORT))
    sock.settimeout(5.0)

    print(f"Who-Is broadcast ({LOCAL_IP} -> {BROADCAST})")
    pkt = build_who_is()
    sock.sendto(pkt, (BROADCAST, LOCAL_PORT))

    found = []
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(1024)
            print(f"  I-Am from {addr[0]}: {data.hex()}")
            found.append(addr[0])
        except socket.timeout:
            break

    sock.close()
    return found


def read_mstp_point(gateway_ip, net, mac, obj_type, obj_inst, label):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, 0))
    sock.settimeout(5.0)

    pkt = build_read_property_routed(net, mac, obj_type, obj_inst)
    sock.sendto(pkt, (gateway_ip, LOCAL_PORT))
    print(f"  {label} [{gateway_ip} net={net} mac={mac}]: istek gönderildi", end=" -> ")
    try:
        data, addr = sock.recvfrom(1024)
        print(f"YANIT {len(data)} byte")
        return data
    except socket.timeout:
        print("yanıt yok")
        return None
    finally:
        sock.close()


if __name__ == "__main__":
    print("=== Who-Is Tarama ===")
    devices = who_is_scan()
    print(f"Bulunan cihaz IP'leri: {devices}\n")

    # Örnek MS/TP okuma (network=1, mac=1, AI:1 → Present Value)
    print("=== MS/TP Okuma Testi ===")
    read_mstp_point("192.168.0.2", 1, 1, 0, 1, "OAT AI:1")
    read_mstp_point("192.168.0.4", 1, 1, 0, 1, "Chiller AI:1")
    read_mstp_point("192.168.0.8", 1, 1, 0, 1, "AHU AI:1")
