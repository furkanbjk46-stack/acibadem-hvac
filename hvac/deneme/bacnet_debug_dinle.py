"""
Ham BACnet paket dinleyici + BBMD kaydı.
Tüm gelen UDP paketlerini dump eder.
LOCAL_IP = 192.168.0.254
"""

import socket
import struct
import time
import threading

LOCAL_IP = "192.168.0.254"
LOCAL_PORT = 47808
BROADCAST = "192.168.0.255"

BVLC_FUNCTIONS = {
    0x00: "BVLC-Result",
    0x01: "Write-BDT",
    0x02: "Read-BDT",
    0x03: "Read-BDT-Ack",
    0x04: "Forwarded-NPDU",
    0x05: "Register-Foreign-Device",
    0x06: "Read-FDT",
    0x07: "Read-FDT-Ack",
    0x08: "Delete-Foreign-Device",
    0x09: "Distribute-Broadcast",
    0x0a: "Original-Unicast-NPDU",
    0x0b: "Original-Broadcast-NPDU",
}


def build_register_foreign_device(bbmd_ip, ttl=60):
    """BBMD'ye Foreign Device kaydı gönderir."""
    pkt = bytes([0x81, 0x05, 0x00, 0x06]) + struct.pack(">H", ttl)
    return pkt


def build_who_is():
    bvlc = bytes([0x81, 0x0b, 0x00, 0x00])
    npdu = bytes([0x01, 0x00])
    apdu = bytes([0x10, 0x08])
    packet = bvlc + npdu + apdu
    packet = packet[:2] + struct.pack(">H", len(packet)) + packet[4:]
    return packet


def decode_packet(data, addr):
    lines = [f"\n{'='*50}", f"  Kaynak: {addr[0]}:{addr[1]}  |  {len(data)} byte"]
    if len(data) < 4:
        lines.append(f"  Ham: {data.hex()}")
        return "\n".join(lines)

    if data[0] == 0x81:
        func = BVLC_FUNCTIONS.get(data[1], f"0x{data[1]:02x}")
        length = struct.unpack(">H", data[2:4])[0]
        lines.append(f"  BVLC: type=BACnet/IP func={func} len={length}")
        payload = data[4:]
    else:
        payload = data

    if len(payload) >= 2:
        version = payload[0]
        ctrl = payload[1]
        lines.append(f"  NPDU: version={version} ctrl=0x{ctrl:02x}")
        apdu = payload[2:]
        if ctrl & 0x20:  # DNET mevcut
            if len(apdu) >= 3:
                dnet = struct.unpack(">H", apdu[:2])[0]
                dlen = apdu[2]
                lines.append(f"  Routing: DNET={dnet} DLEN={dlen}")
                apdu = apdu[3 + dlen + 1:]

        if len(apdu) >= 2:
            pdu_type = (apdu[0] & 0xF0) >> 4
            pdu_names = {0: "ConfReq", 1: "ConfACK", 2: "ComplexACK",
                         3: "SegACK", 4: "Error", 5: "Reject",
                         6: "Abort", 1: "UnconfReq"}
            lines.append(f"  APDU: type={pdu_names.get(pdu_type, pdu_type)} raw={apdu[:8].hex()}")

    return "\n".join(lines)


def gonder_who_is(sock):
    time.sleep(1)
    pkt = build_who_is()
    sock.sendto(pkt, (BROADCAST, LOCAL_PORT))
    print(f"\n[{time.strftime('%H:%M:%S')}] Who-Is broadcast gönderildi")


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((LOCAL_IP, LOCAL_PORT))
    sock.settimeout(1.0)

    print(f"BACnet dinleyici başlatıldı: {LOCAL_IP}:{LOCAL_PORT}")
    print("Ctrl+C ile durdur\n")

    t = threading.Thread(target=gonder_who_is, args=(sock,), daemon=True)
    t.start()

    paket_sayisi = 0
    baslangic = time.time()

    try:
        while True:
            try:
                data, addr = sock.recvfrom(2048)
                paket_sayisi += 1
                print(f"[{time.strftime('%H:%M:%S')}] Paket #{paket_sayisi}")
                print(decode_packet(data, addr))
            except socket.timeout:
                gecen = int(time.time() - baslangic)
                print(f"\r  {gecen}s dinleniyor... ({paket_sayisi} paket)", end="", flush=True)
    except KeyboardInterrupt:
        print(f"\n\nDurduruldu. Toplam {paket_sayisi} paket alındı.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
