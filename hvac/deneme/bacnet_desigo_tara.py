"""
Desigo CC'nin BACnet object space'ini tarar.
AI:1-500 ve AO:1-200 aralıklarını dener.
Sonuç: Desigo CC'nin object space'i boş (0 obje bulundu).
LOCAL_IP = 192.168.0.254
"""

import socket
import struct
import time

LOCAL_IP = "192.168.0.254"
LOCAL_PORT = 47808
DESIGO_IP = "192.168.0.1"    # Desigo CC server IP (ağa göre güncelle)
DESIGO_PORT = 47808


def build_read_property(obj_type, obj_inst, prop_id=85, invoke_id=1):
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    obj_id = (obj_type << 22) | obj_inst
    apdu = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def tara(obj_type_id, obj_type_name, baslangic, bitis, timeout=1.5):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, 0))
    sock.settimeout(timeout)

    bulunanlar = []
    print(f"Taranıyor: {obj_type_name}:{baslangic}-{bitis}")

    for inst in range(baslangic, bitis + 1):
        pkt = build_read_property(obj_type_id, inst)
        sock.sendto(pkt, (DESIGO_IP, DESIGO_PORT))
        try:
            data, _ = sock.recvfrom(1024)
            # Hata yanıtı değilse kaydet
            if len(data) > 4 and data[4] != 0x50:  # 0x50 = Error PDU
                bulunanlar.append(inst)
                print(f"  BULUNDU: {obj_type_name}:{inst} — {data[:10].hex()}")
        except socket.timeout:
            pass

        if inst % 50 == 0:
            print(f"  ... {inst}/{bitis} tarandı", flush=True)

    sock.close()
    return bulunanlar


if __name__ == "__main__":
    print(f"Desigo CC object space taraması")
    print(f"Hedef: {DESIGO_IP}  |  LOCAL_IP: {LOCAL_IP}\n")

    sonuclar = {}

    # AI (obj_type=0): 1-500
    ai_list = tara(0, "AI", 1, 500)
    sonuclar["AI"] = ai_list
    print(f"AI toplamı: {len(ai_list)} obje\n")

    # AO (obj_type=1): 1-200
    ao_list = tara(1, "AO", 1, 200)
    sonuclar["AO"] = ao_list
    print(f"AO toplamı: {len(ao_list)} obje\n")

    # AV (obj_type=2): 1-100
    av_list = tara(2, "AV", 1, 100)
    sonuclar["AV"] = av_list
    print(f"AV toplamı: {len(av_list)} obje\n")

    toplam = sum(len(v) for v in sonuclar.values())
    print(f"GENEL TOPLAM: {toplam} obje")
    if toplam == 0:
        print("=> Desigo CC BACnet object space'i boş (beklenen sonuç)")
