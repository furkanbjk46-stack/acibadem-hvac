# -*- coding: utf-8 -*-
"""
MEKANİK ZEKA AGENT'I — sürüm 1 (veri ve servis kontrolleri)
==========================================================

Mekanik Zeka'yı (main_portal.py, 8005 + ahu_collector analizi + oto-set) 7/24
kontrol eder. Enerji Portal Agent'ı ile AYNI çekirdeği kullanır (enerji_agent.py:
tur, bulgu ömrü, veritabanına gönderim, döngü); yalnızca kontrolleri farklıdır.
Watchdog'un yanında ayrı süreç olarak çalışır.

    python mekanik_zeka_agent.py          → sürekli (15 dk'da bir)
    python mekanik_zeka_agent.py --tek    → tek tur, sonucu yazdır, çık

KONTROLLER
  portal_api        8005 ve /api uçları yanıt veriyor mu (health, son analiz, talimat, grafik)
  giris_qr          giriş ekranı, /hvac, /enerji, QR bakım kartı bağlantısı, QR ayarı
  watchdog          agent'ı başlatan watchdog hâlâ çalışıyor mu
  bakim_karti       bakım kartları yükleniyor mu, durumları geçerli mi, tek kart açılıyor mu
  ayarlar           ayarlar okunuyor mu, her ayar izin verilen aralıkta mı, Chiller/FCU ayarları
  otomatik_analiz   10 dk'lık AHU analizi zamanında mı; analiz edilen santral sayısı
  dis_hava          analiz gerçek dış havayla mı yapıldı (20 °C varsayılan değil)
  ahu_veri          santrallerden veri geliyor mu ("Veri Alınamadı" oranı)
  sensor_mantigi    sensör arızalı satır OPTİMAL sayılıyor mu (kural motoru hatası)
  donmus_ahu        AHU okumaları son 4 analizde birebir aynı mı (donmuş BACnet)
  talep_uretim      canlı talep/üretim grafiğinin verisi güncel mi
  oz_test           Mekanik Zeka öz testi (kurallar, eşik–talimat tutarlılığı) geçti mi
  oto_set           son gündüz/gece geçişi uygulandı mı (YALNIZCA İZLER)
  internet          lokasyon internete çıkabiliyor mu (bilgi; yedek yollar devrede)

SINIRLAR (sürüm 1)
  * SALT OKUR. Dosya yazmaz (kendi durum dosyası hariç), süreç başlatmaz.
  * KORUMA ALANI: oto_set ve bacnet_writer yalnızca İZLENİR; agent buraya dokunmaz,
    sorun her zaman insana iş emri olarak gelir. BACnet'e YAZMAZ.

KAPATMA: configs/mekanik_zeka_agent.json → {"aktif": false}
"""
import argparse
import csv
import json
import logging
import os
import sys
import urllib.parse
from datetime import datetime, timedelta

import enerji_agent as C          # ortak çekirdek
from enerji_agent import Atla, bulgu

MZ = {"agent": "mekanik_zeka", "ad": "Mekanik Zeka Agent'ı", "on": "mekanik_zeka_agent"}
PORTAL = "http://127.0.0.1:8005"

ANALIZ_DIKKAT_DK = 40          # analiz 10 dk'da bir; 4 tur kaçarsa uyarı
ANALIZ_KRITIK_DK = 180
VERI_YOK_ORAN = 0.20           # "Veri Alınamadı" santral oranı
VERI_YOK_EN_AZ = 3
DONMA_DOSYA = 4                # son kaç ham okuma karşılaştırılır
DONMA_ORAN = 0.95
DONMA_EN_AZ_NOKTA = 20
OTO_PAY_DK = 30                # geçiş saatinden sonra bu kadar içinde yazılmış olmalı
VARSAYILAN_OAT = 20.0

logger = logging.getLogger("mekanik_zeka_agent")


