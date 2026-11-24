# -*- coding: utf-8 -*-
"""Cark ana ekrani (YALNIZ sunum modu) testleri — ag baglantisi YOK.

  * ana_ekran_cark_demo.py saf ureticileri: akis / tazeleme / tiklama
    mekanizmalarinin bekledigi sinif ve oznitelikler, deger yoksa uydurma yok
  * CSS: tek palet blogu, kok kapsami, kaydirma kilidi, reduced-motion
  * JS: tekerlek + surukleme + dokunmatik (pointer events), atalet + yapisma,
    mevcut gizli dugmelere kopru
  * app_merkez.py kaynagi: yeni gorunum yalniz demoda; eski demo bayrakla
  * AppTest: CANLI cizim HEAD'deki app_merkez.py ile AYNI; demo varsayilani
    cark, SYNAPSE_DEMO_ESKI=1 ile eski serit
"""
import ast
import html
import json
import os
import re
import subprocess
import sys
import time

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


import ana_ekran_cark_demo as C

# ── 1) Veri ───────────────────────────────────────────────────────────────
_H = {"maslak": {"isim": "Acıbadem Maslak", "kisa": "MASLAK", "m2": 15000, "renk": "#2a78d6"},
      "kartal": {"isim": "Acıbadem Kartal", "kisa": "KARTAL", "m2": 9000, "renk": "#c98500"},
      "bodrum": {"isim": "Acıbadem Bodrum", "kisa": "BODRUM", "m2": 5000, "renk": "#0ca30c"}}
_CANLI = {"maslak": {"enerji": 3000.0, "sebeke": 2000.0, "kojen": 1000.0, "sogutma": 500.0,
                     "trafo": None, "dogalgaz": None, "su": None, "yas": 3, "t": 1.0}}
_BAG = {"maslak": (True, 1), "kartal": (False, 42), "bodrum": (False, None)}
_UY = {"maslak": [("r", "🔴 MASLAK: 2 ARIZALI <b>x</b>"), ("y", "Agent&#x27;in notu")], "kartal": [], "bodrum": []}
_OTO = {"maslak": {"sonuc": "gecis_yok", "metin": "Geçiş yok", "zaman": "2026-11-17T11:02:00",
                   "chiller_mod": "serin", "diger_mod": "sogutma"}}


def _sorun(o):
    return ("yazma_hatasi", "Son geçişte BACnet yazma hatası") if o.get("x") else (None, None)


V = C.veri_hazirla(_H, ["maslak", "kartal", "bodrum"], _CANLI, _BAG, {"maslak": {"set": 7.5, "dis": 12.0}},
                   _OTO, _sorun, _UY, {"oto_aktif": True})
c("durumlar: on / off / yok", [V["lok"][l]["durum"] for l in V["sira"]] == ["on", "off", "yok"])
c("sayim", V["sayim"] == {"on": 1, "off": 1, "yok": 1}, V["sayim"])
c("tuketim sirasi yalniz canli olcumu olana", V["lok"]["maslak"].get("sira") == 1 and "sira" not in V["lok"]["kartal"])
c("olculmeyen alan None (uydurma yok)", V["lok"]["kartal"]["canli"]["enerji"] is None
  and V["lok"]["maslak"]["canli"]["su"] is None)
c("uyari duz metin (etiket / kacis temiz)",
  [u["m"] for u in V["lok"]["maslak"]["uyari"]] == ["🔴 MASLAK: 2 ARIZALI x", "Agent'in notu"])
c("oto: mod adlari ve saat", V["lok"]["maslak"]["oto"]["chiller"] == "Serin"
  and V["lok"]["maslak"]["oto"]["zaman"] == "11:02" and V["lok"]["kartal"]["oto"] is None)
c("veri JSON'a yazilabilir", json.loads(json.dumps(V, ensure_ascii=False))["lok"]["maslak"]["m2"] == 15000)
c("canli_ozet yalniz olculen alanlar", C.canli_ozet(_CANLI) == {"maslak": {"enerji": 3000.0, "sebeke": 2000.0,
                                                                        "kojen": 1000.0, "sogutma": 500.0}})

# ── 2) HTML ───────────────────────────────────────────────────────────────
_o = C.oge_html("maslak", V["lok"]["maslak"], "maslak acibadem maslak")
c("oge: data-lok + arama metni", 'data-lok="maslak" data-ara="maslak acibadem maslak"' in _o)
c("oge: anlik kW canli-sayi (faz ck-enerji-<lok>, data-deger)",
  'data-ck-lok="maslak" data-ck-alan="enerji" data-deger="3000.000" data-ond="0" data-faz="ck-enerji-maslak">3.000<' in _o)
c("oge: kojen uretim ayri faz", 'data-faz="ck-kojen-maslak"' in _o)
c("oge: uyari rozeti kritik", "ck-rz-uy ck-r" in _o)
c("oge: eski lok-kart / ozet-kart sinifi YOK (eski kopru / arama / siralama dokunmaz)",
  "lok-kart" not in _o and "ozet-kart" not in _o)
_k = C.oge_html("kartal", V["lok"]["kartal"], "kartal")
c("cevrimdisi: '—' akmaz (data-deger yok) ama tazelemeyle canlanabilir",
  'data-ck-alan="enerji" data-ond="0" data-faz="ck-enerji-kartal">—<' in _k and "data-deger" not in _k
  and "çevrimdışı" in _k)
