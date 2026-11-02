# -*- coding: utf-8 -*-
"""ŞEBEKE SAYACI DENEME OKUMASI — Siemens SENTRON PAC3200 (192.168.1.15)

NEDEN: Şebeke tüketimi 01.06.2026'dan beri Veri Girişi'nden ELLE giriliyor
(enerji_hesap.YENI_KURAL_BASLANGIC). EDAŞ girişindeki şebeke sayacı Modbus'a
bağlandı; otomatiğe almadan ÖNCE sayacın doğru ve canlı veri verdiği
sahada görülmeli. Bu betik o denemedir — programa bağlı DEĞİLDİR.

NE YAPAR (yalnız OKUR, sayaca hiçbir şey YAZMAZ, hiçbir dosyaya dokunmaz):
  1. 502 portu açık mı?
  2. Tek seferlik tam okuma: gerilim, akım, frekans, faz güçleri, toplam
     etkin/reaktif güç, güç faktörü, enerji sayaçları (Giren/Verilen,
     Tarife 1/2). Her değer için makullük kontrolü.
  3. Canlı akış: her N saniyede toplam etkin güç (register 65) ve enerji
     sayacı. Enerji farkından hesaplanan ortalama güç register'la
     KARŞILAŞTIRILIR (canli_guc.py'deki çapraz denetimle aynı mantık) —
     yanlış register / yanlış akım trafosu oranı böyle yakalanır.
  4. Bilgi: canlı panelin son ölçümünden (configs/canli_guc_son.json)
     "trafo toplamı − kojen üretimi" beklenen şebeke değeri yan yana yazılır.
  5. Her satır sebeke_deneme_<tarih>.csv'ye yazılır — sonucu geri göndermek için.

Register adresleri SENTRON PAC3200 cihaz kitabı, Modbus ölçüm büyüklükleri
tablosundan (programın kojen/TRDP için yıllardır okuduğu adreslerle aynı harita):
    1/3/5   Gerilim L1-N/L2-N/L3-N   float  V
    7/9/11  Gerilim L1-L2/L2-L3/L3-L1 float V
    13/15/17 Akım L1/L2/L3           float  A
    25/27/29 Etkin güç L1/L2/L3      float  W
    55      Frekans                  float  Hz
    63      Toplam görünür güç       float  VA
    65      Toplam etkin güç         float  W   (eksi = şebekeye veriliyor)
    67      Toplam reaktif güç       float  var
    69      Toplam güç faktörü       float
    801/805 Etkin enerji GİREN  T1/T2  double Wh
    809/813 Etkin enerji VERİLEN T1/T2 double Wh

Kullanım (lokasyon PC'sinde, program klasöründe):
    python sebeke_deneme.py                 → 5 sn arayla canlı akış (Ctrl+C ile dur)
    python sebeke_deneme.py --sure 3        → 3 sn arayla
    python sebeke_deneme.py --ip 192.168.1.15 --birim 1
    python sebeke_deneme.py --tek           → yalnız tek seferlik tam okuma
"""
import argparse
import csv
import json
import os
import socket
import struct
import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BURASI = os.path.dirname(os.path.abspath(__file__))
VARSAYILAN_IP = "192.168.1.15"
PORT = 502

# (ad, adres, tip, birim)  tip: "f" = float32 (2 reg), "d" = double (4 reg)
OLCUMLER = [
    ("Gerilim L1-N",   1, "f", "V"),
    ("Gerilim L2-N",   3, "f", "V"),
    ("Gerilim L3-N",   5, "f", "V"),
    ("Gerilim L1-L2",  7, "f", "V"),
    ("Gerilim L2-L3",  9, "f", "V"),
    ("Gerilim L3-L1", 11, "f", "V"),
    ("Akım L1",       13, "f", "A"),
    ("Akım L2",       15, "f", "A"),
    ("Akım L3",       17, "f", "A"),
    ("Etkin güç L1",  25, "f", "W"),
    ("Etkin güç L2",  27, "f", "W"),
    ("Etkin güç L3",  29, "f", "W"),
    ("Frekans",       55, "f", "Hz"),
    ("Toplam görünür güç", 63, "f", "VA"),
    ("Toplam etkin güç",   65, "f", "W"),
    ("Toplam reaktif güç", 67, "f", "var"),
    ("Güç faktörü",        69, "f", ""),
    ("Enerji GİREN T1",   801, "d", "Wh"),
    ("Enerji GİREN T2",   805, "d", "Wh"),
    ("Enerji VERİLEN T1", 809, "d", "Wh"),
    ("Enerji VERİLEN T2", 813, "d", "Wh"),
]