def _json_oku(o, *yol):
    p = o.yol(*yol)
    if not os.path.exists(p):
        raise Atla("%s yok" % "/".join(yol))
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _zaman(m):
    try:
        z = datetime.fromisoformat(str(m).replace("Z", "+00:00"))
        return z.replace(tzinfo=None) if z.tzinfo is None else z.astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _analiz(o):
    d = _json_oku(o, "hvac_ahu_analiz_sonuclari.json")
    satirlar = ((d.get("sonuc") or {}).get("recs_table") or {}).get("rows") or []
    return d, satirlar


# ══════════════════════════════════════════════════════════════════════════
# KONTROLLER
# ══════════════════════════════════════════════════════════════════════════
def k_portal_api(o):
    uclar = ["/api/health", "/api/last_auto_analysis", "/api/instruction-guide", "/api/uretim_tuketim_gecmis"]
    hatali = []
    for uc in uclar:
        kod, neden = o.http(o.portal_url.rstrip("/") + uc, zaman_asimi=10)
        if kod != 200 and not (uc == "/api/last_auto_analysis" and kod == 404):
            hatali.append((uc, kod, neden))
    if hatali and hatali[0][0] == "/api/health":
        o.bekle(20)                                   # workflow: bir kez yeniden dene
        kod, neden = o.http(o.portal_url.rstrip("/") + "/api/health", zaman_asimi=10)
        if kod == 200:
            hatali = hatali[1:]
    if not hatali:
        return []
    kapali = hatali[0][0] == "/api/health"
    return [bulgu(
        "portal_api", "8005" if kapali else "uclar", "kritik" if kapali else "uyari", "Portal sağlığı",
        "Mekanik Zeka (8005) yanıt vermiyor" if kapali else
        "Mekanik Zeka'da %d API ucu hata veriyor" % len(hatali),
        "HTTP 200", "; ".join("%s → %s %s" % (u, k, str(n)[:60]) for u, k, n in hatali),
        denenen="20 sn sonra yeniden denedi (portalı yeniden başlatmadı)" if kapali else "—",
        tekrar_adimi="Lokasyon PC'sinde http://127.0.0.1:8005%s adresini aç" % hatali[0][0],
        olasi_yer="main_portal.py süreci; watchdog penceresi" if kapali else "main_portal.py ilgili uç")]


def k_otomatik_analiz(o):
    d, satirlar = _analiz(o)
    z = _zaman(d.get("timestamp"))
    if z is None:
        raise Atla("analiz zamanı okunamadı")
    dk = (o.simdi() - z).total_seconds() / 60
    cikti = []
    if dk > ANALIZ_DIKKAT_DK:
        cikti.append(bulgu(
            "otomatik_analiz", "gecikti", "kritik" if dk > ANALIZ_KRITIK_DK else "uyari", "Otomatik analiz",
            "Otomatik AHU analizi %d dakikadır çalışmadı" % dk,
            "10 dakikada bir analiz", "son analiz: %s" % z.strftime("%d.%m.%Y %H:%M"),
            tekrar_adimi="Mekanik Zeka → 'Son Otomatik Analizi Göster'; cloud_sync.log içinde 'HVAC AHU analizi'",
            olasi_yer="cloud_sync.py _heartbeat_loop (hvac_son_calisma.txt), ahu_collector.hvac_analiz_calistir"))
    if not d.get("ahu_sayisi") or not satirlar:
        cikti.append(bulgu(
            "otomatik_analiz", "bos", "kritik", "Otomatik analiz",
            "Son otomatik analizde hiç santral yok", "AHU konfigürasyonundaki santraller",
            "ahu_sayisi=%s, satır=%d" % (d.get("ahu_sayisi"), len(satirlar)),
            tekrar_adimi="Mekanik Zeka analiz tablosuna bak",
            olasi_yer="ahu_nokta_konfig.json / BACnet okuması (ahu_collector)"))
    return cikti


