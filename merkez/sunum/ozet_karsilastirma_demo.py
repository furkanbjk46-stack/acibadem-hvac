# -*- coding: utf-8 -*-
"""
GLOBAL ÖZET — LOKASYON KARŞILAŞTIRMA (SUNUM / DEMO SÜRÜMÜ)
==========================================================

YALNIZCA SUNUM MODUNDA (SYNAPSE_DEMO) çalışır; app_merkez.py demo modunda bu
dosyayı, gerçek portalda ozet_karsilastirma.py'yi çalıştırır. Canlı Synapse
bu dosyadan ETKİLENMEZ.

Gerçek sürüme göre eklenenler (Gemini revizyon önerisinden, VERİYE DAYALI
kısımları):
  * Hedef eşiği kartı, eşik çizgisi ve tablo "Durum" sütunu
    (eşikler ayarlar.hedef_esikleri'nden)
  * Çubuğa ya da tablo satırına tıklayınca LOKASYON DETAY penceresi:
      - dönem tüketimi, gösterge, alan
      - sistem bazlı dağılım: chiller'lar (tek tek), soğutma kuleleri,
        MCC panoları, VRF, ölçülmeyen kalan — GERÇEK sayaç kolonlarından
      - şebeke / kojen kaynağı
      - veriye dayalı teşhis maddeleri
      - bağlantı, oto-set, arıza/bakım durumu
      - "Lokasyon detayına git" ve "Rapor oluştur"
Gemini önerisindeki ölçülmeyen kalemler (aydınlatma, medikal/UPS, COP,
OSOS/BEDAŞ) bilerek EKLENMEDİ — sayaç olmadan göstermek uydurma olurdu.

Hesaplar karsilastirma_hesap.py'dedir (test edilebilir).
"""

import json as _json
import os as _os
import sys as _sys
import pandas as _pd

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import karsilastirma_hesap as _KH          # hesaplar
import karsilastirma_panel as _KP          # detay penceresi arayuzu (canli ile ORTAK)

# ── Metrik tanımları — ozet_karsilastirma.py ile AYNI olmalı ──────────────
# (test_ozet_karsilastirma.py iki dosyanın eşitliğini doğrular)
METRIKLER = {
    "enerji": {
        "ad": "TOPLAM ENERJİ", "ikon": "⚡",
        "kolonlar": ["Toplam_Hastane_Tuketim_kWh"],
        "birim": "kWh", "renk": "#38bdf8",
        "artis_iyi": False, "ikinci": "yogunluk",
    },
    "dogalgaz": {
        "ad": "DOĞALGAZ", "ikon": "🔥",
        "kolonlar": ["Kazan_Dogalgaz_m3", "Kojen_Dogalgaz_m3"],
        "birim": "m³", "renk": "#f97316",
        "artis_iyi": False, "ikinci": "yogunluk",
        "kirilim": [("Kazan (ısıtma)", ["Kazan_Dogalgaz_m3"], "#ef4444"),
                    ("Kojen (elektrik)", ["Kojen_Dogalgaz_m3"], "#10b981")],
        "ik_kolonlar": ["Kazan_Dogalgaz_m3"],
        "ik_birim": "m³/m²/gün (kazan)", "ik_sutun": "KAZAN m³/M²/GÜN",
    },
    "sogutma": {
        "ad": "SOĞUTMA", "ikon": "❄️",
        "kolonlar": ["Toplam_Sogutma_Tuketim_kWh"],
        "birim": "kWh", "renk": "#06b6d4",
        "artis_iyi": False, "ikinci": "oran",
        "oran_ad": "Soğutmanın toplam tüketimdeki payı",
        "ik_sutun": "SOĞUTMA PAYI",
    },
    "su": {
        "ad": "SU", "ikon": "💧",
        "kolonlar": ["Su_Tuketimi_m3"],
        "birim": "m³", "renk": "#38bdf8",
        "artis_iyi": False, "ikinci": "yogunluk",
        "ik_carpan": 1000, "ik_birim": "L/m²/gün", "ik_sutun": "L/M²/GÜN",
    },
    "kojen": {
        "ad": "KOJEN ÜRETİM", "ikon": "⚙️",
        "kolonlar": ["Kojen_Uretim_kWh"],
        "birim": "kWh", "renk": "#10b981",
        "artis_iyi": True, "ikinci": "oran",
        "oran_ad": "Kojen karşılama oranı (üretim / tüketim)",
        "ik_sutun": "KARŞILAMA",
    },
}
ORAN_PAYDA = "Toplam_Hastane_Tuketim_kWh"

