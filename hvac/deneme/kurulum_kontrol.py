# -*- coding: utf-8 -*-
"""
KURULUM KONTROLÜ — yeni lokasyonun kurulumu ve "ilk gün" raporu (yol haritası F4, 12.11.2026)
==========================================================================================

    python kurulum_kontrol.py --ilk --lokasyon atasehir --ad "Acıbadem Ataşehir"
        ayar/lokasyon_profili.json yoksa oluşturur, klasör düzenini kurar, eksik ayarları
        ornek_ayar/<lokasyon>/ (yoksa varsayilan/) şablonundan kopyalar, sonra kontrolü çalıştırır.
    python kurulum_kontrol.py
        Kontrol: ayarlar tamam mı, merkeze (thapps) ulaşılıyor mu, sayaçlara ağdan erişiliyor mu,
        agent'lar ilk turda ne buluyor. Sonuç ekrana ve durum/kurulum_kontrol.json'a yazılır.

Hiçbir sayaca / BACnet cihazına YAZMAZ; sayaç kontrolü yalnızca Modbus portuna (502) bağlantı açıp kapatır.
Merkeze veri göndermez (agent turu bulut ayarı olmadan çalıştırılır).
"""
import argparse
import json
import os
import socket
import sys
import time
import urllib.request
from datetime import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import yollar  # noqa: E402

TAMAM, UYARI, EKSIK = "TAMAM", "UYARI", "EKSİK"


def _json(goreli, base):
    p = yollar.yol(goreli, base)
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def ilk_kurulum(base, lokasyon, ad=None):
    """Profil yoksa yazar; taşıma + şablondan eksik ayarlar; portlar (bir kez). Dönüş: kopyalanan ayarlar.

    Profil, lokasyonun şablonunda (ornek_ayar/<lokasyon>/lokasyon_profili.json) varsa ONDAN yazılır —
    koordinat ve ısıtma hatları şablondan gelir (13.11.2026 kurulum provası: boş koordinatla yazılıyordu,
    hava tahmini ve oto-set tahmini çalışmazdı). Verilen ad şablondakinin yerine geçer.
    """
    profil = yollar.yol("configs/lokasyon_profili.json", base)
    if not os.path.exists(profil):
        veri = {"lokasyon_id": lokasyon, "ad": ad or lokasyon, "sehir": "", "enlem": None, "boylam": None,
                "_aciklama": "Kurulumda yazıldı (kurulum_kontrol.py). Koordinat hava tahmini için gerekir."}
        sablon = yollar._tohum_kaynagi(base, "ayar/lokasyon_profili.json", lokasyon)
        if sablon and os.path.basename(os.path.dirname(sablon)) != lokasyon:
            sablon = None                # 'varsayilan' şablonun koordinatı bu lokasyonun değil
        try:
            with open(sablon or "", encoding="utf-8-sig") as f:
                veri = dict(json.load(f), lokasyon_id=lokasyon)
            if ad:
                veri["ad"] = ad
        except (OSError, ValueError, TypeError):
            pass
        profil = yollar.dosya_icin("ayar/lokasyon_profili.json", base)
        with open(profil, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=1)
    rapor = yollar.tasi(base)            # klasör düzeni + profildeki lokasyonun şablonu
    kopyalanan = (rapor.get("tohum") or []) + yollar.tohumla(base, lokasyon)
    try:                                 # portlar: varsayılan doluysa sıradaki boş port; sonra SABİT
        import portlar
        p = portlar.sec(base)
        if p["yazildi"]:
            kopyalanan.append("portlar.json (%s)" % ", ".join("%s=%d" % kv for kv in p["portlar"].items()))
    except Exception:
        pass
    return kopyalanan


def _lisans_sor():
    import lisans
    return lisans.lisans_kontrol(deneme=1)


def _surum(base):
    """Bu PC'deki program sürümü: son uygulanan yama, yoksa yamanın / paketin sürüm dosyası."""
    for goreli in ("durum/son_yama.json", "yama_surumu.json"):
        try:
            with open(os.path.join(base, *goreli.split("/")), encoding="utf-8") as f:
                v = (json.load(f) or {}).get("versiyon")
            if v:
                return v
        except (OSError, ValueError):
            continue
    return None


