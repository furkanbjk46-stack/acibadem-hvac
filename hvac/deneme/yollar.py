# -*- coding: utf-8 -*-
"""
YOLLAR — lokasyon programının bütün dosya yollarının TEK kaynağı (Faz 1 / N1, 12.11.2026)
=======================================================================================

DÖRT KATMAN (program klasörü içinde):
  kod     (kök, static/, monthly_report/, rules/, fonts/)  yama ve kurulum paketi günceller
  ayar/   lokasyona ait ayarlar: teknik ekip değiştirir; yama ASLA dokunmaz; yedeklenir;
          değişiklikleri merkezde görünür (K1). Repoda yalnızca ornek_ayar/ şablonu durur.
  durum/  programların çalışma dosyaları (son okuma, son analiz, debounce, işaretler).
          Silinirse programlar kendini toparlar; yama dokunmaz.
  veri/   kalıcı veri ve arşiv (energy_data.csv, AHU geçmişi, raporlar, loglar). Yedeklenir.

KULLANIM — kodda dosya adı yazılmaz, bu modül sorulur:
    import yollar
    yollar.yol("configs/oto_set_durum.json")    # ESKİ (bugünkü) göreli yolu verirsin
    yollar.yol("energy_data.csv")
  Dönüş: yeni yer varsa yeni; yoksa eski yerlerden VAR OLAN (birden çoksa en son
  değiştirilen); hiçbiri yoksa yeni yer. Böylece:
    * taşıma yapılmadan (eski kurulum, testler) her şey bugünkü gibi çalışır,
    * taşımadan sonra herkes yeni yere bakar,
    * yeni kurulum doğrudan yeni yerlere yazar.
  Kayıtta OLMAYAN bir yol sorulursa kök klasördeki aynı yol döner (kod dosyaları vb.).

TAŞIMA (tasi): eski yerdeki dosyaları bir kez yeni yerlerine taşır. Yalnızca watchdog açılırken,
çocuk süreçler başlamadan çağrılır (aynı anda yazan kimse yok). Eski yerde birden çok kopya
varsa (Maslak: ahu_nokta_konfig.json kökte ve configs/'ta, farklı) en son değiştirilen taşınır,
diğerleri durum/tasima_yedek/ altına konur — hiçbir dosya silinmez. Sonuç durum/tasima.json'a yazılır.
"""
import json
import logging
import os
import shutil
from datetime import datetime

KOK = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger("yollar")

