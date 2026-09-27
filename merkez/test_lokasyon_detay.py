# -*- coding: utf-8 -*-
"""Lokasyon detay sayfasi — grafik secenekleri (ag baglantisi YOK).

Sayfa app_merkez'in globals()'i icinde exec edildigi icin butun olarak
calistirilamaz; bu yuzden secenek kurallari burada birebir kurulup
simulasyon verisiyle dogrulanir, sayfa metni de kontrol edilir.
"""
import ast
import os
import re
import sys

import pandas as pd

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BURASI = os.path.join(KOK, "merkez")
SAYFA = os.path.join(BURASI, "pages", "lokasyon_detay.py")
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


_metin = open(SAYFA, encoding="utf-8").read()
try:
    ast.parse(_metin)
    c("sayfa sozdizimi gecerli", True)
except SyntaxError as e:
    c("sayfa sozdizimi gecerli", False, str(e))

# ── Grafik listesinde trafo secenegi ──────────────────────────────────────
c("trafo secenegi listede", '"🔻 Trafolar (TRDP)"' in _metin)
c("trafo grafigi cizim dali var", 'grafik_tip == "trafo"' in _metin)
c("secenek KOSULA bagli (trafosuz lokasyonda olu link olmasin)",
  "if _trafo_kolonlar:" in _metin)
c("lokasyon degisince eski secim temizlenir (Streamlit hatasi)",
  'st.session_state.get("grafik_sec") not in grafik_secenekler' in _metin)
c("trafolar yiginli cizilir (gunluk toplam okunur kalsin)",
  'barmode="stack"' in _metin.split('grafik_tip == "trafo"')[1][:2000])
c("eksik sayac kullaniciya soylenir",
  "henüz bağlı değil" in _metin.split('grafik_tip == "trafo"')[1][:2500])


# ── Secenek kurali: SAYFADAKI ile ayni ────────────────────────────────────
def trafo_kolonlari(df):
    return sorted([c_ for c_ in df.columns if re.fullmatch(r"TRDP\d+_kWh", str(c_))
                   and pd.to_numeric(df[c_], errors="coerce").fillna(0).sum() > 0],
                  key=lambda c_: int(re.findall(r"\d+", c_)[0]))


c("kolonu olmayan lokasyonda secenek YOK",
  trafo_kolonlari(pd.DataFrame([{"Sebeke_Tuketim_kWh": 100}])) == [])
c("kolon var ama sayac bos ise secenek YOK",
  trafo_kolonlari(pd.DataFrame([{"TRDP1_kWh": 0, "TRDP2_kWh": None}])) == [])
c("dolu trafolar numara sirasinda",
  trafo_kolonlari(pd.DataFrame([{"TRDP10_kWh": 5, "TRDP2_kWh": 3, "TRDP1_kWh": 1}]))
  == ["TRDP1_kWh", "TRDP2_kWh", "TRDP10_kWh"])
c("bagli olmayan trafo (bos kolon) listeye girmez",
  trafo_kolonlari(pd.DataFrame([{"TRDP1_kWh": 5, "TRDP2_kWh": 0}])) == ["TRDP1_kWh"])

# ── Simulasyon: her lokasyonda secenek cikmali (sunum icin) ───────────────
import _sim_sunucu as S

_df = pd.DataFrame(S.veri_uret()["energy_data"])
_lokler = sorted(_df["lokasyon_id"].unique())
_adet = {l: len(trafo_kolonlari(_df[_df["lokasyon_id"] == l])) for l in _lokler}
c("simulasyonda her lokasyonda trafo grafigi acilir",
  all(v >= 2 for v in _adet.values()), {k: v for k, v in _adet.items() if v < 2})
c("simulasyonda trafo adedi lokasyona gore degisir",
  len(set(_adet.values())) > 1, sorted(set(_adet.values())))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
