# -*- coding: utf-8 -*-
"""bacnet_writer testleri — GERCEK UDP, SAHTE CIHAZ, SAHAYA HICBIR PAKET GITMEZ.

    python hvac/deneme/test_bacnet_writer.py

Bilgisayarin icinde (127.0.0.1) calisan kucuk bir BACnet cihaz taklidi
kurulur; bacnet_writer ona gercek soketlerle yazar/okur. Boylece paket
olusturma, cevap cozme, invoke id, zaman asimi ve geri okuma mantigi
ag kosullarina en yakin sekilde sinanir.

NEDEN VAR: Sahadan sikayet "log gonderildi diyor ama set degismiyor".
Eski ayristirici 7 senaryonun 5'inde yanlis karar veriyordu: cevap hic
gelmese de, anlasilmayan cevapta da, router cevabindaki MAC bayti 0x20
oldugunda gercek cevap HATA iken de "basarili" diyordu.
"""
import json
import os
import re
import socket
import struct
import sys
import threading
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging
logging.disable(logging.CRITICAL)
import bacnet_writer as bw

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ════════════════════════════════════════════════════════════════════════
# SAHTE BACNET CIHAZI
# ════════════════════════════════════════════════════════════════════════
class SahteCihaz:
    """Router arkasindaki bir cihazi taklit eder (cevaplar SNET/SADR ile gelir)."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.degerler = {}          # (tip, inst) -> float
        self.mod = {}               # (tip, inst) -> mod adi
        self.override = {}          # (tip, inst) -> sabit kalan deger
        self.okuma_tipi = {}        # (tip, inst) -> "real" | "double" | "unsigned"
        self.istekler = []          # (npdu_control, servis, (tip,inst), deger, priority)
        self.sadr = bytes([0x01, 0x1F])
        self.snet = 2
        self._dur = False
        threading.Thread(target=self._dongu, daemon=True).start()

    # ── cevap paketleri ──
    def _paket(self, apdu, sadr=None, snet=None):
        sadr = self.sadr if sadr is None else sadr
        snet = self.snet if snet is None else snet
        npdu = struct.pack(">BBH B", 0x01, 0x08, snet, len(sadr)) + sadr
        govde = npdu + apdu
        return bytes([0x81, 0x0a]) + struct.pack(">H", 4 + len(govde)) + govde

    def _dongu(self):
        while not self._dur:
            try:
                data, adres = self.sock.recvfrom(1500)
            except OSError:
                return
            try:
                self._isle(data, adres)
            except Exception as e:  # test cihazı çökmesin
                print("SAHTE CIHAZ HATASI:", e)

    def _isle(self, data, adres):
        i = 4
        ctrl = data[i + 1]
        i += 2
        if ctrl & 0x20:
            i += 3 + data[i + 2]
            i += 1                      # hop count
        apdu = data[i:]
        inv, servis = apdu[2], apdu[3]
        obj_id = struct.unpack(">I", apdu[5:9])[0]
        anahtar = (obj_id >> 22, obj_id & 0x3FFFFF)
        deger = priority = None
        if servis == 0x0F:
            j = apdu.index(0x3E, 9)
            deger = struct.unpack(">f", apdu[j + 2:j + 6])[0]
            if len(apdu) > j + 7 and apdu[j + 7] == 0x49:
                priority = apdu[j + 8]
        self.istekler.append((ctrl, servis, anahtar, deger, priority))
        mod = self.mod.get(anahtar, "normal")

        if mod == "sessiz":
            return
        if mod == "error":
            self.sock.sendto(self._paket(bytes([0x50, inv, servis, 0x91, 0x02, 0x91, 40])), adres)
            return
        if mod == "mac20_error":
            self.sock.sendto(self._paket(bytes([0x50, inv, servis, 0x91, 0x02, 0x91, 40]),
                                         sadr=bytes([0x20])), adres)
            return
        if mod == "snet2001_reject":
            self.sock.sendto(self._paket(bytes([0x60, inv, 0x03]), snet=0x2001), adres)
            return
        if mod == "anlamsiz":
            self.sock.sendto(self._paket(bytes([0x99, 0x99])), adres)
            return
        if mod == "yalniz_yanlis_invoke":
            self.sock.sendto(self._paket(bytes([0x20, (inv + 1) & 0xFF, servis])), adres)
            return
        if mod == "once_gec_ack":
            # Önce BAŞKA isteğe ait geç bir cevap, sonra doğrusu
            self.sock.sendto(self._paket(bytes([0x50, (inv + 7) & 0xFF, servis,
                                                0x91, 0x02, 0x91, 40])), adres)
        if mod == "once_ag_mesaji":
            ag = bytes([0x81, 0x0a, 0x00, 0x09, 0x01, 0x80, 0x01, 0x00, 0x02])
            self.sock.sendto(ag, adres)

        if servis == 0x0F:
            if anahtar in self.override:
                self.degerler[anahtar] = self.override[anahtar]   # öncelik ezildi
            else:
                self.degerler[anahtar] = deger
            self.sock.sendto(self._paket(bytes([0x20, inv, 0x0F])), adres)
        elif servis == 0x0C:
            if anahtar not in self.degerler:
                self.sock.sendto(self._paket(bytes([0x50, inv, 0x0C, 0x91, 0x01, 0x91, 31])), adres)
                return
            v = self.degerler[anahtar]
            tip = self.okuma_tipi.get(anahtar, "real")
            if tip == "double":
                deger_bayt = bytes([0x55, 0x08]) + struct.pack(">d", v)
            elif tip == "unsigned":
                deger_bayt = bytes([0x21, int(v) & 0xFF])
            else:
                deger_bayt = bytes([0x44]) + struct.pack(">f", v)
            apdu = (bytes([0x30, inv, 0x0C, 0x0C]) + struct.pack(">I", obj_id)
                    + bytes([0x19, 85, 0x3E]) + deger_bayt + bytes([0x3F]))
            self.sock.sendto(self._paket(apdu), adres)

    def kapat(self):
        self._dur = True
        self.sock.close()


cihaz = SahteCihaz()
bw.BACNET_PORT = cihaz.port
bw.YANIT_TIMEOUT = 0.6
bw.OKUMA_TIMEOUT = 0.6
bw.DOGRULAMA_BEKLEME = 0.05

GW = "127.0.0.1"


def nokta(inst, tip=2):
    return {"gateway_ip": GW, "dnet": 2, "mac_hex": "011F", "obj_type": tip, "obj_inst": inst}


def yaz(inst, deger=6.5, tip=2):
    return bw.bacnet_yaz(GW, 2, "011F", tip, inst, deger)


# ── 1) Normal yazma / okuma ──────────────────────────────────────────────
ok, msg = yaz(1, 6.5)
c("normal yazma basarili", ok, msg)
c("gonderilen NPDU'da 'expecting reply' biti var (0x04)",
  bool(cihaz.istekler[-1][0] & 0x04), hex(cihaz.istekler[-1][0]))
c("gonderilen NPDU'da DNET biti var (0x20)", bool(cihaz.istekler[-1][0] & 0x20))
c("priority 8 gonderildi", cihaz.istekler[-1][4] == 8, cihaz.istekler[-1][4])
c("cihaz dogru degeri aldi", abs(cihaz.degerler[(2, 1)] - 6.5) < 1e-6, cihaz.degerler.get((2, 1)))
ok, val = bw.bacnet_oku(GW, 2, "011F", 2, 1)
c("okuma REAL degeri doner", ok and abs(val - 6.5) < 1e-6, (ok, val))

cihaz.degerler[(2, 50)] = 7.25
cihaz.okuma_tipi[(2, 50)] = "double"
ok, val = bw.bacnet_oku(GW, 2, "011F", 2, 50)
c("okuma DOUBLE degeri cozer", ok and abs(val - 7.25) < 1e-9, (ok, val))
cihaz.degerler[(3, 51)] = 1
cihaz.okuma_tipi[(3, 51)] = "unsigned"
ok, val = bw.bacnet_oku(GW, 2, "011F", 3, 51)
c("okuma UNSIGNED degeri cozer", ok and val == 1.0, (ok, val))

ok, val = bw.bacnet_oku(GW, 2, "011F", 2, 999)
c("olmayan nesne okumasi BASARISIZ ve sebep yazar", (not ok) and "unknown-object" in str(val), (ok, val))

# ── 2) ESKI AYRISTIRICININ YANLIS KARAR VERDIGI SENARYOLAR ───────────────
cihaz.mod[(2, 2)] = "sessiz"
ok, msg = yaz(2)
c("[regresyon] cevap hic gelmezse BASARISIZ", not ok, msg)
c("[regresyon] zaman asimi sebebi yazilir", "Cevap yok" in msg, msg)

cihaz.mod[(2, 3)] = "anlamsiz"
ok, msg = yaz(3)
c("[regresyon] anlasilamayan cevap BASARISIZ", not ok, msg)

cihaz.mod[(2, 4)] = "mac20_error"
ok, msg = yaz(4)
c("[regresyon] router MAC=0x20 + gercek ERROR -> BASARISIZ", not ok, msg)
c("[regresyon] hata sinifi/kodu cozulur", "write-access-denied" in msg, msg)

cihaz.mod[(2, 5)] = "snet2001_reject"
ok, msg = yaz(5)
c("[regresyon] SNET=0x2001 + gercek REJECT -> BASARISIZ", not ok and "Reject" in msg, msg)

cihaz.mod[(2, 6)] = "yalniz_yanlis_invoke"
ok, msg = yaz(6)
c("[regresyon] baska istege ait ACK kabul EDILMEZ", not ok, msg)

cihaz.mod[(2, 7)] = "once_gec_ack"
ok, msg = yaz(7)
c("geç gelen yabanci cevap atlanir, dogru ACK beklenir", ok, msg)

cihaz.mod[(2, 8)] = "once_ag_mesaji"
ok, msg = yaz(8)
c("ag katmani mesaji atlanir, dogru ACK beklenir", ok, msg)

# Not: 90 kullanılır — 9 numarası aşağıda CH1_REM_SET olarak normal yazılıyor;
# burada hata moduna alınırsa sonraki senaryoları da bozar.
cihaz.mod[(2, 90)] = "error"
ok, msg = yaz(90)
c("dogrudan ERROR -> BASARISIZ", not ok, msg)

ok, msg = bw.bacnet_yaz("127.0.0.1", 2, "ZZ", 2, 1, 6.5)
c("bozuk MAC adresi paket olusturmada yakalanir", not ok and "Paket" in msg, msg)

# ── 3) YAZ + GERI OKU ────────────────────────────────────────────────────
cihaz.mod.pop((2, 2), None)
cihaz.override[(2, 21)] = 7.5                   # daha yüksek öncelik: değer değişmez
cihaz.mod[(2, 22)] = "sessiz"                   # yazma cevapsız
# (2, 23): yazma kabul, okuma cevapsız — okuma isteğinde sessizleşen özel mod
_eski_isle = cihaz._isle


def _isle_23(data, adres):
    i = 4 + 2 + 3 + data[4 + 2 + 2] + 1
    apdu = data[i:]
    obj = struct.unpack(">I", apdu[5:9])[0]
    if apdu[3] == 0x0C and (obj & 0x3FFFFF) == 23:
        return                                   # okumaya cevap yok
    return _eski_isle(data, adres)


cihaz._isle = _isle_23

isler = [("A", nokta(20), 6.5), ("B", nokta(21), 6.5), ("C", nokta(22), 6.5), ("D", nokta(23), 6.5)]
sonuc = bw.yaz_dogrula_toplu(isler)
c("[dogrula] normal nokta 'oturdu'", sonuc["A"]["durum"] == "oturdu", sonuc["A"])
c("[dogrula] oturdu mesaji okunan degeri yazar", "6.5" in sonuc["A"]["mesaj"], sonuc["A"]["mesaj"])
c("[dogrula] oncelik ezilen nokta 'sahada_farkli' (ACK geldigi halde)",
  sonuc["B"]["durum"] == "sahada_farkli" and sonuc["B"]["yazma_ok"], sonuc["B"])
c("[dogrula] farkli mesaji cihazdaki degeri yazar", "7.5" in sonuc["B"]["mesaj"], sonuc["B"]["mesaj"])
c("[dogrula] cevapsiz yazma 'yazma_hatasi'", sonuc["C"]["durum"] == "yazma_hatasi", sonuc["C"])
c("[dogrula] okunamayan nokta 'dogrulanamadi'", sonuc["D"]["durum"] == "dogrulanamadi", sonuc["D"])
cihaz._isle = _eski_isle

# IC SET: yazılan REM, okunan ayrı nesne
cihaz.degerler[(1, 27)] = 7.5                   # chiller hâlâ eski set
sonuc = bw.yaz_dogrula_toplu([("CH1", nokta(9), 6.5)], {"CH1": nokta(27, tip=1)})
c("[dogrula] IC SET ayri nesneden okunur", sonuc["CH1"]["ic_okunan"] == 7.5, sonuc["CH1"])
c("[dogrula] IC farki REM dogrulamasini BOZMAZ (chiller gecikmeli uygular)",
  sonuc["CH1"]["durum"] == "oturdu", sonuc["CH1"]["durum"])

# ── 4) KOMUT OMRU ────────────────────────────────────────────────────────
simdi = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)
doldu, yas = bw.komut_suresi_doldu("2026-09-11T07:55:00+00:00", simdi)
c("[omur] 5 dk'lik komut taze", not doldu and abs(yas - 5) < 0.01, (doldu, yas))
doldu, yas = bw.komut_suresi_doldu("2026-09-11T07:15:00+00:00", simdi)
c("[omur] 45 dk'lik komut suresi dolmus", doldu, (doldu, yas))
doldu, _ = bw.komut_suresi_doldu("2026-07-07T15:11:13.123456+00:00", simdi)
c("[omur] 65 gunluk komut (Altunizade senaryosu) uygulanmaz", doldu)
doldu, _ = bw.komut_suresi_doldu("2026-09-11T08:04:00Z", simdi)
c("[omur] PC saati geride (negatif yas) -> taze", not doldu)
doldu, yas = bw.komut_suresi_doldu("bozuk", simdi)
c("[omur] okunamayan tarih komutu DUSURMEZ", (not doldu) and yas is None)
doldu, _ = bw.komut_suresi_doldu("2026-09-11T07:00:00", simdi)
c("[omur] saat dilimsiz tarih UTC kabul edilir", doldu)

# ── 5) komutlari_isle UCTAN UCA (sahte Supabase + sahte cihaz) ───────────
db_komutlar = [
    {"id": "k1", "nokta_adi": "CH1_REM_SET", "hedef_deger": 6.5,
     "created_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
    {"id": "k2", "nokta_adi": "CH2_REM_SET", "hedef_deger": 6.5,
     "created_at": (datetime.now(timezone.utc) - timedelta(days=65)).isoformat()},
    {"id": "k3", "nokta_adi": "YOK_BOYLE_NOKTA", "hedef_deger": 6.5,
     "created_at": datetime.now(timezone.utc).isoformat()},
    {"id": "k4", "nokta_adi": "CH3_REM_SET", "hedef_deger": 3.0,
     "created_at": datetime.now(timezone.utc).isoformat()},
    {"id": "k5", "nokta_adi": "ZON1_KLIMA_SANTRALI_SET", "hedef_deger": 22.0,
     "created_at": datetime.now(timezone.utc).isoformat()},
]
db_noktalar = [dict(nokta(9), nokta_adi="CH1_REM_SET"),
               dict(nokta(11), nokta_adi="CH2_REM_SET"),
               dict(nokta(13), nokta_adi="CH3_REM_SET"),
               dict(nokta(15), nokta_adi="ZON1_KLIMA_SANTRALI_SET")]
cihaz.override[(2, 15)] = 21.0                 # zon-1: BMS başka değerde tutuyor
cihaz.degerler[(1, 27)] = 6.5
guncellenen = {}


def _sb_get(url, key, yol):
    return db_komutlar if "/komutlar" in yol else db_noktalar


def _sb_patch(url, key, yol, veri):
    guncellenen[yol.split("id=eq.")[1]] = veri


_orj = (bw._sb_get, bw._sb_patch, bw.geri_okuma_haritasi)
bw._sb_get, bw._sb_patch = _sb_get, _sb_patch
bw.geri_okuma_haritasi = lambda lok: {"CH1_REM_SET": nokta(27, tip=1)}
_istek_once = len(cihaz.istekler)
try:
    bw.komutlari_isle("https://sahte", "anahtar", "maslak")
finally:
    bw._sb_get, bw._sb_patch, bw.geri_okuma_haritasi = _orj

c("[uctan uca] gecerli komut 'tamamlandi'", guncellenen.get("k1", {}).get("durum") == "tamamlandi",
  guncellenen.get("k1"))
c("[uctan uca] tamamlandi mesaji cihazda dogrulandigini soyler",
  "doğrulandı" in guncellenen.get("k1", {}).get("hata_mesaji", ""), guncellenen.get("k1"))
c("[uctan uca] IC SET bilgisi mesajda", "IC SET: 6.5" in guncellenen.get("k1", {}).get("hata_mesaji", ""),
  guncellenen.get("k1"))
c("[uctan uca] 65 gunluk komut 'suresi_doldu'", guncellenen.get("k2", {}).get("durum") == "suresi_doldu",
  guncellenen.get("k2"))
_yazilan_instler = [a[2][1] for a in cihaz.istekler[_istek_once:] if a[1] == 0x0F]
c("[uctan uca] suresi dolan komut sahaya YAZILMADI", 11 not in _yazilan_instler, _yazilan_instler)
c("[uctan uca] tanimsiz nokta 'hata'", guncellenen.get("k3", {}).get("durum") == "hata")
c("[uctan uca] aralik disi (3 C) 'hata' ve sahaya gitmedi",
  guncellenen.get("k4", {}).get("durum") == "hata" and 13 not in _yazilan_instler,
  (guncellenen.get("k4"), _yazilan_instler))
c("[uctan uca] BMS'in ezdigi nokta 'hata' (eskiden 'tamamlandi' idi)",
  guncellenen.get("k5", {}).get("durum") == "hata", guncellenen.get("k5"))
c("[uctan uca] ezilme mesaji cihazdaki degeri yazar",
  "21.0" in guncellenen.get("k5", {}).get("hata_mesaji", ""), guncellenen.get("k5"))
_ea = guncellenen.get("k1", {}).get("executed_at", "")
c("[uctan uca] executed_at saat dilimi iceriyor (UTC)", _ea.endswith("+00:00"), _ea)

# ── 6) Ekran siniri = lokasyon guvenlik kapisi ──────────────────────────
_mk = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "merkez", "app_merkez.py")
_metin = open(_mk, encoding="utf-8").read()
_m = re.search(r'"Hedef Değer \(°C\)",\s*min_value=([\d.]+),\s*max_value=([\d.]+)', _metin)
c("Uzaktan Kontrol giris alani bulundu", bool(_m))
if _m:
    c("ekran alt siniri = KOMUT_DEGER_MIN", float(_m.group(1)) == bw.KOMUT_DEGER_MIN, _m.group(1))
    c("ekran ust siniri = KOMUT_DEGER_MAX", float(_m.group(2)) == bw.KOMUT_DEGER_MAX, _m.group(2))
for _d in ("dogrulanamadi", "suresi_doldu"):
    c(f"ekran '{_d}' durumunu taniyor", f'"{_d}"' in _metin)

# ── 7) Geri okuma haritasi (configs/geri_okuma.json) ────────────────────
_yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", "geri_okuma.json")
try:
    _h = json.load(open(_yol, encoding="utf-8"))
    c("geri_okuma.json gecerli JSON", True)
except Exception as e:
    _h = {}
    c("geri_okuma.json gecerli JSON", False, str(e))
import oto_set
_m = _h.get("maslak", {})
c("maslak'ta 5 chiller icin IC SET tanimli", set(_m) == set(oto_set.CH_NOKTALAR), sorted(_m))
_alan = ("gateway_ip", "dnet", "mac_hex", "obj_type", "obj_inst")
c("her harita kaydi eksiksiz", all(all(a in v for a in _alan) for v in _m.values()))
c("IC SET okuma noktalari REM SET'lerden FARKLI nesne",
  all(v["obj_inst"] not in (6, 7, 9, 11, 13) or v["obj_type"] != 2 for v in _m.values()))
c("haritasi olmayan lokasyon bos sozluk alir", bw.geri_okuma_haritasi("yok_boyle") == {})
c("maslak haritasi dosyadan okunur", len(bw.geri_okuma_haritasi("maslak")) == 5)

cihaz.kapat()

# ════════════════════════════════════════════════════════════════════════
gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