_metrik_key = st.session_state.get("detay_ozet", "enerji")
_M = METRIKLER.get(_metrik_key, METRIKLER["enerji"])

# ── Geri ──────────────────────────────────────────────────────────────────
if st.button("⬅ Geri", key="ozet_karsilastirma_geri"):
    st.session_state.pop("detay_ozet", None)
    st.rerun()

st.markdown(
    f"<div style='text-align:center;margin:2px 0 14px;'>"
    f"<div style='font-size:9px;color:rgba(120,170,220,0.55);letter-spacing:5px;"
    f"text-transform:uppercase;'>ACIBADEM SAĞLIK GRUBU — LOKASYON KARŞILAŞTIRMA</div>"
    f"<div style='font-family:Playfair Display,serif;font-size:30px;font-weight:600;"
    f"color:#f8fafc;margin-top:4px;'>{_M['ikon']} {_M['ad']}</div>"
    f"<div style='font-size:10px;color:rgba(120,170,220,0.45);margin-top:2px;'>"
    f"Detay için çubuğa ya da tablo satırına tıklayın</div></div>",
    unsafe_allow_html=True)

# ── Veri ──────────────────────────────────────────────────────────────────
_df, _hata = fetch_energy(url, key)
if _hata or _df is None or _df.empty:
    st.warning("Karşılaştırma için veri bulunamadı.")
    st.stop()

_df = _df.copy()
_df["Tarih"] = _pd.to_datetime(_df["Tarih"], errors="coerce")
_df = _df.dropna(subset=["Tarih"])

_bugun = _pd.Timestamp(now_display.date()) if "now_display" in dir() else _pd.Timestamp.today().normalize()


@st.cache_data(ttl=120, show_spinner=False)
def _hedef_esikleri_oku(_url, _key):
    try:
        from supabase import create_client
        r = create_client(_url, _key).table("ayarlar").select("value") \
            .eq("key", "hedef_esikleri").execute()
        return _json.loads(r.data[0]["value"]) if r.data else {}
    except Exception:
        return {}


_ESIK = _hedef_esikleri_oku(url, key).get(_metrik_key)

# ── Dönem seçimi ──────────────────────────────────────────────────────────
_DONEMLER = ["Bu ay", "Geçen ay", "Son 12 ay", "Bu yıl"]
_secim = st.radio("Dönem", _DONEMLER, horizontal=True,
                  label_visibility="collapsed", key="ozet_donem")


def _aralik(secim):
    ay_bas = _bugun.replace(day=1)
    if secim == "Bu ay":
        bas, bit = ay_bas, _bugun
        o_bas = (ay_bas - _pd.Timedelta(days=1)).replace(day=1)
        o_bit = min(o_bas + (_bugun - ay_bas), ay_bas - _pd.Timedelta(days=1))
    elif secim == "Geçen ay":
        bit = ay_bas - _pd.Timedelta(days=1)
        bas = bit.replace(day=1)
        o_bit = bas - _pd.Timedelta(days=1)
        o_bas = o_bit.replace(day=1)
    elif secim == "Son 12 ay":
        bas, bit = _bugun - _pd.Timedelta(days=365), _bugun
        o_bit = bas - _pd.Timedelta(days=1)
        o_bas = o_bit - _pd.Timedelta(days=365)
    else:
        bas, bit = _bugun.replace(month=1, day=1), _bugun
        o_bas = bas.replace(year=bas.year - 1)
        o_bit = o_bas + (bit - bas)
    return bas, bit, o_bas, o_bit


