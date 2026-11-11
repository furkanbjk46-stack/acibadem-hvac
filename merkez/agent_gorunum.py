# -*- coding: utf-8 -*-
"""
AGENT KATMANLARI — CANLI GÖRÜNÜM (hesap kısmı)
=============================================

Synapse > Yönetim > Agent katmanları sekmesi, tasarım sayfasını
(sunum/agent_katmanlari.html) CANLI modda gösterir. Bu modül veritabanındaki
agent_turlar / agent_bulgular / agent_raporlar satırlarından sayfanın
beklediği tek JSON'u üretir (window.SYNAPSE_CANLI).

Streamlit içermez; pages/yonetim.py çağırır, test_agent_gorunum.py dener.
Sayfa bu metinleri HTML olarak basar: DB'den gelen HER metin burada kaçırılır.
"""
import html
import json
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=3))
SUSMA_DK = 45
UST_BAYAT_DK = 10
ONEM_SIRA = {"yuksek": 0, "orta": 1, "dusuk": 2}
DURUM_METIN = {"acik": "Açık", "duzeltiliyor": "Düzeltiliyor", "dogrulaniyor": "Doğrulanıyor",
               "kapandi": "Kapandı"}
KONTROL_AD = {
    "gunluk_dongu": "Günlük döngü", "sayac_erisimi": "Sayaç erişimi", "donmus_veri": "Donmuş veri",
    "veri_kalitesi": "Veri kalitesi", "diyagram_toplami": "Enerji diyagramı",
    "yerel_bulut": "Yerel ↔ bulut", "hava_durumu": "Hava durumu", "portal_sagligi": "Portal sağlığı",
    # Mekanik Zeka agent'ı (hvac/deneme/mekanik_zeka_agent.py)
    "portal_api": "API uçları (8005)", "otomatik_analiz": "Otomatik analiz", "dis_hava": "Dış hava kaynağı",
    "ahu_veri": "AHU verisi", "sensor_mantigi": "Sensör arızası mantığı", "donmus_ahu": "Donmuş AHU okuması",
    "talep_uretim": "Talep / üretim grafiği", "oz_test": "Öz test", "oto_set": "Oto-set geçişi",
    "internet": "İnternet erişimi",
}
DUGUM = {"enerji": "e", "mekanik_zeka": "m", "synapse": "s"}


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


