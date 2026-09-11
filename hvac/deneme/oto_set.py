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


def _kural_okunabilir(url, key):
    """Merkezdeki oto_ ayarlarına gerçekten erişilebiliyor mu?

    RLS izni verilmemişse PostgREST boş liste döner; ağ yoksa istisna atar.
    İkisinde de False dönülür ve kontrol atlanır (fail-closed).
    """
    try:
        d = _istek(url, key, "/rest/v1/ayarlar?key=like.oto_*&select=key&limit=1")
        return bool(d)
    except Exception:
        return False


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
    "yazildi":          "Setler yazıldı ve cihazda doğrulandı",
    "yazma_hatasi":     "BACnet yazma hatası",
    "sahada_farkli":    "Yazıldı ama cihazda farklı değer var",
    "dogrulanamadi":    "Yazıldı ama cihazdan geri okunamadı",
    "hata":             "Beklenmeyen hata",
}

# Chiller'ın yeni seti gerçekten uygulayıp uygulamadığı (IC SET izlemesi)
DOGRULAMA_METIN = {
    "bekliyor":    "Chiller'ların yeni seti uygulaması bekleniyor",
    "uygulandi":   "Chiller'lar yeni seti uyguladı",
    "uygulanmadi": "Chiller'lar yeni seti UYGULAMADI",
}
# Chiller uzaktan seti gecikmeli uygulayabilir; bu süre boyunca her dakika
# IC SET okunur, süre dolduğunda hâlâ tutmuyorsa "uygulanmadi" denir.
IC_IZLEME_DK = 15


def _sonuc_yaz(sonuc, aciklama=""):
    _SON_SONUC.update({"zaman": datetime.now().isoformat(timespec="seconds"),
                       "sonuc": sonuc, "aciklama": str(aciklama)[:200]})
    if sonuc not in ("gecis_yok", "yazildi"):
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


