"""
Gateway'e direkt unicast ReadProperty + 10 saniye dinleme.
DÜZELTME: LOCAL_IP = 192.168.0.254 (eskiden 172.17.91.210 idi)

Önceki sorun: Gateway yanıtı 172.17.91.210'a unicast gönderiyordu
ama o subnet'e route yoktu → paket kayboluyordu.
Düzeltme: 192.168.0.254 kullanınca gateway yanıtı doğru geliyor.
"""

import socket
import struct
import time

LOCAL_IP = "192.168.0.254"   # DÜZELTİLDİ (eski: 172.17.91.210)
LOCAL_PORT = 47808

GATEWAYS = {
    "OAT":     "192.168.0.2",
    "Chiller": "192.168.0.4",
    "AHU":     "192.168.0.8",
}


def build_who_is():
    bvlc = bytes([0x81, 0x0b, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    apdu = bytes([0x10, 0x08])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


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


def gateway_test(gw_name, gw_ip, dinle_sure=10):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((LOCAL_IP, LOCAL_PORT))
    sock.settimeout(1.0)

    print(f"\n{'='*50}")
    print(f"Gateway: {gw_name} ({gw_ip})")
    print(f"LOCAL_IP: {LOCAL_IP}  |  Dinleme: {dinle_sure}s")

    # Who-Is gönder
    who_is = build_who_is()
    sock.sendto(who_is, (gw_ip, LOCAL_PORT))
    print(f"Who-Is gönderildi -> {gw_ip}")

    # ReadProperty AI:1 gönder
    rp = build_read_property(0, 1, 85)
    sock.sendto(rp, (gw_ip, LOCAL_PORT))
    print(f"ReadProperty AI:1 gönderildi -> {gw_ip}")

    # Yanıt dinle
    paket_sayisi = 0
    deadline = time.time() + dinle_sure
    print(f"Yanıt bekleniyor ({dinle_sure}s)...")

    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(2048)
            paket_sayisi += 1
            pdu_type = "?"
            if len(data) > 6:
                apdu_byte = data[6] if len(data) > 6 else 0
                if apdu_byte == 0x10:
                    pdu_type = "Unconf"
                elif (apdu_byte & 0xF0) == 0x20:
                    pdu_type = "ComplexACK"
                elif (apdu_byte & 0xF0) == 0x40:
                    pdu_type = "Error"
            print(f"  [{paket_sayisi}] {addr[0]}:{addr[1]} — {len(data)}b — {pdu_type} — {data[:8].hex()}")
        except socket.timeout:
            kalan = int(deadline - time.time())
            print(f"\r  {kalan}s kaldı...", end="", flush=True)

    print(f"\nSonuç: {paket_sayisi} paket alındı")
    sock.close()
    return paket_sayisi


if __name__ == "__main__":
    print(f"Gateway direkt test — LOCAL_IP={LOCAL_IP}\n")
    for name, ip in GATEWAYS.items():
        gateway_test(name, ip, dinle_sure=10)