def k_dis_hava(o):
    d, _ = _analiz(o)
    try:
        oat = float(d.get("oat"))
    except (TypeError, ValueError):
        raise Atla("analizde dış hava yok")
    if abs(oat - VARSAYILAN_OAT) > 1e-9:
        return []
    return [bulgu(
        "dis_hava", "varsayilan", "uyari", "Analiz parametreleri",
        "Analiz dış hava yerine varsayılan 20 °C ile yapıldı",
        "gerçek dış hava (internet, BACnet sensörü ya da Synapse)", "20,0 °C (varsayılan)",
        tekrar_adimi="Mekanik Zeka → Analiz Parametreleri → Dış Hava Sıcaklığı",
        olasi_yer="ahu_collector._oat_yedek: internet, BACnet 'DIS HAVA' noktası ve Synapse hava_gunluk "
                  "üçü de alınamadı")]


def k_ahu_veri(o):
    _, satirlar = _analiz(o)
    if not satirlar:
        raise Atla("analiz satırı yok")
    yok = [r.get("Location") or r.get("Mahal") or "?" for r in satirlar if r.get("Rule") == "SKIP_VERI_YOK"]
    if len(yok) < VERI_YOK_EN_AZ or len(yok) / len(satirlar) < VERI_YOK_ORAN:
        return []
    return [bulgu(
        "ahu_veri", "veri_yok", "uyari", "BACnet okuma",
        "%d / %d santralden veri alınamıyor" % (len(yok), len(satirlar)),
        "santrallerin çoğundan BACnet verisi", ", ".join(yok[:8]) + ("…" if len(yok) > 8 else ""),
        tekrar_adimi="Mekanik Zeka → Analiz Dışı filtresi → 'Veri Alınamadı'",
        olasi_yer="BACnet gateway / ağ / ahu_nokta_konfig.json adresleri", kanit={"santraller": yok})]


def k_sensor_mantigi(o):
    _, satirlar = _analiz(o)
    if not satirlar:
        raise Atla("analiz satırı yok")
    hatali = [r for r in satirlar
              if (r.get("SAT Status") == "SENSOR_FAULT" or "Sensör Arızası" in str(r.get("Action", "")))
              and (r.get("Status") != "ANALIZ_DISI" or r.get("Severity") == "OPTIMAL")]
    if not hatali:
        return []
    return [bulgu(
        "sensor_mantigi", "optimal", "kritik", "Kural motoru",
        "Sensör arızalı %d santral analiz dışına düşmüyor / optimal sayılıyor" % len(hatali),
        "sensör arızası → Analiz Dışı, önem OPTİMAL değil",
        "; ".join("%s: %s / %s" % (r.get("Location"), r.get("Status"), r.get("Severity")) for r in hatali[:4]),
        tekrar_adimi="Mekanik Zeka → Analiz Dışı filtresi; ilgili santral satırı",
        olasi_yer="main_portal.py analiz kapısı (ANALIZ_DISI ataması), kural_denetim.py")]


def k_donmus_ahu(o):
    klasor = o.yol("ahu_okuma_gecmis")
    if not os.path.isdir(klasor):
        raise Atla("ahu_okuma_gecmis yok")
    dosyalar = sorted(f for f in os.listdir(klasor) if f.startswith("ahu_bacnet_") and f.endswith(".csv"))[-DONMA_DOSYA:]
    if len(dosyalar) < DONMA_DOSYA:
        raise Atla("karşılaştırılacak %d okuma yok" % DONMA_DOSYA)
    okumalar = []
    for f in dosyalar:
        with open(os.path.join(klasor, f), newline="", encoding="utf-8") as fh:
            okumalar.append({(r.get("AHU_Adi"), r.get("Nokta_Tipi")): r.get("Deger")
                             for r in csv.DictReader(fh) if (r.get("Deger") or "").strip() not in ("", "None")})
    ortak = set(okumalar[0]).intersection(*okumalar[1:])
    if len(ortak) < DONMA_EN_AZ_NOKTA:
        raise Atla("karşılaştırılacak nokta az (%d)" % len(ortak))
    ayni = [k for k in ortak if len({ok[k] for ok in okumalar}) == 1]
    oran = len(ayni) / len(ortak)
    if oran < DONMA_ORAN:
        return []
    return [bulgu(
        "donmus_ahu", "son_okumalar", "kritik", "BACnet okuma",
        "AHU okumaları donmuş: son %d okumada noktaların %%%d'i birebir aynı" % (DONMA_DOSYA, oran * 100),
        "okumalar her analizde değişir", "%d / %d nokta aynı (%s → %s)"
        % (len(ayni), len(ortak), dosyalar[0][11:24], dosyalar[-1][11:24]),
        tekrar_adimi="ahu_okuma_gecmis klasöründeki son dosyaları karşılaştır",
        olasi_yer="BACnet gateway yanıtı / ahu_collector okuma önbelleği")]


