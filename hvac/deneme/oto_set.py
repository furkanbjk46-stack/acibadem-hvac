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
from datetime import datetime, timedelta

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

GUNDUZ_VARSAYILAN = 5
GECE_VARSAYILAN   = 22

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


def _ayar_oku(url, key, anahtar, varsayilan=""):
    try:
        d = _istek(url, key, "/rest/v1/ayarlar?key=eq.%s&select=value" % anahtar)
        return d[0]["value"] if d else varsayilan
    except Exception:
        return varsayilan


def _saat_oku(url, key, anahtar, varsayilan):
    try:
        s = int(float(_ayar_oku(url, key, anahtar, "")))
        return s if 0 <= s <= 23 else varsayilan
    except (TypeError, ValueError):
        return varsayilan


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
    """Dönem geçişi olduysa setpoint'leri BACnet ile yazar.

    Komut YALNIZCA dönem geçişinde üretilir. Gün ortasında hava tahmini
    değişse bile set gitmez; bir sonraki geçişte uygulanır.
    """
    try:
        if str(_ayar_oku(sb_url, sb_key, "oto_set_aktif", "true")).lower() != "true":
            return

        gunduz_saat = _saat_oku(sb_url, sb_key, "oto_gunduz_saat", GUNDUZ_VARSAYILAN)
        gece_saat   = _saat_oku(sb_url, sb_key, "oto_gece_saat",   GECE_VARSAYILAN)

        # Lokasyon PC'si Türkiye saatinde; yerel saat doğrudan kullanılır.
        simdi = datetime.now()
        donem = donem_hesapla(simdi.hour, gunduz_saat, gece_saat)

        durum = durum_oku()
        if donem == durum.get("donem"):
            return                                     # geçiş yok → sessiz

        tahmin = tahmin_al()
        if not tahmin:
            # Tahmin yoksa geçiş ERTELENİR: yanlış referansla set göndermektense
            # bir sonraki turda tekrar denemek güvenlidir.
            logger.warning("oto_set: tahmin yok, gecis erteleniyor.")
            return

        ref = tahmin["bugun_max"] if donem == "gunduz" else tahmin["yarin_min"]
        yeni_ch  = ch_modu_hesapla(ref, durum.get("chiller_mod", ""))
        yeni_dig = dig_modu_hesapla(ref, durum.get("diger_mod", ""))

        hedefler = {n: CH_SET[yeni_ch] for n in CH_NOKTALAR}
        hedefler.update(DIG_SET[yeni_dig])

        yazilan, hatali = _setleri_uygula(sb_url, sb_key, lokasyon_id, hedefler)
        if yazilan == 0 and hatali == 0:
            return                                     # bu lokasyonda nokta yok

        durum_yaz({
            "donem": donem, "chiller_mod": yeni_ch, "diger_mod": yeni_dig,
            "ref_sicaklik": ref, "bugun_max": tahmin["bugun_max"],
            "yarin_min": tahmin["yarin_min"],
            "zaman": simdi.isoformat(timespec="seconds"),
            "yazilan": yazilan, "hatali": hatali,
            "gunduz_saat": gunduz_saat, "gece_saat": gece_saat,
        })

        _log_yaz(sb_url, sb_key, lokasyon_id, durum, yeni_ch, yeni_dig, ref, hedefler)

        logger.info("🤖 OTO-SET %s: %s dönemi — chiller=%s (%.1f°C), diger=%s "
                    "— %d nokta yazıldı, %d hata",
                    lokasyon_id, donem, yeni_ch, CH_SET[yeni_ch], yeni_dig,
                    yazilan, hatali)

    except Exception as e:
        logger.warning("oto_set kontrol hatasi: %s", e)


def _setleri_uygula(sb_url, sb_key, lokasyon_id, hedefler):
    """Setpoint'leri BACnet ile yazar. (yazilan, hatali) döner."""
    try:
        from bacnet_writer import bacnet_yaz, komut_degeri_gecerli
    except Exception as e:
        logger.warning("oto_set: bacnet_writer yok (%s)", e)
        return 0, 0

    try:
        noktalar = {n["nokta_adi"]: n for n in _istek(
            sb_url, sb_key,
            "/rest/v1/lokasyon_noktalar?lokasyon=eq.%s"
            "&select=nokta_adi,gateway_ip,dnet,mac_hex,obj_type,obj_inst" % lokasyon_id)}
    except Exception as e:
        logger.warning("oto_set: nokta listesi alinamadi: %s", e)
        return 0, 0

    yazilan = hatali = 0
    for ad, deger in hedefler.items():
        n = noktalar.get(ad)
        if not n:
            continue                                   # bu lokasyonda yok
        # Değer doğrulama kapısı — elle gönderilen komutlarla aynı koruma
        gecerli, sebep = komut_degeri_gecerli(deger)
        if not gecerli:
            logger.error("oto_set: %s reddedildi — %s", ad, sebep)
            hatali += 1
            continue
        ok, mesaj = bacnet_yaz(n["gateway_ip"], n["dnet"], n["mac_hex"],
                               n["obj_type"], n["obj_inst"], deger)
        if ok:
            yazilan += 1
        else:
            hatali += 1
            logger.error("oto_set: %s yazilamadi — %s", ad, mesaj)
    return yazilan, hatali


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
