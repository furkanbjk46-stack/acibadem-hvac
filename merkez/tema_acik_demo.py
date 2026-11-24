"""ÇARK ARAYÜZÜ: AYDINLIK TEMA (sunumda 17.11.2026, canlıda 23.11.2026'dan beri).

Çark ekranları (çark ana ekran, pop-up'lar, lokasyon detayı, Sistem) koyu temayla
yazıldı. Aydınlık tema elle ikinci bir CSS yazmak yerine koyu CSS'ten ÜRETİLİR:
her kuralın yalnız renk taşıyan bildirimleri alınır, renkler aydınlık karşılığına
çevrilir ve seçicinin başına `html.ck-acik-tema` eklenir. Sınıf yokken (varsayılan
karanlık tema) bu kuralların hiçbiri eşleşmez.

Renk çevirisi (özellik türüne göre):
  zemin  (background, --ck-zemin*, --ck-cam): koyu → beyaza yakın (aynı ton), koyu
         yarı saydam perde → hafif lacivert perde, açık vurgu → hafif lacivert vurgu
  yazı   (color, --c, fill, --ck-metin*): açık → lacivert / gri tonları
  kenar  (border, outline, --ck-cam-kenar*): açık → hafif lacivert
  gölge  (box-shadow, filter): koyu gölgeler hafifler, parlamalar koyu turkuaza döner
  turkuaz vurgu her yerde beyaz zeminde okunan koyu turkuaza çekilir; kırmızı / amber /
  yeşil gibi durum renkleri korunur (yazıdaysa biraz koyulaşır).

Geçiş düğmesi çark ekranının alt orta çubuğundadır; seçim tarayıcıda saklanır
(localStorage "ck_tema") ve her sayfa açılışında betikle geri yüklenir.
"""
import colorsys
import functools
import re

SURUM = 9  # app_merkez bu sayıyla açık süreçte modülü yeniden yükler
SINIF = "ck-acik-tema"
KOK = "html." + SINIF
# Tema uygulandı işareti (24.11.2026): sayfa ilk açılışta (sert yenileme) eski başlık →
# koyu çark → aydınlık tema sırasıyla bir an yanıp sönüyordu. Ana ekran bu sınıf gelene
# dek gizli (on_yukleme_css); tema çerezi (ck_tema) zemin rengini sunucuda seçtirir.
HAZIR = "ck-tema-hazir"


def on_yukleme_css(tema: str = None) -> str:
    """Çark ana ekranı, kayıtlı tema uygulanana dek (html.ck-tema-hazir) gizli; zemin
    kayıtlı temanın renginde. Betik çalışmazsa 3 sn sonra içerik yine de görünür."""
    zemin = "#eef3f6" if tema == "acik" else "#03141a"
    # :not(#ck-on) kimlik özgüllüğü katar: çark ekranının body:has(...) zemin kuralını geçer
    h = "html:not(.%s):not(#ck-on)" % HAZIR
    return ("<style>%s, %s body, %s [data-testid=\"stAppViewContainer\"]{ background:%s !important; }\n"
            "%s [data-testid=\"stMainBlockContainer\"]{ opacity:0; animation:ckOnAc 0s linear 3s forwards; }\n"
            "@keyframes ckOnAc{ to{ opacity:1; } }</style>" % (h, h, h, zemin, h))

_RENK = re.compile(r"rgba?\(\s*[\d.]+\s*,\s*[\d.]+\s*,\s*[\d.]+\s*(?:,\s*[\d.]+\s*)?\)|#[0-9a-fA-F]{3,8}\b")

_LACIVERT = (15, 31, 61)       # ana yazı
_GRI_2 = (70, 83, 107)         # ikincil yazı
_GRI_3 = (123, 135, 150)       # soluk yazı
_TURKUAZ = (11, 125, 115)      # vurgu (beyaz zeminde okunur)
_ZEMIN = (238, 243, 246)       # sayfa zemini


def _coz(s: str):
    s = s.strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return r, g, b, a
    p = [float(x) for x in re.findall(r"[\d.]+", s)]
    return int(p[0]), int(p[1]), int(p[2]), (p[3] if len(p) > 3 else 1.0)


def _yaz(r, g, b, a) -> str:
    r, g, b = (max(0, min(255, int(round(x)))) for x in (r, g, b))
    if a >= 0.999:
        return "#%02x%02x%02x" % (r, g, b)
    return "rgba(%d,%d,%d,%s)" % (r, g, b, ("%.3f" % max(0.0, min(1.0, a))).rstrip("0").rstrip("."))


