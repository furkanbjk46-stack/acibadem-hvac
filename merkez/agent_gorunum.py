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
    "giris_qr": "Giriş ekranı ve QR", "watchdog": "Watchdog", "bakim_karti": "Bakım kartları",
    "ayarlar": "Ayarlar", "portal_tutarliligi": "Portallar arası tutarlılık", "kapsam": "Kapsam (izlenmeyen sayaç)",
    # Synapse agent'ı (merkez/synapse_agent.py)
    "lokasyon_baglanti": "Lokasyon bağlantısı", "gunluk_esitleme": "Lokasyon eşitlemesi",
    "canli_sayac": "Canlı sayaçlar", "yama_kuyrugu": "Yama kuyruğu", "komutlar": "Saha komutları",
    "surum": "Lokasyon sürümleri", "anahtarsiz_erisim": "Anahtarsız erişim", "synapse_portal": "Synapse portalı",
    "sunucu": "Yerel sunucu", "ayar_degisikligi": "Lokasyon ayar değişiklikleri",
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


# ── Lokasyon × agent matrisi ve lokasyon seçici (yol haritası F2, 12.11.2026) ──────────────────
# Şemadaki her agent kutusu bütün lokasyonların EN KÖTÜ durumunu gösterir; 10 lokasyonda hangisinin
# sorunlu olduğu görünmez. Matris her lokasyonu ayrı satırda, seçici de şemayı tek lokasyona süzer.
# Synapse agent'ının turu lokasyon_id='merkez' ile yazılır; lokasyona özgü bulgularının anahtarı
# "kontrol:<lokasyon>" biçimindedir (synapse_agent.bul) — lokasyon oradan çıkarılır.
MATRIS_AGENTLAR = (("enerji", "Enerji"), ("mekanik_zeka", "Mekanik Zeka"), ("synapse", "Synapse"))
MERKEZ = "merkez"


def _synapse_lokasyonu(bulgu, lokasyonlar):
    ayirt = str((bulgu or {}).get("anahtar") or "").split(":", 1)[-1]
    return ayirt if ayirt in lokasyonlar else None


def matris(turlar, bulgular, raporlar, lokasyonlar, an=None):
    """[{lokasyon_id, ad, hucreler: {agent: {durum, metin}}}] — durum: ok | hata | bekle | yok.

    lokasyonlar: [{"lokasyon_id", "isim"}] (lokasyonlar tablosu; kayıtlı her lokasyon bir satır).
    Hücre: açık iş emri varsa hata, son tur SUSMA_DK'dan eskiyse bekle, tur yoksa yok, yoksa ok.
    """
    an = (an or datetime.now(timezone.utc)).astimezone(IST)
    idler = [l.get("lokasyon_id") for l in lokasyonlar if l.get("lokasyon_id") and l.get("lokasyon_id") != MERKEZ]
    bulgu_id = {b.get("id"): b for b in bulgular}
    acik = [r for r in raporlar if r.get("durum") != "kapandi"]
    syn_tur = next((t for t in turlar if t.get("agent") == "synapse"), None)
    satirlar = []
    for l in lokasyonlar:
        lok = l.get("lokasyon_id")
        if lok not in idler:
            continue
        h = {}
        for agent, _ in MATRIS_AGENTLAR:
            if agent == "synapse":
                tur = syn_tur
                emir = [r for r in acik if r.get("agent") == "synapse"
                        and _synapse_lokasyonu(bulgu_id.get(r.get("bulgu_id")), idler) == lok]
            else:
                tur = next((t for t in turlar if t.get("agent") == agent and t.get("lokasyon_id") == lok), None)
                emir = [r for r in acik if r.get("agent") == agent and r.get("lokasyon_id") == lok]
            dk = _dk(zaman((tur or {}).get("tur_zamani")), an)
            if emir:
                h[agent] = {"durum": "hata", "metin": "%d iş emri" % len(emir)}
            elif tur is None:
                h[agent] = {"durum": "yok", "metin": "tur yok"}
            elif dk is None or dk > SUSMA_DK:
                h[agent] = {"durum": "bekle", "metin": "susuyor · %s" % saat(tur.get("tur_zamani"))}
            else:
                h[agent] = {"durum": "ok", "metin": "tur %s" % saat(tur.get("tur_zamani"), False)}
        satirlar.append({"lokasyon_id": lok, "ad": l.get("isim") or lok, "hucreler": h})
    sira = {"hata": 0, "bekle": 1, "yok": 2, "ok": 3}
    satirlar.sort(key=lambda s: (min(sira[c["durum"]] for c in s["hucreler"].values()), str(s["ad"])))
    return satirlar