def zaman(m):
    if not m:
        return None
    try:
        z = datetime.fromisoformat(str(m).replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    return (z if z.tzinfo else z.replace(tzinfo=timezone.utc)).astimezone(IST)


def saat(m, gun=True):
    z = zaman(m)
    if not z:
        return "—"
    return z.strftime("%d.%m %H:%M") if gun else z.strftime("%H:%M")


def _dk(z, an):
    return (an - z).total_seconds() / 60 if z else None


def rapor_karti(r):
    """agent_raporlar satırı → sayfanın rapor kartı (değerler kaçırılmış)."""
    ic = r.get("icerik") or {}
    alanlar = []

    def ekle(ad, deger, kod=False):
        if deger not in (None, "", []):
            alanlar.append([ad, ("<code>%s</code>" % e(deger)) if kod else e(deger)])

    ekle("Agent", ic.get("agent_ad"))
    ekle("Lokasyon", ic.get("lokasyon") or r.get("lokasyon_id"))
    ekle("Sekme", ic.get("bolum"))
    ekle("Kontrol", ic.get("kontrol") and KONTROL_AD.get(ic.get("kontrol"), ic.get("kontrol")))
    ekle("Beklenen", ic.get("beklenen"))
    ekle("Bulunan", ic.get("bulunan"))
    ekle("Agent'ın denediği", ic.get("denenen") if ic.get("denenen") not in ("—",) else None)
    ekle("Tekrar üretme", ic.get("tekrar_adimi"))
    ekle("Olası yer", ic.get("olasi_yer"))
    if ic.get("gorulme_sayisi"):
        ekle("Görülme", "%s kez · ilk %s · son %s" % (ic.get("gorulme_sayisi"), saat(ic.get("ilk_gorulme")),
                                                      saat(ic.get("son_gorulme"))))
    if ic.get("tekrarlayan"):
        ekle("Tekrarlayan", "%s. kez açıldı → kod incelemesi önerilir" % ic.get("acilma"))
    if ic.get("deneme"):
        ekle("Tutmayan düzeltme", "%s" % ic.get("deneme"))
    if ic.get("testler"):
        ekle("Yama öncesi testler", ic.get("testler"))
    if r.get("durum") == "dogrulaniyor" and ic.get("dogrulama_sinir"):
        ekle("Doğrulama", "agent aynı kontrolü tekrar çalıştırıyor · sorun görülmezse kapanır · "
                          "en geç %s" % saat(ic.get("dogrulama_sinir")))
    if r.get("cozum"):
        ekle("Sonuç", r.get("cozum"))
    gecmis = r.get("olaylar") or []
    if gecmis:
        alanlar.append(["Geçmiş", "<br>".join("%s · %s" % (e(saat(o.get("zaman"))), e(o.get("metin")))
                                              for o in gecmis[-6:])])
    return {"id": r.get("id"), "no": e(r.get("rapor_no")), "onem": r.get("onem") if r.get("onem") in ONEM_SIRA
            else "orta", "durum": r.get("durum"), "durum_metin": DURUM_METIN.get(r.get("durum"), e(r.get("durum"))),
            "baslik": e(r.get("baslik")), "tur": r.get("tur"), "alanlar": alanlar}


def gorunum(turlar, bulgular, raporlar, an=None, ust_durum=None):
    """Sayfa JSON'u.

    turlar   : agent_turlar (hepsi)
    bulgular : agent_bulgular (açık olanlar)
    raporlar : agent_raporlar (açıklar + son kapananlar)
    ust_durum: ust_agent.arka_plan_durumu() (aynı süreçteyse) — yoksa tur satırından okunur
    """
    an = (an or datetime.now(timezone.utc)).astimezone(IST)
    acik_rapor = [r for r in raporlar if r.get("durum") != "kapandi"]
    kapali = [r for r in raporlar if r.get("durum") == "kapandi"]

    # ── Portal agent'ları ──
    agentlar = {}
    for ad, dugum in DUGUM.items():
        t = [x for x in turlar if x.get("agent") == ad]
        b = [x for x in bulgular if x.get("agent") == ad and x.get("durum") == "acik"]
        if not t:
            agentlar[dugum] = {"durum": None, "rozet": "● henüz çalışmıyor" if ad != "enerji"
                               else "● henüz tur kaydı yok", "renk": "var(--soluk)"}
            continue
        susan = [x["lokasyon_id"] for x in t if (_dk(zaman(x.get("tur_zamani")), an) or 1e9) > SUSMA_DK]
        son = max(t, key=lambda x: str(x.get("tur_zamani")))
        # Kutu İŞ EMİRLERİNE göre renklenir (11.11.2026): açık bulgu olup iş emri olmayanlar
        # ya "bilgi"dir ya da iş emri elle kapatılmış (bilinen) sorundur — kırmızı yakmaz.
        is_emri = [r for r in acik_rapor if r.get("agent") == ad]
        bilgi = sum(1 for x in b if x.get("onem") == "bilgi")
        bilinen = len(b) - bilgi - len({r.get("bulgu_id") for r in is_emri if r.get("bulgu_id") is not None}
                                        & {x.get("id") for x in b})
        ek = (" · %d bilinen" % bilinen if bilinen > 0 else "") + (" · %d bilgi" % bilgi if bilgi else "")
        tur_saat = saat(son.get("tur_zamani"), False)
        if susan:
            agentlar[dugum] = {"durum": "bekle", "rozet": "● susuyor: " + ", ".join(susan), "renk": "var(--sari)"}
        elif is_emri:
            agentlar[dugum] = {"durum": "hata", "rozet": "● %d açık iş emri · tur %s" % (len(is_emri), tur_saat),
                               "renk": "var(--kirmizi)"}
        else:
            agentlar[dugum] = {"durum": "ok", "rozet": "● kontrol ediyor · tur %s%s" % (tur_saat, ek),
                               "renk": "var(--yesil)"}

    # ── Üst agent ──
    ust_tur = next((x for x in turlar if x.get("agent") == "ust"), None)
    ust_z = zaman(ust_tur.get("tur_zamani")) if ust_tur else None
    ust_dk = _dk(ust_z, an)
    calisiyor = ust_dk is not None and ust_dk <= UST_BAYAT_DK
    ust = {"durum": "ok" if calisiyor else ("bekle" if ust_z else "hata"),
           "rozet": ("● çalışıyor · %s" % saat(ust_tur.get("tur_zamani"), False)) if calisiyor else
                    ("● %d dk'dır tur atmadı" % ust_dk if ust_z else "● henüz çalışmadı"),
           "cip": calisiyor}
    if ust_durum and ust_durum.get("hata"):
        ust["rozet"] += " · son hata: " + e(ust_durum["hata"])[:80]

    # ── Düzelten / test / kayıt ──
    duz = sum(1 for r in acik_rapor if r.get("durum") == "duzeltiliyor")
    dog_r = [r for r in acik_rapor if r.get("durum") == "dogrulaniyor"]
    dog = len(dog_r)
    sinirlar = sorted(str((r.get("icerik") or {}).get("dogrulama_sinir") or "") for r in dog_r)
    sinirlar = [x for x in sinirlar if x]

    # ── Şu an ──
    olaylar = []
    for r in raporlar:
        for o in r.get("olaylar") or []:
            olaylar.append((str(o.get("zaman")), r.get("rapor_no"), o.get("metin")))
    olaylar.sort(reverse=True)
    if acik_rapor:
        en = sorted(acik_rapor, key=lambda r: (ONEM_SIRA.get(r.get("onem"), 1), str(r.get("olusturma"))))[0]
        baslik = "%d açık iş emri" % len(acik_rapor)
        metin = "En önemlisi: %s. Raporu inceleyip düzeltmeye başlayabilirsin; yamadan sonra agent aynı " \
                "kontrolü tekrar çalıştırır ve geçerse rapor kendiliğinden kapanır." % e(en.get("baslik") or "")
    elif any(a["durum"] for a in agentlar.values()):
        baslik, metin = "Her şey yolunda", "Agent'lar kendi bölgelerini kontrol ediyor; açık iş emri yok."
    else:
        baslik, metin = ("Agent'lar henüz çalışmıyor",
                         "Enerji Portal Agent'ı lokasyona yama ile gidince turları burada görünür.")
    anlik = None
    if acik_rapor:
        anlik = rapor_karti(sorted(acik_rapor, key=lambda r: str(r.get("guncelleme") or r.get("olusturma")),
                                   reverse=True)[0])
    elif kapali:
        anlik = rapor_karti(sorted(kapali, key=lambda r: str(r.get("kapanma") or ""), reverse=True)[0])

    # ── Agent kontrolleri: şema düğümüne göre, her lokasyonun son turundaki durum (en kötüsü) ──
    kontroller = {d: {} for d in DUGUM.values()}
    sira = {"sorun": 0, "hata": 1, "atlandi": 2, "gecti": 3}
    for t in turlar:
        dugum = DUGUM.get(t.get("agent"))
        if dugum is None:
            continue
        for k in t.get("kontroller") or []:
            onceki = kontroller[dugum].get(k.get("kod"))
            if onceki is None or sira.get(k.get("durum"), 9) < sira.get(onceki["durum"], 9):
                kontroller[dugum][k.get("kod")] = {"durum": k.get("durum"), "mesaj": e(k.get("mesaj")),
                                                   "ad": e(KONTROL_AD.get(k.get("kod"), k.get("ad") or k.get("kod"))),
                                                   "lokasyon": e(t.get("lokasyon_id")),
                                                   "zaman": saat(t.get("tur_zamani"), False)}

    kartlar = sorted(acik_rapor, key=lambda r: (ONEM_SIRA.get(r.get("onem"), 1), str(r.get("olusturma"))))
    kartlar += sorted(kapali, key=lambda r: str(r.get("kapanma") or ""), reverse=True)[:10]
    return {
        "zaman": an.strftime("%d.%m.%Y %H:%M"),
        "agentlar": agentlar, "ust": ust,
        "duz": "%d düzeltiliyor" % duz if duz else "", "test": ("%d doğrulanıyor" % dog + (" · en geç %s" % saat(sinirlar[-1]) if sinirlar else "")) if dog else "",
        "kayit": len(raporlar),
        "su_an": {"baslik": e(baslik), "metin": metin,          # metin içindeki başlık zaten kaçırıldı
                  "gecmis": [{"no": e(n), "zaman": e(saat(z)), "metin": e(m)} for z, n, m in olaylar[:8]]},
        "anlik": anlik, "kontroller": kontroller,
        "raporlar": [rapor_karti(r) for r in kartlar],
        "acik_sayisi": len(acik_rapor),
    }


def sayfa(sablon_html, veri):
    """Tasarım sayfasına canlı veriyi enjekte eder (açık tema)."""
    js = json.dumps(veri, ensure_ascii=False).replace("</", "<\\/")
    return (sablon_html.replace('<html lang="tr">', '<html lang="tr" data-tema="acik">', 1)
            .replace("<script>", "<script>window.SYNAPSE_CANLI = %s;</script>\n<script>" % js, 1))
