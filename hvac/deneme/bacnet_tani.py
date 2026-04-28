"""
BACnet bağlantı tanılama — Maslak PC'de yönetici olarak çalıştır.
Port durumu, firewall ve paket alımını kontrol eder.
"""

import socket
import struct
import subprocess
import time
import os

LOCAL_IP   = "192.168.0.254"
LOCAL_PORT = 47808
BROADCAST  = "192.168.0.255"


def kontrol_port():
    print("=== PORT 47808 DURUMU ===")
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, encoding="cp850", errors="replace"
        )
        satirlar = [s for s in result.stdout.splitlines() if "47808" in s]
        if satirlar:
            print("47808 portu KULLANILIYOR:")
            for s in satirlar:
                print(f"  {s.strip()}")
        else:
            print("47808 portu şu an serbest.")
    except Exception as e:
        print(f"netstat hatası: {e}")
    print()


def kontrol_bind():
    print("=== SOCKET BIND TESTİ ===")
    # Önce LOCAL_IP:47808
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((LOCAL_IP, LOCAL_PORT))
        print(f"OK: {LOCAL_IP}:{LOCAL_PORT} bind başarılı")
        s.close()
    except OSError as e:
        print(f"HATA: {LOCAL_IP}:{LOCAL_PORT} bind BAŞARISIZ -> {e}")

    # Broadcast bind (0.0.0.0)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(("0.0.0.0", LOCAL_PORT))
        print(f"OK: 0.0.0.0:{LOCAL_PORT} bind başarılı")
        s.close()
    except OSError as e:
        print(f"HATA: 0.0.0.0:{LOCAL_PORT} bind BAŞARISIZ -> {e}")
    print()


def who_is_ve_dinle():
    print("=== WHO-IS BROADCAST + 10s DİNLEME ===")
    print(f"Gönderici: {LOCAL_IP}  |  Hedef: {BROADCAST}:{LOCAL_PORT}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", LOCAL_PORT))
    sock.settimeout(1.0)

    # Who-Is paketi
    bvlc = bytes([0x81, 0x0b, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    apdu = bytes([0x10, 0x08])
    pkt  = bvlc + npdu + apdu
    pkt  = pkt[:2] + struct.pack(">H", len(pkt)) + pkt[4:]

    sock.sendto(pkt, (BROADCAST, LOCAL_PORT))
    print("Who-Is gönderildi, yanıt bekleniyor (10s)...\n")

    sayac = 0
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(1024)
            sayac += 1
            print(f"  [{sayac}] {addr[0]}:{addr[1]}  {len(data)} byte  {data[:8].hex()}")
            # I-Am kontrolü
            if len(data) > 6 and data[6] == 0x10 and data[7] == 0x00:
                # Device instance çıkar
                if len(data) > 12 and data[8] == 0xC4:
                    raw = struct.unpack(">I", data[9:13])[0]
                    dev_inst = raw & 0x3FFFFF
                    print(f"       -> I-Am: Device:{dev_inst}")
        except socket.timeout:
            kalan = int(deadline - time.time())
            print(f"\r  Bekleniyor... {kalan}s kaldı  ", end="", flush=True)

    print(f"\n\nSonuç: {sayac} paket alındı")
    sock.close()
    return sayac


def unicast_readproperty():
    """Bilinen gateway IP'lerine direkt ReadProperty gönderir."""
    print("\n=== UNİCAST READPROPERTY TESTİ ===")
    hedefler = [
        ("192.168.0.1", "Gateway/Desigo"),
        ("192.168.0.2", "Gateway-OAT"),
        ("192.168.0.4", "Gateway-Chiller"),
        ("192.168.0.8", "Gateway-AHU"),
    ]

    for ip, label in hedefler:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", 0))
        sock.settimeout(3.0)

        # ReadProperty Device:2099296 AI:1
        obj_id = (0 << 22) | 1  # AI:1
        bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
        npdu = bytes([0x01, 0x00])
        apdu = bytes([0x00, 0x04, 0x01, 0x0c])
        apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
        apdu += bytes([0x19, 85])
        pkt = bvlc + npdu + apdu
        pkt = pkt[:2] + struct.pack(">H", len(pkt)) + pkt[4:]

        try:
            sock.sendto(pkt, (ip, LOCAL_PORT))
            data, addr = sock.recvfrom(1024)
            print(f"  {label:20s} ({ip}): YANIT GELDI {len(data)}b {data[:8].hex()}")
        except socket.timeout:
            print(f"  {label:20s} ({ip}): timeout")
        except Exception as e:
            print(f"  {label:20s} ({ip}): HATA {e}")
        finally:
            sock.close()


def firewall_kural_ekle():
    """Yönetici ayrıcalığıyla Windows Firewall kuralı ekler."""
    print("\n=== FIREWALL KURALI EKLEME ===")
    cmd = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        "name=BACnet-Python-UDP47808",
        "dir=in",
        "action=allow",
        "protocol=UDP",
        "localport=47808"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="cp850", errors="replace")
        if result.returncode == 0:
            print("Firewall kuralı EKLENDİ — gelen UDP 47808 artık açık.")
        else:
            print(f"Firewall kural eklenemedi (yönetici olarak çalıştır!):")
            print(f"  {result.stdout.strip()} {result.stderr.strip()}")
    except Exception as e:
        print(f"Hata: {e}")


if __name__ == "__main__":
    kontrol_port()
    kontrol_bind()

    # Firewall kuralını ekle
    firewall_kural_ekle()

    # Who-Is + dinle
    paket_sayisi = who_is_ve_dinle()

    # Unicast test
    unicast_readproperty()

    print("\n" + "=" * 55)
    if paket_sayisi == 0:
        print("TANI: Hiç paket alınamadı.")
        print("Olası nedenler:")
        print("  1. Bu scripti yönetici (Admin) olarak çalıştır")
        print("  2. YABE açıksa kapat, tekrar dene")
        print("  3. 192.168.0.x ağında başka cihaz var mı kontrol et:")
        print("     CMD: ping 192.168.0.1")
        print("     CMD: arp -a")
    else:
        print(f"BAŞARILI: {paket_sayisi} paket alındı.")