_bas, _bit, _o_bas, _o_bit = _aralik(_secim)
_BEKLENEN_GUN = int((_bit - _bas).days) + 1


def _topla(df, bas, bit, kolonlar):
    d = df[(df["Tarih"] >= bas) & (df["Tarih"] <= bit)]
    if d.empty:
        return {}, {}
    kolonlar = [c for c in kolonlar if c in d.columns]
    if not kolonlar:
        return {}, {}
    d = d.copy()
    d["_deger"] = d[kolonlar].sum(axis=1)
    return (d.groupby("lokasyon_id")["_deger"].sum().to_dict(),
            d.groupby("lokasyon_id")["Tarih"].nunique().to_dict())


_su, _su_gun = _topla(_df, _bas, _bit, _M["kolonlar"])
_onceki, _ = _topla(_df, _o_bas, _o_bit, _M["kolonlar"])
_payda, _ = _topla(_df, _bas, _bit, [ORAN_PAYDA]) \
    if _M.get("ikinci") == "oran" else ({}, {})
_IK_KOLONLAR = _M.get("ik_kolonlar")
_ik_kaynak = _topla(_df, _bas, _bit, _IK_KOLONLAR)[0] if _IK_KOLONLAR else _su
_KIRILIM = _M.get("kirilim") or []
_kirilim_veri = {ad: _topla(_df, _bas, _bit, kols)[0] for ad, kols, _r in _KIRILIM}

if not _su:
    st.warning(f"{_secim} için veri yok.")
    st.stop()

_ORAN = _M.get("ikinci") == "oran"
_DUSUK_IYI = not _M["artis_iyi"]
_donem_df = _df[(_df["Tarih"] >= _bas) & (_df["Tarih"] <= _bit)]

_satirlar = []
for _lid, _deger in _su.items():
    _bilgi = HASTANELER.get(_lid, {})
    _m2 = _bilgi.get("m2") or 0
    _gun = _su_gun.get(_lid, 0) or 1
    _onc = _onceki.get(_lid, 0)
    _ik_deger = _ik_kaynak.get(_lid, 0)
    if _deger <= 0 or _ik_deger <= 0:
        _ikinci = None
    elif _ORAN:
        _pyd = _payda.get(_lid, 0)
        _ikinci = (_ik_deger / _pyd * 100) if _pyd else None
    else:
        _ikinci = (_ik_deger / _m2 / _gun * _M.get("ik_carpan", 1)) if (_m2 and _gun) else None
    _yuk = None
    if "Chiller_Load_Percent" in _donem_df.columns:
        _y = _pd.to_numeric(_donem_df.loc[_donem_df["lokasyon_id"] == _lid,
                                          "Chiller_Load_Percent"], errors="coerce").dropna()
        _yuk = float(_y.mean()) if not _y.empty else None
    _satirlar.append({
        "id": _lid, "ad": _bilgi.get("kisa", _lid), "isim": _bilgi.get("isim", _lid),
        "renk": _bilgi.get("renk", _M["renk"]),
        "deger": _deger, "m2": _m2, "gun": _gun, "ikinci": _ikinci,
        "onceki": _onc, "degisim": ((_deger - _onc) / _onc * 100) if _onc else None,
        "kirilim": {_ad: _kirilim_veri[_ad].get(_lid, 0) for _ad, _k, _r in _KIRILIM},
        "ort_chiller_yuk": _yuk,
    })

_IK_BIRIM = "%" if _ORAN else _M.get("ik_birim", f"{_M['birim']}/m²/gün")
_IK_BASLIK = (_M.get("oran_ad", "Oran") if _ORAN else f"Verimlilik ({_IK_BIRIM})")
_IK_BASLIK += " — yüksek olan iyi" if not _DUSUK_IYI else " — düşük olan iyi"


def _ondalik_sec(degerler):
    d = [abs(v) for v in degerler if v]
    if not d:
        return 2
    ort = sum(d) / len(d)
    return 0 if ort >= 100 else 1 if ort >= 10 else 2 if ort >= 1 else 3 if ort >= 0.1 else 4