def _parlak(r, g, b) -> float:
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _karistir(c1, c2, t):
    return tuple(c1[i] * (1 - t) + c2[i] * t for i in range(3))


def _tur(r, g, b):
    """'turkuaz' | 'durum' (kırmızı / amber / yeşil / mavi / pembe…) | 'notr'"""
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if s < 0.22 or l < 0.2 or (l > 0.86 and s < 0.6):   # gri, çok koyu yüzey, çok açık pastel
        return "notr"
    deg = h * 360
    if 160 <= deg <= 205 and s >= 0.3:
        return "turkuaz"
    return "durum"


def renk_cevir(deger: str, rol: str) -> str:
    r, g, b, a = _coz(deger)
    L = _parlak(r, g, b)
    tur = _tur(r, g, b)
    if rol == "yazi":
        if tur == "turkuaz":
            return _yaz(*_TURKUAZ, a)
        if tur == "durum":
            return _yaz(*_karistir((r, g, b), (0, 0, 0), 0.22 if L > 0.55 else 0.0), a)
        if L > 0.82:
            return _yaz(*_LACIVERT, a)
        if L > 0.55:
            return _yaz(*_GRI_2, a)
        if L > 0.3:
            return _yaz(*_GRI_3, a)
        return _yaz(r, g, b, a)                       # zaten koyu (lacivert logo vb.)
    if rol == "kenar":
        if tur == "turkuaz" and a >= 0.3:
            return _yaz(*_TURKUAZ, min(1.0, a * 1.2))
        if tur == "turkuaz":
            return _yaz(19, 50, 115, min(0.3, a * 1.1))
        if tur == "durum":
            return _yaz(r, g, b, a)
        if L > 0.5:
            return _yaz(19, 50, 115, min(1.0, a * 1.1))
        return _yaz(19, 50, 115, min(0.25, a))
    if rol == "golge":
        if tur == "turkuaz":
            return _yaz(*_TURKUAZ, a * 0.55)
        if tur == "durum":
            return _yaz(r, g, b, a * 0.7)
        return _yaz(15, 31, 61, a * (0.35 if L < 0.3 else 0.25))
    # zemin
    if tur == "turkuaz":
        if L > 0.45:                                  # açık turkuaz vurgu zemini
            return _yaz(*_TURKUAZ, a * (1.0 if a < 0.5 else 0.9))
        return _yaz(*_karistir((r, g, b), (255, 255, 255), 0.95), max(a, 0.88))
    if tur == "durum":
        return _yaz(r, g, b, a)
    if L < 0.06 and a < 0.75:                         # koyu yarı saydam perde
        return _yaz(*_LACIVERT, a * 0.45)
    if L < 0.35:                                      # koyu yüzey → beyaza yakın, tonu korunur
        return _yaz(*_karistir((r, g, b), (255, 255, 255), 0.95), max(a, 0.88))
    if L > 0.85:                                      # koyu zemindeki hafif ışık → hafif lacivert
        return _yaz(*_LACIVERT, min(0.08, a * 1.3) if a < 0.3 else a)
    return _yaz(*_karistir((r, g, b), (255, 255, 255), 0.6), a)


def _rol(ozellik: str) -> str:
    o = ozellik.strip().lower()
    if o.startswith("--"):
        if o == "--c" or o.startswith("--ck-metin"):
            return "yazi"
        if o.startswith(("--ck-cam-kenar", "--ck-cizgi")):
            return "kenar"
        if o.startswith(("--ck-vurgu", "--ck-mavi", "--ck-yesil", "--ck-amber", "--ck-kirmizi", "--ck-gri", "--ai-renk")):
            return "yazi"
        return "zemin"
    if o in ("color", "-webkit-text-fill-color", "caret-color", "fill", "stop-color", "text-decoration-color"):
        return "yazi"
    if o.startswith(("border", "outline", "column-rule", "stroke", "scrollbar-color", "accent-color")):
        return "kenar"
    if o in ("box-shadow", "text-shadow", "filter", "drop-shadow"):
        return "golge"
    return "zemin"