# (yeni yer, [eski yerler]) — göreli, "/" ile. Klasörler sonda "/" ile yazılır.
KAYIT = [
    # ── ayar/ ──────────────────────────────────────────────────────────────
    ("ayar/supabase_config.json", ["supabase_config.json"]),
    ("ayar/lokasyon_anahtari.json", ["configs/lokasyon_anahtari.json"]),
    ("ayar/lokasyon_profili.json", ["configs/lokasyon_profili.json"]),
    ("ayar/sayaclar.json", []),
    ("ayar/bacnet_esleme.json", []),
    ("ayar/bacnet_noktalari.json", ["configs/ahu_nokta_konfig.json", "ahu_nokta_konfig.json"]),
    ("ayar/bacnet_okuma_sablonu.xlsx", ["configs/hedefli_okuma_sablonu_2.xlsx", "hedefli_okuma_sablonu_2.xlsx"]),
    ("ayar/bacnet_points.json", ["configs/bacnet_points.json"]),
    ("ayar/yeni_noktalar_start_basinc.json", ["configs/yeni_noktalar_start_basinc.json"]),
    ("ayar/ahu_sat_limitleri.json", ["configs/ahu_sat_limitleri.json"]),
    ("ayar/ahu_tasarim_kapasiteleri.json", ["configs/ahu_tasarim_kapasiteleri.json"]),
    ("ayar/ahu_tasarim_isitma_kapasiteleri.json", ["configs/ahu_tasarim_isitma_kapasiteleri.json"]),
    ("ayar/chiller_fcu_ayarlari.json", ["configs/chiller_fcu_ayarlari.json"]),
    ("ayar/hvac_settings.json", ["configs/hvac_settings.json"]),
    ("ayar/canli_guc_ayar.json", ["configs/canli_guc_ayar.json"]),
    ("ayar/geri_okuma.json", ["configs/geri_okuma.json"]),
    ("ayar/ai_features.json", ["configs/ai_features.json"]),
    ("ayar/bakim_takvimi.json", ["configs/bakim_takvimi.json"]),
    ("ayar/hastane_merkez.json", ["configs/hastane_merkez.json"]),
    ("ayar/tuketim_tahmin.json", ["configs/tuketim_tahmin.json"]),
    ("ayar/enerji_agent.json", ["configs/enerji_agent.json"]),
    ("ayar/mekanik_zeka_agent.json", ["configs/mekanik_zeka_agent.json"]),
    # ── durum/ ─────────────────────────────────────────────────────────────
    ("durum/oto_set_durum.json", ["configs/oto_set_durum.json"]),
    ("durum/canli_guc_son.json", ["configs/canli_guc_son.json"]),
    ("durum/on_kosul_durum.json", ["configs/on_kosul_durum.json"]),
    ("durum/oz_test_sonuc.json", ["configs/oz_test_sonuc.json"]),
    ("durum/saha_teshis_sonuc.json", ["configs/saha_teshis_sonuc.json"]),
    ("durum/veri_alarm_imza.txt", ["configs/veri_alarm_imza.txt"]),
    ("durum/veri_alarmlari.json", ["configs/veri_alarmlari.json"]),
    ("durum/last_analysis.json", ["configs/last_analysis.json"]),
    ("durum/bacnet_donma_temizlik.json", ["configs/bacnet_donma_temizlik.json"]),
    ("durum/enerji_agent_durum.json", ["configs/enerji_agent_durum.json"]),
    ("durum/mekanik_zeka_agent_durum.json", ["configs/mekanik_zeka_agent_durum.json"]),
    ("durum/active_location.json", ["configs/active_location.json"]),
    ("durum/report_notifications.json", ["configs/report_notifications.json"]),
    ("durum/ayar_ozet.json", []),
    ("durum/yama_yedek/", []),
    ("durum/kurulum_kontrol.json", []),
    ("durum/gecmis_bakim_son.txt", []),
    ("durum/sayac_gunluk_ozet.json", []),
    ("veri/ahu_okuma_gunluk.csv", []),
    ("veri/ahu_analiz_gunluk.csv", []),
    ("durum/ayar_gonderilmeyen.json", []),
    ("veri/ayar_degisiklikleri.jsonl", []),
    ("durum/son_yama.json", ["son_yama.json"]),
    ("durum/hvac_son_calisma.txt", ["hvac_son_calisma.txt"]),
    ("durum/sync_son_calisma.txt", ["sync_son_calisma.txt"]),
    ("durum/bildirim_son_gun.txt", ["bildirim_son_gun.txt"]),
    ("durum/alarm_raporu_son_ay.txt", ["alarm_raporu_son_ay.txt"]),
    ("durum/hvac_analiz_trigger.txt", ["hvac_analiz_trigger.txt"]),
    ("durum/modbus_daily_ref.json", ["modbus_daily_ref.json"]),
    ("durum/analizor_guncel_veriler.csv", ["analizor_guncel_veriler.csv"]),
    ("durum/hedefli_enerji_verileri.csv", ["hedefli_enerji_verileri.csv"]),
    ("durum/hvac_ahu_analiz_sonuclari.json", ["hvac_ahu_analiz_sonuclari.json"]),
    ("durum/bacnet_ham_veriler.xlsx", ["bacnet_ham_veriler.xlsx"]),
    ("durum/uretim_tuketim_gecmis.json", ["configs/uretim_tuketim_gecmis.json"]),
    # ── veri/ ──────────────────────────────────────────────────────────────
    ("veri/energy_data.csv", ["energy_data.csv"]),
    ("veri/maintenance_cards.json", ["configs/maintenance_cards.json"]),
    ("veri/bakim_audit_log.jsonl", ["configs/bakim_audit_log.jsonl"]),
    ("veri/ml_forecast_model.pkl", ["configs/ml_forecast_model.pkl"]),
    ("veri/ml_training_data.json", ["ml_training_data.json"]),
    ("veri/savings_training_data.json", ["savings_training_data.json"]),
    ("veri/hvac_onay_log.json", ["hvac_onay_log.json"]),
    ("veri/hvac_analysis_history.csv", ["hvac_analysis_history.csv"]),
    ("veri/ahu_okuma_gecmis/", ["ahu_okuma_gecmis/"]),
    ("veri/ahu_analiz_gecmis/", ["ahu_analiz_gecmis/"]),
    ("veri/hvac_onaylanan/", ["hvac_onaylanan/"]),
    ("veri/gunluk_raporlar/", ["daily_reports/"]),
    ("veri/aylik_raporlar/", ["monthly_reports_summary/"]),
    ("veri/ahu_alarm_raporlari/", ["monthly_report/ahu_alarm_raporlari/"]),
    ("veri/ciktilar/", ["static/outputs/"]),
    ("veri/log/cloud_sync.log", ["cloud_sync.log"]),
    ("veri/log/enerji_agent.log", ["enerji_agent.log"]),
    ("veri/log/mekanik_zeka_agent.log", ["mekanik_zeka_agent.log"]),
]
# Taşımada yeni yerine giden ama programın adla sormadığı eşlikçi dosyalar (dönen log yedekleri vb.)
ESLIKCI = [("veri/log/", "cloud_sync.log.%d", range(1, 10)),
           ("veri/log/", "enerji_agent.log.%d", range(1, 10)),
           ("veri/log/", "mekanik_zeka_agent.log.%d", range(1, 10))]