def _ic_dogrulama_ilerlet(durum, lokasyon_id, simdi):
    """Geçişten sonraki dakikalarda chiller IC SET'lerini okur.

    REM SET'e yazılan değer cihazda "oturmuş" olsa bile chiller onu uygulamayabilir
    (yerel modda, arızada, sınır dışında). Asıl soru "chiller yeni seti kullanıyor
    mu" olduğu için IC SET izlenir. Beklemeye kilitlenmez: kontrol() her dakika
    çağrılır, bu fonksiyon her çağrıda bir kez okur.
    """
    d = durum.get("dogrulama")
    if not isinstance(d, dict) or d.get("sonuc") != "bekliyor":
        return
    try:
        from bacnet_writer import bacnet_oku, geri_okuma_haritasi
    except Exception:
        return
    harita = geri_okuma_haritasi(lokasyon_id)
    okunan = {}
    for ad, hedef in (d.get("hedefler") or {}).items():
        n = harita.get(ad)
        if not n:
            continue
        ok, val = bacnet_oku(n["gateway_ip"], n["dnet"], n["mac_hex"],
                             n["obj_type"], n["obj_inst"])
        okunan[ad] = round(float(val), 2) if ok else None
    d["okunan"] = okunan
    d["son_kontrol"] = simdi.isoformat(timespec="seconds")

    uymayan = [ad for ad, h in (d.get("hedefler") or {}).items()
               if okunan.get(ad) is None or abs(okunan[ad] - float(h)) > 0.05]
    try:
        gecen = (simdi - datetime.fromisoformat(d["baslangic"])).total_seconds() / 60
    except Exception:
        gecen = IC_IZLEME_DK + 1
    if not uymayan:
        d["sonuc"] = "uygulandi"
        d["uymayan"] = []
        logger.info("oto_set: chiller'lar yeni seti uyguladı (%s)", okunan)
    elif gecen >= IC_IZLEME_DK:
        d["sonuc"] = "uygulanmadi"
        d["uymayan"] = uymayan
        logger.warning("oto_set: %d dk sonra chiller'lar seti UYGULAMADI — %s (okunan %s)",
                       IC_IZLEME_DK, uymayan, okunan)
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
    """Dönem geçişi olduysa setpoint'leri BACnet ile yazar.

    Komut YALNIZCA dönem geçişinde üretilir. Gün ortasında hava tahmini
    değişse bile set gitmez; bir sonraki geçişte uygulanır.
    """
    try:
        # Kural okunamıyorsa (RLS izni yok / ağ yok) hiçbir şey yapılmaz.
        # Varsayılan saatlerle çalışıp yanlış saatte set göndermektense beklemek
        # güvenlidir — bu fonksiyonun tek tetikleyicisi merkezdeki kuraldır.
        if not _kural_okunabilir(sb_url, sb_key):
            _sonuc_yaz("kural_okunamadi")
            return

        if str(_ayar_oku(sb_url, sb_key, "oto_set_aktif", "true")).lower() != "true":
            _sonuc_yaz("kapali")
            return

        gunduz_saat = _saat_oku(sb_url, sb_key, "oto_gunduz_saat", GUNDUZ_VARSAYILAN)
        gece_saat   = _saat_oku(sb_url, sb_key, "oto_gece_saat",   GECE_VARSAYILAN)

        # Lokasyon PC'si Türkiye saatinde; yerel saat doğrudan kullanılır.
        simdi = datetime.now()
        donem = donem_hesapla(simdi.hour, gunduz_saat, gece_saat)

        durum = durum_oku()
        if donem == durum.get("donem"):
            _ic_dogrulama_ilerlet(durum, lokasyon_id, simdi)
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

        yazilan, hatali, detay = _setleri_uygula(sb_url, sb_key, lokasyon_id, hedefler)
        if yazilan == 0 and hatali == 0:
            _sonuc_yaz("nokta_yok")
            return                                     # bu lokasyonda nokta yok

        # "Yazıldı" artık ACK'a değil, cihazdan GERİ OKUNAN değere dayanır.
        oturdu    = sum(1 for s in detay.values() if s.get("durum") == "oturdu")
        farkli    = sum(1 for s in detay.values() if s.get("durum") == "sahada_farkli")
        okunamadi = sum(1 for s in detay.values() if s.get("durum") == "dogrulanamadi")
        if hatali:
            kod = "yazma_hatasi"
        elif farkli:
            kod = "sahada_farkli"
        elif okunamadi:
            kod = "dogrulanamadi"
        else:
            kod = "yazildi"
        _sonuc_yaz(kod, "%s · %d doğrulandı, %d farklı, %d okunamadı, %d hata"
                   % (donem, oturdu, farkli, okunamadi, hatali))

        # Chiller IC SET izlemesi: yazması kabul edilen ve okuma karşılığı
        # tanımlı noktalar için sonraki dakikalarda kontrol edilir.
        try:
            from bacnet_writer import geri_okuma_haritasi
            harita = geri_okuma_haritasi(lokasyon_id)
        except Exception:
            harita = {}
        ic_hedef = {ad: s["deger"] for ad, s in detay.items()
                    if s.get("yazma_ok") and ad in harita}

        durum_yaz({
            "donem": donem, "chiller_mod": yeni_ch, "diger_mod": yeni_dig,
            "ref_sicaklik": ref, "bugun_max": tahmin["bugun_max"],
            "yarin_min": tahmin["yarin_min"],
            "zaman": simdi.isoformat(timespec="seconds"),
            "yazilan": yazilan, "hatali": hatali,
            "son_yazim_sonuc": kod,
            "saha": {"dogrulandi": oturdu, "farkli": farkli,
                     "okunamadi": okunamadi, "hata": hatali},
            "dogrulama": ({"sonuc": "bekliyor",
                           "baslangic": simdi.isoformat(timespec="seconds"),
                           "hedefler": ic_hedef, "okunan": {}, "uymayan": []}
                          if ic_hedef else None),
            "gunduz_saat": gunduz_saat, "gece_saat": gece_saat,
        })

        _log_yaz(sb_url, sb_key, lokasyon_id, durum, yeni_ch, yeni_dig, ref, hedefler)

        logger.info("🤖 OTO-SET %s: %s dönemi — chiller=%s (%.1f°C), diger=%s "
                    "— %d nokta yazıldı, %d hata",
                    lokasyon_id, donem, yeni_ch, CH_SET[yeni_ch], yeni_dig,
                    yazilan, hatali)

    except Exception as e:
        _sonuc_yaz("hata", e)


def _setleri_uygula(sb_url, sb_key, lokasyon_id, hedefler):
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
        isler.append((ad, n, deger))

    if not isler:
        return 0, hatali, {}

    detay = yaz_dogrula_toplu(isler)
    yazilan = sum(1 for s in detay.values() if s.get("yazma_ok"))
    hatali += sum(1 for s in detay.values() if not s.get("yazma_ok"))
    for ad, s in detay.items():
        if s.get("durum") != "oturdu":
            logger.error("oto_set: %s — %s", ad, s.get("mesaj"))
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
