# -*- coding: utf-8 -*-
"""
CANLI İZLEME — akan kW grafiği
==============================

Lokasyon detayındaki "Canlı İzleme" sekmesinin gövdesi. Sahadaki 27 sayacın
o anki gücü (kW) üç başlık altında, satır başına mini akan grafikle gösterilir.

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
import re
from datetime import datetime, timedelta, timezone

# SÜRÜM DAMGASI — sayfa ile bu modülün ayrışmasını yakalamak için.
# pages/lokasyon_detay.py her çalışmada DİSKTEN okunup exec edilir; bu modül
# ise Streamlit sürecine BİR KEZ yüklenir. Yeni sürüm yayınlandığında süreç
# yeniden başlamazsa sayfa yeni, modül eski kalır ve sayfa burada olmayan bir
# işlevi çağırır (21.10.2026: ekranda AttributeError). Sayfa bu damgayı
# kontrol eder, tutmazsa modülü tazeler.
# Modüle YENİ bir işlev eklendiğinde bu sayı artırılır.
SURUM = 2

# Pencere seçenekleri — saniye. Varsayılan 5 dakika (kullanıcı kararı).
PENCERELER = {"1 dakika": 60, "5 dakika": 300, "15 dakika": 900, "30 dakika": 1800}
VARSAYILAN_PENCERE = "5 dakika"

# Satır grafiği renkleri — BİLEREK tek aile (lacivert/mavi).
# Yeşil/turuncu/kırmızı bu portalda DURUM demek (iyi/uyarı/kritik); çizgiyi
# ayırt etmek için onları kullanmak, sağlam bir sayacı sorunluymuş gibi
# gösterir. Ayrım renk tonuyla yapılır, anlamla değil.
CIZGI_RENKLERI = ["#133273", "#2a78d6", "#4a3aa7", "#6da7ec", "#1d4ed8", "#5b8fd4"]

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


# ── Gruplama ─────────────────────────────────────────────────────────────
# Sahadaki 27 sayaç tek listede okunur; ekranda anlamlı üç başlık altında
# toplanır. Eşleşmeyen cihaz KAYBOLMAZ, "DİĞER" başlığına düşer.
GRUPLAR = [
    ("enerji",  "ENERJİ KAYNAĞI",   ("TRDP-",)),
    ("sogutma", "SOĞUTMA SİSTEMİ",  ("CHILLER-", "CH-", "KULE-")),
    ("mcc",     "MCC YÜKÜ",         ("MCC-", "2BK-", "4BK-", "CK-")),
]
GRUP_ACIKLAMA = {
    "enerji":  "Şebeke trafoları · canlı sayaçtan",
    "sogutma": "Chiller'lar ve soğutma kuleleri · canlı sayaçtan",
    "mcc":     "Ana panolar ve blok panoları · canlı sayaçtan",
    "diger":   "Gruplanmamış sayaçlar",
}


def grup_bul(cihaz: str) -> str:
    ad = str(cihaz or "").upper()
    for anahtar, _, onekler in GRUPLAR:
        if any(ad.startswith(o) for o in onekler):
            return anahtar
    return "diger"


def kisa_ad(cihaz: str) -> str:
    """CHILLER-1 → CH-1 (ekranda dar sütuna sığsın; veri adı DEĞİŞMEZ)."""
    return str(cihaz or "").replace("CHILLER-", "CH-")


def _sira_anahtari(cihaz: str, onekler: tuple):
    """Grup içi sıra: önce ön ek sırası, sonra SAYISAL.

    Düz alfabetik sıralamada '2BK-MCC-D01' ana panoların önüne geçiyor ve
    'MCC-10' da 'MCC-2'den önce geliyordu. Ön ek sırası GRUPLAR'daki
    yazılış sırasıdır — ana panolar önce, blok panoları sonra.
    """
    # Sıralama EKRANDAKİ ada göre: CHILLER-5 ile CH-1 aynı aile, listede
    # yan yana ve sayı sırasıyla dursunlar (CH-1, CH-5), ayrı kümeler gibi
    # değil.
    ad = kisa_ad(str(cihaz or "")).upper()
    sira = next((i for i, o in enumerate(onekler) if ad.startswith(o)), len(onekler))
    parcalar = []
    for p in re.split(r"(\d+)", ad):
        parcalar.append((1, int(p)) if p.isdigit() else (0, p))
    return (sira, parcalar)


def gruplara_ayir(cihazlar: list) -> list:
    """[(anahtar, baslik, [cihaz...])] — sıralı, boş grup dönmez."""
    sonuc = []
    kalan = list(cihazlar or [])
    for anahtar, baslik, onekler in GRUPLAR:
        uyan = [c for c in kalan if grup_bul(c) == anahtar]
        if uyan:
            sonuc.append((anahtar, baslik,
                          sorted(uyan, key=lambda c: _sira_anahtari(c, onekler))))
    artan = sorted(c for c in kalan if grup_bul(c) == "diger")
    if artan:
        sonuc.append(("diger", "DİĞER", artan))
    return sonuc


def grup_toplami(seri: dict, cihazlar: list):
    """Gruptaki okunabilen cihazların son değerleri toplamı."""
    son = son_degerler(seri)
    return toplam({c: son.get(c) for c in cihazlar})


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


# ── Satır içi mini grafik (SVG) ──────────────────────────────────────────
# 27 cihaz için 27 Plotly grafiği çizmek ağır olurdu; satır grafiği düz SVG
# olarak üretilir. Her cihaz KENDİ aralığına ölçeklenir: amaç sayaçları
# birbiriyle kıyaslamak değil, o sayacın son dakikalarda ne yaptığını
# göstermek — yoksa 4 kW'lık kulenin hareketi 880 kW'lık trafonun yanında
# düz çizgi görünürdü.

def kivrim_svg(degerler: list, renk: str = "#2a78d6",
               genislik: int = 100, yukseklik: int = 26) -> str:
    """Seriden mini çizgi. Okunamayan noktalar BOŞLUK bırakır."""
    gecerli = [d for d in (degerler or []) if d is not None]
    if not gecerli:
        return (f"<svg viewBox='0 0 {genislik} {yukseklik}' preserveAspectRatio='none' "
                f"style='width:100%;height:{yukseklik}px;display:block;'>"
                f"<line x1='0' y1='{yukseklik/2:.0f}' x2='{genislik}' y2='{yukseklik/2:.0f}' "
                f"stroke='#d7dde7' stroke-width='1.4' stroke-dasharray='3 3'/></svg>")

    n = len(degerler)
    alt, ust = min(gecerli), max(gecerli)
    if ust - alt < 1e-9:                  # düz çizgi: ortada dursun
        alt, ust = alt - 1.0, ust + 1.0
    pay = (ust - alt) * 0.18
    alt, ust = alt - pay, ust + pay

    def nokta(i, v):
        x = 0 if n < 2 else i * genislik / (n - 1)
        y = yukseklik - (v - alt) / (ust - alt) * yukseklik
        return "%.1f,%.1f" % (x, max(1.0, min(yukseklik - 1.0, y)))

    # Boşluklara göre parçalara ayır — kopuk veri birleştirilmez
    parcalar, parca = [], []
    for i, v in enumerate(degerler):
        if v is None:
            if len(parca) > 1:
                parcalar.append(parca)
            parca = []
        else:
            parca.append(nokta(i, v))
    if len(parca) > 1:
        parcalar.append(parca)
    if not parcalar:                      # tek nokta: kısa yatay iz
        i = next(i for i, v in enumerate(degerler) if v is not None)
        x, y = nokta(i, degerler[i]).split(",")
        parcalar = [["%.1f,%s" % (max(0.0, float(x) - 5), y), "%s,%s" % (x, y)]]

    cizgiler = "".join(
        f"<polyline fill='none' stroke='{renk}' stroke-width='1.8' "
        f"stroke-linejoin='round' stroke-linecap='round' points='{' '.join(p)}'/>"
        for p in parcalar)
    return (f"<svg viewBox='0 0 {genislik} {yukseklik}' preserveAspectRatio='none' "
            f"style='width:100%;height:{yukseklik}px;display:block;'>{cizgiler}</svg>")


def tr_sayi(x, ond=1):
    s = ("{:,.%df}" % ond).format(x)
    tam, _, kus = s.partition(".")
    return tam.replace(",", ".") + "," + kus


def satir_html(cihaz: str, deger, cizgi_svg: str, yontem: str = None) -> str:
    """Tek cihaz satırı: ad · mini grafik · anlık kW.

    Okunamayan cihaz "0,0 kW" DEĞİL "okunamadı" yazar: sıfır, sayacın
    durduğunu söyler; okunamamak başka bir şeydir.
    """
    okunamadi = deger is None
    dg = "okunamadı" if okunamadi else (tr_sayi(deger) + "<span class='cg-br'>kW</span>")
    cip_sinif = "cg-cip cg-yok" if okunamadi else "cg-cip"
    dg_sinif = "cg-dg cg-dg-yok" if okunamadi else "cg-dg"
    ipucu = YONTEM_ETIKET.get(yontem, ("", ""))[0]
    baslik = f" title='{ipucu}'" if ipucu else ""
    return (f"<div class='cg-satir'{baslik}><div class='{cip_sinif}'>{kisa_ad(cihaz)}</div>"
            f"<div class='cg-cizgi'>{cizgi_svg}</div>"
            f"<div class='{dg_sinif}'>{dg}</div></div>")


def grup_html(baslik: str, aciklama: str, satirlar: str, toplam_kw,
              okunan: int, adet: int, yukseklik: int = 430) -> str:
    """Bir grup kartı. Liste uzarsa KART değil liste kayar."""
    ust = f"<div class='cg-toplam'>{'—' if toplam_kw is None else tr_sayi(toplam_kw) + ' kW'}</div>"
    return (f"<div class='cg-grup'><h4>{baslik}{ust}</h4>"
            f"<div class='cg-ack'>{aciklama}</div>"
            f"<div class='cg-liste' style='max-height:{yukseklik}px'>{satirlar}</div>"
            f"<div class='cg-dip'>{okunan}/{adet} sayaç okunuyor</div></div>")


STIL = """
<style>
.cg-sarmal{display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
  gap:12px; align-items:start;}
