"""tema_acik_demo testleri (YALNIZ SUNUM aydınlık tema).

Çalıştır: python merkez/test_tema_acik_demo.py
"""
import os
import re
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)

import tema_acik_demo as A  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, detay=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", detay)


def parlak(s):
    r, g, b, _ = A._coz(s)
    return A._parlak(r, g, b)


# ── Renk çevirisi ──
c("acik yazi -> koyu lacivert", parlak(A.renk_cevir("#e8f1f2", "yazi")) < 0.25, A.renk_cevir("#e8f1f2", "yazi"))
c("beyaz sayi -> koyu", parlak(A.renk_cevir("#ffffff", "yazi")) < 0.25)
c("ikincil yazi -> gri", 0.2 < parlak(A.renk_cevir("#a6bcc0", "yazi")) < 0.5)
c("koyu yuzey zemini -> acik", parlak(A.renk_cevir("rgba(16,50,60,.62)", "zemin")) > 0.85)
c("koyu degrade duragi -> acik", parlak(A.renk_cevir("rgba(8,30,38,.84)", "zemin")) > 0.85)
c("koyu perde -> hafif lacivert perde (yari saydam)",
  A._coz(A.renk_cevir("rgba(2,10,14,.6)", "zemin"))[3] < 0.4)
c("acik turkuaz vurgu yazi -> koyu turkuaz", A.renk_cevir("#86e8dc", "yazi") == "#0b7d73")
c("durum rengi zeminde korunur", A.renk_cevir("rgba(240,106,90,.5)", "zemin") == "rgba(240,106,90,0.5)")
c("alfa korunur", A._coz(A.renk_cevir("rgba(232,241,242,.4)", "yazi"))[3] == 0.4)

# ── Dönüşüm ──
_k = A.donustur(".ck-sahne .x{ color:#ffffff; padding:4px; background:rgba(14,46,56,.82) !important; }")
c("secici html.ck-acik-tema ile baslar", _k.startswith("html.ck-acik-tema .ck-sahne .x{"), _k)
c("renksiz bildirim alinmaz", "padding" not in _k)
c("!important korunur", "!important" in _k)
c("background kisa yazimi rengi degistirir (clip sifirlanmaz)", "background-color:" in _k and "background:" not in _k)
_g = A.donustur(".a{ background:linear-gradient(90deg, #0c3a44, #86e8dc); -webkit-background-clip:text; }")
c("degrade background-image olarak", "background-image:linear-gradient" in _g, _g)
c("html seciciye sinif eklenir", A.donustur("html:has(.q){ background:#03141a; }").startswith("html.ck-acik-tema:has(.q)"))
c("keyframes alinmaz", A.donustur("@keyframes z{ from{ color:#fff; } }") == "")
_m = A.donustur("@media (max-width:900px){ .a{ color:#fff; } .b{ margin:0; } }")
c("media icindeki kurallar donusur", _m.startswith("@media (max-width:900px){") and ".ck-acik-tema .a{" in _m and ".b" not in _m, _m)
_n = A.donustur('body .k{ & [style*="background:#fafaf8; "]{ background:rgba(255,255,255,.04) !important; } & .s{ color:#e8f1f2; } }')
c("ic ice kural: seci icindeki ; ve renkler bozulmaz",
  '[style*="background:#fafaf8; "]' in _n and "& .s{" in _n, _n)

# ── Gerçek CSS ──
import ana_ekran_cark_demo as C  # noqa: E402
import detay_tema_demo as T  # noqa: E402
_ana = A.acik_css(C.ekran_css(), C.sahne_css())
c("ana: acilan / kapanan parantez esit", _ana.count("{") == _ana.count("}"))
_govde = _ana[_ana.index(">") + 1:_ana.rindex("<")]
c("ana: her kural aydinlik sinifina bagli (karanlikta eslesmez)",
  all(s.strip().startswith(("html.ck-acik-tema", "@media")) for s in re.findall(r"(?:^|\n)([^\s&][^{\n]*)\{", _govde)))
c("ana: palet degiskenleri aydinlik", "--ck-metin:#0f1f3d" in _ana and "--ck-zemin-1:#eef3f6" in _ana)
_det = A.acik_css(T.tema_css(), T.GECIS_CSS)
c("detay: parantez esit", _det.count("{") == _det.count("}"))
c("yonetim: uretilir", "html.ck-acik-tema" in A.acik_css(T.yonetim_css()))

# ── Düğme ve betik ──
_s = C.sahne_html(C.veri_hazirla({}, [], {}, {}, {}, {}, {}, {}, {}, {}), [], {})
c("alt cubukta tema dugmesi", 'data-ck-eylem="tema"' in _s and "Aydınlık" in _s and "Karanlık" in _s)
_b = A.betik()
c("betik: tercih tarayicida saklanir", "localStorage" in _b and "ck_tema" in _b)
c("betik: pencere duzeyinde (belgeden once) dinler", "W.addEventListener('click'" in _b)
c("betik: motor ana belgeye <script> olarak bir kez eklenir (cerceve olunce dinleyici olmez)",
  "ck-tema-motor" in _b and "d.head.appendChild(s)" in _b and "if(W.__ckTemaUygula)" in _b)
c("hepsi: tum ekranlarin aydinlik kurallari tek parca", A.hepsi().count("html.ck-acik-tema") > 100)

# ── Uygulama ──
_app = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
c("app: uc dalda basilir (ana, detay, Sistem) + on yukleme", _app.count("import tema_acik_demo as") == 4)
c("app: acik surecte SURUM ile yenilenir",
  _app.count('"SURUM", 0) < %d:   # açık süreçte eski modül' % A.SURUM) == 4)
# 24.11.2026: sert yenilemede eski başlık / yanlış tema bir an görünmesin
_on = A.on_yukleme_css("acik")
c("on yukleme: tema hazir olana dek ana alan gizli, 3 sn emniyet",
  'html:not(.ck-tema-hazir):not(#ck-on) [data-testid="stMainBlockContainer"]{ opacity:0; animation:ckOnAc 0s linear 3s forwards; }' in _on)
c("on yukleme: zemin kayitli temada", "#eef3f6" in _on and "#03141a" in A.on_yukleme_css(None)
  and "#03141a" in A.on_yukleme_css("koyu"))
_bt = A.betik()
c("betik: tema uygulaninca hazir isareti ve cerez", "ck-tema-hazir" in _bt and "ck_tema=" in _bt)
c("app: on yukleme yalniz cark ana ekraninda, cerezle",
  'if _cark_arayuz() and not st.session_state.get("detay_lokasyon"):\n    import tema_acik_demo as _tad_on' in _app
  and 'st.context.cookies.get("ck_tema")' in _app)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
