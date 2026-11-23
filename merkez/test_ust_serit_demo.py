# -*- coding: utf-8 -*-
"""Ust serit (YALNIZ sunum modu) testleri — ag baglantisi YOK.

  * ust_serit_demo.py'nin saf HTML ureticileri: tiklama/akis/tazeleme
    mekanizmalarinin bekledigi sinif ve oznitelikler yerinde mi
  * app_merkez.py kaynagi: yeni gorunum yalnizca _demo_modu() arkasinda mi
  * AppTest: demo ve canli mod hatasiz ciziliyor mu; canli modda serit YOK,
    eski Global Ozet / Canli Uyarilar yerinde; demoda serit VAR, eski yerler bos
    (veri yerel simulasyon sunucusundan gelir)
"""
import ast
import os
import re
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


import ust_serit_demo as U

# ── 1) Ozet karti ─────────────────────────────────────────────────────────
_k = U.ozet_kart_html(0, "Toplam Enerji", 1234.5, "3 lokasyon canlı", "kW", "enerji",
                      ' data-onceki="1.000" data-t="1.000" data-sure="15.0"', "1.235",
                      "<i>ik</i>", "<b>n</b>", "#f59e0b")
c("kart a.ozet-kart + data-ozet + href yedegi",
  '<a class="ozet-kart us-kart us-canli" data-ozet="enerji" href="?ozet=enerji"' in _k, _k[:120])
c("sayi canli-sayi, data-faz ozet-*, data-deger .2f, data-ond 0",
  'class="canli-sayi" data-deger="1234.50" data-ond="0" data-faz="ozet-enerji"' in _k)
c("gecis oznitelikleri tasinir", 'data-sure="15.0"' in _k)
c("kart rengi --k ile", "--k:#f59e0b" in _k)
c("iz alani var (canli)", 'class="us-iz"' in _k)
c("ilk yazi kw_metin degeri", ">1.235</span>" in _k)

_p = U.ozet_kart_html(3, "Su", None, "", "m³/h", "su", "", "—", "<i></i>", "<b></b>", "#0ea5e9")
c("degersiz kalem: canli sayac yok", "canlı sayaç yok" in _p)
c("degersiz kalem: pasif sinif, canli-sayi YOK (deger uydurulmaz)",
  "us-pasif" in _p and "canli-sayi" not in _p and "us-iz" not in _p)
c("degersiz kalem de tiklanir", 'data-ozet="su" href="?ozet=su"' in _p)
c("etiket kacislanir", "&lt;" in U.ozet_kart_html(0, "<x>", None, "", "", "su", "", "", "", "", None))

# ── 2) Uyari karti ────────────────────────────────────────────────────────
_l = [("maslak", [("y", "Maslak: set yüksek"), ("r", "Maslak: ARIZA <b>")]),
      ("kartal", [("r", "Kartal: Agent&#x27;in <i>notu</i> &lt;x&gt;")]),
      ("altunizade", [("y", "Altunizade: bakım")])]
_o = U.uyari_ozeti(_l)
c("uyari ozeti sayilar", (_o["toplam"], _o["lokasyon"], _o["kritik"]) == (4, 3, 2), _o)
c("ozet satiri ilk yerin KRITIK mesaji", _o["son"] == "Maslak: ARIZA <b>", _o["son"])
_u = U.uyari_kart_html(5, _l, "<div>LISTE</div>", "", "")
c("kritik uyari: kirmizi + nabiz", "--k:#d03b3b" in _u and "us-kritik" in _u)
c("liste acilir pencerede AYNI html", '<div class="us-acilir"><div>LISTE</div></div>' in _u)
c("ozet satirinda html etiketi calismaz", "ARIZA <b>" not in _u)
_o2 = U.uyari_ozeti(_l[1:])
c("kacisli mesaj duz metne cevrilir (cift kacis yok)",
  _o2["son_metin"] == "Kartal: Agent'in notu <x>", _o2["son_metin"])
_u2 = U.uyari_kart_html(5, _l[1:], "", "", "")
c("karta yazilirken yeniden kacislanir", "Agent&#x27;in notu &lt;x&gt;" in _u2 and "&amp;#x27;" not in _u2)
_y = U.uyari_kart_html(5, [("a", [("y", "x")])], "", "", "")
c("yalniz sari uyari: amber, nabiz yok", "--k:#c98500" in _y and "us-kritik" not in _y)
_n = U.uyari_kart_html(5, [], "", "", "")
c("uyari yok: yesil + 'Uyarı yok'", "--k:#0ca30c" in _n and "Uyarı yok" in _n and "us-liste" not in _n)
c("uyari karti ozet-kart DEGIL (detay sayfasi yok)", "ozet-kart" not in _u + _n)

