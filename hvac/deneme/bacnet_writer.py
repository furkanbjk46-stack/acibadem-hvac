# bacnet_writer.py
# BACnet WriteProperty / ReadProperty (ham UDP socket) + Supabase komutlar tablosu polling
# cloud_sync.py'nin arka plan heartbeat döngüsünden çağrılır.
# Dış kütüphane gerektirmez — data_collector.py ile aynı yaklaşım.

import socket
import struct
import random
import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BACNET_PORT    = 47808
YANIT_TIMEOUT  = 5.0       # yazma cevabı için bekleme (sn)
OKUMA_TIMEOUT  = 3.0       # okuma cevabı için bekleme (sn)
DOGRULAMA_BEKLEME = 2.0    # yazma ile geri okuma arasındaki bekleme (sn)
DOGRULAMA_TOLERANS = 0.05  # geri okunan değer bu kadar farkla "aynı" sayılır (°C)
PROP_PRESENT_VALUE = 85    # BACnet property ID

# ── GÜVENLİK: komut değeri kabul aralığı (°C) ──────────────────────────────
# komutlar tablosuna yazma yetkisi olan herkes sahaya setpoint gönderebiliyor.
# Bu yüzden BACnet'e yazmadan ÖNCE değer burada sınırlanır: aralık dışı komut
# cihaza HİÇ gönderilmez, 'hata' olarak işaretlenir (savunma derinliği —
# Supabase RLS politikaları ilk katman, bu ikinci katman).
# merkez/app_merkez.py "Uzaktan Kontrol" giriş alanı da AYNI sınırları kullanır
# (test_bacnet_writer.py eşitliği doğrular).
KOMUT_DEGER_MIN = 5.0
KOMUT_DEGER_MAX = 40.0

# ── Bekleyen komutun ömrü (dakika) ─────────────────────────────────────────
# Lokasyon uzun süre çevrimdışı kalıp geri geldiğinde, günler önce kuyruğa
# girmiş bir komut o an sahaya yazılıyordu (Altunizade 65 gün çevrimdışıydı).
# Bu süreden eski komut uygulanmaz, "suresi_doldu" olarak işaretlenir.
# 30 dk: lokasyon PC saatinin birkaç dakika kayması komutları boşa düşürmesin.
KOMUT_OMUR_DK = 30


def komut_degeri_gecerli(deger):
    """Komut değerini doğrular. (gecerli: bool, sebep: str) döner."""
    try:
        d = float(deger)
    except (TypeError, ValueError):
        return False, f"Gecersiz deger tipi: {deger!r}"
    if d != d or d in (float("inf"), float("-inf")):  # NaN / sonsuz
        return False, f"Gecersiz sayisal deger: {deger!r}"
    if not (KOMUT_DEGER_MIN <= d <= KOMUT_DEGER_MAX):
        return False, (f"Deger izinli aralik disinda: {d} "
                       f"(izinli {KOMUT_DEGER_MIN}-{KOMUT_DEGER_MAX} C)")
    return True, ""


def komut_suresi_doldu(created_at, simdi=None):
    """Komut ömrünü aştı mı? (doldu: bool, yas_dk: float|None) döner.

    created_at okunamazsa komut ESKİ SAYILMAZ — yanlışlıkla geçerli bir komutu
    düşürmek yerine uygulamak tercih edilir (önceki davranış).
    Lokasyon PC saati Supabase'in gerisindeyse yaş negatif çıkar; o da taze sayılır.
    """
    simdi = simdi or datetime.now(timezone.utc)
    try:
        z = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if z.tzinfo is None:
            z = z.replace(tzinfo=timezone.utc)
    except Exception:
        return False, None
    yas = (simdi - z).total_seconds() / 60
    return yas > KOMUT_OMUR_DK, yas


# ================================================================
# PAKET OLUŞTURMA
# ================================================================

def _pack_length(packet: bytes) -> bytes:
    """BVLC uzunluk alanını güncelle."""
    return packet[:2] + struct.pack(">H", len(packet)) + packet[4:]


def _npdu(dnet=None, dadr=None) -> bytes:
    """NPDU — Confirmed-Request için 'expecting reply' (0x04) biti SET edilir.

    İlk sürümde bu bit yoktu (control=0x20). Standart gereği confirmed istekte
    bulunmalı; bazı router'lar bit yoksa cevabı geri yönlendirmez ve yazma
    cevapsız kalır.
    """
    if dnet is not None and dadr is not None:
        return struct.pack(">BBH B", 0x01, 0x24, int(dnet), len(dadr)) + dadr + b'\xff'
    return bytes([0x01, 0x04])


