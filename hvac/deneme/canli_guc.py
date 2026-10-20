# -*- coding: utf-8 -*-
"""CANLI GÜÇ OKUMASI — TRDP trafolarının anlık kW değeri.

NEDEN: Lokasyon detayında bugün yalnızca dönem toplamı (kWh) var; sahada o
an ne çekildiği görünmüyor. Günlük sayaç okuması (data_collector.modbus_thread)
günde BİR kez çalışır — canlı izleme için uygun değildir.

── İKİ YÖNTEM, BİRBİRİNİ DENETLER ────────────────────────────────────────
Analizörden anlık gücü okumanın iki yolu var:

  1) GÜÇ REGISTER'I — cihazın kendi bildirdiği toplam etkin güç (W).
     Gerçek anlık değerdir, ama register adresi cihaz modeline göre değişir.
     Yanlış adres "makul ama yanlış" bir sayı döndürebilir: tek faz okunursa
     gerçeğin üçte biri, gerilim register'ına denk gelinirse sabit ~230
     görünür. Bunu gözle ayırmak mümkün değildir.

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

# Hangi cihazlar canlı okunuyor. Şimdilik yalnız trafolar (kullanıcı kararı
# 20.10.2026); chiller/MCC/kule aynı mekanizmayla sonra eklenebilir.
CIHAZ_ONEKI = "TRDP-"

VARSAYILAN_AYAR = {
    "periyot_sn": 15,          # kaç saniyede bir güç okunsun
    "sayac_her_n_tur": 4,      # kaç turda bir kWh ile çapraz denetim (4×15 = 60 sn)
    "tolerans_oran": 0.12,     # register ile sayaç farkı: %12'ye kadar uyumlu sayılır
    "tolerans_kw": 15.0,       # küçük yüklerde oran anlamsız, mutlak pay
    "makul_alt_kw": -50.0,     # şebekeye verme ihtimaline karşı negatife biraz pay
    "makul_ust_kw": 5000.0,    # bir trafodan beklenebilecek üst sınır
    # Toplam etkin güç register adresi (W, float32). Cihaz modeline göre
    # değişir; sahada GUC: komutuyla doğrulanır ve gerekirse BURADAN
    # düzeltilir — kod değişmeden.
    "guc_register": {"janitza": 19026, "siemens": 65},
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
    return round(w / 1000.0, 2)          # W → kW


def cihazlar() -> list:
    """Canlı okunacak cihazlar — TEK KAYNAK data_collector.ANALYZERS.

    Ayrı bir liste tutulmaz: sahada bir trafo eklenip ANALYZERS'a yazıldığında
    canlı panel de kendiliğinden onu gösterir.
    """
    try:
        import data_collector as dc
        return [d for d in dc.ANALYZERS if str(d.get("name", "")).startswith(CIHAZ_ONEKI)]
    except Exception as e:
        logger.warning("Analizör listesi okunamadı: %s", e)
        return []


def _sayac_oku(dev: dict):
    """kWh sayacı — ÜRETİMDEKİ okuyucuyla (tek kaynak)."""
    try:
        import data_collector as dc
        return dc.modbus_get_kwh(dev)
    except Exception:
        return None


# ── Ölçüm turu ────────────────────────────────────────────────────────────

class Olcer:
    """Turları yürütür ve sayaç geçmişini tutar (çapraz denetim için)."""

    def __init__(self, ayar: dict = None, kilit=None):
        self.ayar = ayar or ayar_oku()
        self.kilit = kilit                 # günlük okumayla çakışmayı önler
        self.tur_no = 0
        self._sayac = {}                   # cihaz → (kwh, zaman)
        self._son_karar = {}               # cihaz → {"yontem": ...} (doğrulama damgası)

    def _makul(self, kw) -> bool:
        return (kw is not None
                and self.ayar["makul_alt_kw"] <= kw <= self.ayar["makul_ust_kw"])

    def _sayac_gucu(self, ad: str, kwh, simdi: float):
        """Sayaç farkından ortalama kW. İlk okumada / geriye saymada None."""
        onceki = self._sayac.get(ad)
        self._sayac[ad] = (kwh, simdi)
        if onceki is None or kwh is None:
            return None
        eski_kwh, eski_zaman = onceki
        dt = simdi - eski_zaman
        if dt < 5 or kwh < eski_kwh:       # çok kısa aralık / sayaç sıfırlanmış
            return None
        return round((kwh - eski_kwh) / dt * 3600.0, 2)

    def tur(self) -> list:
        """Bir ölçüm turu. Her cihaz için sözlük döner."""
        self.tur_no += 1
        sayac_turu = (self.tur_no % max(1, int(self.ayar["sayac_her_n_tur"])) == 1)
        sonuc = []

        for dev in cihazlar():
            ad = dev.get("name", "?")
            if self.kilit is not None:
                self.kilit.acquire()
            try:
                kw_reg = guc_oku(dev, self.ayar)
                kwh = _sayac_oku(dev) if sayac_turu else None
            finally:
                if self.kilit is not None:
                    self.kilit.release()

            kw_sayac = self._sayac_gucu(ad, kwh, time.time()) if sayac_turu else None
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
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump({"zaman": datetime.now().isoformat(timespec="seconds"),
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
        yas = (datetime.now() - datetime.fromisoformat(veri["zaman"])).total_seconds()
        if yas > azami_yas_sn:
            return None
        veri["yas_sn"] = round(yas, 1)
        return veri
    except Exception:
        return None


# ── Döngü (data_collector tarafından thread olarak başlatılır) ────────────

def dongu(kilit=None):
    ayar = ayar_oku()
    periyot = max(5, int(ayar.get("periyot_sn", 15)))
    olcer = Olcer(ayar, kilit=kilit)
    logger.info("Canlı güç okuması başladı — %d cihaz, %d sn periyot",
                len(cihazlar()), periyot)
    while True:
        basla = time.time()
        try:
            dosyaya_yaz(olcer.tur())
        except Exception as e:
            logger.warning("Canlı güç turu hatası: %s", e)
        # Tur uzun sürerse bekleme kısalır; turlar ÜST ÜSTE binmez
        time.sleep(max(1.0, periyot - (time.time() - basla)))


def baslat(kilit=None):
    t = threading.Thread(target=dongu, kwargs={"kilit": kilit},
                         daemon=True, name="canli-guc")
    t.start()
    return t
