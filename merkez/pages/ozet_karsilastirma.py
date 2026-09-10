# -*- coding: utf-8 -*-
"""
GLOBAL ÖZET — LOKASYON KARŞILAŞTIRMA
====================================

Global Özet'teki bir metriğe tıklandığında açılır ve o metriği TÜM
lokasyonlar için yan yana koyar.

NASIL ÇALIŞIR: app_merkez.py bu dosyayı `exec` ile KENDİ globals()'ı içinde
çalıştırır (lokasyon_detay.py ile aynı desen). Dolayısıyla st, pd, go,
HASTANELER, fetch_energy, url, key buradan doğrudan kullanılabilir ve
sayfa yeniden yüklenmez — oturum korunur.

ŞU AN YALNIZCA "Toplam Enerji" metriği bağlıdır (deneme). Diğer dört metrik
METRIKLER sözlüğüne eklenerek aynı sayfayı kullanabilir.
"""

import pandas as _pd

# ── Hangi metrik? ─────────────────────────────────────────────────────────
# kolonlar: birden fazlaysa toplanır (ör. doğalgaz = kazan + kojen)
METRIKLER = {
    "enerji": {
        "ad": "TOPLAM ENERJİ", "ikon": "⚡",
        "kolonlar": ["Toplam_Hastane_Tuketim_kWh"],
        "birim": "kWh", "renk": "#38bdf8",
        "yogunluk": True,          # kWh/m² anlamlı mı
        "artis_iyi": False,        # tüketimde artış kötüdür
    },
}

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
    f"color:#f8fafc;margin-top:4px;'>{_M['ikon']} {_M['ad']}</div></div>",
    unsafe_allow_html=True)

# ── Veri ──────────────────────────────────────────────────────────────────
# fetch_energy @st.cache_data ile önbellekli — ana sayfa zaten çektiyse
# yeniden indirilmez.
_df, _hata = fetch_energy(url, key)
if _hata or _df is None or _df.empty:
    st.warning("Karşılaştırma için veri bulunamadı.")
    st.stop()

_df = _df.copy()
_df["Tarih"] = _pd.to_datetime(_df["Tarih"], errors="coerce")
_df = _df.dropna(subset=["Tarih"])

_bugun = _pd.Timestamp(now_display.date()) if "now_display" in dir() else _pd.Timestamp.today().normalize()

# ── Dönem seçimi ──────────────────────────────────────────────────────────
_DONEMLER = ["Bu ay", "Geçen ay", "Son 12 ay", "Bu yıl"]
_secim = st.radio("Dönem", _DONEMLER, horizontal=True,
                  label_visibility="collapsed", key="ozet_donem")


def _aralik(secim):
    """(baslangic, bitis, onceki_baslangic, onceki_bitis) — kıyas için."""
    ay_bas = _bugun.replace(day=1)
    if secim == "Bu ay":
        bas, bit = ay_bas, _bugun
        # Kıyas: geçen ayın AYNI GÜN aralığı (kısmi ayı tam ayla kıyaslamamak için)
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
    else:  # Bu yıl
        bas, bit = _bugun.replace(month=1, day=1), _bugun
        o_bas = bas.replace(year=bas.year - 1)
        o_bit = o_bas + (bit - bas)
    return bas, bit, o_bas, o_bit


_bas, _bit, _o_bas, _o_bit = _aralik(_secim)


def _topla(df, bas, bit):
    """Lokasyon başına metrik toplamı ve veri günü sayısı."""
    d = df[(df["Tarih"] >= bas) & (df["Tarih"] <= bit)]
    if d.empty:
        return {}, {}
    kolonlar = [c for c in _M["kolonlar"] if c in d.columns]
    if not kolonlar:
        return {}, {}
    d = d.copy()
    d["_deger"] = d[kolonlar].sum(axis=1)
    toplam = d.groupby("lokasyon_id")["_deger"].sum().to_dict()
    gun = d.groupby("lokasyon_id")["Tarih"].nunique().to_dict()
    return toplam, gun


_su, _su_gun = _topla(_df, _bas, _bit)
_onceki, _ = _topla(_df, _o_bas, _o_bit)

if not _su:
    st.warning(f"{_secim} için veri yok.")
    st.stop()

