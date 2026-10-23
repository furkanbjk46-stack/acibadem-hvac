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

hata = [a for a, k in T if not k]
for a, k in T:
    print(("PASS " if k else "FAIL ") + a)
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