def _bildirim_cevir(bildirim: str):
    """'özellik: değer [!important]' → çevrilmiş bildirim; renk yoksa None."""
    if ":" not in bildirim:
        return None
    oz, deg = bildirim.split(":", 1)
    if not _RENK.search(deg):
        return None
    rol = _rol(oz)
    # "background" kısa yazımı background-clip:text gibi ayarları sıfırlar: yalnız rengi değiştir
    if oz.strip().lower() == "background" and "url(" not in deg:
        oz = "background-image" if "gradient(" in deg else "background-color"
    if oz.strip().lower() == "--ck-zemin-1":
        return "%s:%s" % (oz, _RENK.sub(lambda m: _yaz(*_ZEMIN, 1), deg))
    return "%s:%s" % (oz, _RENK.sub(lambda m: renk_cevir(m.group(0), rol), deg))


def _bolumle(govde: str):
    """Kural gövdesini bildirimlere ve iç içe kurallara böler."""
    parcalar, d, bas = [], 0, 0
    tirnak, koseli = None, 0
    i = 0
    while i < len(govde):
        ch = govde[i]
        if tirnak:                       # tırnak içi (seçicideki [style*="a; b"]) atlanır
            if ch == tirnak:
                tirnak = None
            i += 1
            continue
        if ch in "\"'":
            tirnak = ch
        elif ch == "[":
            koseli += 1
        elif ch == "]":
            koseli -= 1
        elif koseli:
            pass
        elif ch == "{":
            d += 1
        elif ch == "}":
            d -= 1
            if d == 0:
                parcalar.append(("kural", govde[bas:i + 1].strip()))
                bas = i + 1
        elif ch == ";" and d == 0:
            parcalar.append(("bildirim", govde[bas:i].strip()))
            bas = i + 1
        i += 1
    kalan = govde[bas:].strip()
    if kalan:
        parcalar.append(("bildirim", kalan))
    return parcalar


def _secici_onekle(secici: str) -> str:
    """Seçici listesindeki her parçanın başına html.ck-acik-tema ekler."""
    d, bas, parca = 0, 0, []
    for i, ch in enumerate(secici):
        if ch in "([":
            d += 1
        elif ch in ")]":
            d -= 1
        elif ch == "," and d == 0:
            parca.append(secici[bas:i])
            bas = i + 1
    parca.append(secici[bas:])
    sonuc = []
    for p in parca:
        p = p.strip()
        if not p:
            continue
        if p.startswith("html"):
            sonuc.append("html." + SINIF + p[4:])
        elif p.startswith(":root"):
            sonuc.append(KOK + p[5:])
        else:
            sonuc.append(KOK + " " + p)
    return ", ".join(sonuc)


def _kural_cevir(kural: str, ic_ice: bool = False):
    if "{" not in kural:
        return ""
    bas = kural.index("{")
    secici = kural[:bas].strip()
    govde = kural[bas + 1:kural.rindex("}")]
    if secici.startswith("@keyframes") or secici.startswith("@font-face"):
        return ""
    if secici.startswith("@media") or secici.startswith("@supports"):
        ic = "".join(_kural_cevir(k) for t, k in _bolumle(govde) if t == "kural")
        return "%s{%s}\n" % (secici, ic) if ic else ""
    satirlar = []
    for tur, p in _bolumle(govde):
        if tur == "bildirim":
            c = _bildirim_cevir(p)
            if c:
                satirlar.append(c)
        else:
            c = _kural_cevir(p, ic_ice=True)
            if c:
                satirlar.append(c.strip())
    if not satirlar:
        return ""
    yeni = secici if ic_ice else _secici_onekle(secici)
    return "%s{ %s }\n" % (yeni, "; ".join(s for s in satirlar if not s.endswith("}")) +
                           ("; " if any(not s.endswith("}") for s in satirlar) else "") +
                           " ".join(s for s in satirlar if s.endswith("}")))


def donustur(css: str) -> str:
    """Koyu tema CSS metnini (<style> etiketli ya da değil) aydınlık eşine çevirir."""
    css = re.sub(r"</?style[^>]*>", "", css)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    cikti, d, bas = [], 0, 0
    for i, ch in enumerate(css):
        if ch == "{":
            d += 1
        elif ch == "}":
            d -= 1
            if d == 0:
                cikti.append(_kural_cevir(css[bas:i + 1].strip()))
                bas = i + 1
    return "".join(cikti)


# Elle eklenenler: dönüşümün yakalayamadığı birkaç özel durum
_EK = """
KOK body{ color-scheme:light; }
KOK .ck-sahne .ck-kure{ background:#1f2559; }
KOK .ck-sahne .ck-kart-sayi, KOK .ck-sahne .ck-p-buyuk b{ --c:#0f1f3d; }
KOK [data-testid="stAppViewContainer"]::before{ filter:blur(7px) brightness(1.35) saturate(.5) !important; opacity:.32 !important; }
KOK .ck-sahne .ck-tema .ck-tema-koyu{ display:inline; } KOK .ck-sahne .ck-tema .ck-tema-acik{ display:none; }
"""


