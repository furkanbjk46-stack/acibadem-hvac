# -*- coding: utf-8 -*-
"""
SQL DURUMU — Yönetim sayfasının canlı veritabanı bölümü (hesap kısmı)
=====================================================================

Veri `synapse_sql_durumu()` RPC'sinden gelir (veritabani/degisiklikler/
001_sql_durumu_olcumu.sql). Fonksiyon yalnızca service_role'a açıktır;
merkez thapps'te service_role anahtarıyla çalışır.

Sunucu dosya sistemi (gece yedekleri, disk) merkez thapps'te çalıştığı için
doğrudan okunur; okunamazsa (yerel PC, yetki) ilgili kutu "—" görünür.

Streamlit içermez: pages/yonetim.py çizer, test_sql_durumu.py dener.
"""

import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=3))
YEDEK_KLASORU = "/opt/Backup"
YEDEK_KALIBI = re.compile(r"^synapse_db_(\d{8})_(\d{6})\.dump$")

# Uyarı eşikleri (dakika). canli_guc lokasyon PC'sinden ~dakikada bir gelir.
CANLI_VERI_DIKKAT_DK = 10
YEDEK_DIKKAT_SAAT = 26          # gece 01:30 yedeği + pay
DISK_DIKKAT_YUZDE = 80
DISK_KRITIK_YUZDE = 90


def oku(url, key, zaman_asimi=20):
    """(veri | None, yanıt_ms | None, hata_metni | None)"""
    bas = time.monotonic()
    try:
        istek = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/rpc/synapse_sql_durumu", data=b"{}",
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as c:
            veri = json.load(c)
    except urllib.error.HTTPError as e:
        ms = (time.monotonic() - bas) * 1000
        if e.code == 404:
            return None, ms, "fonksiyon_yok"
        if e.code in (401, 403):
            return None, ms, "yetki_yok"
        return None, ms, "HTTP %s" % e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        return None, None, "baglanti: %s" % getattr(e, "reason", e)
    ms = (time.monotonic() - bas) * 1000
    if isinstance(veri, list):
        veri = veri[0] if veri and isinstance(veri[0], dict) else None
    if not isinstance(veri, dict) or "tablolar" not in veri:
        return None, ms, "fonksiyon_yok"
    return veri, ms, None


