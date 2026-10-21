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
SURUM = 5

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


def dogrulandi_mi(yontem) -> bool:
    """Değer, cihazın kendi kWh sayacıyla doğrulanmış mı?"""
    return yontem == "register"


def yontem_ozeti(olcumler: list) -> tuple:
    """(metin, renk) — KISA sayım özeti.

    İlk sürüm doğrulanan ve doğrulanmayan cihazların ADLARINI tek tek
    yazıyordu; 27 sayaçta alt bant ekranı boydan boya dolduruyordu
    (21.10.2026). Hangi sayacın hangi durumda olduğu artık SATIRINDAKİ
    noktadan okunuyor; burada yalnızca sayılar var.
    """
    okunan = [o for o in (olcumler or []) if o.get("cihaz") and o.get("kw") is not None]
    if not okunan:
        return "", "#46536b"
    dogru = sum(1 for o in okunan if dogrulandi_mi(o.get("yontem")))
    eksik = len(okunan) - dogru
    if not eksik:
        return "%d sayaç doğrulandı" % dogru, "#0ca30c"
    return ("%d sayaç doğrulandı · %d sayaç doğrulanmadı" % (dogru, eksik)), "#c98500"


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


def toplam_seri(seri: dict, cihazlar: list) -> list:
    """Cihazların zaman İÇİNDE toplamı — ŞEBEKE gibi birleşik satırlar için.

    Bir anda hiçbir cihaz okunamadıysa o nokta None kalır; okunanların
    toplamı alınır (eksik sayaç yüzünden toplam sıfıra düşmesin).
    """
    diziler = [seri.get("cihazlar", {}).get(c) or [] for c in cihazlar]
    n = len(seri.get("zamanlar") or [])
    sonuc = []
    for i in range(n):
        degerler = [d[i] for d in diziler if i < len(d) and d[i] is not None]
        sonuc.append(round(sum(degerler), 1) if degerler else None)
    return sonuc


