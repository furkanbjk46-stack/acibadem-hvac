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


def html_uret(tablolar, sayilar):
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
<main>%(govde)s</main>
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
</body></html>""" % {"zaman": zaman, "tablo": len(tablolar), "govde": "".join(parcalar)}


def main():
    tablolar = sema_oku()
    sayilar = {t: satir_sayisi(t) for t in tablolar}
    with open(CIKTI, "w", encoding="utf-8") as f:
        f.write(html_uret(tablolar, sayilar))
    print("yazildi: %s (%d tablo)" % (CIKTI, len(tablolar)))
    for t in sorted(tablolar):
        print("  %-22s %6s satir  %3d kolon"
              % (t, sayilar.get(t) if sayilar.get(t) is not None else "?",
                 len(tablolar[t].get("properties", {}))))


if __name__ == "__main__":
    main()