def zaman(metin):
    """ISO / 'YYYY-MM-DD HH:MM:SS+00' / 'YYYY-MM-DD' → İstanbul saatli datetime (ya da None).
    Saat dilimi yazmayan değer İstanbul saati kabul edilir."""
    if not metin:
        return None
    s = str(metin).strip().replace(" ", "T", 1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        # Tarih sütunu (gün): o günün sonu kabul edilir, saat dilimi İstanbul
        return datetime.fromisoformat(s).replace(hour=23, minute=59, tzinfo=IST)
    s = re.sub(r"([+-]\d{2})$", r"\1:00", s.replace("Z", "+00:00"))
    try:
        z = datetime.fromisoformat(s)
    except ValueError:
        return None
    if z.tzinfo is None:
        # Saat dilimsiz değerler sahadan İstanbul saatiyle yazılır (ör. lokasyonlar.
        # ping_zamani metin sütunu). timestamptz sütunları her zaman ofsetli gelir.
        z = z.replace(tzinfo=IST)
    return z.astimezone(IST)


def once(z, simdi=None):
    """datetime → '3 dk önce' / '2,5 saat önce' / '4 gün önce'"""
    if z is None:
        return "—"
    dk = ((simdi or datetime.now(IST)) - z).total_seconds() / 60
    if dk < 1:
        return "az önce"
    if dk < 60:
        return "%d dk önce" % dk
    if dk < 1440:
        return ("%.1f saat önce" % (dk / 60)).replace(".", ",")
    return "%d gün önce" % (dk / 1440)


def calisma_suresi(baslangic, simdi=None):
    z = zaman(baslangic)
    if z is None:
        return "—"
    sn = ((simdi or datetime.now(IST)) - z).total_seconds()
    gun, saat = int(sn // 86400), int(sn % 86400 // 3600)
    return "%d gün %d saat" % (gun, saat) if gun else "%d saat %d dk" % (saat, sn % 3600 // 60)


def yedekler(klasor=YEDEK_KLASORU):
    """Gece yedekleri, yeniden eskiye: [{'ad', 'bayt', 'zaman'}]. Okunamazsa []."""
    try:
        adlar = os.listdir(klasor)
    except OSError:
        return []
    sonuc = []
    for ad in adlar:
        m = YEDEK_KALIBI.match(ad)
        if not m:
            continue
        try:
            bayt = os.stat(os.path.join(klasor, ad)).st_size
        except OSError:
            bayt = None
        z = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=IST)
        sonuc.append({"ad": ad, "bayt": bayt, "zaman": z})
    return sorted(sonuc, key=lambda y: y["zaman"], reverse=True)


def disk(yol="/"):
    """(kullanılan, toplam, boş) bayt; okunamazsa None."""
    try:
        d = shutil.disk_usage(yol)
        return d.used, d.total, d.free
    except OSError:
        return None


def tablo_satirlari(veri, simdi=None):
    """Ekrandaki tablo etkinliği listesi (son kayda göre yeniden eskiye)."""
    satirlar = []
    for t in veri.get("tablolar", []):
        z = zaman(t.get("son_kayit"))
        satirlar.append({
            "Tablo": t.get("tablo"),
            "Satır": t.get("satir"),
            "Sütun": t.get("sutun"),
            "Son kayıt": z.strftime("%d.%m %H:%M") if z and len(str(t.get("son_kayit"))) > 10
                         else (z.strftime("%d.%m.%Y") if z else "—"),
            "Ne zaman": once(z, simdi) if z and len(str(t.get("son_kayit"))) > 10
                        else (gun_metni(z, simdi) if z else "—"),
            "Eklenen": t.get("eklenen"),
            "Güncellenen": t.get("guncellenen"),
            "Silinen": t.get("silinen"),
            "Ölü satır": t.get("olu_satir"),
            "Son bakım": (zaman(t.get("son_vacuum")) or zaman(t.get("son_analyze"))
                          or None),
            "Erişim": erisim_metni(t),
            "_z": z,
        })
    for s in satirlar:
        s["Son bakım"] = s["Son bakım"].strftime("%d.%m %H:%M") if s["Son bakım"] else "—"
    satirlar.sort(key=lambda s: s["_z"] or datetime.min.replace(tzinfo=IST), reverse=True)
    for s in satirlar:
        s.pop("_z")
    return satirlar


def gun_metni(z, simdi=None):
    """Tarih (gün) sütunları için: bugün / dün / N gün önce."""
    fark = ((simdi or datetime.now(IST)).date() - z.date()).days
    return "bugün" if fark <= 0 else ("dün" if fark == 1 else "%d gün önce" % fark)


def erisim_metni(t):
    if not t.get("rls"):
        return "⛔ RLS kapalı"
    n = t.get("politika") or 0
    return "🔒 %d kural" % n if n else "🔒 yalnız merkez"


def uyarilar(veri, yedek_listesi=None, disk_bilgisi=None, simdi=None):
    """(seviye, başlık, açıklama) — seviye: kritik | dikkat | iyi."""
    simdi = simdi or datetime.now(IST)
    cikti = []
    tablolar = {t.get("tablo"): t for t in veri.get("tablolar", [])}

    acik = [ad for ad, t in tablolar.items() if not t.get("rls")]
    if acik:
        cikti.append(("kritik", "Erişim kuralı (RLS) kapalı: " + ", ".join(sorted(acik)),
                      "Bu tabloları sahadaki ortak anahtar sınırsız okuyup yazabilir. "
                      "Tabloya RLS açılmalı ve kural yazılmalı."))

    cg = zaman((tablolar.get("canli_guc") or {}).get("son_kayit"))
    if cg is not None and (simdi - cg).total_seconds() / 60 > CANLI_VERI_DIKKAT_DK:
        cikti.append(("dikkat", "Canlı güç verisi %s geldi" % once(cg, simdi),
                      "Lokasyonlardan dakikalık veri akışı durmuş olabilir "
                      "(lokasyon PC'si, ağ ya da cloud_sync)."))

    ed = zaman((tablolar.get("energy_data") or {}).get("son_kayit"))
    if ed is not None and (simdi.date() - ed.date()).days > 1:
        cikti.append(("dikkat", "Son günlük enerji satırı %s" % ed.strftime("%d.%m.%Y"),
                      "Dünün satırı gelmemiş. data_bridge (00:05) ya da cloud_sync kontrol edilmeli."))

    kilit = veri.get("bekleyen_kilit") or 0
    if kilit:
        cikti.append(("dikkat", "%d sorgu kilit bekliyor" % kilit,
                      "Uzun süren bir işlem tabloyu tutuyor olabilir."))

    ist = veri.get("istatistik") or {}
    if ist.get("kilitlenme"):
        cikti.append(("dikkat", "%s kilitlenme (deadlock)" % ist["kilitlenme"],
                      "Eşzamanlı yazımlar çakışmış (istatistik sıfırlandığından beri)."))

    if yedek_listesi is not None:
        if not yedek_listesi:
            cikti.append(("dikkat", "Gece yedeği görülemedi",
                          "%s okunamadı ya da synapse_db yedeği yok." % YEDEK_KLASORU))
        else:
            yas = (simdi - yedek_listesi[0]["zaman"]).total_seconds() / 3600
            if yas > YEDEK_DIKKAT_SAAT:
                cikti.append(("kritik" if yas > 2 * YEDEK_DIKKAT_SAAT else "dikkat",
                              "Son gece yedeği %s" % once(yedek_listesi[0]["zaman"], simdi),
                              "01:30 yedeği alınmamış görünüyor (/opt/Backup/Backup_Synapse.sh)."))

    if disk_bilgisi:
        kul, top, _ = disk_bilgisi
        oran = kul / top * 100 if top else 0
        if oran >= DISK_KRITIK_YUZDE:
            cikti.append(("kritik", "Sunucu diski %%%.0f dolu" % oran,
                          "Disk dolarsa veritabanı yazamaz; lokasyon senkronu durur."))
        elif oran >= DISK_DIKKAT_YUZDE:
            cikti.append(("dikkat", "Sunucu diski %%%.0f dolu" % oran, "Büyümeyi izleyin."))

    if not cikti:
        # Yalnızca gerçekten kontrol edileni söyle (yedek/disk okunamadıysa iddia etme)
        parca = ["erişim kuralları açık", "veri akışı güncel", "kilit yok"]
        if yedek_listesi:
            parca.append("gece yedeği alınmış")
        if disk_bilgisi:
            parca.append("disk yeterli")
        cikti.append(("iyi", "Veritabanı sağlıklı", ", ".join(parca).capitalize() + "."))
    return cikti


def baglanti_ozeti(veri):
    """'4 (PostgREST 3, psql 1)'"""
    b = veri.get("baglantilar") or []
    top = sum(x.get("adet") or 0 for x in b)
    parca = ", ".join("%s %s" % ((x.get("uygulama") or x.get("kullanici") or "?").split(" ")[0],
                                 x.get("adet")) for x in b)
    return top, parca
