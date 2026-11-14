# -*- coding: utf-8 -*-
"""
ENERJİ PORTAL AGENT'I — sürüm 1, aşama 1 (veri kontrolleri)
==========================================================

Enerji ve Verimlilik portalının veri zincirini (sayaç → köprü → hesap → bulut)
7/24 kontrol eder. Watchdog'un yanında ayrı süreç olarak çalışır.

    python enerji_agent.py          → sürekli (her TUR_DAKIKA'da bir tur)
    python enerji_agent.py --tek    → tek tur çalıştır, sonucu yazdır ve çık

NE YAPAR
  Her turda aşağıdaki kontrolleri çalıştırır; bulduğu her sorunu "bulgu" olarak
  kaydeder. Bulgu şunları taşır: kontrol, beklenen, bulunan, agent'ın denediği,
  tekrar üretme adımı, olası kod/donanım yeri. Sonuç iki yere yazılır:
    * configs/enerji_agent_durum.json  (yerelde, her zaman)
    * veritabanı: agent_turlar + agent_bulgular  (supabase_config.json varsa)
  Üst agent (thapps) bulgulardan numaralı rapor üretir; Synapse > Yönetim >
  Agent katmanları'nda iş emri olarak görünür.

KONTROLLER (aşama 1 — ekran açmadan yapılabilenler)
  gunluk_dongu     Modbus 23:59, BACnet 07:05, köprü 00:05, bulut eşitleme 08:00
  sayac_erisimi    analizörler okunuyor mu (Şebeke, Kojen, trafo, chiller kritik)
  donmus_veri      bir ölçüm/sayaç günlerce aynı değerde mi; kojen üretimi 0 mı
  veri_kalitesi    eksik gün, mükerrer tarih, eksi değer, aykırı toplam
  diyagram_toplami Hastane Genel = Şebeke + Kojen; kayıtlı değer = hesap kuralı
  yerel_bulut      yereldeki günlük değer = Synapse'e giden değer
  portal_tutarliligi bu ay / geçen ay toplamı Enerji portalı = Synapse lokasyon detayı; mükerrer gün
  kapsam           veri gelen ama donmuş veri kontrolünde olmayan sayaç sütunu (bilgi)
  hava_durumu      dünün hava alanları dolu mu; boşsa servis yanıt veriyor mu
  portal_sagligi   8501 açık mı; eşitleme kaydında yeni hata var mı
  (Aşama 3: ekran ve buton kontrolleri — bu dosyada YOK.)

SINIRLAR (sürüm 1)
  * SALT OKUR. energy_data.csv'yi değiştirmez, süreç başlatmaz/durdurmaz.
    Kendi "workflow"u yalnızca zararsız olanlardır: yeniden deneme ve günü
    BELLEKTE yeniden hesaplama. Dosyaya yazan / portalı yeniden başlatan
    müdahaleler bu sürümde yoktur (configs/enerji_agent.json "mudahale" ileride).
  * Otomatik set yazımına (oto_set, bacnet_writer) ve BACnet'e DOKUNMAZ.
  * Yalnızca kendi iki tablosuna ve kendi durum dosyasına yazar.
  * Agent ölürse portallar etkilenmez (watchdog onu ayrı izler).

KAPATMA: configs/enerji_agent.json → {"aktif": false}
"""
import yollar  # dosya yolları (ayar/ durum/ veri/; Faz 1)
import argparse
import csv
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

SURUM = "1.1"
AGENT = "enerji"
# Agent kimliği: tur/gönderim/döngü çekirdeği Mekanik Zeka agent'ı ile ORTAK (mekanik_zeka_agent.py)
ENERJI = {"agent": "enerji", "ad": "Enerji Portal Agent'ı", "on": "enerji_agent"}
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TUR_DAKIKA = 15
BASLANGIC_BEKLEME_SN = 120    # açılışta portallar ayağa kalksın (yanlış "8501 yanıt vermiyor" olmasın)
HAVA_GUN = 7                  # hava kontrolü penceresi
DONMA_GUN = 4                 # sayaç sütunu bu kadar gün birebir aynıysa donmuş
KOJEN_SIFIR_GUN = 3
KALITE_GUN = 30               # veri kalitesi penceresi
KARSILASTIRMA_GUN = 7         # diyagram ve yerel↔bulut penceresi
TOLERANS_KWH = 1.0
AYKIRI_UST, AYKIRI_ALT = 2.5, 0.4   # toplam, 30 günlük medyanın katı

# Günlük döngü: işin saati + pay (dakika). Bu saatten önce "henüz" sayılır.
KOPRU_SON = (0, 30)           # köprü 00:05
BACNET_SON = (7, 40)          # BACnet 07:05
BULUT_SON = (8, 30)           # bulut eşitleme 08:00

# Sayaçlar ve kritik olanlar ayar/sayaclar.json'dan gelir (sayaclar.py; Faz 1 / C1). Aşağıdaki
# iki liste YALNIZCA sayaç dosyası okunamazsa kullanılan yedektir (Maslak'ın 12.11.2026 hâli).
KRITIK_SAYAC = ("SEBEKE", "KOJEN", "TRDP", "CHILLER")
SAYAC_SUTUNLARI = (["Sebeke_Tuketim_kWh", "Kojen1_kWh", "Kojen2_kWh", "Kojen3_kWh", "Kojen4_kWh",
                    "TRDP1_kWh", "TRDP2_kWh", "TRDP3_kWh", "TRDP4_kWh"]
                   + ["Chiller%d_kWh" % i for i in range(1, 6)]
                   + ["MCC%d_kWh" % i for i in range(1, 8)]
                   # 11.11.2026: kapsam kontrolü buldu — Kule ve bina MCC sayaçları (data_collector ANALYZERS)
                   + ["Kule%d_kWh" % i for i in range(1, 4)]
                   + ["MCC_2BK_D01_kWh", "MCC_2BK_D02_kWh", "MCC_4BK_E01_kWh", "MCC_4BK_E02_kWh",
                      "MCC_4BK_F01_kWh", "MCC_CK_D01_kWh", "MCC_CK_E01_kWh", "MCC_CK_F01_kWh"])
BULUT_SUTUNLARI = ["Toplam_Hastane_Tuketim_kWh", "Sebeke_Tuketim_kWh", "Kojen_Uretim_kWh",
                   "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh"]
TURETILMIS = ["Toplam_Hastane_Tuketim_kWh", "Sebeke_Tuketim_kWh", "Kojen_Uretim_kWh",
              "Toplam_Sogutma_Tuketim_kWh", "Diger_Yuk_kWh"]

logger = logging.getLogger("enerji_agent")


class Atla(Exception):
    """Kontrol bu turda yapılamadı (dosya yok, ayar yok). Sorun sayılmaz."""


# ══════════════════════════════════════════════════════════════════════════
# ORTAM — dosya yolları, saat ve ağ. Testler bunu sahteleriyle değiştirir.
# ══════════════════════════════════════════════════════════════════════════
def _port(url):
    """'http://127.0.0.1:8501' → '8501' (iş emri metinleri için)."""
    return str(url).rstrip("/").rsplit(":", 1)[-1]


