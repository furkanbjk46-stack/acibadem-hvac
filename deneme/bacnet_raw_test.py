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
    BVLC + NPDU routing header'larini dogru sekilde atlayarak
    I-Am APDU'sundan cihaz instance numarasini ve kaynak MS/TP
    network/adresini cikar. (device_id, snet, sadr) dondurur.
    Basarisiz olursa (None, None, None).
    """
    try:
        if len(data) < 8 or data[0] != 0x81:
            return None, None, None

        bvlc_func = data[1]
        i = 4

        # Forwarded-NPDU: 6 ekstra byte (asil kaynak IP + port)
        if bvlc_func == 0x04:
            i += 6

        if i + 2 > len(data):
            return None, None, None

        npdu_ctrl = data[i + 1]
        i += 2

        # Network layer mesaji — APDU icermez
        if npdu_ctrl & 0x80:
            return None, None, None

        snet = sadr = None

        # Hedef adresi varsa atla (bit 5)
        if npdu_ctrl & 0x20:
            if i + 3 > len(data):
                return None, None, None
            i += 2                    # DNET
            dlen = data[i]; i += 1 + dlen  # DLEN + DADR

        # Kaynak adresi varsa oku (bit 3) — MS/TP cihaz bilgisi burada
        if npdu_ctrl & 0x08:
            if i + 3 > len(data):
                return None, None, None
            snet = (data[i] << 8) | data[i + 1]; i += 2
            slen = data[i]; i += 1
            sadr = data[i: i + slen].hex(); i += slen

        # Hedef varsa hop count'u atla (bit 5)
        if npdu_ctrl & 0x20:
            i += 1

        if i + 2 > len(data):
            return None, None, None

        # APDU: PDU type=1 (Unconfirmed-Req), service=0 (I-Am)
        if (data[i] >> 4) != 1 or data[i + 1] != 0:
            return None, None, None
        i += 2

        # Object-identifier: application tag 0xC4, 4 byte deger
        if i + 5 > len(data) or data[i] != 0xC4:
            return None, None, None

        obj_id   = struct.unpack(">I", data[i + 1: i + 5])[0]
        obj_type = (obj_id >> 22) & 0x3FF
        obj_inst = obj_id & 0x3FFFFF

        if obj_type == 8:
            return obj_inst, snet, sadr

    except Exception:
        pass
    return None, None, None


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
            dev_id, snet, sadr = parse_iam(data)
            yanit_listesi.append((addr, data, dev_id, snet, sadr))

            if dev_id is not None:
                routing = f"  MS/TP net={snet} mac={sadr}" if snet else ""
                print(f"  I-Am   {addr[0]:15s}  →  device {dev_id}{routing}")
            else:
                print(f"  PDU    {addr[0]:15s}  hex: {data[:16].hex()}")
        except socket.timeout:
            continue
        except Exception as e:
            print(f"  [hata] {e}")

    sock.close()

    print("\n" + "=" * 55)
    print(f"Toplam paket  : {len(yanit_listesi)}")

    # En son I-Am'i kullan (tekrar edenler icin)
    bulunanlar: dict[int, tuple] = {}
    for addr, _, dev_id, snet, sadr in yanit_listesi:
        if dev_id is not None:
            bulunanlar[dev_id] = (addr[0], snet, sadr)

    print(f"I-Am / cihaz  : {len(bulunanlar)}")

    if bulunanlar:
        print("\nCihazlar:")
        for dev_id, (ip, snet, sadr) in sorted(bulunanlar.items()):
            routing = f"  (MS/TP net={snet} mac={sadr})" if snet else ""
            print(f"  device {dev_id:10d}  kaynak: {ip}{routing}")
    else:
        print("\nHicbir cihaz I-Am gondermedi.")
        print("Kontrol listesi:")
        print("  1. Desigo servisleri durduruldu mu?  (services.msc -> Desigo)")
        print("  2. Firewall UDP 47808 portuna izin veriyor mu?")
        print("  3. Gateway'ler fiziksel olarak calisiyor mu?")

    input("\nCikmak icin Enter...")


if __name__ == "__main__":
    main()
