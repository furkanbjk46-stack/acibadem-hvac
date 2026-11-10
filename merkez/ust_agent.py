# -*- coding: utf-8 -*-
"""
ÜST AGENT · RAPORLAYICI — sürüm 1 (kural tabanlı)
================================================

Portal agent'larının (şimdilik yalnızca Enerji) veritabanına yazdığı bulguları
toplar, her biri için numaralı rapor (iş emri) açar, takip eder ve kapatır.
Raporlar Synapse > Yönetim > Agent katmanları'nda görünür.

Nerede çalışır: thapps. Merkez portal sürecinin içinde arka plan iş parçacığı
olarak başlar (baslat_arka_plan); ileride ayrı servise taşınırsa aynı dosya
`python ust_agent.py` ile kendi başına çalışır — kod değişmez.

KURALLAR (her turda, sırayla)
  1. Topla   : açık bulgular, açık raporlar, agent turları okunur.
  2. Rapor   : açık bulgu için o açılışa ait rapor yoksa yeni rapor açılır
               (RPR-YYYY-AAGG-NNN). Bulgu 3. kez açılıyorsa "tekrarlayan sorun"
               işaretlenir ve önemi yükseltilir (kod incelemesi önerilir).
  3. Takip   : bulgu kapandıysa rapor kapanır:
                 - sen düzeltip yamayı gönderdiysen → "agent tekrar kontrolü geçti"
                 - kimse dokunmadıysa → "sorun kendiliğinden geçti"
               Yamadan sonra (DOGRULAMA_PAYI_DK geçince) bulgu hâlâ görülüyorsa
               → "düzeltme tutmadı", rapor yeniden açılır, deneme sayısı artar.
  4. Çapraz  : turunu bitirmeyen (susan) agent ayrı rapor açar; agent yeniden
               tur atınca kapanır.

SÜRÜM 1 SINIRLARI
  * Yalnızca agent_raporlar'a ve kendi tur satırına yazar. Bulgulara, enerji
    verisine, lokasyonlara ve yama kuyruğuna DOKUNMAZ.
  * Düzeltme ve yama her zaman insandan gelir (Synapse'teki düğmeler).
"""
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SURUM = "1.0"
TUR_SN = 120
SUSMA_DK = 45                 # portal agent'ı 15 dk'da bir tur atar; 3 tur kaçırırsa susmuş sayılır
DOGRULAMA_PAYI_DK = 60        # yama sahaya ulaşıp agent tekrar kontrol edene kadar bekleme
TEKRAR_ESIGI = 3              # bulgu bu kadar kez açıldıysa tekrarlayan sorun
ONEM = {"kritik": "yuksek", "uyari": "orta", "bilgi": "dusuk"}
AGENT_AD = {"enerji": "Enerji Portal Agent'ı", "mekanik_zeka": "Mekanik Zeka Agent'ı",
            "synapse": "Synapse Agent'ı", "ust": "Üst agent"}
ACIK_DURUMLAR = ("acik", "duzeltiliyor", "dogrulaniyor")

logger = logging.getLogger("ust_agent")


def simdi_utc():
    return datetime.now(timezone.utc)