_ISTISNA = {1: "fonksiyon desteklenmiyor", 2: "register adresi yok",
            3: "geçersiz değer/adet", 4: "cihaz hatası", 6: "cihaz meşgul",
            10: "gateway yolu yok", 11: "gateway arkasındaki cihaz cevap vermedi"}


# ── Modbus TCP (programla aynı yaklaşım: ham soket, kütüphanesiz) ─────────
# Programdaki okuyucular (canli_guc._float_oku, data_collector._siemens_double)
# hatada yalnız None döner. Deneme için NEDEN okunamadığı gerekli
# (ağ mı, adres mi, birim no mu) — bu yüzden hata metniyle dönen sürüm.

_islem_no = 0


def _oku(ip, adres, adet, birim, timeout):
    """(ham_bayt, hata) döner. Hata yoksa ham_bayt adet*2 uzunluğundadır."""
    global _islem_no
    _islem_no = (_islem_no + 1) % 65000
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, PORT))
        s.sendall(struct.pack(">HHHBBHH", _islem_no, 0, 6, birim, 3, int(adres), int(adet)))
        beklenen = 9 + adet * 2
        veri = b""
        while len(veri) < 9 or (veri[7] == 3 and len(veri) < beklenen):
            parca = s.recv(256)
            if not parca:
                break
            veri += parca
        if len(veri) >= 9 and veri[7] == 0x83:
            kod = veri[8]
            return None, "Modbus istisnası %d (%s)" % (kod, _ISTISNA.get(kod, "?"))
        if len(veri) < beklenen or veri[7] != 3:
            return None, "eksik/bozuk yanıt (%d bayt)" % len(veri)
        return veri[9:9 + adet * 2], None
    except socket.timeout:
        return None, "zaman aşımı"
    except ConnectionRefusedError:
        return None, "bağlantı reddedildi (502 kapalı)"
    except OSError as e:
        return None, "ağ hatası: %s" % e
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


def deger_oku(ip, adres, tip, birim, timeout=2.5):
    adet = 2 if tip == "f" else 4
    ham, hata = _oku(ip, adres, adet, birim, timeout)
    if hata:
        return None, hata
    return struct.unpack(">f" if tip == "f" else ">d", ham)[0], None


def port_acik_mi(ip, sure=3.0):
    try:
        with socket.create_connection((ip, PORT), timeout=sure):
            return True, None
    except Exception as e:
        return False, str(e)


# ── Makullük ──────────────────────────────────────────────────────────────

