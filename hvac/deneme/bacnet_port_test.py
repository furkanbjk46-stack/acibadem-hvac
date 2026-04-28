"""
Farklı kaynak portlardan BACnet isteği gönderir.
Port çakışmasının sorun olmadığını doğrular.
LOCAL_IP = 192.168.0.254
"""

import socket
import struct

LOCAL_IP = "192.168.0.254"
TARGET_PORT = 47808

GATEWAYS = ["192.168.0.2", "192.168.0.4", "192.168.0.8"]
TEST_PORTS = [47808, 50668, 0]  # 0 = OS random port


def build_read_property(obj_type=0, obj_inst=1, prop_id=85, invoke_id=1):
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    obj_id = (obj_type << 22) | obj_inst
    apdu = bytes([0x00, 0x04, invoke_id, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def test_port(src_port, gw_ip):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((LOCAL_IP, src_port))
        actual_port = sock.getsockname()[1]
        sock.settimeout(3.0)
        pkt = build_read_property()
        sock.sendto(pkt, (gw_ip, TARGET_PORT))
        print(f"  src_port={actual_port} -> {gw_ip}: istek gönderildi", end=" | ")
        try:
            data, _ = sock.recvfrom(1024)
            print(f"YANIT {len(data)} byte")
            return True
        except socket.timeout:
            print("yanıt yok")
            return False
    except OSError as e:
        print(f"  src_port={src_port} HATA: {e}")
        return False
    finally:
        sock.close()


if __name__ == "__main__":
    print(f"Port testi — LOCAL_IP={LOCAL_IP}\n")
    for gw in GATEWAYS:
        print(f"Gateway: {gw}")
        for port in TEST_PORTS:
            test_port(port, gw)
        print()
