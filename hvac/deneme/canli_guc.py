# -*- coding: utf-8 -*-
"""CANLI GÜÇ OKUMASI — TRDP trafolarının anlık kW değeri.

NEDEN: Lokasyon detayında bugün yalnızca dönem toplamı (kWh) var; sahada o
an ne çekildiği görünmüyor. Günlük sayaç okuması (data_collector.modbus_thread)
günde BİR kez çalışır — canlı izleme için uygun değildir.

── İKİ YÖNTEM, BİRBİRİNİ DENETLER ────────────────────────────────────────
Analizörden anlık gücü okumanın iki yolu var:

  1) GÜÇ REGISTER'I — cihazın kendi bildirdiği toplam etkin güç (W).
     Gerçek anlık değerdir. Adresler üretici kılavuzlarından alındı (aşağıda
     VARSAYILAN_AYAR'da kaynağıyla yazılı), ama saha her zaman kâğıda
     uymaz: başka model takılabilir, akım trafosu oranı yanlış girilmiş
     olabilir, tek faz okunuyor olabilir. Böyle bir durumda değer "makul
     ama yanlış" görünür ve gözle ayırt edilemez.

  2) SAYAÇ FARKI — kWh sayacının iki okuma arasındaki artışı / geçen süre.
     Anlık değil, aradaki sürenin ORTALAMASIDIR; buna karşılık kaynağı
     üretimde yıllardır kullanılan, doğruluğu bilinen sayaçtır.

Bu yüzden ikisi de hesaplanır ve KARŞILAŞTIRILIR. Uyuşuyorsa register
değeri gösterilir (gerçek anlık). Uyuşmuyorsa register'a güvenilmez, sayaç
farkı gösterilir ve "yöntem" alanı bunu söyler. Böylece yanlış bir register
adresi sessizce yanlış kW üretemez — en kötü ihtimalle ortalamaya düşeriz.

── SAHAYA ETKİSİ ─────────────────────────────────────────────────────────
  · Yalnızca OKUR. Hiçbir cihaza yazmaz.
  · Günlük tüketim referansına (modbus_daily_ref.json) ve günlük okuma
    CSV'sine DOKUNMAZ — günlük hesap bu okumalardan etkilenmez.
  · Okuma data_collector sürecinde, günlük okumayla AYNI kilit altında
    yapılır; iki okuma aynı sayaca aynı anda gitmez.
"""
import json
import logging
import os
import socket
import struct
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

BURASI = os.path.dirname(os.path.abspath(__file__))
AYAR_DOSYA = os.path.join(BURASI, "configs", "canli_guc_ayar.json")
SONUC_DOSYA = os.path.join(BURASI, "configs", "canli_guc_son.json")

MODBUS_PORT = 502
OKUMA_TIMEOUT = 2.0          # günlük okumadan kısa: canlı turu geciktirmesin

# Hangi cihazlar canlı okunuyor.
#   20.10.2026: yalnız trafolar (TRDP) ile başlandı.
#   21.10.2026: sahanın TAMAMI — 27 analizör. Önce okumalar paralelleştirildi
#               ve arızalı cihaz geçici atlanır hale getirildi; yoksa cevap
#               vermeyen birkaç sayaç 15 saniyelik turu tek başına yerdi.
# Boş liste = data_collector.ANALYZERS'ın tamamı. Daraltmak için ayar
# dosyasına ön ek yazılır (ör. ["TRDP-"]) — kod değişmeden.
CIHAZ_ONEKLERI = []

