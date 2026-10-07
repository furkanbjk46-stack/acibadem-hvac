# -*- coding: utf-8 -*-
"""
VERİ TOPLAMA ALARMLARI — tek kaynak
===================================

Analizörlerden (MCC / trafo / chiller / kule) veri gelmediğinde alarm üretir.
Üç yer aynı listeyi kullanır:

  * app_portal.py   → Enerji portalındaki bildirim çubuğu
  * cloud_sync.py   → heartbeat (bakim_ozet.veri_alarm) → Synapse CANLI UYARILAR
  * bildirimler     → Supabase bildirim kaydı (portalda mesaj olarak da görünür)

NEDEN AYRI MODÜL: Aynı tespiti üç yerde tekrar yazmak, birinin eşiği değişince
diğerlerinin sessizce ayrışması demekti. Tespit burada, gösterim orada.

İKİ FARKLI SORUN AYRILIR:
  bağlantı : cihaz okunamadı (Modbus bağlantı hatası) — sayaç/ağ sorunu
  veri_yok : cihaz okundu ama günlük tüketim hesaplanamadı (referans yok,
             sayaç sıfırlandı, tarih uyumsuz) — veri boş kalır

ÖNEM: Trafo ve chiller eksikse KRİTİK — şebeke ve soğutma hesabı bozulur
(27.09'daki çift sayım tam bu yüzden fark edilmemişti). MCC/kule eksikse
UYARI: kırılım eksilir ama toplam hesabı ayakta kalır.
"""

import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODBUS_CSV = os.path.join(BASE_DIR, "analizor_guncel_veriler.csv")
DURUM_DOSYA = os.path.join(BASE_DIR, "configs", "veri_alarmlari.json")

# Cihaz adından grup: önem ve mesaj bundan belirlenir
GRUPLAR = (
    ("TRDP", "trafo", "kritik"),
    ("CHILLER", "chiller", "kritik"),
    ("KULE", "kule", "uyari"),
    ("MCC", "mcc", "uyari"),
)
GRUP_ETIKET = {"trafo": "Trafo", "chiller": "Chiller", "kule": "Soğutma kulesi",
               "mcc": "MCC panosu", "diger": "Analizör"}


def _grup(cihaz_adi: str):
    ad = (cihaz_adi or "").upper()
    for onek, grup, onem in GRUPLAR:
        if onek in ad:
            return grup, onem
    return "diger", "uyari"


def csv_durumlari(yol: str = None) -> dict:
    """analizor_guncel_veriler.csv → {cihaz: durum metni}.

    data_collector her turda bu dosyayı yeniden yazar; okunamayan cihaz için
    Durum alanına "[Baglanti Hatasi]" yazar.
    """
    import csv as _csv
    yol = yol or MODBUS_CSV
    cikti = {}
    if not os.path.exists(yol):
        return cikti
    try:
        with open(yol, newline="", encoding="utf-8") as f:
            for satir in _csv.DictReader(f):
                ad = (satir.get("Cihaz_Adi") or "").strip()
                if ad:
                    cikti[ad] = (satir.get("Durum") or "").strip()
    except Exception:
        pass
    return cikti


def alarm_uret(analizorler, csv_durum, daily_kwh, tarih=None) -> list:
    """Alarm listesi döner: [{tur, grup, onem, cihazlar, mesaj}].

    analizorler : data_collector.ANALYZERS (ad listesi de olabilir)
    csv_durum   : csv_durumlari() çıktısı
    daily_kwh   : data_bridge.calc_daily_kwh() çıktısı (None/False olabilir)
    """
    adlar = [a["name"] if isinstance(a, dict) else str(a) for a in (analizorler or [])]
    gunluk = daily_kwh if isinstance(daily_kwh, dict) else {}

    baglanti, veri_yok = {}, {}
    for ad in adlar:
        durum = csv_durum.get(ad)
        grup, onem = _grup(ad)
        if durum is None or "hata" in durum.lower():
            # Hiç okunamadı ya da bağlantı hatası
            baglanti.setdefault((grup, onem), []).append(ad)
            continue
        deger = gunluk.get(ad)
        if deger is None or deger == "":
            # Okundu ama günlük fark üretilemedi
            veri_yok.setdefault((grup, onem), []).append(ad)

    tarih = tarih or datetime.now().strftime("%Y-%m-%d")
    alarmlar = []
    for tur, sozluk, kalip in (
        ("baglanti", baglanti, "%s bağlantı hatası: %s"),
        ("veri_yok", veri_yok, "%s günlük verisi boş: %s"),
    ):
        for (grup, onem), cihazlar in sorted(sozluk.items()):
            cihazlar = sorted(cihazlar)
            gorunen = ", ".join(cihazlar[:4]) + ("…" if len(cihazlar) > 4 else "")
            alarmlar.append({
                "tur": tur,
                "grup": grup,
                "onem": onem,
                "tarih": tarih,
                "cihazlar": cihazlar,
                "mesaj": kalip % (GRUP_ETIKET.get(grup, "Analizör"), gorunen),
            })
    # Kritikler önce
    alarmlar.sort(key=lambda a: (a["onem"] != "kritik", a["tur"], a["grup"]))
    return alarmlar


