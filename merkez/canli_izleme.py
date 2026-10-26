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
SURUM = 8

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
    # Sahada bugün canlı okunmayan kalemler. Bu adlarla bir sayaç tabloya
    # yazılırsa (bugün yalnız sunum verisi yazıyor) kendi grubunda görünür;
    # yazılmıyorsa grup hiç çıkmaz, OLCULMEYEN satırı gösterilir.
    ("kojen",    "KOJEN ÜRETİMİ",   ("KOJEN-",)),
    ("dogalgaz", "DOĞALGAZ",        ("DOGALGAZ-",)),
    ("su",       "SU",              ("SU-",)),
]
GRUP_ACIKLAMA = {
    "enerji":  "Trafolar · canlı sayaçtan",
    "sogutma": "Chiller'lar ve soğutma kuleleri · canlı sayaçtan",
    "mcc":     "Ana panolar ve blok panoları · canlı sayaçtan",
    "kojen":   "Kojen jeneratörleri · canlı sayaçtan",
    "dogalgaz": "Kazan + kojen gaz girişi · canlı sayaçtan",
    "su":      "Şebeke suyu girişi · canlı sayaçtan",
    "diger":   "Gruplanmamış sayaçlar",
}
# Tablo sütununun adı "kw" olsa da gaz ve su debi olarak (m³/h) yazılır
BIRIM = {"dogalgaz": "m³/h", "su": "m³/h"}


def birim(grup: str) -> str:
    return BIRIM.get(grup, "kW")


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
# Kalemin canlı grubu: o grup ekranda varsa "ölçülmüyor" satırı basılmaz
OLCULMEYEN_GRUP = {"KOJEN": "kojen", "DOĞALGAZ": "dogalgaz", "SU": "su"}

# Kojenler ENERJİ KAYNAĞI kartında "ÜRETİM" başlığı altında (26.10.2026).
# Canlı sayaçları sahaya yakında eklenecek; gelene kadar her biri "sayaç
# bekleniyor" satırıyla görünür (0 kW yazılmaz). KOJEN-1 ... KOJEN-n adıyla
# canli_guc'a yazılmaya başlayınca satır kendiliğinden canlı değere döner.
KOJEN_ADET = 4
KOJEN_BEKLEME_NOTU = "canlı sayaç yakında eklenecek"


def kojen_adlari(adet: int = KOJEN_ADET) -> list:
    return ["KOJEN-%d" % i for i in range(1, adet + 1)]


def kojen_bekleyenler(canli_kojenler: list, adet: int = KOJEN_ADET) -> list:
    """Henüz canlı okunmayan kojenler (sırayla). Canlı gelen listeden düşer."""
    canli = {str(c).upper() for c in (canli_kojenler or [])}
    return [k for k in kojen_adlari(adet) if k not in canli]


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


# ── Yük çubuğu (yatay dolgu) ─────────────────────────────────────────────
# Satır grafiği yerine SCADA'daki gibi dolgulu çubuk: anlık yükün ne kadar
# olduğu bir bakışta okunsun.
#
# ÇUBUK NEYE GÖRE DOLUYOR: cihazın "nominal kapasitesi" sistemde kayıtlı
# değil (sayaçlar yalnızca anlık gücü veriyor). Bu yüzden ölçek, AYNI
# GRUPTAKİ sayaçların seçili pencerede gördüğü EN YÜKSEK değerdir. Yani
# çubuk "kapasitenin %x'i" demez, "bu gruptaki en yüksek yüke göre %x"
# der — ekranda da böyle yazar. Pencere içindeki tepe kullanılır ki
# lider değiştikçe bütün çubuklar zıplamasın.
#
# RENK ise MUTLAK kW eşiğine göredir (kullanıcı ölçütü): <500 yeşil,
# 500-700 yeşilden turuncuya, 700-800 turuncudan kırmızıya, >800 kırmızı.
# Trafolarda anlamlı bir uyarı verir; küçük panolar doğal olarak yeşil kalır.

ESIK_YESIL = (34, 197, 94)
ESIK_TURUNCU = (245, 158, 11)
ESIK_KIRMIZI = (239, 68, 68)


