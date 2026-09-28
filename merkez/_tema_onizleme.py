# -*- coding: utf-8 -*-
"""
TEMA ÖNİZLEME — yalnızca geliştirme makinesinde.

Sunum (demo) uygulamasını örnek veriyle ve geçici bir test girişiyle açar;
tema değişikliklerini canlı Supabase'e dokunmadan görmek içindir.
Sahaya ya da Streamlit Cloud'a KURULMAZ.

Çalıştırma: streamlit run merkez/_tema_onizleme.py
Giriş: tema / tema
"""
import os

os.environ["SYNAPSE_DEMO"] = "1"
os.environ["SYNAPSE_GIRIS_KULLANICI"] = "tema"

import giris  # noqa: E402  (ortam değişkenleri önce kurulmalı)

os.environ["SYNAPSE_GIRIS_PAROLA_HASH"] = giris.parola_hash_uret("tema")

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "app_merkez.py"), encoding="utf-8") as _f:
    _kaynak = _f.read()
exec(compile(_kaynak, "app_merkez.py", "exec"))
