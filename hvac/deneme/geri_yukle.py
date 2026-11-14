# -*- coding: utf-8 -*-
"""
GERİ YÜKLE — arızalı lokasyon PC'sinin yerine kurulan yeni PC'ye merkezden ayar ve veri (yol haritası F3)
====================================================================================================

Merkezde (thapps) her lokasyonun kopyası duruyor:
  * lokasyon_ayarlari : ayar/ klasöründeki her dosyanın son hâli (K1; JSON içerik, xlsx base64)
  * energy_data       : günlük enerji satırları (cloud_sync)
  * bakim_kartlari    : bakım kartları (cloud_sync)

Yeni PC'de, kurulum paketinden SONRA ve portallar ilk kez açılmadan ÖNCE:

    python geri_yukle.py --lokasyon maslak              # ne yapılacağını gösterir, hiçbir şey yazmaz
    python geri_yukle.py --lokasyon maslak --uygula     # eksik olanları merkezden yazar

Kurallar:
  * Var olan dosyanın üzerine YAZMAZ (--uzerine-yaz verilmedikçe; o zaman eskisi
    durum/geri_yukleme_yedek/ altına alınır).
  * Bağlantı dosyası ve lokasyon anahtarı merkezde yoktur, elle konur (kurulum belgesi).
  * Enerji verisi yalnız yerel dosya yoksa / boşsa ya da merkezde daha çok gün varsa (--uzerine-yaz) yazılır.
  * Bakım kartları yalnız yerel kart dosyası yoksa / boşsa yazılır. Portallar kartsız açılırsa
    kartlar merkezden hiç inmez (eşitleme yalnız yerelde olan kartları günceller).
Sonuç durum/geri_yukleme.json'a yazılır.
"""
import argparse
import base64
import csv
import json
import os
import shutil
import sys
from datetime import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import yollar  # noqa: E402

GIZLI = {"supabase_config.json", "lokasyon_anahtari.json", "panel_sifresi.json"}
ENERJI_ATLA = {"id", "lokasyon_id", "created_at", "updated_at"}


def _sayfali(sorgu_kur, parti=1000, ust=500):
    satirlar = []
    for i in range(ust):
        r = sorgu_kur().range(i * parti, (i + 1) * parti - 1).execute()
        satirlar.extend(r.data or [])
        if len(r.data or []) < parti:
            break
    return satirlar


def _yedekle(p, base):
    hedef = yollar.dosya_icin("durum/geri_yukleme_yedek/%s_%s" % (
        datetime.now().strftime("%Y%m%d_%H%M%S"), os.path.basename(p)), base)
    shutil.copy2(p, hedef)
    return hedef


def _csv_satir_sayisi(p):
    try:
        with open(p, newline="", encoding="utf-8-sig") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except OSError:
        return 0


def plan(client, lokasyon_id, base=None, uzerine_yaz=False):
    """[{tur, hedef, islem, aciklama, veri}] — islem: yaz | atla."""
    base = base or BURASI
    adimlar = []

    # 1) Ayarlar
    ayarlar = _sayfali(lambda: client.table("lokasyon_ayarlari").select("dosya,icerik,boyut,guncelleme")
                       .eq("lokasyon_id", lokasyon_id))
    for a in sorted(ayarlar, key=lambda x: x.get("dosya") or ""):
        ad = os.path.basename(str(a.get("dosya") or ""))
        if not ad or ad in GIZLI:
            continue
        hedef = os.path.join(base, "ayar", ad)
        ic = a.get("icerik")
        if ic is None:
            adimlar.append({"tur": "ayar", "hedef": hedef, "islem": "atla",
                            "aciklama": "merkezde içerik yok (yalnız özet; dosya silinmiş ya da büyük)"})
            continue
        var = os.path.exists(hedef)
        adimlar.append({"tur": "ayar", "hedef": hedef, "islem": "yaz" if (not var or uzerine_yaz) else "atla",
                        "aciklama": ("yerelde var, korunur" if var and not uzerine_yaz else
                                     "merkezdeki hâl (%s)" % str(a.get("guncelleme") or "")[:16]),
                        "veri": ic})

    # 2) Enerji verisi
    enerji = _sayfali(lambda: client.table("energy_data").select("*").eq("lokasyon_id", lokasyon_id).order("Tarih"))
    hedef = yollar.yol("energy_data.csv", base)
    yerel = _csv_satir_sayisi(hedef) if os.path.exists(hedef) else 0
    if not enerji:
        adimlar.append({"tur": "enerji", "hedef": hedef, "islem": "atla", "aciklama": "merkezde enerji verisi yok"})
    elif yerel == 0 or (uzerine_yaz and len(enerji) > yerel):
        adimlar.append({"tur": "enerji", "hedef": hedef, "islem": "yaz",
                        "aciklama": "%d gün (%s → %s); yerelde %d" % (len(enerji), enerji[0].get("Tarih"),
                                                                     enerji[-1].get("Tarih"), yerel), "veri": enerji})
    else:
        adimlar.append({"tur": "enerji", "hedef": hedef, "islem": "atla",
                        "aciklama": "yerelde %d gün var (merkezde %d) — korunur%s" % (
                            yerel, len(enerji), "; --uzerine-yaz ile değiştirilebilir" if len(enerji) > yerel else "")})

    # 3) Bakım kartları
    kartlar = _sayfali(lambda: client.table("bakim_kartlari").select("cihaz,kart,updated_at")
                       .eq("lokasyon_id", lokasyon_id))
    hedef = yollar.yol("configs/maintenance_cards.json", base)
    try:
        with open(hedef, encoding="utf-8") as f:
            yerel_kart = len((json.load(f).get("cards") or {}))
    except (OSError, ValueError, AttributeError):
        yerel_kart = 0
    if not kartlar:
        adimlar.append({"tur": "kart", "hedef": hedef, "islem": "atla", "aciklama": "merkezde bakım kartı yok"})
    elif yerel_kart == 0:
        adimlar.append({"tur": "kart", "hedef": hedef, "islem": "yaz", "aciklama": "%d kart" % len(kartlar),
                        "veri": kartlar})
    else:
        adimlar.append({"tur": "kart", "hedef": hedef, "islem": "atla",
                        "aciklama": "yerelde %d kart var — korunur (eşitleme ikisini birleştirir)" % yerel_kart})
    return adimlar