_IK_OND = 1 if _ORAN else _ondalik_sec([r["ikinci"] for r in _satirlar])


def _ik_metin(v):
    if v is None:
        return "—"
    return f"%{v:.1f}" if _ORAN else f"{v:.{_IK_OND}f}"


_satirlar.sort(key=lambda r: r["deger"], reverse=True)
_toplam = sum(r["deger"] for r in _satirlar)
for _r in _satirlar:
    _r["kotu"], _r["durum"] = _KH.esik_durumu(_r["ikinci"], _ESIK, _M["artis_iyi"])


_tr = _KP.tr


# ── Üst şerit ─────────────────────────────────────────────────────────────
_yog = [r for r in _satirlar if r["ikinci"] is not None]
_dusuk = min(_yog, key=lambda r: r["ikinci"]) if _yog else None
_yuksek = max(_yog, key=lambda r: r["ikinci"]) if _yog else None
_en_iyi = _dusuk if _DUSUK_IYI else _yuksek
_en_kotu = _yuksek if _DUSUK_IYI else _dusuk
_ort_ikinci = (sum(r["ikinci"] for r in _yog) / len(_yog)) if _yog else None
_esik_disi = sum(1 for r in _satirlar if r["kotu"])


_kutu = _KP.kutu


_veri_olan = len(_yog)
_alt_metin = f"{len(_satirlar)} lokasyon · {_secim.lower()}"
if _veri_olan < len(_satirlar):
    _alt_metin = f"{_veri_olan}/{len(_satirlar)} lokasyonda veri · {_secim.lower()}"

_kutular = _kutu("Σ", "TOPLAM", f"{_tr(_toplam)} {_M['birim']}", _alt_metin)
if _ort_ikinci is not None:
    _kutular += _kutu("⌀", "ORTALAMA", _ik_metin(_ort_ikinci), _IK_BIRIM)
if _en_kotu:
    _kutular += _kutu("⚠️", "EN ZAYIF", _ik_metin(_en_kotu["ikinci"]),
                      f"{_en_kotu['ad']} · {_IK_BIRIM}", "#f59e0b")
if _ESIK is not None:
    _kutular += _kutu("🎯", "HEDEF", ("≥ " if _M["artis_iyi"] else "≤ ") + _ik_metin(_ESIK),
                      f"{_esik_disi} lokasyon hedef dışı",
                      "#ef4444" if _esik_disi else "#10b981")
elif _en_iyi:
    _kutular += _kutu("🏆", "EN İYİ", _ik_metin(_en_iyi["ikinci"]),
                      f"{_en_iyi['ad']} · {_IK_BIRIM}", "#10b981")

st.markdown(f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;'>"
            f"{_kutular}</div>", unsafe_allow_html=True)

# ── Tıklama → detay penceresi ─────────────────────────────────────────────
_AD2ID = {r["ad"]: r["id"] for r in _satirlar}


def _yeni_secim(kaynak, lid):
    return _KP.yeni_secim(st, kaynak, lid)


def _grafik_secimi(olay):
    return _KP.grafik_secimi(olay, _AD2ID)


_acilacak = None


def _bar(baslik, veriler, etiketler, renkler, metin, eksen_basligi, esik=None):
    f = go.Figure(go.Bar(
        x=veriler, y=etiketler, orientation="h",
        marker=dict(color=renkler, line=dict(width=0)),
        text=metin, textposition="outside",
        textfont=dict(size=10, color="rgba(200,230,255,0.75)"),
        hovertemplate="%{y}: %{x:,.4g} — detay için tıklayın<extra></extra>",
    ))
    if esik is not None:
        f.add_vline(x=esik, line_width=1.5, line_dash="dash", line_color="#ef4444",
                    annotation_text="hedef", annotation_position="top",
                    annotation_font=dict(size=9, color="#ef4444"))
    f.update_layout(
        title=dict(text=baslik, font=dict(size=12, color="rgba(150,210,255,0.75)")),
        height=max(320, 22 * len(etiketler) + 90),
        margin=dict(l=8, r=60, t=40, b=30),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(200,230,255,0.7)", size=10),
        xaxis=dict(title=eksen_basligi, gridcolor="rgba(56,189,248,0.08)",
                   zerolinecolor="rgba(56,189,248,0.15)"),
        yaxis=dict(autorange="reversed"),
        showlegend=False, clickmode="event+select",
    )
    return f


