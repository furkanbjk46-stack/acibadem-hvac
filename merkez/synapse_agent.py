# -*- coding: utf-8 -*-
"""
SYNAPSE AGENT'I — sürüm 1 (merkez ve lokasyonların genel durumu)
================================================================

thapps'te canliizleme-agent servisinin içinde (agent_servisi.py) 15 dk'da bir
çalışır; mevcut kısıtlı ust_agent rolüyle bağlanır (veritabani/07_synapse_agent_yetkisi.sql).

KONTROLLER
  lokasyon_baglanti   her lokasyonun son sinyali (heartbeat) 10 dk'dan eski mi
  gunluk_esitleme     09:00'dan sonra her lokasyonun dünkü enerji satırı gelmiş mi (yalnız tarih)
  canli_sayac         lokasyonun canlı güç verisi akıyor mu; sayaçların çoğu bayat mı
  yama_kuyrugu        30 dk'dan uzun "bekliyor"da takılı ya da "hata" ile biten yama var mı
  komutlar            10 dk'dan uzun bekleyen ya da son 24 saatte başarısız saha komutu var mı
  surum               lokasyonlar aynı sürümde mi (bilgi)
  anahtarsiz_erisim   veritabanına anahtarsız istek reddediliyor mu (401)
  synapse_portal      Synapse'in sağlık adresi 200 mü
  sunucu              disk, bellek, servisler, gece yedeği

SINIRLAR
  * Yalnızca OKUR (yetkisi de yalnız okuma). Yazdığı tek şey kendi tur ve bulgu satırları
    (lokasyon_id='merkez', agent='synapse').
  * Diske YAZMAZ: servis salt okunur dosya sisteminde çalışır. Bulgu geçmişi (ilk görülme,
    görülme / açılma sayısı) veritabanındaki kendi satırlarından okunur.
"""
import json
import logging
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SURUM = "1.0"
AGENT = "synapse"
LOKASYON = "merkez"
TUR_SN = 15 * 60
IST = timezone(timedelta(hours=3))
PORTAL_SAGLIK = "https://thapps.acibadem.com.tr/canliizleme/_stcore/health"
SERVISLER = ("canliizleme", "postgrest-synapse", "canliizleme-agent", "nginx")

PING_DIKKAT_DK = 10
PING_KRITIK_DK = 60
ESITLEME_SAAT = (9, 0)              # 08:00 eşitlemesi + pay
CANLI_DIKKAT_DK = 10
BAYAT_SAYAC_DK = 15
BAYAT_SAYAC_ORAN = 0.3
YAMA_BEKLEME_DK = 30
KOMUT_BEKLEME_DK = 10
DISK_DIKKAT, DISK_KRITIK = 85, 92
BELLEK_DIKKAT_YUZDE = 10            # boş bellek bu yüzdenin altına inerse
YEDEK_DIKKAT_SAAT = 26
YEDEK_KLASORU = "/opt/Backup"

logger = logging.getLogger("synapse_agent")


class Atla(Exception):
    """Kontrol bu turda yapılamadı (sorun sayılmaz)."""


def bulgu(kontrol, ayirt, onem, bolum, baslik, beklenen, bulunan, tekrar_adimi="", olasi_yer="",
          denenen="—", kanit=None):
    return {"anahtar": "%s:%s" % (kontrol, ayirt), "kontrol": kontrol, "onem": onem, "bolum": bolum,
            "baslik": baslik, "beklenen": beklenen, "bulunan": bulunan, "denenen": denenen,
            "tekrar_adimi": tekrar_adimi, "olasi_yer": olasi_yer, "kanit": kanit or {}}