@functools.lru_cache(maxsize=8)
def _onbellek(css: str) -> str:
    return donustur(css)


def hepsi() -> str:
    """Tüm demo ekranlarının aydınlık kuralları TEK PARÇA: ana ekran, pop-up'lar, geçiş
    iskeleti, detay ve Sistem. Her sayfada aynısı basılır; böylece geçişte (sayfa
    değişirken) aydınlık kurallar eksik kalıp ekran bir an karanlığa dönmez."""
    import importlib
    import ana_ekran_cark_demo as C
    import detay_tema_demo as T
    if not hasattr(T, "yonetim_css"):
        T = importlib.reload(T)
    return acik_css(C.ekran_css(), C.sahne_css(), T.tema_css(), T.GECIS_CSS, T.yonetim_css())


def acik_css(*koyu_css: str) -> str:
    """Verilen koyu tema CSS'lerinin aydınlık karşılığı (<style> içinde)."""
    return "<style>\n" + "".join(_onbellek(c) for c in koyu_css) + _EK.replace("KOK", KOK) + "</style>"


# Sistem ekranından "Geri": yeni ana ekran çizilirken eski Sistem kabı sayfada ~0,7 sn
# kalıyordu; ana ekran kuralları ":not(:has(.st-key-yonetim_katmani))" ile kapalı
# kaldığından gizli "git" düğmeleri ve boyutsuz büyük ikonlar bir an görünüyordu
# (24.11.2026). Tıklama anında eski kap gizlenir ve işaret sınıfı alınır; Streamlit
# eski kabı yeniden çizimin sonunda zaten kaldırır. Ana belgeye bir kez eklenir.
YON_CIKIS = ("(function(){var d=document;window.__ckYonCikis=1;"
             "d.addEventListener('click',function(ev){var b=ev.target&&ev.target.closest&&"
             "ev.target.closest('.st-key-yonetim_geri button');if(!b){return;}"
             "var k=d.querySelector('.st-key-yonetim_katmani');if(!k){return;}"
             "k.style.display='none';k.classList.remove('st-key-yonetim_katmani');"
             "k.classList.add('ck-yon-eski');},true);})();")


def betik() -> str:
    """Kaydedilen temayı (localStorage ck_tema) uygular; tema düğmesine (data-ck-eylem="tema")
    basılınca değiştirir. Motor ANA BELGEYE <script> olarak bir kez eklenir: components.html
    çerçevesi her yeniden çizimde yok olur ve çerçevede tanımlı dinleyiciler onunla ölür
    (düğmenin "bazen çalışmaması" bundandı)."""
    import json
    motor = ("(function(){var d=document,W=window,S='" + SINIF + "';"
             "function oku(){try{return W.localStorage.getItem('ck_tema');}catch(e){return null;}}"
             "function uygula(t){var h=d.documentElement;h.classList.toggle(S,t==='acik');h.classList.add('" + HAZIR + "');"
             "try{d.cookie='ck_tema='+(t==='acik'?'acik':'koyu')+'; path=/; max-age=31536000; SameSite=Lax';}catch(e){}}"
             "W.__ckTemaUygula=function(){uygula(oku());};W.__ckTemaUygula();"
             "W.addEventListener('click',function(ev){var b=ev.target&&ev.target.closest&&"
             "ev.target.closest('[data-ck-eylem=\"tema\"]');if(!b){return;}ev.preventDefault();ev.stopPropagation();"
             "var y=d.documentElement.classList.contains(S)?'koyu':'acik';"
             "try{W.localStorage.setItem('ck_tema',y);}catch(e){}uygula(y);},true);})();")
    return ("<script>(function(){var W=window.parent,d;try{d=W.document;}catch(e){return;}"
            "if(!W.__ckYonCikis){var y=d.createElement('script');y.id='ck-yon-cikis';y.textContent="
            + json.dumps(YON_CIKIS) + ";d.head.appendChild(y);}"
            "if(W.__ckTemaUygula){W.__ckTemaUygula();return;}"
            "var s=d.createElement('script');s.id='ck-tema-motor';s.textContent=" + json.dumps(motor) + ";"
            "d.head.appendChild(s);})();</script>")
