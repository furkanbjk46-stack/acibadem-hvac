# -*- coding: utf-8 -*-
"""
PORTLAR — Enerji (Streamlit) ve Mekanik Zeka (FastAPI) portalının portu, TEK KAYNAK (13.11.2026)
==============================================================================================

Kaynak: ayar/portlar.json  {"enerji": 8501, "mekanik_zeka": 8005}
Dosya yoksa varsayılanlar (bugünkü portlar) geçerlidir; Maslak'ta hiçbir şey değişmez.

Neden: bazı PC'lerde 8005 / 8501'i başka bir program tutuyor (geliştirme PC'sinde 8005'i Windows
tutuyor). Port KURULUMDA BİR KEZ seçilir (sec()): varsayılan boşsa o, doluysa sıradaki boş port
yazılır. Sonra SABİT kalır — çalışırken başka porta KAYDIRILMAZ: sahadaki bakım kartı QR etiketleri
http://<pc-ip>:<port>/bakim/... adresini taşır, yer imleri ve agent kontrolleri de portu bilir.
Port sonradan dolarsa watchdog açıkça uyarır (durum/portlar_durum.json, log → merkezde hata özeti).
"""
import json
import logging
import os
import socket

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
DOSYA = "ayar/portlar.json"
VARSAYILAN = {"enerji": 8501, "mekanik_zeka": 8005}
ARAMA_SINIRI = 50              # varsayılandan sonra en çok bu kadar port denenir
logger = logging.getLogger("portlar")


def yukle(base_dir=None):
    """{"enerji": int, "mekanik_zeka": int} — dosya yok / bozuksa varsayılan (eksik alan da varsayılan)."""
    p = yollar.yol(DOSYA, base_dir or BURASI)
    sonuc = dict(VARSAYILAN)
    try:
        with open(p, encoding="utf-8-sig") as f:
            veri = json.load(f)
        for ad in VARSAYILAN:
            v = int(veri.get(ad, sonuc[ad]))
            if 1024 <= v <= 65535:
                sonuc[ad] = v
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return sonuc


def enerji(base_dir=None):
    return yukle(base_dir)["enerji"]


def mekanik_zeka(base_dir=None):
    return yukle(base_dir)["mekanik_zeka"]


def enerji_url(base_dir=None, host="127.0.0.1"):
    return "http://%s:%d" % (host, enerji(base_dir))


def mekanik_zeka_url(base_dir=None, host="127.0.0.1"):
    return "http://%s:%d" % (host, mekanik_zeka(base_dir))


def bos_mu(port):
    """Bu PC'de port dinlemeye uygun mu (hem 0.0.0.0 hem 127.0.0.1)."""
    for host in ("0.0.0.0", "127.0.0.1"):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind((host, port))
        except OSError:
            return False
        finally:
            s.close()
    return True


def sec(base_dir=None, _bos_mu=None):
    """KURULUMDA bir kez: ayar/portlar.json yoksa portları seçip yazar; varsa olduğu gibi bırakır.

    Dönüş: {"portlar": {...}, "yazildi": bool, "degisen": [ad, ...]} — degisen: varsayılan dolu olduğu
    için başka port seçilenler.
    """
    base_dir = base_dir or BURASI
    _bos_mu = _bos_mu or bos_mu
    p = yollar.yol(DOSYA, base_dir)
    if os.path.exists(p):
        return {"portlar": yukle(base_dir), "yazildi": False, "degisen": []}
    secilen, degisen, kullanilan = {}, [], set()
    for ad, varsayilan in VARSAYILAN.items():
        for port in range(varsayilan, varsayilan + ARAMA_SINIRI):
            if port not in kullanilan and _bos_mu(port):
                break
        else:
            port = varsayilan          # boş bulunamadı: varsayılan yazılır, kontrol listesi uyarır
        secilen[ad] = port
        kullanilan.add(port)
        if port != varsayilan:
            degisen.append(ad)
    p = yollar.dosya_icin(DOSYA, base_dir)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dict(secilen, _aciklama="Kurulumda seçildi; sonradan DEĞİŞTİRMEYİN — bakım kartı QR "
                                          "etiketleri bu portu taşır."), f, ensure_ascii=False, indent=1)
    return {"portlar": secilen, "yazildi": True, "degisen": degisen}


def durum_yaz(base_dir=None, _bos_mu=None):
    """Watchdog açılışında: portlar boş mu → durum/portlar_durum.json. Dönüş: dolu olanlar [(ad, port)]."""
    from datetime import datetime
    base_dir = base_dir or BURASI
    _bos_mu = _bos_mu or bos_mu
    portlar = yukle(base_dir)
    dolu = [(ad, port) for ad, port in portlar.items() if not _bos_mu(port)]
    try:
        with open(yollar.dosya_icin("durum/portlar_durum.json", base_dir), "w", encoding="utf-8") as f:
            json.dump({"zaman": datetime.now().isoformat(timespec="seconds"), "portlar": portlar,
                       "dolu": [{"ad": a, "port": p} for a, p in dolu]}, f, ensure_ascii=False)
    except OSError:
        pass
    return dolu