def zaman(m):
    """ISO metin → UTC'li datetime (saat dilimsiz değer UTC kabul edilir; tablolar timestamptz)."""
    if not m:
        return None
    try:
        z = datetime.fromisoformat(str(m).replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    return z if z.tzinfo else z.replace(tzinfo=timezone.utc)


def olay(an, kod, metin):
    return {"zaman": an.isoformat(timespec="seconds"), "olay": kod, "metin": metin}


# ══════════════════════════════════════════════════════════════════════════
# KARAR — saf fonksiyon: veriden yapılacak işler (test edilir, ağ yok)
# ══════════════════════════════════════════════════════════════════════════
def kararlar(bulgular, raporlar, turlar, an=None, gecmis=None):
    """Dönüş: {"yeni": [rapor satırı], "guncelle": [(id, alanlar)]}.

    bulgular : agent_bulgular satırları (açık olanlar + raporu açık olanların bulguları)
    raporlar : kapanmamış agent_raporlar satırları
    turlar   : agent_turlar satırları
    gecmis   : açık bulgulara ait KAPANMIŞ raporlar. Aynı açılış için kapanmış rapor
               varsa yenisi açılmaz: elle kapatılan iş emri, sorun gerçekten geçip
               yeniden çıkana (açılma sayısı artana) kadar sessiz kalır.
    """
    an = an or simdi_utc()
    yeni, guncelle = [], []
    bulgu_id = {b["id"]: b for b in bulgular}
    rapor_bulgu = {}
    for r in gecmis or []:
        if r.get("bulgu_id") is not None:
            rapor_bulgu[(r["bulgu_id"], (r.get("icerik") or {}).get("acilma", 1))] = r
    capraz = {}
    for r in raporlar:
        ic = r.get("icerik") or {}
        if r.get("bulgu_id") is not None:
            rapor_bulgu[(r["bulgu_id"], ic.get("acilma", 1))] = r
        if ic.get("capraz"):
            capraz[ic["capraz"]] = r

    # 2) Açık bulgu → rapor
    for b in bulgular:
        if b.get("durum") != "acik" or b.get("onem") == "bilgi":
            continue                                   # "bilgi" bulgusu iş emri açmaz
        acilma = b.get("acilma_sayisi") or 1
        if (b["id"], acilma) in rapor_bulgu:
            continue
        tekrar = acilma >= TEKRAR_ESIGI
        icerik = {
            "agent_ad": AGENT_AD.get(b.get("agent"), b.get("agent")),
            "lokasyon": b.get("lokasyon_id"), "bolum": b.get("bolum"), "kontrol": b.get("kontrol"),
            "beklenen": b.get("beklenen"), "bulunan": b.get("bulunan"), "denenen": b.get("denenen"),
            "tekrar_adimi": b.get("tekrar_adimi"), "olasi_yer": b.get("olasi_yer"),
            "ilk_gorulme": b.get("ilk_gorulme"), "son_gorulme": b.get("son_gorulme"),
            "gorulme_sayisi": b.get("gorulme_sayisi") or 1, "acilma": acilma, "deneme": 0,
        }
        olaylar = [olay(an, "acildi", "%s bildirdi" % icerik["agent_ad"])]
        if tekrar:
            icerik["tekrarlayan"] = True
            olaylar.append(olay(an, "tekrarlayan",
                                "%d. kez açıldı → kod incelemesi önerilir" % acilma))
        yeni.append({"bulgu_id": b["id"], "lokasyon_id": b.get("lokasyon_id"), "agent": b.get("agent"),
                     "tur": "ariza", "onem": "yuksek" if tekrar else ONEM.get(b.get("onem"), "orta"),
                     "durum": "acik", "baslik": b.get("baslik"), "icerik": icerik, "olaylar": olaylar})

    # 3) Takip: bulguya bağlı açık raporlar
    for r in raporlar:
        if r.get("bulgu_id") is None or r.get("durum") not in ACIK_DURUMLAR:
            continue
        b = bulgu_id.get(r["bulgu_id"])
        if b is None:
            continue
        ic = dict(r.get("icerik") or {})
        olaylar = list(r.get("olaylar") or [])
        bu_acilma = (b.get("acilma_sayisi") or 1) == ic.get("acilma", 1)
        if b.get("durum") == "kapandi" or not bu_acilma:
            # Bulgu kapandı (ya da kapanıp yeni bir açılışa geçti): bu rapor kapanır
            if r["durum"] == "dogrulaniyor":
                cozum, kod = "Düzeltme sahada doğrulandı: agent tekrar kontrolü geçti.", "dogrulandi"
            elif r["durum"] == "duzeltiliyor":
                cozum, kod = ("Sorun düzeltme işaretlenmeden geçti; agent tekrar kontrolü geçti.",
                              "kendiliginden")
            else:
                cozum, kod = "Sorun kendiliğinden geçti: agent sonraki turda görmedi.", "kendiliginden"
            olaylar.append(olay(an, kod, cozum))
            guncelle.append((r["id"], {"durum": "kapandi", "kapanma": an.isoformat(), "cozum": (
                (r.get("cozum") + " · " if r.get("cozum") else "") + cozum),
                "olaylar": olaylar, "guncelleme": an.isoformat()}))
            continue

        degisti = False
        # Yamadan sonra sorun sürüyor → düzeltme tutmadı
        dz = zaman(ic.get("dogrulama_zamani"))
        sg = zaman(b.get("son_gorulme"))
        if r["durum"] == "dogrulaniyor" and dz and sg and sg > dz + timedelta(minutes=DOGRULAMA_PAYI_DK):
            ic["deneme"] = (ic.get("deneme") or 0) + 1
            olaylar.append(olay(an, "tutmadi", "Yama sonrası agent sorunu yine gördü → rapor yeniden açıldı "
                                               "(%d. deneme tutmadı)" % ic["deneme"]))
            ic.pop("dogrulama_zamani", None)
            guncelle.append((r["id"], {"durum": "acik", "icerik": dict(ic, son_gorulme=b.get("son_gorulme"),
                                                                        gorulme_sayisi=b.get("gorulme_sayisi"),
                                                                        bulunan=b.get("bulunan")),
                                       "olaylar": olaylar, "guncelleme": an.isoformat()}))
            continue
        # Kanıt tazelensin (son görülme, sayaç, son bulunan değer)
        for a, k in (("son_gorulme", "son_gorulme"), ("gorulme_sayisi", "gorulme_sayisi"), ("bulunan", "bulunan")):
            if b.get(k) is not None and ic.get(a) != b.get(k):
                ic[a] = b.get(k)
                degisti = True
        if degisti:
            guncelle.append((r["id"], {"icerik": ic, "guncelleme": an.isoformat()}))

    # 4) Çapraz: susan agent
    for t in turlar:
        if t.get("agent") == "ust":
            continue
        anahtar = "susan:%s:%s" % (t.get("lokasyon_id"), t.get("agent"))
        tz = zaman(t.get("tur_zamani"))
        sustu = tz is not None and (an - tz) > timedelta(minutes=SUSMA_DK)
        r = capraz.get(anahtar)
        if sustu and r is None:
            ad = AGENT_AD.get(t.get("agent"), t.get("agent"))
            yeni.append({"bulgu_id": None, "lokasyon_id": t.get("lokasyon_id"), "agent": t.get("agent"),
                         "tur": "capraz", "onem": "yuksek", "durum": "acik",
                         "baslik": "%s susuyor (%s)" % (ad, t.get("lokasyon_id")),
                         "icerik": {"capraz": anahtar, "agent_ad": "Üst agent", "lokasyon": t.get("lokasyon_id"),
                                    "bolum": "Agent'ların kendisi", "kontrol": "agent %d dk içinde tur atar" % SUSMA_DK,
                                    "beklenen": "son tur ≤ %d dk önce" % SUSMA_DK,
                                    "bulunan": "son tur: %s" % t.get("tur_zamani"),
                                    "tekrar_adimi": "Lokasyon PC'sinde enerji_agent.log dosyasına bak",
                                    "olasi_yer": "PC kapalı / watchdog / enerji_agent.py çöktü / ağ"},
                         "olaylar": [olay(an, "acildi", "Üst agent: %s turunu bitirmedi" % ad)]})
        elif not sustu and r is not None and r.get("durum") in ACIK_DURUMLAR:
            olaylar = list(r.get("olaylar") or []) + [olay(an, "kendiliginden", "Agent yeniden tur attı.")]
            guncelle.append((r["id"], {"durum": "kapandi", "kapanma": an.isoformat(),
                                       "cozum": "Agent yeniden tur attı.", "olaylar": olaylar,
                                       "guncelleme": an.isoformat()}))
    return {"yeni": yeni, "guncelle": guncelle}


# ══════════════════════════════════════════════════════════════════════════
# VERİTABANI (PostgREST, service_role)
# ══════════════════════════════════════════════════════════════════════════
class Db:
    def __init__(self, url, key, http=None):
        self.taban = url.rstrip("/") + "/rest/v1/"
        self.key = key
        self.http = http or self._http

    def _http(self, url, yontem="GET", govde=None, ek=None):
        h = {"apikey": self.key, "Authorization": "Bearer " + self.key, "Content-Type": "application/json"}
        h.update(ek or {})
        istek = urllib.request.Request(url, method=yontem, headers=h,
                                       data=json.dumps(govde, ensure_ascii=False).encode("utf-8")
                                       if govde is not None else None)
        try:
            with urllib.request.urlopen(istek, timeout=20) as c:
                metin = c.read().decode("utf-8")
                return c.status, (json.loads(metin) if metin.strip() else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")[:300]

    def oku(self, yol):
        kod, veri = self.http(self.taban + yol)
        if kod != 200:
            raise RuntimeError("okuma %s: %s %s" % (yol.split("?")[0], kod, veri))
        return veri or []

    def ekle(self, tablo, satir):
        kod, veri = self.http(self.taban + tablo, "POST", satir, {"Prefer": "return=representation"})
        if kod not in (200, 201):
            raise RuntimeError("ekleme %s: %s %s" % (tablo, kod, veri))
        return veri

    def degistir(self, tablo, filtre, alanlar):
        kod, veri = self.http(self.taban + tablo + "?" + filtre, "PATCH", alanlar, {"Prefer": "return=minimal"})
        if kod not in (200, 204):
            raise RuntimeError("güncelleme %s: %s %s" % (tablo, kod, veri))

    def ust_tur_yaz(self, ozet, an):
        kod, veri = self.http(self.taban + "agent_turlar?on_conflict=lokasyon_id,agent", "POST",
                              {"lokasyon_id": "merkez", "agent": "ust", "tur_zamani": an.isoformat(),
                               "surum": SURUM, "ozet": ozet, "kontroller": []},
                              {"Prefer": "resolution=merge-duplicates,return=minimal"})
        if kod not in (200, 201, 204):
            raise RuntimeError("tur: %s %s" % (kod, veri))


def rapor_no(db, an):
    """RPR-YYYY-AAGG-NNN (İstanbul günü)."""
    gun = an.astimezone(timezone(timedelta(hours=3)))
    onek = "RPR-%s-%s-" % (gun.strftime("%Y"), gun.strftime("%m%d"))
    mevcut = db.oku("agent_raporlar?select=rapor_no&rapor_no=like.%s*" % urllib.parse.quote(onek))
    n = max([int(r["rapor_no"].rsplit("-", 1)[1]) for r in mevcut if r.get("rapor_no")] or [0]) + 1
    return "%s%03d" % (onek, n)


SERVIS_TAZE_DK = 5             # servis bu kadar dk içinde tur attıysa merkezdeki yedek kopya çalışmaz


def servis_aktif(db, an=None):
    """Ayrı agent servisi (agent_servisi.py) son SERVIS_TAZE_DK dakikada tur attı mı?"""
    an = an or simdi_utc()
    try:
        r = db.oku("agent_turlar?select=tur_zamani,ozet&lokasyon_id=eq.merkez&agent=eq.ust")
    except Exception:
        return False
    if not r or (r[0].get("ozet") or {}).get("kaynak") != "servis":
        return False
    z = zaman(r[0].get("tur_zamani"))
    return bool(z and an - z < timedelta(minutes=SERVIS_TAZE_DK))


def tur(db, an=None, kaynak="merkez"):
    """Tek üst agent turu. Dönüş: {"acilan": [...], "guncellenen": n, "ozet": {...}}.

    kaynak: "servis" (agent_servisi.py) ya da "merkez" (portal içindeki yedek kopya)."""
    an = an or simdi_utc()
    raporlar = db.oku("agent_raporlar?select=*&durum=in.(acik,duzeltiliyor,dogrulaniyor)")
    acik_bulgu = db.oku("agent_bulgular?select=*&durum=eq.acik")
    gerekli = {r["bulgu_id"] for r in raporlar if r.get("bulgu_id") is not None} - {b["id"] for b in acik_bulgu}
    ek = db.oku("agent_bulgular?select=*&id=in.(%s)" % ",".join(str(i) for i in sorted(gerekli))) if gerekli else []
    turlar = db.oku("agent_turlar?select=lokasyon_id,agent,tur_zamani")
    acik_id = sorted({b["id"] for b in acik_bulgu})
    gecmis = db.oku("agent_raporlar?select=id,bulgu_id,icerik,durum&durum=eq.kapandi&bulgu_id=in.(%s)"
                    % ",".join(str(i) for i in acik_id)) if acik_id else []
    k = kararlar(acik_bulgu + ek, raporlar, turlar, an, gecmis)

    acilan = []
    for satir in k["yeni"]:
        satir = dict(satir, rapor_no=rapor_no(db, an), olusturma=an.isoformat(), guncelleme=an.isoformat())
        db.ekle("agent_raporlar", satir)
        acilan.append(satir["rapor_no"])
        logger.info("Rapor açıldı %s: %s", satir["rapor_no"], satir["baslik"])
    for rid, alanlar in k["guncelle"]:
        db.degistir("agent_raporlar", "id=eq.%d" % rid, alanlar)
    ozet = {"acik_bulgu": len(acik_bulgu), "acik_rapor": len(raporlar) + len(acilan)
            - sum(1 for _, a in k["guncelle"] if a.get("durum") == "kapandi"),
            "acilan": len(acilan), "guncellenen": len(k["guncelle"]), "kaynak": kaynak}
    db.ust_tur_yaz(ozet, an)
    return {"acilan": acilan, "guncellenen": len(k["guncelle"]), "ozet": ozet}


# ══════════════════════════════════════════════════════════════════════════
# İNSAN EYLEMLERİ (Synapse düğmeleri) — sürüm 1'de düzelten sensin
# ══════════════════════════════════════════════════════════════════════════
EYLEMLER = {
    "baslat": ("duzeltiliyor", "Düzeltmeye başlandı"),
    "yama": ("dogrulaniyor", "Düzeltildi, yama gönderildi; agent tekrar kontrol edecek"),
    "kapat": ("kapandi", "Elle kapatıldı"),
}


def eylem_alanlari(rapor, eylem, kim, not_=None, an=None):
    """Bir rapora düğmeyle yapılan işlemin yazılacak alanları."""
    an = an or simdi_utc()
    durum, metin = EYLEMLER[eylem]
    ic = dict(rapor.get("icerik") or {})
    olaylar = list(rapor.get("olaylar") or [])
    olaylar.append(olay(an, eylem, metin + (" — " + not_.strip() if not_ and not_.strip() else "")
                       + " (%s)" % kim))
    alanlar = {"durum": durum, "olaylar": olaylar, "duzelten": kim, "guncelleme": an.isoformat()}
    if eylem == "yama":
        ic["dogrulama_zamani"] = an.isoformat()
        alanlar["icerik"] = ic
    if eylem == "kapat":
        alanlar["kapanma"] = an.isoformat()
        alanlar["cozum"] = "Elle kapatıldı" + (": " + not_.strip() if not_ and not_.strip() else "")
    elif not_ and not_.strip():
        alanlar["cozum"] = not_.strip()
    return alanlar


# ══════════════════════════════════════════════════════════════════════════
# ÇALIŞTIRMA — merkez sürecinde arka plan (tek kopya) ya da kendi başına
# ══════════════════════════════════════════════════════════════════════════
_ARKA = {"thread": None, "son": None, "hata": None}
_ARKA_KILIT = threading.Lock()


def _dongu(url, key, bekle=TUR_SN):
    """Merkez portalının içindeki YEDEK kopya: ayrı servis çalışıyorsa hiçbir şey yapmaz."""
    db = Db(url, key)
    while True:
        try:
            if servis_aktif(db):
                _ARKA["son"], _ARKA["hata"] = simdi_utc(), None
                time.sleep(bekle)
                continue
            s = tur(db)
            _ARKA["son"], _ARKA["hata"] = simdi_utc(), None
            if s["acilan"] or s["guncellenen"]:
                logger.info("Üst agent turu: %d rapor açıldı, %d güncellendi", len(s["acilan"]), s["guncellenen"])
        except Exception as e:                          # tablo yok, ağ, yetki: döngü sürer
            _ARKA["hata"] = "%s: %s" % (type(e).__name__, e)
            logger.warning("Üst agent turu tamamlanamadı: %s", _ARKA["hata"])
        time.sleep(bekle)


def baslat_arka_plan(url, key):
    """Merkez portal sürecinde TEK kopya arka plan döngüsü başlatır. True: çalışıyor."""
    if not url or not key or os.environ.get("SYNAPSE_UST_AGENT", "1") == "0":
        return False
    with _ARKA_KILIT:
        t = _ARKA["thread"]
        if t is not None and t.is_alive():
            return True
        t = threading.Thread(target=_dongu, args=(url, key), name="ust_agent", daemon=True)
        t.start()
        _ARKA["thread"] = t
        logger.info("Üst agent arka planda başladı (her %d sn)", TUR_SN)
        return True


def arka_plan_durumu():
    t = _ARKA["thread"]
    return {"calisiyor": bool(t and t.is_alive()), "son": _ARKA["son"], "hata": _ARKA["hata"]}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [UST] %(message)s")
    u, k = os.environ.get("SYNAPSE_URL", ""), os.environ.get("SYNAPSE_SERVICE_KEY", "")
    if not u or not k:
        sys.exit("SYNAPSE_URL ve SYNAPSE_SERVICE_KEY ortam değişkenleri gerekli.")
    if "--tek" in sys.argv:
        print(json.dumps(tur(Db(u, k)), ensure_ascii=False, indent=1))
    else:
        _dongu(u, k)