# ── 3) Serit, CSS, betik ──────────────────────────────────────────────────
_css = U.serit_css()
c("6 sutun genis ekran", "repeat(6, minmax(0, 1fr))" in _css)
c("tablette 3 sutun", re.search(r"max-width:1180px\)\{ \.us-serit\{ grid-template-columns:repeat\(3", _css))
c("dar ekranda 2 sutun", "repeat(2, minmax(0, 1fr))" in _css)
c("prefers-reduced-motion", "prefers-reduced-motion: reduce" in _css)
_b = U.serit_betigi()
c("betik gizli ozet dugmesine yonlendirir",
  "'.st-key-gizli_ozet_' + a.getAttribute('data-ozet') + ' button'" in _b)
c("betik tiklamayi belgeye yakalama evresinde baglar (yenilenen kartlarda da calisir)",
  "d.addEventListener('click', W.__synUstDisFn, true)" in _b)
c("betik eski dinleyiciyi kaldirip yeniden kurar (ikinci kez islemez)",
  "d.removeEventListener('click', W.__synUstDisFn, true)" in _b)
c("olay karta inmeden durdurulur (sol kopru ikinci kez tetiklemez)", "ev.stopPropagation()" in _b)
c("uyari karti listesi acik/kapali yazisi", "Listeyi kapat" in _u)
c("betik reduced-motion'a bakar", "prefers-reduced-motion" in _b)
c("betik gozcuyu yeniden kurarken eskisini kapatir", "__synUstGozcu.disconnect()" in _b)

# ── 3b) Tek ekran (kaydirmasiz) duzen CSS'i ───────────────────────────────
_ek = U.ekran_css()
c("tek ekran: yer tutucu kalmadi", "§" not in _ek and "ANA" not in _ek)
c("tek ekran: yalniz genis ve yeterince yuksek ekranda",
  "@media (min-width:1181px) and (min-height:560px){" in _ek)
_ic = re.sub(r"/\*.*?\*/", "", _ek[_ek.index("{") + 1:_ek.rindex("}")], flags=re.S)
_ic = re.sub(r"@media[^{]*\{", "", _ic)
_secici_satirlari = [p.split("{")[0].strip() for p in _ic.split("}") if "{" in p]
c("tek ekran: her kural ana ekran + demo kokuyle kapsanir",
  _secici_satirlari and all(all(p.strip().startswith(U._EKRAN_KOK)
                                for p in re.split(r",(?![^()]*\))", s) if p.strip())
                            for s in _secici_satirlari),
  [s[:80] for s in _secici_satirlari if not s.startswith(U._EKRAN_KOK)][:3])
c("tek ekran: kok seritli sayfa; detay/ozet/yonetim katmaninda uygulanmaz",
  "body:has(.st-key-ust_serit_demo)" in U._EKRAN_KOK
  and all(k in U._EKRAN_KOK for k in ("detay_gecis_katmani", "ozet_gecis_katmani", "yonetim_katmani")))
c("tek ekran: ic ice :has yok (tarayici kurali tumden yok sayar)",
  not re.search(r":has\((?:[^()]|\([^()]*\))*:has\(", _ek))
c("tek ekran: ana kap gorunur yukseklige kilitli", "height:100dvh" in _ek and "height:100vh" in _ek)
c("tek ekran: olcek vh/vw'ye bagli clamp", "--se-u:calc(clamp(5.5px, min(.85vh, .48vw), 10px)" in _ek
  and "--se-sayi:calc(clamp(19px, min(2.7vh, 1.5vw), 30px)" in _ek
  and "var(--se-sayi)" in _ek and "var(--se-kart-h)" in _ek)
c("tek ekran: liste, harita ve sag sutun kalan yuksekligi alir / icinde kayar",
  ".lok-scroll{ position:absolute !important; inset:0" in _ek
  and 'iframe[src^="data:"]{ display:block; height:100% !important; }' in _ek
  and "overflow-y:auto !important" in _ek)
c("tek ekran: kisa ekranda iz gizlenir, sayi her zaman kalir",
  "@media (max-height:820px)" in _ek and ".us-iz{ display:none; }" in _ek
  and "us-sayi{ font-size:var(--se-sayi)" in _ek and not re.search(r"\.us-(sayi|etiket|birim)[^{]*\{[^}]*display:none", _ek))
c("tek ekran: arama suzmesinin display kurali ezilmez (lokasyon kartina display verilmez)",
  not re.search(r"lok-kart[^{,]*\{[^}]*display:", _ek))