_b = C.oge_html("bodrum", V["lok"]["bodrum"], "bodrum")
c("kurulmadi: sayi yok, 'kurulmadı'", "kurulmadı" in _b and "canli-sayi" not in _b)

_kart = C.ozet_kart_html(0, "Anlık Toplam Tüketim", 1234.5, "kW", "enerji", "enerji", "<i>ik</i>", aktif=True)
c("kalem karti: akan sayi (toplam, faz ck-top-<k>, 15 sn tazelemede _top)",
  'class="canli-sayi" data-ck-lok="_top" data-ck-alan="enerji" data-deger="1234.500" data-ond="0" '
  'data-faz="ck-top-enerji">1.234<' in _kart)
c("kalem karti: tek tik secim (data-kalem); ozet detayina gidis YOK (› oku / href yok, 19.11.2026)",
  'data-kalem="enerji"' in _kart and "ck-kart-ok" not in _kart and "?ozet=" not in _kart
  and "ozet-kart" not in _kart and "ck-aktif" in _kart)
_betik = C.betik({})
c("betik: kalem kartinda cift tik / Shift+Enter ile ozet acilmaz",
  "on('dblclick'" not in _betik and "ozetAc(ev.target" not in _betik and "closest('.ck-kart-ok')" not in _betik)
# Detaydan taşınan bölümler: saha_ozeti (detaydakiyle aynı kurallar)
_SH = C.saha_ozeti(
    {"toplam_ariza": 2, "arizali_cihazlar": [{"ad": "AHU-3"}, "Pompa"], "toplam_bakim": 0,
     "oto": {"sonuc": "gecis_yok", "metin": "Bekliyor", "zaman": "2026-11-19T08:05:00", "chiller_mod": "serin",
             "diger_mod": "sogutma", "setler": {"chiller": 7.5, "GUNDUZ_KOLLEKTOR_SET": 10, "GECE_KOLLEKTOR_SET": 12,
                                                "A_BLOK_FCU_SET": 14, "ZON1_KLIMA_SANTRALI_SET": 10}},
     "oz_test": {"durum": "GECTI", "gecen": 40, "toplam": 40}},
    '{"kritik": [], "uyari": [], "normal": [1, 2, 3]}')
c("saha: ariza listesi ve sayisi", _SH["ariza"] == 2 and _SH["ariza_l"] == ["AHU-3", "Pompa"])
c("saha: hvac kritik/uyari yoksa arizalilar kritik sayilir (detay kurali)",
  _SH["hv_kritik"] == 2 and _SH["hv_uyari"] == 0 and _SH["hv_normal"] == 3)
c("saha: yururlukteki setler", _SH["set"] == {"chiller": "7.5°C", "ch_mod": "Serin", "kol": "10°C / 12°C",
                                              "dig_mod": "Soğutma", "fcu": "14°C", "ahu": "10°C"}, _SH["set"])
c("saha: oto-set iyi + saat, oz test gecti, geri bildirim yok",
  _SH["oto"]["iyi"] and _SH["oto"]["zaman"] == "08:05" and _SH["oz"]["metin"] == "40/40 geçti" and _SH["gb"] is None)
_BOS = C.saha_ozeti(None, None)
c("saha: veri yoksa uydurma yok", _BOS["set"] is None and _BOS["oto"] is None and _BOS["ariza"] == 0)
c("veri_hazirla: saha her lokasyonda", V["lok"]["kartal"]["saha"]["set"] is None)
# 24.11.2026: veri gelmeyen sayaç listeden düşmez — değer None + yaş (turuncu nokta)
import canli_izleme as _CI
from datetime import datetime as _dt, timedelta as _td
_sim = _dt.now()
_cg = C.cihaz_gruplari([
    {"lokasyon_id": "maslak", "cihaz": "TRDP-1", "kw": 100.0, "olcum_zamani": (_sim - _td(seconds=10)).isoformat()},
    {"lokasyon_id": "maslak", "cihaz": "TRDP-2", "kw": 90.0, "olcum_zamani": (_sim - _td(hours=3)).isoformat()},
    {"lokasyon_id": "maslak", "cihaz": "TRDP-3", "kw": 80.0, "olcum_zamani": None}], _CI, 120)
_cc = {x[2]: x for g in _cg.get("maslak", []) for x in g["c"]}
c("olcum: taze sayac degerli, yasi yok (yesil)", _cc.get("TRDP-1", [0, 0])[1] == 100.0 and _cc["TRDP-1"][3] is None, _cc)
c("olcum: eski sayac listede, degersiz, yasiyla (turuncu)",
  "TRDP-2" in _cc and _cc["TRDP-2"][1] is None and 10700 < (_cc["TRDP-2"][3] or 0) < 10900, _cc.get("TRDP-2"))
c("olcum: zamani okunamayan sayac listede, yas -1", "TRDP-3" in _cc and _cc["TRDP-3"][1] is None and _cc["TRDP-3"][3] == -1)
c("olcum: tazelemede eski sayac None (panel turuncu yapar)",
  C.cihaz_degerleri(_cg)["maslak"] == {"TRDP-1": 100.0, "TRDP-2": None, "TRDP-3": None})