def _portlar(base=None):
    try:
        import portlar
        return portlar.yukle(base or BURASI)
    except Exception:
        return {"enerji": 8501, "mekanik_zeka": 8005}


def lisans_onayini_bekle(sure_sn, lisans=None, _bekle=None, aralik_sn=20) -> bool:
    """Kurulumun son adımı: lisans talebi Synapse'te onay bekliyorsa en çok sure_sn bekler
    (portallar onaydan sonra açılır). Dönüş: lisans geçerli mi."""
    lisans = lisans or _lisans_sor
    _bekle = _bekle or time.sleep
    lis = lisans() or {}
    if lis.get("gecerli") or lis.get("talep") != "bekliyor":
        return bool(lis.get("gecerli"))
    print("\n Lisans talebi Synapse'e gönderildi. Synapse → Yönetim → Lisanslar'dan onaylayın.")
    print(" Makine ID: %s — onay bekleniyor (en çok %d dk)..." % (lis.get("makine_id"), sure_sn // 60), flush=True)
    sinir = time.monotonic() + sure_sn
    while time.monotonic() < sinir:
        _bekle(aralik_sn)
        lis = lisans() or {}
        if lis.get("gecerli"):
            print(" Lisans onaylandı.", flush=True)
            return True
    print(" Lisans bu sürede onaylanmadı; onaydan sonra program kendiliğinden açılır.", flush=True)
    return False


def portallari_bekle(sure_sn, http=None, _bekle=None, base=None):
    """Enerji ve Mekanik Zeka (ayar/portlar.json) yanıt verene kadar bekler. Dönüş: ikisi de açıldı mı."""
    p = _portlar(base)
    import time
    http = http or _http
    _bekle = _bekle or time.sleep
    sinir = time.monotonic() + sure_sn
    while True:
        if (http("http://127.0.0.1:%d/_stcore/health" % p["enerji"]) == 200
                and http("http://127.0.0.1:%d/api/health" % p["mekanik_zeka"]) == 200):
            return True
        if time.monotonic() >= sinir:
            return False
        _bekle(5)


def kontrol(base=None, tcp=None, http=None, agent_turu=True, lisans=None):
    """[(başlık, durum, açıklama)] — tcp(ip, port) / http(url) / lisans() testlerde değiştirilir."""
    base = base or BURASI
    tcp = tcp or _tcp
    http = http or _http
    lisans = lisans or _lisans_sor
    sonuc = []

    def ekle(b, d, a):
        sonuc.append({"kontrol": b, "durum": d, "aciklama": a})

    profil = _json("configs/lokasyon_profili.json", base) or {}
    lok = str(profil.get("lokasyon_id") or "")
    ekle("Lokasyon profili", TAMAM if lok else EKSIK,
         "kimlik: %s, ad: %s" % (lok, profil.get("ad")) if lok else "ayar/lokasyon_profili.json yok ya da kimlik boş")
    if lok:
        ekle("Koordinat (hava tahmini)", TAMAM if profil.get("enlem") and profil.get("boylam") else UYARI,
             "%s, %s" % (profil.get("enlem"), profil.get("boylam")) if profil.get("enlem")
             else "enlem / boylam boş — hava verisi Synapse'ten de alınamaz")

    sayac = (_json("ayar/sayaclar.json", base) or {}).get("sayaclar") or []
    ekle("Sayaç listesi", TAMAM if sayac else EKSIK,
         "%d sayaç (%s)" % (len(sayac), ", ".join(sorted({s.get("tur", "?") for s in sayac}))) if sayac
         else "ayar/sayaclar.json yok ya da boş — enerji verisi okunmaz")
    esleme = _json("ayar/bacnet_esleme.json", base) or {}
    ekle("BACnet eşlemesi", TAMAM if esleme.get("noktalar") else EKSIK,
         "%d nokta, %d ısıtma hattı" % (len(esleme.get("noktalar") or {}), len(esleme.get("isitma_hatlari") or []))
         if esleme.get("noktalar") else "ayar/bacnet_esleme.json yok — BACnet değerleri tabloya yazılmaz")
    noktalar = _json("configs/ahu_nokta_konfig.json", base) or []
    ekle("AHU nokta listesi (Mekanik Zeka)", TAMAM if noktalar else EKSIK,
         "%d nokta, %d santral" % (len(noktalar), len({(n.get('lokasyon'), n.get('ahu_adi')) for n in noktalar}))
         if noktalar else "ayar/bacnet_noktalari.json yok — Mekanik Zeka analiz yapamaz")
    ekle("BACnet okuma şablonu", TAMAM if os.path.exists(yollar.yol("configs/hedefli_okuma_sablonu_2.xlsx", base))
         else EKSIK, "ayar/bacnet_okuma_sablonu.xlsx")

    # Portlar (kurulumda seçilir, sonra sabit): şu an dolu olanı, çalışan portal mı tutuyor bilinmez —
    # yanıt veren portal tutuyor sayılır.
    _pt = _portlar(base)
    try:
        import portlar as _portlar_mod
        _bos = _portlar_mod.bos_mu
    except Exception:
        _bos = lambda port: True  # noqa: E731
    _yol = {"enerji": "/_stcore/health", "mekanik_zeka": "/api/health"}
    _dolu = [ad for ad, port in _pt.items()
             if not _bos(port) and http("http://127.0.0.1:%d%s" % (port, _yol[ad])) != 200]
    ekle("Portlar", UYARI if _dolu else TAMAM,
         "Enerji %d, Mekanik Zeka %d%s" % (_pt["enerji"], _pt["mekanik_zeka"],
                                          ("; başka program tutuyor: " + ", ".join(_dolu)) if _dolu else ""))

    baglanti = _json("supabase_config.json", base) or {}
    url = str(baglanti.get("supabase_url") or "")
    if not url or "BURAYA" in url:
        ekle("Merkez bağlantısı", EKSIK, "ayar/supabase_config.json yok ya da ayarlanmamış")
    else:
        kod = http(url.rstrip("/") + "/rest/v1/")
        ekle("Merkez bağlantısı", TAMAM if kod in (200, 401) else EKSIK,
             "%s → HTTP %s" % (url, kod) if kod else "%s → ulaşılamıyor (ağ / DNS / güvenlik duvarı)" % url)
    if url and "BURAYA" not in url:
        try:
            lis = lisans() or {}
        except Exception as e:
            lis = {"gecerli": False, "hata": str(e)}
        ekle("Lisans", TAMAM if lis.get("gecerli") else EKSIK,
             ("%s (makine: %s)" % (lis.get("makine_adi") or "geçerli", lis.get("makine_id")) if lis.get("gecerli")
              else "Onay bekleniyor: talep Synapse'e gönderildi — Yönetim → Lisanslar'dan onaylayın (Makine ID: %s)"
              % lis.get("makine_id") if lis.get("talep") == "bekliyor"
              else "%s — Makine ID: %s (Genel Merkez Enerji Yönetimi'ne iletin)" % (lis.get("hata"), lis.get("makine_id"))))
    surum = _surum(base)
    ekle("Program sürümü", TAMAM if surum else UYARI, surum or "sürüm dosyası yok (yama_surumu.json)")
    ekle("Lokasyon anahtarı", TAMAM if os.path.exists(yollar.yol("configs/lokasyon_anahtari.json", base)) else UYARI,
         "ayar/lokasyon_anahtari.json" + ("" if os.path.exists(yollar.yol("configs/lokasyon_anahtari.json", base))
                                          else " yok — ortak anahtarla çalışır (Alp Bey'den lokasyon anahtarı)"))

    if sayac:
        ulasilamayan = [s["ad"] for s in sayac if s.get("ip") and not tcp(s["ip"], 502)]
        ekle("Sayaçlara ağ erişimi (Modbus 502)", TAMAM if not ulasilamayan else UYARI,
             "%d / %d sayaca ulaşıldı%s" % (len(sayac) - len(ulasilamayan), len(sayac),
                                          ("; ulaşılamayan: " + ", ".join(ulasilamayan)) if ulasilamayan else ""))
    if agent_turu:
        try:
            import logging
            logging.disable(logging.WARNING)
            import enerji_agent as C
            import mekanik_zeka_agent as M
            _pt = _portlar(base)
            for kim, kontroller, port in ((C.ENERJI, C.KONTROLLER, "http://127.0.0.1:%d" % _pt["enerji"]),
                                          (M.MZ, M.KONTROLLER, "http://127.0.0.1:%d" % _pt["mekanik_zeka"])):
                t = C.tur(C.Ortam(dizin=base, bulut=None, kim=kim, portal_url=port), kontroller)
                o = t["ozet"]
                ekle("%s (ilk tur)" % kim["ad"], TAMAM if not o.get("sorun") and not o.get("hata") else UYARI,
                     "%d geçti, %d sorun, %d atlandı%s" % (o.get("gecti", 0), o.get("sorun", 0), o.get("atlandi", 0),
                                                         ("; " + "; ".join(k["mesaj"][:60] for k in t["kontroller"]
                                                                           if k["durum"] == "sorun")[:300])
                                                         if o.get("sorun") else ""))
        except Exception as e:
            ekle("Agent ilk turu", UYARI, "çalıştırılamadı: %s" % e)
    try:
        with open(yollar.dosya_icin("durum/kurulum_kontrol.json", base), "w", encoding="utf-8") as f:
            json.dump({"zaman": datetime.now().isoformat(timespec="seconds"), "sonuc": sonuc}, f, ensure_ascii=False, indent=1)
    except OSError:
        pass
    return sonuc


def _tcp(ip, port, zaman_asimi=1.5):
    try:
        with socket.create_connection((ip, port), timeout=zaman_asimi):
            return True
    except OSError:
        return False


def _http(url, zaman_asimi=6):
    try:
        with urllib.request.urlopen(url, timeout=zaman_asimi) as c:
            return c.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Lokasyon kurulum kontrolü")
    p.add_argument("--ilk", action="store_true")
    p.add_argument("--lokasyon")
    p.add_argument("--ad")
    p.add_argument("--agentsiz", action="store_true", help="agent ilk turunu atla")
    p.add_argument("--bekle", type=int, default=0, help="agent turundan önce portalları en çok bu kadar sn bekle")
    a = p.parse_args()
    if a.ilk:
        if not a.lokasyon:
            p.error("--ilk için --lokasyon gerekli")
        lok = a.lokasyon.strip().lower()
        kop = ilk_kurulum(BURASI, lok, a.ad)
        if kop:
            print("Şablondan kopyalanan ayarlar: %s" % ", ".join(kop))
        elif not os.path.isdir(os.path.join(BURASI, "ornek_ayar", lok)):
            print("ornek_ayar/%s şablonu yok — sayaç, BACnet ve nokta ayarları lokasyonda hazırlanmalı." % lok)
        else:
            print("Şablondan kopyalanacak yeni ayar yok (lokasyonun ayarları zaten var).")
    if a.bekle and not a.agentsiz:
        try:
            lisans_onayini_bekle(1800)              # yeni PC: Synapse'te onay gelene kadar (en çok 30 dk)
        except Exception:
            pass
        print("Portalların açılması bekleniyor (en çok %d sn)..." % a.bekle, flush=True)
        if not portallari_bekle(a.bekle):
            print("Portallar bu sürede açılmadı; agent turu yine çalıştırılıyor (sonuçta görünür).")
    sonuc = kontrol(BURASI, agent_turu=not a.agentsiz)
    print("\n KURULUM KONTROLÜ — %s" % datetime.now().strftime("%d.%m.%Y %H:%M"))
    for s in sonuc:
        print("  [%-5s] %-38s %s" % (s["durum"], s["kontrol"], s["aciklama"]))
    eksik = [s for s in sonuc if s["durum"] == EKSIK]
    print("\n %s" % ("Eksik yok — lokasyon canlıya alınabilir." if not eksik
                     else "%d eksik var; tamamlanmadan canlıya alınmamalı." % len(eksik)))
    sys.exit(1 if eksik else 0)


if __name__ == "__main__":
    main()