def k_talep_uretim(o):
    g = _json_oku(o, "configs", "uretim_tuketim_gecmis.json")
    if not g:
        raise Atla("grafik geçmişi boş")
    z = _zaman(g[-1].get("timestamp"))
    if z is None:
        raise Atla("grafik zamanı okunamadı")
    dk = (o.simdi() - z).total_seconds() / 60
    if dk <= ANALIZ_DIKKAT_DK:
        return []
    return [bulgu(
        "talep_uretim", "bayat", "uyari", "Talep / üretim grafiği",
        "Canlı talep/üretim grafiği %d dakikadır güncellenmiyor" % dk,
        "her analizde (10 dk) yeni nokta", "son nokta: %s" % z.strftime("%d.%m.%Y %H:%M"),
        tekrar_adimi="Mekanik Zeka → Üretilen / Talep Edilen Soğutma grafiği",
        olasi_yer="ahu_collector.gecmis_kaydet (analiz çalışmıyor olabilir)")]


def k_oz_test(o):
    d = _json_oku(o, "configs", "oz_test_sonuc.json")
    if d.get("durum") == "GECTI":
        return []
    kalan = d.get("kalan_dosyalar") or [t.get("dosya") for t in d.get("testler", []) if t.get("durum") != "GECTI"]
    return [bulgu(
        "oz_test", "kaldi", "kritik", "Kurallar ve talimatlar",
        "Mekanik Zeka öz testi kaldı (%s/%s)" % (d.get("gecen", "?"), d.get("toplam", "?")),
        "bütün kural / eşik / talimat testleri geçer", "kalan: %s" % (", ".join(map(str, kalan[:6])) or "?"),
        tekrar_adimi="Lokasyon PC'sinde: python oz_test.py",
        olasi_yer="kalan test dosyasının denetlediği kural (main_portal.py / kural_denetim.py)",
        kanit={"kalan": kalan})]


def _oto_kural(o):
    """Synapse'teki oto-set kuralı (lokasyona özel anahtar varsa o). (aktif, gündüz, gece) ya da None."""
    if not o.bulut:
        return None
    kod, metin = o.http("%s/rest/v1/ayarlar?key=like.oto_*&select=key,value" % o.bulut["url"],
                        basliklar=C._bulut_baslik(o), zaman_asimi=15)
    if kod != 200:
        return None
    ayar = {r.get("key"): r.get("value") for r in json.loads(metin)}
    lok = o.bulut["lokasyon_id"]

    def al(k):
        return ayar.get("%s_%s" % (k, lok), ayar.get(k))
    try:
        return (str(al("oto_set_aktif")).strip().lower() == "true",
                int(float(al("oto_gunduz_saat"))), int(float(al("oto_gece_saat"))))
    except (TypeError, ValueError):
        return None


