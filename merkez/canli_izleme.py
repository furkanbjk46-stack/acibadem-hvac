# -*- coding: utf-8 -*-
"""
CANLI İZLEME — akan kW grafiği
==============================

Lokasyon detayındaki "Canlı İzleme" sekmesinin gövdesi. Sahadaki sayaçların
o anki gücü (kW) kayan bir pencerede çizilir; çizgi soldan sağa akar.

── GEÇMİŞ NEREDE TUTULUYOR (ÖNEMLİ KARAR) ───────────────────────────────
Hiçbir yerde. Supabase'deki canli_guc tablosu SON değeri tutar, üzerine
yazar: lokasyon×cihaz başına tek satır, yani sabit boyut. Grafiğin
ihtiyacı olan birkaç dakikalık seri MERKEZİN OTURUMUNDA birikir
(st.session_state) ve pencereden çıkan nokta atılır.

Neden böyle: 15 saniyede bir kalıcı kayıt tutmak günde lokasyon başına
5.760 satır eder ve tablo sürekli şişer; 24 saatlik seriyi her yenilemede
indirmek de ağır olur. Kullanıcı kararı (20.10.2026): önce 5 dakikalık
pencereyle çalışalım, veri tabanında yer kaplamasın.

Bunun bedeli dürüstçe söylenir: sekme açıldığında grafik BOŞ başlar ve
pencere süresi kadar dolar. Tarayıcı yenilenirse seri sıfırlanır. Kalıcı
24 saatlik geçmiş istenirse ayrı bir kayıt tablosu gerekir — o zaman
burada değil, lokasyon tarafında yazılır.

Hesap (seri_guncelle) saf fonksiyondur: Streamlit olmadan test edilir.
"""
from datetime import datetime, timedelta, timezone

# Pencere seçenekleri — saniye. Varsayılan 5 dakika (kullanıcı kararı).
PENCERELER = {"1 dakika": 60, "5 dakika": 300, "15 dakika": 900, "30 dakika": 1800}
VARSAYILAN_PENCERE = "5 dakika"

# Dört trafo için sabit renk: grafikte ve kartlarda AYNI renk kullanılsın
CIZGI_RENKLERI = ["#133273", "#2a78d6", "#6da7ec", "#4a3aa7",
                  "#0ca30c", "#c98500", "#d03b3b", "#46536b"]

# Değerin NEREDEN geldiği ekranda yazar: tahmin, ölçüm gibi gösterilmesin.
#   register  → cihazın güç register'ı, kWh sayacıyla doğrulandı
#   register? → güç register'ı, henüz doğrulanmadı
#   sayac     → kWh sayacının farkından (register yok ya da çelişti)
YONTEM_ETIKET = {
    "register": ("sayaçla doğrulandı", "#0ca30c"),
    "register?": ("henüz doğrulanmadı", "#c98500"),
    "sayac": ("sayaç farkından", "#c98500"),
}


def yontem_ozeti(olcumler: list) -> tuple:
    """(metin, renk) — dört sayacın yöntemi aynıysa tek satır, değilse döküm."""
    yontemler = {}
    for o in olcumler or []:
        if o.get("cihaz"):
            yontemler.setdefault(o.get("yontem"), []).append(o["cihaz"])
    if not yontemler:
        return "", "#46536b"
    if len(yontemler) == 1:
        y = next(iter(yontemler))
        etiket, renk_ = YONTEM_ETIKET.get(y, ("okunamadı", "#d03b3b"))
        return "Tüm sayaçlar: " + etiket, renk_
    parcalar = []
    for y, cihazlar in yontemler.items():
        etiket, _ = YONTEM_ETIKET.get(y, ("okunamadı", "#d03b3b"))
        parcalar.append("%s: %s" % (", ".join(sorted(cihazlar)), etiket))
    return " · ".join(parcalar), "#c98500"


def renk(cihaz: str, sirali_cihazlar: list) -> str:
    """Cihazın rengi — listedeki sırasına göre, her yenilemede AYNI."""
    try:
        return CIZGI_RENKLERI[sirali_cihazlar.index(cihaz) % len(CIZGI_RENKLERI)]
    except ValueError:
        return CIZGI_RENKLERI[-1]


def _zaman_coz(deger):
    """ISO metni → datetime (saat dilimi varsa yerel saate çevrilir)."""
    if isinstance(deger, datetime):
        return deger
    try:
        t = datetime.fromisoformat(str(deger).replace("Z", "+00:00"))
    except Exception:
        return None
    if t.tzinfo is not None:
        t = t.astimezone().replace(tzinfo=None)
    return t


def bos_seri() -> dict:
    return {"zamanlar": [], "cihazlar": {}}