c("betik: turuncu nokta ve ipucu", "ck-p-oc-bayat" in _betik and "Veri alınamıyor" in _betik and "function yasYaz(" in _betik)
c("betik: panelde tasinan bolumler ve baslik karti",
  all(x in _betik for x in ("HVAC & Bakım durumu", "Yürürlükteki setler", "Sistem sağlığı", "ck-p-kafa")))
_p = C.ozet_kart_html(3, "Su", None, "m³/h", "su", "su", "")
c("kalem karti degersiz: 'canlı sayaç yok', data-deger yok (uydurma yok)",
  "canlı sayaç yok" in _p and "data-deger" not in _p and "ck-pasif" in _p)
c("7 kalem, kullanici sirasi",
  [k for k, *_ in C.KALEMLER] == ["enerji", "sebeke", "kojen", "dogalgaz_kojen", "dogalgaz_kazan", "sogutma", "su"])
# Çark satırı: TEK değer kutusu (seçili kalem) + Anlık Toplam seçiliyken kojen; CSS diğerlerini gizler
c("oge: her kalem icin ayri gizli kutu + kojen eki",
  _o.count('class="ck-rz ck-deger"') == len(C.KALEMLER) and _o.count("ck-koj-ek") == 1)
_sc0 = C.sahne_css()
c("oge css: kalem kutulari varsayilan gizli (.ck-rz'den guclu secici), yalniz secili gorunur",
  ".ck-sahne .ck-rz.ck-deger, .ck-sahne .ck-rz.ck-koj-ek{ display:none; }" in _sc0
  and '.ck-sahne[data-kalem="su"] .ck-deger[data-kalem="su"]{ display:inline-flex; }' in _sc0
  and '.ck-sahne[data-kalem="enerji"] .ck-rz.ck-koj-ek{ display:inline-flex; }' in _sc0
  and _sc0.index(".ck-rz.ck-deger, ") < _sc0.index('.ck-sahne[data-kalem="enerji"] .ck-deger'))
c("toplamlar: olculmeyen kalem None", C.toplamlar(_CANLI)["su"] is None and C.toplamlar(_CANLI)["enerji"] == 3000.0)
_GS = [{"lokasyon_id": "maslak", "cihaz": "DOGALGAZ-KOJEN", "kw": 260.0},
       {"lokasyon_id": "maslak", "cihaz": "DOGALGAZ-KAZAN", "kw": 210.0},
       {"lokasyon_id": "kartal", "cihaz": "DOGALGAZ-ANA", "kw": 99.0}]
_bir = C.canli_birlestir({"maslak": {"enerji": 1.0}, "kartal": {"enerji": 2.0}}, _GS,
                         lambda rs: {r["lokasyon_id"]: {"dogalgaz": sum(x["kw"] for x in rs if x["lokasyon_id"] == r["lokasyon_id"])} for r in rs})
c("gaz ayrimi: kojen / kazan ayri, ayrilmamis tek sayac bu kalemlere yazilmaz",
  _bir["maslak"]["dogalgaz_kojen"] == 260.0 and _bir["maslak"]["dogalgaz_kazan"] == 210.0
  and "dogalgaz_kojen" not in _bir["kartal"] and "dogalgaz_kazan" not in _bir["kartal"])

_IK = {a: "<i class='%s'></i>" % a for a in ("alarm", "oto", "harita", "ayar", "yonetim", "cikis")}
_s = C.sahne_html(dict(V, genel={"uyari_toplam": 2, "uyari_kritik": 1, "zaman": "17.11.2026 10:00"}),
                  [_kart], _IK, surum="X1")
c("sahne tek satir (markdown bos satirda HTML'i bolmesin)", "\n" not in _s)
_m = re.search(r'data-veri="([^"]*)"', _s)
c("sahne verisi oznitelikte, JSON geri okunur",
  _m and json.loads(html.unescape(_m.group(1)))["lok"]["maslak"]["isim"] == "Acıbadem Maslak")
c("sahne surum damgasi", 'data-surum="X1"' in _s)
c("logo: repodaki GM 'A' isareti + ACIBADEM yazisi", C.GM_A in _s and "<b>ACIBADEM</b>" in _s)
c("alt orta: Sunucu Ayarlari (a.ayar-ac), Sistem, Oturumu Kapat",
  '<a class="ayar-ac ck-dugme"' in _s and 'data-ck-eylem="sistem"' in _s and 'data-ck-eylem="cikis"' in _s
  and _s.index("ck-alt") < _s.index('data-ck-eylem="cikis"'))
c("sag ust: uyarilar (sayac), OTO SET, harita",
  all('data-ck-eylem="%s"' % e in _s for e in ("uyarilar", "kontrol", "harita")) and 'ck-sayac ck-r">2<' in _s)
c("arama kutusu + cark + ray + panel + baglanti svg",
  all(k in _s for k in ('class="ck-ara-kutu"', 'class="ck-cark"', 'class="ck-ray"', 'class="ck-panel"',
                        '<svg class="ck-baglar"')))
c("izleyicide ayarlar dugmesi yok", "ayar-ac" not in C.sahne_html(V, [], _IK, izleyici=True))
_app = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
c("GM_A haritadaki Genel Mudurluk logosuyla ayni yol", "var GM_A = '%s';" % C.GM_A in _app)

# ── 3) CSS ────────────────────────────────────────────────────────────────