# ── Satırları kur ─────────────────────────────────────────────────────────
_satirlar = []
for _lid, _deger in _su.items():
    _bilgi = HASTANELER.get(_lid, {})
    _m2 = _bilgi.get("m2") or 0
    _gun = _su_gun.get(_lid, 0) or 1
    _onc = _onceki.get(_lid, 0)
    _satirlar.append({
        "id": _lid,
        "ad": _bilgi.get("kisa", _lid),
        "renk": _bilgi.get("renk", _M["renk"]),
        "deger": _deger,
        "m2": _m2,
        "gun": _gun,
        "yogunluk": (_deger / _m2 / _gun) if (_m2 and _gun) else None,
        "onceki": _onc,
        "degisim": ((_deger - _onc) / _onc * 100) if _onc else None,
    })

_satirlar.sort(key=lambda r: r["deger"], reverse=True)
_toplam = sum(r["deger"] for r in _satirlar)


def _tr(sayi, ondalik=0):
    fmt = f"{sayi:,.{ondalik}f}"
    if ondalik > 0:
        tam, _, kusur = fmt.partition(".")
        return tam.replace(",", ".") + "," + kusur
    return fmt.replace(",", ".")


# ── Üst şerit: özet göstergeler ───────────────────────────────────────────
_yog = [r for r in _satirlar if r["yogunluk"] is not None]
_en_verimli   = min(_yog, key=lambda r: r["yogunluk"]) if _yog else None
_en_verimsiz  = max(_yog, key=lambda r: r["yogunluk"]) if _yog else None
_ort_yogunluk = (sum(r["yogunluk"] for r in _yog) / len(_yog)) if _yog else None


def _kutu(ikon, baslik, deger, alt, renk="#38bdf8"):
    return (
        f"<div style='flex:1;min-width:120px;background:rgba(0,20,50,0.6);"
        f"border:1px solid rgba(56,189,248,0.12);border-radius:10px;padding:10px 12px;'>"
        f"<div style='font-size:9px;color:rgba(150,210,255,0.55);letter-spacing:1px;'>"
        f"{ikon} {baslik}</div>"
        f"<div style='font-family:Playfair Display,serif;font-size:20px;font-weight:700;"
        f"color:{renk};margin-top:2px;'>{deger}</div>"
        f"<div style='font-size:9px;color:rgba(120,170,220,0.5);'>{alt}</div></div>"
    )


_kutular = _kutu("Σ", "TOPLAM", f"{_tr(_toplam)} {_M['birim']}",
                 f"{len(_satirlar)} lokasyon · {_secim.lower()}")
if _en_verimli:
    _kutular += _kutu("🏆", "EN VERİMLİ", f"{_en_verimli['yogunluk']:.2f}",
                      f"{_en_verimli['ad']} · {_M['birim']}/m²/gün", "#10b981")
if _en_verimsiz:
    _kutular += _kutu("⚠️", "EN YÜKSEK", f"{_en_verimsiz['yogunluk']:.2f}",
                      f"{_en_verimsiz['ad']} · {_M['birim']}/m²/gün", "#f59e0b")
if _ort_yogunluk:
    _kutular += _kutu("⌀", "ORTALAMA", f"{_ort_yogunluk:.2f}",
                      f"{_M['birim']}/m²/gün")

st.markdown(f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;'>"
            f"{_kutular}</div>", unsafe_allow_html=True)

# ── Grafikler ─────────────────────────────────────────────────────────────
_sol, _sag = st.columns(2)


def _bar(baslik, veriler, etiketler, renkler, metin, eksen_basligi):
    f = go.Figure(go.Bar(
        x=veriler, y=etiketler, orientation="h",
        marker=dict(color=renkler, line=dict(width=0)),
        text=metin, textposition="outside",
        textfont=dict(size=10, color="rgba(200,230,255,0.75)"),
        hovertemplate="%{y}: %{x:,.0f}<extra></extra>",
    ))
    f.update_layout(
        title=dict(text=baslik, font=dict(size=12, color="rgba(150,210,255,0.75)")),
        height=max(320, 22 * len(etiketler) + 90),
        margin=dict(l=8, r=60, t=40, b=30),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(200,230,255,0.7)", size=10),
        xaxis=dict(title=eksen_basligi, gridcolor="rgba(56,189,248,0.08)",
                   zerolinecolor="rgba(56,189,248,0.15)"),
        yaxis=dict(autorange="reversed"),
        showlegend=False,
    )
    return f


with _sol:
    st.plotly_chart(
        _bar(f"Toplam tüketim ({_M['birim']})",
             [r["deger"] for r in _satirlar],
             [r["ad"] for r in _satirlar],
             [r["renk"] for r in _satirlar],
             [_tr(r["deger"]) for r in _satirlar],
             _M["birim"]),
        use_container_width=True, key="ozet_bar_toplam")

