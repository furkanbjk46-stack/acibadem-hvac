# -*- coding: utf-8 -*-
"""
OTO-SET — LOKASYON TARAFI KARAR MOTORU
======================================

NEDEN BU MODÜL VAR:
Oto-set kararı önce merkez portalda (Streamlit) veriliyordu. Streamlit Cloud
kimse kullanmayınca uygulamayı UYUTUYOR; arka plan döngüsü de onunla birlikte
duruyor. Sonuç: setler belirlenen saatte değil, biri portalı açtığında
gidiyordu. Sahadan ölçülen gerçek örnekler (ayar 08:00 / 23:00):

    31.08 00:32   <- 23:00 olmalıydı (1.5 saat geç)
    30.08 08:56   <- 08:00 olmalıydı
    29.08 11:35   <- hiçbir geçiş saati değil

Lokasyon PC'si 7/24 açık ve zaten 1 dakikalık bir döngü çalıştırıyor; karar
burada verilince setler tam saatinde gider.

GÖREV DAĞILIMI
    merkez   -> KURALI yayınlar (saatler, açık/kapalı)      [ayarlar tablosu]
    lokasyon -> kuralı uygular, setpoint'i BACnet'e yazar   [bu modül]

NEDEN `komutlar` TABLOSU KULLANILMIYOR:
Güvenlik çalışmasında anon anahtarın `komutlar` tablosuna yazma yetkisi
kapatıldı (GitHub'da açık olan bu anahtarla hastane BMS'ine setpoint
yazılabiliyordu). Lokasyon da aynı anahtarı kullandığı için o tabloya
yazamaz — ve yeniden açmak kazanılan güvenliği geri verirdi. Bunun yerine
setpoint doğrudan BACnet'e yazılır; denetim izi `oto_mod_log`'a düşer.

DURUM YERELDE TUTULUR (configs/oto_set_durum.json): böylece buluta yazma
yetkisi gerekmez ve her lokasyon kendi durumunu bağımsız yönetir.
"""

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_BASE = os.path.dirname(os.path.abspath(__file__))
DURUM_FILE = os.path.join(_BASE, "configs", "oto_set_durum.json")

# ── Kural varsayılanları (merkez ile birebir aynı olmalı) ──────────────────
CH_SINIRLAR = [7.0, 23.0, 26.0]
CH_MODLAR   = ["koc_soguk", "serin", "ilimli", "sicak"]
CH_SET      = {"koc_soguk": 8.0, "serin": 7.5, "ilimli": 7.0, "sicak": 6.5}
CH_H        = 2.0

DIG_ESIK = 23.0
DIG_H    = 3.0
DIG_SET  = {
    "sogutma": {"GUNDUZ_KOLLEKTOR_SET": 8.0, "GECE_KOLLEKTOR_SET": 10.0,
                "A_BLOK_FCU_SET": 12.0, "B_BLOK_FCU_SET": 12.0,
                "ZON1_KLIMA_SANTRALI_SET": 8.0, "ZON2_KLIMA_SANTRALI_SET": 8.0},
    "isitma":  {"GUNDUZ_KOLLEKTOR_SET": 10.0, "GECE_KOLLEKTOR_SET": 12.0,
                "A_BLOK_FCU_SET": 14.0, "B_BLOK_FCU_SET": 14.0,
                "ZON1_KLIMA_SANTRALI_SET": 10.0, "ZON2_KLIMA_SANTRALI_SET": 10.0},
}
CH_NOKTALAR = ["CH1_REM_SET", "CH2_REM_SET", "CH3_REM_SET", "CH4_REM_SET", "CH5_REM_SET"]

# NOT: Varsayılan geçiş saati BİLEREK YOK. Önceden ayar okunamazsa 05:00/22:00
# kullanılıyordu; 12.09'da anlık bir ağ hatasında gece geçişi 23:00 yerine
# 22:41'de yapıldı, bir dakika sonra geri dönüldü (sahaya 3 set turu gitti).
# Kural okunamazsa o tur hiçbir şey yapılmaz — bkz. _kural_oku.
KURAL_ANAHTARLARI = ("oto_set_aktif", "oto_gunduz_saat", "oto_gece_saat")

_tahmin_onbellek = {"zaman": None, "veri": None}
_TAHMIN_OMRU_DK = 30