def _parcala(secici):
    """Seçici listesini virgülden böler (parantez ve tırnak içindeki virgüller hariç)."""
    parca, derin, tirnak, bas = [], 0, None, 0
    for i, ch in enumerate(secici):
        if tirnak:
            tirnak = None if ch == tirnak else tirnak
        elif ch in "\"'":
            tirnak = ch
        elif ch in "([":
            derin += 1
        elif ch in ")]":
            derin -= 1
        elif ch == "," and derin == 0:
            parca.append(secici[bas:i]); bas = i + 1
    parca.append(secici[bas:])
    return parca


_ek = C.ekran_css()
c("ekran: yer tutucu kalmadi", "§" not in _ek and "PALET" not in _ek and "KONTROL" not in _ek
  and "HARITA" not in _ek and " ANA " not in _ek)
_ic = re.sub(r"/\*.*?\*/", "", _ek[_ek.index(">") + 1:_ek.rindex("<")], flags=re.S)
# En üst seviye kurallar (iç içe yazılan pop-up içerik bloğu tek kural sayılır)
import detay_tema_demo as _T_kur
_seciciler = [k.split("{")[0].strip() for k in _T_kur._ust_kurallar(_ic) if "{" in k]
_kok_ok = lambda s: (s.startswith(("body", ":where(body", ":is(body")) and ":has(.st-key-cark_demo)" in s
                     or s.startswith("html:has(.st-key-cark_demo)"))
c("ekran: her kural cark kabi kokuyle kapsanir (canli portalda hic eslesmez)",
  _seciciler and all(all(_kok_ok(p.strip()) for p in _parcala(s) if p.strip())
                     for s in _seciciler), [s[:90] for s in _seciciler][:3])
c("ekran: detay / ozet / yonetim katmaninda uygulanmaz",
  all(k in C.EKRAN_KOK for k in ("detay_gecis_katmani", "ozet_gecis_katmani", "yonetim_katmani")))
c("ekran: ic ice :has yok", not re.search(r":has\((?:[^()]|\([^()]*\))*:has\(", _ek))
c("ekran: sayfa kaydirmasi kilitli", "height:100dvh" in _ek and "overflow:hidden !important" in _ek)
c("ekran: eski sag ust dugmeler ekran disinda (display:none degil)",
  "div.st-key-cikis_kutusu{ left:-20000px" in _ek and "cikis_kutusu{ display:none" not in _ek)
c("ekran: OTO SET cekmecesi / harita katmani govde sinifiyla acilir",
  "body.ck-kontrol-acik:has(.st-key-cark_demo)" in _ek and "body.ck-harita-acik:has(.st-key-cark_demo)" in _ek)
c("palet: tek blok, olcek degiskeni", _ek.count("--ck-vurgu:") == 1 and "--ck-olcek:1;" in _ek
  and "* var(--ck-olcek)" in _ek)
_sc = C.sahne_css()
c("sahne: renk --c ile (genel !important kuralini yener)",
  ".ck-sahne.ck-sahne, .ck-sahne.ck-sahne :is(" in _sc and "color:var(--c) !important" in _sc)
c("sahne: palet degerleri sahnede tekrar tanimlanmaz", "--ck-vurgu:" not in _sc)
c("sahne: prefers-reduced-motion", "prefers-reduced-motion: reduce" in _sc)
c("sahne: dar ekran duzeni", "@media (max-width:900px)" in _sc)
c("sahne: zoom yok", "zoom" not in _sc + _ek)
c("sahne: cark dokunmatikte sayfayi kaydirmaz", "touch-action:none" in _sc)

# ── 4) JS ─────────────────────────────────────────────────────────────────
_j = C.betik({"alarm": "<span>a</span></x>"})
c("betik: yer tutucu kalmadi", "__SURUM__" not in _j and "__K__" not in _j and "__IKON__" not in _j)
c("betik: simge JSON'u </ kacisli", "<\\/" in _j and "</x>" not in _j)
c("betik: tekerlek (passive:false) + pointer events + capture",
  all(k in _j for k in ("on('wheel'", "{passive: false}", "on('pointerdown'", "on('pointermove'",
                        "on('pointerup'", "on('pointercancel'", "setPointerCapture")))
c("betik: atalet + en yakina yapisma", "v * 0.32" in _j and "git(Math.round(" in _j)
c("betik: requestAnimationFrame + reduced-motion", "requestAnimationFrame" in _j and "prefers-reduced-motion" in _j)
c("betik: mevcut gizli dugmelere kopru",
  all(k in _j for k in ("'.st-key-gizli_detay_' + lok + ' button'", "'.st-key-gizli_ozet_' + k + ' button'",
                        "'.st-key-yonetim_btn button'", "'.st-key-cikis_btn button'")))
c("betik: href yedegi (dugme yoksa)", "'?detay=' + encodeURIComponent(lok)" in _j)
c("betik: eski motorun dinleyicisi susar, zamanlayicilari kapanir",
  "function benim()" in _j and "if (benim()) { fn(ev); }" in _j and "W.clearInterval(eski.aralik)" in _j)
c("betik: ayarlar dugmesini mevcut betige birakir", "if (t.closest('a.ayar-ac')) { return; }" in _j)
c("betik: Esc katmani kapatir", "ev.key === 'Escape'" in _j)
_t = C.tazele_betigi(_CANLI, {"maslak": True, "kartal": False})
c("tazele: data-ck-lok / alan ile yeniler, olmayan '—'",
  "canli-sayi[data-ck-lok]" in _t and "'\\u2014'" in _t and '"kartal": false' in _t)