with _sag:
    if _yog:
        # Verimlilik: m² ve gün sayısına bölünmüş — büyük hastane otomatik
        # olarak "kötü" görünmesin diye ham tüketim yerine bu kıyaslanır.
        _ys = sorted(_yog, key=lambda r: r["yogunluk"])
        st.plotly_chart(
            _bar(f"Verimlilik ({_M['birim']}/m²/gün) — düşük olan iyi",
                 [r["yogunluk"] for r in _ys],
                 [r["ad"] for r in _ys],
                 ["#10b981" if r["yogunluk"] <= (_ort_yogunluk or 0) else "#f59e0b"
                  for r in _ys],
                 [f"{r['yogunluk']:.2f}" for r in _ys],
                 f"{_M['birim']}/m²/gün"),
            use_container_width=True, key="ozet_bar_yogunluk")
    else:
        st.info("m² bilgisi olmadığı için verimlilik karşılaştırması yapılamadı.")

# ── Tablo ─────────────────────────────────────────────────────────────────
st.markdown("<div style='font-size:10px;letter-spacing:2px;"
            "color:rgba(56,189,248,0.6);margin:6px 0 4px;'>DETAY TABLOSU</div>",
            unsafe_allow_html=True)

_satir_html = ""
for _i, _r in enumerate(_satirlar, 1):
    _pay = (_r["deger"] / _toplam * 100) if _toplam else 0
    if _r["degisim"] is None:
        _deg_html = "<span style='color:rgba(150,210,255,0.3);'>—</span>"
    else:
        # Tüketimde düşüş iyidir (artis_iyi=False)
        _iyi = (_r["degisim"] >= 0) if _M["artis_iyi"] else (_r["degisim"] <= 0)
        _deg_html = (f"<span style='color:{'#10b981' if _iyi else '#ef4444'};'>"
                     f"{'▼' if _r['degisim'] <= 0 else '▲'}"
                     f"{abs(_r['degisim']):.1f}%</span>")
    _yog_html = f"{_r['yogunluk']:.2f}" if _r["yogunluk"] is not None else "—"
    _satir_html += (
        f"<tr style='border-bottom:1px solid rgba(56,189,248,0.06);'>"
        f"<td style='padding:5px 6px;color:rgba(150,210,255,0.35);'>{_i}</td>"
        f"<td style='padding:5px 6px;color:{_r['renk']};font-weight:600;'>{_r['ad']}</td>"
        f"<td style='padding:5px 6px;text-align:right;color:#f8fafc;'>{_tr(_r['deger'])}</td>"
        f"<td style='padding:5px 6px;text-align:right;color:rgba(200,230,255,0.6);'>%{_pay:.1f}</td>"
        f"<td style='padding:5px 6px;text-align:right;color:rgba(200,230,255,0.6);'>{_yog_html}</td>"
        f"<td style='padding:5px 6px;text-align:right;'>{_deg_html}</td>"
        f"<td style='padding:5px 6px;text-align:right;color:rgba(150,210,255,0.35);'>"
        f"{_tr(_r['m2'])}</td></tr>"
    )

st.markdown(
    f"<div style='background:rgba(0,20,50,0.45);border:1px solid rgba(56,189,248,0.1);"
    f"border-radius:10px;padding:6px 10px;overflow-x:auto;'>"
    f"<table style='width:100%;border-collapse:collapse;font-size:10px;'>"
    f"<thead><tr style='color:rgba(56,189,248,0.5);font-size:8px;letter-spacing:1px;'>"
    f"<th style='text-align:left;padding:4px 6px;'>#</th>"
    f"<th style='text-align:left;padding:4px 6px;'>LOKASYON</th>"
    f"<th style='text-align:right;padding:4px 6px;'>{_M['birim'].upper()}</th>"
    f"<th style='text-align:right;padding:4px 6px;'>PAY</th>"
    f"<th style='text-align:right;padding:4px 6px;'>{_M['birim']}/M²/GÜN</th>"
    f"<th style='text-align:right;padding:4px 6px;'>ÖNCEKİ DÖNEME</th>"
    f"<th style='text-align:right;padding:4px 6px;'>M²</th>"
    f"</tr></thead><tbody>{_satir_html}</tbody></table></div>",
    unsafe_allow_html=True)

st.caption(f"Dönem: {_bas.strftime('%d.%m.%Y')} → {_bit.strftime('%d.%m.%Y')} "
           f"· Kıyas: {_o_bas.strftime('%d.%m.%Y')} → {_o_bit.strftime('%d.%m.%Y')}")