def seri_guncelle(seri: dict, olcumler: list, pencere_sn: int,
                  simdi: datetime = None) -> dict:
    """Yeni ölçümü seriye ekler, pencereden çıkanları atar. SAF fonksiyon.

    olcumler: [{"cihaz": .., "kw": .., "olcum_zamani": ..}, ...]
    Aynı ölçüm zamanı İKİ KEZ eklenmez — ekran sahadan hızlı yenileniyor,
    yoksa aynı nokta üst üste yığılır ve grafik yanlış yoğunluk gösterir.
    """
    seri = seri or bos_seri()
    zamanlar = list(seri.get("zamanlar") or [])
    cihazlar = {k: list(v) for k, v in (seri.get("cihazlar") or {}).items()}

    gecerli = [o for o in (olcumler or []) if o.get("cihaz")]
    if gecerli:
        t = _zaman_coz(gecerli[0].get("olcum_zamani")) or (simdi or datetime.now())
        if not zamanlar or t > zamanlar[-1]:
            zamanlar.append(t)
            n = len(zamanlar)
            yeni = {o["cihaz"]: o.get("kw") for o in gecerli}
            for ad in yeni:
                if ad not in cihazlar:
                    # Sonradan görünen cihaz: geçmişi boş bırakılır ki
                    # eksenler kaymasın (uydurma değerle doldurulmaz).
                    cihazlar[ad] = [None] * (n - 1)
            for ad, degerler in cihazlar.items():
                degerler.append(yeni.get(ad))
                if len(degerler) < n:               # eksik kalan varsa hizala
                    degerler.extend([None] * (n - len(degerler)))

    # Pencere dışını at
    if zamanlar:
        sinir = (simdi or zamanlar[-1]) - timedelta(seconds=pencere_sn)
        kesme = 0
        while kesme < len(zamanlar) and zamanlar[kesme] < sinir:
            kesme += 1
        if kesme:
            zamanlar = zamanlar[kesme:]
            cihazlar = {ad: d[kesme:] for ad, d in cihazlar.items()}

    return {"zamanlar": zamanlar, "cihazlar": cihazlar}


def son_degerler(seri: dict) -> dict:
    """Her cihazın serideki son (None olmayan) değeri."""
    sonuc = {}
    for ad, degerler in (seri.get("cihazlar") or {}).items():
        sonuc[ad] = next((d for d in reversed(degerler) if d is not None), None)
    return sonuc


def toplam(degerler: dict):
    """Okunabilen cihazların toplamı. Hiçbiri okunamadıysa None."""
    okunan = [v for v in (degerler or {}).values() if v is not None]
    return round(sum(okunan), 1) if okunan else None


def eksen_araligi(seri: dict, pencere_sn: int, simdi: datetime = None) -> tuple:
    """Grafiğin x aralığı: SON ANA sabitlenir, pencere kadar geriye gider.

    Aralık saate bağlı olduğu için yeni veri gelmese bile çizgi sola akar —
    'ilerleyen grafik' görüntüsü buradan gelir.
    """
    bit = simdi or datetime.now()
    zamanlar = seri.get("zamanlar") or []
    if zamanlar and zamanlar[-1] > bit:
        bit = zamanlar[-1]
    return bit - timedelta(seconds=pencere_sn), bit


def grafik(go, seri: dict, pencere_sn: int, simdi: datetime = None,
           yukseklik: int = 380):
    """Akan çizgi grafiği (plotly)."""
    cihazlar = seri.get("cihazlar") or {}
    sirali = sorted(cihazlar)
    zamanlar = seri.get("zamanlar") or []
    bas, bit = eksen_araligi(seri, pencere_sn, simdi)

    fig = go.Figure()
    for ad in sirali:
        fig.add_trace(go.Scatter(
            x=zamanlar, y=cihazlar[ad], name=ad, mode="lines",
            line=dict(color=renk(ad, sirali), width=2, shape="spline", smoothing=0.6),
            hovertemplate="%{y:.1f} kW<extra>" + ad + "</extra>",
            connectgaps=False,          # okunamayan nokta BOŞLUK kalsın
        ))

    fig.update_layout(
        height=yukseklik,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, system-ui, sans-serif", size=11, color="#24324d"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0,
                    font=dict(size=11, color="#24324d")),
        hovermode="x unified",
        # uirevision: yenilemede kullanıcının gezinme/yakınlaştırmasi bozulmasın
        uirevision="canli",
        transition=dict(duration=0),
    )
    fig.update_xaxes(range=[bas, bit], gridcolor="#e8edf4", linecolor="#c9d2e0",
                     tickformat="%H:%M:%S", title=None)
    fig.update_yaxes(gridcolor="#e8edf4", linecolor="#c9d2e0",
                     title=dict(text="kW", font=dict(size=11, color="#46536b")),
                     rangemode="tozero")
    return fig


def durum_metni(seri: dict, yas_sn=None, pencere_sn: int = 300) -> str:
    """Grafiğin altındaki tek satırlık durum açıklaması."""
    n = len(seri.get("zamanlar") or [])
    if n == 0:
        return "Veri bekleniyor — sahadan ilk ölçüm gelince çizim başlar."
    zamanlar = seri["zamanlar"]
    sure = (zamanlar[-1] - zamanlar[0]).total_seconds()
    parcalar = ["%d nokta" % n]
    if sure < pencere_sn - 30:
        parcalar.append("pencere doluyor (%d sn / %d sn)" % (sure, pencere_sn))
    else:
        parcalar.append("son %d dakika" % round(pencere_sn / 60))
    if yas_sn is not None:
        parcalar.append("son ölçüm %.0f sn önce" % yas_sn)
    return " · ".join(parcalar)