def _sayi(v, ond=1):
    if v is None:
        return "—"
    return f"{v:,.{ond}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tam_okuma(ip, birim):
    """Tüm tabloyu bir kez oku, yazdır, değerleri sözlük olarak döndür."""
    print("\n── TEK SEFERLİK TAM OKUMA ─────────────────────────────────────")
    d = {}
    for ad, adres, tip, br in OLCUMLER:
        v, hata = deger_oku(ip, adres, tip, birim)
        d[adres] = v
        if hata:
            print(f"  {ad:<22} [{adres:>3}]  OKUNAMADI — {hata}")
        else:
            gos = v
            br_g = br
            if br == "W" or br == "VA" or br == "var":
                gos, br_g = v / 1000.0, "k" + br
            elif br == "Wh":
                gos, br_g = v / 1000.0, "kWh"
            print(f"  {ad:<22} [{adres:>3}]  {_sayi(gos, 3 if br == '' else 1):>18} {br_g}")

    print("\n── KONTROLLER ─────────────────────────────────────────────────")
    sorun = 0

    def kontrol(ok, metin, ipucu=""):
        nonlocal sorun
        if ok is None:
            print("  [ ? ] " + metin + " — okunamadığı için kontrol edilemedi")
            return
        print(("  [OK ] " if ok else "  [!! ] ") + metin + ("" if ok or not ipucu else "  → " + ipucu))
        if not ok:
            sorun += 1

    f = d.get(55)
    kontrol(None if f is None else 49.0 <= f <= 51.0,
            f"Frekans 49–51 Hz ({_sayi(f, 2)} Hz)",
            "frekans saçma → register haritası bu cihaza uymuyor ya da birim no yanlış")

    pf = d.get(69)
    kontrol(None if pf is None else -1.0001 <= pf <= 1.0001,
            f"Güç faktörü −1..1 ({_sayi(pf, 3)})")

    p = d.get(65)
    faz = [d.get(25), d.get(27), d.get(29)]
    if p is not None and all(x is not None for x in faz):
        top = sum(faz)
        pay = max(2000.0, abs(p) * 0.03)
        kontrol(abs(top - p) <= pay,
                f"Toplam güç = faz güçleri toplamı ({_sayi(p/1000)} kW / {_sayi(top/1000)} kW)",
                "toplam register'ı faz toplamıyla uyuşmuyor")
    else:
        kontrol(None, "Toplam güç = faz güçleri toplamı")

    u = [d.get(7), d.get(9), d.get(11)]
    i_ = [d.get(13), d.get(15), d.get(17)]
    if p is not None and pf not in (None, 0) and all(x is not None for x in u + i_):
        u_ort, i_ort = sum(u) / 3, sum(i_) / 3
        s_hesap = 3 ** 0.5 * u_ort * i_ort           # VA
        s_reg = d.get(63)
        if s_reg:
            kontrol(abs(s_hesap - s_reg) <= max(5000.0, s_reg * 0.05),
                    f"√3·U·I = görünür güç ({_sayi(s_hesap/1000)} kVA / {_sayi(s_reg/1000)} kVA)",
                    "gerilim/akım trafosu oranı cihazda eksik girilmiş olabilir")
        print(f"  [bil] Hat gerilimi ort. {_sayi(u_ort)} V, akım ort. {_sayi(i_ort)} A "
              f"→ ölçüm {'ORTA GERİLİM (OG)' if u_ort > 1000 else 'ALÇAK GERİLİM (AG)'} tarafında")

    if p is not None:
        print(f"  [bil] Toplam etkin güç {_sayi(p/1000)} kW — "
              + ("şebekeden ÇEKİLİYOR" if p >= 0 else "şebekeye VERİLİYOR (eksi)"))
        if abs(p) < 1000:
            print("  [!! ] Güç 1 kW'ın altında: hastane girişi için çok düşük → akım trafosu "
                  "oranı cihazda girilmemiş (sekonder değer) olabilir")
            sorun += 1

    t2 = [d.get(805), d.get(813)]
    if any(x for x in t2 if x):
        print("  [bil] Tarife-2 sayaçlarında enerji var → otomatikte T1 + T2 toplanmalı")
    ver = [d.get(809), d.get(813)]
    if any(x for x in ver if x):
        print("  [bil] VERİLEN sayacında enerji var → şebekeye zaman zaman enerji verilmiş "
              "(ya da akım trafosu ters bağlı: bu durumda GİREN ~0 kalır)")

    print(f"\n  Sonuç: {'SORUN YOK' if sorun == 0 else str(sorun) + ' kontrol başarısız'}")
    return d


# ── Canlı panelden beklenen değer (bilgi) ─────────────────────────────────

def beklenen_sebeke():
    """configs/canli_guc_son.json → (trafo_kw, kojen_kw, kojen_adet, yas_sn) | None."""
    try:
        with open(os.path.join(BURASI, "configs", "canli_guc_son.json"), encoding="utf-8") as f:
            veri = json.load(f)
        t = datetime.fromisoformat(veri["zaman"])
        simdi = datetime.now().astimezone() if t.tzinfo else datetime.now()
        yas = (simdi - t).total_seconds()
        trafo = kojen = 0.0
        tn = kn = 0
        for o in veri.get("olcumler") or []:
            ad, kw = str(o.get("cihaz", "")), o.get("kw")
            if kw is None:
                continue
            if ad.startswith("TRDP-"):
                trafo += kw
                tn += 1
            elif ad.startswith("KOJEN-"):
                kojen += kw
                kn += 1
        if tn == 0:
            return None
        return trafo, kojen, tn, kn, yas
    except Exception:
        return None


# ── Canlı akış ───────────────────────────────────────────────────────────