_sol, _sag = st.columns(2)
with _sol:
    if _KIRILIM:
        _f = go.Figure()
        for _ad, _k, _rnk in _KIRILIM:
            _f.add_trace(go.Bar(
                x=[r["kirilim"].get(_ad, 0) for r in _satirlar],
                y=[r["ad"] for r in _satirlar],
                name=_ad, orientation="h",
                marker=dict(color=_rnk, line=dict(width=0)),
                hovertemplate="%{y} · " + _ad + ": %{x:,.0f} — detay için tıklayın<extra></extra>",
            ))
        _f.update_layout(
            barmode="stack",
            title=dict(text=f"Toplam tüketim ({_M['birim']}) — kırılım",
                       font=dict(size=12, color="rgba(150,210,255,0.75)")),
            height=max(320, 22 * len(_satirlar) + 110),
            margin=dict(l=8, r=30, t=40, b=30),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="rgba(200,230,255,0.7)", size=10),
            xaxis=dict(title=_M["birim"], gridcolor="rgba(56,189,248,0.08)"),
            yaxis=dict(autorange="reversed"),
            legend=dict(orientation="h", y=1.06, x=0, font=dict(size=9), bgcolor="rgba(0,0,0,0)"),
            clickmode="event+select",
        )
        _olay = st.plotly_chart(_f, use_container_width=True, key=f"ozet_demo_bar1_{_metrik_key}",
                                on_select="rerun", selection_mode="points")
    else:
        _olay = st.plotly_chart(
            _bar(f"Toplam tüketim ({_M['birim']})",
                 [r["deger"] for r in _satirlar], [r["ad"] for r in _satirlar],
                 [r["renk"] for r in _satirlar], [_tr(r["deger"]) for r in _satirlar],
                 _M["birim"]),
            use_container_width=True, key=f"ozet_demo_bar1_{_metrik_key}",
            on_select="rerun", selection_mode="points")
    _acilacak = _yeni_secim("bar1", _grafik_secimi(_olay)) or _acilacak

with _sag:
    if _yog:
        _ys = sorted(_yog, key=lambda r: r["ikinci"], reverse=not _DUSUK_IYI)
        _renkler = []
        for r in _ys:
            if r["kotu"] is not None:
                _renkler.append("#f97316" if r["kotu"] else "#10b981")
            else:
                _iyi = (r["ikinci"] <= (_ort_ikinci or 0)) if _DUSUK_IYI \
                    else (r["ikinci"] >= (_ort_ikinci or 0))
                _renkler.append("#10b981" if _iyi else "#f59e0b")
        _olay2 = st.plotly_chart(
            _bar(_IK_BASLIK, [r["ikinci"] for r in _ys], [r["ad"] for r in _ys],
                 _renkler, [_ik_metin(r["ikinci"]) for r in _ys], _IK_BIRIM, esik=_ESIK),
            use_container_width=True, key=f"ozet_demo_bar2_{_metrik_key}",
            on_select="rerun", selection_mode="points")
        _acilacak = _yeni_secim("bar2", _grafik_secimi(_olay2)) or _acilacak
    else:
        st.info("Karşılaştırma için yeterli veri yok.")

# ── Tablo (satıra tıklanabilir) ───────────────────────────────────────────
st.markdown("<div style='font-size:10px;letter-spacing:2px;"
            "color:rgba(56,189,248,0.6);margin:6px 0 4px;'>DETAY TABLOSU "
            "<span style='letter-spacing:0;color:rgba(120,170,220,0.45);'>— satıra tıklayın</span></div>",
            unsafe_allow_html=True)

