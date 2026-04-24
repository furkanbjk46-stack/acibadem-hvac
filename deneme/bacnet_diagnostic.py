# bacnet_diagnostic.py
# Desigo CC BACnet tani scripti.
# Who-Is olmadan dogrudan IP:port ile baglanip:
#   - Object list okur
#   - Bilinen noktalari dener
#   - Fiziksel AS nesnelerini tarar
# Calistir: python bacnet_diagnostic.py

import asyncio
import socket
import sys

DESIGO_IP   = "192.168.0.254"
DESIGO_PORT = 47808
LOCAL_PORT  = 47809

FIZIKSEL_AS = [
    ("192.168.0.2", 1050625),
    ("192.168.0.3", 1050626),
]

VIRTUAL_DEVICES = [
    (DESIGO_IP, 2099287),
    (DESIGO_IP, 2099291),
    (DESIGO_IP, 2098211),
]

# Maslak AHU-01 icin bilinen noktalar
BILINEN_NOKTALAR = [
    {"aciklama": "AHU-01 SAT (Ufleme)",    "device": 2099287, "type": "analogInput",  "instance": 254},
    {"aciklama": "AHU-01 Room (Donus)",    "device": 2099287, "type": "analogInput",  "instance": 251},
    {"aciklama": "AHU-01 Sogutma Vanasi",  "device": 2099287, "type": "analogOutput", "instance": 150},
    {"aciklama": "AHU-01 Isitma Vanasi",   "device": 2099287, "type": "analogOutput", "instance": 148},
    {"aciklama": "Plant Supply (Sogutma)", "device": 2099291, "type": "analogInput",  "instance": 22},
    {"aciklama": "Plant Return (Sogutma)", "device": 2099291, "type": "analogInput",  "instance": 23},
    {"aciklama": "OAT (Dis Hava)",         "device": 2098211, "type": "analogInput",  "instance": 33},
]


def _detect_local_ip(target_ip: str) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target_ip, 1))
            return s.getsockname()[0]
    except Exception:
        return ""


def sep(char="=", n=60):
    print(char * n)


async def run_diagnostic():
    try:
        import BAC0
    except ImportError:
        print("[HATA] BAC0 yuklu degil! Komut: pip install BAC0")
        sys.exit(1)

    local_ip = _detect_local_ip(DESIGO_IP)
    print(f"\n Yerel IP : {local_ip}")
    print(f" Desigo   : {DESIGO_IP}:{DESIGO_PORT}")
    print(f" BAC0 port: {LOCAL_PORT}\n")

    sep()
    print("  BAC0 baslatiliyor...")
    sep()
    try:
        if local_ip:
            bacnet = BAC0.lite(ip=f"{local_ip}/24", port=LOCAL_PORT)
        else:
            bacnet = BAC0.lite(port=LOCAL_PORT)
        await asyncio.sleep(3)
        print("[OK] BAC0 basladi.\n")
    except Exception as e:
        print(f"[HATA] BAC0 baslatılamadi: {e}")
        return

    # ── 1. Sanal Desigo Cihazlari — Object List ───────────
    sep()
    print("  1. SANAL DESIGO CIHAZLARI — OBJECT LIST")
    sep()
    for ip, dev_id in VIRTUAL_DEVICES:
        addr = f"{ip}:{DESIGO_PORT}"
        print(f"\n>>> Device {dev_id} @ {addr}")
        try:
            obj_list = bacnet.read(f"{addr} device {dev_id} objectList")
            if obj_list:
                print(f"    {len(obj_list)} nesne bulundu:")
                for obj in obj_list[:30]:
                    print(f"      {obj}")
                if len(obj_list) > 30:
                    print(f"      ... ve {len(obj_list)-30} nesne daha")
            else:
                print("    Object list bos veya None dondu.")
        except Exception as e:
            print(f"    [HATA] {e}")

    # ── 2. Fiziksel AS Cihazlari — Object List ────────────
    sep()
    print("\n  2. FIZIKSEL AS CIHAZLARI — OBJECT LIST")
    sep()
    for ip, dev_id in FIZIKSEL_AS:
        print(f"\n>>> Device {dev_id} @ {ip}")
        try:
            obj_list = bacnet.read(f"{ip} device {dev_id} objectList")
            if obj_list:
                print(f"    {len(obj_list)} nesne bulundu:")
                # AHU ile ilgili olabilecekleri filtrele
                ilgili = [o for o in obj_list if any(
                    t in str(o).lower() for t in ["analog", "binary", "multi"]
                )]
                for obj in ilgili[:40]:
                    print(f"      {obj}")
                if len(ilgili) > 40:
                    print(f"      ... ve {len(ilgili)-40} nesne daha")
            else:
                print("    Object list bos veya None dondu.")
        except Exception as e:
            print(f"    [HATA] {e}")

    # ── 3. Bilinen Noktalari Dogrudan Oku ────────────────
    sep()
    print("\n  3. BILINEN NOKTALARI DOGRUDAN OKU (Who-Is olmadan)")
    sep()
    for nokta in BILINEN_NOKTALAR:
        dev_id   = nokta["device"]
        obj_type = nokta["type"]
        instance = nokta["instance"]
        aciklama = nokta["aciklama"]

        # Hangi IP bu device'a ait?
        ip = next(
            (ip for ip, d in VIRTUAL_DEVICES + FIZIKSEL_AS if d == dev_id),
            DESIGO_IP
        )
        port = DESIGO_PORT if ip == DESIGO_IP else 47808
        addr = f"{ip}:{port}" if port != 47808 or ip == DESIGO_IP else ip

        # Format 1: IP:port type instance presentValue
        adres1 = f"{addr} {obj_type} {instance} presentValue"
        # Format 2: IP:port type:instance presentValue
        adres2 = f"{addr} {obj_type}:{instance} presentValue"

        print(f"\n>>> {aciklama}")
        print(f"    Device {dev_id} | {obj_type} #{instance}")

        deger = None
        for fmt, adres in [("Format1", adres1), ("Format2", adres2)]:
            try:
                deger = float(bacnet.read(adres))
                print(f"    [{fmt}] BASARILI: {deger}")
                break
            except Exception as e:
                print(f"    [{fmt}] Hata: {e}")

        if deger is None:
            print(f"    !! Okunamadi")

    # ── 4. Who-Is Tarama ─────────────────────────────────
    sep()
    print("\n  4. WHO-IS TARAMA (broadcast + unicast)")
    sep()
    print("Broadcast Who-Is...")
    try:
        bacnet.whois()
        await asyncio.sleep(5)
    except Exception as e:
        print(f"Broadcast hata: {e}")

    print(f"\nUnicast Who-Is (192.168.0.1-10, .100, .254)...")
    hedef_ips = [f"192.168.0.{i}" for i in list(range(1, 11)) + [100, 254]]
    for ip in hedef_ips:
        try:
            bacnet.whois(address=f"{ip}:{DESIGO_PORT}")
        except Exception:
            pass
    await asyncio.sleep(5)

    discovered = getattr(bacnet, "discoveredDevices", {}) or {}
    if discovered:
        print(f"\n Kesfedilen cihazlar ({len(discovered)} adet):")
        for dev_id, info in discovered.items():
            print(f"   Device {dev_id} → {info}")
    else:
        print("\n Hic cihaz kesfedilemedi.")

    # ── Sonuc ─────────────────────────────────────────────
    sep()
    print("\n  TANI TAMAMLANDI")
    sep()
    try:
        bacnet.disconnect()
    except Exception:
        pass
    print("\nYukaridaki sonuclari paylasin — hangi nesnelerin okunabildigini gorecegiz.\n")


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