def _build_write_property(obj_type: int, obj_inst: int, value: float,
                           invoke_id: int = 1,
                           dnet: int = None, dadr: bytes = None,
                           priority: int = 8) -> bytes:
    """
    BACnet WriteProperty Confirmed-Request paketi oluştur.
    Sadece REAL (float32) değer desteklenir — tüm analog set noktaları için yeterli.
    """
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])  # BVLC original-unicast (uzunluk sonra doldurulur)
    obj_id = (int(obj_type) << 22) | int(obj_inst)

    # APDU: Confirmed-Request, service=15 (WriteProperty)
    apdu  = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0F])
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)       # ctx 0 — Object Identifier
    apdu += bytes([0x19, PROP_PRESENT_VALUE])              # ctx 1 — present-value
    apdu += bytes([0x3e])                                   # ctx 3 — açılış
    apdu += bytes([0x44]) + struct.pack(">f", float(value)) # REAL
    apdu += bytes([0x3f])                                   # kapanış
    if priority is not None:
        apdu += bytes([0x49, int(priority)])                # ctx 4 — Priority

    return _pack_length(bvlc + _npdu(dnet, dadr) + apdu)


def _build_read_property(obj_type: int, obj_inst: int, prop_id: int = PROP_PRESENT_VALUE,
                          invoke_id: int = 1, dnet: int = None, dadr: bytes = None) -> bytes:
    """BACnet ReadProperty Confirmed-Request paketi."""
    bvlc = bytes([0x81, 0x0a, 0x00, 0x00])
    obj_id = (int(obj_type) << 22) | int(obj_inst)
    apdu  = bytes([0x00, 0x04, invoke_id & 0xFF, 0x0C])     # service=12 ReadProperty
    apdu += bytes([0x0c]) + struct.pack(">I", obj_id)
    apdu += bytes([0x19, int(prop_id) & 0xFF])
    return _pack_length(bvlc + _npdu(dnet, dadr) + apdu)


# ================================================================
# CEVAP ÇÖZME
# ================================================================
#
# İLK SÜRÜMDEKİ HATA: cevabın 4.–20. baytları taranıp üst yarısı 0x2X olan
# ilk bayt "SimpleACK" sayılıyordu. Router üzerinden gelen cevaplarda NPDU'daki
# ağ numarası (SNET) ya da MAC (SADR) baytları bu değeri taşıyabildiği için
# gerçek cevap HATA olduğu hâlde başarı raporlanabiliyordu. Ayrıca istek
# numarası (invoke id) hiç kontrol edilmiyor, cevapsızlık ve anlaşılamayan
# cevap da "başarılı" sayılıyordu. Ağsız sınamada 7 senaryonun 5'i yanlıştı.
#
# Artık NPDU standarttaki alanlarına göre atlanır, APDU tipi ve invoke id
# doğrulanır; cevap yoksa ya da anlaşılmıyorsa sonuç BAŞARISIZDIR.

_BACNET_HATA_SINIF = {0: "device", 1: "object", 2: "property", 3: "resources",
                      4: "security", 5: "services", 7: "communication"}
_BACNET_HATA_KOD = {2: "configuration-in-progress", 9: "invalid-data-type",
                    31: "unknown-object", 32: "unknown-property",
                    37: "value-out-of-range", 40: "write-access-denied",
                    42: "invalid-array-index"}


def _apdu_ayikla(data: bytes):
    """BVLC ve NPDU'yu standarda göre atlayıp APDU baytlarını döner.

    Ağ katmanı mesajı ya da bozuk paket için None.
    """
    try:
        if len(data) < 6 or data[0] != 0x81:
            return None
        fn = data[1]
        i = 4
        if fn == 0x04:              # Forwarded-NPDU (BBMD): +6 bayt kaynak adresi
            i += 6
        elif fn not in (0x0a, 0x0b):
            return None
        if data[i] != 0x01:         # NPDU sürümü
            return None
        ctrl = data[i + 1]
        i += 2
        if ctrl & 0x80:             # ağ katmanı mesajı — APDU yok
            return None
        if ctrl & 0x20:             # DNET, DLEN, DADR
            i += 3 + data[i + 2]
        if ctrl & 0x08:             # SNET, SLEN, SADR
            i += 3 + data[i + 2]
        if ctrl & 0x20:             # hop count
            i += 1
        return data[i:] if i < len(data) else None
    except IndexError:
        return None