def _karistir(a, b, t):
    return tuple(round(x + t * (y - x)) for x, y in zip(a, b))


def esik_rengi(kw) -> str:
    """Mutlak kW eşiğine göre çubuk rengi (aralıklarda yumuşak geçiş)."""
    if kw is None:
        return "rgb(203, 213, 225)"
    kw = abs(float(kw))
    if kw <= 500:
        r = ESIK_YESIL
    elif kw <= 700:
        r = _karistir(ESIK_YESIL, ESIK_TURUNCU, (kw - 500) / 200.0)
    elif kw <= 800:
        r = _karistir(ESIK_TURUNCU, ESIK_KIRMIZI, (kw - 700) / 100.0)
    else:
        r = ESIK_KIRMIZI
    return "rgb(%d, %d, %d)" % r


def olcek_degeri(seri: dict, cihazlar: list) -> float:
    """Grubun ölçeği: pencere boyunca görülen en yüksek değer.

    Anlık en yüksek yerine PENCERE TEPESİ kullanılır; yoksa lider her
    değiştiğinde bütün çubuklar yeniden ölçeklenip zıplardı.
    """
    tepe = 0.0
    for c in cihazlar or []:
        for d in (seri.get("cihazlar", {}).get(c) or []):
            if d is not None and abs(d) > tepe:
                tepe = abs(d)
    return tepe


# Yük eşiği (yeşil→kırmızı) yalnız TÜKETEN sayaçlar için anlamlı. Kojen
# üretimi yüksekken kırmızı "alarm" gibi görünürdü; gaz/su debisi kW değil.
ESIKSIZ_GRUPLAR = ("kojen", "dogalgaz", "su")
ESIKSIZ_RENK = "rgb(42, 120, 214)"


def bar_html(deger, olcek, baslik: str = "", birim: str = "kW", esikli: bool = True) -> str:
    """Yatay dolgu çubuğu. Ölçek yoksa/0 ise boş iz döner."""
    if deger is None or not olcek or olcek <= 0:
        return "<div class='cg-iz'></div>"
    oran = max(0.0, min(100.0, abs(float(deger)) / float(olcek) * 100.0))
    ipucu = baslik or ("%s %s · %%%.0f" % (tr_sayi(deger), birim, oran))
    renk = esik_rengi(deger) if esikli else ESIKSIZ_RENK
    return (f"<div class='cg-iz' title='{ipucu}'>"
            f"<div class='cg-dolgu' style='width:{oran:.1f}%;"
            f"background-color:{renk};'></div></div>")


def tr_sayi(x, ond=1):
    s = ("{:,.%df}" % ond).format(x)
    tam, _, kus = s.partition(".")
    return tam.replace(",", ".") + "," + kus


def satir_html(cihaz: str, deger, cubuk: str, yontem: str = None, birim: str = "kW",
               gecis: tuple = None) -> str:
    """Tek cihaz satırı: ad · mini grafik · anlık kW.

    Okunamayan cihaz "0,0 kW" DEĞİL "okunamadı" yazar: sıfır, sayacın
    durduğunu söyler; okunamamak başka bir şeydir.
    """
    okunamadi = deger is None
    dg = "okunamadı" if okunamadi else (akan(deger, 1, cihaz, *(gecis or ()))
                                        + f"<span class='cg-br'>{birim}</span>")
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
    # İpucu ÇİPTE: satır display:contents olduğu için kendi kutusu yok,
    # üzerine konan title görünmezdi.
    return (f"<div class='cg-satir'>"
            f"<div class='{cip_sinif}'{baslik}>{nokta}{kisa_ad(cihaz)}</div>"
            f"<div class='cg-cizgi'>{cubuk}</div>"
            f"<div class='{dg_sinif}'>{dg}</div></div>")


def toplam_satir_html(ad: str, deger, cubuk: str, faz: str = "", gecis: tuple = None) -> str:
    """Grubun TOPLAMINI gösteren vurgulu satır (ör. ŞEBEKE = 4 trafo)."""
    dg = "—" if deger is None else (akan(deger, 1, faz or ad, *(gecis or ()))
                                    + "<span class='cg-br'>kW</span>")
    return (f"<div class='cg-satir cg-ust-satir'><div class='cg-cip cg-cip-ust'>{ad}</div>"
            f"<div class='cg-cizgi'>{cubuk}</div>"
            f"<div class='cg-dg cg-dg-ust'>{dg}</div></div>")