def ozet(alarmlar) -> dict:
    """Heartbeat'e konacak KÜÇÜK özet (bakim_ozet JSONB'si şişmesin)."""
    alarmlar = alarmlar or []
    return {
        "toplam": len(alarmlar),
        "kritik": sum(1 for a in alarmlar if a.get("onem") == "kritik"),
        "baglanti": sorted({c for a in alarmlar if a.get("tur") == "baglanti"
                            for c in a.get("cihazlar", [])})[:8],
        "veri_yok": sorted({c for a in alarmlar if a.get("tur") == "veri_yok"
                            for c in a.get("cihazlar", [])})[:8],
        "mesajlar": [a["mesaj"] for a in alarmlar[:4]],
        "zaman": datetime.now().isoformat(timespec="seconds"),
    }


def kaydet(alarmlar) -> dict:
    """Alarmları configs/veri_alarmlari.json'a yazar ve özeti döner."""
    veri = {"alarmlar": alarmlar or [], "ozet": ozet(alarmlar)}
    try:
        os.makedirs(os.path.dirname(DURUM_DOSYA), exist_ok=True)
        gecici = DURUM_DOSYA + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
        os.replace(gecici, DURUM_DOSYA)
    except Exception:
        pass
    return veri["ozet"]


def oku() -> dict:
    """Son kaydedilen alarm durumu. Dosya yoksa boş yapı döner."""
    try:
        with open(DURUM_DOSYA, encoding="utf-8") as f:
            veri = json.load(f)
        if isinstance(veri, dict):
            veri.setdefault("alarmlar", [])
            veri.setdefault("ozet", ozet(veri["alarmlar"]))
            return veri
    except Exception:
        pass
    return {"alarmlar": [], "ozet": ozet([])}


def son_ozet() -> dict:
    """cloud_sync heartbeat için: yalnızca özet (alarm yoksa boş sözlük)."""
    o = oku().get("ozet") or {}
    return o if o.get("toplam") else {}


def _imza(alarmlar) -> str:
    """Aynı alarm için günde bir kez bildirim: tarih + cihaz listesi."""
    parcalar = ["%s:%s:%s" % (a.get("tarih", ""), a.get("tur"), ",".join(a.get("cihazlar", [])))
                for a in (alarmlar or [])]
    return "|".join(sorted(parcalar))


def bildirim_gonder(sb_url, sb_key, lokasyon_id, alarmlar, _imza_dosya=None) -> bool:
    """Supabase `bildirimler` tablosuna tek bir kayıt atar.

    Aynı alarm tekrar tekrar bildirilmez: imza değişmedikçe sessiz kalır
    (veri toplama her gün çalışır, aynı arızalı sayaç her gün yeni bildirim
    üretirse mesaj kutusu kullanılamaz hale gelir).
    """
    import urllib.request
    if not (alarmlar and sb_url and sb_key):
        return False
    imza_dosya = _imza_dosya or os.path.join(BASE_DIR, "configs", "veri_alarm_imza.txt")
    yeni = _imza(alarmlar)
    try:
        with open(imza_dosya, encoding="utf-8") as f:
            if f.read().strip() == yeni:
                return False            # aynı durum, tekrar bildirme
    except Exception:
        pass

    kritik = [a for a in alarmlar if a.get("onem") == "kritik"]
    mesaj = ("⚠️ Veri toplama alarmı — %d uyarı%s\n" % (len(alarmlar),
             (", %d KRİTİK" % len(kritik)) if kritik else "")
             + "\n".join("• " + a["mesaj"] for a in alarmlar[:6]))
    if kritik:
        mesaj += "\nKritik: trafo/chiller verisi eksikken şebeke ve soğutma hesabı eksik kalır."

    veri = json.dumps({
        "lokasyon": lokasyon_id,
        "mesaj": mesaj,
        "gonderen": "Veri Toplama",
        "oncelik": "yuksek" if kritik else "normal",
        "okundu": False,
    }).encode("utf-8")
    try:
        istek = urllib.request.Request(
            sb_url.rstrip("/") + "/rest/v1/bildirimler", data=veri,
            headers={"apikey": sb_key, "Authorization": "Bearer " + sb_key,
                     "Content-Type": "application/json", "Prefer": "return=minimal"},
            method="POST")
        urllib.request.urlopen(istek, timeout=8)
    except Exception:
        return False
    try:
        os.makedirs(os.path.dirname(imza_dosya), exist_ok=True)
        with open(imza_dosya, "w", encoding="utf-8") as f:
            f.write(yeni)
    except Exception:
        pass
    return True


def kontrol_et(daily_kwh, tarih=None, sb_url=None, sb_key=None, lokasyon_id=None) -> dict:
    """Tek çağrı: tespit + kaydet + (varsa) bildir. Özet döner.

    data_bridge.run_daily_snapshot() sonunda çağrılır.
    """
    try:
        import data_collector as dc
        analizorler = dc.ANALYZERS
    except Exception:
        analizorler = []
    alarmlar = alarm_uret(analizorler, csv_durumlari(), daily_kwh, tarih)
    o = kaydet(alarmlar)
    if alarmlar and sb_url and sb_key and lokasyon_id:
        bildirim_gonder(sb_url, sb_key, lokasyon_id, alarmlar)
    return o