# ── 4b) Detay temasi ve gecis (detay_tema_demo) ───────────────────────────
import detay_tema_demo as T
_tc = T.tema_css()
c("tema: yer tutucu kalmadi", not re.search(r"§|PALET|SATIR_ICI|IZ_SVG| D | D\)", _tc))
# Canlı İzleme satırları dar sütunda kesilmesin (18.11.2026): sabit 86/60/92 px ızgara esner
c("tema: canli izleme satir izgarasi esnek",
  ".cg-liste:not(.cg-liste-blok){ grid-template-columns:minmax(0, max-content) minmax(14px, 1fr) max-content" in _tc)
# 24.11.2026: tarih parçaları okunur, Excel düğmesi kesilmez, geçiş yalnız transform/opacity
c("tema: tarih kutusu gun/ay/yil parcalari acik renkte",
  '[data-testid="stDateInput"] [role="group"] span{ color:var(--ck-metin) !important;' in _tc)
c("tema: Excel dugmesi kayan kutunun ustunden tasmaz", "top:-4px" not in re.sub(r"/\*.*?\*/", "", _tc, flags=re.S) and "top:0; right:0; width:132px" in _tc)
_gcss = re.sub(r"/\*.*?\*/", "", T.GECIS_CSS, flags=re.S)
c("gecis: blur ve kutu olcusu canlandirilmaz (compositor)",
  "blur(" not in _gcss and not re.search(r"transition:[^;]*\b(left|top|width|height|filter|background)\b", _gcss))
c("gecis: panel olcumu eklemeden once (buyume animasyonu oynar)",
  T.GECIS_JS.index("var hedef = hedefDetay();") < T.GECIS_JS.index("var o = kaplama(isim);"))
_tic = re.sub(r"/\*.*?\*/", "", _tc[_tc.index(">") + 1:_tc.rindex("<")], flags=re.S)
_tic = re.sub(r"@media[^{]*\{", "", _tic)
_tsec = [x.split("{")[0].strip() for x in _tic.split("}") if "{" in x]


def _tkok(x):
    return (":has(.st-key-detay_tema_demo)" in x.split(" ")[0]
            or x.startswith(":where(body:has(.st-key-detay_tema_demo)")
            or x.startswith("html:has(.st-key-detay_tema_demo)"))


_tdis = [x[:90] for x in _tsec if not all(_tkok(q.strip()) for q in _parcala(x) if q.strip())]
c("tema: her kural detay tema kabi kokuyle kapsanir (canli detayda eslesmez)", _tsec and not _tdis, _tdis[:3])
c("tema: ozet / yonetim katmaninda uygulanmaz", "ozet_gecis_katmani" in T.KOK and "yonetim_katmani" in T.KOK)
c("tema: palet ana ekranla AYNI blok", C.PALET_CSS.strip() in _tc)
c("tema: sagda yuksek cam panel + solda bulanik iz",
  "margin:var(--ck-dp-ust, 50px) var(--ck-dp-sag, 1.6vw) var(--ck-dp-alt, 1.4vh) var(--ck-dp-sol, 27vw)" in _tc
  and "data:image/svg+xml," in _tc and "filter:blur(7px)" in _tc and "flex:0 0 auto !important" in _tc)
c("tema: satir ici koyu renkler iki bicimde de eslenir",
  '[style*="color:#46536b"]' in _tc and '[style*="color: rgb(70, 83, 107)"]' in _tc)
c("tema: plotly yazi ve izgara", ".legendtext" in _tc and ".gridlayer, .zerolinelayer" in _tc)
c("tema: ic ice :has yok", not re.search(r":has\((?:[^()]|\([^()]*\))*:has\(", _tc + T.GECIS_CSS))
_gm = T.GECIS_JS
c("gecis: motor ana belgede (script etiketi), surumlu, tek kopya",
  "d.createElement('script')" in T.motor_kur_js() and "E.surum === SURUM" in _gm and "E.mo.disconnect()" in _gm)
c("gecis: tiklamada aninda iskelet panel, hedef = detay paneli olcusu",
  "G.ileri = function" in _gm and "ck-dp-olcu" in _gm and "ck-gp-izgara" in _gm and "ck-gecis-surer" in _gm)
c("gecis: icerik hazir olunca (detay DOM) iskelet soner, en az animasyon suresi beklenir",
  "st-key-detay_geri" in _gm and "'ileri' ? 440" in _gm and "ck-detay-giris" in _gm)
c("gecis: geri - panel cark ekranindaki panelin yerine kuculur, sahne baglaninca netlesir",
  "G.geri = function" in _gm and "hedefAna()" in _gm and "S.el.isConnected" in _gm and "ck-sahne-giris" in _gm)
c("gecis: Geri tiklamasi demo dugmesine yonlenir (yalniz tema varken)",
  "'.st-key-ck_detay_geri button'" in _gm and "ev.stopPropagation()" in _gm and "st-key-detay_tema_demo" in _gm)
c("gecis: rAF durursa zamanlayici yedegi + 15 sn emniyet", "W.setTimeout(c, 50)" in _gm and "15000" in _gm)
c("gecis css: sayfa degisimi opacity ile gizli, zemin koyu, reduced-motion",
  "*:not(:has(.ck-sahne)){\n  opacity:0 !important;" in T.GECIS_CSS and "background-color:#03141a" in T.GECIS_CSS
  and "prefers-reduced-motion: reduce" in T.GECIS_CSS and "ckKaplamaEmniyet .4s ease 16s" in T.GECIS_CSS)
