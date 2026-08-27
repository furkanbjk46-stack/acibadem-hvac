# -*- coding: utf-8 -*-
"""
SYNAPSE — SUNUM (DEMO) UYGULAMASI
=================================

Bu dosya ayrı bir kod değildir; gerçek portalı (app_merkez.py) SUNUM MODUNDA
çalıştıran ince bir sarmalayıcıdır. Portal, canlı Supabase yerine kendi
ürettiği örnek veriyi kullanır.

NEDEN AYRI DOSYA:
Streamlit Cloud aynı depo + branch + giriş dosyası kombinasyonuyla ikinci bir
uygulama açtırmıyor. Demo'yu ayrı bir adreste yayınlayabilmek için farklı bir
giriş dosyası gerekiyor.

KURULUM (Streamlit Cloud):
    Repository : furkanbjk46-stack/acibadem-hvac
    Branch     : main
    Main file  : merkez/app_demo.py        <-- tek fark bu
    App URL    : acibadem-synapse-demo
    Secrets    : GEREKMEZ

GİRİŞ: acibadem / sunum2026

GÜVENLİK NOTU:
Demo girişi bilerek buraya yazılmıştır; arkasında yalnızca sentetik veri vardır,
canlı sisteme bağlantı YOKTUR (Supabase adresi hiç tanımlanmaz). Yine de farklı
bir parola istenirse Streamlit secrets'a [giris] bölümü eklenmesi yeterlidir;
secrets varsa buradaki değerler kullanılmaz.
"""

import os
import runpy
import sys

_DIZIN = os.path.dirname(os.path.abspath(__file__))

# Sunum modu: portal örnek veri sunucusunu kendi içinde başlatır.
os.environ["SYNAPSE_DEMO"] = "1"

# Demo girişi (secrets tanımlıysa secrets önceliklidir — bkz. giris._ayarlar)
os.environ.setdefault("SYNAPSE_GIRIS_KULLANICI", "acibadem")
os.environ.setdefault(
    "SYNAPSE_GIRIS_PAROLA_HASH",
    "pbkdf2_sha256$200000$e107cd6db1fd1bfa079dbe8784e9d46b$"
    "c2e2fb7dbfc9617b2bb1527d6633af85ce50326adc176048872c74a61c046dc7",
)

if _DIZIN not in sys.path:
    sys.path.insert(0, _DIZIN)

# run_path kullanılır: app_merkez içindeki __file__ doğru klasörü gösterir,
# böylece configs/ ve pages/ yolları bozulmaz.
runpy.run_path(os.path.join(_DIZIN, "app_merkez.py"), run_name="__main__")