def canli(ip, birim, periyot):
    dosya = os.path.join(BURASI, "sebeke_deneme_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M"))
    print("\n── CANLI AKIŞ (%d sn arayla, Ctrl+C ile durur) ─────────────────" % periyot)
    print("  Kayıt: " + dosya)
    print("  'sayaç farkı' = iki okuma arası enerji artışı / süre (ortalama güç).")
    print("  Register ile uyuşuyorsa okuma doğru demektir.\n")
    print(f"  {'ZAMAN':<8} | {'GÜÇ reg.65':>12} | {'sayaç farkı':>12} | {'uyum':<6} | "
          f"{'GİREN T1+T2':>15} | {'VERİLEN':>11} | trafo − kojen (panel)")
    print("  " + "-" * 110)

    onceki = None   # (zaman, net_kwh)
    with open(dosya, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["zaman", "guc_reg_kw", "guc_sayac_kw", "giren_kwh", "verilen_kwh",
                    "panel_trafo_kw", "panel_kojen_kw", "hata"])
        try:
            while True:
                bas = time.time()
                p, h1 = deger_oku(ip, 65, "f", birim)
                gir = [deger_oku(ip, a, "d", birim) for a in (801, 805)]
                ver = [deger_oku(ip, a, "d", birim) for a in (809, 813)]
                hatalar = [h for h in [h1] + [x[1] for x in gir + ver] if h]
                giren = (sum(x[0] for x in gir) / 1000.0) if all(x[0] is not None for x in gir) else None
                verilen = (sum(x[0] for x in ver) / 1000.0) if all(x[0] is not None for x in ver) else None

                kw_sayac, uyum = None, ""
                simdi = time.time()
                if giren is not None and verilen is not None:
                    net = giren - verilen
                    if onceki:
                        dt = simdi - onceki[0]
                        if dt > 0:
                            kw_sayac = (net - onceki[1]) * 3600.0 / dt
                    onceki = (simdi, net)
                kw = p / 1000.0 if p is not None else None
                if kw is not None and kw_sayac is not None:
                    # Sayaç kWh çözünürlüğü kısa aralıkta kaba kalır: pay geniş
                    pay = max(30.0, abs(kw) * 0.15)
                    uyum = "uyumlu" if abs(kw - kw_sayac) <= pay else "FARKLI"

                bek = beklenen_sebeke()
                bek_txt = "—"
                if bek:
                    tr, kj, tn, kn, yas = bek
                    bek_txt = (f"{_sayi(tr - kj)} kW  (trafo {tn}/4 {_sayi(tr)}, kojen {kn} sayaç "
                               f"{_sayi(kj)}; {int(yas)} sn önce)")

                print(f"  {datetime.now():%H:%M:%S} | {_sayi(kw):>9} kW | "
                      f"{(_sayi(kw_sayac) + ' kW') if kw_sayac is not None else 'ilk okuma':>12} | "
                      f"{uyum:<6} | {_sayi(giren):>11} kWh | {_sayi(verilen):>7} kWh | {bek_txt}"
                      + (("   HATA: " + hatalar[0]) if hatalar else ""))
                w.writerow([datetime.now().isoformat(timespec="seconds"),
                            "" if kw is None else round(kw, 2),
                            "" if kw_sayac is None else round(kw_sayac, 2),
                            "" if giren is None else round(giren, 3),
                            "" if verilen is None else round(verilen, 3),
                            round(bek[0], 2) if bek else "", round(bek[1], 2) if bek else "",
                            hatalar[0] if hatalar else ""])
                f.flush()
                time.sleep(max(0.0, periyot - (time.time() - bas)))
        except KeyboardInterrupt:
            print("\n  Akış durduruldu. Kayıt: " + dosya)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Şebeke sayacı (PAC3200) deneme okuması — yalnız okur")
    ap.add_argument("--ip", default=VARSAYILAN_IP)
    ap.add_argument("--birim", type=int, default=1, help="Modbus birim no (varsayılan 1)")
    ap.add_argument("--sure", type=int, default=5, help="canlı akış aralığı, sn (varsayılan 5)")
    ap.add_argument("--tek", action="store_true", help="yalnız tek seferlik tam okuma")
    a = ap.parse_args(argv)

    print("=" * 66)
    print(f"  ŞEBEKE SAYACI DENEMESİ — Siemens PAC3200  {a.ip}:{PORT}  birim {a.birim}")
    print(f"  {datetime.now():%d.%m.%Y %H:%M:%S}   (yalnız okur, cihaza yazmaz)")
    print("=" * 66)

    ok, hata = port_acik_mi(a.ip)
    if not ok:
        print(f"\n  [!! ] {a.ip}:{PORT} bağlantısı kurulamadı: {hata}")
        print("       → PC bu ağa (192.168.1.x) erişiyor mu? Aynı ağdaki KOJEN-3 (192.168.1.18)")
        print("         okunuyorsa kablo/IP/cihazın Modbus TCP ayarı kontrol edilmeli.")
        return 2
    print(f"\n  [OK ] {a.ip}:{PORT} açık")

    tam_okuma(a.ip, a.birim)
    if not a.tek:
        canli(a.ip, a.birim, max(1, a.sure))
    return 0


if __name__ == "__main__":
    kod = 1
    try:
        kod = main()
    except Exception as ex:
        print("\nBeklenmeyen hata: %s" % ex)
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        input("\nPencereyi kapatmak için Enter'a basın...")
    sys.exit(kod)