def matris_html(satirlar):
    """Matrisin tablosu (değerler kaçırılmış)."""
    renk = {"ok": ("#0ca30c", "#e8f6e8"), "hata": ("#d03b3b", "#fbeaea"), "bekle": ("#b57a00", "#fdf4e1"),
            "yok": ("#8b97ab", "#f3f5f8")}
    ust = "".join("<th style='text-align:left;padding:6px 10px;font-size:11px;color:#46536b;'>%s</th>" % e(a)
                  for _, a in MATRIS_AGENTLAR)
    govde = []
    for s in satirlar:
        hucre = []
        for agent, _ in MATRIS_AGENTLAR:
            c = s["hucreler"][agent]
            yazi, zemin = renk[c["durum"]]
            hucre.append("<td style='padding:5px 10px;'><span style='display:inline-block;padding:2px 9px;"
                         "border-radius:8px;font-size:11.5px;font-weight:650;color:%s;background:%s;'>● %s</span></td>"
                         % (yazi, zemin, e(c["metin"])))
        govde.append("<tr style='border-top:1px solid #edf0f5;'><td style='padding:5px 10px;font-size:12.5px;"
                     "font-weight:650;color:#24324d;'>%s</td>%s</tr>" % (e(s["ad"]), "".join(hucre)))
    return ("<table style='border-collapse:collapse;width:100%%;background:#fff;border-radius:12px;'>"
            "<thead><tr><th style='text-align:left;padding:6px 10px;font-size:11px;color:#46536b;'>Lokasyon</th>"
            "%s</tr></thead><tbody>%s</tbody></table>" % (ust, "".join(govde)))


def canli_uyarilar(raporlar, syn_bulgular, lokasyon_idleri):
    """Açık agent iş emirleri → ana sayfadaki Canlı Uyarılar satırları (yol haritası F1, Synapse içi).

    Dönüş: {lokasyon_id | "merkez": [(önem, metin)]} — önem "r" (kırmızı) | "y" (sarı); metin kaçırılmış.
    Yüksek önemli ve açık iş emri kırmızı; düzeltiliyor / doğrulanıyor ya da orta / düşük önemli sarı.
    Synapse agent'ının iş emri bulgu anahtarındaki lokasyona ("kontrol:<lokasyon>") yazılır;
    lokasyona özgü değilse (sunucu, güvenlik) "merkez" altında toplanır.
    """
    bulgu_id = {b.get("id"): b for b in syn_bulgular}
    cikti = {}
    sira = sorted((r for r in raporlar if r.get("durum") != "kapandi"),
                  key=lambda r: (0 if (r.get("onem") == "yuksek" and r.get("durum") == "acik") else 1,
                                 ONEM_SIRA.get(r.get("onem"), 1), str(r.get("olusturma") or "")))
    for r in sira:
        if r.get("agent") == "synapse":
            lok = _synapse_lokasyonu(bulgu_id.get(r.get("bulgu_id")), lokasyon_idleri) or MERKEZ
        else:
            lok = r.get("lokasyon_id") or MERKEZ
        kirmizi = r.get("onem") == "yuksek" and r.get("durum") == "acik"
        ek = "" if r.get("durum") == "acik" else " · %s" % DURUM_METIN.get(r.get("durum"), r.get("durum")).lower()
        cikti.setdefault(lok, []).append(
            ("r" if kirmizi else "y", "🤖 %s <span style='opacity:.7'>(%s%s)</span>" % (
                e(r.get("baslik")), e(r.get("rapor_no")), e(ek))))
    return cikti


