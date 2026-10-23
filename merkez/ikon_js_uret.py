# -*- coding: utf-8 -*-
"""Synapse simgelerini Mekanik Zeka (hvac/deneme/static) için JS dosyasına çevirir.

NEDEN ÜRETİCİ: Simgelerin TEK kaynağı merkez/ikonlar.py. Mekanik Zeka lokasyon
PC'sinde çalışır ve merkez/ klasörünü görmez; simgeleri elle kopyalarsak
bir gün Synapse'te değişir, burada eski kalır. Bu betik ikonlar.py'den
static/synapse_ikon.js'i üretir — simge değişince betik yeniden çalıştırılır,
test_ikon_js.py iki dosyanın eşit olduğunu doğrular.

Çalıştır:  python merkez/ikon_js_uret.py
"""
import json
import os
import re
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import ikonlar  # noqa: E402

HEDEF = os.path.join(BURASI, "..", "hvac", "deneme", "static", "synapse_ikon.js")


def uret() -> str:
    css = re.search(r"<style>(.*?)</style>", ikonlar.CSS, re.S).group(1).strip()
    veri = {
        "surum": ikonlar.SURUM,
        "svg": ikonlar._SVG,
        "renk": ikonlar.RENK,
        "takma": ikonlar._TAKMA,
        "css": css,
    }
    return (
        "/* OTOMATİK ÜRETİLDİ — elle düzenleme. Kaynak: merkez/ikonlar.py\n"
        "   Yeniden üret: python merkez/ikon_js_uret.py */\n"
        "window.SYNAPSE_IKON = " + json.dumps(veri, ensure_ascii=False) + ";\n"
    )


if __name__ == "__main__":
    yol = os.path.normpath(HEDEF)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(uret())
    print("yazıldı:", yol)