c("gecis css: tam ekran backdrop-filter yok (yavas makinede takilma)", "backdrop-filter:blur" not in T.GECIS_CSS)
c("gecis: betikte </script kacisli", "</script" not in T.betik()[8:-9])
c("cark betigi motoru kurar ve tiklamada baslatir",
  "W.__ckGecis.ileri(" in _j and "'.st-key-ck_detay_' + lok + ' button'" in _j and "ck-gecis-stil" in _j)
c("ana sahnede backdrop-filter yok (yazilimla cizimde pahali)", "backdrop-filter" not in C.sahne_css())
c("gizli sutunlar cizilmez (content-visibility)", "content-visibility:hidden" in C.ekran_css())

# ── 5) app_merkez kaynagi ─────────────────────────────────────────────────
_agac = ast.parse(_app)


def _kosullu_mu(agac, ad, kosul):
    """`ad` adının geçtiği HER yer, testi `kosul` olan bir if'in gövdesinde mi?"""
    disarida = []

    def gez(dugum, icinde):
        if isinstance(dugum, ast.If) and ast.unparse(dugum.test).strip() == kosul:
            for d in dugum.body:
                gez(d, True)
            for d in dugum.orelse:
                gez(d, icinde)
            gez(dugum.test, icinde)
            return
        if isinstance(dugum, ast.Name) and dugum.id == ad and not icinde:
            disarida.append(dugum.lineno)
        for d in ast.iter_child_nodes(dugum):
            gez(d, icinde)
    gez(agac, False)
    return disarida


c("_ckd (cark modulu) yalniz `if _cark_kutu is not None:` govdelerinde kullanilir",
  not _kosullu_mu(_agac, "_ckd", "_cark_kutu is not None"), _kosullu_mu(_agac, "_ckd", "_cark_kutu is not None"))
c("cark kabi _cark_arayuz() ile (canlida da varsayilan, 23.11.2026)",
  '_demo_eski = _demo_modu() and os.environ.get("SYNAPSE_DEMO_ESKI", "").strip() == "1"' in _app
  and '_cark_kutu = st.container(key="cark_demo") if _cark_arayuz() else None' in _app)
c("_cark_arayuz: SYNAPSE_ESKI_ARAYUZ=1 geri donus, sunumda SYNAPSE_DEMO_ESKI=1 eski serit",
  'if os.environ.get("SYNAPSE_ESKI_ARAYUZ", "").strip() == "1":\n        return False\n'
  '    return not (_demo_modu() and os.environ.get("SYNAPSE_DEMO_ESKI", "").strip() == "1")' in _app)
c("eski serit yalniz SYNAPSE_DEMO_ESKI=1 ile",
  '_ust_serit_kutu = st.container(key="ust_serit_demo") if _demo_eski else None' in _app)
c("acik surecte modul SURUM ile yenilenir", 'getattr(_ckd, "SURUM", 0) < %d' % C.SURUM in _app)
c("detay temasi yalniz cark arayuzunde",
  not _kosullu_mu(_agac, "_dtd", "_cark_arayuz()"), _kosullu_mu(_agac, "_dtd", "_cark_arayuz()"))
c("on_click detay dugmeleri yalniz cark dalinda",
  not _kosullu_mu(_agac, "_dtd_c", "_cark_kutu is not None"), _kosullu_mu(_agac, "_dtd_c", "_cark_kutu is not None"))
c("eski siralama betigi cark ekraninda calismaz (demo dalinda kosul)",
  "        if _cark_kutu is None:\n            import canli_izleme as _ci_s\n            _components.html(_ci_s.siralama_betigi(), height=0)" in _app)
c("acik surecte tema modulu SURUM ile yenilenir",
  _app.count('"SURUM", 0) < %d:   # açık süreçte eski modül' % T.SURUM) == 3)   # detay, çark, Sistem
c("tazeleme parcasina eklenen satir kosullu",
  "        if _cark_kutu is not None:   # YALNIZ SUNUM: çark ekranındaki sayılar ve durum\n"
  "            _ck_s = fetch_canli_tum(url, key)\n"
  "            _components.html(_ckd.tazele_betigi(" in _app)

# ── 6) AppTest ────────────────────────────────────────────────────────────
for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ[v] = "http://127.0.0.1:9"
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
try:
    from streamlit.testing.v1 import AppTest
    import giris
    import _sim_sunucu
except Exception as e:
    AppTest = None
    print("ATLANDI AppTest:", e)

