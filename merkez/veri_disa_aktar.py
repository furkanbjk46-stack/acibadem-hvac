# -*- coding: utf-8 -*-
"""
VERİ DIŞA AKTARMA — Supabase'deki tabloları tek tıkla JSON / CSV indirmek
=======================================================================

Ayarlar → "Veri" sekmesi bu modülü kullanır. Yalnızca OKUR (GET); hiçbir
tabloya yazmaz. Okuma, portalın kendi bağlantı anahtarıyla yapılır: o
anahtarın okuyamadığı (RLS ile kapalı) tablo boş gelir ve ekranda öyle yazar.

Biçimler:
  json → tek dosya: {"olusturma": ..., "kaynak": ..., "tablolar": {ad: [satır...]}}
  csv  → ZIP: her tablo ayrı .csv (Excel Türkçe karakterleri doğru açsın
          diye UTF-8 BOM'lu, ayraç ';'), yanında ozet.txt

Sayfalama: PostgREST tek istekte en fazla ~1000 satır döner; tablo 1000'lik
sayfalarla sonuna kadar okunur. Sıra sabit olsun diye önce "id"ye göre
sıralanır; tabloda id yoksa sırasız okunur.
"""
import csv
import io
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime

# Synapse'in bildiği tablolar (kodda kullanılanlar). Sunucunun şema listesi
# okunabiliyorsa oradaki EK tablolar da listeye katılır.
TABLOLAR = [
    "energy_data", "lokasyonlar", "ayarlar", "canli_guc", "komutlar",
    "guncellemeler", "bildirimler", "bakim_kartlari", "oto_mod_log",
    "lokasyon_noktalar", "lisanslar", "hvac_summary", "dis_hava_log",
    "ai_analizler",
]
SAYFA = 1000
ZAMAN_ASIMI = 30


def _basliklar(key: str) -> dict:
    return {"apikey": key, "Authorization": "Bearer " + key, "Accept": "application/json"}


def _get(url: str, key: str):
    istek = urllib.request.Request(url, headers=_basliklar(key), method="GET")
    with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as yanit:
        return json.loads(yanit.read().decode("utf-8") or "null")


def tablolari_bul(url: str, key: str) -> list:
    """Bilinen tablolar + sunucunun şemasında görünen ek tablolar (sıralı)."""
    liste = list(TABLOLAR)
    try:
        sema = _get(url.rstrip("/") + "/rest/v1/", key)
        tanimlar = (sema or {}).get("definitions") or {}
        for ad in sorted(tanimlar):
            if ad not in liste and not ad.startswith("_"):
                liste.append(ad)
    except Exception:
        pass   # şema kapalıysa bilinen liste yeterli
    return liste


def tablo_oku(url: str, key: str, tablo: str, sayfa: int = SAYFA) -> list:
    """Tablonun TÜM satırları. Hata olursa istisna fırlatır (çağıran yakalar)."""
    taban = url.rstrip("/") + "/rest/v1/" + urllib.parse.quote(tablo)
    satirlar, ofset, sirali = [], 0, True
    while True:
        p = {"select": "*", "limit": str(sayfa), "offset": str(ofset)}
        if sirali:
            p["order"] = "id.asc"
        try:
            parca = _get(taban + "?" + urllib.parse.urlencode(p), key)
        except urllib.error.HTTPError as e:
            if sirali and e.code == 400 and ofset == 0:
                sirali = False          # tabloda "id" sütunu yok → sırasız oku
                continue
            raise
        if not isinstance(parca, list):
            break
        satirlar.extend(parca)
        if len(parca) < sayfa:
            break
        ofset += sayfa
    return satirlar


def hepsini_oku(url: str, key: str, tablolar: list, ilerleme=None) -> tuple:
    """({tablo: satırlar}, {tablo: hata metni}). ilerleme(i, toplam, tablo) çağrılır."""
    veri, hatalar = {}, {}
    for i, t in enumerate(tablolar):
        if ilerleme:
            ilerleme(i, len(tablolar), t)
        try:
            veri[t] = tablo_oku(url, key, t)
        except urllib.error.HTTPError as e:
            hatalar[t] = "HTTP %d%s" % (e.code, " (tablo yok)" if e.code == 404 else
                                        " (erişim yok)" if e.code in (401, 403) else "")
        except Exception as e:
            hatalar[t] = type(e).__name__ + ": " + str(e)[:120]
    return veri, hatalar


def _hucre(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def tablo_csv(satirlar: list) -> bytes:
    """Satırlar → CSV (UTF-8 BOM, ';' ayraç). Sütunlar tüm satırların birleşimi."""
    sutunlar = []
    for s in satirlar:
        for k in s:
            if k not in sutunlar:
                sutunlar.append(k)
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    w.writerow(sutunlar)
    for s in satirlar:
        w.writerow([_hucre(s.get(k)) for k in sutunlar])
    return ("﻿" + tampon.getvalue()).encode("utf-8")


def ozet_metni(veri: dict, hatalar: dict, kaynak: str, zaman: datetime) -> str:
    satir = ["Synapse veri yedeği", "Oluşturma: " + zaman.strftime("%d.%m.%Y %H:%M:%S"),
             "Kaynak: " + kaynak, ""]
    for t, s in veri.items():
        satir.append("%-20s %8d satır" % (t, len(s)))
    for t, h in hatalar.items():
        satir.append("%-20s okunamadı: %s" % (t, h))
    return "\n".join(satir) + "\n"


def paket(veri: dict, hatalar: dict, bicim: str, kaynak: str = "", zaman: datetime = None) -> tuple:
    """(dosya adı, bayt, mime). bicim: 'json' | 'csv'."""
    zaman = zaman or datetime.now()
    damga = zaman.strftime("%Y%m%d_%H%M")
    if bicim == "json":
        govde = {
            "olusturma": zaman.isoformat(timespec="seconds"),
            "kaynak": kaynak,
            "satir_sayilari": {t: len(s) for t, s in veri.items()},
            "okunamayan": hatalar,
            "tablolar": veri,
        }
        return ("synapse_yedek_%s.json" % damga,
                json.dumps(govde, ensure_ascii=False, indent=1, default=str).encode("utf-8"),
                "application/json")
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for t, s in veri.items():
            z.writestr(t + ".csv", tablo_csv(s))
        z.writestr("ozet.txt", ozet_metni(veri, hatalar, kaynak, zaman).encode("utf-8"))
    return "synapse_yedek_%s_csv.zip" % damga, tampon.getvalue(), "application/zip"
