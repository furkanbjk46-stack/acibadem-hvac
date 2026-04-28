"""
Device 2098215 @ 192.168.0.2 — AI ve BI nokta testi.
Maslak PC'de (192.168.0.254) çalıştır, Desigo KAPALI olsun.
"""

import socket
import struct
import time

LOCAL_IP   = "192.168.0.254"
LOCAL_PORT = 47808
DEVICE_IP  = "192.168.0.2"
DEVICE_ID  = 2098215
TIMEOUT    = 3.0

AI_LIST = [3, 4, 7, 8, 11, 12, 15, 16, 19, 20, 25, 26, 28, 29]
BI_LIST = [1, 2, 3, 5, 7]


def build_read_property(obj_type, obj_inst, prop_id=85, invoke_id=1):
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    obj_id = (obj_type << 22) | obj_inst
    apdu  = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    pkt   = bvlc + npdu + apdu
    return pkt[:2] + struct.pack(">H", len(pkt)) + pkt[4:]


def parse_value(data):
    """Present Value'yu APDU'dan çıkarır (real, bool, unsigned)."""
    try:
        for i in range(len(data) - 4):
            tag = data[i]
            if tag == 0x44:                          # real (float)
                return round(struct.unpack(">f", data[i+1:i+5])[0], 3)
            if tag == 0x9 and i + 2 <= len(data):   # boolean / enum len=1
                return data[i+1]
            if (tag & 0xF0) == 0x20 and (tag & 0x07) in (1, 2):  # unsigned
                ln = tag & 0x07
                return int.from_bytes(data[i+1:i+1+ln], "big")
    except Exception:
        pass
    return None


def oku(obj_type, obj_inst, label):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, 0))
    sock.settimeout(TIMEOUT)
    try:
        pkt = build_read_property(obj_type, obj_inst)
        sock.sendto(pkt, (DEVICE_IP, LOCAL_PORT))
        data, _ = sock.recvfrom(1024)
        # Hata yanıtı mı?
        if len(data) > 8 and (data[6] & 0xF0) == 0x50:
            return None, f"ERR class={data[8]} code={data[9] if len(data)>9 else '?'}"
        val = parse_value(data)
        return val, "OK"
    except socket.timeout:
        return None, "TIMEOUT"
    except Exception as e:
        return None, f"HATA:{e}"
    finally:
        sock.close()


def main():
    print("=" * 60)
    print(f"Device {DEVICE_ID} @ {DEVICE_IP}")
    print(f"LOCAL_IP={LOCAL_IP}  |  Desigo KAPALI olmalı")
    print("=" * 60)

    basarili = 0
    toplam   = len(AI_LIST) + len(BI_LIST)

    print(f"\n── Analog Inputs ({len(AI_LIST)} nokta) ──")
    for inst in AI_LIST:
        val, durum = oku(0, inst, f"AI:{inst}")
        isaretci = "✓" if val is not None else "✗"
        deger    = str(val) if val is not None else durum
        print(f"  {isaretci} AI:{inst:2d}  {deger}")
        if val is not None:
            basarili += 1

    print(f"\n── Binary Inputs ({len(BI_LIST)} nokta) ──")
    for inst in BI_LIST:
        val, durum = oku(3, inst, f"BI:{inst}")
        isaretci = "✓" if val is not None else "✗"
        deger    = str(val) if val is not None else durum
        print(f"  {isaretci} BI:{inst}   {deger}")
        if val is not None:
            basarili += 1

    print(f"\nSonuç: {basarili}/{toplam} nokta okundu")
    if basarili == toplam:
        print("TAMAM — tüm noktalar okunabildi.")
    elif basarili > 0:
        print("KISMI — bazı noktalar okunamadı, yukarıdaki ✗ satırlarına bak.")
    else:
        print("BAŞARISIZ — hiç veri gelmedi. Desigo kapalı mı? IP doğru mu?")


if __name__ == "__main__":
    main()
