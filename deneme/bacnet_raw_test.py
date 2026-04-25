# bacnet_raw_test.py
# BAC0 kullanmaz — ham UDP soketleri ile BACnet Who-Is gonderir,
# gelen tum I-Am yanitlarini ekrana yazar.
# Hem port musaitligini hem ag baglantisini test eder.
# Calistir: python bacnet_raw_test.py

import socket
import struct
import time
import sys

BACNET_PORT = 47808
GATEWAYS    = ["192.168.0.2", "192.168.0.3", "192.168.0.4", "192.168.0.5"]
BEKLEME_SN  = 20  # yanit bekleme suresi

# YABE'nin kullandigi IP — bunu degistirme
LOCAL_IP = "172.17.91.210"


def _bvlc(fonksiyon: int, payload: bytes) -> bytes:
    uzunluk = 4 + len(payload)
    return struct.pack(">BBH", 0x81, fonksiyon, uzunluk) + payload


def build_whois(unicast: bool = False) -> bytes:
    apdu = b"\x10\x08"           # Unconfirmed-Req, Who-Is, aralik yok
    npdu = b"\x01\x04"           # version 1, expecting-reply
    fonk = 0x0A if unicast else 0x0B  # Original-Unicast vs Original-Broadcast
    return _bvlc(fonk, npdu + apdu)


def parse_iam(data: bytes):
    """
    I-Am APDU'sundan cihaz instance numarasini cikar.
    Basarili olursa int, olmazsa None.
    """
    try:
        for i in range(4, len(data) - 1):
            if data[i] == 0x10 and data[i + 1] == 0x00:
                k = i + 2
                if k + 5 <= len(data) and data[k] == 0xC4:
                    obj_id = struct.unpack(">I", data[k + 1: k + 5])[0]
                    obj_type     = (obj_id >> 22) & 0x3FF
                    obj_instance = obj_id & 0x3FFFFF
                    if obj_type == 8:          # device
                        return obj_instance
    except Exception:
        pass
    return None


def main():
    # LOCAL_IP uzerinden broadcast adresi: 172.17.91.255
    parts = LOCAL_IP.split(".")
    bc = ".".join(parts[:3]) + ".255"

    print(f"\nYerel IP      : {LOCAL_IP}")
    print(f"Broadcast     : {bc}")
    print(f"BACnet portu  : {BACNET_PORT}")
    print("=" * 55)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        # LOCAL_IP'e bagla: paketler bu arayuz uzerinden gider/gelir
        sock.bind((LOCAL_IP, BACNET_PORT))
        print(f"Port {BACNET_PORT} baglantisi : OK\n")
    except OSError as e:
        print(f"\n[HATA] {LOCAL_IP}:{BACNET_PORT} baglanamadi: {e}")
        print("Desigo veya baska bir servis bu portu kullaniyor!")
        print("Cozum: Desigo servislerini tamamen durdurun.")
        sock.close()
        input("\nCikmak icin Enter...")
        return

    sock.settimeout(0.3)

    # --- Who-Is gonder ---
    pkt_bc = build_whois(unicast=False)
    pkt_uc = build_whois(unicast=True)

    sock.sendto(pkt_bc, (bc, BACNET_PORT))
    print(f"Broadcast Who-Is gonderildi  → {bc}:{BACNET_PORT}")

    for gw in GATEWAYS:
        sock.sendto(pkt_uc, (gw, BACNET_PORT))
        print(f"Unicast  Who-Is gonderildi  → {gw}:{BACNET_PORT}")

    print(f"\nYanitlar bekleniyor ({BEKLEME_SN} sn)...\n")

    yanit_listesi = []
    baslangic = time.time()

    while time.time() - baslangic < BEKLEME_SN:
        try:
            data, addr = sock.recvfrom(1024)
            dev_id = parse_iam(data)
            yanit_listesi.append((addr, data, dev_id))

            if dev_id is not None:
                print(f"  I-Am   {addr[0]:15s}:{addr[1]}  →  device {dev_id}")
            else:
                print(f"  PDU    {addr[0]:15s}:{addr[1]}  hex: {data[:12].hex()}")
        except socket.timeout:
            continue
        except Exception as e:
            print(f"  [hata] {e}")

    sock.close()

    print("\n" + "=" * 55)
    print(f"Toplam paket  : {len(yanit_listesi)}")

    bulunanlar = {r[2]: r[0] for r in yanit_listesi if r[2] is not None}
    print(f"I-Am / cihaz  : {len(bulunanlar)}")

    if bulunanlar:
        print("\nCihazlar:")
        for dev_id, addr in sorted(bulunanlar.items()):
            print(f"  device {dev_id:10d}  kaynak: {addr[0]}:{addr[1]}")
    else:
        print("\nHicbir cihaz I-Am gondermedi.")
        print("Kontrol listesi:")
        print("  1. Desigo servisleri durduruldu mu?  (services.msc -> Desigo)")
        print("  2. Firewall UDP 47808 portuna izin veriyor mu?")
        print("  3. Gateway'ler fiziksel olarak calisiyor mu?")

    input("\nCikmak icin Enter...")


if __name__ == "__main__":
    main()