def _hata_metni(apdu: bytes) -> str:
    tip = apdu[0] >> 4
    if tip == 5:
        try:
            sinif = _BACNET_HATA_SINIF.get(apdu[4], apdu[4])
            kod = _BACNET_HATA_KOD.get(apdu[6], apdu[6])
            return f"BACnet Error ({sinif}/{kod})"
        except IndexError:
            return "BACnet Error"
    if tip == 6:
        return f"BACnet Reject (sebep {apdu[2] if len(apdu) > 2 else '?'})"
    if tip == 7:
        return f"BACnet Abort (sebep {apdu[2] if len(apdu) > 2 else '?'})"
    return "Beklenmeyen cevap"


def _istek_gonder(gateway_ip: str, pkt: bytes, invoke_id: int, timeout: float):
    """Paketi gönderir, AYNI invoke id'li cevabı bekler.

    (apdu | None, mesaj) döner. Başka isteğe ait / anlaşılamayan paketler
    atlanır ve süre dolana kadar beklemeye devam edilir.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", 0))
        sock.sendto(pkt, (gateway_ip, BACNET_PORT))
        bitis = time.monotonic() + timeout
        atlanan = 0
        while True:
            kalan = bitis - time.monotonic()
            if kalan <= 0:
                break
            sock.settimeout(kalan)
            try:
                data, _ = sock.recvfrom(1500)
            except socket.timeout:
                break
            apdu = _apdu_ayikla(data)
            if not apdu or len(apdu) < 2 or (apdu[0] >> 4) not in (2, 3, 5, 6, 7):
                atlanan += 1
                continue
            if apdu[1] != (invoke_id & 0xFF):   # başka isteğe ait (geç gelen) cevap
                atlanan += 1
                continue
            return apdu, ""
        ek = f", {atlanan} ilgisiz paket atlandı" if atlanan else ""
        return None, f"Cevap yok (zaman aşımı {timeout:.0f} sn{ek})"
    except Exception as e:
        return None, f"Soket hatası: {e}"
    finally:
        sock.close()


def _mac_bytes(mac_hex) -> bytes:
    mac_str = str(mac_hex).replace("0x", "").replace("0X", "").replace(" ", "").strip()
    if len(mac_str) % 2 != 0:
        mac_str = "0" + mac_str
    return bytes.fromhex(mac_str)


def _deger_coz(apdu: bytes):
    """ReadProperty ComplexACK içinden sayısal değeri çıkarır. None: çözülemedi."""
    try:
        if apdu[0] & 0x08:          # segmentli cevap — tek değer için beklenmez
            return None
        i = 3
        if apdu[i] != 0x0C:         # ctx 0 object id
            return None
        i += 5
        b = apdu[i]                 # ctx 1 property id (1-2 bayt)
        if (b >> 4) != 1:
            return None
        i += 1 + (b & 0x07)
        if (apdu[i] >> 4) == 2 and (apdu[i] & 0x08):   # ctx 2 array index (opsiyonel)
            i += 1 + (apdu[i] & 0x07)
        if apdu[i] != 0x3E:
            return None
        i += 1
        b = apdu[i]
        tag, uzunluk = b >> 4, b & 0x07
        if b & 0x08:                # context tag — uygulama değeri değil
            return None
        if tag == 1:                # BOOLEAN (değer uzunluk alanında)
            return float(uzunluk)
        if uzunluk == 5:
            uzunluk = apdu[i + 1]
            i += 1
        veri = apdu[i + 1:i + 1 + uzunluk]
        if tag == 4 and uzunluk == 4:
            return struct.unpack(">f", veri)[0]
        if tag == 5 and uzunluk == 8:
            return struct.unpack(">d", veri)[0]
        if tag in (2, 9):           # UNSIGNED / ENUMERATED
            return float(int.from_bytes(veri, "big"))
        if tag == 3:                # SIGNED
            return float(int.from_bytes(veri, "big", signed=True))
        return None
    except (IndexError, struct.error):
        return None


# ================================================================
# BACNET YAZMA / OKUMA
# ================================================================

def bacnet_yaz(gateway_ip: str, dnet: int, mac_hex: str,
               obj_type: int, obj_inst: int, deger: float,
               priority: int = 8) -> tuple[bool, str]:
    """
    BACnet WriteProperty ile değer yaz.
    Dönüş: (başarı: bool, mesaj: str) — YALNIZCA cihazdan SimpleACK gelirse başarılı.
    """
    try:
        invoke_id = random.randint(1, 255)
        pkt = _build_write_property(int(obj_type), int(obj_inst), float(deger),
                                    invoke_id=invoke_id, dnet=int(dnet),
                                    dadr=_mac_bytes(mac_hex), priority=priority)
    except Exception as e:
        return False, f"Paket oluşturulamadı: {e}"

    apdu, mesaj = _istek_gonder(gateway_ip, pkt, invoke_id, YANIT_TIMEOUT)
    if apdu is None:
        return False, mesaj
    if (apdu[0] >> 4) == 2:
        logger.debug(f"  BACnet SimpleACK: {gateway_ip} obj={obj_type}/{obj_inst} val={deger}")
        return True, "SimpleACK alındı"
    return False, _hata_metni(apdu)


def bacnet_oku(gateway_ip: str, dnet: int, mac_hex: str,
               obj_type: int, obj_inst: int,
               prop_id: int = PROP_PRESENT_VALUE) -> tuple[bool, object]:
    """BACnet ReadProperty. (başarı, değer | hata mesajı) döner."""
    try:
        invoke_id = random.randint(1, 255)
        pkt = _build_read_property(int(obj_type), int(obj_inst), prop_id,
                                   invoke_id=invoke_id, dnet=int(dnet),
                                   dadr=_mac_bytes(mac_hex))
    except Exception as e:
        return False, f"Paket oluşturulamadı: {e}"

    apdu, mesaj = _istek_gonder(gateway_ip, pkt, invoke_id, OKUMA_TIMEOUT)
    if apdu is None:
        return False, mesaj
    if (apdu[0] >> 4) != 3:
        return False, _hata_metni(apdu)
    deger = _deger_coz(apdu)
    if deger is None:
        return False, "Okunan değer çözülemedi"
    return True, deger


def _nokta_adres(n: dict):
    return (n["gateway_ip"], n["dnet"], n["mac_hex"], n["obj_type"], n["obj_inst"])


def yaz_dogrula_toplu(isler: list, geri_okuma: dict = None) -> dict:
    """Setpoint'leri yazar ve SAHADA oturduğunu geri okuyarak doğrular.

    isler     : [(anahtar, nokta_dict, deger), ...]
    geri_okuma: {anahtar: nokta_dict} — ek olarak okunacak "gerçekleşen" nokta
                (ör. CH-1 REM SET yazılır, CH-1 IC SET okunur). Opsiyonel.

    Her anahtar için sözlük döner:
      durum : "oturdu"        — yazıldı ve aynı nesnede aynı değer okundu
              "sahada_farkli" — yazıldı (ACK) ama cihazda başka değer var
                                 (daha yüksek öncelikli bir yazma/override olabilir)
              "dogrulanamadi" — yazıldı (ACK) ama geri okunamadı
              "yazma_hatasi"  — cihaz yazmayı kabul etmedi / cevap vermedi
      mesaj, okunan, ic_okunan (varsa)

    Önce hepsi yazılır, TEK bekleme yapılır, sonra hepsi okunur: 11 nokta için
    nokta başına beklemek heartbeat döngüsünü ~20 sn kilitliyordu.
    """
    geri_okuma = geri_okuma or {}
    sonuc = {}
    for anahtar, n, deger in isler:
        ok, mesaj = bacnet_yaz(*_nokta_adres(n), deger)
        sonuc[anahtar] = {"deger": deger, "yazma_ok": ok, "mesaj": mesaj,
                          "okunan": None, "ic_okunan": None,
                          "durum": None if ok else "yazma_hatasi"}

    if any(s["yazma_ok"] for s in sonuc.values()):
        time.sleep(DOGRULAMA_BEKLEME)

    for anahtar, n, deger in isler:
        s = sonuc[anahtar]
        if not s["yazma_ok"]:
            continue
        rok, val = bacnet_oku(*_nokta_adres(n))
        if not rok:
            s["durum"] = "dogrulanamadi"
            s["mesaj"] = f"Yazıldı (ACK) ama geri okunamadı: {val}"
        elif abs(float(val) - float(deger)) <= DOGRULAMA_TOLERANS:
            s["durum"] = "oturdu"
            s["okunan"] = round(float(val), 2)
            s["mesaj"] = f"Cihazda doğrulandı: {s['okunan']}"
        else:
            s["durum"] = "sahada_farkli"
            s["okunan"] = round(float(val), 2)
            s["mesaj"] = (f"Yazıldı (ACK) ama cihazda {s['okunan']} okundu — "
                          f"daha yüksek öncelikli bir yazma/override olabilir")
        ic = geri_okuma.get(anahtar)
        if ic:
            iok, ival = bacnet_oku(*_nokta_adres(ic))
            if iok:
                s["ic_okunan"] = round(float(ival), 2)
    return sonuc


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
            # timestamptz kolonu: saat dilimi YAZILMALI. Önceden yerel saat
            # dilimsiz yazılıyor, Postgres onu UTC sanıyor ve 3 saat kaymış
            # görünüyordu.
            "executed_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.error(f"Komut güncelleme hatası ({komut_id}): {e}")


# Doğrulama sonucunun komut tablosuna yansıması
_KOMUT_DURUMU = {
    "oturdu":        "tamamlandi",
    "sahada_farkli": "hata",
    "yazma_hatasi":  "hata",
    "dogrulanamadi": "dogrulanamadi",
}


def geri_okuma_haritasi(lokasyon_id: str) -> dict:
    """configs/geri_okuma.json — yazılan nokta → gerçekleşen değerin okunduğu nokta.

    Ör. maslak: CH1_REM_SET (yazılan) → CH-1 IC SET (chiller'ın o an kullandığı).
    Dosya yoksa / lokasyon tanımlı değilse boş sözlük (yalnızca aynı nesne
    geri okunur).
    """
    try:
        yol = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "configs", "geri_okuma.json")
        with open(yol, encoding="utf-8") as f:
            return json.load(f).get(lokasyon_id, {}) or {}
    except Exception:
        return {}


def komutlari_isle(sb_url: str, sb_key: str, lokasyon_id: str):
    """
    komutlar tablosundan bekleyen kayıtları çek, BACnet ile yaz, sahada doğrula,
    durumu güncelle. Her 1 dakikada bir cloud_sync._heartbeat_loop() tarafından çağrılır.
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
        harita = geri_okuma_haritasi(lokasyon_id)

        # 3) Ön kontroller — geçenler toplu yazılıp doğrulanır
        isler = []
        for komut in komutlar:
            kid        = komut["id"]
            nokta_adi  = komut["nokta_adi"]
            hedef      = komut["hedef_deger"]

            doldu, yas = komut_suresi_doldu(komut.get("created_at"))
            if doldu:
                _komut_guncelle(sb_url, sb_key, kid, "suresi_doldu",
                                f"Uygulanmadı: {yas:.0f} dk bekledi "
                                f"(ömür {KOMUT_OMUR_DK} dk)")
                logger.warning(f"  ⌛ Süresi dolmuş komut atlandı ({nokta_adi}, {yas:.0f} dk)")
                continue

            if nokta_adi not in noktalar:
                _komut_guncelle(sb_url, sb_key, kid, "hata",
                                f"Nokta tanımsız: {nokta_adi}")
                logger.warning(f"  ⚠️ Tanımsız nokta: {nokta_adi}")
                continue

            # GÜVENLİK KAPISI: aralık dışı/bozuk değer sahaya gönderilmez
            _gecerli, _sebep = komut_degeri_gecerli(hedef)
            if not _gecerli:
                _komut_guncelle(sb_url, sb_key, kid, "hata", _sebep)
                logger.warning(f"  🛑 Komut reddedildi ({nokta_adi}): {_sebep}")
                continue

            isler.append((kid, noktalar[nokta_adi], hedef))

        if not isler:
            return

        ic_noktalari = {kid: harita[k["nokta_adi"]] for k in komutlar
                        for kid in [k["id"]] if k["nokta_adi"] in harita}
        sonuc = yaz_dogrula_toplu(isler, ic_noktalari)

        for kid, n, hedef in isler:
            s = sonuc[kid]
            mesaj = s["mesaj"]
            if s.get("ic_okunan") is not None:
                # Bilgi amaçlı: chiller uzaktan seti gecikmeli uygulayabilir,
                # bu yüzden IC SET farkı komutu başarısız saymaz.
                mesaj += f" · IC SET: {s['ic_okunan']}"
            _komut_guncelle(sb_url, sb_key, kid, _KOMUT_DURUMU[s["durum"]], mesaj)
            simge = "✅" if s["durum"] == "oturdu" else "⚠️" if s["durum"] == "dogrulanamadi" else "❌"
            logger.info(f"  {simge} {n.get('nokta_adi', kid)} = {hedef} → {mesaj}")

    except Exception as e:
        logger.error(f"komutlari_isle genel hata: {e}")