def zaman(m, saat_dilimsiz=IST):
    """ISO metin → İstanbul saatli datetime. Saat dilimsiz değer (ping_zamani) İstanbul kabul edilir."""
    if not m:
        return None
    try:
        z = datetime.fromisoformat(str(m).replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    return (z if z.tzinfo else z.replace(tzinfo=saat_dilimsiz)).astimezone(IST)


def tr(z):
    return z.strftime("%d.%m %H:%M") if z else "hiç"


# ══════════════════════════════════════════════════════════════════════════
# ORTAM — veritabanı, saat, sunucu. Testler sahteleriyle değiştirir.
# ══════════════════════════════════════════════════════════════════════════
class Ortam:
    def __init__(self, url, key, simdi=None, http=None, sunucu=None):
        self.taban = url.rstrip("/") + "/rest/v1/"
        self.key = key
        self._simdi = simdi
        self.http = http or self._http
        self.sunucu = sunucu or Sunucu()

    def simdi(self):
        return (self._simdi or datetime.now(timezone.utc)).astimezone(IST)

    def _http(self, url, yontem="GET", govde=None, ek=None, anahtarsiz=False, zaman_asimi=20):
        h = {} if anahtarsiz else {"apikey": self.key, "Authorization": "Bearer " + self.key}
        h["Content-Type"] = "application/json"
        h.update(ek or {})
        istek = urllib.request.Request(url, method=yontem, headers=h,
                                       data=json.dumps(govde, ensure_ascii=False).encode("utf-8")
                                       if govde is not None else None)
        try:
            with urllib.request.urlopen(istek, timeout=zaman_asimi) as c:
                metin = c.read().decode("utf-8")
                try:
                    return c.status, (json.loads(metin) if metin.strip() else None)
                except ValueError:
                    return c.status, metin[:300]              # sağlık adresi düz metin döner ("ok")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")[:300]
        except Exception as e:
            return None, str(getattr(e, "reason", e))

    def oku(self, yol):
        kod, veri = self.http(self.taban + yol)
        if kod != 200:
            raise Atla("okunamadı: %s (%s)" % (yol.split("?")[0], kod))
        return veri or []


class Sunucu:
    """Yetkisiz bir kullanıcının da görebildiği sunucu bilgileri (sudo yok)."""

    def disk(self):
        d = shutil.disk_usage("/")
        return d.used, d.total, d.free

    def bellek(self):
        degerler = {}
        with open("/proc/meminfo", encoding="ascii") as f:
            for satir in f:
                ad, _, deger = satir.partition(":")
                degerler[ad] = int(deger.split()[0])
        return degerler["MemAvailable"], degerler["MemTotal"]

    def servis(self, ad):
        r = subprocess.run(["systemctl", "is-active", ad], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or r.stderr.strip()

    def yedekler(self):
        import sql_durumu
        return sql_durumu.yedekler(YEDEK_KLASORU)


# ══════════════════════════════════════════════════════════════════════════
# KONTROLLER
# ══════════════════════════════════════════════════════════════════════════
def k_lokasyon_baglanti(o):
    loklar = o.oku("lokasyonlar?select=lokasyon_id,isim,ping_zamani")
    if not loklar:
        raise Atla("kayıtlı lokasyon yok")
    cikti = []
    for l in loklar:
        z = zaman(l.get("ping_zamani"))
        dk = (o.simdi() - z).total_seconds() / 60 if z else None
        if dk is None or dk > PING_DIKKAT_DK:
            cikti.append(bulgu(
                "lokasyon_baglanti", l["lokasyon_id"],
                "kritik" if dk is None or dk > PING_KRITIK_DK else "uyari", "Harita",
                "%s çevrimdışı (son sinyal %s)" % (l.get("isim") or l["lokasyon_id"], tr(z)),
                "son sinyal ≤ %d dk önce" % PING_DIKKAT_DK,
                "son sinyal: %s" % ("hiç" if dk is None else "%d dk önce" % dk),
                tekrar_adimi="Synapse haritası / Yönetim → Lokasyon bağlantısı",
                olasi_yer="lokasyon PC'si kapalı, HVAC penceresi kapatıldı ya da ağ (cloud_sync heartbeat)"))
    return cikti


def k_gunluk_esitleme(o):
    simdi = o.simdi()
    if (simdi.hour, simdi.minute) < ESITLEME_SAAT:
        raise Atla("08:00 eşitlemesi için henüz erken")
    dun = (simdi - timedelta(days=1)).date().isoformat()
    loklar = [l["lokasyon_id"] for l in o.oku("lokasyonlar?select=lokasyon_id")]
    satir = o.oku('energy_data?select=lokasyon_id,Tarih&Tarih=gte.%s' % (simdi - timedelta(days=7)).date().isoformat())
    son = {}
    for r in satir:
        son[r["lokasyon_id"]] = max(son.get(r["lokasyon_id"], ""), str(r.get("Tarih"))[:10])
    cikti = []
    for lok in loklar:
        if son.get(lok, "") < dun:
            cikti.append(bulgu(
                "gunluk_esitleme", lok, "uyari", "Lokasyon eşitlemesi",
                "%s: dünün (%s) enerji satırı Synapse'e gelmedi" % (lok, dun),
                "08:00 eşitlemesiyle dünün satırı", "son gün: %s" % (son.get(lok) or "son 7 günde yok"),
                tekrar_adimi="Synapse → lokasyon detayı → günlük tablo",
                olasi_yer="lokasyonda data_bridge (00:05) ya da cloud_sync (08:00); Enerji agent'ının bulgularına bakın"))
    return cikti


def k_canli_sayac(o):
    satir = o.oku("canli_guc?select=lokasyon_id,cihaz,olcum_zamani")
    if not satir:
        raise Atla("canlı güç verisi yok")
    lok = {}
    for r in satir:
        lok.setdefault(r["lokasyon_id"], []).append((r.get("cihaz"), zaman(r.get("olcum_zamani"))))
    simdi, cikti = o.simdi(), []
    for ad, cihazlar in sorted(lok.items()):
        zamanlar = [z for _, z in cihazlar if z]
        en_yeni = max(zamanlar) if zamanlar else None
        if en_yeni is None or (simdi - en_yeni).total_seconds() / 60 > CANLI_DIKKAT_DK:
            cikti.append(bulgu(
                "canli_sayac", "%s:akis" % ad, "uyari", "Canlı izleme",
                "%s canlı güç verisi akmıyor (son ölçüm %s)" % (ad, tr(en_yeni)),
                "dakikalık canlı ölçüm", "son ölçüm: %s" % tr(en_yeni),
                tekrar_adimi="Synapse → lokasyon detayı → Canlı",
                olasi_yer="lokasyonda canli_guc.py / Modbus okuma / cloud_sync"))
            continue
        bayat = sorted(c for c, z in cihazlar if not z or (simdi - z).total_seconds() / 60 > BAYAT_SAYAC_DK)
        if bayat and len(bayat) / len(cihazlar) >= BAYAT_SAYAC_ORAN:
            cikti.append(bulgu(
                "canli_sayac", "%s:bayat" % ad, "uyari", "Canlı izleme",
                "%s: %d / %d canlı sayaç %d dk'dan eski" % (ad, len(bayat), len(cihazlar), BAYAT_SAYAC_DK),
                "sayaçların çoğu güncel", ", ".join(bayat[:8]) + ("…" if len(bayat) > 8 else ""),
                tekrar_adimi="Synapse → lokasyon detayı → Canlı (bayat sayaç notları)",
                olasi_yer="ilgili sayaçların ağ bağlantısı / Modbus adresleri", kanit={"sayaclar": bayat}))
    return cikti


def k_yama_kuyrugu(o):
    simdi = o.simdi()
    satir = o.oku("guncellemeler?select=id,versiyon,hedef,durum,created_at&durum=in.(bekliyor,hata)"
                  "&order=created_at.desc&limit=50")
    cikti = []
    for y in satir:
        z = zaman(y.get("created_at"))
        if y.get("durum") == "hata":
            cikti.append(bulgu(
                "yama_kuyrugu", "hata:%s" % y["id"], "kritik", "Yama kuyruğu",
                "Yama %s (%s) lokasyonda hata ile bitti" % (y.get("versiyon"), y.get("hedef")),
                "durum = tamamlandı", "durum = hata (%s)" % tr(z),
                tekrar_adimi="Lokasyonda cloud_sync.log içinde yamanın dosya satırları",
                olasi_yer="lokasyonda dosya yazma izni / disk; cloud_sync.check_and_apply_update"))
        elif z and (simdi - z).total_seconds() / 60 > YAMA_BEKLEME_DK:
            cikti.append(bulgu(
                "yama_kuyrugu", "bekliyor:%s" % y["id"], "uyari", "Yama kuyruğu",
                "Yama %s (%s) %d dakikadır bekliyor" % (y.get("versiyon"), y.get("hedef"),
                                                       (simdi - z).total_seconds() / 60),
                "lokasyon 2 dk içinde alır", "gönderildi: %s, hâlâ 'bekliyor'" % tr(z),
                tekrar_adimi="Yönetim → Yama kuyruğu",
                olasi_yer="hedef lokasyon çevrimdışı ya da cloud_sync güncelleme kontrolü çalışmıyor"))
    return cikti


def k_komutlar(o):
    simdi = o.simdi()
    sinir = (simdi - timedelta(hours=24)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    satir = o.oku("komutlar?select=id,lokasyon,nokta_adi,durum,created_at,executed_at&created_at=gte.%s"
                  "&order=created_at.desc&limit=500" % sinir)
    cikti = []
    bekleyen = [k for k in satir if k.get("durum") == "bekliyor" and zaman(k.get("created_at"))
                and (simdi - zaman(k.get("created_at"))).total_seconds() / 60 > KOMUT_BEKLEME_DK]
    if bekleyen:
        cikti.append(bulgu(
            "komutlar", "bekleyen", "uyari", "Uzaktan kontrol",
            "%d saha komutu %d dk'dan uzun süredir bekliyor" % (len(bekleyen), KOMUT_BEKLEME_DK),
            "lokasyon komutu 1 dk içinde uygular",
            "; ".join("%s %s (%s)" % (k.get("lokasyon"), k.get("nokta_adi"), tr(zaman(k.get("created_at"))))
                      for k in bekleyen[:4]),
            tekrar_adimi="Ayarlar → Uzaktan Kontrol → Son komutlar",
            olasi_yer="lokasyon çevrimdışı ya da cloud_sync komut döngüsü (bacnet_writer)"))
    basarisiz = [k for k in satir if k.get("durum") in ("hata", "dogrulanamadi", "suresi_doldu")]
    if basarisiz:
        cikti.append(bulgu(
            "komutlar", "basarisiz", "uyari", "Uzaktan kontrol",
            "Son 24 saatte %d saha komutu başarısız" % len(basarisiz), "komutlar 'tamamlandı'",
            "; ".join("%s %s → %s" % (k.get("lokasyon"), k.get("nokta_adi"), k.get("durum")) for k in basarisiz[:4]),
            tekrar_adimi="Ayarlar → Uzaktan Kontrol → Son komutlar",
            olasi_yer="BACnet erişimi / nokta adresi; oto-set ya da elle gönderim"))
    return cikti


def k_surum(o):
    loklar = [l for l in o.oku("lokasyonlar?select=lokasyon_id,versiyon") if l.get("versiyon")]
    if len(loklar) < 2:
        raise Atla("karşılaştırılacak 2 lokasyon yok")
    surumler = {}
    for l in loklar:
        surumler.setdefault(str(l["versiyon"]), []).append(l["lokasyon_id"])
    if len(surumler) == 1:
        return []
    return [bulgu(
        "surum", "fark", "bilgi", "Yama kuyruğu", "Lokasyonlar farklı sürümde",
        "tüm lokasyonlar aynı sürümde", "; ".join("%s: %s" % (v, ", ".join(sorted(l)))
                                                  for v, l in sorted(surumler.items())),
        tekrar_adimi="Yönetim → Lokasyonlar", olasi_yer="yama yalnız bazı lokasyonlara gönderildi")]


def k_anahtarsiz_erisim(o):
    kod, _ = o.http(o.taban + "energy_data?select=lokasyon_id&limit=1", anahtarsiz=True, zaman_asimi=10)
    if kod in (401, 403):
        return []
    if kod is None:
        raise Atla("veritabanına ulaşılamadı")
    return [bulgu(
        "anahtarsiz_erisim", "energy_data", "kritik", "Güvenlik",
        "Veritabanı anahtarsız isteğe yanıt veriyor (HTTP %s)" % kod, "HTTP 401 (anahtarsız erişim kapalı)",
        "HTTP %s" % kod, tekrar_adimi="Anahtarsız: GET /synapse-db/rest/v1/energy_data",
        olasi_yer="PostgREST db-anon-role ayarı / nginx (yönetici)")]


def k_synapse_portal(o):
    kod, neden = o.http(PORTAL_SAGLIK, anahtarsiz=True, zaman_asimi=15)
    if kod == 200:
        return []
    return [bulgu(
        "synapse_portal", "saglik", "kritik", "Ana sayfa",
        "Synapse portalı yanıt vermiyor (HTTP %s)" % kod, "HTTP 200", "%s %s" % (kod, str(neden)[:80]),
        tekrar_adimi="https://thapps.acibadem.com.tr/canliizleme/ adresini aç",
        olasi_yer="canliizleme.service (canliizlemectl status / errors)")]


def k_sunucu(o):
    s, cikti = o.sunucu, []
    try:
        kul, top, bos = s.disk()
        oran = kul / top * 100
        if oran >= DISK_DIKKAT:
            cikti.append(bulgu(
                "sunucu", "disk", "kritik" if oran >= DISK_KRITIK else "uyari", "Yerel sunucu",
                "Sunucu diski %%%d dolu" % oran, "< %%%d" % DISK_DIKKAT, "%.1f GB boş" % (bos / 1024 ** 3),
                olasi_yer="büyüyen loglar / yedekler (yönetici)"))
    except OSError:
        pass
    try:
        bos, top = s.bellek()
        if bos / top * 100 < BELLEK_DIKKAT_YUZDE:
            cikti.append(bulgu(
                "sunucu", "bellek", "uyari", "Yerel sunucu",
                "Sunucuda boş bellek %%%d" % (bos / top * 100), "≥ %%%d" % BELLEK_DIKKAT_YUZDE,
                "%d MB boş" % (bos // 1024), olasi_yer="bellek tüketen süreç (yönetici)"))
    except (OSError, KeyError, ValueError):
        pass
    for ad in SERVISLER:
        try:
            d = s.servis(ad)
        except Exception as e:
            d = "okunamadı: %s" % e
        if d != "active":
            cikti.append(bulgu(
                "sunucu", "servis:%s" % ad, "kritik", "Yerel sunucu",
                "%s servisi çalışmıyor (%s)" % (ad, d), "active", d,
                tekrar_adimi="canliizlemectl status / agent-status", olasi_yer="%s.service (yönetici)" % ad))
    yed = s.yedekler()
    if yed is not None:
        if not yed:
            cikti.append(bulgu("sunucu", "yedek", "bilgi", "Yerel sunucu", "Gece yedeği görülemedi",
                               "synapse_db_*.dump", "%s boş ya da okunamadı" % YEDEK_KLASORU,
                               olasi_yer="/opt/Backup/Backup_Synapse.sh (yönetici)"))
        else:
            saat = (o.simdi() - yed[0]["zaman"]).total_seconds() / 3600
            if saat > YEDEK_DIKKAT_SAAT:
                cikti.append(bulgu(
                    "sunucu", "yedek", "kritik" if saat > 2 * YEDEK_DIKKAT_SAAT else "uyari", "Yerel sunucu",
                    "Son gece yedeği %d saat önce" % saat, "her gece 01:30", yed[0]["ad"],
                    olasi_yer="/opt/Backup/Backup_Synapse.sh, cron (yönetici)"))
    return cikti


KONTROLLER = [
    ("lokasyon_baglanti", "Lokasyon bağlantısı", k_lokasyon_baglanti),
    ("gunluk_esitleme", "Lokasyon eşitlemesi", k_gunluk_esitleme),
    ("canli_sayac", "Canlı sayaçlar", k_canli_sayac),
    ("yama_kuyrugu", "Yama kuyruğu", k_yama_kuyrugu),
    ("komutlar", "Saha komutları", k_komutlar),
    ("surum", "Lokasyon sürümleri", k_surum),
    ("anahtarsiz_erisim", "Anahtarsız erişim", k_anahtarsiz_erisim),
    ("synapse_portal", "Synapse portalı", k_synapse_portal),
    ("sunucu", "Yerel sunucu", k_sunucu),
]


# ══════════════════════════════════════════════════════════════════════════
# TUR — bulgu geçmişi veritabanındaki kendi satırlarından (diske yazılmaz)
# ══════════════════════════════════════════════════════════════════════════
def tur(o, kontroller=None):
    bas = time.monotonic()
    an = o.simdi().astimezone(timezone.utc).isoformat(timespec="seconds")
    sonuclar, bulunan, calisan = [], {}, set()
    for kod, ad, fn in (kontroller or KONTROLLER):
        try:
            liste = fn(o)
            calisan.add(kod)
            for b in liste:
                bulunan[b["anahtar"]] = b
            sonuclar.append({"kod": kod, "ad": ad, "durum": "sorun" if liste else "gecti",
                             "mesaj": (liste[0]["baslik"] + (" (+%d)" % (len(liste) - 1) if len(liste) > 1 else ""))
                             if liste else ""})
        except Atla as e:
            sonuclar.append({"kod": kod, "ad": ad, "durum": "atlandi", "mesaj": str(e)})
        except Exception as e:
            logger.exception("Synapse kontrol hatası: %s", kod)
            sonuclar.append({"kod": kod, "ad": ad, "durum": "hata", "mesaj": "%s: %s" % (type(e).__name__, e)})

    onceki = {r["anahtar"]: r for r in o.oku(
        "agent_bulgular?select=anahtar,kontrol,durum,ilk_gorulme,gorulme_sayisi,acilma_sayisi"
        "&lokasyon_id=eq.%s&agent=eq.%s" % (LOKASYON, AGENT))}
    yazilacak = []
    for anahtar, b in bulunan.items():
        r = onceki.get(anahtar)
        if r and r.get("durum") == "acik":
            ilk, gorulme, acilma = r.get("ilk_gorulme"), (r.get("gorulme_sayisi") or 1) + 1, r.get("acilma_sayisi") or 1
        else:
            ilk, gorulme, acilma = an, 1, ((r.get("acilma_sayisi") or 1) + 1) if r else 1
        yazilacak.append(dict(b, lokasyon_id=LOKASYON, agent=AGENT, durum="acik", ilk_gorulme=ilk,
                              son_gorulme=an, gorulme_sayisi=gorulme, acilma_sayisi=acilma, kapanma=None))
    hatalar = []
    if yazilacak:
        kod, m = o.http(o.taban + "agent_bulgular?on_conflict=lokasyon_id,agent,anahtar", "POST", yazilacak,
                        {"Prefer": "resolution=merge-duplicates,return=minimal"})
        if kod not in (200, 201, 204):
            hatalar.append("bulgu: %s %s" % (kod, str(m)[:100]))
    kapanan = [a for a, r in onceki.items()
               if r.get("durum") == "acik" and a not in bulunan and r.get("kontrol") in calisan]
    for a in kapanan:
        kod, m = o.http(o.taban + "agent_bulgular?lokasyon_id=eq.%s&agent=eq.%s&anahtar=eq.%s"
                        % (LOKASYON, AGENT, urllib.parse.quote(a, safe="")), "PATCH",
                        {"durum": "kapandi", "kapanma": an}, {"Prefer": "return=minimal"})
        if kod not in (200, 204):
            hatalar.append("kapanış: %s" % kod)
    ozet = {"toplam": len(sonuclar), "gecti": sum(s["durum"] == "gecti" for s in sonuclar),
            "sorun": sum(s["durum"] == "sorun" for s in sonuclar),
            "atlandi": sum(s["durum"] == "atlandi" for s in sonuclar),
            "hata": sum(s["durum"] == "hata" for s in sonuclar), "acik_bulgu": len(bulunan)}
    kod, m = o.http(o.taban + "agent_turlar?on_conflict=lokasyon_id,agent", "POST",
                    {"lokasyon_id": LOKASYON, "agent": AGENT, "tur_zamani": an,
                     "sure_sn": round(time.monotonic() - bas, 2), "surum": SURUM, "ozet": ozet,
                     "kontroller": sonuclar},
                    {"Prefer": "resolution=merge-duplicates,return=minimal"})
    if kod not in (200, 201, 204):
        hatalar.append("tur: %s %s" % (kod, str(m)[:100]))
    return {"zaman": an, "ozet": ozet, "kontroller": sonuclar, "bulgular": list(bulunan.values()),
            "kapananlar": kapanan, "gonderim": "gönderildi" if not hatalar else "; ".join(hatalar)}