_tablo = []
for _i, _r in enumerate(_satirlar, 1):
    _satir = {"#": _i, "Lokasyon": _r["ad"], _M["birim"]: _tr(_r["deger"])}
    for _ad, _k, _rnk in _KIRILIM:
        _satir[_ad.split(" ")[0]] = _tr(_r["kirilim"].get(_ad, 0))
    _satir["Pay"] = f"%{(_r['deger'] / _toplam * 100) if _toplam else 0:.1f}"
    _satir[_M.get("ik_sutun") or (_M["birim"] + "/m²/gün")] = _ik_metin(_r["ikinci"])
    _satir["Durum"] = _r["durum"]
    _satir["Önceki döneme"] = ("—" if _r["degisim"] is None else
                               f"{'▼' if _r['degisim'] <= 0 else '▲'}%{abs(_r['degisim']):.1f}")
    _satir["m²"] = _tr(_r["m2"])
    _tablo.append(_satir)
_tablo_df = _pd.DataFrame(_tablo)


try:
    _stil = _tablo_df.style.map(_KP.durum_stil, subset=["Durum"])
except AttributeError:                       # eski pandas
    _stil = _tablo_df.style.applymap(_KP.durum_stil, subset=["Durum"])

_olay3 = st.dataframe(_stil, hide_index=True, use_container_width=True,
                      key=f"ozet_demo_tablo_{_metrik_key}",
                      on_select="rerun", selection_mode="single-row")
_acilacak = _yeni_secim("tablo", _KP.tablo_secimi(_olay3, _satirlar)) or _acilacak

st.caption(f"Dönem: {_bas.strftime('%d.%m.%Y')} → {_bit.strftime('%d.%m.%Y')} "
           f"· Kıyas: {_o_bas.strftime('%d.%m.%Y')} → {_o_bit.strftime('%d.%m.%Y')}"
           + (f" · Hedef eşiği: {('≥ ' if _M['artis_iyi'] else '≤ ')}{_ik_metin(_ESIK)} {_IK_BIRIM}"
              if _ESIK is not None else ""))

# ── Grup bağlamı (teşhis için) ────────────────────────────────────────────
_sog_paylari = []
for _lid in _su:
    _d = _donem_df[_donem_df["lokasyon_id"] == _lid]
    _t = _pd.to_numeric(_d.get("Toplam_Hastane_Tuketim_kWh"), errors="coerce").sum() if not _d.empty else 0
    if _t:
        _s = sum(_pd.to_numeric(_d[c], errors="coerce").sum()
                 for c in _d.columns if c in ("Chiller_Tuketim_kWh", "VRF_Split_Tuketim_kWh")
                 or c.startswith("Kule"))
        _sog_paylari.append(_s / _t * 100)
_GRUP = {"ort_ikinci": _ort_ikinci,
         "ort_sogutma_payi": (sum(_sog_paylari) / len(_sog_paylari)) if _sog_paylari else None}


# ── Detay penceresi (gövdesi karsilastirma_panel.py'de — canlı ile ORTAK) ──
@st.dialog("Lokasyon detayı", width="large")
def _panel(lid):
    r = next((x for x in _satirlar if x["id"] == lid), None)
    if r is None:
        st.write("Lokasyon bulunamadı.")
        return
    dag = _KH.sistem_dagilimi(_donem_df[_donem_df["lokasyon_id"] == lid].to_dict("records"))
    try:
        _lok_kaydi = next((l for l in (fetch_lokasyonlar(url, key) or [])
                           if l.get("lokasyon_id") == lid), {})
    except Exception:
        _lok_kaydi = {}
    _KP.panel_govde(st, r, dag, _KH.lokasyon_durumu(_lok_kaydi), {
        "M": _M, "secim": _secim, "bas": _bas, "bit": _bit,
        "ik_metin": _ik_metin, "ik_birim": _IK_BIRIM, "esik": _ESIK,
        "oran": _ORAN, "ik_ond": _IK_OND, "beklenen_gun": _BEKLENEN_GUN,
        "grup": _GRUP, "teshis": _KH.teshis, "anahtar": "ozet_panel",
    })


if _acilacak:
    _panel(_acilacak)
