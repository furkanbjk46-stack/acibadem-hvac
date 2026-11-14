# -*- coding: utf-8 -*-
"""
AYAR KAYDI — lokasyonda yapılan ayar değişikliklerinin kaydı ve merkeze gönderimi (Faz 1 / K1, 12.11.2026)
=====================================================================================================

Ayarları lokasyondaki teknik ekip değiştirir (her lokasyon farklı olabilir); merkez izler.
cloud_sync her heartbeat'te (≈2 dk) tara_ve_gonder() çağırır:

  1. ayar/ klasöründeki her dosya bir önceki hâliyle (durum/ayar_ozet.json) karşılaştırılır.
     JSON dosyalarında ALAN ALAN fark çıkarılır (alan yolu, eski, yeni); diğerlerinde (xlsx)
     yalnızca "dosya değişti" + boyut.
  2. Her fark veri/ayar_degisiklikleri.jsonl'e yazılır (kalıcı yerel kayıt) ve merkeze
     (ayar_degisiklikleri tablosu) gönderilir; değişen dosyanın son hâli lokasyon_ayarlari
     tablosuna yazılır (merkez her lokasyonun güncel ayarını görür; PC arızasında geri yükleme).
  3. Gönderilemeyenler durum/ayar_gonderilmeyen.json'da bekler, sonraki turda yeniden denenir.

İLK TUR: önceki hâl yoksa fark üretilmez; bütün dosyaların hâli merkeze bir kez gönderilir.
GİZLİLİK: bağlantı dosyası ve lokasyon anahtarı ASLA okunmaz ve gönderilmez.
"""
import getpass
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
GIZLI = {"supabase_config.json", "lokasyon_anahtari.json", "panel_sifresi.json"}
ALAN_SINIRI = 200          # bir dosyada bir turda en çok bu kadar alan farkı kaydedilir
DEGER_SINIRI = 500         # eski/yeni değer metni bu uzunlukta kesilir
logger = logging.getLogger("ayar_kaydi")


def _kullanici():
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _duzlestir(v, yol="", cikti=None):
    """JSON → {"a.b[2].c": değer}. Liste elemanında 'ad'/'name'/'ahu_adi' varsa yol onunla yazılır."""
    cikti = {} if cikti is None else cikti
    if isinstance(v, dict):
        for k, x in v.items():
            _duzlestir(x, "%s.%s" % (yol, k) if yol else str(k), cikti)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            etiket = None
            if isinstance(x, dict):
                etiket = x.get("ad") or x.get("name") or (
                    "%s/%s" % (x.get("ahu_adi"), x.get("nokta_tipi")) if x.get("ahu_adi") else None)
            _duzlestir(x, "%s[%s]" % (yol, etiket if etiket is not None else i), cikti)
    else:
        cikti[yol] = v
    return cikti


def _metin(v):
    if v is None:
        return None
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s[:DEGER_SINIRI]


def _dosyalar(base):
    d = os.path.join(base, "ayar")
    if not os.path.isdir(d):
        return []
    return sorted(a for a in os.listdir(d) if os.path.isfile(os.path.join(d, a)) and a not in GIZLI)


def _oku(p):
    with open(p, "rb") as f:
        ham = f.read()
    ozet = hashlib.sha256(ham).hexdigest()[:16]
    icerik = None
    if p.endswith(".json"):
        try:
            icerik = json.loads(ham.decode("utf-8-sig"))
        except Exception:
            icerik = None
    return ozet, len(ham), icerik


IKILI_SINIR = 2_000_000     # JSON olmayan ayar dosyası (xlsx) bu boyuta kadar içeriğiyle merkeze gider


def _ikili(p, boyut):
    """JSON olmayan dosyanın içeriği (base64) — PC arızasında merkezden geri yüklenebilsin (F3).
    Fark hesabına girmez (durum/ayar_ozet.json'a yazılmaz); yalnız lokasyon_ayarlari'na gider."""
    if boyut > IKILI_SINIR:
        return None
    try:
        import base64
        with open(p, "rb") as f:
            return {"_ikili": base64.b64encode(f.read()).decode("ascii")}
    except OSError:
        return None


