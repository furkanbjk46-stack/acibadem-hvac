# -*- coding: utf-8 -*-
"""
HATA ÖZETİ — sahadaki uyarı / hataların gün gün özeti ve merkeze gönderimi (yol haritası N5, 12.11.2026)
====================================================================================================

Sahadaki loglar ~3 gün tutuyordu (cloud_sync.log 4 × 2 MB); hafta sonu çıkan bir arıza pazartesi
incelenemiyordu, merkezde log yoktu. Bu modül:

  1) Her süreçte (cloud_sync, Enerji portalı, Mekanik Zeka) WARNING ve üstü log satırlarını yakalar,
     ŞABLONA indirger (sayı, IP, tırnak içi değer → <n>, <ip>, '…') ve gün + şablon başına sayar:
     adet, ilk / son zaman, son örnek. Dosya: durum/hata_ozeti_<kaynak>.json (son 30 gün).
  2) cloud_sync 10 dakikada bir bütün kaynakların özetini merkezdeki lokasyon_hatalari tablosuna
     (veritabani/degisiklikler/007) gönderir — yalnız değişen satırlar.

Log satırının kendisi değil, şablonu ve kısaltılmış son örneği gider (kişisel veri yazılmaz: loglarda
yalnız cihaz / dosya / bağlantı bilgisi var; yine de örnek 200 karakterle sınırlı).
Kayıt hiçbir durumda programı durdurmaz: yakalayıcı hatası yutulur.
"""
import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
SAKLA_GUN = 30
YAZ_ARALIK_SN = 60
TABLO = "lokasyon_hatalari"
_SABLON = [
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"'[^']{0,200}'|\"[^\"]{0,200}\""), "'…'"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.I), "<id>"),
    (re.compile(r"[-+]?\d+(?:[.,]\d+)?"), "<n>"),
    (re.compile(r"\s+"), " "),
]


def sablon(mesaj: str) -> str:
    s = str(mesaj or "")
    for desen, yerine in _SABLON:
        s = desen.sub(yerine, s)
    return s.strip()[:160]


def anahtar(seviye, kaynak, sab):
    return hashlib.sha1(("%s|%s|%s" % (seviye, kaynak, sab)).encode("utf-8")).hexdigest()[:16]


class Toplayici(logging.Handler):
    """WARNING+ satırları gün + şablon başına sayar; en çok YAZ_ARALIK_SN'de bir dosyaya yazar."""

    def __init__(self, kaynak, base_dir=None, simdi=None):
        super().__init__(level=logging.WARNING)
        self.kaynak = kaynak
        self.base = base_dir or BURASI
        self._simdi = simdi or datetime.now
        self._kilit = threading.Lock()
        self._son_yazma = 0.0
        try:
            self.veri = _oku(self.dosya())
        except Exception:
            self.veri = {}

    def dosya(self):
        return yollar.dosya_icin("durum/hata_ozeti_%s.json" % self.kaynak, self.base)

    def emit(self, kayit):
        try:
            if kayit.name == "hata_ozeti":
                return
            z = self._simdi()
            mesaj = kayit.getMessage()
            if kayit.exc_info and kayit.exc_info[0] is not None:
                mesaj = "%s [%s]" % (mesaj, kayit.exc_info[0].__name__)
            sab = sablon(mesaj)
            gun = z.strftime("%Y-%m-%d")
            k = anahtar(kayit.levelname, self.kaynak, sab)
            with self._kilit:
                g = self.veri.setdefault(gun, {})
                s = g.get(k)
                if s is None:
                    s = g[k] = {"seviye": kayit.levelname, "kaynak": self.kaynak, "modul": kayit.name[:60],
                                "sablon": sab, "adet": 0, "ilk": z.isoformat(timespec="seconds")}
                s["adet"] += 1
                s["son"] = z.isoformat(timespec="seconds")
                s["ornek"] = mesaj[:200]
            if time.monotonic() - self._son_yazma >= YAZ_ARALIK_SN:
                self.yaz()
        except Exception:
            pass

    def yaz(self):
        try:
            with self._kilit:
                sinir = (self._simdi() - timedelta(days=SAKLA_GUN)).strftime("%Y-%m-%d")
                for gun in [g for g in self.veri if g < sinir]:
                    del self.veri[gun]
                metin = json.dumps(self.veri, ensure_ascii=False)
            p = self.dosya()
            gecici = p + ".tmp"
            with open(gecici, "w", encoding="utf-8") as f:
                f.write(metin)
            os.replace(gecici, p)
            self._son_yazma = time.monotonic()
        except Exception:
            pass