def k_oto_set(o):
    kural = _oto_kural(o)
    if kural is None:
        raise Atla("oto-set kuralı okunamadı (Synapse)")
    aktif, gunduz, gece = kural
    if not aktif:
        raise Atla("oto-set kapalı (merkez ayarı)")
    d = _json_oku(o, "configs", "oto_set_durum.json")
    simdi = o.simdi()
    # Son geçiş anı: bugünün ve dünün gündüz/gece saatlerinden, şimdiden pay kadar önce olan en yenisi
    adaylar = []
    for g in (0, 1):
        gun = (simdi - timedelta(days=g)).replace(minute=0, second=0, microsecond=0)
        adaylar += [(gun.replace(hour=gunduz), "gündüz"), (gun.replace(hour=gece), "gece")]
    gecmis = [a for a in adaylar if a[0] <= simdi - timedelta(minutes=OTO_PAY_DK)]
    if not gecmis:
        return []
    son_gecis, donem = max(gecmis)
    yazim = _zaman(d.get("zaman"))
    if yazim is not None and yazim >= son_gecis - timedelta(minutes=5):
        return []
    return [bulgu(
        "oto_set", "gecis", "kritik", "Koruma alanı · oto-set",
        "Oto-set son geçişi uygulamadı (%s %s)" % (son_gecis.strftime("%d.%m %H:%M"), donem),
        "%s geçişinde setler yazılır" % son_gecis.strftime("%d.%m %H:%M"),
        "son set yazımı: %s · kayıtlı dönem: %s"
        % (yazim.strftime("%d.%m.%Y %H:%M") if yazim else "hiç", d.get("donem", "?")),
        denenen="yalnızca izler (koruma alanı: agent oto-set'e dokunmaz)",
        tekrar_adimi="cloud_sync.log içinde 'oto_set' satırları (ör. 'tahmin alınamadı, geçiş ertelendi')",
        olasi_yer="oto_set.tahmin_al (internet yoksa geçiş ertelenir), oto_set kuralı; DÜZELTME İNSAN ONAYIYLA")]


def k_internet(o):
    kod, neden = o.http("https://api.open-meteo.com/v1/forecast?latitude=41&longitude=29"
                        "&current=temperature_2m&forecast_days=1", zaman_asimi=6)
    if kod == 200:
        return []
    return [bulgu(
        "internet", "yok", "bilgi", "Ağ",
        "Lokasyon internete çıkamıyor (yedek yollar devrede)", "Open-Meteo yanıt verir",
        "yanıt: %s %s" % (kod, str(neden)[:80]),
        tekrar_adimi="Lokasyon PC'sinde tarayıcıda https://api.open-meteo.com adresini aç",
        olasi_yer="hastane ağı / güvenlik duvarı; hava, dış hava ve sayfa kaynakları yedek yollardan geliyor")]


def _json(o, uc):
    """8005'ten JSON okur: (kod, veri | None)."""
    kod, metin = o.http(o.portal_url.rstrip("/") + uc, zaman_asimi=10)
    if kod != 200:
        return kod, None
    try:
        return kod, json.loads(metin)
    except ValueError:
        return kod, None


def k_giris_qr(o):
    """Portal giriş ekranı, HVAC / Enerji geçişleri ve QR bakım kartı bağlantısı açılıyor mu.
    (Yönlendirmeler izlenir: /hvac → arayüz, /enerji → 8501, /bakim/X → arayüz + bakım kartı.)"""
    taban = o.portal_url.rstrip("/")
    kod, metin = o.http(taban + "/", zaman_asimi=10)
    if kod is None:
        raise Atla("8005 yanıt vermiyor (portal_api kontrolüne bakın)")
    sorun = []
    if kod != 200:
        sorun.append("giriş ekranı (/) → HTTP %s" % kod)
    elif "/hvac" not in metin or "/enerji" not in metin:
        sorun.append("giriş ekranında HVAC / Enerji bağlantısı yok")
    for uc, ad in (("/hvac", "HVAC arayüzü"), ("/enerji", "Enerji portalına geçiş"),
                   ("/bakim/AGENT-TEST", "QR bakım kartı bağlantısı")):
        k, m = o.http(taban + uc, zaman_asimi=15)
        if k != 200:
            sorun.append("%s (%s) → HTTP %s %s" % (ad, uc, k, str(m)[:40] if k is None else ""))
    k, d = _json(o, "/api/qr-config")
    if k != 200:
        sorun.append("QR ayarı (/api/qr-config) → HTTP %s" % k)
    elif not (d or {}).get("lokasyon_id"):
        sorun.append("QR ayarında lokasyon kimliği boş (supabase_config.json lokasyon_id)")
    if not sorun:
        return []
    return [bulgu(
        "giris_qr", "giris", "uyari", "Giriş ekranı ve QR",
        "Giriş ekranı / QR bağlantısında %d sorun" % len(sorun), "giriş ekranı, /hvac, /enerji, /bakim/… açılır",
        "; ".join(sorun),
        tekrar_adimi="Lokasyon PC'sinde http://127.0.0.1:8005/ aç, HVAC ve Enerji düğmelerine bas; "
                     "telefonla bir santral QR etiketini okut",
        olasi_yer="main_portal.py portal_home / hvac_entry / enerji_entry / bakim_qr_link")]


