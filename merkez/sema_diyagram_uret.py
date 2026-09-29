# -*- coding: utf-8 -*-
"""
ŞEMA DİYAGRAMI ÜRETECİ
======================

Supabase'in Schema Visualizer'ı düzeni KAYDETMİYOR: sayfa her açıldığında
otomatik yerleşim baştan çalışıyor ve energy_data'nın ~70 kolonu yüzünden
tablolar alt alta diziliyor. Bu araç, canlı şemadan sabit düzenli, tek
dosyalık bir HTML üretir.

Şema PostgREST'in OpenAPI çıktısından okunur (information_schema REST'e
açık değildir); satır sayıları HEAD + Prefer: count=exact ile alınır.

Çalıştırma:  python merkez/sema_diyagram_uret.py
Çıktı:       merkez/sema_diyagram.html
"""

import html
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BURASI = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(BURASI)
URL = "https://qayjwkqnnjjsnnxovhei.supabase.co"
CIKTI = os.path.join(BURASI, "sema_diyagram.html")
IST = timezone(timedelta(hours=3))

# Tabloların mantıksal grupları ve ne işe yaradıkları. Yeni tablo eklenirse
# buraya yazılmazsa "Diğer" grubunda görünür (kaybolmaz).
GRUPLAR = [
    ("Enerji verisi", "#2a78d6", [
        ("energy_data", "Lokasyonların günlük enerji satırı — tüketim, trafo "
                        "(TRDP), chiller/MCC/kule kırılımı, doğalgaz, su, kojen."),
        ("dis_hava_log", "Dış hava sıcaklığı geçmişi; oto-set kararları ve "
                         "kıyaslamalar bunu kullanır."),
    ]),
    ("Lokasyon yönetimi", "#133273", [
        ("lokasyonlar", "Her lokasyonun kaydı: ping zamanı, sürüm, bakım özeti "
                        "(heartbeat buraya yazar)."),
        ("lokasyon_noktalar", "BACnet nokta adresleri — oto-set komutlarının "
                              "gideceği cihazlar."),
        ("guncellemeler", "Yama dağıtımı: dosya içerikleri JSONB olarak durur, "
                          "lokasyon 2 dakikada bir kontrol eder."),
        ("lisanslar", "Lokasyon lisans kayıtları."),
    ]),
    ("Mekanik Zeka", "#4a3aa7", [
        ("hvac_summary", "Lokasyondaki HVAC analizinin merkeze gönderilen özeti "
                         "(kritik/uyarı/normal sayıları)."),
        ("bakim_kartlari", "Cihaz bazında arıza/bakım işaretleri; kural motoru "
                           "arızalı bileşeni analiz dışı bırakır."),
        ("ai_analizler", "Üretilen analiz/öneri kayıtları."),
    ]),
    ("Oto-set ve komut", "#eb6834", [
        ("komutlar", "Sahaya gönderilen set komutları ve sonuçları "
                     "(gecikmeli geri okuma ile doğrulanır)."),
        ("oto_mod_log", "Oto-set mod geçişlerinin kaydı."),
        ("ayarlar", "Anahtar/değer ayarları — geçiş saatleri, hedef eşikleri."),
    ]),
    ("Bildirim", "#0ca30c", [
        ("bildirimler", "Lokasyondan merkeze düşen uyarı/bildirim kayıtları."),
    ]),
]


def _istek(yol, basliklar=None, yontem="GET"):
    key = json.load(open(os.path.join(KOK, "hvac", "deneme", "supabase_secret.json"),
                         encoding="utf-8"))["service_role_key"]
    h = {"apikey": key, "Authorization": "Bearer " + key}
    h.update(basliklar or {})
    return urllib.request.urlopen(
        urllib.request.Request(URL + yol, headers=h, method=yontem), timeout=60)


def sema_oku():
    with _istek("/rest/v1/", {"Accept": "application/openapi+json"}) as c:
        return json.load(c)["definitions"]


