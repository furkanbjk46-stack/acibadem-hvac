# bacnet_writer.py
# BACnet WriteProperty (ham UDP socket) + Supabase komutlar tablosu polling
# cloud_sync.py'nin arka plan heartbeat döngüsünden çağrılır.
# Dış kütüphane gerektirmez — data_collector.py ile aynı yaklaşım.

import socket
import struct
import random
import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime

logger = logging.getLogger(__name__)

BACNET_PORT    = 47808
WRITE_TIMEOUT  = 5.0
PROP_PRESENT_VALUE = 85  # BACnet property ID


# ================================================================
# YARDIMCI FONKSİYONLAR
# ================================================================

def _pack_length(packet: bytes) -> bytes:
    """BVLC uzunluk alanını güncelle."""
    return packet[:2] + struct.pack(">H", len(packet)) + packet[4:]


def _build_write_property(obj_type: int, obj_inst: int, value: float,
                           invoke_id: int = 1,
                           dnet: int = None, dadr: bytes = None,
                           priority: int = 8) -> bytes:
    """
    BACnet WriteProperty Confirmed-Request paketi oluştur.
    Sadece REAL (float32) değer desteklenir — tüm analog set noktaları için yeterli.
    """
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])  # BVLC original-unicast (uzunluk sonra doldurulur)

    # NPDU — routed ağ için
    if dnet is not None and dadr is not None:
        npdu = struct.pack(">BBH B", 0x01, 0x20, dnet, len(dadr)) + dadr + b'\xff'
    else:
        npdu = bytes([0x01, 0x00])

    obj_id = (int(obj_type) << 22) | int(obj_inst)

    # APDU: Confirmed-Request, service=15 (WriteProperty)
    apdu  = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0F])
    # Context tag 0 — Object Identifier
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    # Context tag 1 — Property Identifier (present-value = 85)
    apdu += bytes([0x19, PROP_PRESENT_VALUE])
    # Context tag 3 — Property Value, opening tag
    apdu += bytes([0x3e])
    # Application tag 4 (REAL), length 4
    apdu += bytes([0x44]) + struct.pack(">f", float(value))
    # Closing tag
    apdu += bytes([0x3f])
    # Context tag 4 — Priority (isteğe bağlı)
    if priority is not None:
        apdu += bytes([0x49, int(priority)])

    return _pack_length(bvlc + npdu + apdu)


# ================================================================
# BACNET YAZMA
# ================================================================

def bacnet_yaz(gateway_ip: str, dnet: int, mac_hex: str,
               obj_type: int, obj_inst: int, deger: float,
               priority: int = 8) -> tuple[bool, str]:
    """
    BACnet WriteProperty ile değer yaz.
    Dönüş: (başarı: bool, mesaj: str)
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    sock.settimeout(WRITE_TIMEOUT)
    try:
        # MAC adresini bytes'a çevir
        mac_str = str(mac_hex).replace("0x", "").replace(" ", "").strip()
        if len(mac_str) % 2 != 0:
            mac_str = "0" + mac_str
        mac_bytes = bytes.fromhex(mac_str)

        invoke_id = random.randint(1, 255)
        pkt = _build_write_property(
            int(obj_type), int(obj_inst), float(deger),
            invoke_id=invoke_id,
            dnet=int(dnet), dadr=mac_bytes,
            priority=priority
        )
        sock.sendto(pkt, (gateway_ip, BACNET_PORT))

        # Cevap bekle — SimpleACK (0x20) veya Error (0x50/0x60/0x70)
        try:
            data, _ = sock.recvfrom(1024)
            # BVLC atlayarak NPDU+APDU'ya geç
            for i in range(4, min(20, len(data))):
                pdu_type = data[i] & 0xF0
                if pdu_type == 0x20:  # SimpleACK
                    logger.debug(f"  BACnet SimpleACK: {gateway_ip} obj={obj_type}/{obj_inst} val={deger}")
                    return True, "SimpleACK alındı"
                elif pdu_type == 0x50:
                    return False, "BACnet Error yanıtı"
                elif pdu_type == 0x60:
                    return False, "BACnet Reject"
                elif pdu_type == 0x70:
                    return False, "BACnet Abort"
            return True, "Cevap alındı (format bilinmiyor)"
        except socket.timeout:
            # Timeout = bazı cihazlar ACK göndermez, yine de başarılı sayılır
            return True, "Gönderildi (ACK beklenmedi)"

    except Exception as e:
        return False, f"Soket hatası: {e}"
    finally:
        sock.close()


# ================================================================
# SUPABASE KOMUT TABLOSU POLLING
# ================================================================

def _sb_get(sb_url: str, sb_key: str, query_path: str) -> list:
    """Supabase REST GET isteği."""
    req = urllib.request.Request(
        sb_url + query_path,
        headers={
            "apikey": sb_key,
            "Authorization": "Bearer " + sb_key,
            "Content-Type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def _sb_patch(sb_url: str, sb_key: str, path: str, payload: dict):
    """Supabase REST PATCH isteği."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        sb_url + path,
        data=data,
        headers={
            "apikey": sb_key,
            "Authorization": "Bearer " + sb_key,
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="PATCH"
    )
    urllib.request.urlopen(req, timeout=8)