def olcum_araligi_sn(seri: dict):
    """Ölçümler kaç saniyede bir geliyor (ortanca). Yetersiz veri → None."""
    zamanlar = seri.get("zamanlar") or []
    if len(zamanlar) < 3:
        return None
    farklar = sorted((zamanlar[i + 1] - zamanlar[i]).total_seconds()
                     for i in range(len(zamanlar) - 1))
    orta = farklar[len(farklar) // 2]
    return int(round(orta)) if orta > 0 else None


# Canlı sayacı OLMAYAN kalemler. Enerji grubunda kesik çizgiyle gösterilir.
# (ad, energy_data sütunu, neden). Sütun o lokasyonda hiç dolmuyorsa o
# sistem binada yok demektir ve satır GÖSTERİLMEZ — kojeni olmayan
# hastanede "kojen verisi çekilemiyor" yazmak yanlış olurdu.
OLCULMEYEN = [
    ("KOJEN",    "Kojen_Uretim_kWh",  "canlı sayaç yok · günlük üretim kaydı var"),
    ("DOĞALGAZ", "Kazan_Dogalgaz_m3", "m³ sayacı canlı okunmuyor"),
    ("SU",       "Su_Tuketimi_m3",    "m³ sayacı canlı okunmuyor"),
]


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
                f"stroke='#d7dde7' stroke-width='1.4' vector-effect='non-scaling-stroke' "
                f"stroke-dasharray='3 3'/></svg>")

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

    # vector-effect='non-scaling-stroke' ŞART: SVG yatayda esnetiliyor
    # (preserveAspectRatio='none'), kalem de onunla esniyordu — dik inişler
    # ince, yataya yakın yerler kalın görünüyordu (21.10.2026). Bu özellikle
    # çizgi kalınlığı ekranda her yerde AYNI kalır.
    cizgiler = "".join(
        f"<polyline fill='none' stroke='{renk}' stroke-width='1.6' "
        f"vector-effect='non-scaling-stroke' "
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

    # Doğrulama durumu CİHAZ ADININ yanında: yeşil = kWh sayacıyla
    # doğrulandı, turuncu = doğrulanmadı / sayaç farkından. Nokta, ait
    # olduğu cihazla birlikte okunsun diye değerin değil adın yanındadır.
    if okunamadi:
        nokta = ""
    else:
        nokta = ("<span class='cg-dot cg-dot-ok'></span>" if dogrulandi_mi(yontem)
                 else "<span class='cg-dot cg-dot-bekle'></span>")
    return (f"<div class='cg-satir'{baslik}>"
            f"<div class='{cip_sinif}'>{kisa_ad(cihaz)}{nokta}</div>"
            f"<div class='cg-cizgi'>{cizgi_svg}</div>"
            f"<div class='{dg_sinif}'>{dg}</div></div>")


def toplam_satir_html(ad: str, deger, cizgi_svg: str) -> str:
    """Grubun TOPLAMINI gösteren vurgulu satır (ör. ŞEBEKE = 4 trafo)."""
    dg = "—" if deger is None else (tr_sayi(deger) + "<span class='cg-br'>kW</span>")
    return (f"<div class='cg-satir cg-ust-satir'><div class='cg-cip cg-cip-ust'>{ad}</div>"
            f"<div class='cg-cizgi'>{cizgi_svg}</div>"
            f"<div class='cg-dg cg-dg-ust'>{dg}</div></div>")


def olculmeyen_satir_html(ad: str, aciklama: str) -> str:
    """Canlı sayacı OLMAYAN kalem: kesik çizgi + nedeni.

    Bu satırlar "0 kW" göstermez. Sıfır, tüketimin durduğunu söyler;
    burada ölçüm yoktur — ikisi aynı şey değildir.
    """
    return (f"<div class='cg-satir cg-olcusuz'><div class='cg-cip cg-yok'>{ad}</div>"
            f"<div class='cg-bos'><span class='cg-tire'></span>"
            f"<span class='cg-bos-not'>{aciklama}</span>"
            f"<span class='cg-tire'></span></div>"
            f"<div class='cg-dg cg-dg-yok'>veri çekilemiyor</div></div>")


def grup_html(baslik: str, aciklama: str, satirlar: str, toplam_kw,
              okunan: int, olcusuz: int = 0, yukseklik: int = 430) -> str:
    """Bir grup kartı. Liste uzarsa KART değil liste kayar."""
    ust = f"<div class='cg-toplam'>{'—' if toplam_kw is None else tr_sayi(toplam_kw) + ' kW'}</div>"
    dip = "%d kalem canlı okunuyor" % okunan
    if olcusuz:
        dip += " · %d kalemde sayaç yok" % olcusuz
    return (f"<div class='cg-grup'><h4>{baslik}{ust}</h4>"
            f"<div class='cg-ack'>{aciklama}</div>"
            f"<div class='cg-liste' style='max-height:{yukseklik}px'>{satirlar}</div>"
            f"<div class='cg-dip'>{dip}</div></div>")


def ozet_kart_html(etiket: str, deger: str, alt: str, canli: bool = False) -> str:
    nokta = "<span class='cg-nabiz'></span>" if canli else ""
    return (f"<div class='cg-ozet'><div class='cg-ozet-et'>{nokta}{etiket}</div>"
            f"<div class='cg-ozet-dg'>{deger}</div>"
            f"<div class='cg-ozet-alt'>{alt}</div></div>")


def ozet_serit_html(kartlar: list) -> str:
    return "<div class='cg-serit'>" + "".join(kartlar) + "</div>"


def alt_bant_html(yontem_metin: str, yontem_renk: str, ozet: str) -> str:
    return (f"<div class='cg-alt'><span style='color:{yontem_renk};'>● {yontem_metin}</span>"
            f"<span class='cg-alt-ayrac'>·</span>{ozet}</div>")


STIL = """
<style>
/* ── özet şeridi ── */
.cg-serit{display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
  gap:12px; margin:2px 0 14px;}
.cg-ozet{background:#fff; border:1px solid rgba(24,26,30,.10); border-radius:16px;
  padding:11px 15px;
  box-shadow:0 1px 1px rgba(20,22,26,.05),0 10px 22px -12px rgba(20,22,26,.22);}
.cg-ozet-et{font-size:10px; letter-spacing:1.2px; color:#46536b; font-weight:600;}
.cg-ozet-dg{font-size:26px; font-weight:700; color:#133273; margin-top:1px; line-height:1.15;}
.cg-ozet-alt{font-size:10px; color:#46536b; margin-top:1px;}
.cg-nabiz{display:inline-block; width:7px; height:7px; border-radius:50%;
  background:#0ca30c; margin-right:5px; animation:cgNabiz 1.6s ease-in-out infinite;}
@keyframes cgNabiz{0%,100%{opacity:1; transform:scale(1);} 50%{opacity:.35; transform:scale(.8);}}

/* ── alt bant ── */
.cg-alt{font-size:12px; color:#46536b; margin-top:12px;}
.cg-alt-ayrac{margin:0 8px; color:#c9d2e0;}

/* align-items:stretch (varsayılan): kartlar EN UZUNUN boyunda durur.
   Önceden 'start' idi ve 15 satırlık MCC kartı diğerlerinden uzun
   görünüyordu (21.10.2026). Kart dikey flex; liste kalan yeri doldurur. */
.cg-sarmal{display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
  gap:12px;}
.cg-grup{background:#fff; border:1px solid rgba(24,26,30,.10); border-radius:16px;
  padding:11px 6px 9px 13px; display:flex; flex-direction:column;
  box-shadow:0 1px 1px rgba(20,22,26,.05),0 12px 26px -14px rgba(20,22,26,.25);}
.cg-grup h4{margin:0 0 2px; font-size:12px; letter-spacing:1.4px; color:#133273;
  font-weight:700; padding-right:8px;}
.cg-toplam{float:right; font-size:13px; font-weight:700; color:#133273;}
.cg-ack{font-size:9.5px; color:#46536b; margin-bottom:5px; padding-right:8px;}
.cg-dip{font-size:9px; color:#9aa2b1; padding:6px 8px 0 0;
  border-top:1px solid rgba(24,26,30,.07); margin-top:3px;}
.cg-liste{flex:1 1 auto; min-height:0; overflow-y:auto; padding-right:8px;
  scrollbar-width:thin; scrollbar-color:#cdd5e2 transparent;}
.cg-liste::-webkit-scrollbar{width:7px;}
.cg-liste::-webkit-scrollbar-thumb{background:#cdd5e2; border-radius:4px;}
.cg-satir{display:grid; grid-template-columns:104px 1fr 92px; gap:10px; align-items:center;
  padding:10px 0; border-bottom:1px solid rgba(24,26,30,.06);}
.cg-satir:last-child{border-bottom:0;}
.cg-cip{font-size:11px; font-weight:600; color:#0f1f3d; background:#f6f7f9;
  border:1px solid rgba(24,26,30,.12); border-radius:9px; padding:6px 5px; text-align:center;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.cg-cip.cg-yok{color:#8b93a3; background:#f3f3f4; border-style:dashed;}
.cg-cip-ust{font-weight:700; background:#eef3fb; border-color:#cddcf1; color:#133273;}
.cg-dg-ust{font-size:16px;}
.cg-cizgi{height:28px; overflow:hidden;}
.cg-dg{font-size:15px; font-weight:700; color:#133273; text-align:right; white-space:nowrap;}
.cg-dg.cg-dg-yok{font-size:10.5px; font-weight:600; color:#9aa2b1;}
.cg-br{font-size:9.5px; font-weight:500; color:#46536b; margin-left:2px;}

/* ── doğrulama noktası: cihaz adının yanında, yanıp söner ── */
.cg-dot{display:inline-block; width:6px; height:6px; border-radius:50%;
  margin-left:5px; vertical-align:middle; animation:cgNabiz 2.2s ease-in-out infinite;}
.cg-dot-ok{background:#0ca30c;}      /* kWh sayacıyla doğrulandı */
.cg-dot-bekle{background:#fab219;}   /* doğrulanmadı / sayaç farkından */

/* ── ölçülemeyen kalem: kesik çizgi + nedeni ── */
.cg-bos{height:28px; display:flex; align-items:center; gap:7px;}
.cg-bos .cg-tire{flex:1; border-top:1.6px dashed #cfd5df;}
.cg-bos-not{font-size:10px; color:#9aa2b1; white-space:nowrap;}
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