def _surec_canli(pid):
    """Windows'ta süreç yaşıyor mu (OpenProcess + WaitForSingleObject); diğerlerinde os.kill(pid, 0)."""
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000 | 0x1000, False, pid)     # SYNCHRONIZE | QUERY_LIMITED
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) == 0x102          # WAIT_TIMEOUT → çalışıyor
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def k_watchdog(o):
    """Bu agent'ı watchdog başlatır; watchdog'un kendisi hâlâ ayakta mı (ölürse portallar
    düştüğünde kimse yeniden başlatmaz). Agent elle başlatıldıysa atlanır."""
    if os.environ.get("HVAC_WATCHDOG") != "1" and not getattr(o, "watchdog_pid", None):
        raise Atla("agent watchdog'dan başlatılmamış (elle çalıştırma)")
    pid = getattr(o, "watchdog_pid", None) or os.getppid()
    canli = getattr(o, "surec_canli", None) or _surec_canli
    if canli(pid):
        return []
    return [bulgu(
        "watchdog", "surec", "kritik", "Watchdog",
        "Watchdog çalışmıyor (PID %s)" % pid, "portal_watchdog.py çalışır, düşen portalı yeniden başlatır",
        "watchdog süreci yok; portallar düşerse kendiliğinden kalkmaz",
        tekrar_adimi="Lokasyon PC'sinde watchdog penceresi açık mı; görev yöneticisinde python portal_watchdog.py",
        olasi_yer="watchdog penceresi kapatıldı ya da çöktü (BASLAT.bat ile yeniden başlatın)")]


def k_bakim_karti(o):
    kod, d = _json(o, "/api/maintenance")
    if kod is None:
        raise Atla("8005 yanıt vermiyor (portal_api kontrolüne bakın)")
    if kod != 200 or not (d or {}).get("success"):
        return [bulgu("bakim_karti", "api", "uyari", "Bakım kartları", "Bakım kartları yüklenemiyor",
                      "/api/maintenance → success", "HTTP %s" % kod,
                      tekrar_adimi="Mekanik Zeka → Bakım Kartları",
                      olasi_yer="main_portal.py load_maintenance_cards (bakım kartı JSON dosyası bozuk olabilir)")]
    kartlar = (d.get("data") or {}).get("cards") or {}
    gecerli, bilesen = set(d.get("statuses") or []), d.get("components") or []
    bozuk = ["%s/%s=%s" % (c, b, (k or {}).get(b)) for c, k in sorted(kartlar.items()) for b in bilesen
             if (k or {}).get(b) is not None and (k or {}).get(b) not in gecerli]
    cikti = []
    if bozuk:
        cikti.append(bulgu(
            "bakim_karti", "durum", "uyari", "Bakım kartları",
            "%d bakım kartı alanında geçersiz durum" % len(bozuk), "durum: " + "/".join(sorted(gecerli)),
            ", ".join(bozuk[:6]), tekrar_adimi="Mekanik Zeka → Bakım Kartları",
            olasi_yer="bakım kartı JSON dosyası elle düzenlenmiş ya da eski biçimde"))
    if kartlar:
        ilk = sorted(kartlar)[0]
        k, tek = _json(o, "/api/maintenance/" + urllib.parse.quote(ilk, safe=""))
        if k != 200 or not (tek or {}).get("success"):
            cikti.append(bulgu(
                "bakim_karti", "tek", "uyari", "Bakım kartları", "Tek cihazın bakım kartı açılmıyor (%s)" % ilk,
                "HTTP 200", "HTTP %s" % k, tekrar_adimi="QR etiketi / Bakım Kartları → %s" % ilk,
                olasi_yer="main_portal.py get_equipment_maintenance"))
    return cikti


