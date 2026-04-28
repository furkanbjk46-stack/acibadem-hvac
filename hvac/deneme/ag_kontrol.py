"""
Makinedeki ağ adaptörlerini listeler.
KRİTİK KEŞİF: Siemens adaptöründe 192.168.0.254 IP'si var
→ Bu IP gateway'lerle (192.168.0.2/4/8) aynı subnet'te
→ LOCAL_IP olarak 192.168.0.254 kullanılmalı
"""

import socket
import struct
import subprocess
import platform
import re


def get_adapters_windows():
    """Windows'ta ipconfig ile adaptörleri listeler."""
    try:
        result = subprocess.run(
            ["ipconfig", "/all"],
            capture_output=True, text=True, encoding="cp850", errors="replace"
        )
        return result.stdout
    except Exception as e:
        return f"ipconfig hatası: {e}"


def get_adapters_linux():
    """Linux'ta ip addr ile adaptörleri listeler."""
    try:
        result = subprocess.run(
            ["ip", "addr"],
            capture_output=True, text=True
        )
        return result.stdout
    except Exception as e:
        return f"ip addr hatası: {e}"


def parse_ips(text):
    """Metinden IPv4 adreslerini çıkarır."""
    pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b'
    ips = re.findall(pattern, text)
    return list(set(ips))


def kontrol_subnet(ip, hedef_subnet="192.168.0"):
    return ip.startswith(hedef_subnet)


def main():
    print("=" * 60)
    print("AĞ ADAPTÖR KONTROLÜ")
    print("=" * 60)

    os_type = platform.system()
    print(f"İşletim Sistemi: {os_type}\n")

    if os_type == "Windows":
        output = get_adapters_windows()
    else:
        output = get_adapters_linux()

    print(output)
    print("=" * 60)

    # IP'leri çıkar ve analiz et
    tum_ipler = parse_ips(output)
    print(f"\nBulunan tüm IP'ler: {tum_ipler}\n")

    gateway_subnet_ipler = [ip for ip in tum_ipler if kontrol_subnet(ip)]
    print(f"192.168.0.x subnet'indeki IP'ler: {gateway_subnet_ipler}")

    if gateway_subnet_ipler:
        print("\nKRİTİK: Bu makinede 192.168.0.x adresi var!")
        print("Gateway'lerle (192.168.0.2/4/8) aynı subnet'teyiz.")
        for ip in gateway_subnet_ipler:
            print(f"  -> LOCAL_IP = '{ip}' kullanılmalı")
    else:
        print("\nUYARI: 192.168.0.x adresi bulunamadı!")
        print("Mevcut IP'ler gateway subnet'iyle eşleşmiyor.")
        print("BACnet yanıtları kaybolabilir (routing yok).")

    # Hostname
    try:
        hostname = socket.gethostname()
        local_ips = socket.getaddrinfo(hostname, None)
        ipv4 = [x[4][0] for x in local_ips if x[0] == socket.AF_INET]
        print(f"\nHostname: {hostname}")
        print(f"IPv4 adresleri: {list(set(ipv4))}")
    except Exception as e:
        print(f"Hostname hatası: {e}")


if __name__ == "__main__":
    main()