VARSAYILAN_AYAR = {
    "periyot_sn": 15,          # kaç saniyede bir güç okunsun
    "es_zamanli": 8,           # aynı anda kaç sayaç okunsun (0/1 = sırayla)
    "ariza_esigi": 3,          # kaç ardışık hatadan sonra cihaz geçici atlanır
    "ariza_bekleme_tur": 10,   # atlanan cihaz kaç tur sonra tekrar denenir
    "sayac_her_n_tur": 8,      # kaç turda bir kWh ile çapraz denetim (8×15 = 2 dk)
    "tolerans_oran": 0.12,     # register ile sayaç farkı: %12'ye kadar uyumlu sayılır
    "tolerans_kw": 15.0,       # küçük yüklerde oran anlamsız, mutlak pay
    "makul_alt_kw": -50.0,     # şebekeye verme ihtimaline karşı negatife biraz pay
    "makul_ust_kw": 5000.0,    # bir trafodan beklenebilecek üst sınır
    # Toplam etkin güç register adresi (W, float32, 2 register).
    # ÜRETİCİ KILAVUZLARINDAN ALINDI (20.10.2026) — tahmin değildir:
    #   janitza 19026 → "_G_P_SUM3  W  Sum; Psum3=P1+P2+P3"  (UMG float tablosu;
    #                   aynı tabloda 19060 = "Real energy L1..L3", yani
    #                   data_collector'ın yıllardır okuduğu kWh adresi — harita
    #                   bu cihazlarla birebir tutuyor)
    #   siemens 65    → "Aktif güç toplamı  Float  W"  (SENTRON PAC3200 cihaz
    #                   kitabı, Modbus ölçüm büyüklükleri tablosu; aynı belgede
    #                   801 = "Aktif enerji Giren Tarife 1  Double  Wh", yine
    #                   kodun okuduğu adres. PAC4200 bu temel ölçümlerde
    #                   PAC3200 ile aynı haritayı kullanır.)
    # Sahada farklı model çıkarsa GUC: komutuyla denenir ve BURADAN düzeltilir
    # — kod değişmeden.
    "guc_register": {"janitza": 19026, "siemens": 65},
    # Boş = tüm analizörler. Daraltmak için ör. ["TRDP-"].
    "cihaz_onekleri": [],
}


def ayar_oku() -> dict:
    """configs/canli_guc_ayar.json — yoksa varsayılan. Eksik alan tamamlanır."""
    a = dict(VARSAYILAN_AYAR)
    try:
        with open(AYAR_DOSYA, encoding="utf-8") as f:
            kullanici = json.load(f)
        for k, v in (kullanici or {}).items():
            if k == "guc_register" and isinstance(v, dict):
                reg = dict(VARSAYILAN_AYAR["guc_register"])
                reg.update(v)
                a[k] = reg
            elif k in a:
                a[k] = v
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("canli_guc_ayar.json okunamadı (%s) — varsayılan kullanılıyor", e)
    return a


# ── Modbus (data_collector ile aynı yaklaşım: ham TCP, kütüphanesiz) ──────

def _istek_paketi(adres: int, adet: int = 2, birim: int = 1) -> bytes:
    """Modbus TCP 'read holding registers' isteği."""
    return struct.pack(">HHHBBHH", 1, 0, 6, birim, 3, int(adres), int(adet))