class Ortam:
    def __init__(self, dizin=BASE_DIR, simdi=None, bulut="oku", http=None, bekle=None,
                 portal_url=None, kim=None):
        self.kim = kim or ENERJI
        self.dizin = dizin
        self._simdi = simdi
        if portal_url is None:              # Enerji portalı portu: ayar/portlar.json (yoksa 8501)
            try:
                import portlar
                portal_url = portlar.enerji_url(dizin)
            except Exception:
                portal_url = "http://127.0.0.1:8501"
        self.portal_url = portal_url
        self.http = http or _http
        self.bekle = bekle or time.sleep
        self.bulut = self._bulut_oku() if bulut == "oku" else bulut

    def simdi(self):
        return self._simdi or datetime.now()

    def yol(self, *p):
        # ayar/ durum/ veri/ katmanları (yollar.py, Faz 1); eski kurulumda bugünkü yerler
        return yollar.yol("/".join(p), self.dizin)

    def _bulut_oku(self):
        """supabase_config.json → {url, key, lokasyon_id} ya da None (bu PC göndermez)."""
        try:
            with open(self.yol("supabase_config.json"), encoding="utf-8-sig") as f:
                c = json.load(f)
            u, k = c.get("supabase_url", ""), c.get("supabase_key", "")
            if not u or not k or "BURAYA" in u or "BURAYA" in k:
                return None
            import location_manager as _lm_k   # kimlik: lokasyon profili (Faz 1)
            return {"url": u.rstrip("/"), "key": k,
                    "lokasyon_id": _lm_k.lokasyon_id(self.dizin, c.get("lokasyon_id")) or "bilinmeyen"}
        except Exception:
            return None

    def ayar(self):
        try:
            with open(self.yol("configs", self.kim["on"] + ".json"), encoding="utf-8-sig") as f:
                a = json.load(f)
            return a if isinstance(a, dict) else {}
        except Exception:
            return {}


def _http(url, yontem="GET", basliklar=None, govde=None, zaman_asimi=15):
    """(durum kodu, metin). Ağ hatasında (None, hata metni)."""
    try:
        istek = urllib.request.Request(
            url, method=yontem, headers=basliklar or {},
            data=json.dumps(govde, ensure_ascii=False).encode("utf-8") if govde is not None else None)
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as c:
            return c.status, c.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]
    except Exception as e:
        return None, str(getattr(e, "reason", e))


def _bulut_baslik(o, ek=None):
    try:
        import sb_kimlik
        return sb_kimlik.basliklar(o.bulut["key"], ek)
    except Exception:
        h = {"apikey": o.bulut["key"], "Authorization": "Bearer " + o.bulut["key"]}
        h.update(ek or {})
        return h


# ══════════════════════════════════════════════════════════════════════════
# YARDIMCILAR
# ══════════════════════════════════════════════════════════════════════════
def bulgu(kontrol, ayirt, onem, bolum, baslik, beklenen, bulunan, denenen="—",
          tekrar_adimi="", olasi_yer="", kanit=None):
    return {"anahtar": "%s:%s" % (kontrol, ayirt), "kontrol": kontrol, "onem": onem,
            "bolum": bolum, "baslik": baslik, "beklenen": beklenen, "bulunan": bulunan,
            "denenen": denenen, "tekrar_adimi": tekrar_adimi, "olasi_yer": olasi_yer,
            "kanit": kanit or {}}


def _say(x):
    """1234.5 → '1.234,5 kWh' biçiminin sayı kısmı."""
    try:
        s = ("%.1f" % float(x)).rstrip("0").rstrip(".")
        tam, _, kes = s.partition(".")
        eksi = tam.startswith("-")
        tam = tam.lstrip("-")
        tam = ".".join([tam[max(0, i - 3):i] for i in range(len(tam), 0, -3)][::-1])
        return ("−" if eksi else "") + tam + ("," + kes if kes else "")
    except (TypeError, ValueError):
        return "—"