def olculmeyen_satir_html(ad: str, aciklama: str, sag: str = "veri çekilemiyor") -> str:
    """Canlı sayacı OLMAYAN kalem: kesik çizgi + nedeni.

    Bu satırlar "0 kW" göstermez. Sıfır, tüketimin durduğunu söyler;
    burada ölçüm yoktur — ikisi aynı şey değildir.
    """
    return (f"<div class='cg-satir cg-olcusuz'><div class='cg-cip cg-yok'>{ad}</div>"
            f"<div class='cg-bos'><span class='cg-tire'></span>"
            f"<span class='cg-bos-not'>{aciklama}</span>"
            f"<span class='cg-tire'></span></div>"
            f"<div class='cg-dg cg-dg-yok'>{sag}</div></div>")


def grup_html(baslik: str, aciklama: str, satirlar: str, toplam_kw,
              okunan: int, olcusuz: int = 0, yukseklik: int = 430, birim: str = "kW",
              gecis: tuple = None) -> str:
    """Bir grup kartı. Liste uzarsa KART değil liste kayar."""
    _t = '—' if toplam_kw is None else akan(toplam_kw, 1, 'grup-' + baslik, *(gecis or ())) + ' ' + birim
    ust = f"<div class='cg-toplam'>{_t}</div>"
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