# Eski configs/ altında adı tarihle değişen yedekler veri/eski_yedekler/ altına
DESEN_YEDEK = [("configs/", "energy_data_yedek_"), ("configs/", "sebeke_gecisi_")]

_ESKIDEN_YENIYE = {}
for _y, _eskiler in KAYIT:
    for _e in _eskiler:
        _ESKIDEN_YENIYE[_e.rstrip("/")] = _y.rstrip("/")
    _ESKIDEN_YENIYE.setdefault(_y.rstrip("/"), _y.rstrip("/"))
_YENIDEN_ESKILERE = {y.rstrip("/"): [e.rstrip("/") for e in es] for y, es in KAYIT}


def _tam(base, goreli):
    return os.path.join(base, *goreli.split("/"))


def yeni_yer(goreli: str) -> str:
    """Eski (ya da yeni) göreli yolun YENİ göreli yeri; kayıtta yoksa kendisi."""
    g = goreli.replace("\\", "/").strip("/")
    return _ESKIDEN_YENIYE.get(g, g)


def yol(goreli: str, base: str = None) -> str:
    """Dosya/klasörün geçerli tam yolu (bkz. modül açıklaması)."""
    base = base or KOK
    yeni = yeni_yer(goreli)
    tam_yeni = _tam(base, yeni)
    if os.path.exists(tam_yeni):
        return tam_yeni
    eskiler = [_tam(base, e) for e in _YENIDEN_ESKILERE.get(yeni, [])]
    var = [p for p in eskiler if os.path.exists(p)]
    if var:
        return max(var, key=os.path.getmtime)
    if yeni.startswith("ayar/") and _tohumla_bir(base, yeni):
        return tam_yeni                     # başlangıç ayarı ornek_ayar/'dan kopyalandı
    if yeni != goreli.replace("\\", "/").strip("/") or yeni.split("/", 1)[0] in ("ayar", "durum", "veri"):
        try:                       # yeni yere ilk yazım: üst klasör hazır olsun (open(..., "w") hata vermesin)
            os.makedirs(os.path.dirname(tam_yeni.rstrip(os.sep)), exist_ok=True)
        except OSError:
            pass
    return tam_yeni


# ── Başlangıç ayarları: ornek_ayar/<lokasyon>/ → ayar/ (yalnızca EKSİK olanlar, bir kez) ─────────
# Repoda lokasyona ait ayar durmaz; her lokasyonun başlangıç ayarı ornek_ayar/<lokasyon_id>/
# altındadır (yoksa ornek_ayar/varsayilan/). Program bir ayar dosyasını bulamazsa oradan kopyalar;
# lokasyonda VAR olan ayar asla ezilmez (teknik ekibin değişikliği korunur).
def _lokasyon_kimligi(base):
    for p in (_tam(base, "ayar/lokasyon_profili.json"), _tam(base, "configs/lokasyon_profili.json")):
        try:
            with open(p, encoding="utf-8-sig") as f:
                lok = str(json.load(f).get("lokasyon_id") or "").strip()
            if lok:
                return lok
        except Exception:
            continue
    return ""