def _tr(t):
    return datetime.strptime(str(t)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")


def _gecti_mi(simdi, saat_dk):
    return (simdi.hour, simdi.minute) >= saat_dk


def enerji_df(o):
    """energy_data.csv → DataFrame (Tarih 'YYYY-AA-GG' metin, tarihe göre sıralı)."""
    yol = o.yol("energy_data.csv")
    if not os.path.exists(yol):
        raise Atla("energy_data.csv yok")
    import pandas as pd
    df = pd.read_csv(yol)
    if df.empty or "Tarih" not in df.columns:
        raise Atla("energy_data.csv boş")
    t = pd.to_datetime(df["Tarih"], errors="coerce")
    df = df[t.notna()].copy()
    df["Tarih"] = t[t.notna()].dt.strftime("%Y-%m-%d")
    return df.sort_values("Tarih", kind="stable").reset_index(drop=True)


def hesaplanmis(df):
    """Türetilmiş sütunları portalın/eşitlemenin kullandığı kuralla yeniden hesaplar (kopyada)."""
    import enerji_hesap
    return enerji_hesap.yeniden_hesapla(df.copy())


def _sayi(v):
    try:
        f = float(v)
        return None if f != f else f          # NaN → None
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════════
# KONTROLLER — her biri bulgu listesi döner (boş = geçti) ya da Atla fırlatır
# ══════════════════════════════════════════════════════════════════════════
def k_gunluk_dongu(o):
    simdi = o.simdi()
    bugun, dun = simdi.date(), simdi.date() - timedelta(days=1)
    cikti = []

    # 1) Modbus 23:59 okuması
    yol = o.yol("analizor_guncel_veriler.csv")
    if os.path.exists(yol) and _gecti_mi(simdi, KOPRU_SON):
        with open(yol, newline="", encoding="utf-8") as f:
            zamanlar = [r.get("Okuma_Zamani", "") for r in csv.DictReader(f) if r.get("Okuma_Zamani")]
        son = max(zamanlar) if zamanlar else ""
        if not son or son[:10] < dun.isoformat():
            cikti.append(bulgu(
                "gunluk_dongu", "modbus", "kritik", "Günlük döngü",
                "Modbus 23:59 günlük okuması yapılmamış",
                "son okuma %s 23:59" % _tr(dun), "son okuma: %s" % (son or "hiç"),
                tekrar_adimi="analizor_guncel_veriler.csv dosyasının Okuma_Zamani sütununa bak",
                olasi_yer="data_collector.py modbus_thread (süreç çalışıyor mu, PC 23:59'da açık mıydı)"))

    # 2) Köprü 00:05 — dünün satırı
    if _gecti_mi(simdi, KOPRU_SON):
        try:
            df = enerji_df(o)
            if dun.isoformat() not in set(df["Tarih"]):
                cikti.append(bulgu(
                    "gunluk_dongu", "kopru:%s" % dun, "kritik", "Günlük döngü",
                    "%s gününün satırı energy_data'ya yazılmamış" % _tr(dun),
                    "00:05'te %s satırı yazılır" % _tr(dun),
                    "son satır: %s" % _tr(df["Tarih"].iloc[-1]),
                    tekrar_adimi="Enerji portalı → Veri Görüntüleme, son satırın tarihi",
                    olasi_yer="data_bridge.py run_daily_snapshot (PC 00:05'te kapalıysa açılışta telafi eder)"))
        except Atla:
            pass

    # 3) BACnet 07:05
    yol = o.yol("hedefli_enerji_verileri.csv")
    if os.path.exists(yol) and _gecti_mi(simdi, BACNET_SON):
        with open(yol, newline="", encoding="utf-8") as f:
            zamanlar = [r.get("Timestamp", "") for r in csv.DictReader(f) if r.get("Timestamp")]
        son = max(zamanlar) if zamanlar else ""
        if not son or son[:10] < bugun.isoformat():
            cikti.append(bulgu(
                "gunluk_dongu", "bacnet", "kritik", "Günlük döngü",
                "BACnet 07:05 okuması bugün yapılmamış",
                "son okuma bugün 07:05", "son okuma: %s" % (son or "hiç"),
                tekrar_adimi="hedefli_enerji_verileri.csv dosyasının Timestamp sütununa bak",
                olasi_yer="data_collector.py bacnet_thread, configs/hedefli_okuma_sablonu_2.xlsx, BACnet gateway"))

    # 4) Bulut eşitleme 08:00
    if o.bulut and _gecti_mi(simdi, BULUT_SON) and not os.path.exists(o.yol("_sync_disabled.flag")):
        try:
            with open(o.yol("sync_son_calisma.txt"), encoding="utf-8") as f:
                son = f.read().strip()
        except OSError:
            son = ""
        if son[:10] != bugun.isoformat():
            cikti.append(bulgu(
                "gunluk_dongu", "bulut", "uyari", "Günlük döngü",
                "Bulut eşitlemesi (08:00) bugün çalışmamış",
                "sync_son_calisma.txt = %s" % bugun.isoformat(), "son eşitleme: %s" % (son or "kayıt yok"),
                tekrar_adimi="cloud_sync.log içinde bugünkü 'Senkronizasyon' satırlarına bak",
                olasi_yer="cloud_sync.py start_background_sync (süreç, ağ ya da veritabanı)"))
    return cikti


def k_sayac_erisimi(o):
    yol = o.yol("analizor_guncel_veriler.csv")
    if not os.path.exists(yol):
        raise Atla("analizor_guncel_veriler.csv yok")
    with open(yol, newline="", encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    try:                                     # kritik sayaçlar: ayar/sayaclar.json (Faz 1 / C1)
        import sayaclar
        _kritikler = sayaclar.kritik_adlar(o.dizin)
    except Exception:
        _kritikler = set()
    cikti = []
    for r in satirlar:
        ad, durum = (r.get("Cihaz_Adi") or "").strip(), (r.get("Durum") or "").strip()
        if ad and "hata" in durum.lower():
            kritik = (ad in _kritikler) if _kritikler else any(k in ad.upper() for k in KRITIK_SAYAC)
            cikti.append(bulgu(
                "sayac_erisimi", ad, "kritik" if kritik else "uyari", "Sayaç erişimi",
                "%s sayacı okunamıyor" % ad, "günlük okumada kWh değeri",
                "%s (%s, %s)" % (durum, r.get("IP", "?"), r.get("Okuma_Zamani", "?")),
                tekrar_adimi="Lokasyon PC'sinden %s adresine ping at; sayaç ekranını kontrol et" % r.get("IP", "?"),
                olasi_yer="sayaç / ağ kablosu / IP; data_collector.py ANALYZERS"))
    return cikti


def k_donmus_veri(o):
    cikti = []
    df = enerji_df(o)
    # BACnet ölçümleri: mevcut tespit (veri_alarm) — aynı eşik, aynı sütunlar
    try:
        import veri_alarm
        for a in veri_alarm.bacnet_alarmlari(o.simdi(), o.yol("hedefli_enerji_verileri.csv"),
                                             o.yol("energy_data.csv")):
            if a.get("tur") == "donmus_deger":
                cikti.append(bulgu(
                    "donmus_veri", "bacnet", "uyari", "Donmuş veri", a["mesaj"],
                    "ölçümler günden güne değişir", ", ".join(a.get("cihazlar", [])),
                    tekrar_adimi="Veri Görüntüleme'de bu sütunların son günlerine bak",
                    olasi_yer="BACnet okuması (data_collector.py bacnet_thread) ya da sensör"))
    except Exception as e:
        logger.debug("veri_alarm kullanılamadı: %s", e)

    son = df.tail(30)
    for c in sayac_sutunlari(o):
        if c not in son.columns:
            continue
        v = [x for x in (_sayi(x) for x in son[c]) if x is not None]
        if len(v) >= DONMA_GUN and v[-1] != 0 and len(set(v[-DONMA_GUN:])) == 1:
            n = 0
            for x in reversed(v):
                if x != v[-1]:
                    break
                n += 1
            cikti.append(bulgu(
                "donmus_veri", c, "uyari", "Donmuş veri",
                "%s %d gündür aynı değerde (%s)" % (c, n, _say(v[-1])),
                "günlük tüketim günden güne değişir", "%d gün üst üste %s" % (n, _say(v[-1])),
                tekrar_adimi="Veri Görüntüleme'de %s sütununun son %d gününe bak" % (c, n),
                olasi_yer="sayaç haberleşmesi ya da data_bridge.py günlük fark hesabı"))

    if "Kojen_Uretim_kWh" in df.columns:
        k = [(_sayi(x) or 0) for x in hesaplanmis(df)["Kojen_Uretim_kWh"]]
        if len(k) > KOJEN_SIFIR_GUN + 7 and all(x == 0 for x in k[-KOJEN_SIFIR_GUN:]) \
                and any(x > 0 for x in k[-(KOJEN_SIFIR_GUN + 30):-KOJEN_SIFIR_GUN]):
            n = 0
            for x in reversed(k):
                if x != 0:
                    break
                n += 1
            cikti.append(bulgu(
                "donmus_veri", "kojen_sifir", "uyari", "Donmuş veri",
                "Kojen üretimi %d gündür 0" % n,
                "kojen çalışıyorsa günlük üretim > 0", "son %d gün 0 kWh" % n,
                tekrar_adimi="Kojen sayaçlarının ekranındaki toplam kWh değerini iki gün arayla karşılaştır",
                olasi_yer="kojen gerçekten kapalı olabilir; değilse KOJEN-n sayaç okuması"))
    return cikti


def k_veri_kalitesi(o):
    df = enerji_df(o)
    simdi = o.simdi()
    dun = simdi.date() - timedelta(days=1)
    cikti = []

    # Mükerrer tarih (bütün dosya)
    say = df["Tarih"].value_counts()
    for t in sorted(say[say > 1].index)[-5:]:
        cikti.append(bulgu(
            "veri_kalitesi", "mukerrer:%s" % t, "uyari", "Veri kalitesi",
            "%s tarihi %d kez kayıtlı" % (_tr(t), say[t]), "her gün tek satır", "%d satır" % say[t],
            tekrar_adimi="Veri Görüntüleme'de %s tarihini filtrele" % _tr(t),
            olasi_yer="app_portal.py veri girişi (UPSERT) ya da data_bridge.py date_exists_in_csv"))

    # Eksik gün (son KALITE_GUN gün; dosyanın ilk gününden önceki günler sayılmaz)
    var = set(df["Tarih"])
    ilk = max(date.fromisoformat(df["Tarih"].iloc[0]), dun - timedelta(days=KALITE_GUN - 1))
    son_gun = dun if _gecti_mi(simdi, KOPRU_SON) else dun - timedelta(days=1)
    eksik = [g for g in (ilk + timedelta(days=i) for i in range((son_gun - ilk).days + 1))
             if g.isoformat() not in var and g < dun]      # dünün eksikliği gunluk_dongu'da
    if eksik:
        cikti.append(bulgu(
            "veri_kalitesi", "eksik_gun", "uyari", "Veri kalitesi",
            "Son %d günde %d gün eksik" % (KALITE_GUN, len(eksik)), "her gün için bir satır",
            ", ".join(_tr(g.isoformat()) for g in eksik[:8]) + ("…" if len(eksik) > 8 else ""),
            tekrar_adimi="Veri Görüntüleme'de tarih sırasına bak",
            olasi_yer="PC o günlerde kapalıydı ya da köprü yazamadı; veri girişinden elle tamamlanabilir",
            kanit={"eksik": [g.isoformat() for g in eksik]}))

    # Eksi değer (şebeke yeni kuralda eksi olabilir: şebekeye verilen enerji)
    import enerji_hesap
    pencere = df[df["Tarih"] >= (dun - timedelta(days=KALITE_GUN - 1)).isoformat()]
    for c in [k for k in pencere.columns if k.endswith(("_kWh", "_m3"))]:
        for _, r in pencere.iterrows():
            v = _sayi(r[c])
            if v is not None and v < 0 and not (
                    c == "Sebeke_Tuketim_kWh" and enerji_hesap.yeni_kural_mi(r["Tarih"])):
                cikti.append(bulgu(
                    "veri_kalitesi", "eksi:%s:%s" % (c, r["Tarih"]), "uyari", "Veri kalitesi",
                    "%s günü %s eksi (%s)" % (_tr(r["Tarih"]), c, _say(v)), "0 ya da büyük", _say(v),
                    tekrar_adimi="Veri Girişi'nde %s tarihini aç" % _tr(r["Tarih"]),
                    olasi_yer="sayaç sıfırlanması / data_bridge.py calc_daily_kwh"))
    cikti = cikti[:12]

    # Aykırı toplam: son 3 gün ↔ önceki günlerin medyanı
    h = hesaplanmis(pencere)
    top = [(r["Tarih"], _sayi(r["Toplam_Hastane_Tuketim_kWh"])) for _, r in h.iterrows()]
    onceki = sorted(v for _, v in top[:-3] if v and v > 0)
    if len(onceki) >= 10:
        medyan = onceki[len(onceki) // 2]
        for t, v in top[-3:]:
            if v is not None and v > 0 and not (AYKIRI_ALT * medyan <= v <= AYKIRI_UST * medyan):
                cikti.append(bulgu(
                    "veri_kalitesi", "aykiri:%s" % t, "uyari", "Veri kalitesi",
                    "%s günü hastane toplamı olağan dışı (%s kWh)" % (_tr(t), _say(v)),
                    "son günlerin medyanı %s kWh (×%.1f – ×%.1f arası)" % (_say(medyan), AYKIRI_ALT, AYKIRI_UST),
                    "%s kWh" % _say(v),
                    tekrar_adimi="Enerji diyagramında %s tarihini aç" % _tr(t),
                    olasi_yer="eksik/çift sayaç okuması ya da gerçek tüketim değişimi"))
    return cikti


def k_diyagram_toplami(o):
    """Enerji diyagramı: kayıtlı türetilmiş değerler hesap kuralıyla tutuyor mu; kural kendi içinde tutarlı mı."""
    import enerji_hesap
    df = enerji_df(o).drop_duplicates(subset=["Tarih"], keep="last").tail(KARSILASTIRMA_GUN)
    h = hesaplanmis(df)
    cikti = []
    for (_, k), (_, y) in zip(df.iterrows(), h.iterrows()):
        t = k["Tarih"]
        seb, koj, top = _sayi(y.get("Sebeke_Tuketim_kWh")), _sayi(y.get("Kojen_Uretim_kWh")) or 0, \
            _sayi(y.get("Toplam_Hastane_Tuketim_kWh")) or 0

        # (a) Kuralın kendi tutarlılığı — bozuksa sorun KODDA
        if enerji_hesap.yeni_kural_mi(t) and abs(top - ((seb or 0) + koj)) > TOLERANS_KWH:
            cikti.append(bulgu(
                "diyagram_toplami", "kural:%s" % t, "kritik", "Enerji Diyagramı",
                "Enerji diyagramında Hastane Genel toplamı tutmuyor (%s)" % _tr(t),
                "Hastane Genel = Şebeke + Kojen = %s kWh (Şebeke %s + Kojen %s)"
                % (_say((seb or 0) + koj), _say(seb or 0), _say(koj)),
                "%s kWh · fark %s kWh" % (_say(top), _say(top - ((seb or 0) + koj))),
                denenen="günü yeniden hesaplattı → fark sürüyor",
                tekrar_adimi="Diyagramı aç, tarih %s" % _tr(t),
                olasi_yer="enerji_hesap.py yeniden_hesapla, app_portal.py diyagram bölümü (tahmin)"))
            continue

        # (b) Dosyadaki değer kuralın ürettiğiyle aynı mı — değilse dosya eski hesapla duruyor
        fark = []
        for c in TURETILMIS:
            if c in df.columns:
                a, b = _sayi(k.get(c)), _sayi(y.get(c))
                if (a or 0) != (b or 0) and abs((a or 0) - (b or 0)) > TOLERANS_KWH:
                    fark.append("%s: kayıtlı %s, kural %s" % (c, _say(a or 0), _say(b or 0)))
        if fark:
            # BİLGİ: buluta giden değer cloud_sync'te bu kuralla yeniden hesaplanır; yalnızca
            # yereldeki dosya eski kalmıştır. İş emri açılmaz (yerel↔bulut farkı ayrıca denetlenir).
            cikti.append(bulgu(
                "diyagram_toplami", "kayit:%s" % t, "bilgi", "Enerji Diyagramı",
                "%s günü kayıtlı toplamlar hesap kuralıyla tutmuyor" % _tr(t),
                "kayıtlı değer = hesap kuralının sonucu", "; ".join(fark[:3]),
                denenen="günü bellekte yeniden hesapladı → kural değeri farklı; dosya değiştirilmedi",
                tekrar_adimi="Enerji portalını aç (açılışta yeniden hesaplar), %s tarihine bak" % _tr(t),
                olasi_yer="energy_data.csv eski hesapla kalmış; portal açılınca ya da eşitlemede düzelir. "
                          "Sürüyorsa app_portal.py recalc"))
    return cikti


def k_yerel_bulut(o):
    if not o.bulut:
        raise Atla("bulut ayarı yok (supabase_config.json) — bu PC veri göndermiyor")
    if os.path.exists(o.yol("_sync_disabled.flag")):
        raise Atla("enerji eşitlemesi kapalı (_sync_disabled.flag)")
    simdi = o.simdi()
    dun = simdi.date() - timedelta(days=1)
    # Dünün satırı buluta 08:00 eşitlemesiyle gider; ondan önce dün karşılaştırılmaz
    son = dun if _gecti_mi(simdi, BULUT_SON) else dun - timedelta(days=1)
    ilk = son - timedelta(days=KARSILASTIRMA_GUN - 1)

    h = hesaplanmis(enerji_df(o).drop_duplicates(subset=["Tarih"], keep="last"))
    yerel = {r["Tarih"]: r for _, r in h.iterrows() if ilk.isoformat() <= r["Tarih"] <= son.isoformat()}
    if not yerel:
        raise Atla("karşılaştırılacak gün yok")

    sorgu = ("%s/rest/v1/energy_data?lokasyon_id=eq.%s&Tarih=gte.%s&Tarih=lte.%s&select=Tarih,%s"
             % (o.bulut["url"], urllib.parse.quote(o.bulut["lokasyon_id"]), ilk, son,
                ",".join(BULUT_SUTUNLARI)))
    kod, metin = o.http(sorgu, basliklar=_bulut_baslik(o))
    if kod != 200:
        o.bekle(20)                                   # workflow: bir kez yeniden dene
        kod, metin = o.http(sorgu, basliklar=_bulut_baslik(o))
    if kod != 200:
        return [bulgu(
            "yerel_bulut", "erisim", "uyari", "Yerel ↔ bulut",
            "Synapse veritabanına ulaşılamıyor", "HTTP 200", "HTTP %s: %s" % (kod, str(metin)[:120]),
            denenen="20 sn sonra yeniden denedi → yine ulaşılamadı",
            tekrar_adimi="Lokasyon PC'sinden thapps adresini tarayıcıda aç",
            olasi_yer="ağ / thapps / supabase_config.json")]
    bulut = {}
    for r in json.loads(metin):
        bulut.setdefault(str(r.get("Tarih"))[:10], r)   # aynı gün birden çoksa ilki

    cikti = []
    for t in sorted(yerel):
        if t not in bulut:
            cikti.append(bulgu(
                "yerel_bulut", "yok:%s" % t, "uyari", "Yerel ↔ bulut",
                "%s günü Synapse'te yok" % _tr(t), "yereldeki her gün Synapse'te de olur",
                "yerelde var, veritabanında yok",
                tekrar_adimi="Synapse → lokasyon detayı, %s" % _tr(t),
                olasi_yer="cloud_sync.py sync_energy_data (cloud_sync.log'da 'senkronizasyon hatası')"))
            continue
        fark = []
        for c in BULUT_SUTUNLARI:
            a, b = _sayi(yerel[t].get(c)) or 0, _sayi(bulut[t].get(c)) or 0
            if abs(a - b) > TOLERANS_KWH:
                fark.append("%s: yerel %s, Synapse %s" % (c.replace("_kWh", ""), _say(a), _say(b)))
        if fark:
            cikti.append(bulgu(
                "yerel_bulut", "fark:%s" % t, "uyari", "Yerel ↔ bulut",
                "%s günü yerel değer Synapse'tekiyle tutmuyor" % _tr(t),
                "yerel = Synapse (fark ≤ %g kWh)" % TOLERANS_KWH, "; ".join(fark[:3]),
                tekrar_adimi="Enerji portalı ve Synapse lokasyon detayında %s gününü karşılaştır" % _tr(t),
                olasi_yer="gün yerelde sonradan düzeltilmiş ve henüz eşitlenmemiş olabilir (08:00); "
                          "sürüyorsa cloud_sync.py sync_energy_data"))
    return cikti


def _ay_araliklari(son):
    """Eşitlenmiş son güne göre (bu ay başı → son), (geçen ay başı → geçen ay sonu)."""
    bu_bas = son.replace(day=1)
    gecen_son = bu_bas - timedelta(days=1)
    return [(bu_bas, son), (gecen_son.replace(day=1), gecen_son)]


def k_portal_tutarliligi(o):
    """Portallar arası tutarlılık: Enerji portalının aylık toplamı = Synapse lokasyon detayının
    toplamı. Synapse detayı veritabanındaki SATIRLARI toplar; aynı gün iki kez yazılmışsa
    detaydaki toplam şişer (yerel ↔ bulut günlük karşılaştırması bunu göremez)."""
    if not o.bulut:
        raise Atla("bulut ayarı yok (supabase_config.json) — bu PC veri göndermiyor")
    if os.path.exists(o.yol("_sync_disabled.flag")):
        raise Atla("enerji eşitlemesi kapalı (_sync_disabled.flag)")
    simdi = o.simdi()
    dun = simdi.date() - timedelta(days=1)
    son = dun if _gecti_mi(simdi, BULUT_SON) else dun - timedelta(days=1)
    h = hesaplanmis(enerji_df(o).drop_duplicates(subset=["Tarih"], keep="last"))
    cikti = []
    for bas, bit in _ay_araliklari(son):
        yerel = h[(h["Tarih"] >= bas.isoformat()) & (h["Tarih"] <= bit.isoformat())]
        if yerel.empty:
            continue
        sorgu = ("%s/rest/v1/energy_data?lokasyon_id=eq.%s&Tarih=gte.%s&Tarih=lte.%sT23:59:59&select=Tarih,%s"
                 % (o.bulut["url"], urllib.parse.quote(o.bulut["lokasyon_id"]), bas, bit, ",".join(BULUT_SUTUNLARI)))
        kod, metin = o.http(sorgu, basliklar=_bulut_baslik(o))
        if kod != 200:
            raise Atla("Synapse okunamadı (HTTP %s) — yerel ↔ bulut kontrolüne bakın" % kod)
        satirlar = [r for r in json.loads(metin) if bas.isoformat() <= str(r.get("Tarih"))[:10] <= bit.isoformat()]
        ay = bas.strftime("%m.%Y")
        gunler = [str(r.get("Tarih"))[:10] for r in satirlar]
        mukerrer = sorted({g for g in gunler if gunler.count(g) > 1})
        if mukerrer:
            cikti.append(bulgu(
                "portal_tutarliligi", "mukerrer:%s" % bas.strftime("%Y-%m"), "uyari", "Portallar arası tutarlılık",
                "Synapse'te %s ayında %d gün iki kez kayıtlı" % (ay, len(mukerrer)),
                "her gün Synapse'te tek satır", ", ".join(_tr(g) for g in mukerrer[:6]),
                tekrar_adimi="Synapse → lokasyon detayı → %s toplamı ile Enerji portalını karşılaştır" % ay,
                olasi_yer="cloud_sync.py sync_energy_data (aynı günü UPSERT yerine yeniden ekliyor); "
                          "lokasyon detayı mükerrer satırları da toplar"))
        fark = []
        for c in BULUT_SUTUNLARI:
            a = float(sum(_sayi(v) or 0 for v in yerel[c])) if c in yerel.columns else 0.0
            b = float(sum(_sayi(r.get(c)) or 0 for r in satirlar))
            if abs(a - b) > TOLERANS_KWH * max(1, len(yerel)):
                fark.append("%s: Enerji %s, Synapse %s" % (c.replace("_kWh", ""), _say(a), _say(b)))
        if fark:
            cikti.append(bulgu(
                "portal_tutarliligi", "toplam:%s" % bas.strftime("%Y-%m"), "uyari", "Portallar arası tutarlılık",
                "%s aylık toplamı Enerji portalı ile Synapse'te farklı" % ay,
                "Enerji portalı toplamı = Synapse lokasyon detayı toplamı", "; ".join(fark[:3]),
                tekrar_adimi="Enerji portalı (%s, %s–%s) ve Synapse lokasyon detayı aynı aralık"
                             % (ay, _tr(bas.isoformat()), _tr(bit.isoformat())),
                olasi_yer="ay içinde sonradan düzeltilen bir gün eşitlenmemiş olabilir (yerel ↔ bulut 7 günü görür); "
                          "sürüyorsa cloud_sync.py sync_energy_data", kanit={"farklar": fark}))
    return cikti


# Donmuş veri kontrolünün baktığı sayaçlar + toplam/türetilmiş sütunlar (sayaç değil, kapsam dışı).
def sayac_sutunlari(o):
    """Donmuş veri kontrolünün baktığı sayaç sütunları: ayar/sayaclar.json (yoksa yedek liste)."""
    try:
        import sayaclar
        return sayaclar.sutunlar(base_dir=o.dizin) or list(SAYAC_SUTUNLARI)
    except Exception:
        return list(SAYAC_SUTUNLARI)


def izlenen(o):
    return set(sayac_sutunlari(o)) | set(TURETILMIS) | set(BULUT_SUTUNLARI)


def k_kapsam(o):
    """Kapsam: energy_data.csv'de veri gelen ama DONMUŞ VERİ kontrolünün bakmadığı sayaç sütunu var mı.
    (Okuma ve canlı veri kontrolleri ANALYZERS'taki bütün sayaçlara zaten bakar; günlük değerin
    günlerce aynı kalması ise yalnızca ayar/sayaclar.json'dakilerde yakalanır.) Yalnızca bilgi."""
    df = enerji_df(o)
    son = df[df["Tarih"] >= (o.simdi().date() - timedelta(days=KALITE_GUN)).isoformat()]
    yeni = []
    for c in df.columns:
        if not c.endswith("_kWh") or c in izlenen(o):
            continue
        if any((_sayi(v) or 0) != 0 for v in son[c]):
            yeni.append(c)
    if not yeni:
        return []
    return [bulgu(
        "kapsam", "sayac", "bilgi", "Kapsam",
        "%d sayaç sütunu donmuş veri kontrolünde yok" % len(yeni),
        "veri gelen her sayaç donmuş veri kontrolünde (okuma ve canlı veri kontrolleri bütün sayaçlara bakar)",
        ", ".join(sorted(yeni)), tekrar_adimi="energy_data.csv sütunları ↔ ayar/sayaclar.json (sutun alanı)",
        olasi_yer="ayar/sayaclar.json (yeni sayaç eklenince buraya da eklenmeli)",
        kanit={"sutunlar": sorted(yeni)})]


def k_hava_durumu(o):
    """Son HAVA_GUN günde internet hava alanları boş gün var mı; varsa iki kaynağı yoklar."""
    simdi = o.simdi()
    dun = simdi.date() - timedelta(days=1)
    son = dun if _gecti_mi(simdi, KOPRU_SON) else dun - timedelta(days=1)
    df = enerji_df(o)
    if "Hava_Sicaklik_Ort_C" not in df.columns:
        raise Atla("hava sütunları yok")
    pencere = df[(df["Tarih"] > (son - timedelta(days=HAVA_GUN)).isoformat()) & (df["Tarih"] <= son.isoformat())]
    bos = sorted({r["Tarih"] for _, r in pencere.iterrows() if _sayi(r["Hava_Sicaklik_Ort_C"]) is None})
    if not bos:
        return []
    # Kaynak 1: internet (Open-Meteo)
    kod, metin = o.http("https://api.open-meteo.com/v1/forecast?latitude=41&longitude=29"
                        "&daily=temperature_2m_mean&forecast_days=1", zaman_asimi=10)
    internet = kod == 200
    # Kaynak 2: Synapse yedek yolu (merkezin yazdığı hava_gunluk)
    yedek = None
    if o.bulut:
        k2, m2 = o.http("%s/rest/v1/hava_gunluk?select=tarih&lokasyon_id=eq.%s&tarih=gte.%s&tarih=lte.%s&tahmin=eq.false"
                        % (o.bulut["url"], urllib.parse.quote(o.bulut["lokasyon_id"]), bos[0], bos[-1]),
                        basliklar=_bulut_baslik(o), zaman_asimi=15)
        try:
            yedek = len(json.loads(m2)) if k2 == 200 else None
        except (TypeError, ValueError):
            yedek = None
    durum = ["internet: %s" % ("yanıt veriyor" if internet else "ulaşılamıyor (%s)" % str(metin)[:80])]
    durum.append("Synapse yedek yolu: %s" % ("ayar yok" if not o.bulut else
                                             "ulaşılamıyor" if yedek is None else "%d/%d gün hazır" % (yedek, len(bos))))
    if internet or yedek:
        yer = ("Veri bir kaynakta hazır: data_bridge.py hava_doldur portal yeniden başlatılınca (açılışta) "
               "boş günleri doldurur; günlük satır 00:05'te zaten bu yolla yazılır.")
    else:
        yer = ("Lokasyonun internet erişimi (api.open-meteo.com, archive-api.open-meteo.com) ve "
               "Synapse'teki hava_gunluk tablosu (merkez hava_besleyici) birlikte kontrol edilmeli.")
    return [bulgu(
        "hava_durumu", bos[0], "uyari", "Tahmin ve trend",
        "Hava verisi boş: %s" % ", ".join(_tr(t) for t in bos),
        "son %d günün günlük hava özeti dolu" % HAVA_GUN,
        "%d gün boş · %s" % (len(bos), " · ".join(durum)),
        denenen="iki kaynağı yokladı → " + " · ".join(durum),
        tekrar_adimi="Tahmin ve trend kartlarına bak; Veri Görüntüleme'de Hava_ sütunları",
        olasi_yer=yer, kanit={"bos_gunler": bos, "internet": internet, "yedek_gun": yedek})]


def k_portal_sagligi(o):
    cikti = []
    adres = o.portal_url.rstrip("/") + "/_stcore/health"
    kod, neden = o.http(adres, zaman_asimi=8)
    if kod != 200:
        o.bekle(20)                                   # workflow: bir kez yeniden dene
        kod, neden = o.http(adres, zaman_asimi=8)
        if kod != 200:
            cikti.append(bulgu(
                "portal_sagligi", "8501", "kritik", "Portal sağlığı",   # anahtar sabit (bulgu kimliği)
                "Enerji portalı (%s) yanıt vermiyor" % _port(o.portal_url), "HTTP 200",
                "yanıt: %s · %s" % (kod, str(neden)[:80]),
                denenen="20 sn sonra yeniden denedi → yine yanıt yok (portalı yeniden başlatmadı)",
                tekrar_adimi="Lokasyon PC'sinde %s adresini aç" % o.portal_url.rstrip("/"),
                olasi_yer="app_portal.py süreci; watchdog penceresi (PORTAL_BASLAT.bat)"))

    # Eşitleme kaydında son iki tur içinde yeni HATA satırı
    yol = o.yol("cloud_sync.log")
    if os.path.exists(yol):
        sinir = (o.simdi() - timedelta(minutes=2 * TUR_DAKIKA)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(yol, "rb") as f:
                f.seek(max(0, os.path.getsize(yol) - 200_000))
                satirlar = f.read().decode("utf-8", "replace").splitlines()
        except OSError:
            satirlar = []
        hata = [s for s in satirlar if " ERROR " in s and s[:19] >= sinir]
        if hata:
            cikti.append(bulgu(
                "portal_sagligi", "esitleme_hatasi", "uyari", "Portal sağlığı",
                "Eşitleme kaydında son %d dakikada %d hata" % (2 * TUR_DAKIKA, len(hata)),
                "hata satırı yok", hata[-1][:220],
                tekrar_adimi="cloud_sync.log dosyasının son satırlarını aç",
                olasi_yer="cloud_sync.py (hata satırındaki işlem)", kanit={"son": hata[-3:]}))
    return cikti


KONTROLLER = [
    ("gunluk_dongu", "Günlük döngü", k_gunluk_dongu),
    ("sayac_erisimi", "Sayaç erişimi", k_sayac_erisimi),
    ("donmus_veri", "Donmuş veri", k_donmus_veri),
    ("veri_kalitesi", "Veri kalitesi", k_veri_kalitesi),
    ("diyagram_toplami", "Enerji diyagramı toplamları", k_diyagram_toplami),
    ("yerel_bulut", "Yerel ↔ bulut", k_yerel_bulut),
    ("portal_tutarliligi", "Portallar arası tutarlılık", k_portal_tutarliligi),
    ("kapsam", "Kapsam (izlenmeyen sayaç)", k_kapsam),
    ("hava_durumu", "Hava durumu", k_hava_durumu),
    ("portal_sagligi", "Portal sağlığı", k_portal_sagligi),
]


# ══════════════════════════════════════════════════════════════════════════
# TUR — kontrolleri çalıştır, önceki turla karşılaştır, kaydet, gönder
# ══════════════════════════════════════════════════════════════════════════
def _durum_oku(o):
    try:
        with open(o.yol("configs", o.kim["on"] + "_durum.json"), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("acik", {})
            d.setdefault("acilma", {})
            d.setdefault("bekleyen_kapanis", [])
            return d
    except Exception:
        pass
    return {"acik": {}, "acilma": {}, "bekleyen_kapanis": []}


def _durum_yaz(o, d):
    yol = o.yol("configs", o.kim["on"] + "_durum.json")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(yol + ".tmp", yol)


def tur(o=None, kontroller=None):
    """Tek kontrol turu. Dönüş: {zaman, sure_sn, ozet, kontroller, bulgular, kapananlar, gonderim}."""
    o = o or Ortam()
    bas = time.monotonic()
    simdi = o.simdi().astimezone() if o.simdi().tzinfo is None else o.simdi()
    zaman = simdi.isoformat(timespec="seconds")

    sonuclar, bulunan, calisan = [], {}, set()
    for kod, ad, fn in (kontroller or KONTROLLER):
        try:
            liste = fn(o)
            calisan.add(kod)
            for b in liste:
                bulunan[b["anahtar"]] = b
            sonuclar.append({"kod": kod, "ad": ad, "durum": "sorun" if liste else "gecti",
                             "mesaj": liste[0]["baslik"] + (" (+%d)" % (len(liste) - 1) if len(liste) > 1 else "")
                             if liste else ""})
        except Atla as e:
            sonuclar.append({"kod": kod, "ad": ad, "durum": "atlandi", "mesaj": str(e)})
        except Exception as e:                       # kontrolün kendisi bozuldu: agent çökmesin
            logger.exception("Kontrol hatası: %s", kod)
            sonuclar.append({"kod": kod, "ad": ad, "durum": "hata",
                             "mesaj": "%s: %s" % (type(e).__name__, e)})

    d = _durum_oku(o)
    acik, acilma = d["acik"], d["acilma"]
    for anahtar, b in bulunan.items():
        if anahtar in acik:
            b["ilk_gorulme"] = acik[anahtar]["ilk_gorulme"]
            b["gorulme_sayisi"] = acik[anahtar].get("gorulme_sayisi", 1) + 1
            b["acilma_sayisi"] = acik[anahtar].get("acilma_sayisi", 1)
        else:
            acilma[anahtar] = acilma.get(anahtar, 0) + 1
            b["ilk_gorulme"], b["gorulme_sayisi"], b["acilma_sayisi"] = zaman, 1, acilma[anahtar]
        b["son_gorulme"], b["durum"] = zaman, "acik"

    # Önceki turda açık olup bu turda görülmeyen: KONTROLÜ ÇALIŞTIYSA kapanır
    kapananlar = [dict(v, anahtar=k, durum="kapandi", kapanma=zaman)
                  for k, v in acik.items()
                  if k not in bulunan and v.get("kontrol") in calisan]
    kalan = {k: v for k, v in acik.items() if k not in bulunan and v.get("kontrol") not in calisan}

    ozet = {"toplam": len(sonuclar),
            "gecti": sum(1 for s in sonuclar if s["durum"] == "gecti"),
            "sorun": sum(1 for s in sonuclar if s["durum"] == "sorun"),
            "atlandi": sum(1 for s in sonuclar if s["durum"] == "atlandi"),
            "hata": sum(1 for s in sonuclar if s["durum"] == "hata"),
            "acik_bulgu": len(bulunan) + len(kalan)}
    sonuc = {"zaman": zaman, "sure_sn": round(time.monotonic() - bas, 2), "surum": SURUM,
             "ozet": ozet, "kontroller": sonuclar, "bulgular": list(bulunan.values()),
             "kapananlar": kapananlar}

    d["acik"] = dict(kalan, **{k: {a: b[a] for a in ("kontrol", "baslik", "onem", "ilk_gorulme", "son_gorulme",
                                                      "gorulme_sayisi", "acilma_sayisi")}
                               for k, b in bulunan.items()})
    d["bekleyen_kapanis"] = (d["bekleyen_kapanis"] + [{"anahtar": k["anahtar"], "kapanma": zaman}
                                                      for k in kapananlar])[-200:]
    d["acilma"] = dict(list(acilma.items())[-500:])
    d["son_tur"] = {a: sonuc[a] for a in ("zaman", "sure_sn", "surum", "ozet", "kontroller")}
    sonuc["gonderim"] = gonder(o, sonuc, d)
    _durum_yaz(o, d)
    return sonuc


def gonder(o, sonuc, d):
    """Turu ve bulguları veritabanına yazar. Bulut ayarı yoksa hiçbir şey göndermez."""
    if not o.bulut:
        return "bulut ayarı yok — yalnızca yerel dosyaya yazıldı"
    lok, taban = o.bulut["lokasyon_id"], o.bulut["url"] + "/rest/v1/"
    ust = {"Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}
    hatalar = []

    kod, m = o.http(taban + "agent_turlar?on_conflict=lokasyon_id,agent", "POST", _bulut_baslik(o, ust),
                    {"lokasyon_id": lok, "agent": o.kim["agent"], "tur_zamani": sonuc["zaman"],
                     "sure_sn": sonuc["sure_sn"], "surum": SURUM, "ozet": sonuc["ozet"],
                     "kontroller": sonuc["kontroller"]})
    if kod not in (200, 201, 204):
        hatalar.append("tur: %s %s" % (kod, str(m)[:100]))

    if sonuc["bulgular"]:
        alanlar = ("anahtar", "kontrol", "bolum", "onem", "baslik", "beklenen", "bulunan", "denenen",
                   "tekrar_adimi", "olasi_yer", "kanit", "durum", "ilk_gorulme", "son_gorulme",
                   "gorulme_sayisi", "acilma_sayisi")
        govde = [dict({a: b.get(a) for a in alanlar}, lokasyon_id=lok, agent=o.kim["agent"], kapanma=None)
                 for b in sonuc["bulgular"]]
        kod, m = o.http(taban + "agent_bulgular?on_conflict=lokasyon_id,agent,anahtar", "POST",
                        _bulut_baslik(o, ust), govde)
        if kod not in (200, 201, 204):
            hatalar.append("bulgu: %s %s" % (kod, str(m)[:100]))

    # Kapanışlar: gönderilemeyen bir sonraki turda yeniden denenir
    kalan = []
    for k in d["bekleyen_kapanis"]:
        if k["anahtar"] in d["acik"]:
            continue                                  # bu arada yeniden açıldı
        kod, m = o.http(taban + "agent_bulgular?lokasyon_id=eq.%s&agent=eq.%s&anahtar=eq.%s"
                        % (urllib.parse.quote(lok), o.kim["agent"], urllib.parse.quote(k["anahtar"], safe="")),
                        "PATCH", _bulut_baslik(o, {"Content-Type": "application/json",
                                                   "Prefer": "return=minimal"}),
                        {"durum": "kapandi", "kapanma": k["kapanma"]})
        if kod not in (200, 204):
            kalan.append(k)
            hatalar.append("kapanış: %s" % kod)
    d["bekleyen_kapanis"] = kalan
    return "gönderildi" if not hatalar else "gönderim hatası: " + "; ".join(hatalar[:3])


# ══════════════════════════════════════════════════════════════════════════
# SÜREÇ
# ══════════════════════════════════════════════════════════════════════════
def yazdir(s, ad="Enerji Portal Agent'ı"):
    simge = {"gecti": "✓", "sorun": "✗", "atlandi": "–", "hata": "!"}
    print("%s · tur %s · %.1f sn" % (ad, s["zaman"], s["sure_sn"]))
    for k in s["kontroller"]:
        print("  %s %-28s %s" % (simge[k["durum"]], k["ad"], k["mesaj"]))
    for b in s["bulgular"]:
        print("\n  [%s] %s\n     beklenen : %s\n     bulunan  : %s\n     denenen  : %s\n     tekrar   : %s\n     olası yer: %s"
              % (b["onem"].upper(), b["baslik"], b["beklenen"], b["bulunan"], b["denenen"],
                 b["tekrar_adimi"], b["olasi_yer"]))
    for k in s["kapananlar"]:
        print("\n  [KAPANDI] %s" % k.get("baslik", k["anahtar"]))
    print("\n  özet: %(gecti)d geçti · %(sorun)d sorun · %(atlandi)d atlandı · %(hata)d hata" % s["ozet"])
    print("  kayıt: %s" % s["gonderim"])


def dongu(kim=None, kontroller=None, ortam_ek=None):
    """Sürekli döngü. kim: agent kimliği (varsayılan Enerji); kontroller: kontrol listesi;
    ortam_ek: Ortam'a ek argümanlar (ör. Mekanik Zeka'nın portal adresi)."""
    kim = kim or ENERJI
    ortam_ek = ortam_ek or {}
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(os.path.join(BASE_DIR, kim["on"] + ".log"), maxBytes=1_000_000,
                                 backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [AGENT] %(levelname)s %(message)s"))
        logging.getLogger().addHandler(fh)
    except Exception:
        pass
    try:
        from kilit import surec_kilidi_al
        if not surec_kilidi_al(kim["on"]):
            logger.info("%s başka bir süreçte çalışıyor — bu kopya kapanıyor.", kim["ad"])
            return
    except Exception as e:
        logger.warning("Tek kopya kilidi kullanılamadı: %s", e)

    logger.info("%s başladı (sürüm %s, her %d dk; ilk tur %d sn sonra)",
                kim["ad"], SURUM, TUR_DAKIKA, BASLANGIC_BEKLEME_SN)
    time.sleep(BASLANGIC_BEKLEME_SN)
    while True:
        o = Ortam(kim=kim, **ortam_ek)
        ayar = o.ayar()
        if ayar.get("aktif", True) is False:
            logger.info("Agent kapalı (configs/%s.json) — bekliyor", kim["on"])
        else:
            try:
                s = tur(o, kontroller)
                logger.info("Tur: %d geçti, %d sorun, %d atlandı, %d hata · %s",
                            s["ozet"]["gecti"], s["ozet"]["sorun"], s["ozet"]["atlandi"],
                            s["ozet"]["hata"], s["gonderim"])
                for b in s["bulgular"]:
                    if b["gorulme_sayisi"] == 1:
                        logger.warning("YENİ BULGU [%s] %s — %s", b["onem"], b["baslik"], b["bulunan"])
                for k in s["kapananlar"]:
                    logger.info("KAPANDI %s", k.get("baslik", k["anahtar"]))
            except Exception:
                logger.exception("Tur tamamlanamadı")
        time.sleep(max(1, int(ayar.get("tur_dakika", TUR_DAKIKA))) * 60)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [AGENT] %(message)s")
    p = argparse.ArgumentParser(description="Enerji Portal Agent'ı")
    p.add_argument("--tek", action="store_true", help="tek tur çalıştır ve sonucu yazdır")
    if p.parse_args().tek:
        logging.getLogger().setLevel(logging.WARNING)
        yazdir(tur())
    else:
        dongu()
