"""
Device 2098215 @ 192.168.0.2 — object-list okuma + AI/BI test.
Önce cihazın gerçek obje listesini çeker, sonra her birini okur.
Maslak PC'de çalıştır (LOCAL_IP=192.168.0.254).
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

OBJ_TYPE_NAMES = {
    0: "AI", 1: "AO", 2: "AV", 3: "BI", 4: "BO", 5: "BV",
    8: "Device", 10: "File", 13: "MI", 14: "MO", 19: "MV",
}

ERROR_CLASS = {0: "device", 1: "object", 2: "property", 3: "resources",
               4: "security", 5: "services", 6: "vt"}
ERROR_CODE  = {31: "unknown-object", 32: "unknown-property",
               44: "unknown-object-type", 25: "optional-functionality-not-supported"}


def _pack(pkt):
    return pkt[:2] + struct.pack(">H", len(pkt)) + pkt[4:]


def build_read_property(obj_type, obj_inst, prop_id=85, invoke_id=1):
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    obj_id = (obj_type << 22) | obj_inst
    apdu  = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0c])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, prop_id])
    return _pack(bvlc + npdu + apdu)


def parse_error(data):
    """BACnet Error PDU'yu düzgün parse eder."""
    # BVLC(4) + NPDU(2) + Error PDU:
    # [6]=0x50  [7]=invoke-id  [8]=service-choice
    # [9]=0x91(tag)  [10]=class_val
    # [11]=0x91(tag) [12]=code_val
    try:
        if len(data) > 10:
            cls_val  = data[10]
            code_val = data[12] if len(data) > 12 else 0
            cls_str  = ERROR_CLASS.get(cls_val, str(cls_val))
            code_str = ERROR_CODE.get(code_val, str(code_val))
            return f"ERR {cls_str}/{code_str}"
    except Exception:
        pass
    return f"ERR raw={data[6:14].hex()}"


def parse_value(data):
    """Present Value'yu APDU'dan çıkarır."""
    try:
        for i in range(len(data) - 4):
            tag = data[i]
            if tag == 0x44:                            # real float
                return round(struct.unpack(">f", data[i+1:i+5])[0], 3)
            if tag == 0x91 and i + 2 <= len(data):    # enumerated (BI active/inactive)
                return data[i+1]
            if tag == 0x21 and i + 2 <= len(data):    # unsigned int 1 byte
                return data[i+1]
            if tag == 0x22 and i + 3 <= len(data):    # unsigned int 2 byte
                return struct.unpack(">H", data[i+1:i+3])[0]
    except Exception:
        pass
    return None


def oku(obj_type, obj_inst, prop_id=85):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LOCAL_IP, 0))
    sock.settimeout(TIMEOUT)
    try:
        pkt = build_read_property(obj_type, obj_inst, prop_id)
        sock.sendto(pkt, (DEVICE_IP, LOCAL_PORT))
        data, _ = sock.recvfrom(4096)
        # Hata PDU kontrolü: data[6] = 0x50
        if len(data) > 6 and data[6] == 0x50:
            return None, parse_error(data)
        val = parse_value(data)
        return val, "OK"
    except socket.timeout:
        return None, "TIMEOUT"
    except Exception as e:
        return None, f"HATA:{e}"
    finally:
        sock.close()


def oku_object_list():
    """Device obje listesini okur (property 76)."""
    print(f"\n── Object-List (Device:{DEVICE_ID}) ──")
    val, durum = oku(8, DEVICE_ID, 76)   # Device obj, prop 76 = object-list
    if val is None:
        print(f"  object-list okunamadı: {durum}")
        return []

    # Parse: her 4 byte bir obje tanımlayıcı
    objects = []
    raw = val if isinstance(val, bytes) else b""
    for i in range(0, len(raw) - 3, 4):
        word = struct.unpack(">I", raw[i:i+4])[0]
        t = (word >> 22) & 0x3FF
        n = word & 0x3FFFFF
        name = OBJ_TYPE_NAMES.get(t, f"type{t}")
        objects.append((t, n, name))
        print(f"  {name}:{n}")
    return objects


def test_noktalar():
    basarili = 0
    toplam   = len(AI_LIST) + len(BI_LIST)

    print(f"\n── Analog Inputs ({len(AI_LIST)} nokta) ──")
    for inst in AI_LIST:
        val, durum = oku(0, inst)
        ok = val is not None
        isaretci = "✓" if ok else "✗"
        deger = str(val) if ok else durum
        print(f"  {isaretci} AI:{inst:2d}  {deger}")
        if ok:
            basarili += 1

    print(f"\n── Binary Inputs ({len(BI_LIST)} nokta) ──")
    for inst in BI_LIST:
        val, durum = oku(3, inst)
        ok = val is not None
        isaretci = "✓" if ok else "✗"
        deger = str(val) if ok else durum
        bi_str = "active" if val == 1 else ("inactive" if val == 0 else deger)
        print(f"  {isaretci} BI:{inst}   {bi_str}")
        if ok:
            basarili += 1

    print(f"\nSonuç: {basarili}/{toplam} nokta okundu")
    return basarili


def tarama_1_50():
    """AI 1-50 arası hangileri yanıt veriyor tarar."""
    print(f"\n── AI 1-50 Tarama (yanıt verenleri bul) ──")
    bulunanlar = []
    for i in range(1, 51):
        val, durum = oku(0, i)
        if val is not None:
            print(f"  ✓ AI:{i:2d} = {val}")
            bulunanlar.append(i)
        elif "unknown-object" not in durum and "TIMEOUT" not in durum:
            print(f"  ? AI:{i:2d} = {durum}")
    print(f"  Bulunan AI'lar: {bulunanlar}")
    return bulunanlar


if __name__ == "__main__":
    print("=" * 60)
    print(f"Device {DEVICE_ID} @ {DEVICE_IP}")
    print(f"LOCAL_IP={LOCAL_IP}")
    print("=" * 60)

    # 1. Bilinen noktaları test et
    basarili = test_noktalar()

    # 2. Hiç gelmezse veya kısmi gelirse tarama yap
    if basarili == 0:
        print("\nHiç veri gelmedi — AI 1-50 taranıyor...")
        tarama_1_50()
    elif basarili < len(AI_LIST) + len(BI_LIST):
        print("\nBazı noktalar boş — AI 1-50 taranıyor...")
        tarama_1_50()
