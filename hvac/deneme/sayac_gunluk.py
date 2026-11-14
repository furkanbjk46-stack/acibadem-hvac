# -*- coding: utf-8 -*-
"""
SAYAÇ GÜNLÜK — her sayacın günlük değerini merkezdeki ince tabloya gönderir (yol haritası D1, 12.11.2026)
=====================================================================================================

energy_data geniş tablodur: sayaç başına bir sütun. Yeni lokasyonun yeni sayacı için önce merkezde SQL
sütunu açılması gerekiyordu. sayac_gunluk'ta (veritabani/degisiklikler/006) sayaç bir SATIRDIR:
    lokasyon_id, tarih, sayac (sayaclar.json "ad"), deger, birim, tur
ayar/sayaclar.json'a eklenen sayaç, merkezde hiçbir değişiklik yapılmadan buraya gelir.

Geçiş döneminde iki yere de yazılır: energy_data aynen gönderilmeye devam eder (cloud_sync).

Yalnız içeriği DEĞİŞEN günler gönderilir (gün başına özet: durum/sayac_gunluk_ozet.json); ilk turda
bütün geçmiş gider. Sahada silinen gün merkezden de silinir — ama bir turda çok sayıda gün kaybolursa
(CSV yarım / bozuk) silme yapılmaz, yalnız loglanır.
"""
import hashlib
import json
import logging
import math
import os

import sayaclar
import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
TABLO = "sayac_gunluk"
OZET = "durum/sayac_gunluk_ozet.json"
PARTI = 500
logger = logging.getLogger("sayac_gunluk")


def _sayi(v):
    if v is None:
        return None
    try:
        f = float(v.item() if hasattr(v, "item") else v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


def _tarih(v):
    s = str(v)[:10]
    return s if len(s) == 10 and s[4] == "-" and s[7] == "-" else None


def satirlar(kayitlar, lokasyon_id, base_dir=None):
    """{tarih: [satır, ...]} — kayitlar: energy_data satırları (dict; "Tarih" + sayaç sütunları)."""
    liste = [s for s in sayaclar.yukle(base_dir) if s.get("sutun")]
    gunler = {}
    for r in kayitlar:
        t = _tarih(r.get("Tarih"))
        if not t:
            continue
        gunler[t] = [{"lokasyon_id": lokasyon_id, "tarih": t, "sayac": s["ad"], "deger": _sayi(r.get(s["sutun"])),
                      "birim": s.get("birim") or "kWh", "tur": s["tur"]}
                     for s in liste if s["sutun"] in r]
    return {t: v for t, v in gunler.items() if v}


def _iz(satir_listesi):
    ham = json.dumps([(x["sayac"], x["deger"], x["birim"], x["tur"]) for x in satir_listesi], sort_keys=True)
    return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]


def _ozet_oku(p, lokasyon_id):
    try:
        with open(p, encoding="utf-8") as f:
            veri = json.load(f)
        return dict(veri.get(lokasyon_id) or {}) if isinstance(veri, dict) else {}
    except (OSError, ValueError):
        return {}


def _ozet_yaz(p, lokasyon_id, ozet):
    try:
        with open(p, encoding="utf-8") as f:
            veri = json.load(f)
        if not isinstance(veri, dict):
            veri = {}
    except (OSError, ValueError):
        veri = {}
    veri[lokasyon_id] = ozet
    gecici = p + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)
    os.replace(gecici, p)


def gonder(client, kayitlar, lokasyon_id, base_dir=None) -> dict:
    """Değişen günleri upsert eder, sahada silinen günleri siler. Dönüş: {"gun", "satir", "silinen"[, "hata"]}."""
    base_dir = base_dir or BURASI
    p = yollar.dosya_icin(OZET, base_dir)
    onceki = _ozet_oku(p, lokasyon_id)
    gunler = satirlar(kayitlar, lokasyon_id, base_dir)
    yeni = {t: _iz(v) for t, v in gunler.items()}
    degisen = sorted(t for t in yeni if onceki.get(t) != yeni[t])
    giden = sorted(t for t in onceki if t not in yeni)
    sonuc = {"gun": len(degisen), "satir": 0, "silinen": 0}

    # Bozuk / yarım CSV koruması: bir turda bu kadar günün kaybolması normal değil (portaldan tek tek silinir)
    if giden and len(giden) > max(31, len(onceki) // 10):
        logger.error("⛔ sayac_gunluk: %d gün yerelde yok (önceden %d) — yarım CSV şüphesi, silme yapılmadı",
                     len(giden), len(onceki))
        giden = []
        sonuc["silme_atlandi"] = True

    try:
        gidecek = [x for t in degisen for x in gunler[t]]
        for i in range(0, len(gidecek), PARTI):
            client.table(TABLO).upsert(gidecek[i:i + PARTI], on_conflict="lokasyon_id,tarih,sayac",
                                       returning="minimal").execute()
            sonuc["satir"] += len(gidecek[i:i + PARTI])
        for i in range(0, len(giden), 100):
            client.table(TABLO).delete().eq("lokasyon_id", lokasyon_id).in_("tarih", giden[i:i + 100]).execute()
            sonuc["silinen"] += len(giden[i:i + 100])
    except Exception as e:
        # Gönderilen kısmı özete işle; kalanlar sonraki turda yeniden denenir
        gonderilen = set()
        say = 0
        for t in degisen:
            say += len(gunler[t])
            if say <= sonuc["satir"]:
                gonderilen.add(t)
        kalan = {t: h for t, h in onceki.items() if t in yeni or t in giden}
        kalan.update({t: yeni[t] for t in gonderilen})
        try:
            _ozet_yaz(p, lokasyon_id, kalan)
        except OSError:
            pass
        sonuc["hata"] = str(e)[:200]
        logger.warning("sayac_gunluk gönderimi yarım kaldı (%d satır gitti): %s", sonuc["satir"], e)
        return sonuc

    son = dict(yeni)
    if sonuc.get("silme_atlandi"):                    # silinmeyen günler özette kalır, sonraki tur yine bakar
        son.update({t: h for t, h in onceki.items() if t not in yeni})
    _ozet_yaz(p, lokasyon_id, son)
    if sonuc["satir"] or sonuc["silinen"]:
        logger.info("📊 sayac_gunluk: %d gün / %d satır gönderildi, %d gün silindi (%s)",
                    sonuc["gun"], sonuc["satir"], sonuc["silinen"], lokasyon_id)
    return sonuc