def _komut_guncelle(sb_url: str, sb_key: str, komut_id: str,
                    durum: str, mesaj: str = ""):
    """Komutun durumunu ve executed_at'ını güncelle."""
    try:
        _sb_patch(sb_url, sb_key, f"/rest/v1/komutlar?id=eq.{komut_id}", {
            "durum": durum,
            "hata_mesaji": mesaj,
            "executed_at": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"Komut güncelleme hatası ({komut_id}): {e}")


def komutlari_isle(sb_url: str, sb_key: str, lokasyon_id: str):
    """
    komutlar tablosundan bekleyen kayıtları çek, BACnet ile yaz, durumu güncelle.
    Her 1 dakikada bir cloud_sync._heartbeat_loop() tarafından çağrılır.
    """
    try:
        # 1) Bekleyen komutlar
        komutlar = _sb_get(
            sb_url, sb_key,
            f"/rest/v1/komutlar"
            f"?lokasyon=eq.{lokasyon_id}"
            f"&durum=eq.bekliyor"
            f"&order=created_at.asc"
            f"&limit=20"
        )
        if not komutlar:
            return

        logger.info(f"⚡ {len(komutlar)} bekleyen komut bulundu: {lokasyon_id}")

        # 2) Bu lokasyonun nokta tablosunu çek
        noktalar_list = _sb_get(
            sb_url, sb_key,
            f"/rest/v1/lokasyon_noktalar"
            f"?lokasyon=eq.{lokasyon_id}"
            f"&select=nokta_adi,gateway_ip,dnet,mac_hex,obj_type,obj_inst"
        )
        noktalar = {n["nokta_adi"]: n for n in noktalar_list}

        # 3) Her komutu işle
        for komut in komutlar:
            kid        = komut["id"]
            nokta_adi  = komut["nokta_adi"]
            hedef      = komut["hedef_deger"]

            if nokta_adi not in noktalar:
                _komut_guncelle(sb_url, sb_key, kid, "hata",
                                f"Nokta tanımsız: {nokta_adi}")
                logger.warning(f"  ⚠️ Tanımsız nokta: {nokta_adi}")
                continue

            n = noktalar[nokta_adi]
            basari, mesaj = bacnet_yaz(
                n["gateway_ip"], n["dnet"], n["mac_hex"],
                n["obj_type"], n["obj_inst"], hedef
            )

            if basari:
                _komut_guncelle(sb_url, sb_key, kid, "tamamlandi", mesaj)
                logger.info(f"  ✅ {nokta_adi} = {hedef} → {mesaj}")
            else:
                _komut_guncelle(sb_url, sb_key, kid, "hata", mesaj)
                logger.error(f"  ❌ {nokta_adi} → {mesaj}")

    except Exception as e:
        logger.error(f"komutlari_isle genel hata: {e}")
