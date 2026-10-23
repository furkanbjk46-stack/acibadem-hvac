# -*- coding: utf-8 -*-
"""Mekanik Zeka'nın simge dosyası, Synapse'in tek kaynağıyla (ikonlar.py) aynı mı?"""
import os
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import ikon_js_uret as U  # noqa: E402

STATIC = os.path.join(BURASI, "..", "hvac", "deneme", "static")
T = []


def c(ad, kosul):
    T.append((ad, bool(kosul)))


def oku(ad):
    with open(os.path.join(STATIC, ad), encoding="utf-8") as f:
        return f.read()


c("synapse_ikon.js ikonlar.py ile aynı (değiştiyse ikon_js_uret.py çalıştır)",
  oku("synapse_ikon.js") == U.uret())
html = oku("index.html")
c("index.html tasarım katmanını yüklüyor",
  "synapse_tema.css" in html and "synapse_ikon.js" in html and "synapse_tema.js" in html)
c("katman stilden SONRA yükleniyor", html.index("synapse_tema.css") > html.index("</style>"))
c("grafik yazıları beyaz değil (açık zeminde görünmez)", "color: 'white'" not in html)
css = oku("synapse_tema.css")
c("hareketi azalt tercihine uyuyor", "prefers-reduced-motion" in css)
c("akan başlık + nabız + parıltı animasyonları var",
  all(k in css for k in ("@keyframes synAkis", "@keyframes synNabiz", "@keyframes synParilti")))

# ── 2. tur: kullanıcı istekleri (23.10.2026) ──
c("motor seçimi kaldırıldı, değer sabit v2",
  '<select class="engine-select"' not in html and 'id="engineSelect" value="v2"' in html)
c("üstteki 'ACIBADEM SAĞLIK GRUBU — HVAC' çerçevesi kalktı: /hvac arayüze yönlendirir",
  "RedirectResponse(url=\"/static/index.html\"" in open(os.path.join(STATIC, "..", "main_portal.py"), encoding="utf-8").read())
c("Ana Sayfa / Ayarlar / Bakım Kartları sağda yan yana", 'class="header-actions"' in html and 'href="/"' in html)
c("KPI simgesi rakamın solunda", html.count('class="kpi-satir"') == 4)
c("kapasite ve kW kartlarında hareketli çubuk",
  all(k in html for k in ("coolingCapacityBar", "heat_kw_uretim_bar", "synKapasite(", "synKw(")))
c("kapasite metninde emoji yok", "${coolCap.emoji}" not in html and "${heatCap.emoji}" not in html)
c("yatay taşma düzeltmesi (1fr sütunu daralır)", ".main-layout > *, .results-section" in css)
c("sayaç rozeti CSS'i simge span'ını boyamaz", ".filter-btn span[id]:not(:empty)" in css)

hata = [a for a, k in T if not k]
for a, k in T:
    print(("PASS " if k else "FAIL ") + a)
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