c("tek ekran: tek kok olcek degiskeni, boyutlar ondan turer",
  "--se-olcek:1;" in _ek and "* var(--se-olcek)" in _ek and _ek.count("var(--se-u)") > 40)
c("tek ekran: sayfa zoom/scale ile kucultulmez", "zoom" not in _ek and "scale(" not in _ek)
c("tek ekran: baslik tek satir, KPI karti kompakt",
  ".bs-kutu{ display:flex !important;" in _ek and "--se-kart-h:calc(clamp(84px, 11vh, 120px)" in _ek)
c("tek ekran: satir ici stil secicileri tarayicinin bicimiyle de eslesir (bosluklu)",
  '[style*="font-size: 15px; font-weight: 800"]' in _ek and '[style*="overflow-y: auto"]' in _ek
  and '[style*="position: fixed; top: 10px; left: 18px"]' in _ek)

# ── 4) app_merkez kaynagi: yalniz demoda ──────────────────────────────────
_mrk = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
ast.parse(_mrk)
_EKRAN_BLOK = re.search(r"\nif _ust_serit_kutu is not None:\n(?:    .*\n|        .*\n)+", _mrk)
c("tek ekran CSS'i yalniz serit kabi (demo) varken basilir",
  _EKRAN_BLOK and "_usd_ekran.ekran_css()" in _EKRAN_BLOK.group(0)
  and _mrk.count("_usd_ekran.ekran_css()") == 1)
c("tek ekran blogu serit kabindan hemen sonra, sutunlardan once",
  _EKRAN_BLOK and _mrk.index('key="ust_serit_demo"') < _EKRAN_BLOK.start() < _mrk.index("sol, merkez, sag = st.columns("))
c("acik surecte eski modul yeniden yuklenir (SURUM)",
  'getattr(_usd_ekran, "SURUM", 0) < %d' % U.SURUM in _mrk)
c("serit kabi yalniz demoda ve SYNAPSE_DEMO_ESKI=1 iken acilir (varsayilan demo: cark ekrani)",
  '_ust_serit_kutu = st.container(key="ust_serit_demo") if _demo_eski else None' in _mrk
  and '_demo_eski = _demo_modu() and os.environ.get("SYNAPSE_DEMO_ESKI", "").strip() == "1"' in _mrk)
c("kap ana uc sutundan ONCE", _mrk.index('key="ust_serit_demo"') < _mrk.index("sol, merkez, sag = st.columns("))
c("modul yalniz else (demo) dalinda yuklenir",
  re.search(r"else:\n\s+# ── YALNIZ SUNUM: üst şerit.*?\n\s+import ust_serit_demo as _usd", _mrk, re.S))
c("eski Global Ozet basligi canlida duruyor",
  "if _ust_serit_kutu is None:\n        st.markdown('<div class=\"sec\">' + _ik.ikon(\"enerji\", 17) + 'GLOBAL ÖZET — ANLIK</div>'" in _mrk)
c("ozet kartlari demoda saga kaymaz, continue ile atlanir",
  "_ust_ozet_kartlar.append((" in _mrk and "continue" in _mrk)

# ── 5) AppTest: canli ve demo cizimi ──────────────────────────────────────
for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ[v] = "http://127.0.0.1:9"          # dis aga cikis olmasin
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
try:
    from streamlit.testing.v1 import AppTest
    import giris
    import _sim_sunucu
except Exception as e:                       # streamlit yoksa bu bolum atlanir
    AppTest = None
    print("ATLANDI AppTest:", e)

