# -*- coding: utf-8 -*-
"""ANLIK SAHA OKUMASI — merkezden istenen tek seferlik sayaç okuması.

Synapse'teki lokasyon detay sayfasından "sahadan oku" denince merkez `komutlar`
tablosuna `nokta_adi = "OKUMA:<cihaz>"` olan bir istek yazar. Lokasyon her
dakika komutları işlerken bu isteği YAZMA yoluna sokmadan burada karşılar,
sayacı ÜRETİMDEKİ okuyucuyla (data_collector.modbus_get_kwh) okur ve sonucu
aynı komut satırına yazar. Merkez sonucu oradan gösterir.

NEDEN: Yeni bağlanan bir sayacın (21.09.2026: TRDP-4) çalıştığını görmek için
ertesi sabahın otomatik okumasını beklemek ya da sahaya gidip betik çalıştırmak
gerekiyordu.

GÜVENLİK:
  - Yalnızca OKUR. Hiçbir cihaza yazmaz.
  - Yalnızca IZINLI kümesindeki cihazlar okunabilir (şimdilik yalnız TRDP-4).
  - Günlük tüketim referansına (modbus_daily_ref.json) ve okuma CSV'sine
    DOKUNMAZ — günlük hesap etkilenmez.
  - bacnet_writer bu istekleri nokta tablosuna / değer kapısına / BACnet yazmaya
    ulaşmadan ayırır; ayrıca "OKUMA:..." hiçbir nokta adıyla eşleşmediği ve
    hedef değer 0 olduğu için yanlışlıkla yazma yoluna girse bile yazılamaz.
"""
import socket
import time

OKUMA_ONEK = "OKUMA:"

# Merkezden okunmasına izin verilen cihazlar. Kullanıcı kararı (21.09.2026):
# yalnızca TRDP-4 — yeni bağlanan sayacın veri verip vermediğini görmek için.
IZINLI = {"TRDP-4"}


def okuma_istegi_mi(nokta_adi) -> bool:
    return isinstance(nokta_adi, str) and nokta_adi.startswith(OKUMA_ONEK)


def _tcp_acik_mi(ip, port=502, sure=3.0):
    try:
        s = socket.socket()
        s.settimeout(sure)
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False


def isle(nokta_adi):
    """Okuma isteğini yürütür. (durum, mesaj) döner.

    durum: "tamamlandi" — okundu, mesajda değer var
           "hata"       — izin yok / cihaz tanımsız / okunamadı (mesajda teşhis)
    Her iki durum da komutlar RLS'inin izin verdiği "bekliyor → sonuçlanmış"
    geçişidir.
    """
    cihaz = str(nokta_adi)[len(OKUMA_ONEK):].strip()
    if cihaz not in IZINLI:
        return "hata", ("Okuma izni yok: %s (merkezden okunabilenler: %s)"
                        % (cihaz or "?", ", ".join(sorted(IZINLI))))
    try:
        import data_collector as dc                   # ÜRETİMDEKİ okuyucu
    except Exception as e:
        return "hata", "Okuyucu yüklenemedi: %s" % e

    dev = next((a for a in dc.ANALYZERS if a.get("name") == cihaz), None)
    if not dev:
        return "hata", "%s toplayıcı listesinde tanımsız (yama inmemiş olabilir)" % cihaz

    t0 = time.time()
    deger = dc.modbus_get_kwh(dev)
    sure = time.time() - t0
    if deger is not None:
        return "tamamlandi", ("%s okundu: %s kWh · %s · %.1f sn"
                              % (cihaz, format(deger, ",.3f"), dev["ip"], sure))

    # Teşhis: ağ mı, protokol mü?
    if _tcp_acik_mi(dev["ip"]):
        neden = "TCP 502 açık ama Modbus yanıtı çözülemedi (register adresi / birim kimliği?)"
    else:
        neden = "cihaza erişilemiyor (TCP 502 kapalı / ağ)"
    return "hata", "%s okunamadı: %s · %s" % (cihaz, neden, dev["ip"])