KAYNAK_AD = {"sync": "Arka plan (cloud_sync)", "enerji": "Enerji portalı", "mz": "Mekanik Zeka"}
SEVIYE_AD = {"WARNING": "Uyarı", "ERROR": "Hata", "CRITICAL": "Kritik"}


def hata_ozeti(satirlar):
    """lokasyon_hatalari satırları (son 30 gün) → şablon başına tek satır, en yeni üstte.

    [{seviye, kaynak, mesaj, adet, gun, ilk, son, ornek}] — Synapse'te tablo olarak gösterilir (N5).
    """
    grup = {}
    for r in satirlar:
        g = grup.setdefault(r.get("anahtar"), {"seviye": SEVIYE_AD.get(r.get("seviye"), r.get("seviye")),
                                              "kaynak": KAYNAK_AD.get(r.get("kaynak"), r.get("kaynak")),
                                              "mesaj": r.get("sablon"), "adet": 0, "gunler": set(),
                                              "ilk": r.get("ilk"), "son": r.get("son"), "ornek": r.get("ornek")})
        g["adet"] += int(r.get("adet") or 0)
        g["gunler"].add(str(r.get("gun")))
        if str(r.get("ilk") or "") < str(g["ilk"] or "~"):
            g["ilk"] = r.get("ilk")
        if str(r.get("son") or "") >= str(g["son"] or ""):
            g["son"], g["ornek"] = r.get("son"), r.get("ornek")
    cikti = [dict(g, gun=len(g.pop("gunler")), ilk=saat(g["ilk"]), son_ham=str(g["son"]), son=saat(g["son"]))
             for g in grup.values()]
    cikti.sort(key=lambda x: x.pop("son_ham"), reverse=True)
    return cikti


def suz(turlar, bulgular, raporlar, lokasyon_id, lokasyonlar=()):
    """Şemayı tek lokasyona süzer. Üst agent ve Synapse turu kalır; Synapse bulgu / iş emirlerinden
    yalnız bu lokasyonunkiler ile lokasyona özgü olmayanlar (sunucu, güvenlik) kalır."""
    if not lokasyon_id:
        return turlar, bulgular, raporlar
    idler = [l.get("lokasyon_id") if isinstance(l, dict) else l for l in lokasyonlar]
    bulgu_id = {b.get("id"): b for b in bulgular}

    def tut_b(b):
        if b.get("agent") == "synapse":
            return _synapse_lokasyonu(b, idler) in (None, lokasyon_id)
        return b.get("lokasyon_id") == lokasyon_id

    def tut_r(r):
        if r.get("agent") == "synapse":
            b = bulgu_id.get(r.get("bulgu_id"))
            return b is None or _synapse_lokasyonu(b, idler) in (None, lokasyon_id)
        return r.get("lokasyon_id") == lokasyon_id

    return ([t for t in turlar if t.get("lokasyon_id") in (lokasyon_id, MERKEZ) or t.get("agent") in ("ust", "synapse")],
            [b for b in bulgular if tut_b(b)], [r for r in raporlar if tut_r(r)])


def sayfa(sablon_html, veri):
    """Tasarım sayfasına canlı veriyi enjekte eder (açık tema)."""
    js = json.dumps(veri, ensure_ascii=False).replace("</", "<\\/")
    return (sablon_html.replace('<html lang="tr">', '<html lang="tr" data-tema="acik">', 1)
            .replace("<script>", "<script>window.SYNAPSE_CANLI = %s;</script>\n<script>" % js, 1))