if AppTest is not None:
    _H = giris.parola_hash_uret("yalniz-test")
    os.environ["SYNAPSE_GIRIS_KULLANICI"] = "test"
    os.environ["SYNAPSE_GIRIS_PAROLA_HASH"] = _H
    _SIM = _sim_sunucu.sunucu_baslat(8099)

    def _calistir(demo, dosya=None):
        if demo:
            os.environ["SYNAPSE_DEMO"] = "1"
            # Serit artik eski demo gorunumu: bayrakla acilir (varsayilan cark ekrani)
            os.environ["SYNAPSE_DEMO_ESKI"] = "1"
            os.environ.pop("SYNAPSE_ESKI_ARAYUZ", None)
            os.environ.pop("SYNAPSE_SIM_URL", None)
        else:
            os.environ.pop("SYNAPSE_DEMO", None)
            os.environ.pop("SYNAPSE_DEMO_ESKI", None)
            # Canli 23.11.2026'dan beri cark; bu dosya eski uc sutun duzenini (geri donus
            # bayragi SYNAPSE_ESKI_ARAYUZ=1) sinar
            os.environ["SYNAPSE_ESKI_ARAYUZ"] = "1"
            os.environ["SYNAPSE_SIM_URL"] = _SIM
        # Sarici ASCII kalir (AppTest sistem kodlamasiyla yazar)
        at = AppTest.from_string("import runpy\nrunpy.run_path(%r, run_name='__main__')\n"
                                 % (dosya or os.path.join(BURASI, "app_merkez.py")), default_timeout=240)
        at.session_state["giris_ok"] = True
        at.session_state["giris_jeton"] = giris._jeton_uret(_H, 3600)
        at.session_state["giris_son_hareket"] = time.time()
        at.run()
        return at, "\n".join(m.value for m in at.markdown), [b.key for b in at.button]

    _at, _md, _bt = _calistir(False)
    c("[canli] hatasiz cizilir", not _at.exception, [str(e.value)[:200] for e in _at.exception])
    c("[canli] serit YOK", "us-serit" not in _md)
    c("[canli] Global Ozet sol sutunda", "GLOBAL ÖZET — ANLIK" in _md and _md.count('<a class="ozet-kart"') == 5)
    c("[canli] Canli Uyarilar sag sutunda", "CANLI UYARILAR</div>" in _md)
    c("[canli] gizli ozet dugmeleri", sum(1 for b in _bt if b and b.startswith("gizli_ozet_")) == 5)
    c("[canli] tek ekran CSS'i YOK", "100dvh" not in _md and "--se-kart-h" not in _md)

    # Canli cizim, tek ekran blogu cikarilmis kaynakla AYNI olmali (sayilar ve
    # saat damgalari ayiklanir: veri saniyelik degisir).
    def _iz(at):
        # Oge kimligi betik yolundan, oturum jetonu zamandan turetilir (her calismada farkli)
        _n = lambda s: re.sub(r"\d+(?:[.,]\d+)*", "0", re.sub(
            r"[0-9a-f.]{16,}", "H", re.sub(r"\$\$ID-[0-9a-f]+-", "$$ID-", s)))
        return ([_n(m.value) for m in at.markdown], [b.key for b in at.button],
                [_n(str(getattr(e, "proto", ""))) for e in at.main if type(e).__name__ != "Markdown"])
    _kiyas = os.path.join(BURASI, "_kiyas_app_merkez_tmp.py")
    try:
        with open(_kiyas, "w", encoding="utf-8") as _f:
            _f.write(_mrk.replace(_EKRAN_BLOK.group(0), "\n", 1))
        _at2, _, _ = _calistir(False, _kiyas)
        _a, _b = _iz(_at), _iz(_at2)
        c("[canli] tek ekran blogu olmadan cizimle ayni (markdown, dugmeler, diger ogeler)",
          not _at2.exception and _a == _b,
          [(k, len(x), len(y), next(((i, p[:300], q[:300]) for i, (p, q) in enumerate(zip(x, y)) if p != q), None))
           for k, (x, y) in enumerate(zip(_a, _b)) if x != y])
    finally:
        if os.path.exists(_kiyas):
            os.remove(_kiyas)

    _at, _md, _bt = _calistir(True)
    c("[demo] hatasiz cizilir", not _at.exception, [str(e.value)[:200] for e in _at.exception])
    c("[demo] seritte 5 ozet karti", _md.count('class="ozet-kart us-kart') == 5)
    c("[demo] seritte uyari karti", 'class="us-kart us-uyari' in _md)
    c("[demo] tek ekran CSS'i basilir (bir kez)", _md.count("height:100dvh") == 1)
    c("[demo] sol sutundaki eski kartlar yok",
      "GLOBAL ÖZET — ANLIK" not in _md and '<a class="ozet-kart" ' not in _md)
    c("[demo] sag sutundaki eski uyari basligi yok", "CANLI UYARILAR</div>" not in _md)
    c("[demo] gizli ozet dugmeleri duruyor", sum(1 for b in _bt if b and b.startswith("gizli_ozet_")) == 5)
    c("[demo] lokasyon kartlari duruyor", 'lok-kart" data-lok=' in _md)
    c("[demo] lokasyon arama kutusu duruyor", any(t.key == "lok_ara" for t in _at.text_input))
    _sira = [m for m in re.findall(r'data-ozet="([a-z]+)"', _md)]
    c("[demo] kart sirasi enerji, dogalgaz, sogutma, su, kojen",
      _sira[:5] == ["enerji", "dogalgaz", "sogutma", "su", "kojen"], _sira)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