# ══════════════════════════════════════════════════════════════════════════
# Supabase okuma (stdlib; ek bağımlılık yok) — YALNIZCA OKUMA
# ══════════════════════════════════════════════════════════════════════════
def _istek(url, key, yol, veri=None, method="GET", timeout=10):
    h = {"apikey": key, "Authorization": "Bearer " + key,
         "Content-Type": "application/json"}
    if method == "POST":
        h["Prefer"] = "return=minimal"
    d = json.dumps(veri).encode() if veri is not None else None
    r = urllib.request.Request(url + yol, data=d, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as y:
        govde = y.read().decode()
        return json.loads(govde) if govde.strip() else []


def _kural_oku(url, key):
    """Merkezdeki oto-set kuralını TEK istekte okur. (kural | None, sebep) döner.

    Önceki sürüm önce "erişilebiliyor mu" diye bir istek atıyor, sonra her
    ayarı ayrı istekle okuyordu; ilk istek geçip sonrakilerden biri anlık
    ağ hatasına düşerse o ayar SESSİZCE varsayılana (05:00/22:00) dönüyordu.
    Artık üç ayar birlikte gelir; biri eksik ya da bozuksa kural YOK sayılır.
    """
    try:
        d = _istek(url, key, "/rest/v1/ayarlar?key=like.oto_*&select=key,value")
    except Exception as e:
        return None, "ağ/izin hatası: %s" % e
    ayar = {r.get("key"): r.get("value") for r in (d or []) if isinstance(r, dict)}
    eksik = [k for k in KURAL_ANAHTARLARI if ayar.get(k) in (None, "")]
    if eksik:
        return None, "eksik ayar: %s" % ", ".join(eksik)
    try:
        gunduz = int(float(ayar["oto_gunduz_saat"]))
        gece = int(float(ayar["oto_gece_saat"]))
    except (TypeError, ValueError):
        return None, "saat ayarı sayı değil"
    if not (0 <= gunduz <= 23 and 0 <= gece <= 23):
        return None, "saat ayarı 0-23 dışında"
    return {"aktif": str(ayar["oto_set_aktif"]).strip().lower() == "true",
            "gunduz_saat": gunduz, "gece_saat": gece}, ""


# ══════════════════════════════════════════════════════════════════════════
# Yerel durum
# ══════════════════════════════════════════════════════════════════════════
def durum_oku():
    try:
        with open(DURUM_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def durum_yaz(d):
    try:
        os.makedirs(os.path.dirname(DURUM_FILE), exist_ok=True)
        with open(DURUM_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("oto_set durum yazilamadi: %s", e)


# ══════════════════════════════════════════════════════════════════════════
# GÖRÜNÜRLÜK — "neden komut gitmedi?" sorusunun cevabı
#
# İlk sürümde kontrolün DÖRT çıkış yolu da sessizce return ediyordu (kural
# okunamadı / oto-set kapalı / dönem değişmedi / tahmin yok). Saha kurulumunda
# cloud_sync logu yalnızca konsola yazdığı ve o konsol kimsede görünmediği
# için sistem 10 gün boyunca sessizce durdu ve kimse fark etmedi.
#
# Artık her tur bir SONUÇ bırakır; heartbeat bunu Supabase'e taşır ve merkez
# portal kartta gösterir. Ek RLS izni gerekmez — `lokasyonlar` satırına
# yazma yetkisi zaten var.
# ══════════════════════════════════════════════════════════════════════════
_SON_SONUC = {"zaman": None, "sonuc": "henuz_calismadi", "aciklama": ""}

# Kullanıcıya gösterilecek metinler
SONUC_METIN = {
    "henuz_calismadi":  "Henüz çalışmadı",
    "kural_okunamadi":  "Merkezdeki kural okunamıyor (ağ/izin)",
    "kapali":           "Oto-set kapalı",
    "gecis_yok":        "Bekliyor — geçiş saati değil",
    "tahmin_yok":       "Hava tahmini alınamadı, geçiş ertelendi",
    "nokta_yok":        "Bu lokasyon için tanımlı set noktası yok",
    "yazildi":          "Setler gönderildi — cihazdan doğrulama bekleniyor",
    "yazma_hatasi":     "BACnet yazma hatası",
    "sahada_farkli":    "Yazıldı ama cihazda farklı değer var",
    "dogrulanamadi":    "Yazıldı ama cihazdan geri okunamadı",
    "mesgul":           "Başka bir tur çalışıyor, bu tur atlandı",
    "hata":             "Beklenmeyen hata",
}

# Gönderilen setlerin cihazda gerçekten uygulanıp uygulanmadığı (gecikmeli geri okuma)
DOGRULAMA_METIN = {
    "bekliyor":    "Setlerin cihazda uygulanması bekleniyor",
    "uygulandi":   "Tüm setler cihazda uygulandı",
    "uygulanmadi": "Bazı setler cihazda UYGULANMADI",
}
# GECİKMELİ GERİ OKUMA (21.09.2026):
# Komutu gönderdiğimiz AN cihaz henüz yeni değeri almamış olur; o anki okuma
# ESKİ değeri döndürür (sahada gözlendi: CH5'e 6.5 gitti, anında IC SET 7.5 okundu).
# Bu yüzden karar yazmadan hemen sonra DEĞİL, ILK_DOGRULAMA_DK dakika sonra verilir.
# Chiller'larda "gerçekleşen" nokta (IC SET) okunur; karşılığı olmayan noktalarda
# (kollektör / FCU setleri) yazılan noktanın kendisi tekrar okunur.
# Uymayan nokta IC_IZLEME_DK dolana kadar her dakika yeniden denenir.
ILK_DOGRULAMA_DK = 3
IC_IZLEME_DK = 15
DOGRULAMA_TOLERANS = 0.05


def _sonuc_yaz(sonuc, aciklama=""):
    _SON_SONUC.update({"zaman": datetime.now().isoformat(timespec="seconds"),
                       "sonuc": sonuc, "aciklama": str(aciklama)[:200]})
    if sonuc not in ("gecis_yok", "yazildi", "mesgul"):
        logger.warning("oto_set: %s %s", SONUC_METIN.get(sonuc, sonuc), aciklama)
    return _SON_SONUC


def durum_ozet():
    """Heartbeat'in Supabase'e taşıyacağı küçük özet."""
    d = durum_oku()
    return {
        "zaman": _SON_SONUC["zaman"],
        "sonuc": _SON_SONUC["sonuc"],
        "metin": SONUC_METIN.get(_SON_SONUC["sonuc"], _SON_SONUC["sonuc"]),
        "aciklama": _SON_SONUC["aciklama"],
        "donem": d.get("donem"),
        "chiller_mod": d.get("chiller_mod"),
        "diger_mod": d.get("diger_mod"),
        "son_yazim": d.get("zaman"),
        # Son geçişin sahadaki sonucu — "sonuc" her dakika "gecis_yok" ile
        # güncellendiği için geçişteki sorun burada KALICI tutulur.
        "son_yazim_sonuc": d.get("son_yazim_sonuc"),
        "saha": d.get("saha"),
        "dogrulama": ({
            "sonuc": d["dogrulama"].get("sonuc"),
            "metin": DOGRULAMA_METIN.get(d["dogrulama"].get("sonuc"), ""),
            "okunan": d["dogrulama"].get("okunan"),
            "uymayan": d["dogrulama"].get("uymayan"),
        } if isinstance(d.get("dogrulama"), dict) else None),
    }


_ADRES_ALANLARI = ("gateway_ip", "dnet", "mac_hex", "obj_type", "obj_inst")


def _adres(n):
    """Nokta sözlüğünden yalnızca BACnet adresini alır (durum dosyasına yazılabilir)."""
    try:
        return {k: n[k] for k in _ADRES_ALANLARI}
    except Exception:
        return None


def _dogrulama_baslat(detay, harita, etiket, simdi):
    """Yazması kabul edilen (ACK) HER nokta için gecikmeli doğrulama kaydı kurar.

    Okunacak nokta: chiller'da "gerçekleşen" nokta (IC SET, configs/geri_okuma.json);
    karşılığı yoksa yazılan noktanın kendisi.
    """
    noktalar = {}
    for ad, s in detay.items():
        if not s.get("yazma_ok"):
            continue
        ic = harita.get(ad)
        if ic:
            adres, kaynak = _adres(ic), ic.get("okuma_noktasi") or "IC SET"
        else:
            adres, kaynak = s.get("adres"), "yazılan nokta"
        noktalar[ad] = {"hedef": s["deger"], "adres": adres, "kaynak": kaynak,
                        "durum": "bekliyor", "okunan": None}
    if not noktalar:
        return None
    return {"sonuc": "bekliyor", "baslangic": simdi.isoformat(timespec="seconds"),
            "etiket": etiket, "noktalar": noktalar,
            "hedefler": {ad: p["hedef"] for ad, p in noktalar.items()},
            "okunan": {}, "uymayan": []}


def _dogrulama_logu_yaz(sb_url, sb_key, lokasyon_id, d, bitenler, gecen):
    """Doğrulaması SONUÇLANAN noktaları komutlar tablosuna yazar.

    Uzaktan Kontrol listesindeki satır artık GERÇEK sonucu gösterir: gönderimden
    birkaç dakika sonra cihazdan okunan değer. (Eskiden satır gönderim anında
    yazılıyor ve o an okunan ESKİ IC SET'i gösteriyordu.)
    """
    if not bitenler or not sb_url:
        return
    etiket = d.get("etiket") or ""
    simdi = datetime.now(timezone.utc).isoformat()
    satirlar = []
    for ad, p in bitenler.items():
        if p["durum"] == "dogrulandi":
            durum_k = "tamamlandi"
            mesaj = "%.0f dk sonra cihazda doğrulandı: %s (%s)" % (gecen, p["okunan"], p["kaynak"])
        elif p["durum"] == "okunamadi":
            durum_k = "dogrulanamadi"
            mesaj = "%d dk boyunca cihazdan geri okunamadı (%s)" % (IC_IZLEME_DK, p["kaynak"])
        else:
            durum_k = "hata"
            mesaj = ("%d dk içinde UYGULANMADI — cihazda %s okundu (%s), hedef %s"
                     % (IC_IZLEME_DK, p["okunan"], p["kaynak"], p["hedef"]))
        satirlar.append({
            "lokasyon": lokasyon_id, "nokta_adi": ad, "hedef_deger": p["hedef"],
            "durum": durum_k,
            "hata_mesaji": "%s · %s · %s" % (OTO_KOMUT_ONEK, etiket, mesaj),
            "executed_at": simdi,
        })
    try:
        _istek(sb_url, sb_key, "/rest/v1/komutlar", veri=satirlar, method="POST")
    except Exception as e:
        logger.warning("oto_set dogrulama logu yazilamadi: %s", e)


def _ic_dogrulama_ilerlet(durum, lokasyon_id, simdi, sb_url=None, sb_key=None):
    """Geçişten sonraki dakikalarda gönderilen setleri cihazdan GERİ OKUR.

    - ILK_DOGRULAMA_DK dolmadan okuma yapılmaz: cihaz yeni değeri henüz almamış
      olur, anlık okuma eski değeri döndürür.
    - Tutan nokta hemen "doğrulandı" olur ve komut listesine yazılır.
    - Tutmayan nokta IC_IZLEME_DK dolana kadar her dakika yeniden okunur; süre
      dolunca "uygulanmadı" (okunduysa) ya da "okunamadı" olarak kapanır.
    Beklemeye kilitlenmez: kontrol() her dakika çağrılır, bu fonksiyon bir kez okur.
    """
    d = durum.get("dogrulama")
    if not isinstance(d, dict) or d.get("sonuc") != "bekliyor":
        return
    noktalar = d.get("noktalar")
    if not isinstance(noktalar, dict):
        # Eski sürümden (v8.5 öncesi) kalan kayıt: yeni biçime çevrilir.
        try:
            from bacnet_writer import geri_okuma_haritasi
            harita = geri_okuma_haritasi(lokasyon_id)
        except Exception:
            harita = {}
        noktalar = {ad: {"hedef": h, "adres": _adres(harita[ad]) if ad in harita else None,
                         "kaynak": "IC SET", "durum": "bekliyor", "okunan": None}
                    for ad, h in (d.get("hedefler") or {}).items()}
        d["noktalar"] = noktalar

    try:
        gecen = (simdi - datetime.fromisoformat(d["baslangic"])).total_seconds() / 60
    except Exception:
        gecen = IC_IZLEME_DK + 1
    if gecen < ILK_DOGRULAMA_DK:
        return                                  # cihaza zaman tanı

    try:
        from bacnet_writer import bacnet_oku
    except Exception:
        return

    bitenler = {}
    for ad, p in noktalar.items():
        if p.get("durum") != "bekliyor":
            continue
        a = p.get("adres")
        if a:
            ok, val = bacnet_oku(a["gateway_ip"], a["dnet"], a["mac_hex"],
                                 a["obj_type"], a["obj_inst"])
        else:
            ok, val = False, "adres yok"
        p["okunan"] = round(float(val), 2) if ok else None
        if ok and abs(float(val) - float(p["hedef"])) <= DOGRULAMA_TOLERANS:
            p["durum"] = "dogrulandi"
            bitenler[ad] = p
        elif gecen >= IC_IZLEME_DK:
            p["durum"] = "uygulanmadi" if ok else "okunamadi"
            bitenler[ad] = p

    d["okunan"] = {ad: p.get("okunan") for ad, p in noktalar.items()}
    d["son_kontrol"] = simdi.isoformat(timespec="seconds")
    _dogrulama_logu_yaz(sb_url, sb_key, lokasyon_id, d, bitenler, gecen)

    if all(p.get("durum") != "bekliyor" for p in noktalar.values()):
        uymayan = [ad for ad, p in noktalar.items() if p.get("durum") != "dogrulandi"]
        d["uymayan"] = uymayan
        d["sonuc"] = "uygulanmadi" if uymayan else "uygulandi"
        if uymayan:
            logger.warning("oto_set: %d dk sonra setler UYGULANMADI — %s (okunan %s)",
                           IC_IZLEME_DK, uymayan, d["okunan"])
        else:
            logger.info("oto_set: tüm setler cihazda doğrulandı (%s)", d["okunan"])
    durum["dogrulama"] = d
    durum_yaz(durum)


# ══════════════════════════════════════════════════════════════════════════
# Karar mantığı — merkez ile birebir aynı
# ══════════════════════════════════════════════════════════════════════════
def donem_hesapla(saat, gunduz_saat, gece_saat):
    """Saate göre dönem. Gece yarısını aşan aralıklar da desteklenir."""
    if gunduz_saat == gece_saat:
        return "gunduz"
    if gunduz_saat < gece_saat:
        return "gunduz" if gunduz_saat <= saat < gece_saat else "gece"
    return "gunduz" if (saat >= gunduz_saat or saat < gece_saat) else "gece"


def _hedef_bolge(ort):
    for i, sinir in enumerate(CH_SINIRLAR):
        if ort < sinir:
            return CH_MODLAR[i]
    return CH_MODLAR[-1]


def ch_modu_hesapla(ort, mevcut):
    """4 bölgeli chiller modu — ±2°C histerezis, KADEMESİZ geçiş."""
    if mevcut in CH_MODLAR:
        idx = CH_MODLAR.index(mevcut)
        ust = CH_SINIRLAR[idx]     if idx < len(CH_SINIRLAR) else None
        alt = CH_SINIRLAR[idx - 1] if idx > 0                else None
        cikis = ((ust is not None and ort > ust + CH_H) or
                 (alt is not None and ort < alt - CH_H))
        if not cikis:
            return mevcut
    return _hedef_bolge(ort)


def dig_modu_hesapla(ort, mevcut):
    """Kollektör/FCU/AHU ikili mod — ±3°C histerezis."""
    if mevcut == "sogutma":
        return "isitma" if ort < DIG_ESIK - DIG_H else "sogutma"
    if mevcut == "isitma":
        return "sogutma" if ort > DIG_ESIK + DIG_H else "isitma"
    return "sogutma" if ort >= DIG_ESIK else "isitma"


def tahmin_al(zorla=False):
    """Bugünün max, yarının min sıcaklığı (30 dk önbellekli).

    Gündüz seti BUGÜNÜN max'ına, gece seti YARININ min'ine bakar: sabah
    başlayan gündüz bugünün gündüzüdür; akşam başlayan gece takvimde yarına
    sarkar ve en düşük sıcaklık yarın sabaha doğru oluşur.
    """
    simdi = datetime.now()
    if (not zorla and _tahmin_onbellek["veri"] and _tahmin_onbellek["zaman"] and
            (simdi - _tahmin_onbellek["zaman"]) < timedelta(minutes=_TAHMIN_OMRU_DK)):
        return _tahmin_onbellek["veri"]
    try:
        api = ("https://api.open-meteo.com/v1/forecast"
               "?latitude=41.0082&longitude=28.9784"
               "&daily=temperature_2m_max,temperature_2m_min"
               "&timezone=Europe%2FIstanbul&forecast_days=3")
        with urllib.request.urlopen(api, timeout=10) as r:
            d = json.loads(r.read())
        veri = {"bugun_max": round(d["daily"]["temperature_2m_max"][0], 1),
                "yarin_min": round(d["daily"]["temperature_2m_min"][1], 1)}
        _tahmin_onbellek.update({"zaman": simdi, "veri": veri})
        return veri
    except Exception as e:
        logger.warning("oto_set tahmin alinamadi: %s", e)
        return _tahmin_onbellek["veri"]


# ══════════════════════════════════════════════════════════════════════════
# ANA KONTROL — cloud_sync döngüsünden her dakika çağrılır
# ══════════════════════════════════════════════════════════════════════════
def kontrol(sb_url, sb_key, lokasyon_id):
    """Her dakika çağrılır; kararı KİLİT altında verir.

    Aynı geçiş saniyeler arayla 2-3 kez uygulanıyordu: birden fazla döngü aynı
    anda durum dosyasını okuyup "geçiş var" diyor, hepsi sahaya yazıyordu.
    Kilit başka bir tur tarafından tutuluyorsa bu tur hiçbir şey yapmadan
    atlanır ("mesgul"); bir dakika sonra durum dosyası güncel olarak okunur.
    """
    try:
        from kilit import kisa_kilit
    except Exception:
        return _kontrol_kilitsiz(sb_url, sb_key, lokasyon_id)   # kilit modülü yoksa eski davranış
    with kisa_kilit("oto_set") as alindi:
        if not alindi:
            _sonuc_yaz("mesgul")
            return
        return _kontrol_kilitsiz(sb_url, sb_key, lokasyon_id)


def _kontrol_kilitsiz(sb_url, sb_key, lokasyon_id):
    """Dönem geçişi olduysa setpoint'leri BACnet ile yazar.

    Komut YALNIZCA dönem geçişinde üretilir. Gün ortasında hava tahmini
    değişse bile set gitmez; bir sonraki geçişte uygulanır.
    """
    try:
        # Kural okunamıyorsa (RLS izni yok / ağ yok / ayar eksik) hiçbir şey
        # yapılmaz. Varsayılan saatlerle çalışıp yanlış saatte set göndermektense
        # beklemek güvenlidir — bu fonksiyonun tek tetikleyicisi merkezdeki kuraldır.
        kural, sebep = _kural_oku(sb_url, sb_key)
        if kural is None:
            _sonuc_yaz("kural_okunamadi", sebep)
            return

        if not kural["aktif"]:
            _sonuc_yaz("kapali")
            return

        gunduz_saat = kural["gunduz_saat"]
        gece_saat   = kural["gece_saat"]

        # Lokasyon PC'si Türkiye saatinde; yerel saat doğrudan kullanılır.
        simdi = datetime.now()
        donem = donem_hesapla(simdi.hour, gunduz_saat, gece_saat)

        durum = durum_oku()
        if donem == durum.get("donem"):
            _ic_dogrulama_ilerlet(durum, lokasyon_id, simdi, sb_url, sb_key)
            _sonuc_yaz("gecis_yok", "%s · sonraki %02d:00"
                       % (donem, gece_saat if donem == "gunduz" else gunduz_saat))
            return

        tahmin = tahmin_al()
        if not tahmin:
            # Tahmin yoksa geçiş ERTELENİR: yanlış referansla set göndermektense
            # bir sonraki turda tekrar denemek güvenlidir.
            _sonuc_yaz("tahmin_yok", "%s dönemine geçilemedi" % donem)
            return

        ref = tahmin["bugun_max"] if donem == "gunduz" else tahmin["yarin_min"]
        yeni_ch  = ch_modu_hesapla(ref, durum.get("chiller_mod", ""))
        yeni_dig = dig_modu_hesapla(ref, durum.get("diger_mod", ""))

        hedefler = {n: CH_SET[yeni_ch] for n in CH_NOKTALAR}
        hedefler.update(DIG_SET[yeni_dig])

        _etiket = "%s geçişi · chiller=%s · kollektör/FCU=%s" % (
            "gündüz" if donem == "gunduz" else "gece", yeni_ch, yeni_dig)
        yazilan, hatali, detay = _setleri_uygula(sb_url, sb_key, lokasyon_id, hedefler, _etiket)
        if yazilan == 0 and hatali == 0:
            _sonuc_yaz("nokta_yok")
            return                                     # bu lokasyonda nokta yok

        # Geçiş anında YALNIZCA "cihaz yazmayı kabul etti mi (ACK)" bilinir.
        # Sahada gerçekten uygulanıp uygulanmadığı ILK_DOGRULAMA_DK dakika sonra
        # geri okunarak belirlenir (_ic_dogrulama_ilerlet). Anlık okuma karar
        # vermez: cihaz o an yeni değeri henüz almamış olur, eski değer döner.
        kod = "yazma_hatasi" if hatali else "yazildi"
        _sonuc_yaz(kod, "%s · %d gönderildi, %d hata · %d dk sonra cihazdan doğrulanacak"
                   % (donem, yazilan, hatali, ILK_DOGRULAMA_DK))

        try:
            from bacnet_writer import geri_okuma_haritasi
            harita = geri_okuma_haritasi(lokasyon_id)
        except Exception:
            harita = {}

        durum_yaz({
            "donem": donem, "chiller_mod": yeni_ch, "diger_mod": yeni_dig,
            "ref_sicaklik": ref, "bugun_max": tahmin["bugun_max"],
            "yarin_min": tahmin["yarin_min"],
            "zaman": simdi.isoformat(timespec="seconds"),
            "yazilan": yazilan, "hatali": hatali,
            "son_yazim_sonuc": kod,
            "saha": {"gonderildi": yazilan, "hata": hatali},
            "dogrulama": _dogrulama_baslat(detay, harita, _etiket, simdi),
            "gunduz_saat": gunduz_saat, "gece_saat": gece_saat,
        })

        _log_yaz(sb_url, sb_key, lokasyon_id, durum, yeni_ch, yeni_dig, ref, hedefler)

        logger.info("🤖 OTO-SET %s: %s dönemi — chiller=%s (%.1f°C), diger=%s "
                    "— %d nokta yazıldı, %d hata",
                    lokasyon_id, donem, yeni_ch, CH_SET[yeni_ch], yeni_dig,
                    yazilan, hatali)

    except Exception as e:
        _sonuc_yaz("hata", e)


# Uzaktan Kontrol "Son komutlar" listesinde oto-set satırlarını ayırt eden önek.
# merkez/rls_komut_log.sql de bu öneke bakar: lokasyon anahtarı yalnızca bu
# önekli ve SONUÇLANMIŞ kayıt ekleyebilir.
OTO_KOMUT_ONEK = "OTO-SET"
_KOMUT_TABLO_DURUMU = {
    "oturdu":        "tamamlandi",
    "sahada_farkli": "hata",
    "yazma_hatasi":  "hata",
    "dogrulanamadi": "dogrulanamadi",
}


def _komut_logu_yaz(sb_url, sb_key, lokasyon_id, detay, reddedilen, etiket):
    """Her noktaya ne gönderildiğini ve sonucunu `komutlar` tablosuna yazar.

    v7.0'da oto-set lokasyona taşınınca komutlar tablosu kullanılmaz olmuş ve
    "kollektöre kaç derece gitti, chiller'a kaç gitti, ACK geldi mi" bilgisi
    Uzaktan Kontrol ekranından kaybolmuştu. Satırlar sahaya yazma BİTTİKTEN
    sonra, sonuçlanmış durumda eklenir — lokasyon hiçbir zaman `bekliyor`
    komut üretmez (RLS de buna izin vermez).
    Kayıt yazılamazsa geçiş etkilenmez; yalnızca uyarı loglanır.
    """
    simdi = datetime.now(timezone.utc).isoformat()
    satirlar = []
    for ad, s in detay.items():
        mesaj = s.get("mesaj") or ""
        if s.get("ic_okunan") is not None:
            mesaj += " · IC SET: %s" % s["ic_okunan"]
        satirlar.append({
            "lokasyon": lokasyon_id, "nokta_adi": ad, "hedef_deger": s.get("deger"),
            "durum": _KOMUT_TABLO_DURUMU.get(s.get("durum"), "hata"),
            "hata_mesaji": "%s · %s · %s" % (OTO_KOMUT_ONEK, etiket, mesaj),
            "executed_at": simdi,
        })
    for ad, deger, sebep in reddedilen:
        satirlar.append({
            "lokasyon": lokasyon_id, "nokta_adi": ad, "hedef_deger": deger,
            "durum": "hata",
            "hata_mesaji": "%s · %s · Gönderilmedi: %s" % (OTO_KOMUT_ONEK, etiket, sebep),
            "executed_at": simdi,
        })
    if not satirlar:
        return
    try:
        _istek(sb_url, sb_key, "/rest/v1/komutlar", veri=satirlar, method="POST")
    except Exception as e:
        logger.warning("oto_set komut logu yazilamadi (rls_komut_log.sql calistirildi mi?): %s", e)


def _setleri_uygula(sb_url, sb_key, lokasyon_id, hedefler, etiket=""):
    """Setpoint'leri BACnet ile yazar ve cihazdan geri okuyarak doğrular.

    (yazilan, hatali, detay) döner:
      yazilan : cihazın kabul ettiği (SimpleACK) yazma sayısı
      hatali  : reddedilen / cevapsız / değer kapısından geçemeyen
      detay   : {nokta: {durum, mesaj, okunan, deger, yazma_ok}}
    """
    try:
        from bacnet_writer import komut_degeri_gecerli, yaz_dogrula_toplu
    except Exception as e:
        # Sessizce (0,0) dönülürse çağıran bunu "bu lokasyonda nokta yok"
        # sanıyor ve gerçek sebep kayboluyordu. Yükseltilen hata dışarıdaki
        # try/except'te "hata" sonucuna dönüşür ve merkezde görünür.
        raise RuntimeError("bacnet_writer yuklenemedi: %s" % e)

    try:
        noktalar = {n["nokta_adi"]: n for n in _istek(
            sb_url, sb_key,
            "/rest/v1/lokasyon_noktalar?lokasyon=eq.%s"
            "&select=nokta_adi,gateway_ip,dnet,mac_hex,obj_type,obj_inst" % lokasyon_id)}
    except Exception as e:
        logger.warning("oto_set: nokta listesi alinamadi: %s", e)
        return 0, 0, {}

    hatali = 0
    isler = []
    reddedilen = []
    for ad, deger in hedefler.items():
        n = noktalar.get(ad)
        if not n:
            continue                                   # bu lokasyonda yok
        # Değer doğrulama kapısı — elle gönderilen komutlarla aynı koruma
        gecerli, sebep = komut_degeri_gecerli(deger)
        if not gecerli:
            logger.error("oto_set: %s reddedildi — %s", ad, sebep)
            hatali += 1
            reddedilen.append((ad, deger, sebep))
            continue
        isler.append((ad, n, deger))

    if not isler:
        _komut_logu_yaz(sb_url, sb_key, lokasyon_id, {}, reddedilen, etiket)
        return 0, hatali, {}

    # Yazılır. IC SET burada OKUNMAZ: gönderim anında okunan değer eskidir ve
    # komut listesinde yanıltıcı görünüyordu ("IC SET: 7.5"). Gerçekleşen değer
    # birkaç dakika sonra _ic_dogrulama_ilerlet ile okunur.
    detay = yaz_dogrula_toplu(isler)
    adresler = {ad: _adres(n) for ad, n, _d in isler}
    for ad, s in detay.items():
        s["adres"] = adresler.get(ad)
    yazilan = sum(1 for s in detay.values() if s.get("yazma_ok"))
    hatali += sum(1 for s in detay.values() if not s.get("yazma_ok"))
    for ad, s in detay.items():
        if not s.get("yazma_ok"):
            logger.error("oto_set: %s — %s", ad, s.get("mesaj"))
    # Komut listesine şimdi YALNIZCA kesinleşmiş başarısızlıklar yazılır (cihaz
    # reddetti / değer kapısı). Kabul edilenler doğrulama sonuçlanınca yazılır —
    # böylece her nokta için listede tek ve DOĞRU bir satır olur.
    _komut_logu_yaz(sb_url, sb_key, lokasyon_id,
                    {ad: s for ad, s in detay.items() if not s.get("yazma_ok")},
                    reddedilen, etiket)
    return yazilan, hatali, detay


def _log_yaz(sb_url, sb_key, lokasyon_id, eski_durum, yeni_ch, yeni_dig, ref, hedefler):
    """Denetim izi — merkez portal bu kayıtları gösterir."""
    eski_ch  = eski_durum.get("chiller_mod") or yeni_ch
    eski_dig = eski_durum.get("diger_mod") or yeni_dig
    kayitlar = [{
        "tip": "chiller" if yeni_ch != eski_ch else "chiller_yenileme",
        "eski_mod": eski_ch, "yeni_mod": yeni_ch, "tahmin_ort": ref,
        "komut_sayisi": sum(1 for a in hedefler if a in CH_NOKTALAR),
        "lokasyonlar": lokasyon_id,
    }, {
        "tip": "diger" if yeni_dig != eski_dig else "diger_yenileme",
        "eski_mod": eski_dig, "yeni_mod": yeni_dig, "tahmin_ort": ref,
        "komut_sayisi": sum(1 for a in hedefler if a not in CH_NOKTALAR),
        "lokasyonlar": lokasyon_id,
    }]
    try:
        _istek(sb_url, sb_key, "/rest/v1/oto_mod_log", veri=kayitlar, method="POST")
    except Exception as e:
        logger.warning("oto_set log yazilamadi: %s", e)