def _float_oku(ip: str, adres: int, timeout: float = OKUMA_TIMEOUT):
    """Tek bir float32 register çiftini oku (W). Hata → None."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, MODBUS_PORT))
        s.send(_istek_paketi(adres, 2))
        resp = s.recv(256)
        if len(resp) >= 13 and resp[7] == 3:
            return struct.unpack(">f", resp[9:13])[0]
        # Modbus istisna yanıtı (fonksiyon kodu | 0x80): adres yok / izin yok
        return None
    except Exception:
        return None
    finally:
        try:
            if s:
                s.close()
        except Exception:
            pass


# ÜRETİM sayaçları (kojen, "uretim": True) — 27.10.2026
# Jeneratör çıkışındaki analizörde akım trafosunun yönü sahada doğrulanmadı:
# ters bağlıysa güç NEGATİF okunur. Yön varsayılmaz: güç mutlak değerle alınır.
# Enerji tarafı (Giren + Verilen) data_collector.modbus_get_kwh'de — günlük
# okuma ile canlı çapraz denetim AYNI okuyucuyu kullanır.


def guc_oku(dev: dict, ayar: dict = None, adres: int = None):
    """Cihazın toplam etkin gücünü kW olarak oku. Hata → None."""
    ayar = ayar or ayar_oku()
    if adres is None:
        adres = (ayar.get("guc_register") or {}).get(dev.get("brand"))
    if adres is None:
        return None
    w = _float_oku(dev["ip"], int(adres))
    if w is None:
        return None
    if dev.get("uretim"):
        w = abs(w)                       # üretim: yön bağlantıya göre işaretli gelebilir
    return round(w / 1000.0, 2)          # W → kW


def cihazlar(ayar: dict = None) -> list:
    """Canlı okunacak cihazlar — TEK KAYNAK data_collector.ANALYZERS.

    Ayrı bir liste tutulmaz: sahada bir sayaç eklenip ANALYZERS'a
    yazıldığında canlı panel de kendiliğinden onu gösterir.
    """
    onekler = (ayar or {}).get("cihaz_onekleri", CIHAZ_ONEKLERI) or []
    try:
        import data_collector as dc
        liste = list(dc.ANALYZERS)
    except Exception as e:
        logger.warning("Analizör listesi okunamadı: %s", e)
        return []
    if onekler:
        liste = [d for d in liste
                 if any(str(d.get("name", "")).startswith(o) for o in onekler)]
    return liste


def _sayac_oku(dev: dict):
    """kWh sayacı — ÜRETİMDEKİ okuyucuyla (tek kaynak; üretim sayacında
    Giren + Verilen toplamı, data_collector.URETIM_ENERJI_REG)."""
    try:
        import data_collector as dc
        return dc.modbus_get_kwh(dev)
    except Exception:
        return None


# ── Ölçüm turu ────────────────────────────────────────────────────────────

class Olcer:
    """Turları yürütür ve sayaç geçmişini tutar (çapraz denetim için).

    OKUMA PARALEL, KARAR TEK İPLİK: cihazlardan okuma iş parçacığı havuzunda
    yapılır (27 sayaç sırayla okunursa cevap vermeyen tek cihaz bütün turu
    geciktirir), ama hangi değerin gösterileceğine ana iplik karar verir.
    Böylece sayaç geçmişi ve doğrulama damgası yarış koşuluna girmez.
    """

    def __init__(self, ayar: dict = None, kilit_al=None):
        self.ayar = ayar or ayar_oku()
        # kilit_al(dev) → o cihazın kilidi. Günlük okumayla çakışmayı önler;
        # cihaz bazında olduğu için farklı sayaçlar birbirini beklemez.
        self.kilit_al = kilit_al
        self.tur_no = 0
        self._sayac = {}                   # cihaz → (kwh, zaman)
        self._son_karar = {}               # cihaz → {"yontem": ...} (doğrulama damgası)
        self._hata = {}                    # cihaz → ardışık hata sayısı
        self._atla = {}                    # cihaz → kaç tur daha atlanacak

    def _oku_tek(self, dev, sayac_turu):
        """TEK cihazdan okuma (havuzda çalışır, ortak duruma DOKUNMAZ)."""
        kilit = self.kilit_al(dev) if self.kilit_al else None
        if kilit is not None:
            kilit.acquire()
        try:
            kw_reg = guc_oku(dev, self.ayar)
            kwh = _sayac_oku(dev) if sayac_turu else None
        finally:
            if kilit is not None:
                kilit.release()
        return kw_reg, kwh

    def _makul(self, kw) -> bool:
        return (kw is not None
                and self.ayar["makul_alt_kw"] <= kw <= self.ayar["makul_ust_kw"])

    def _sayac_gucu(self, ad: str, kwh, simdi: float):
        """Sayaç farkından ortalama kW. İlk okumada / geriye saymada None."""
        onceki = self._sayac.get(ad)
        if kwh is None:
            # Okunamayan tur geçmişi SİLMEZ ve boş değer saklanmaz. 31.10.2026:
            # (None, zaman) saklanıyordu; sonraki turda "kwh < None" TypeError
            # verip TÜM turu düşürüyordu (hiçbir cihazın canlı değeri yazılmadı).
            return None
        self._sayac[ad] = (kwh, simdi)
        if onceki is None or onceki[0] is None:
            return None
        eski_kwh, eski_zaman = onceki
        dt = simdi - eski_zaman
        if dt < 5 or kwh < eski_kwh:       # çok kısa aralık / sayaç sıfırlanmış
            return None
        return round((kwh - eski_kwh) / dt * 3600.0, 2)

    def _atlanacak(self, ad) -> bool:
        """Üst üste cevap vermeyen cihaz bir süre atlanır.

        NEDEN: her başarısız okuma zaman aşımı kadar (2 sn) bekler. Arızalı
        beş sayaç, 15 saniyelik turun 10 saniyesini tek başına yer; sağlam
        sayaçların verisi de gecikir. Atlanan cihaz ekranda 'okunamadı'
        kalır — gizlenmez — ve belirli aralıkla yeniden denenir.
        """
        kalan = self._atla.get(ad, 0)
        if kalan > 0:
            self._atla[ad] = kalan - 1
            return True
        return False

    def _hata_isle(self, ad, basarili):
        if basarili:
            self._hata[ad] = 0
            return
        self._hata[ad] = self._hata.get(ad, 0) + 1
        if self._hata[ad] >= int(self.ayar["ariza_esigi"]):
            self._atla[ad] = int(self.ayar["ariza_bekleme_tur"])
            self._hata[ad] = 0
            logger.info("%s üst üste cevap vermedi — %d tur atlanacak",
                        ad, self.ayar["ariza_bekleme_tur"])

    def tur(self) -> list:
        """Bir ölçüm turu. Her cihaz için sözlük döner."""
        self.tur_no += 1
        sayac_turu = (self.tur_no % max(1, int(self.ayar["sayac_her_n_tur"])) == 1)
        liste = cihazlar(self.ayar)
        okunacak = [d for d in liste if not self._atlanacak(d.get("name", "?"))]

        # ── Paralel okuma ────────────────────────────────────────────────
        ham = {}
        es_zamanli = max(1, int(self.ayar.get("es_zamanli", 8)))
        if es_zamanli > 1 and len(okunacak) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(es_zamanli, len(okunacak)),
                                    thread_name_prefix="canli-guc") as havuz:
                isler = {havuz.submit(self._oku_tek, d, sayac_turu): d for d in okunacak}
                for is_, dev in isler.items():
                    try:
                        ham[dev.get("name", "?")] = is_.result()
                    except Exception:
                        ham[dev.get("name", "?")] = (None, None)
        else:
            for dev in okunacak:
                try:
                    ham[dev.get("name", "?")] = self._oku_tek(dev, sayac_turu)
                except Exception:
                    ham[dev.get("name", "?")] = (None, None)

        # ── Karar: tek iplikte, sıra GARANTİLİ ───────────────────────────
        simdi = time.time()
        sonuc = []
        for dev in liste:
            ad = dev.get("name", "?")
            if ad not in ham:                       # bu tur atlandı
                kayit = self._karar(ad, None, None, None)
                kayit["not"] = "cihaz cevap vermiyor — geçici olarak atlanıyor"
                sonuc.append(kayit)
                continue
            kw_reg, kwh = ham[ad]
            self._hata_isle(ad, kw_reg is not None or kwh is not None)
            kw_sayac = self._sayac_gucu(ad, kwh, simdi) if sayac_turu else None
            sonuc.append(self._karar(ad, kw_reg, kw_sayac, kwh))

        return sonuc

    def _karar(self, ad, kw_reg, kw_sayac, kwh) -> dict:
        """Hangi değeri göstereceğimize karar ver ve NEDENİNİ yaz.

        yontem: "register"   → güç register'ı sayaçla doğrulandı
                "register?"  → henüz doğrulanmadı (ilk tur / sayaç turu değil)
                "sayac"      → register yok ya da sayaçla çelişti, ortalama
                None         → okunamadı
        """
        reg_makul = self._makul(kw_reg)
        sayac_makul = self._makul(kw_sayac)
        onceki = self._son_karar.get(ad, {})

        kayit = {"cihaz": ad, "kw": None, "yontem": None, "not": None,
                 "kw_register": kw_reg if reg_makul else None,
                 "kw_sayac": kw_sayac if sayac_makul else None,
                 "kwh": kwh}

        if reg_makul and sayac_makul:
            fark = abs(kw_reg - kw_sayac)
            pay = max(self.ayar["tolerans_kw"],
                      abs(kw_sayac) * self.ayar["tolerans_oran"])
            if fark <= pay:
                kayit.update(kw=kw_reg, yontem="register")
            else:
                kayit.update(kw=kw_sayac, yontem="sayac",
                             **{"not": "register %.0f kW sayaçla uyuşmadı (%.0f kW)"
                                % (kw_reg, kw_sayac)})
        elif reg_makul:
            # Daha önce doğrulanmışsa damga korunur; hiç doğrulanmadıysa soru işaretli
            dogrulanmis = onceki.get("yontem") == "register"
            kayit.update(kw=kw_reg, yontem="register" if dogrulanmis else "register?")
        elif sayac_makul:
            kayit.update(kw=kw_sayac, yontem="sayac",
                         **{"not": "güç register'ı okunamadı"})
        else:
            kayit.update(**{"not": "cihaz okunamadı"})

        # Sayaç turu olmayan turlarda eski doğrulama damgası taşınsın
        self._son_karar[ad] = {"yontem": kayit["yontem"] if kayit["yontem"] != "register?"
                               else onceki.get("yontem")}
        return kayit


# ── Dosyaya yazma (cloud_sync buradan okuyup buluta taşır) ────────────────

def dosyaya_yaz(olcumler: list, dosya: str = None) -> None:
    dosya = dosya or SONUC_DOSYA
    try:
        os.makedirs(os.path.dirname(dosya), exist_ok=True)
        gecici = dosya + ".tmp"
        # Zaman damgası SAAT DİLİMİYLE yazılır (astimezone).
        # Çıplak damga Supabase'in timestamptz sütununda UTC sayılıyordu;
        # lokasyon UTC+3 olduğu için merkez ölçümü 3 saat GELECEKTE görüyor
        # ve ekranda "son ölçüm -10766 sn önce" yazıyordu (21.10.2026).
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump({"zaman": datetime.now().astimezone().isoformat(timespec="seconds"),
                       "olcumler": olcumler}, f, ensure_ascii=False)
        os.replace(gecici, dosya)          # yarım dosya okunmasın
    except Exception as e:
        logger.warning("Canlı güç dosyası yazılamadı: %s", e)


def son_olcum(dosya: str = None, azami_yas_sn: int = 120):
    """Son ölçümü oku. Bayatsa None — merkeze eski değer gitmesin."""
    dosya = dosya or SONUC_DOSYA
    try:
        with open(dosya, encoding="utf-8") as f:
            veri = json.load(f)
        _t = datetime.fromisoformat(veri["zaman"])
        # Eski dosyalar saat dilimsiz yazılmış olabilir — ikisini de karşıla
        _simdi = datetime.now().astimezone() if _t.tzinfo else datetime.now()
        yas = (_simdi - _t).total_seconds()
        if yas > azami_yas_sn:
            return None
        veri["yas_sn"] = round(yas, 1)
        return veri
    except Exception:
        return None


# ── Döngü (data_collector tarafından thread olarak başlatılır) ────────────

def dongu(kilit_al=None):
    ayar = ayar_oku()
    periyot = max(5, int(ayar.get("periyot_sn", 15)))
    olcer = Olcer(ayar, kilit_al=kilit_al)
    logger.info("Canlı güç okuması başladı — %d cihaz, %d sn periyot, %d eş zamanlı",
                len(cihazlar(ayar)), periyot, ayar.get("es_zamanli", 8))
    while True:
        basla = time.time()
        try:
            dosyaya_yaz(olcer.tur())
        except Exception as e:
            logger.warning("Canlı güç turu hatası: %s", e)
        # Tur uzun sürerse bekleme kısalır; turlar ÜST ÜSTE binmez
        time.sleep(max(1.0, periyot - (time.time() - basla)))


def baslat(kilit_al=None):
    t = threading.Thread(target=dongu, kwargs={"kilit_al": kilit_al},
                         daemon=True, name="canli-guc")
    t.start()
    return t