def _tohum_kaynagi(base, yeni, lok=None):
    ad = yeni.split("/", 1)[1]
    lok = lok or _lokasyon_kimligi(base)
    for klasor_adi in ([lok] if lok else []) + ["varsayilan"]:
        p = _tam(base, "ornek_ayar/%s/%s" % (klasor_adi, ad))
        if os.path.exists(p):
            return p
    return None


def _tohumla_bir(base, yeni, lok=None):
    kaynak = _tohum_kaynagi(base, yeni, lok)
    if not kaynak:
        return False
    hedef = _tam(base, yeni)
    try:
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        shutil.copy2(kaynak, hedef)
        logger.info("Başlangıç ayarı kopyalandı: %s → %s", os.path.relpath(kaynak, base), yeni)
        return True
    except OSError as e:
        logger.warning("Başlangıç ayarı kopyalanamadı (%s): %s", yeni, e)
        return False


def tohumla(base: str = None, lokasyon_id: str = None) -> list:
    """ornek_ayar/<lokasyon>/ (ve varsayilan/) içindeki, ayar/'da EKSİK her dosyayı kopyalar.
    lokasyon_id verilmezse profilden okunur; profil yoksa yalnızca varsayilan/ kullanılır
    (lokasyon tahmin edilmez — yanlış lokasyonun ayarıyla açılmaktansa eksik kalmak güvenli)."""
    base = base or KOK
    kopyalanan = []
    lok = lokasyon_id or _lokasyon_kimligi(base)
    for klasor_adi in ([lok] if lok else []) + ["varsayilan"]:
        d = _tam(base, "ornek_ayar/" + klasor_adi)
        if not os.path.isdir(d):
            continue
        for ad in sorted(os.listdir(d)):
            if os.path.isfile(os.path.join(d, ad)) and not os.path.exists(_tam(base, "ayar/" + ad)):
                eskiler = _YENIDEN_ESKILERE.get("ayar/" + ad, [])
                if any(os.path.exists(_tam(base, e)) for e in eskiler):
                    continue            # taşınmamış eski kopya var: o geçerli, tohum gerekmez
                if _tohumla_bir(base, "ayar/" + ad, lok):
                    kopyalanan.append(ad)
    return kopyalanan


def klasor(goreli: str, base: str = None) -> str:
    """yol() gibi; dönen klasör yoksa oluşturur (yazmadan önce)."""
    p = yol(goreli, base)
    os.makedirs(p, exist_ok=True)
    return p


def dosya_icin(goreli: str, base: str = None) -> str:
    """yol() gibi; dosyanın klasörünü oluşturur (yazmadan önce)."""
    p = yol(goreli, base)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def katman(goreli: str) -> str:
    """'ayar' | 'durum' | 'veri' | 'kod' — yama ve yedek kararları için."""
    y = yeni_yer(goreli)
    ilk = y.split("/", 1)[0]
    return ilk if ilk in ("ayar", "durum", "veri") else "kod"


def yama_yazabilir_mi(goreli: str) -> bool:
    """Yama bu yola yazabilir mi? Ayar, durum ve veri katmanına (eski ya da yeni adıyla) yazamaz."""
    g = goreli.replace("\\", "/").strip("/")
    if g.split("/", 1)[0] in ("ayar", "durum", "veri", "configs"):
        return False
    return katman(g) == "kod"


def _kod_iceriyor(p):
    """Klasör Python kodu içeriyor mu (kod paketi asla taşınmaz; 12.11.2026 tuketim_tahmin dersi)."""
    if not os.path.isdir(p):
        return False
    for _kok, _d, dosyalar in os.walk(p):
        if any(f.endswith(".py") for f in dosyalar):
            return True
    return False


