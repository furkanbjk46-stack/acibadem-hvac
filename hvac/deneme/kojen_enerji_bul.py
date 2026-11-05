# -*- coding: utf-8 -*-
"""KOJEN-1/2 (Janitza UMG 512 PRO) ENERJİ REGISTER'INI BULUR — SAHADA ÇALIŞTIRILIR.

NEDEN: canlı panelde kojenlerin GÜCÜ doğru okunuyor (register 19026), ama
GÜNLÜK kWh için kullanılacak enerji register'ı doğrulanmadı. Yanlış adres
"makul ama yanlış" bir sayı verir; yanlış birim (Wh yerine kWh) ise günlük
tüketimi sessizce 1000 kat küçültür. Bu yüzden adres tahmin edilmez:
cihazın KENDİ ekranındaki sayıyla eşleştirilir.

NASIL ÇALIŞIR
  1. Cihazın web arayüzünü aç:  http://10.70.131.2/soverview.html
     "Quickview" tablosundaki kWh sütununu oku (L1, L2, L3 ve L1..L3).
  2. Bu sayıları aşağıdaki HEDEFLER'e yaz (ya da komut satırından ver).
  3. Betiği lokasyon PC'sinde çalıştır:
         python kojen_enerji_bul.py
     ya da sayıları elle vererek:
         python kojen_enerji_bul.py 10.70.131.2 -10325301 -3202835 -4124357 -2998107
  4. Çıktıdaki "EŞLEŞTİ" satırlarını bana gönder.

Betik YALNIZ OKUR (Modbus fonksiyon 3). Cihaza hiçbir şey yazmaz, sayaç
sıfırlamaz, ayar değiştirmez.
"""
import socket
import struct
import sys

PORT = 502
ZAMAN_ASIMI = 3.0

# Cihazın Quickview ekranından okunan kWh değerleri (05.11.2026, KOJEN-1).
# Sayaç ilerlediği için eşleşme YÜZDE ile aranır (bkz. TOLERANS).
VARSAYILAN_IP = "10.70.131.2"
HEDEFLER = [
    ("L1..L3 kWh", -10325301.0),
    ("L1 kWh",      -3202835.0),
    ("L2 kWh",      -4124357.0),
    ("L3 kWh",      -2998107.0),
]

# Enerji sayacı günde ~%0,2 ilerliyor; ekran görüntüsü ile betik arasında
# saatler geçmiş olabilir. %0,5 bandı hem bunu tolere eder hem de 7 haneli
# bir sayıda yanlış eşleşmeye yer bırakmaz.
TOLERANS = 0.005

# Janitza UMG 5xx ölçüm değerleri float bloğu. Adres TAHMİN EDİLMEZ: blok
# baştan sona taranır, hangi adres cihazın kendi sayısını veriyorsa o bulunur.
BLOKLAR = [(19000, 250), (19250, 250)]

# Register ham değeri ile ekrandaki kWh arasındaki olası birim farkları
OLCEKLER = [("kWh (register doğrudan kWh)", 1.0),
            ("Wh  (register Wh, /1000)", 0.001),
            ("MWh (register MWh, x1000)", 1000.0)]


def _istek(s, adres, adet):
    """Modbus TCP fonksiyon 3. Hata/olumsuz yanıt → None."""
    try:
        s.send(struct.pack(">HHHBBHH", 1, 0, 6, 1, 3, int(adres), int(adet)))
        yanit = s.recv(4096)
    except Exception:
        return None
    if len(yanit) < 9 or yanit[7] != 3:
        return None                      # exception yanıtı (adres yok vb.)
    bayt = yanit[8]
    govde = yanit[9:9 + bayt]
    return govde if len(govde) == bayt == adet * 2 else None


def blok_oku(ip, adres, adet):
    """Bloğu okur; cihaz büyük isteği reddederse 20'şer registera böler."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(ZAMAN_ASIMI)
        s.connect((ip, PORT))
        tam = _istek(s, adres, adet)
        if tam is not None:
            return tam
        parcalar = []
        for off in range(0, adet, 20):
            n = min(20, adet - off)
            p = _istek(s, adres + off, n)
            if p is None:
                break                    # haritalanmamış bölge: buraya kadar
            parcalar.append(p)
        return b"".join(parcalar) if parcalar else None
    except Exception as e:
        print("  ! %s:%d bağlanamadı (%s)" % (ip, PORT, e))
        return None
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


def _uyar(a, b):
    """İki sayı TOLERANS bandında mı (işaret farkı önemsiz)."""
    a, b = abs(float(a)), abs(float(b))
    if b == 0:
        return a == 0
    return abs(a - b) / b <= TOLERANS


def cozumle(ham, taban):
    """Blokta her offseti float32 ve float64 olarak çözer → [(adres, tip, deger)]."""
    sonuc = []
    toplam = len(ham) // 2
    for i in range(toplam - 1):
        try:
            sonuc.append((taban + i, "float32", struct.unpack(">f", ham[i * 2:i * 2 + 4])[0]))
        except Exception:
            pass
    for i in range(toplam - 3):
        try:
            sonuc.append((taban + i, "float64", struct.unpack(">d", ham[i * 2:i * 2 + 8])[0]))
        except Exception:
            pass
    return sonuc


def tara(ip, hedefler):
    print("=" * 72)
    print("CIHAZ: %s" % ip)
    print("=" * 72)
    bulundu = []
    for taban, adet in BLOKLAR:
        ham = blok_oku(ip, taban, adet)
        if not ham:
            print("  %d-%d: okunamadı (bu blok cihazda olmayabilir)" % (taban, taban + adet - 1))
            continue
        okunan = len(ham) // 2
        print("  %d-%d: %d register okundu" % (taban, taban + okunan - 1, okunan))
        for adres, tip, deger in cozumle(ham, taban):
            if deger != deger or abs(deger) in (float("inf"),):   # NaN / sonsuz
                continue
            for ad, hedef in hedefler:
                for olcek_ad, olcek in OLCEKLER:
                    if _uyar(deger * olcek, hedef):
                        isaret = "EKSİ" if deger < 0 else "artı"
                        bulundu.append((adres, tip, deger, ad, olcek_ad, isaret))
                        print("    EŞLEŞTİ  register %-6d (0x%04X)  %-8s  ham=%.3f  "
                              "→ %s  [%s]  işaret=%s"
                              % (adres, adres, tip, deger, ad, olcek_ad, isaret))
    if not bulundu:
        print("  Eşleşme YOK. Quickview'daki kWh sayıları güncel mi? "
              "Değilse sayıları komut satırından ver.")
    return bulundu


def main(argv):
    ip = argv[1] if len(argv) > 1 else VARSAYILAN_IP
    hedefler = HEDEFLER
    if len(argv) > 2:
        adlar = ["L1..L3 kWh", "L1 kWh", "L2 kWh", "L3 kWh"]
        hedefler = [(adlar[i], float(v)) for i, v in enumerate(argv[2:2 + 4])]
    print("Hedef sayılar (cihazın kendi ekranından):")
    for ad, v in hedefler:
        print("  %-12s %.0f" % (ad, v))
    print()
    bulundu = tara(ip, hedefler)
    print()
    if bulundu:
        print("SONUÇ: yukarıdaki EŞLEŞTİ satırlarını olduğu gibi gönder.")
        print("Günlük kWh için L1..L3 toplamını veren adres kullanılacak;")
        print("işaret EKSİ ise günlük fark da eksi çıkar, kod buna göre düzeltilir.")
    return 0 if bulundu else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