.cg-grup{background:#fff; border:1px solid rgba(24,26,30,.10); border-radius:16px;
  padding:11px 6px 9px 13px;
  box-shadow:0 1px 1px rgba(20,22,26,.05),0 12px 26px -14px rgba(20,22,26,.25);}
.cg-grup h4{margin:0 0 2px; font-size:12px; letter-spacing:1.4px; color:#133273;
  font-weight:700; padding-right:8px;}
.cg-toplam{float:right; font-size:13px; font-weight:700; color:#133273;}
.cg-ack{font-size:9.5px; color:#46536b; margin-bottom:5px; padding-right:8px;}
.cg-dip{font-size:9px; color:#9aa2b1; padding:6px 8px 0 0;
  border-top:1px solid rgba(24,26,30,.07); margin-top:3px;}
.cg-liste{overflow-y:auto; padding-right:8px;
  scrollbar-width:thin; scrollbar-color:#cdd5e2 transparent;}
.cg-liste::-webkit-scrollbar{width:7px;}
.cg-liste::-webkit-scrollbar-thumb{background:#cdd5e2; border-radius:4px;}
.cg-satir{display:grid; grid-template-columns:96px 1fr 84px; gap:9px; align-items:center;
  padding:7px 0; border-bottom:1px solid rgba(24,26,30,.06);}
.cg-satir:last-child{border-bottom:0;}
.cg-cip{font-size:10.5px; font-weight:600; color:#0f1f3d; background:#f6f7f9;
  border:1px solid rgba(24,26,30,.12); border-radius:8px; padding:4px 5px; text-align:center;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.cg-cip.cg-yok{color:#8b93a3; background:#f3f3f4; border-style:dashed;}
.cg-cizgi{height:26px; overflow:hidden;}
.cg-dg{font-size:14px; font-weight:700; color:#133273; text-align:right; white-space:nowrap;}
.cg-dg.cg-dg-yok{font-size:10px; font-weight:600; color:#9aa2b1;}
.cg-br{font-size:9px; font-weight:500; color:#46536b; margin-left:2px;}
</style>
"""


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
