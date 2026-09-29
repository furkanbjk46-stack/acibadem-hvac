# -*- coding: utf-8 -*-
"""
İZLEME — ortak ölçüm ve alarm mantığı
=====================================

İki yer kullanır:
  * pages/yonetim.py        → Synapse içindeki CANLI yönetim ekranı
  * sema_diyagram_uret.py   → tek dosyalık statik şema/izleme sayfası

Eşikler configs/izleme_limitleri.json'da; kod içine sayı yazılmaz.
Ölçümler salt okur `synapse_kullanim()` RPC'sinden gelir (bkz.
izleme_kurulum.sql). Fonksiyon yalnızca service_role'a açıktır.
"""

import json
import os
import urllib.error
import urllib.request

BURASI = os.path.dirname(os.path.abspath(__file__))
LIMIT_DOSYA = os.path.join(BURASI, "configs", "izleme_limitleri.json")


def limitler():
    with open(LIMIT_DOSYA, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def kullanim_oku(url, key, zaman_asimi=30):
    """synapse_kullanim() RPC'si. Fonksiyon kurulu değilse None döner."""
    try:
        istek = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/rpc/synapse_kullanim",
            data=b"{}",
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as c:
            veri = json.load(c)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None
    # PostgREST kimi kurulumlarda tek satiri liste icinde dondurur; sunum
    # sunucusu ise tanimadigi yola bos liste verir.
    if isinstance(veri, list):
        veri = veri[0] if veri and isinstance(veri[0], dict) else None
    return veri if isinstance(veri, dict) else None


def boyut(bayt):
    """1234567 → '1.2 MB'"""
    if bayt is None:
        return "—"
    b = float(bayt)
    for birim in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or birim == "TB":
            return ("%.0f %s" if birim in ("B", "KB") else "%.1f %s") % (b, birim)
        b /= 1024


def sayi(n):
    """1234567 → '1.234.567'"""
    try:
        return format(int(n), ",d").replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def disk_orani(kullanim, lim):
    """(kullanilan_bayt, kota_bayt, yuzde)"""
    kota = lim["plan_disk_gb"] * 1024 ** 3
    top = (kullanim.get("veritabani_bayt") if isinstance(kullanim, dict) else 0) or 0
    return top, kota, (top / kota * 100 if kota else 0.0)


def disk_seviye(oran, lim):
    """Doluluk yüzdesinin seviyesi: kritik | dikkat | iyi.

    Eşik kararı TEK YERDE dursun diye burada; ekranlar yalnızca renk seçer.
    """
    if oran >= lim["disk_kritik_yuzde"]:
        return "kritik"
    if oran >= lim["disk_dikkat_yuzde"]:
        return "dikkat"
    return "iyi"


def alarmlar(kullanim, lim):
    """(seviye, baslik, aciklama) listesi. Seviye: kritik | dikkat | iyi."""
    if not isinstance(kullanim, dict) or not kullanim:
        return []
    cikti = []
    _top, _kota, oran = disk_orani(kullanim, lim)
    _sev = disk_seviye(oran, lim)
    if _sev == "kritik":
        cikti.append(("kritik", "Disk kotası %%%.0f dolu" % oran,
                      "Kota dolduğunda Supabase istekleri reddeder: lokasyon "
                      "senkronu ve Synapse veri alamaz. Acil temizlik gerekir."))
    elif _sev == "dikkat":
        cikti.append(("dikkat", "Disk kotası %%%.0f dolu" % oran,
                      "Büyüme hızını izleyin; biriken tabloları temizleyin."))

    for t in kullanim.get("tablolar", []):
        ad = t.get("tablo")
        mb = (t.get("toplam_bayt") or 0) / 1024 ** 2
        ek = (" Bu tablo içerik/log biriktirir, eski kayıtlar silinebilir."
              if ad in lim.get("buyume_uyari_tablolari", []) else "")
        if mb >= lim["tablo_kritik_mb"]:
            cikti.append(("kritik", "%s tablosu %s" % (ad, boyut(t.get("toplam_bayt"))),
                          "Eşik %d MB." % lim["tablo_kritik_mb"] + ek))
        elif mb >= lim["tablo_dikkat_mb"]:
            cikti.append(("dikkat", "%s tablosu %s" % (ad, boyut(t.get("toplam_bayt"))),
                          "Eşik %d MB." % lim["tablo_dikkat_mb"] + ek))
        veri = t.get("veri_bayt") or 0
        indeks = t.get("indeks_bayt") or 0
        if veri > 5 * 1024 ** 2 and indeks > veri * lim["indeks_oran_dikkat"]:
            cikti.append(("dikkat", "%s indeksleri veriden büyük" % ad,
                          "İndeks %s / veri %s — kullanılmayan indeks olabilir."
                          % (boyut(indeks), boyut(veri))))

    s = kullanim.get("saglik") or {}
    isabet = s.get("onbellek_isabet_yuzde")
    if isabet is not None:
        try:
            if float(isabet) < lim["onbellek_isabet_dikkat"]:
                cikti.append(("dikkat", "Önbellek isabeti %%%.1f" % float(isabet),
                              "Eşik %%%d. Sorgular diskten okuyor, yavaşlama beklenir."
                              % lim["onbellek_isabet_dikkat"]))
        except (TypeError, ValueError):
            pass
    aktif, azami = s.get("aktif_baglanti"), s.get("azami_baglanti")
    if aktif and azami and aktif / azami * 100 >= lim["baglanti_dikkat_yuzde"]:
        cikti.append(("dikkat", "Bağlantı %d/%d" % (aktif, azami),
                      "Bağlantı havuzu doluyor."))
    if s.get("kilitlenme"):
        cikti.append(("dikkat", "%s kilitlenme (deadlock)" % s["kilitlenme"],
                      "Eşzamanlı yazımlar çakışıyor olabilir."))

    if not cikti:
        cikti.append(("iyi", "Tüm eşikler normal",
                      "Disk, tablo boyutları, önbellek ve bağlantılar sınırların altında."))
    return cikti


def en_kotu(alarm_listesi):
    """Alarm listesinin genel seviyesi."""
    seviyeler = {a[0] for a in alarm_listesi}
    if "kritik" in seviyeler:
        return "kritik"
    if "dikkat" in seviyeler:
        return "dikkat"
    return "iyi"