def ozet_ikili_kart_html(parcalar: list) -> str:
    """Tek kart içinde yan yana iç kartlar (ör. TRAFO TOPLAM | ÜRETİM TOPLAM).

    parcalar: [(etiket, deger_html, alt, canli), ...]
    """
    nabiz = "<span class='cg-nabiz'></span>"
    ic = "".join(
        "<div class='cg-ic'><div class='cg-ozet-et'>" + (nabiz if canli else "") + etiket + "</div>"
        "<div class='cg-ozet-dg'>" + deger + "</div><div class='cg-ozet-alt'>" + alt + "</div></div>"
        for etiket, deger, alt, canli in parcalar)
    return f"<div class='cg-ozet cg-ozet-ikili'>{ic}</div>"


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
/* İki iç kartlı özet (TRAFO TOPLAM | ÜRETİM TOPLAM): şeritte iki sütun kaplar */
.cg-ozet-ikili{grid-column:span 2; display:grid; grid-template-columns:1fr 1fr; gap:8px; padding:7px;}
.cg-ic{background:#f6f8fc; border:1px solid rgba(24,26,30,.08); border-radius:12px; padding:7px 11px; min-width:0;}
@media (max-width:560px){ .cg-ozet-ikili{grid-column:span 1; grid-template-columns:1fr;} }

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
/* Izgara LİSTEDE, satırda değil: sütunlar bütün satırlarda ORTAK olsun.
   Her satır kendi ızgarası olsaydı uzun adlı satır geniş, kısa adlı dar
   çıkar ve çizgiler satırdan satıra kayardı. Satırlar display:contents ile
   bu ızgaraya katılır. */
.cg-liste{flex:1 1 auto; min-height:0; overflow-y:auto; padding-right:8px;
  display:grid; grid-template-columns:minmax(86px,max-content) minmax(60px,1fr) 92px;
  column-gap:10px; align-items:center; align-content:start;
  scrollbar-width:thin; scrollbar-color:#cdd5e2 transparent;}
.cg-liste::-webkit-scrollbar{width:7px;}
.cg-liste::-webkit-scrollbar-thumb{background:#cdd5e2; border-radius:4px;}
/* Ad sütunu İÇERİĞE göre genişler (max-content): "2BK-MCC-D01" gibi uzun
   adlar sabit 104px'e sığmayıp "2BK-MCC-D0…" diye kesiliyordu (21.10.2026).
   Çizgiye en az 60px bırakılır ki uzun bir ad grafiği yutmasın. */
.cg-satir{display:contents;}
.cg-liste > .cg-satir > *{padding:10px 0; border-bottom:1px solid rgba(24,26,30,.06);}
.cg-liste > .cg-satir:last-child > *{border-bottom:0;}
.cg-cip{font-size:11px; font-weight:600; color:#0f1f3d; background:#f6f7f9;
  border:1px solid rgba(24,26,30,.12); border-radius:9px; padding:6px 5px; text-align:center;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
.cg-cip.cg-yok{color:#8b93a3; background:#f3f3f4; border-style:dashed;}
.cg-cip-ust{font-weight:700; background:#eef3fb; border-color:#cddcf1; color:#133273;}
.cg-dg-ust{font-size:16px;}
.cg-cizgi{height:28px; display:flex; align-items:center;}

/* ── Yük çubuğu: iz + dolgu, şeritler akar, üstünden parıltı geçer ── */
.cg-iz{width:100%; height:8px; background:#e2e8f0; border-radius:4px;
  overflow:hidden; position:relative; box-shadow:inset 0 1px 2px rgba(0,0,0,.06);}
.cg-dolgu{height:100%; border-radius:4px; position:relative; overflow:hidden;
  transition:width .6s cubic-bezier(.4,0,.2,1), background-color .6s ease;
  background-image:linear-gradient(45deg,
    rgba(255,255,255,.24) 25%, transparent 25%, transparent 50%,
    rgba(255,255,255,.24) 50%, rgba(255,255,255,.24) 75%, transparent 75%, transparent);
  background-size:16px 16px; animation:cgSerit .85s linear infinite;}
@keyframes cgSerit{0%{background-position:0 0;} 100%{background-position:16px 0;}}
.cg-dolgu::after{content:""; position:absolute; top:0; left:0; right:0; bottom:0;
  background:linear-gradient(90deg, rgba(255,255,255,0) 0%,
    rgba(255,255,255,.45) 50%, rgba(255,255,255,0) 100%);
  transform:translateX(-100%);
  animation:cgParilti 2.2s infinite cubic-bezier(.4,0,.2,1); pointer-events:none;}
@keyframes cgParilti{0%{transform:translateX(-100%);} 55%,100%{transform:translateX(100%);}}
.cg-dg{font-size:15px; font-weight:700; color:#133273; text-align:right; white-space:nowrap;}
.cg-dg.cg-dg-yok{font-size:10.5px; font-weight:600; color:#9aa2b1;}
.cg-br{font-size:9.5px; font-weight:500; color:#46536b; margin-left:2px;}

/* ── doğrulama noktası: cihaz adının SOLUNDA, yanıp söner ── */
.cg-dot{display:inline-block; width:6px; height:6px; border-radius:50%;
  margin-right:6px; vertical-align:middle; animation:cgNabiz 2.2s ease-in-out infinite;}
.cg-dot-ok{background:#0ca30c;}      /* kWh sayacıyla doğrulandı */
.cg-dot-bekle{background:#fab219;}   /* doğrulanmadı / sayaç farkından */

/* ── ölçülemeyen kalem: kesik çizgi + nedeni ── */
/* min-width:0 + kesme: uzun not sağdaki "veri çekilemiyor" yazısının
   üstüne taşıyordu (26.10.2026). */
.cg-bos{height:28px; display:flex; align-items:center; gap:7px; min-width:0; overflow:hidden;}
.cg-bos .cg-tire{flex:1 1 8px; min-width:8px; border-top:1.6px dashed #cfd5df;}
.cg-bos-not{font-size:10px; color:#9aa2b1; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; min-width:0; flex:0 1 auto;}
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

# ── Saniyelik akış ───────────────────────────────────────────────────────
# Sunucu ekranı 3-10 sn'de bir çiziyor (sayfaya göre); saha 15 sn'de bir
# ölçüm yazıyor. Tarayıcı .canli-sayi ile işaretli sayıları her saniye
# günceller. İki kip var:
#
#   "gecis" (GERÇEK SİSTEM) — sayı, sahadan gelen ÖNCEKİ ölçümden SON ölçüme
#       iki ölçüm arasındaki süre boyunca saniye saniye ilerler, son ölçüme
#       varınca durur. Ekranda görünen her değer iki gerçek ölçümün arasında
#       kalır; yeni değer UYDURULMAZ (kullanıcı kararı 25.10.2026). Bedeli:
#       ekran son ölçüme en geç bir ölçüm aralığı (~15 sn) içinde ulaşır.
#       Önceki ölçüm bilinmiyorsa (sayfa yeni açıldı) sayı olduğu gibi durur.
#   "dalga" (YALNIZ SUNUM) — örnek veri sunucunun değeri etrafında yumuşakça
#       oynatılır. Gerçek sistemde kullanılmaz.

GECIS_SURE_ALT, GECIS_SURE_UST = 3.0, 60.0   # ölçüm aralığı bu bandın dışındaysa kırpılır


def gecis_suresi(t_onceki, t_son):
    """İki ölçüm arasındaki süre (sn), makul banda kırpılmış. Bilinmiyorsa None."""
    if t_onceki is None or t_son is None or t_son <= t_onceki:
        return None
    return max(GECIS_SURE_ALT, min(GECIS_SURE_UST, float(t_son - t_onceki)))


def seri_gecis(seri: dict):
    """Serideki son iki GERÇEK ölçüm: ({cihaz: önceki değer}, son zaman, süre).

    Seri aynı ölçüm zamanını iki kez eklemediği için son iki nokta sahadan
    gelen son iki ayrı ölçümdür. Yetersizse ({}, None, None) — sayı sabit kalır.
    """
    zamanlar = seri.get("zamanlar") or []
    if len(zamanlar) < 2:
        return {}, None, None
    t_son, t_onc = zamanlar[-1].timestamp(), zamanlar[-2].timestamp()
    sure = gecis_suresi(t_onc, t_son)
    if not sure:
        return {}, None, None
    onceki = {c: d[-2] for c, d in (seri.get("cihazlar") or {}).items()
              if len(d) >= 2 and d[-2] is not None and d[-1] is not None}
    return onceki, t_son, sure


def grup_gecis(onceki: dict, degerler: dict, cihazlar: list, t, sure):
    """Grubun (önceki toplam, t, süre) geçişi — önceki ölçümü olmayan sayaç
    son değeriyle sayılır; önceki hiç yoksa None."""
    if not t or not any(c in onceki for c in cihazlar):
        return None
    oku = [c for c in cihazlar if degerler.get(c) is not None]
    if not oku:
        return None
    return (sum(onceki.get(c, degerler[c]) for c in oku), t, sure)


def gecis_izle(durum: dict, anahtar, deger, t) -> dict:
    """Bir kalemin ÖNCEKİ ve SON gerçek ölçümünü tutar. SAF fonksiyon.

    durum: oturumda saklanan sözlük (yerinde güncellenir).
    Döner {"o": önceki, "d": son, "t": son ölçüm zamanı, "s": geçiş süresi};
    ölçüm zamanı değişmediyse önceki/son korunur (sayfa yeniden çizilse de
    aynı ölçüm "yeni" sayılmaz). Değer yoksa None.
    """
    if deger is None or t is None:
        return None
    eski = durum.get(anahtar)
    if eski is None:
        yeni = {"o": None, "d": float(deger), "t": float(t), "ot": None}
    elif eski["t"] != float(t):
        yeni = {"o": eski["d"], "d": float(deger), "t": float(t), "ot": eski["t"]}
    else:
        yeni = eski
    durum[anahtar] = yeni
    return {"o": yeni["o"], "d": yeni["d"], "t": yeni["t"], "s": gecis_suresi(yeni["ot"], yeni["t"])}


def akan(deger, ond: int = 1, faz: str = "", onceki=None, t=None, sure=None) -> str:
    """Sayıyı akış betiğinin bulacağı span içinde yazar.

    onceki/t/sure verilirse (gerçek ölçüm geçişi) "gecis" kipi sayıyı
    onceki → deger arasında ilerletir; verilmezse sayı sabit kalır.
    """
    ek = ""
    if onceki is not None and t is not None and sure:
        ek = f" data-onceki='{float(onceki):.3f}' data-t='{float(t):.3f}' data-sure='{float(sure):.1f}'"
    return (f"<span class='canli-sayi' data-deger='{float(deger):.3f}' "
            f"data-ond='{ond}' data-faz='{faz}'{ek}>{tr_sayi(deger, ond)}</span>")


def akis_betigi(harita_taban: dict = None, mod: str = "dalga") -> str:
    """.canli-sayi öğelerini (ve verilirse harita penceresini) saniyede bir günceller.

    harita_taban: {lok: {"sebeke": x, "kojen": y}} — x/y ya sayı ya da
    {"o": önceki, "d": son, "t": ölçüm zamanı (epoch), "s": geçiş süresi}.
    Betik her çizimde yeniden kurulur; önceki aralık kapatılır ki iki sayaç
    üst üste çalışmasın. Geçiş başlangıçları sayfa yeniden çizilse de korunur.
    """
    import json
    taban = harita_taban or {}
    return """
<script>
(function () {
  var taban = %s, MOD = %s;
  var W = window.parent;
  if (W.__synAkis) { W.clearInterval(W.__synAkis); }
  W.__synGecisBas = W.__synGecisBas || {};
  function faz(s) { var h = 0; for (var i = 0; i < s.length; i++) { h = (h * 31 + s.charCodeAt(i)) %% 1000; } return h / 1000 * 6.2832; }
  function carpan(s, t) { var p = faz(s); return 1 + 0.025 * Math.sin(t / 9 + p) + 0.012 * Math.sin(t / 2.7 + 2 * p) + 0.006 * Math.sin(t / 1.1 + 3 * p); }
  function yaz(x, ond) { return x.toLocaleString('tr-TR', {minimumFractionDigits: ond, maximumFractionDigits: ond}); }
  // GERÇEK: önceki → son ölçüm arası doğrusal geçiş; son ölçümden ileri GİTMEZ
  function gecis(anahtar, o, d, t, s, simdi) {
    if (o == null || t == null || !s) { return d; }
    // Anahtar başına YALNIZ son ölçüm tutulur (uzun açık ekranda bellek büyümesin)
    var b = W.__synGecisBas[anahtar];
    if (!b || b.t !== String(t)) { b = W.__synGecisBas[anahtar] = {t: String(t), bas: simdi}; }
    var f = Math.min(1, Math.max(0, (simdi - b.bas) / s));
    return o + (d - o) * f;
  }
  function harita_deger(lok, alan, x, simdi) {
    if (x == null) { return null; }
    if (typeof x === 'number') { return MOD === 'dalga' ? x * carpan(lok, simdi) : x; }
    return gecis('harita|' + lok + '|' + alan, x.o, x.d, x.t, x.s, simdi);
  }
  function adim() {
    var d; try { d = W.document; } catch (e) { return; }
    var simdi = Date.now() / 1000;
    d.querySelectorAll('.canli-sayi').forEach(function (el) {
      var v = parseFloat(el.getAttribute('data-deger'));
      if (isNaN(v)) { return; }
      var ond = parseInt(el.getAttribute('data-ond') || '0', 10), fz = el.getAttribute('data-faz') || '';
      if (MOD === 'dalga') { el.textContent = yaz(v * carpan(fz, simdi), ond); return; }
      var o = el.getAttribute('data-onceki');
      el.textContent = yaz(gecis(fz, o == null ? null : parseFloat(o), v,
                                 el.getAttribute('data-t'), parseFloat(el.getAttribute('data-sure')), simdi), ond);
    });
    var lokler = Object.keys(taban);
    if (!lokler.length) { return; }
    var veri = {};
    lokler.forEach(function (lok) {
      var s = harita_deger(lok, 'sebeke', taban[lok].sebeke, simdi), k = harita_deger(lok, 'kojen', taban[lok].kojen, simdi);
      veri[lok] = {sebeke: s == null ? null : yaz(s, 0), kojen: k == null ? null : yaz(k, 0)};
    });
    d.querySelectorAll('iframe[src^="data:text/html;base64"]').forEach(function (f) {
      try { f.contentWindow.postMessage({tip: 'synapse-canli', veri: veri}, '*'); } catch (e) {}
    });
  }
  adim();
  W.__synAkis = W.setInterval(adim, 1000);
})();
</script>
""" % (json.dumps(taban, ensure_ascii=False), json.dumps(mod))