def _oku(p):
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


_KURULU = {}


def kur(kaynak, base_dir=None):
    """Bu sürecin kök logger'ına toplayıcıyı bir kez ekler (aynı kaynak iki kez eklenmez)."""
    if kaynak in _KURULU:
        return _KURULU[kaynak]
    try:
        t = Toplayici(kaynak, base_dir)
        logging.getLogger().addHandler(t)
        import atexit
        atexit.register(t.yaz)
        _KURULU[kaynak] = t
        return t
    except Exception:
        return None


def satirlar(lokasyon_id, base_dir=None, simdi=None):
    """Bütün kaynakların özeti → tablo satırları (son SAKLA_GUN gün)."""
    base_dir = base_dir or BURASI
    for t in _KURULU.values():          # bu süreçteki toplayıcı önce diske yazsın
        t.yaz()
    sinir = ((simdi or datetime.now()) - timedelta(days=SAKLA_GUN)).strftime("%Y-%m-%d")
    klasor = os.path.dirname(yollar.dosya_icin("durum/hata_ozeti_x.json", base_dir))
    cikti = []
    for ad in sorted(os.listdir(klasor)) if os.path.isdir(klasor) else []:
        if not (ad.startswith("hata_ozeti_") and ad.endswith(".json")):
            continue
        for gun, kayitlar in _oku(os.path.join(klasor, ad)).items():
            if gun < sinir:
                continue
            for k, s in kayitlar.items():
                cikti.append({"lokasyon_id": lokasyon_id, "gun": gun, "anahtar": k, "seviye": s.get("seviye"),
                              "kaynak": s.get("kaynak"), "modul": s.get("modul"), "sablon": s.get("sablon"),
                              "adet": int(s.get("adet") or 0), "ilk": s.get("ilk"), "son": s.get("son"),
                              "ornek": s.get("ornek")})
    return cikti


def gonder(client, lokasyon_id, base_dir=None, simdi=None) -> dict:
    """Değişen satırları upsert eder. Gönderilenlerin izi: durum/hata_gonderim_izi.json."""
    base_dir = base_dir or BURASI
    iz_dosya = yollar.dosya_icin("durum/hata_gonderim_izi.json", base_dir)
    iz = _oku(iz_dosya)
    hepsi = satirlar(lokasyon_id, base_dir, simdi)
    gidecek = [r for r in hepsi if iz.get("%s|%s" % (r["gun"], r["anahtar"])) != "%s|%s" % (r["adet"], r["son"])]
    sonuc = {"satir": 0}
    try:
        for i in range(0, len(gidecek), 200):
            client.table(TABLO).upsert(gidecek[i:i + 200], on_conflict="lokasyon_id,gun,anahtar",
                                       returning="minimal").execute()
            for r in gidecek[i:i + 200]:
                iz["%s|%s" % (r["gun"], r["anahtar"])] = "%s|%s" % (r["adet"], r["son"])
            sonuc["satir"] += len(gidecek[i:i + 200])
    except Exception as e:
        sonuc["hata"] = str(e)[:200]
    sinir = ((simdi or datetime.now()) - timedelta(days=SAKLA_GUN + 1)).strftime("%Y-%m-%d")
    iz = {k: v for k, v in iz.items() if k.split("|", 1)[0] >= sinir}
    try:
        with open(iz_dosya, "w", encoding="utf-8") as f:
            json.dump(iz, f)
    except OSError:
        pass
    return sonuc