def uygula(adimlar, base=None):
    base = base or BURASI
    yazilan = []
    for a in adimlar:
        if a["islem"] != "yaz":
            continue
        p = a["hedef"]
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.exists(p):
            a["yedek"] = _yedekle(p, base)
        gecici = p + ".geri_yukle"
        if a["tur"] == "ayar":
            v = a["veri"]
            if isinstance(v, dict) and set(v) == {"_ikili"}:
                with open(gecici, "wb") as f:
                    f.write(base64.b64decode(v["_ikili"]))
            else:
                with open(gecici, "w", encoding="utf-8") as f:
                    json.dump(v, f, ensure_ascii=False, indent=2)
        elif a["tur"] == "enerji":
            sutunlar = [k for k in a["veri"][0] if k not in ENERJI_ATLA]
            if "Tarih" in sutunlar:
                sutunlar.remove("Tarih")
                sutunlar.insert(0, "Tarih")
            with open(gecici, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(sutunlar)
                for r in sorted(a["veri"], key=lambda x: str(x.get("Tarih"))):
                    w.writerow(["" if r.get(k) is None else r.get(k) for k in sutunlar])
        elif a["tur"] == "kart":
            kartlar = {}
            for k in a["veri"]:
                govde = dict(k.get("kart") or {})
                govde["_updated_at"] = k.get("updated_at")
                kartlar[k["cihaz"]] = govde
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump({"last_updated": datetime.now().isoformat(), "updated_by": "geri_yukle", "cards": kartlar},
                          f, ensure_ascii=False, indent=2)
        os.replace(gecici, p)
        yazilan.append(p)
    return yazilan


def _rapor_yaz(base, lokasyon_id, adimlar, uygulandi):
    try:
        with open(yollar.dosya_icin("durum/geri_yukleme.json", base), "w", encoding="utf-8") as f:
            json.dump({"zaman": datetime.now().isoformat(timespec="seconds"), "lokasyon": lokasyon_id,
                       "uygulandi": uygulandi,
                       "adimlar": [{k: v for k, v in a.items() if k != "veri"} for a in adimlar]},
                      f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Merkezden lokasyon ayar ve veri geri yükleme")
    p.add_argument("--lokasyon", required=True)
    p.add_argument("--uygula", action="store_true", help="yaz (verilmezse yalnız gösterir)")
    p.add_argument("--uzerine-yaz", action="store_true", help="var olan dosyaları da değiştir (eskisi yedeklenir)")
    a = p.parse_args()
    import cloud_sync
    client = cloud_sync.get_supabase_client(cloud_sync.load_config())
    if not client:
        sys.exit("Merkeze bağlanılamadı: ayar/supabase_config.json (ve lokasyon anahtarı) yerinde mi?")
    lok = a.lokasyon.strip().lower()
    try:
        adimlar = plan(client, lok, BURASI, a.uzerine_yaz)
    except Exception as e:              # kurulum programı devam eder; ayarlar şablondan gelir
        print("Merkezden okunamadı (%s). Geri yükleme yapılmadı." % str(e)[:200])
        sys.exit(2)
    print("\n GERİ YÜKLEME — %s %s" % (lok, "(UYGULANIYOR)" if a.uygula else "(yalnız gösterim)"))
    for s in adimlar:
        print("  [%-4s] %-6s %-45s %s" % (s["islem"], s["tur"], os.path.relpath(s["hedef"], BURASI), s["aciklama"]))
    if a.uygula:
        yazilan = uygula(adimlar, BURASI)
        print("\n %d dosya yazıldı. Sonra: python kurulum_kontrol.py" % len(yazilan))
    else:
        print("\n Yazmak için --uygula ekleyin.")
    _rapor_yaz(BURASI, lok, adimlar, a.uygula)


if __name__ == "__main__":
    main()
