"""
Desigo CC'nin kendi BACnet object space'ini test eder.
192.168.0.1 = Desigo CC sunucu IP (ağa göre güncelle)
LOCAL_IP = 192.168.0.254 (Siemens adaptörü, gateway'lerle aynı subnet)
"""

import socket
import struct
import time

LOCAL_IP = "192.168.0.254"
LOCAL_PORT = 47808
DESIGO_IP = "192.168.0.1"
DESIGO_PORT = 47808

def build_read_property(device_instance, obj_type, obj_instance, prop_id=85):
    """BACnet ReadProperty isteği oluşturur."""
    # BVLC header
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    # NPDU
    npdu = bytes([0x01, 0x00])
    # APDU - ReadProperty Request
    apdu = bytes([
        0x00,        # PDU type: Confirmed Request
        0x04,        # Max APDU + segments
        0x01,        # Invoke ID
        0x0c,        # Service: ReadProperty
    ])
    # Object identifier
    obj_id = (obj_type << 22) | obj_instance
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    # Property identifier
    apdu += bytes([0x19, prop_id])

    packet = bvlc + npdu + apdu
    # Uzunluk güncelle
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def test_desigo_objects():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, LOCAL_PORT))
    sock.settimeout(3.0)

    print(f"Desigo CC test: {DESIGO_IP}:{DESIGO_PORT}")
    print(f"LOCAL_IP: {LOCAL_IP}\n")

    # AI (0), AO (1), AV (2), BI (3), BO (4), BV (5)
    test_cases = [
        (0, 1, "AI:1"),
        (0, 2, "AI:2"),
        (1, 1, "AO:1"),
        (2, 1, "AV:1"),
        (8, 1, "Device:1"),
    ]

    for obj_type, obj_inst, label in test_cases:
        pkt = build_read_property(1, obj_type, obj_inst)
        sock.sendto(pkt, (DESIGO_IP, DESIGO_PORT))
        print(f"  {label}: istek gönderildi", end=" -> ")
        try:
            data, addr = sock.recvfrom(1024)
            print(f"YANIT {len(data)} byte — {data.hex()}")
        except socket.timeout:
            print("yanıt yok (timeout)")

    sock.close()


if __name__ == "__main__":
    test_desigo_objects()