def limitler():
    yol = os.path.join(BURASI, "configs", "izleme_limitleri.json")
    with open(yol, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def kullanim_oku():
    """synapse_kullanim() RPC'si — kurulmamışsa None döner (sayfa yine üretilir)."""
    try:
        with _istek("/rest/v1/rpc/synapse_kullanim",
                    {"Content-Type": "application/json"}, "POST") as c:
            return json.load(c)
    except urllib.error.HTTPError as e:
        if e.code in (404, 400):
            return None
        raise
    except urllib.error.URLError:
        return None


def _boyut(bayt):
    if bayt is None:
        return "—"
    b = float(bayt)
    for birim in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or birim == "TB":
            return ("%.0f %s" if birim in ("B", "KB") else "%.1f %s") % (b, birim)
        b /= 1024


def alarmlar(kullanim, lim):
    """(seviye, baslik, aciklama) listesi. Seviye: kritik | dikkat | iyi."""
    cikti = []
    if not kullanim:
        return cikti
    kota = lim["plan_disk_gb"] * 1024 ** 3
    top = kullanim.get("veritabani_bayt") or 0
    oran = top / kota * 100 if kota else 0
    if oran >= lim["disk_kritik_yuzde"]:
        cikti.append(("kritik", "Disk kotası %.0f%% dolu" % oran,
                      "Kota dolduğunda Supabase istekleri reddeder: lokasyon "
                      "senkronu ve Synapse veri alamaz. Acil temizlik gerekir."))
    elif oran >= lim["disk_dikkat_yuzde"]:
        cikti.append(("dikkat", "Disk kotası %.0f%% dolu" % oran,
                      "Büyüme hızını izleyin; biriken tabloları temizleyin."))

    for t in kullanim.get("tablolar", []):
        mb = (t.get("toplam_bayt") or 0) / 1024 ** 2
        ad = t.get("tablo")
        ek = (" Bu tablo içerik/log biriktirir, eski kayıtlar silinebilir."
              if ad in lim.get("buyume_uyari_tablolari", []) else "")
        if mb >= lim["tablo_kritik_mb"]:
            cikti.append(("kritik", "%s tablosu %s" % (ad, _boyut(t["toplam_bayt"])),
                          "Eşik %d MB." % lim["tablo_kritik_mb"] + ek))
        elif mb >= lim["tablo_dikkat_mb"]:
            cikti.append(("dikkat", "%s tablosu %s" % (ad, _boyut(t["toplam_bayt"])),
                          "Eşik %d MB." % lim["tablo_dikkat_mb"] + ek))
        veri = t.get("veri_bayt") or 0
        indeks = t.get("indeks_bayt") or 0
        if veri > 5 * 1024 ** 2 and indeks > veri * lim["indeks_oran_dikkat"]:
            cikti.append(("dikkat", "%s indeksleri veriden büyük" % ad,
                          "İndeks %s / veri %s — kullanılmayan indeks olabilir."
                          % (_boyut(indeks), _boyut(veri))))

    s = kullanim.get("saglik") or {}
    isabet = s.get("onbellek_isabet_yuzde")
    if isabet is not None and float(isabet) < lim["onbellek_isabet_dikkat"]:
        cikti.append(("dikkat", "Önbellek isabeti %%%.1f" % float(isabet),
                      "Eşik %%%d. Sorgular diskten okuyor, yavaşlama beklenir."
                      % lim["onbellek_isabet_dikkat"]))
    aktif, azami = s.get("aktif_baglanti"), s.get("azami_baglanti")
    if aktif and azami and aktif / azami * 100 >= lim["baglanti_dikkat_yuzde"]:
        cikti.append(("dikkat", "Bağlantı %d/%d" % (aktif, azami),
                      "Bağlantı havuzu doluyor."))
    if s.get("kilitlenme"):
        cikti.append(("dikkat", "%s kilitlenme (deadlock)" % s["kilitlenme"],
                      "Eşzamanlı yazımlar çakışıyor olabilir."))
    if not cikti:
        cikti.append(("iyi", "Tüm eşikler normal",
                      "Disk, tablo boyutları, önbellek ve bağlantılar sınırların altında."))
    return cikti


def izleme_html(kullanim, lim):
    if not kullanim:
        return ("<section class='grup'><h2 style='border-color:#fab219'>"
                "<span class='nokta' style='background:#fab219'></span>"
                "Kullanım ve izleme</h2>"
                "<div class='uyari-kutu'>Bu bölüm için tek seferlik kurulum gerekiyor: "
                "<code>merkez/izleme_kurulum.sql</code> dosyasını Supabase → SQL Editor'de "
                "çalıştırın, sonra üreteci yeniden koşun. Fonksiyon salt okurdur ve "
                "yalnızca service_role'a açılır.</div></section>")

    kota = lim["plan_disk_gb"] * 1024 ** 3
    top = kullanim.get("veritabani_bayt") or 0
    oran = min(100.0, top / kota * 100) if kota else 0
    bar_renk = ("#d03b3b" if oran >= lim["disk_kritik_yuzde"]
                else "#fab219" if oran >= lim["disk_dikkat_yuzde"] else "#0ca30c")

    uyarilar = "".join(
        "<div class='alarm %s'><b>%s</b><span>%s</span></div>"
        % (sev, html.escape(bas), html.escape(ack))
        for sev, bas, ack in alarmlar(kullanim, lim))

    satirlar = []
    for t in kullanim.get("tablolar", []):
        toplam = t.get("toplam_bayt") or 0
        pay = toplam / top * 100 if top else 0
        satirlar.append(
            "<tr><td class='k'>%s</td><td class='t'>%s</td><td class='t'>%s</td>"
            "<td class='t'>%s</td><td class='t'>%s</td>"
            "<td><div class='mini'><i style='width:%.1f%%'></i></div></td></tr>"
            % (html.escape(t.get("tablo", "?")), _boyut(toplam),
               _boyut(t.get("veri_bayt")), _boyut(t.get("indeks_bayt")),
               format(int(t.get("satir_tahmin") or 0), ",d").replace(",", "."),
               pay))

    s = kullanim.get("saglik") or {}
    kutular = [
        ("Veritabanı", _boyut(top), "%d GB kotanın %%%.1f'i" % (lim["plan_disk_gb"], oran)),
        ("Önbellek isabeti", "%%%s" % (s.get("onbellek_isabet_yuzde") or "—"),
         "yüksek olan iyi"),
        ("Aktif bağlantı", "%s / %s" % (s.get("aktif_baglanti", "—"),
                                        s.get("azami_baglanti", "—")), "anlık"),
        ("İşlem", format(int(s.get("islem_commit") or 0), ",d").replace(",", "."),
         "commit · %s rollback" % format(int(s.get("islem_rollback") or 0), ",d").replace(",", ".")),
    ]
    kutu_html = "".join(
        "<div class='kutu'><div class='kb'>%s</div><div class='kd'>%s</div>"
        "<div class='ka'>%s</div></div>" % (b, d, a) for b, d, a in kutular)

    return ("<section class='grup' id='izleme'><h2 style='border-color:#133273'>"
            "<span class='nokta' style='background:#133273'></span>Kullanım ve izleme"
            "<span class='adet'>ölçüm: %s</span></h2>"
            "<div class='kutular'>%s</div>"
            "<div class='bar'><i style='width:%.1f%%;background:%s'></i></div>"
            "%s"
            "<table class='boyut'><thead><tr><th>Tablo</th><th>Toplam</th><th>Veri</th>"
            "<th>İndeks</th><th>Satır</th><th>Pay</th></tr></thead><tbody>%s</tbody></table>"
            "</section>"
            % (html.escape(str(kullanim.get("olculme", ""))[:16].replace("T", " ")),
               kutu_html, oran, bar_renk, uyarilar, "".join(satirlar)))


def satir_sayisi(tablo):
    """PostgREST'in Content-Range başlığından toplam satır sayısı."""
    try:
        with _istek("/rest/v1/%s?select=*&limit=1" % tablo,
                    {"Prefer": "count=exact", "Range": "0-0"}) as c:
            aralik = c.headers.get("Content-Range", "")
        return int(aralik.split("/")[-1]) if "/" in aralik else None
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None


def _kolon_bilgisi(ad, tanim, zorunlu):
    aciklama = (tanim.get("description") or "")
    rozet = ""
    if "<pk/>" in aciklama:
        rozet = "PK"
    elif "<fk" in aciklama:
        rozet = "FK"
    return {
        "ad": ad,
        "tip": tanim.get("format", tanim.get("type", "?")),
        "rozet": rozet,
        "zorunlu": ad in zorunlu,
    }


def html_uret(tablolar, sayilar, izleme=""):
    bilinen = {t for _g, _r, liste in GRUPLAR for t, _a in liste}
    gruplar = [(ad, renk, [(t, a) for t, a in liste if t in tablolar])
               for ad, renk, liste in GRUPLAR]
    kalan = sorted(set(tablolar) - bilinen)
    if kalan:
        gruplar.append(("Diğer", "#46536b", [(t, "") for t in kalan]))

    parcalar = []
    for grup_ad, renk, liste in gruplar:
        if not liste:
            continue
        kartlar = []
        for tablo, aciklama in liste:
            tanim = tablolar[tablo]
            zorunlu = set(tanim.get("required", []))
            kolonlar = [_kolon_bilgisi(k, v, zorunlu)
                        for k, v in tanim.get("properties", {}).items()]
            n = sayilar.get(tablo)
            satirlar = "".join(
                "<tr><td class='k'>%s%s</td><td class='t'>%s</td></tr>" % (
                    html.escape(k["ad"]),
                    (" <span class='rz %s'>%s</span>" % (k["rozet"].lower(), k["rozet"]))
                    if k["rozet"] else "",
                    html.escape(k["tip"]))
                for k in kolonlar)
            kartlar.append(
                "<details class='tablo'%s>"
                "<summary><span class='ad'>%s</span>"
                "<span class='sayi'>%s</span>"
                "<span class='kolon'>%d kolon</span></summary>"
                "%s<table>%s</table></details>" % (
                    " open" if len(kolonlar) <= 14 else "",
                    html.escape(tablo),
                    ("%s satır" % format(n, ",d").replace(",", ".")) if n is not None else "—",
                    len(kolonlar),
                    ("<p class='aciklama'>%s</p>" % html.escape(aciklama)) if aciklama else "",
                    satirlar))
        parcalar.append(
            "<section class='grup'><h2 style='border-color:%s'>"
            "<span class='nokta' style='background:%s'></span>%s"
            "<span class='adet'>%d tablo</span></h2>"
            "<div class='izgara'>%s</div></section>"
            % (renk, renk, html.escape(grup_ad), len(liste), "".join(kartlar)))

    zaman = datetime.now(IST).strftime("%d.%m.%Y %H:%M")
    return """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Synapse Veri Şeması</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--sayfa:#fff;--yuzey:#fff;--yuzey2:#f3f6fb;--murekkep:#0f1f3d;--ikincil:#24324d;
      --soluk:#46536b;--cerceve:rgba(19,50,115,.22);--lacivert:#133273;
      --golge:0 1px 2px rgba(19,50,115,.07),0 10px 24px -12px rgba(19,50,115,.28);}
*{box-sizing:border-box}
body{margin:0;background:var(--sayfa);color:var(--murekkep);
     font:14px/1.5 Inter,system-ui,-apple-system,Segoe UI,sans-serif;
     font-feature-settings:"tnum" 1;-webkit-font-smoothing:antialiased;}
header{padding:28px 32px 18px;border-bottom:1px solid var(--cerceve);}
h1{margin:0;font-size:22px;font-weight:650;letter-spacing:-.02em;}
.ust{font-size:9px;letter-spacing:3.2px;text-transform:uppercase;color:var(--soluk);}
.alt{margin-top:6px;font-size:12px;color:var(--soluk);}
.arac{padding:14px 32px;position:sticky;top:0;background:var(--sayfa);
      border-bottom:1px solid var(--cerceve);z-index:5;}
#ara{width:320px;max-width:100%%;padding:9px 12px;border:1px solid var(--cerceve);
     border-radius:9px;font:inherit;color:var(--murekkep);background:var(--yuzey2);}
#ara:focus{outline:none;border-color:var(--lacivert);box-shadow:0 0 0 3px rgba(19,50,115,.12);}
main{padding:8px 32px 48px;}
.grup{margin-top:26px}
h2{display:flex;align-items:center;gap:9px;font-size:11px;font-weight:700;
   letter-spacing:2.2px;text-transform:uppercase;color:var(--lacivert);
   padding-bottom:8px;border-bottom:2px solid;margin:0 0 14px;}
.nokta{width:8px;height:8px;border-radius:50%%;display:inline-block}
.adet{margin-left:auto;font-weight:500;letter-spacing:0;color:var(--soluk);
      text-transform:none;font-size:11px}
.izgara{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:14px;
        align-items:start;}
.tablo{background:var(--yuzey);border:1px solid var(--cerceve);border-radius:10px;
       box-shadow:var(--golge);overflow:hidden;}
summary{cursor:pointer;padding:12px 14px;display:flex;align-items:baseline;gap:8px;
        list-style:none;}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸";color:var(--soluk);font-size:11px;transition:transform .15s}
details[open] summary::before{transform:rotate(90deg)}
.ad{font-weight:600;font-size:13px}
.sayi{font-size:11px;color:var(--soluk)}
.kolon{margin-left:auto;font-size:10px;color:var(--soluk)}
.aciklama{margin:0;padding:0 14px 10px;font-size:11.5px;color:var(--ikincil);}
table{width:100%%;border-collapse:collapse;font-size:11.5px}
td{padding:5px 14px;border-top:1px solid rgba(19,50,115,.09)}
.k{color:var(--murekkep)}
.t{color:var(--soluk);text-align:right;white-space:nowrap}
.rz{font-size:8.5px;font-weight:700;padding:1px 4px;border-radius:4px;margin-left:5px;
    vertical-align:middle}
.rz.pk{background:rgba(19,50,115,.12);color:var(--lacivert)}
.rz.fk{background:rgba(235,104,52,.14);color:#a8431c}
.kutular{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;
         margin-bottom:12px}
.kutu{background:var(--yuzey);border:1px solid var(--cerceve);border-radius:10px;
      padding:11px 13px;box-shadow:var(--golge)}
.kb{font-size:9px;letter-spacing:1.4px;text-transform:uppercase;color:var(--soluk)}
.kd{font-size:19px;font-weight:650;margin-top:3px}
.ka{font-size:10.5px;color:var(--soluk)}
.bar{height:9px;border-radius:5px;background:var(--yuzey2);overflow:hidden;
     border:1px solid var(--cerceve);margin-bottom:14px}
.bar i{display:block;height:100%%}
.alarm{display:flex;flex-direction:column;gap:2px;padding:10px 13px;border-radius:9px;
       margin-bottom:8px;border:1px solid}
.alarm b{font-size:12.5px}
.alarm span{font-size:11.5px;color:var(--ikincil)}
.alarm.kritik{background:rgba(208,59,59,.07);border-color:rgba(208,59,59,.45)}
.alarm.kritik b{color:#b42525}
.alarm.dikkat{background:rgba(250,178,25,.10);border-color:rgba(250,178,25,.5)}
.alarm.dikkat b{color:#8a5a00}
.alarm.iyi{background:rgba(12,163,12,.07);border-color:rgba(12,163,12,.4)}
.alarm.iyi b{color:#006300}
table.boyut{margin-top:12px;background:var(--yuzey);border:1px solid var(--cerceve);
            border-radius:10px;overflow:hidden;box-shadow:var(--golge)}
table.boyut th{font-size:9px;letter-spacing:1.2px;text-transform:uppercase;
               color:var(--soluk);text-align:right;padding:9px 14px;
               border-bottom:1px solid var(--cerceve)}
table.boyut th:first-child{text-align:left}
.mini{height:6px;border-radius:3px;background:var(--yuzey2);width:110px}
.mini i{display:block;height:100%%;background:#2a78d6;border-radius:3px}
.uyari-kutu{background:rgba(250,178,25,.10);border:1px solid rgba(250,178,25,.5);
            border-radius:10px;padding:12px 14px;font-size:12.5px}
code{background:var(--yuzey2);padding:1px 5px;border-radius:4px;font-size:11.5px}
.gizli{display:none}
footer{padding:0 32px 40px;font-size:11px;color:var(--soluk)}
@media(prefers-color-scheme:dark){body{background:#fff}}
</style></head><body>
<header>
  <div class="ust">Acıbadem Sağlık Grubu — Synapse</div>
  <h1>Veri Şeması</h1>
  <div class="alt">%(zaman)s itibarıyla canlı şemadan üretildi · %(tablo)d tablo ·
     düzen sabittir, sayfayı kapatıp açmak bozmaz</div>
</header>
<div class="arac"><input id="ara" type="search" placeholder="Tablo ya da kolon ara…"></div>
<main>%(izleme)s%(govde)s</main>
<footer>Yeniden üretmek için: <code>python merkez/sema_diyagram_uret.py</code></footer>
<script>
const ara = document.getElementById('ara');
ara.addEventListener('input', () => {
  const s = ara.value.trim().toLocaleLowerCase('tr');
  document.querySelectorAll('.tablo').forEach(t => {
    const bulundu = !s || t.textContent.toLocaleLowerCase('tr').includes(s);
    t.classList.toggle('gizli', !bulundu);
    if (s && bulundu) t.open = true;
  });
  document.querySelectorAll('.grup').forEach(g => {
    const acik = [...g.querySelectorAll('.tablo')].some(t => !t.classList.contains('gizli'));
    g.classList.toggle('gizli', !acik);
  });
});
</script>
</body></html>""" % {"zaman": zaman, "tablo": len(tablolar), "govde": "".join(parcalar),
   "izleme": izleme}


def main():
    tablolar = sema_oku()
    sayilar = {t: satir_sayisi(t) for t in tablolar}
    lim = limitler()
    kullanim = kullanim_oku()
    if kullanim is None:
        print("NOT: synapse_kullanim() yok - once merkez/izleme_kurulum.sql calistirilmali.")
    with open(CIKTI, "w", encoding="utf-8") as f:
        f.write(html_uret(tablolar, sayilar, izleme_html(kullanim, lim)))
    for sev, bas, _a in alarmlar(kullanim, lim):
        print("  [%s] %s" % (sev.upper(), bas))
    print("yazildi: %s (%d tablo)" % (CIKTI, len(tablolar)))
    for t in sorted(tablolar):
        print("  %-22s %6s satir  %3d kolon"
              % (t, sayilar.get(t) if sayilar.get(t) is not None else "?",
                 len(tablolar[t].get("properties", {}))))


if __name__ == "__main__":
    main()