def k_ayarlar(o):
    kod, d = _json(o, "/api/settings")
    if kod is None:
        raise Atla("8005 yanıt vermiyor (portal_api kontrolüne bakın)")
    cikti = []
    if kod != 200 or not (d or {}).get("success"):
        cikti.append(bulgu("ayarlar", "api", "uyari", "Ayarlar", "Mekanik Zeka ayarları okunamıyor",
                           "/api/settings → success", "HTTP %s" % kod, tekrar_adimi="Mekanik Zeka → Ayarlar",
                           olasi_yer="main_portal.py get_settings / ayar dosyası"))
    else:
        disari = []
        for ad, (alt, ust) in sorted((d.get("limits") or {}).items()):
            v = (d.get("settings") or {}).get(ad)
            if isinstance(v, (int, float)) and not alt <= v <= ust:
                disari.append("%s=%s (%s–%s)" % (ad, v, alt, ust))
        if disari:
            cikti.append(bulgu(
                "ayarlar", "sinir", "uyari", "Ayarlar", "%d Mekanik Zeka ayarı izin verilen aralık dışında" % len(disari),
                "her ayar CONFIG_LIMITS içinde", ", ".join(disari[:6]),
                tekrar_adimi="Mekanik Zeka → Ayarlar (bu değerle Kaydet reddedilir)",
                olasi_yer="ayar dosyası elle düzenlenmiş ya da sınırlar sonradan daraltılmış"))
    kod, d = _json(o, "/api/chiller_fcu_ayarlari")
    if kod != 200 or not (d or {}).get("success"):
        cikti.append(bulgu("ayarlar", "chiller_fcu", "uyari", "Ayarlar", "Chiller/FCU kapasite ayarları okunamıyor",
                           "/api/chiller_fcu_ayarlari → success", "HTTP %s" % kod,
                           tekrar_adimi="Mekanik Zeka → Ayarlar → Chiller/FCU",
                           olasi_yer="main_portal.py get_chiller_fcu_ayarlari"))
    return cikti


KONTROLLER = [
    ("portal_api", "API uçları (8005)", k_portal_api),
    ("giris_qr", "Giriş ekranı ve QR", k_giris_qr),
    ("watchdog", "Watchdog", k_watchdog),
    ("bakim_karti", "Bakım kartları", k_bakim_karti),
    ("ayarlar", "Ayarlar", k_ayarlar),
    ("otomatik_analiz", "Otomatik analiz", k_otomatik_analiz),
    ("dis_hava", "Dış hava kaynağı", k_dis_hava),
    ("ahu_veri", "AHU verisi", k_ahu_veri),
    ("sensor_mantigi", "Sensör arızası mantığı", k_sensor_mantigi),
    ("donmus_ahu", "Donmuş AHU okuması", k_donmus_ahu),
    ("talep_uretim", "Talep / üretim grafiği", k_talep_uretim),
    ("oz_test", "Öz test", k_oz_test),
    ("oto_set", "Oto-set geçişi", k_oto_set),
    ("internet", "İnternet erişimi", k_internet),
]


def ortam(**ek):
    return C.Ortam(kim=MZ, portal_url=PORTAL, **ek)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [MZ-AGENT] %(message)s")
    p = argparse.ArgumentParser(description=MZ["ad"])
    p.add_argument("--tek", action="store_true", help="tek tur çalıştır ve sonucu yazdır")
    if p.parse_args().tek:
        logging.getLogger().setLevel(logging.WARNING)
        C.yazdir(C.tur(ortam(), KONTROLLER), MZ["ad"])
    else:
        C.dongu(MZ, KONTROLLER, {"portal_url": PORTAL})