if AppTest is not None:
    _PH = giris.parola_hash_uret("yalniz-test")
    os.environ["SYNAPSE_GIRIS_KULLANICI"] = "test"
    os.environ["SYNAPSE_GIRIS_PAROLA_HASH"] = _PH
    _SIM = _sim_sunucu.sunucu_baslat(8099)

    def _calistir(demo, dosya=None, eski=False, durum=None, eski_arayuz=False):
        if demo:
            os.environ["SYNAPSE_DEMO"] = "1"
            os.environ.pop("SYNAPSE_SIM_URL", None)
        else:
            os.environ.pop("SYNAPSE_DEMO", None)
            os.environ["SYNAPSE_SIM_URL"] = _SIM
        if eski:
            os.environ["SYNAPSE_DEMO_ESKI"] = "1"
        else:
            os.environ.pop("SYNAPSE_DEMO_ESKI", None)
        if eski_arayuz:
            os.environ["SYNAPSE_ESKI_ARAYUZ"] = "1"
        else:
            os.environ.pop("SYNAPSE_ESKI_ARAYUZ", None)
        at = AppTest.from_string("import runpy\nrunpy.run_path(%r, run_name='__main__')\n"
                                 % (dosya or os.path.join(BURASI, "app_merkez.py")), default_timeout=240)
        at.session_state["giris_ok"] = True
        at.session_state["giris_jeton"] = giris._jeton_uret(_PH, 3600)
        at.session_state["giris_son_hareket"] = time.time()
        for _k, _v in (durum or {}).items():
            at.session_state[_k] = _v
        at.run()
        return at, "\n".join(m.value for m in at.markdown), [b.key for b in at.button]

    # Genel yazı kuralına eklenen YALNIZ SUNUM hariç tutması (canlıda hiçbir öğeye eşleşmez):
    # HEAD kıyasında metin farkı sayılmaz
    _HARIC = (':not(:where(body:has(.st-key-cark_demo) :is([data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret) > '
              '[data-testid="stColumn"]:is(:nth-child(2), :nth-child(3)), .st-key-ayarlar_panel) *, '
              'body:has(.ck-yonetim-tema) .st-key-yonetim_katmani *))')
    _HARIC_NOT = ("/* Çark arayüzü: koyu pop-up'lar (uyarılar, OTO SET, harita, ayarlar) ve Sistem ekranı da "
                  "kendi renklerini korusun; eski arayüzde (SYNAPSE_ESKI_ARAYUZ=1) bu seçiciler hiçbir şeye eşleşmez; "
                  ":where özgüllüğü değiştirmez */\n")

    def _iz(at):
        _n = lambda s: re.sub(r"\d+(?:[.,]\d+)*", "0", re.sub(
            r"[0-9a-f.]{16,}", "H", re.sub(r"\$\$ID-[0-9a-f]+-", "$$ID-",
                                           s.replace(_HARIC, "").replace(_HARIC_NOT, ""))))
        return ([_n(m.value) for m in at.markdown], [b.key for b in at.button],
                [_n(str(getattr(e, "proto", ""))) for e in at.main if type(e).__name__ != "Markdown"])

    # CANLI (23.11.2026'dan beri): varsayilan cark arayuzu
    _at, _md, _bt = _calistir(False)
    c("[canli] hatasiz cizilir", not _at.exception, [str(e.value)[:200] for e in _at.exception])
    c("[canli] cark sahnesi bir kez", _md.count('<div class="ck-sahne"') == 1)
    c("[canli] on_click detay dugmeleri", sum(1 for b in _bt if b and b.startswith("ck_detay_")) > 0)
    _at.button(key="ck_detay_maslak").click().run()
    _dmd = "\n".join(m.value for m in _at.markdown)
    c("[canli] detay koyu temada, tek sekme, saha bolumleri ana ekranda",
      not _at.exception and "st-key-detay_tema_demo" in _dmd and "YÜRÜRLÜKTEKİ SETLER" not in _dmd
      and "HVAC & BAKIM DURUMU" not in _dmd)
    # ESKI ARAYUZ (geri donus bayragi): bugunku canli ile birebir ayni
    _at, _md, _bt = _calistir(False, eski_arayuz=True)
    c("[canli-eski] hatasiz cizilir", not _at.exception, [str(e.value)[:200] for e in _at.exception])
    _mdc = _md.replace(_HARIC, "")
    c("[canli-eski] cark YOK", "ck-sahne" not in _mdc and "cark_demo" not in _mdc and "--ck-u" not in _mdc)
    c("[canli-eski] eski duzen yerinde", "GLOBAL ÖZET — ANLIK" in _md and "CANLI UYARILAR</div>" in _md
      and 'lok-kart" data-lok=' in _md)
    _head = os.path.join(BURASI, "_kiyas_head_app_merkez_tmp.py")
    _head_detay = os.path.join(BURASI, "_kiyas_head_lokasyon_detay_tmp.py")
    try:
        _kaynak = subprocess.run(["git", "show", "HEAD:merkez/app_merkez.py"], cwd=BURASI,
                                 capture_output=True, check=True).stdout.decode("utf-8")
        # HEAD kopyası detay sayfasını da HEAD'deki pages/lokasyon_detay.py'den çalıştırır
        # (çalışma ağacındaki lokasyon_detay.py'nin canlı çizimi değiştirmediği kanıtlansın)
        _detay_head_kaynak = subprocess.run(["git", "show", "HEAD:merkez/pages/lokasyon_detay.py"], cwd=BURASI,
                                            capture_output=True, check=True).stdout.decode("utf-8")
        with open(_head_detay, "w", encoding="utf-8") as _f:
            _f.write(_detay_head_kaynak)
        _yol_ifade = 'os.path.join(os.path.dirname(__file__), "pages", "lokasyon_detay.py")'
        c("HEAD kopyasi detay yolu degistirilebilir", _yol_ifade in _kaynak)
        _kaynak = _kaynak.replace(_yol_ifade, repr(_head_detay))
        with open(_head, "w", encoding="utf-8") as _f:
            _f.write(_kaynak)
        _at2, _, _ = _calistir(False, _head, eski_arayuz=True)
        _a, _b = _iz(_at), _iz(_at2)
        c("[canli-eski] HEAD'deki (bugunku canli) app_merkez.py ile ayni cizim (markdown, dugmeler, diger ogeler)",
          not _at2.exception and _a == _b,
          [(k, len(x), len(y), next(((i, p[:300], q[:300]) for i, (p, q) in enumerate(zip(x, y)) if p != q), None))
           for k, (x, y) in enumerate(zip(_a, _b)) if x != y])
        # Lokasyon detayi (canli): calisma agaci = HEAD; tema / gecis yok
        _d1, _dm, _db = _calistir(False, durum={"detay_lokasyon": "maslak"}, eski_arayuz=True)
        _d2, _, _ = _calistir(False, _head, durum={"detay_lokasyon": "maslak"}, eski_arayuz=True)
        c("[canli-eski-detay] hatasiz, tema ve demo geri dugmesi YOK",
          not _d1.exception and "detay_tema_demo" not in _dm and "ck_detay_geri" not in _db and "detay_geri" in _db)
        # Excel dosyası 24.11.2026'dan beri tıklanınca üretilir (download_button data=çağrılabilir):
        # dosya alanı (hazır url / ertelenmiş kimlik) dışında düğme aynı olmalı
        _xl = re.compile(r'(?:deferred_file_id|url): "[^"]*"\n')
        _a, _b = ([[_xl.sub("", s) if isinstance(s, str) else s for s in x] for x in _iz(_d)]
                  for _d in (_d1, _d2))
        c("[canli-eski-detay] HEAD'deki app_merkez.py ile ayni cizim",
          not _d2.exception and _a == _b,
          [(k, len(x), len(y), next(((i, p[:300], q[:300]) for i, (p, q) in enumerate(zip(x, y)) if p != q), None))
           for k, (x, y) in enumerate(zip(_a, _b)) if x != y])
    except subprocess.CalledProcessError as e:
        print("ATLANDI HEAD kiyasi:", e)
    finally:
        for _gec in (_head, _head_detay):
            if os.path.exists(_gec):
                os.remove(_gec)

    # DEMO varsayilan: cark
    _at, _md, _bt = _calistir(True)
    c("[demo] hatasiz cizilir", not _at.exception, [str(e.value)[:200] for e in _at.exception])
    c("[demo] cark sahnesi bir kez", _md.count('<div class="ck-sahne"') == 1)
    c("[demo] 7 kalem karti sirayla",
      re.findall(r'<div class="ck-kart[^"]*" data-kalem="([a-z_]+)"', _md)
      == ["enerji", "sebeke", "kojen", "dogalgaz_kojen", "dogalgaz_kazan", "sogutma", "su"])
    import hastaneler as _hst
    c("[demo] her hastane cakta", _md.count('<div class="ck-oge ') == len(_hst.yukle()))
    c("[demo] eski serit cizilmez", 'class="us-serit"' not in _md)
    c("[demo] gizli detay / ozet / yonetim / cikis dugmeleri duruyor",
      sum(1 for b in _bt if b and b.startswith("gizli_detay_")) == len(_hst.yukle())
      and sum(1 for b in _bt if b and b.startswith("gizli_ozet_")) == 5
      and "yonetim_btn" in _bt and "cikis_btn" in _bt)
    c("[demo] OTO SET karti ve harita cekmece icin cizilir", "OTO SET" in _md and "HASTANE ENERJİ AĞI" in _md)

    c("[demo] on_click detay dugmeleri her hastane icin",
      sum(1 for b in _bt if b and b.startswith("ck_detay_")) == len(_hst.yukle()))
    # Tiklama: on_click durumu yazar, TEK yeniden cizimle detay (tema + demo geri dugmesi)
    _at.button(key="ck_detay_maslak").click().run()
    _dmd = "\n".join(m.value for m in _at.markdown)
    _dbt = [b.key for b in _at.button]
    c("[demo] ck_detay tiklamasi detayi acar, koyu tema basilir",
      not _at.exception and _at.session_state["detay_lokasyon"] == "maslak" and "st-key-detay_tema_demo" in _dmd
      and "ck_detay_geri" in _dbt and "detay_geri" in _dbt and '<div class="ck-sahne"' not in _dmd)
    _at.button(key="ck_detay_geri").click().run()
    _gmd = "\n".join(m.value for m in _at.markdown)
    c("[demo] demo geri dugmesi ana ekrana doner",
      not _at.exception and "detay_lokasyon" not in _at.session_state and '<div class="ck-sahne"' in _gmd)

    # DEMO + SYNAPSE_DEMO_ESKI=1: onceki serit gorunumu
    _at, _md, _bt = _calistir(True, eski=True)
    c("[demo-eski] hatasiz cizilir", not _at.exception, [str(e.value)[:200] for e in _at.exception])
    c("[demo-eski] serit var, cark yok", 'class="us-serit"' in _md and '<div class="ck-sahne"' not in _md)
    _at, _md, _bt = _calistir(True, eski=True, durum={"detay_lokasyon": "maslak"})
    c("[demo-eski] detay eski (acik) temada", not _at.exception and "detay_tema_demo" not in _md and "ck_detay_geri" not in _bt)
    os.environ.pop("SYNAPSE_DEMO_ESKI", None)
    os.environ.pop("SYNAPSE_ESKI_ARAYUZ", None)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
