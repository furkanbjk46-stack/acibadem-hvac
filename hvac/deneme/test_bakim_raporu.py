# -*- coding: utf-8 -*-
"""Bakım raporu — otomatik PDF ile EKRANDAKİ PDF aynı kalıpta mı?

Bakım durumu iki ayrı yerde PDF'e dökülüyor:
  · static/index.html  → jsPDF, kullanıcı "PDF Oluştur" deyince
  · bakim_raporu.py    → fpdf2, ayın 5'inde otomatik
Eskiden otomatik rapor bambaşka bir biçimdeydi (santral kartları, yalnız
"Arızalı: ..." satırı). Aynı veriyi iki farklı yüzle görmek sahada karışıklık
yarattı. Bu test iki kalıbın başlık, sütun, rozet ve lejant metinlerinin
AYNI kaldığını koruyor: biri değişirse diğeri de değişmek zorunda.
"""
import os
import re
import shutil
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
# Test adlarında ✓ gibi işaretler var; konsol cp1254 ise çökmesin.
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import bakim_raporu as br  # noqa: E402

HTML = open(os.path.join(BURASI, "static", "index.html"), encoding="utf-8").read()
PY = open(os.path.join(BURASI, "bakim_raporu.py"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def _js_dizi(ad):
    """index.html içindeki `const <ad> = ['a', 'b', ...];` dizisini oku."""
    m = re.search(r"const\s+" + ad + r"\s*=\s*\[(.*?)\]", HTML, re.S)
    return re.findall(r"'([^']*)'", m.group(1)) if m else []


def _js_sozluk(ad):
    """index.html içindeki `const <ad> = { k: 'v', ... };` eşlemesini oku."""
    m = re.search(r"const\s+" + ad + r"\s*=\s*\{(.*?)\n\s*\};", HTML, re.S)
    if not m:
        return {}
    return {k: v.replace("\\n", "\n")
            for k, v in re.findall(r"(\w+)\s*:\s*'([^']*)'", m.group(1))}


# ── 1) Bileşen listesi ve etiketler iki tarafta AYNI ─────────────────────
_js_comp = _js_dizi("components")
c("ekran bileşen listesi okundu", len(_js_comp) == 7, _js_comp)
c("bileşen sırası ekranla aynı", br.BILESENLER == _js_comp,
  (br.BILESENLER, _js_comp))
c("bileşen etiketleri ekranla aynı", br.BILESEN_ETIKET == _js_sozluk("compLabels"),
  (br.BILESEN_ETIKET, _js_sozluk("compLabels")))
c("tablo başlıkları ekranla aynı", br.BILESEN_BASLIK == _js_sozluk("compHead"),
  (br.BILESEN_BASLIK, _js_sozluk("compHead")))

# ── 2) Sayfa metinleri iki tarafta AYNI ──────────────────────────────────
for _metin in ("DİJİTAL BAKIM VE BİLEŞEN DURUM RAPORU",
               "ARIZA VE BAKIM DETAYI",
               "SANTRAL", "ARIZALI SANTRAL", "BAKIMDAKİ SANTRAL",
               "ARIZALI BİLEŞEN", "BAKIMDAKİ BİLEŞEN",
               "ARIZALI — müdahale gerekli", "BAKIMDA — bakım sürüyor",
               "✓ Sağlam", "— Bu santralde yok (N/A)",
               "Synergy — Mekanik Zeka · Dijital Bakım Kartları",
               "Arızalı Bileşenler", "Bakımdaki Bileşenler", "Son Güncelleme",
               "KRİTİK / ACİL", "Santral bakımda"):
    c("ortak metin: %s" % _metin, _metin in HTML and _metin in PY)

c("eski kalıp (santral kartları) kaldırıldı",
  "AYLIK BAKIM RAPORU" not in PY and "SORUN KAYDI OLMAYAN" not in PY)

# ── 3) Rozet / özet kuralları ────────────────────────────────────────────
C = br.BILESENLER


def kart(arizali=(), bakimda=()):
    k = {x: "OK" for x in C}
    k.update({x: "FAULTY" for x in arizali})
    k.update({x: "MAINTENANCE" for x in bakimda})
    return k


_oz = {s["ad"]: s for s in br.santral_ozetleri({
    "AHU-2": kart(bakimda=[C[0]]),
    "AHU-1": kart(arizali=[C[0]]),
    "AHU-4": kart(),
    "AHU-3": kart(bakimda=C),
    "AHU-5": kart(arizali=[C[1], C[2]], bakimda=[C[3]]),
})}
c("arızalı santral KRİTİK / ACİL", _oz["AHU-1"]["rozet"] == "KRİTİK / ACİL")
c("bakımdaki santral ORTA", _oz["AHU-2"]["rozet"] == "ORTA")
c("sorunsuz santral DÜŞÜK", _oz["AHU-4"]["rozet"] == "DÜŞÜK")
c("sorunsuz özet 'Sağlam 7 / 7'", _oz["AHU-4"]["ozet"] == "Sağlam 7 / 7",
  _oz["AHU-4"]["ozet"])
c("tüm bileşenler bakımda → 'Santral bakımda'",
  _oz["AHU-3"]["ozet"].startswith("Santral bakımda"), _oz["AHU-3"]["ozet"])
c("karışık durum iki satır yazar", _oz["AHU-5"]["ozet"] == "2 arızalı\n1 bakımda",
  _oz["AHU-5"]["ozet"])
c("arızalı bileşen adları etiketle verilir",
  _oz["AHU-1"]["arizali"] == [br.BILESEN_ETIKET[C[0]]], _oz["AHU-1"]["arizali"])

_sira = [s["ad"] for s in br.santral_ozetleri({
    "AHU-9": kart(), "AHU-8": kart(bakimda=[C[0]]), "AHU-7": kart(arizali=[C[0]]),
    "AHU-6": kart(arizali=[C[1]]),
})]
c("önce arızalılar, sonra bakımdakiler, sonra ada göre",
  _sira == ["AHU-6", "AHU-7", "AHU-8", "AHU-9"], _sira)
c("kart yoksa çökmez", br.santral_ozetleri({}) == [] and br.santral_ozetleri(None) == [])

# ── 4) PDF gerçekten üretiliyor ──────────────────────────────────────────
_gecici = tempfile.mkdtemp(prefix="bakim_test_")
try:
    _kartlar = os.path.join(_gecici, "cards.json")
    with open(_kartlar, "w", encoding="utf-8") as f:
        import json
        json.dump({"cards": {
            "MAS-1 AHU-1": dict(kart(arizali=[C[4]]), notes="Sensör sapmalı",
                                _updated_at="2026-09-18T09:12:00+00:00"),
            "MAS-1 AHU-2": kart(bakimda=C),
            "MAS-1 AHU-3": kart(),
        }}, f, ensure_ascii=False)
    _eski = (br.CARDS_FILE, br.TAKVIM_FILE, br.AUDIT_FILE, br.OUT_DIR)
    br.CARDS_FILE = _kartlar
    br.TAKVIM_FILE = os.path.join(_gecici, "yok.json")
    br.AUDIT_FILE = os.path.join(_gecici, "yok.jsonl")
    br.OUT_DIR = _gecici
    _pdf = br.generate(2026, 9)
    c("PDF üretildi", os.path.exists(_pdf) and os.path.getsize(_pdf) > 5000,
      os.path.getsize(_pdf) if os.path.exists(_pdf) else "yok")
    c("dosya adı dönemi taşır", os.path.basename(_pdf) == "bakim_raporu_202609.pdf",
      os.path.basename(_pdf))
    _ham = open(_pdf, "rb").read(400)
    c("geçerli PDF başlığı", _ham.startswith(b"%PDF"))
    # Kart yokken de rapor üretilmeli (boş ay)
    with open(_kartlar, "w", encoding="utf-8") as f:
        f.write('{"cards": {}}')
    _bos = br.generate(2026, 8)
    c("kart yokken de PDF üretilir", os.path.exists(_bos))
    br.CARDS_FILE, br.TAKVIM_FILE, br.AUDIT_FILE, br.OUT_DIR = _eski
finally:
    shutil.rmtree(_gecici, ignore_errors=True)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
