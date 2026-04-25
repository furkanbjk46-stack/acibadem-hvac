# bacnet_seslen.py
# YABE'de gorulen tum BACnet cihazlarina Who-Is gonderir,
# cevap verenleri ve bir test noktasini ekrana yazar.
# Calistir: python bacnet_seslen.py
# Gereksinim: pip install BAC0

import asyncio
import socket
import sys

# Gateway'ler ve altlarindaki cihaz instance'lari (YABE'den)
GATEWAY_CIHAZLAR = {
    "192.168.0.2": [2098211, 2098213, 2098214, 2099204, 2099205,
                    2099211, 2099214, 2099233, 2099234],
    "192.168.0.3": [2098186, 2098188, 2098189, 2098201, 2098202,
                    2098203, 2098204, 2098207, 2099209, 2099219,
                    2099223, 2099229, 2099282],
    "192.168.0.4": [2098217, 2098218, 2098229, 2098234, 2098235,
                    2098240, 2098244, 2098246, 2098247, 2098252,
                    2098243, 2099262, 2099280, 2099291],
    "192.168.0.5": [2098221, 2098222, 2098223, 2098224],
}

BACNET_PORT = 47808
LOCAL_PORT  = 47809


def _local_ip(target: str) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target, 1))
            return s.getsockname()[0]
    except Exception:
        return ""


async def seslen():
    try:
        import BAC0
    except ImportError:
        print("BAC0 yuklu degil! Komut: pip install BAC0")
        sys.exit(1)

    lip = _local_ip("192.168.0.2")
    print(f"\nYerel IP   : {lip}")
    print(f"BAC0 port  : {LOCAL_PORT}")
    print(f"Hedef port : {BACNET_PORT}\n")
    print("=" * 55)

    # BAC0 baslat
    print("BAC0 baslatiliyor...")
    try:
        bacnet = BAC0.lite(ip=f"{lip}/24", port=LOCAL_PORT) if lip \
                 else BAC0.lite(port=LOCAL_PORT)
        await asyncio.sleep(3)
        print("BAC0 hazir.\n")
    except Exception as e:
        print(f"BAC0 baslatılamadi: {e}")
        return

    # Her gateway icin Who-Is gonder
    tum_cihazlar = []
    for gw_ip, cihazlar in GATEWAY_CIHAZLAR.items():
        tum_cihazlar.extend(cihazlar)

    min_id = min(tum_cihazlar)
    max_id = max(tum_cihazlar)

    print(f"Who-Is gonderiliyor (range {min_id}–{max_id})...")
    for gw_ip in GATEWAY_CIHAZLAR:
        try:
            await bacnet.who_is(
                low_limit=min_id, high_limit=max_id,
                address=f"{gw_ip}:{BACNET_PORT}"
            )
            print(f"  → {gw_ip} ✓")
        except Exception as e:
            print(f"  → {gw_ip} HATA: {e}")

    print("\nCevaplar bekleniyor (10 sn)...")
    await asyncio.sleep(10)

    raw = getattr(bacnet, "discoveredDevices", None) or {}
    print(f"\nKesfeilen cihaz sayisi: {len(raw)}")
    print("=" * 55)

    # Her cihazi raporla
    bulunanlar = []
    bulunamayanlar = []

    for gw_ip, cihazlar in GATEWAY_CIHAZLAR.items():
        print(f"\nGateway {gw_ip}:")
        for dev_id in cihazlar:
            if dev_id in raw:
                info = raw[dev_id]
                addr = info.get("address", str(info)) if isinstance(info, dict) else str(info)
                print(f"  [OK] {dev_id:10d}  →  {addr}")
                bulunanlar.append((dev_id, gw_ip, addr))
            else:
                print(f"  [--] {dev_id:10d}  —  cevap yok")
                bulunamayanlar.append((dev_id, gw_ip))

    print("\n" + "=" * 55)
    print(f"Toplam: {len(bulunanlar)} bulundu / {len(bulunamayanlar)} bulunamadi")

    if not bulunanlar:
        print("\nHicbir cihaz cevap vermedi.")
        print("Desigo sunucusu kapali mi? Port 47808 musait mi kontrol edin.")
        try:
            bacnet.disconnect()
        except Exception:
            pass
        return

    # Bulunan ilk cihazdan test okuma
    print("\n--- Bulunan ilk cihazdan test okuma ---")
    dev_id, gw_ip, addr = bulunanlar[0]
    print(f"Cihaz: {dev_id}  Adres: {addr}")

    test_noktalar = [
        ("analogInput", 1),
        ("analogInput", 2),
        ("analogInput", 3),
        ("analogOutput", 1),
        ("binaryInput", 1),
    ]

    for obj_type, instance in test_noktalar:
        adres = f"{addr} {obj_type}:{instance} presentValue"
        try:
            val = await bacnet.read(adres)
            print(f"  {obj_type}:{instance:3d}  =  {val}")
        except Exception as e:
            print(f"  {obj_type}:{instance:3d}  —  {e}")

    try:
        bacnet.disconnect()
    except Exception:
        pass

    print("\nTest tamamlandi.")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(seslen())
    except KeyboardInterrupt:
        print("\nDurduruluyor...")
    finally:
        loop.close()
        input("\nCikmak icin Enter...")