def _tasi_bir(base, eski_tam, yeni_tam, yedek_dizin, rapor):
    if _kod_iceriyor(eski_tam):
        raise OSError("kod içeren klasör taşınmaz: %s" % os.path.relpath(eski_tam, base))
    os.makedirs(os.path.dirname(yeni_tam.rstrip(os.sep)), exist_ok=True)
    shutil.move(eski_tam, yeni_tam)
    rapor["tasinan"].append(os.path.relpath(eski_tam, base).replace("\\", "/") + " → "
                            + os.path.relpath(yeni_tam, base).replace("\\", "/"))


def tasi(base: str = None) -> dict:
    """Eski yerlerdeki dosyaları bir kez yeni yerlerine taşır. Tekrar çağrılması zararsızdır."""
    base = base or KOK
    yedek_dizin = _tam(base, "durum/tasima_yedek")
    rapor = {"zaman": datetime.now().isoformat(timespec="seconds"), "tasinan": [], "yedeklenen": [], "hata": []}
    for yeni, eskiler in KAYIT:
        yeni_tam = _tam(base, yeni.rstrip("/"))
        var = [_tam(base, e.rstrip("/")) for e in eskiler if os.path.exists(_tam(base, e.rstrip("/")))]
        if not var:
            continue
        try:
            if os.path.exists(yeni_tam):
                kalanlar = var            # yeni yer zaten dolu: eskiler yalnızca yedeğe
            else:
                en_yeni = max(var, key=os.path.getmtime)
                _tasi_bir(base, en_yeni, yeni_tam, yedek_dizin, rapor)
                kalanlar = [p for p in var if p != en_yeni]
            for p in kalanlar:            # eski / ayrışmış kopyalar silinmez, yedeğe
                if _kod_iceriyor(p):
                    rapor["hata"].append("kod içeren klasör taşınmaz: %s" % os.path.relpath(p, base))
                    continue
                hedef = os.path.join(yedek_dizin, os.path.relpath(p, base))
                os.makedirs(os.path.dirname(hedef), exist_ok=True)
                if os.path.exists(hedef):
                    hedef += ".%s" % datetime.now().strftime("%Y%m%d%H%M%S")
                shutil.move(p, hedef)
                rapor["yedeklenen"].append(os.path.relpath(p, base).replace("\\", "/"))
        except OSError as e:
            rapor["hata"].append("%s: %s" % (yeni, e))
    for hedef_dizin, kalip, sayilar in ESLIKCI:
        for n in sayilar:
            ad = kalip % n
            eski = _tam(base, ad)
            if os.path.exists(eski) and not os.path.exists(_tam(base, hedef_dizin + ad)):
                try:
                    _tasi_bir(base, eski, _tam(base, hedef_dizin + ad), yedek_dizin, rapor)
                except OSError as e:
                    rapor["hata"].append("%s: %s" % (ad, e))
    for dizin, onek in DESEN_YEDEK:
        d = _tam(base, dizin.rstrip("/"))
        if os.path.isdir(d):
            for ad in sorted(os.listdir(d)):
                if ad.startswith(onek):
                    try:
                        _tasi_bir(base, os.path.join(d, ad), _tam(base, "veri/eski_yedekler/" + ad), yedek_dizin, rapor)
                    except OSError as e:
                        rapor["hata"].append("%s: %s" % (ad, e))
    if rapor["tasinan"] or rapor["yedeklenen"] or rapor["hata"]:
        try:
            p = dosya_icin("durum/tasima.json", base)
            gecmis = []
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    gecmis = json.load(f)
            gecmis.append(rapor)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(gecmis, f, ensure_ascii=False, indent=1)
        except Exception as e:                 # rapor yazılamasa da taşıma geçerli
            logger.warning("tasima.json yazılamadı: %s", e)
        logger.info("Klasör düzeni: %d taşındı, %d eski kopya yedeğe, %d hata",
                    len(rapor["tasinan"]), len(rapor["yedeklenen"]), len(rapor["hata"]))
    for k in ("ayar", "durum", "veri"):
        os.makedirs(_tam(base, k), exist_ok=True)
    try:
        rapor["tohum"] = tohumla(base)       # eksik başlangıç ayarları (ör. ayar/sayaclar.json)
    except Exception as e:
        rapor["hata"].append("tohum: %s" % e)
    return rapor