def tara(base: str = None, simdi: datetime = None) -> dict:
    """Değişiklikleri bulur, yerel kayda yazar. Dönüş: {"degisiklikler": [...], "anlik": [...]}.
    anlik: merkeze gönderilecek dosya hâlleri (ilk turda hepsi, sonra yalnız değişenler)."""
    base = base or BURASI
    zaman = (simdi or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    ozet_yolu = yollar.yol("durum/ayar_ozet.json", base)
    try:
        with open(ozet_yolu, encoding="utf-8") as f:
            onceki = json.load(f)
    except Exception:
        onceki = None
    ilk = onceki is None
    onceki = onceki or {}
    yeni_ozet, degisiklikler, anlik = {}, [], []
    kim = _kullanici()
    for ad in _dosyalar(base):
        try:
            ozet, boyut, icerik = _oku(os.path.join(base, "ayar", ad))
        except OSError as e:
            logger.warning("Ayar dosyası okunamadı (%s): %s", ad, e)
            continue
        yeni_ozet[ad] = {"ozet": ozet, "boyut": boyut, "icerik": icerik}
        eski = onceki.get(ad)
        if eski and eski.get("ozet") == ozet:
            continue
        anlik.append({"dosya": ad, "ozet": ozet, "boyut": boyut,
                      "icerik": icerik if icerik is not None else _ikili(os.path.join(base, "ayar", ad), boyut)})
        if ilk:
            continue
        if eski is None:
            degisiklikler.append({"zaman": zaman, "dosya": ad, "alan": "", "eski": None,
                                  "yeni": "dosya eklendi (%d bayt)" % boyut, "kullanici": kim})
            continue
        if icerik is not None and eski.get("icerik") is not None:
            a, b = _duzlestir(eski["icerik"]), _duzlestir(icerik)
            farklar = [k for k in sorted(set(a) | set(b)) if a.get(k, "<yok>") != b.get(k, "<yok>")]
            for k in farklar[:ALAN_SINIRI]:
                degisiklikler.append({"zaman": zaman, "dosya": ad, "alan": k, "eski": _metin(a.get(k)),
                                      "yeni": _metin(b.get(k)), "kullanici": kim})
            if len(farklar) > ALAN_SINIRI:
                degisiklikler.append({"zaman": zaman, "dosya": ad, "alan": "…",
                                      "eski": None, "yeni": "+%d alan daha" % (len(farklar) - ALAN_SINIRI),
                                      "kullanici": kim})
        else:
            degisiklikler.append({"zaman": zaman, "dosya": ad, "alan": "", "eski": "%s bayt" % eski.get("boyut"),
                                  "yeni": "dosya değişti (%d bayt)" % boyut, "kullanici": kim})
    for ad in sorted(set(onceki) - set(yeni_ozet)):
        if not ilk:
            degisiklikler.append({"zaman": zaman, "dosya": ad, "alan": "", "eski": "dosya vardı",
                                  "yeni": "dosya silindi", "kullanici": kim})
            anlik.append({"dosya": ad, "ozet": None, "boyut": 0, "icerik": None})
    if degisiklikler:
        try:
            with open(yollar.dosya_icin("veri/ayar_degisiklikleri.jsonl", base), "a", encoding="utf-8") as f:
                for d in degisiklikler:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Ayar değişiklik kaydı yazılamadı: %s", e)
        logger.info("Ayar değişikliği: %d alan (%s)", len(degisiklikler),
                    ", ".join(sorted({d["dosya"] for d in degisiklikler})))
    if ilk or degisiklikler or anlik:
        with open(ozet_yolu, "w", encoding="utf-8") as f:
            json.dump(yeni_ozet, f, ensure_ascii=False)
    return {"degisiklikler": degisiklikler, "anlik": anlik}


def tara_ve_gonder(client, lokasyon_id: str, base: str = None) -> dict:
    """tara() + merkeze gönderim; gönderilemeyenler sonraki turda yeniden denenir."""
    base = base or BURASI
    sonuc = tara(base)
    bekleyen_yolu = yollar.yol("durum/ayar_gonderilmeyen.json", base)
    try:
        with open(bekleyen_yolu, encoding="utf-8") as f:
            bekleyen = json.load(f)
    except Exception:
        bekleyen = {"degisiklikler": [], "anlik": {}}
    bekleyen["degisiklikler"] += sonuc["degisiklikler"]
    for a in sonuc["anlik"]:
        bekleyen["anlik"][a["dosya"]] = a
    if not bekleyen["degisiklikler"] and not bekleyen["anlik"]:
        return {"gonderilen": 0}
    gonderilen = 0
    try:
        if bekleyen["degisiklikler"]:
            # returning="minimal": tablo sahaya okunamaz (yalnız ekleme); eklenen satır geri istenmez
            client.table("ayar_degisiklikleri").insert(
                [dict(d, lokasyon_id=lokasyon_id) for d in bekleyen["degisiklikler"]], returning="minimal").execute()
            gonderilen += len(bekleyen["degisiklikler"])
            bekleyen["degisiklikler"] = []
        if bekleyen["anlik"]:
            zaman = datetime.now(timezone.utc).isoformat(timespec="seconds")
            client.table("lokasyon_ayarlari").upsert(
                [{"lokasyon_id": lokasyon_id, "dosya": a["dosya"], "ozet": a["ozet"], "boyut": a["boyut"],
                  "icerik": a["icerik"], "guncelleme": zaman} for a in bekleyen["anlik"].values()],
                on_conflict="lokasyon_id,dosya", returning="minimal").execute()
            bekleyen["anlik"] = {}
    except Exception as e:
        logger.warning("Ayar kaydı merkeze gönderilemedi (sonraki turda yeniden): %s", e)
    with open(bekleyen_yolu, "w", encoding="utf-8") as f:
        json.dump(bekleyen, f, ensure_ascii=False)
    return {"gonderilen": gonderilen, "bekleyen": len(bekleyen["degisiklikler"]) + len(bekleyen["anlik"])}
