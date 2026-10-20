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
GUC_ONEK = "GUC:"

# Merkezden okunmasına izin verilen cihazlar.
#   21.09.2026: yalnızca TRDP-4 — yeni bağlanan sayacın veri verip vermediğini
#               görmek için.
#   20.10.2026: dört trafo da eklendi. Canlı güç paneli bu cihazları okuyor;
#               bir trafo "0 kW" gösterdiğinde sorunun ağda mı, register
#               adresinde mi olduğunu sahaya gitmeden ayırabilmek gerekiyor.
# Liste bilerek dardır: yalnızca trafolar, yalnızca OKUMA.
IZINLI = {"TRDP-1", "TRDP-2", "TRDP-3", "TRDP-4"}


def okuma_istegi_mi(nokta_adi) -> bool:
    return isinstance(nokta_adi, str) and nokta_adi.startswith(OKUMA_ONEK)


def guc_istegi_mi(nokta_adi) -> bool:
    return isinstance(nokta_adi, str) and nokta_adi.startswith(GUC_ONEK)


def istek_mi(nokta_adi) -> bool:
    """Bu komut bir OKUMA isteği mi (yani yazma yoluna girmemeli mi)?"""
    return okuma_istegi_mi(nokta_adi) or guc_istegi_mi(nokta_adi)


def _tcp_acik_mi(ip, port=502, sure=3.0):
    try:
        s = socket.socket()
        s.settimeout(sure)
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False


def _cihaz_bul(cihaz):
    """(dev, hata_mesaji) — izin ve tanım kontrolü tek yerde."""
    if cihaz not in IZINLI:
        return None, ("Okuma izni yok: %s (merkezden okunabilenler: %s)"
                      % (cihaz or "?", ", ".join(sorted(IZINLI))))
    try:
        import data_collector as dc                   # ÜRETİMDEKİ okuyucu
    except Exception as e:
        return None, "Okuyucu yüklenemedi: %s" % e
    dev = next((a for a in dc.ANALYZERS if a.get("name") == cihaz), None)
    if not dev:
        return None, "%s toplayıcı listesinde tanımsız (yama inmemiş olabilir)" % cihaz
    return dev, None


def guc_isle(nokta_adi):
    """GUC:<cihaz>[:<register>] — anlık güç register'ını okur ve DOĞRULAR.

    Canlı panel gücü bir register'dan okuyor; o adres cihaz modeline göre
    değişir ve yanlış adres "makul ama yanlış" bir sayı döndürebilir. Bu
    komut iki soruyu sahaya gitmeden cevaplar:
      · register ne diyor?
      · sayaç farkı (kWh) ne diyor — yani register'a güvenilir mi?

    Register verilirse o adres DENENİR (doğru adresi aramak için); verilmezse
    ayardaki adres kullanılır ve varsa canlı ölçümün kendi çapraz denetimi
    raporlanır.
    """
    govde = str(nokta_adi)[len(GUC_ONEK):].strip()
    parcalar = [p.strip() for p in govde.split(":")]
    cihaz = parcalar[0]
    adres = None
    if len(parcalar) > 1 and parcalar[1]:
        try:
            adres = int(parcalar[1], 0)      # "19026" ya da "0x4A52"
        except ValueError:
            return "hata", "Register adresi sayı olmalı: %s" % parcalar[1]

    dev, hata = _cihaz_bul(cihaz)
    if hata:
        return "hata", hata

    try:
        import canli_guc
    except Exception as e:
        return "hata", "Canlı güç modülü yüklenemedi: %s" % e

    ayar = canli_guc.ayar_oku()
    kullanilan = adres if adres is not None else \
        (ayar.get("guc_register") or {}).get(dev.get("brand"))

    t0 = time.time()
    kw = canli_guc.guc_oku(dev, ayar, adres=adres)
    sure = time.time() - t0

    if kw is None:
        neden = ("TCP 502 açık ama register okunamadı (adres %s cihazda yok olabilir)"
                 % kullanilan) if _tcp_acik_mi(dev["ip"]) \
            else "cihaza erişilemiyor (TCP 502 kapalı / ağ)"
        return "hata", "%s güç okunamadı: %s · %s" % (cihaz, neden, dev["ip"])

    # Doğrulama: canlı ölçüm tazeyse onun kendi çapraz denetimini kullan,
    # yoksa burada iki sayaç okumasıyla ortalama gücü çıkar.
    dogrulama = ""
    son = canli_guc.son_olcum()
    kayit = next((o for o in (son or {}).get("olcumler", [])
                  if o.get("cihaz") == cihaz), None) if adres is None else None
    if kayit and kayit.get("kw_sayac") is not None:
        dogrulama = " · sayaç farkı %.0f kW → %s" % (
            kayit["kw_sayac"],
            "UYUMLU" if kayit.get("yontem") == "register" else "UYUŞMUYOR")
    else:
        e1 = _dc_kwh(dev)
        time.sleep(10)
        e2 = _dc_kwh(dev)
        if e1 is not None and e2 is not None and e2 >= e1:
            kw_sayac = (e2 - e1) / 10.0 * 3600.0
            fark = abs(kw - kw_sayac)
            pay = max(ayar["tolerans_kw"], abs(kw_sayac) * ayar["tolerans_oran"])
            dogrulama = " · sayaç farkı %.0f kW → %s" % (
                kw_sayac, "UYUMLU" if fark <= pay else "UYUŞMUYOR")
        else:
            dogrulama = " · sayaç farkı alınamadı (doğrulanamadı)"

    return "tamamlandi", ("%s güç: %.1f kW · register %s · %s · %.1f sn%s"
                          % (cihaz, kw, kullanilan, dev["ip"], sure, dogrulama))


def _dc_kwh(dev):
    try:
        import data_collector as dc
        return dc.modbus_get_kwh(dev)
    except Exception:
        return None


def isle(nokta_adi):
    """Okuma isteğini yürütür. (durum, mesaj) döner.

    durum: "tamamlandi" — okundu, mesajda değer var
           "hata"       — izin yok / cihaz tanımsız / okunamadı (mesajda teşhis)
    Her iki durum da komutlar RLS'inin izin verdiği "bekliyor → sonuçlanmış"
    geçişidir.
    """
    if guc_istegi_mi(nokta_adi):
        return guc_isle(nokta_adi)

    cihaz = str(nokta_adi)[len(OKUMA_ONEK):].strip()
    dev, hata = _cihaz_bul(cihaz)
    if hata:
        return "hata", hata

    t0 = time.time()
    deger = _dc_kwh(dev)
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
