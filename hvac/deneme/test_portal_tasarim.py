# -*- coding: utf-8 -*-
"""Enerji portalı tasarım dili (29.10.2026): Mekanik Zeka başlığı + Synapse kartları.

    python test_portal_tasarim.py
"""
import ast
import os
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import portal_tasarim as PT  # noqa: E402

PORTAL = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── Başlık: Mekanik Zeka düzeni, Bakım Kartları YOK ──
b = PT.baslik_html("Enerji ve Verimlilik", "Enerji Yönetimi & Raporlama", "Sistem Hazır", "Maslak",
                   [("Ana Sayfa", "geri", "http://x/"), ("Ayarlar", "ayar", "http://x/static/index.html#ayarlar")])
c("başlıkta Ana Sayfa ve Ayarlar var", "Ana Sayfa" in b and "Ayarlar" in b)
c("başlıkta Bakım Kartları yok", "Bakım" not in b)
c("düğmeler üst pencerede açılır (gömülü çerçeveden çıkar)", b.count('target="_top"') == 2)
c("Ayarlar düğmesi Mekanik Zeka ayar penceresine gider", "#ayarlar" in b)
_html = open(os.path.join(BURASI, "static", "index.html"), encoding="utf-8").read()
c("Mekanik Zeka #ayarlar ile ayar penceresini açar", "location.hash === '#ayarlar'" in _html)
c("başlık akan degrade + ışık çizgisi (Mekanik Zeka)", "synAkis" in PT.CSS and "synCizgi" in PT.CSS)
c("portal başlığı çiziyor, eski st.title yok",
  "_pt.baslik_html(" in PORTAL and 'st.title("⚡ Enerji ve Verimlilik")\n\n' not in PORTAL)

# ── Yazı tipi: Inter (Mekanik Zeka ile aynı) ──
c("yazı tipi Inter", "family=Inter" in PT.CSS and "font-family: Inter" in PT.CSS)
c("simge yazı tipleri bozulmaz", "Material Symbols Rounded" in PT.CSS)

# ── Sekmeler: numarasız, emojisiz, simgeli ──
_agac = ast.parse(PORTAL)
_adlar = next(ast.literal_eval(d.value) for d in ast.walk(_agac)
              if isinstance(d, ast.Assign) and getattr(d.targets[0], "id", "") == "TAB_NAMES")
c("sekme sayısı simge listesiyle aynı", len(_adlar) == len(PT.SEKMELER), (len(_adlar), len(PT.SEKMELER)))
c("sekme adlarında numara yok", not any(a[:2].rstrip(")").isdigit() for a in _adlar), _adlar)
c("sekme adlarında emoji yok", all(ord(ch) < 0x2190 or ch in "ıİşŞğĞüÜöÖçÇ" for a in _adlar for ch in a), _adlar)
c("sekmeler simge kabında", 'st.container(key="enerji_sekmeler")' in PORTAL)
c("sekme yazısı büyük harfe çevrilmez", "text-transform: none !important" in PT.CSS)
c("her sekmeye simge kuralı", PT.sekme_css().count("::before") == len(PT.SEKMELER) * 2 or not PT.IK)

# ── Kartlar: değer olduğu gibi yazılır ──
k = PT.kart("enerji", "Dünkü Tüketim", "55.454", "kWh", "▲ %7,1", "syn-kotu")
c("kart değeri olduğu gibi", ">55.454<" in k)
c("kart metni kaçışlı (HTML enjekte edilmez)", "&lt;b&gt;" in PT.kart("enerji", "<b>", "1"))
c("bölüm başlığı (Synapse .sec)", "syn-sec" in PT.bolum("Kojen & Kaynak", "kojen"))
c("Dashboard Synapse kartlarını kullanır", PORTAL.count("_pt.kart(") >= 10)
c("Dashboard'da ÖZET / KOJEN & KAYNAK bölümleri",
  '_pt.bolum(f"Özet — {_gun_txt}"' in PORTAL and '_pt.bolum("Kojen & Kaynak"' in PORTAL)
c("sayma / JavaScript yok (değerler sabit)", "<script" not in open(os.path.join(BURASI, "portal_tasarim.py"),
                                                                  encoding="utf-8").read().lower())

# ── Enerji diyagramı: Synapse kart dili ──
c("diyagramda emoji başlık kalmadı", "🏢 Bina Genel" not in PORTAL and "⚙️ Bina Mekanik" not in PORTAL)
c("diyagram Synapse simgeleri", '("CHILLER", "sogutma", [' in PORTAL and "_ik('trdp', 16)" in PORTAL)

# ── Simge modülü: Synapse'tekinin AYNISI (ayrışmasın) ──
_merkez = os.path.join(BURASI, "..", "..", "merkez", "ikonlar.py")
if os.path.exists(_merkez):     # yalnız geliştirme deposunda (lokasyonda merkez/ yok)
    c("synapse_ikonlar.py = merkez/ikonlar.py",
      open(_merkez, encoding="utf-8").read() == open(os.path.join(BURASI, "synapse_ikonlar.py"),
                                                       encoding="utf-8").read())

# ── /enerji çerçevesi kalktı (Mekanik Zeka /hvac gibi doğrudan açılır) ──
_mp = open(os.path.join(BURASI, "main_portal.py"), encoding="utf-8").read()
_enerji = _mp.split('@app.get("/enerji"')[1].split("\n# ", 1)[0]   # yalnız bu rotanın gövdesi
c("/enerji çerçevesiz açılır", "RedirectResponse" in _enerji and "_iframe_wrapper_html(" not in _enerji)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
