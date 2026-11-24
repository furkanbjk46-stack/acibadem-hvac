# -*- coding: utf-8 -*-
"""
ÇARK ANA EKRANI
===============

Synapse'in varsayılan ana ekranı: sunumda 17.11.2026'dan, canlıda 23.11.2026'dan beri
(app_merkez._cark_arayuz). Geri dönüş: SYNAPSE_ESKI_ARAYUZ=1 → eski üç sütun düzeni
(bu modül hiç yüklenmez). Dosya adındaki "_demo" tarihseldir.

DÜZEN (soldan sağa, tek ekran, sayfa kaydırması yok)
  * Logo dairesi: repodaki Acıbadem "A" işareti (haritadaki Genel Müdürlük
    logosuyla aynı yol, GM_A) + ACIBADEM yazısı; etrafında yavaş dönen yörüngeler.
  * 5 cam kart: Global Özet kalemleri (Toplam Enerji, Doğalgaz, Soğutma, Su,
    Kojen Üretim). Tıklama → mevcut gizli `gizli_ozet_<k>` düğmesi (özet detay).
  * Çark: hastaneler bir YAY üzerinde; ortadaki öğe büyük ve net, uçlara doğru
    küçülüp solar. Tekerlek, sol tık sürükleme, dokunmatik (pointer events),
    sağdaki ray; bırakınca atalet + en yakın öğeye yapışma. Ortadaki = seçili;
    seçiliye tekrar tık / çift tık / Enter / "Detay" → `gizli_detay_<lok>`.
  * Kartlardan çarka ince eğri ışık çizgileri (SVG; akan ışık animasyonu).
  * Sağ cam panel: seçili lokasyonun mevcut verileri (küçük yazı).
  * Alt orta: Sunucu Ayarları (a.ayar-ac → mevcut ayarlar paneli), Sistem
    (mevcut Yönetim düğmesi), Oturumu Kapat (mevcut Çıkış düğmesi).
  * Sağ üst: Uyarılar / OTO SET · Saha / Harita — eski sağ sütun ve harita
    sütunu (Streamlit öğeleri olduğu gibi) açılır katman olarak gösterilir.

CANLI SAYILAR
  Sayılar `.canli-sayi` (data-deger / data-ond / data-faz): saniyelik akış
  (canli_izleme.akis_betigi) yazıyı günceller. faz "ck-<alan>-<lok>": aynı
  lokasyonun listedeki ve paneldeki sayısı aynı fazda akar. 15 sn tazelemede
  `tazele_betigi` data-deger'i yeniler (data-ck-lok / data-ck-alan). Özet
  kartları eski kartla AYNI öznitelikte (faz "ozet-<k>"): mevcut tazeleme yeniler.
  Değer yoksa sayı UYDURULMAZ: "—" / "kurulmadı" / "canlı sayaç yok".

RENKLER: tek blok — PALET_CSS (aşağıda). Değiştirmek için yalnız orayı düzenleyin.
"""

import html as _html
import json
import re

SURUM = 21  # app_merkez bu sayıyla açık süreçte modülü yeniden yükler

# Repodaki Acıbadem "A" işareti — app_merkez.py içindeki haritanın Genel
# Müdürlük logosuyla (var GM_A) aynı yol. Yeni logo çizilmez.
GM_A = "M17.8 83L50.1 17L82.3 83L73.4 83L50.1 35.5L26.9 83Z"

CANLI_ALANLAR = ("enerji", "sebeke", "trafo", "kojen", "sogutma", "dogalgaz", "su",
                 "dogalgaz_kojen", "dogalgaz_kazan")

# Kart / çark kalemleri — SIRA ÖNEMLİ (kullanıcı kararı 18.11.2026).
# (anahtar, etiket, birim, simge, özet detay sayfası anahtarı)
# Özet detay sayfası (ozet_karsilastirma) yalnız 5 kalemi tanır: şebeke → enerji,
# kojen / kazan doğalgazı → doğalgaz sayfasına gider.
KALEMLER = (
    ("enerji", "Anlık Toplam Tüketim", "kW", "enerji", "enerji"),
    ("sebeke", "Şebeke Tüketim", "kW", "sebeke", "enerji"),
    ("kojen", "Kojen Üretim", "kW", "kojen", "kojen"),
    ("dogalgaz_kojen", "Kojen Doğalgaz", "m³/h", "dogalgaz", "dogalgaz"),
    ("dogalgaz_kazan", "Kazan Doğalgaz", "m³/h", "kazan", "dogalgaz"),
    ("sogutma", "Soğutma", "kW", "sogutma", "sogutma"),
    ("su", "Su", "m³/h", "su", "su"),
)
# Çark satırındaki tek değer kutusunun küçük kalem etiketi
KISA_ETIKET = {"enerji": "toplam", "sebeke": "şebeke", "kojen": "kojen", "dogalgaz_kojen": "kojen gaz",
               "dogalgaz_kazan": "kazan gaz", "sogutma": "soğutma", "su": "su"}
# Gaz girişleri cihaz adından ayrılır (canli_guc.cihaz): DOGALGAZ-KOJEN* / DOGALGAZ-KAZAN*.
# Ayrılmamış tek gaz sayacı (ör. DOGALGAZ-ANA) bu iki kaleme YAZILMAZ ("sayaç yok").
GAZ_ONEK = {"dogalgaz_kojen": "DOGALGAZ-KOJEN", "dogalgaz_kazan": "DOGALGAZ-KAZAN"}

# Çarkın her iki yanında görünen öğe sayısı (JS'deki K ile aynı)
CARK_YARI = 7

# Lokasyonun bildirdiği OTO SET modları (app_merkez'deki etiketlerle aynı ad)
_CH_MOD = {"koc_soguk": "Koç soğuk", "serin": "Serin", "ilimli": "Ilımlı", "sicak": "Sıcak"}
_DIG_MOD = {"yogun_sogutma": "Yoğun soğutma", "sogutma": "Soğutma", "isitma": "Isıtma"}

# ── PALET (tek yer) ──────────────────────────────────────────────────────────
# Referansın koyu teal cam atmosferi + Acıbadem kurumsal tonları:
#   zemin   : teal-siyah (zemin-1..3) — referanstaki gibi
#   vurgu   : zümrüt/turkuaz (çizgiler, seçili kart, canlı nokta)
#   mavi    : Acıbadem mavisi (#2a78d6'nın koyu zemine uyarlanmış açığı)
#   lacivert: kurumsal lacivert — logo küresi
#   amber / kırmızı: yalnız uyarı rozetleri (sıcak, küçük)
# --ck-olcek: tüm boyutların tek çarpanı (1 = varsayılan, 0.9 = daha küçük).
PALET_CSS = """
  --ck-zemin-1:#03141a; --ck-zemin-2:#072a32; --ck-zemin-3:#0c3a44;
  --ck-cam:rgba(16,50,60,.62); --ck-cam-2:rgba(22,64,76,.32);
  --ck-cam-kenar:rgba(150,225,225,.14); --ck-cam-kenar-2:rgba(150,225,225,.32);
  --ck-vurgu:#2ec4b6; --ck-vurgu-acik:#86e8dc;
  --ck-mavi:#5b9bff; --ck-lacivert:#133273;
  --ck-metin:#e8f1f2; --ck-metin-2:#a6bcc0; --ck-metin-3:#6f8a8f;
  --ck-yesil:#3ddc97; --ck-amber:#f2b441; --ck-kirmizi:#f06a5a; --ck-gri:#7d8b90;
  --ck-cizgi:rgba(134,232,220,.26);
  --ck-olcek:1;
  --ck-u:calc(clamp(5px, min(.9vh, .5vw), 11px) * var(--ck-olcek));
  --ck-cekmece-gen:min(460px, 92vw);
  --ck-cekmece-ust:calc(var(--ck-u) * 5.4);
"""

# Kök: çark kabı olan ana sayfa; detay / özet / yönetim katmanında uygulanmaz
_KOK = ('body{ek}:has(.st-key-cark_demo):not(:has(.st-key-detay_gecis_katmani))'
        ':not(:has(.st-key-ozet_gecis_katmani)):not(:has(.st-key-yonetim_katmani))')
EKRAN_KOK = _KOK.format(ek="")
_ANA = '[data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret)'

_EKRAN_KURALLAR = """
§{ PALET background:var(--ck-zemin-1) !important; overflow:hidden !important; }
html:has(.st-key-cark_demo):not(:has(.st-key-detay_gecis_katmani)):not(:has(.st-key-ozet_gecis_katmani)):not(:has(.st-key-yonetim_katmani)){
  overflow:hidden !important; background:var(--ck-zemin-1, #03141a) !important; }
§ [data-testid="stAppViewContainer"], § [data-testid="stMain"]{ background:transparent !important; overflow:hidden !important; }
§ [data-testid="stMainBlockContainer"]{ height:100vh; height:100dvh; overflow:hidden !important; box-sizing:border-box; }
/* Streamlit üst şeridi tıklamayı yutmasın; eski sağ üst düğmeler ekran dışına
   (gizli düğme olarak çalışmaya devam eder; display:none KULLANILMAZ) */
§ header[data-testid="stHeader"]{ display:none !important; }
§ div.st-key-cikis_kutusu{ left:-20000px !important; right:auto !important; width:400px !important; }
§ .st-key-ck_gizli_detay{ position:fixed !important; left:-9999px !important; top:0 !important; width:1px !important; height:1px !important; overflow:hidden !important; }
/* Simülasyon etiketi koyu zeminde okunsun */
§ div:is([style*="position:fixed;top:10px;left:18px"], [style*="position: fixed; top: 10px; left: 18px"]){
  background:rgba(242,180,65,.14) !important; border-color:rgba(242,180,65,.45) !important; }
§ div:is([style*="position:fixed;top:10px;left:18px"], [style*="position: fixed; top: 10px; left: 18px"]),
§ div:is([style*="position:fixed;top:10px;left:18px"], [style*="position: fixed; top: 10px; left: 18px"]) *{ color:#f2c66d !important; }

/* Gizli sütunlar çizilmez (content-visibility): eski lokasyon listesi her zaman, harita ve
   OTO SET sütunu kapalıyken. Öğeler DOM'da kalır; gizli düğmeler ve betikler çalışır. */
§ ANA > [data-testid="stColumn"]:is(:nth-child(1), :nth-child(2), :nth-child(3)){ content-visibility:hidden; }
KONTROL ANA > [data-testid="stColumn"]:nth-child(3), UYARI ANA > [data-testid="stColumn"]:nth-child(3), HARITA ANA > [data-testid="stColumn"]:nth-child(2){ content-visibility:visible; }
/* ── Eski sağ sütun → ORTADA AÇILAN POP-UP (18.11.2026). İki ayrı kip:
   UYARI: yalnız Canlı Uyarılar (sütunun 1-2. öğesi)
   KONTROL: yalnız OTO SET kartı + Dış Hava & Chiller Set (uyarılar ve AI notu gizli) ── */
§ ANA > [data-testid="stColumn"]:nth-child(3){
  position:fixed !important; z-index:70; left:50%; top:9vh; max-height:80vh;
  width:min(560px, 92vw) !important; max-width:none !important;
  flex:none !important; box-sizing:border-box; overflow-y:auto !important; overflow-x:hidden;
  padding:calc(var(--ck-u) * 1.8) calc(var(--ck-u) * 1.8) calc(var(--ck-u) * 2) !important;
  background:linear-gradient(180deg, rgba(14,48,58,.97), rgba(5,24,30,.97)); border-radius:18px;
  border:1px solid rgba(134,232,220,.32);
  box-shadow:0 40px 90px -30px rgba(0,0,0,.85), 0 0 0 6px rgba(46,196,182,.06), inset 0 1px 0 rgba(255,255,255,.05);
  scrollbar-width:thin; scrollbar-color:rgba(134,232,220,.3) transparent;
  transform:translate(-50%, 14px) scale(.97); opacity:0; visibility:hidden; pointer-events:none;
  transition:transform .3s cubic-bezier(.2,.7,.2,1), opacity .22s ease, visibility 0s linear .3s; }
§ ANA > [data-testid="stColumn"]:nth-child(3) > [data-testid="stVerticalBlock"]{ max-height:none !important; overflow:visible !important; }
:is(KONTROL, UYARI) ANA > [data-testid="stColumn"]:nth-child(3){
  transform:translate(-50%, 0); opacity:1; visibility:visible; pointer-events:auto;
  transition:transform .3s cubic-bezier(.2,.7,.2,1), opacity .22s ease, visibility 0s; }
KONTROL ANA > [data-testid="stColumn"]:nth-child(3){ width:min(640px, 94vw) !important; }
UYARI ANA > [data-testid="stColumn"]:nth-child(3) > [data-testid="stVerticalBlock"] > :nth-child(n+3){ display:none !important; }
KONTROL ANA > [data-testid="stColumn"]:nth-child(3) > [data-testid="stVerticalBlock"] > :is(:nth-child(-n+4), :nth-child(n+10)){ display:none !important; }
UYARI ANA > [data-testid="stColumn"]:nth-child(3) div:is([style*="max-height:195px"], [style*="max-height: 195px"]){ max-height:none !important; }
/* Pop-up içindeki sınıf stilli kartlar (#fafaf8) → cam */
§ ANA > [data-testid="stColumn"]:nth-child(3) :is(.st-key-oto_set_karti, .st-key-dis_hava_karti){
  background:linear-gradient(180deg, rgba(24,68,78,.50), rgba(10,36,44,.55)) !important;
  border-color:var(--ck-cam-kenar) !important; box-shadow:0 18px 40px -26px rgba(0,0,0,.85), inset 0 1px 0 rgba(255,255,255,.05) !important; }

/* ── Harita sütunu: ortada açılan katman ── */
§ ANA > [data-testid="stColumn"]:nth-child(2){
  position:fixed !important; z-index:70; left:50%; top:9vh; height:76vh;
  width:min(1180px, 90vw) !important; max-width:none !important; flex:none !important; box-sizing:border-box;
  padding:calc(var(--ck-u) * 1.4) !important; display:flex !important; flex-direction:column;
  background:linear-gradient(180deg, rgba(14,48,58,.97), rgba(5,24,30,.97)); border-radius:18px;
  border:1px solid rgba(134,232,220,.32); box-shadow:0 40px 90px -30px rgba(0,0,0,.85);
  transform:translate(-50%, 0) scale(.97); opacity:0; visibility:hidden; pointer-events:none;
  transition:transform .3s ease, opacity .25s ease, visibility 0s linear .3s; }
HARITA ANA > [data-testid="stColumn"]:nth-child(2){
  transform:translate(-50%, 0); opacity:1; visibility:visible; pointer-events:auto;
  transition:transform .3s ease, opacity .25s ease, visibility 0s; }
§ ANA > [data-testid="stColumn"]:nth-child(2) > [data-testid="stVerticalBlock"]{ flex:1 1 auto; min-height:0;
  display:flex !important; flex-direction:column; }
§ ANA > [data-testid="stColumn"]:nth-child(2) [data-testid="stElementContainer"]:has(> iframe[srcdoc]){
  position:absolute !important; height:0 !important; overflow:hidden !important; pointer-events:none !important; }
§ ANA > [data-testid="stColumn"]:nth-child(2) [data-testid="stElementContainer"]:has(> iframe[src^="data:"]){
  flex:1 1 auto !important; height:auto !important; min-height:0; }
§ ANA > [data-testid="stColumn"]:nth-child(2) iframe[src^="data:"]{ display:block; height:100% !important; }
"""


def ekran_css() -> str:
    """Sayfa düzeyi kurallar (kaydırma kilidi, eski düğmeler, çekmece / harita
    katmanı). Yalnız çark kabının içinde basılır; canlı portalda hiç çağrılmaz."""
    k = (_EKRAN_KURALLAR.replace("PALET", PALET_CSS)
         .replace("KONTROL", _KOK.format(ek=".ck-kontrol-acik"))
         .replace("UYARI", _KOK.format(ek=".ck-uyari-acik"))
         .replace("HARITA", _KOK.format(ek=".ck-harita-acik"))
         .replace("ANA", _ANA).replace("§", EKRAN_KOK))
    # Pop-up içerikleri detay sayfasıyla AYNI koyu temada (detay_tema_demo.icerik_css)
    import detay_tema_demo as _dt
    if getattr(_dt, "SURUM", 0) < 25:   # açık süreçte eski modül önbellekte kalmasın
        import importlib
        _dt = importlib.reload(_dt)
    # Üç pop-up tek seçici listesiyle (üç kopya CSS yerine bir kopya; sayfa hafif kalsın)
    kapsam = (":is(" + _ANA + ' > [data-testid="stColumn"]:nth-child(3), '
              + _ANA + ' > [data-testid="stColumn"]:nth-child(2), .st-key-ayarlar_panel)')
    k += "\n" + _dt.icerik_css(EKRAN_KOK, kapsam, palet=False)   # palet gövdede tanımlı
    k += "\n" + _AYAR_POPUP.replace("§", EKRAN_KOK)
    return "<style>\n" + k + "</style>"


# Sunucu Ayarları: aynı yerde açılır, beyaz yerine koyu cam
_AYAR_POPUP = """
§.ayarlar-acik .st-key-ayarlar_panel{
  background:linear-gradient(180deg, rgba(14,48,58,.98), rgba(5,24,30,.98)) !important;
  border:1px solid rgba(134,232,220,.32) !important; box-shadow:0 40px 90px -30px rgba(0,0,0,.85) !important; }
§.ayarlar-acik::after{ background:rgba(2,10,14,.6) !important; }
§ .st-key-ayarlar_panel .ayar-ust b{ color:var(--ck-vurgu-acik) !important; }
§ .st-key-ayarlar_panel .ayar-kapat{ color:var(--ck-metin) !important; border-color:var(--ck-cam-kenar-2) !important;
  background:rgba(14,46,56,.9) !important; }
§ .st-key-ayarlar_panel .ayar-kapat:hover{ background:rgba(240,106,90,.5) !important; }
"""


def sahne_css() -> str:
    """Çark sahnesinin stil bloğu (seçiciler .ck-sahne altında).

    Genel kural (app_merkez) her div/span/p rengini !important ile koyu yapar.
    Sahnede renk --c değişkeniyle verilir: tek bir !important kuralı (iki sınıf
    derinliği) rengi --c'den alır; öğeler yalnız --c'yi değiştirir.
    """
    return """
<style>
@keyframes ckDon{ to{ transform:rotate(360deg); } }
@keyframes ckNefes{ 0%,100%{ transform:scale(1); } 50%{ transform:scale(1.03); } }
@keyframes ckAkis{ from{ stroke-dashoffset:100; } to{ stroke-dashoffset:0; } }
@keyframes ckNabiz{ 0%,100%{ box-shadow:0 0 0 0 rgba(61,220,151,.55); } 60%{ box-shadow:0 0 0 5px rgba(61,220,151,0); } }
@keyframes ckGiris{ from{ opacity:0; transform:translateY(8px); } to{ opacity:1; transform:none; } }

.ck-sahne.ck-sahne, .ck-sahne.ck-sahne :is(div,span,p,b,strong,small,label,a,i,em,li,input){
  color:var(--c) !important; }
.ck-sahne{ --c:var(--ck-metin);
  position:fixed; inset:0; z-index:40; box-sizing:border-box; overflow:hidden;
  /* logo | kartlar (en az ~19u: dar ekranda ikona büzülmesin) | çark | panel */
  display:grid; grid-template-columns:minmax(0,20fr) minmax(calc(var(--ck-u) * 19), 13fr) minmax(0,31fr) minmax(0,25fr);
  grid-template-rows:minmax(0,1fr) auto; column-gap:calc(var(--ck-u) * 1.6);
  padding:calc(var(--ck-u) * 5.4) calc(var(--ck-u) * 2.6) calc(var(--ck-u) * 1.3);
  font-size:max(10px, calc(var(--ck-u) * 1.3)); line-height:1.35;
  background:
    radial-gradient(ellipse 45% 60% at 13% 50%, rgba(46,196,182,.11), transparent 62%),
    radial-gradient(ellipse 40% 55% at 58% 48%, rgba(91,155,255,.07), transparent 66%),
    radial-gradient(ellipse 60% 50% at 92% 8%, rgba(46,196,182,.07), transparent 60%),
    linear-gradient(160deg, var(--ck-zemin-2) 0%, var(--ck-zemin-1) 55%, #020d11 100%); }
.ck-sahne *, .ck-sahne *::before, .ck-sahne *::after{ box-sizing:border-box; }
.ck-sahne a{ text-decoration:none !important; }

/* ── Bağlantı çizgileri ── */
.ck-sahne svg.ck-baglar{ position:absolute; inset:0; width:100%; height:100%; pointer-events:none; z-index:1; overflow:visible; }
.ck-sahne .ck-bag{ fill:none; stroke:var(--ck-cizgi); stroke-width:1; }
.ck-sahne .ck-bag.ck-bag-merkez{ stroke:rgba(134,232,220,.9); stroke-width:1.5; }
.ck-sahne .ck-bag-logo{ stroke:rgba(134,232,220,.38); }
.ck-sahne .ck-bag-logo.ck-bag-aktif{ stroke:rgba(134,232,220,.75); stroke-width:1.4; }
.ck-sahne .ck-akis{ fill:none; stroke:#c8fbf4; stroke-width:1.8; stroke-linecap:round; stroke-dasharray:2.5 97.5;
  animation:ckAkis 3.4s linear infinite; }

/* ── Logo dairesi ── */
.ck-sahne .ck-logo-alan{ grid-column:1; grid-row:1; position:relative; z-index:2; min-width:0;
  display:flex; flex-direction:column; align-items:center; justify-content:center; }
.ck-sahne .ck-disk{ position:relative; width:min(46vh, 18.5vw); aspect-ratio:1/1; border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  background:radial-gradient(circle, rgba(9,38,46,.95) 0%, rgba(6,28,35,.9) 50%, rgba(4,20,26,.55) 68%, transparent 72%);
  box-shadow:0 0 120px -30px rgba(46,196,182,.35); }
.ck-sahne .ck-yorunge{ position:absolute; border-radius:50%; will-change:transform; border:1px dashed rgba(134,232,220,.22);
  animation:ckDon 70s linear infinite; }
.ck-sahne .ck-yorunge.y1{ inset:21%; }
.ck-sahne .ck-yorunge.y2{ inset:12%; border-style:solid; border-color:rgba(134,232,220,.10); animation-duration:100s; animation-direction:reverse; }
.ck-sahne .ck-yorunge.y3{ inset:3%; border-color:rgba(91,155,255,.16); animation-duration:140s; }
.ck-sahne .ck-yorunge > i{ position:absolute; top:-3px; left:calc(50% - 3px); width:6px; height:6px; border-radius:50%;
  background:var(--ck-vurgu-acik); box-shadow:0 0 10px var(--ck-vurgu); }
.ck-sahne .ck-yorunge.y2 > i{ top:auto; bottom:-3px; background:var(--ck-mavi); box-shadow:0 0 10px var(--ck-mavi); }
/* Logo = haritadaki GENEL MÜDÜRLÜK rozeti: lacivert (#1f2559) yuvarlatılmış kare, beyaz A,
   çevrimiçi yeşili (#0ca30c) çerçeve, dışa yayılan yeşil halkalar, A'nın üstünden geçen ışık */
.ck-sahne .ck-kure{ position:relative; width:30%; aspect-ratio:1/1; border-radius:20%;
  display:flex; align-items:center; justify-content:center; animation:ckGmSuz 3s ease-in-out infinite;
  background:#1f2559; border:2.5px solid rgba(12,163,12,.55);
  box-shadow:0 2px 6px rgba(19,50,115,.35), 0 0 22px rgba(12,163,12,.45), 0 0 70px 6px rgba(12,163,12,.14); }
.ck-sahne .ck-kure::before, .ck-sahne .ck-kure::after{ content:""; position:absolute; left:50%; top:50%;
  width:112%; height:112%; border-radius:50%; border:2px solid #0ca30c; pointer-events:none;
  transform:translate(-50%,-50%) scale(.6); opacity:0; animation:ckGmHalka 2.4s ease-out infinite; }
.ck-sahne .ck-kure::after{ animation-delay:1.2s; }
@keyframes ckGmHalka{ 0%{ transform:translate(-50%,-50%) scale(.6); opacity:.85; } 100%{ transform:translate(-50%,-50%) scale(1.55); opacity:0; } }
@keyframes ckGmSuz{ 0%,100%{ transform:translateY(0); filter:drop-shadow(0 0 0 rgba(12,163,12,0)); }
  50%{ transform:translateY(-3px); filter:drop-shadow(0 0 11px rgba(12,163,12,.67)); } }
.ck-sahne .ck-a{ width:78%; height:78%; overflow:visible; }
.ck-sahne .ck-marka{ position:absolute; top:13%; left:0; right:0; text-align:center; line-height:1.15; }
.ck-sahne .ck-marka b{ display:block; font-size:max(13px, calc(var(--ck-u) * 2.1)); font-weight:800;
  letter-spacing:calc(var(--ck-u) * .55); --c:#ffffff; }
.ck-sahne .ck-marka span{ display:block; font-size:max(8px, calc(var(--ck-u) * 1.0)); letter-spacing:calc(var(--ck-u) * .4);
  --c:var(--ck-vurgu-acik); font-weight:600; }
.ck-sahne .ck-disk-alt{ position:absolute; bottom:12%; left:0; right:0; display:flex; flex-direction:column;
  align-items:center; gap:calc(var(--ck-u) * .5); }
.ck-sahne .ck-rozet{ display:inline-flex; align-items:center; gap:5px; padding:2px 8px; border-radius:5px;
  font-size:max(8px, calc(var(--ck-u) * 1.0)); font-weight:600; background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.09); --c:var(--ck-metin-2); white-space:nowrap; }
.ck-sahne .ck-sayim{ display:inline-flex; gap:8px; font-size:max(8px, calc(var(--ck-u) * 1.0)); --c:var(--ck-metin-2); }
.ck-sahne .ck-sayim i{ display:inline-block; width:7px; height:7px; border-radius:2px; margin-right:3px; vertical-align:0; }
.ck-sahne .ck-canli-etiket{ margin-top:calc(var(--ck-u) * 1.2); display:flex; align-items:center; gap:7px;
  font-size:max(9px, calc(var(--ck-u) * 1.1)); letter-spacing:1.6px; text-transform:uppercase; --c:var(--ck-metin-2); }
.ck-sahne .ck-canli-nokta{ width:7px; height:7px; border-radius:50%; background:var(--ck-yesil); animation:ckNabiz 2s ease-out infinite; }

/* ── 5 kart ── */
/* Logo ile kartlar arasında boşluk (bağlantı çizgileri görünsün, birbirine girmesin) */
.ck-sahne .ck-kartlar{ grid-column:2; grid-row:1; position:relative; z-index:2; min-width:0;
  margin-left:calc(var(--ck-u) * 3.2);
  display:flex; flex-direction:column; justify-content:center; gap:calc(var(--ck-u) * 1.05); }
.ck-sahne .ck-kart{ position:relative; display:flex; align-items:center; gap:calc(var(--ck-u) * 1.1); min-width:0;
  padding:calc(var(--ck-u) * .75) calc(var(--ck-u) * 1.1); border-radius:calc(var(--ck-u) * 1.2);
  background:var(--ck-cam); border:1px solid var(--ck-cam-kenar); cursor:pointer; user-select:none;
  box-shadow:0 12px 26px -18px rgba(0,0,0,.8), inset 0 1px 0 rgba(255,255,255,.04);
  transition:border-color .2s ease, transform .2s ease, box-shadow .2s ease, background .2s ease;
  animation:ckGiris .5s ease-out both; animation-delay:calc(var(--sira, 0) * 70ms); }
.ck-sahne .ck-kart:hover{ border-color:var(--ck-cam-kenar-2); transform:translateX(2px); }
.ck-sahne .ck-kart:focus-visible{ outline:1px solid var(--ck-vurgu-acik); outline-offset:2px; }
.ck-sahne .ck-kart.ck-aktif{ border-color:rgba(134,232,220,.7);
  background:linear-gradient(135deg, rgba(34,96,102,.62), rgba(14,46,56,.55));
  box-shadow:0 0 0 1px rgba(134,232,220,.22), 0 0 26px -6px rgba(46,196,182,.55), inset 0 0 22px -10px rgba(134,232,220,.45); }
.ck-sahne .ck-kart-ikon{ flex-shrink:0; display:flex; filter:saturate(.8) brightness(1.15); }
.ck-sahne .ck-kart-ikon .ai{ width:calc(var(--ck-u) * 2.5) !important; height:calc(var(--ck-u) * 2.5) !important; }
.ck-sahne .ck-kart-govde{ display:flex; flex-direction:column; min-width:0; }
.ck-sahne .ck-kart-sayi{ font-size:max(14px, calc(var(--ck-u) * 2.2)); font-weight:700; line-height:1.05;
  white-space:nowrap; font-variant-numeric:tabular-nums; --c:#ffffff; }
.ck-sahne .ck-kart-sayi small{ font-size:.52em; font-weight:600; margin-left:3px; --c:var(--ck-metin-2); }
.ck-sahne .ck-kart-etiket{ font-size:max(8.5px, calc(var(--ck-u) * 1.08)); --c:var(--ck-metin-2);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; }
.ck-sahne .ck-kart-ok{ margin-left:auto; flex-shrink:0; --c:var(--ck-metin-3); font-size:1.15em; line-height:1;
  padding:3px 7px; border-radius:7px; border:1px solid transparent; transition:all .2s ease; }
.ck-sahne .ck-kart-ok:hover{ --c:#ffffff; border-color:var(--ck-cam-kenar-2); background:rgba(46,196,182,.18); }
.ck-sahne .ck-kart-sayi{ font-size:max(13px, calc(var(--ck-u) * 1.95)) !important; }
/* Çarkta yalnız seçili kartın kalemi görünür (.ck-rz'den güçlü seçici: aşağıdaki
   .ck-sahne .ck-rz{display:inline-flex} bunu ezmesin) + Anlık Toplam seçiliyken kojen */
.ck-sahne .ck-rz.ck-deger, .ck-sahne .ck-rz.ck-koj-ek{ display:none; }
.ck-sahne[data-kalem="enerji"] .ck-rz.ck-koj-ek{ display:inline-flex; }
.ck-sahne .ck-rz-et{ font-style:normal; font-size:.82em; margin-left:3px; letter-spacing:.3px; --c:var(--ck-metin-3); }
.ck-sahne[data-kalem="enerji"] .ck-deger[data-kalem="enerji"]{ display:inline-flex; }
.ck-sahne[data-kalem="sebeke"] .ck-deger[data-kalem="sebeke"]{ display:inline-flex; }
.ck-sahne[data-kalem="kojen"] .ck-deger[data-kalem="kojen"]{ display:inline-flex; }
.ck-sahne[data-kalem="dogalgaz_kojen"] .ck-deger[data-kalem="dogalgaz_kojen"]{ display:inline-flex; }
.ck-sahne[data-kalem="dogalgaz_kazan"] .ck-deger[data-kalem="dogalgaz_kazan"]{ display:inline-flex; }
.ck-sahne[data-kalem="sogutma"] .ck-deger[data-kalem="sogutma"]{ display:inline-flex; }
.ck-sahne[data-kalem="su"] .ck-deger[data-kalem="su"]{ display:inline-flex; }
/* Değere göre sıralama: öğeler yeni yerlerine yumuşakça kayar */
.ck-sahne .ck-cark.ck-siralaniyor .ck-oge{ transition:transform .55s cubic-bezier(.2,.75,.15,1), opacity .4s ease; }
.ck-sahne .ck-sirala{ align-self:flex-end; margin:calc(var(--ck-u) * .4) calc(var(--ck-u) * 2.4) 0 0; padding:2px 9px; border-radius:99px;
  font-size:max(8.5px, calc(var(--ck-u) * 1)); --c:var(--ck-metin-2); border:1px solid var(--ck-cam-kenar); background:var(--ck-cam);
  cursor:pointer; position:relative; z-index:3; }
.ck-sahne .ck-sirala.ck-acik{ --c:#062018; background:var(--ck-vurgu); border-color:var(--ck-vurgu); font-weight:700; }
.ck-sahne .ck-kart.ck-pasif .ck-kart-sayi{ font-size:max(10px, calc(var(--ck-u) * 1.25)); --c:var(--ck-metin-3); font-weight:600; }
.ck-sahne .ck-kart.ck-pasif .ck-kart-ikon{ filter:grayscale(.7) opacity(.6); }

/* ── Çark ── */
.ck-sahne .ck-cark-alan{ grid-column:3; grid-row:1; position:relative; z-index:2; min-width:0; min-height:0;
  display:flex; flex-direction:column; }
.ck-sahne .ck-ara{ align-self:flex-end; display:flex; align-items:center; gap:7px; width:min(100%, calc(var(--ck-u) * 30));
  padding:calc(var(--ck-u) * .55) calc(var(--ck-u) * 1.2); margin-right:calc(var(--ck-u) * 2.4);
  border-radius:99px; background:var(--ck-cam); border:1px solid var(--ck-cam-kenar); }
.ck-sahne .ck-ara:focus-within{ border-color:var(--ck-cam-kenar-2); }
.ck-sahne .ck-ara svg{ width:13px; height:13px; flex-shrink:0; stroke:var(--ck-metin-3); fill:none; stroke-width:2; }
.ck-sahne input.ck-ara-kutu{ flex:1; min-width:0; background:transparent !important; border:0 !important; outline:0 !important;
  box-shadow:none !important; padding:0 !important; height:auto; font-size:max(10px, calc(var(--ck-u) * 1.2)); --c:var(--ck-metin); }
.ck-sahne input.ck-ara-kutu::placeholder{ color:var(--ck-metin-3); }
.ck-sahne .ck-ara-say{ font-size:max(8.5px, calc(var(--ck-u) * 1.0)); --c:var(--ck-metin-3); white-space:nowrap; }
.ck-sahne .ck-cark{ position:relative; flex:1 1 auto; min-height:0; touch-action:none; user-select:none;
  -webkit-user-select:none; cursor:grab; outline:none; margin-right:calc(var(--ck-u) * 2.4);
  margin-left:calc(var(--ck-u) * 4.5); /* kartlarla çark arasında boşluk: çizgiler yelpaze gibi açılsın */ }
.ck-sahne .ck-cark.ck-surukleniyor{ cursor:grabbing; }
.ck-sahne .ck-cark:focus-visible{ box-shadow:inset 0 0 0 1px rgba(134,232,220,.25); border-radius:12px; }
.ck-sahne .ck-oge{ position:absolute; left:0; top:0; transform-origin:0 50%; visibility:hidden; opacity:0;
  display:flex; align-items:center; gap:calc(var(--ck-u) * .9); padding:calc(var(--ck-u) * .35) calc(var(--ck-u) * 1.1) calc(var(--ck-u) * .35) 0;
  white-space:nowrap; will-change:transform, opacity; }
.ck-sahne .ck-oge::before{ content:""; position:absolute; z-index:-1; inset:-2px -6px -2px calc(var(--ck-u) * -1.2);
  border-radius:8px; opacity:0; transition:opacity .2s ease;
  background:linear-gradient(90deg, rgba(46,196,182,.20), rgba(46,196,182,.04) 70%, transparent);
  border:1px solid rgba(134,232,220,.22); }
.ck-sahne .ck-oge.ck-merkez::before{ opacity:1; }
.ck-sahne .ck-nokta{ width:calc(var(--ck-u) * 1.05); height:calc(var(--ck-u) * 1.05); border-radius:50%; flex-shrink:0;
  margin-left:calc(var(--ck-u) * -.52); background:#d8b56a; box-shadow:0 0 8px rgba(216,181,106,.6); }
.ck-sahne .ck-oge.ck-on .ck-nokta{ background:var(--ck-vurgu-acik); box-shadow:0 0 9px rgba(46,196,182,.75); }
.ck-sahne .ck-oge.ck-off .ck-nokta{ background:var(--ck-kirmizi); box-shadow:0 0 9px rgba(240,106,90,.65); }
.ck-sahne .ck-oge.ck-yok .ck-nokta{ background:var(--ck-gri); box-shadow:none; }
.ck-sahne .ck-oge.ck-merkez .ck-nokta{ box-shadow:0 0 0 3px rgba(134,232,220,.18), 0 0 14px var(--ck-vurgu); }
.ck-sahne .ck-oge-ic{ display:flex; flex-direction:column; gap:3px; }
.ck-sahne .ck-ad{ font-size:max(10px, calc(var(--ck-u) * 1.35)); font-weight:600; letter-spacing:.4px; --c:var(--ck-metin); }
.ck-sahne .ck-oge.ck-merkez .ck-ad{ --c:#ffffff; text-shadow:0 0 14px rgba(134,232,220,.45); }
.ck-sahne .ck-sira{ font-size:.72em; margin-left:5px; --c:var(--ck-metin-3); font-weight:600; }
.ck-sahne .ck-rozetler{ display:flex; align-items:center; gap:4px; }
.ck-sahne .ck-rz{ display:inline-flex; align-items:baseline; gap:3px; padding:1px 5px; border-radius:4px;
  font-size:max(8px, calc(var(--ck-u) * .98)); background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.08);
  --c:var(--ck-metin-2); white-space:nowrap; font-variant-numeric:tabular-nums; }
.ck-sahne .ck-rz b{ font-weight:700; --c:var(--ck-metin); }
.ck-sahne .ck-rz-koj b{ --c:#9fe9c8; }
.ck-sahne .ck-rz-yok{ --c:var(--ck-metin-3); font-style:italic; }
.ck-sahne .ck-rz-off{ --c:#ffb3a8; background:rgba(240,106,90,.12); border-color:rgba(240,106,90,.3); }
.ck-sahne .ck-rz-uy{ font-weight:700; }
.ck-sahne .ck-rz-uy.ck-r{ --c:#ffd0c9; background:rgba(240,106,90,.22); border-color:rgba(240,106,90,.45); }
.ck-sahne .ck-rz-uy.ck-y{ --c:#ffe3a8; background:rgba(242,180,65,.20); border-color:rgba(242,180,65,.45); }
/* Durum kutucukları: aralıklı, "/" yönünde eğik paralelkenar (19.11.2026) */
.ck-sahne .ck-cubuk{ display:inline-flex; gap:calc(var(--ck-u) * .35); padding:0 calc(var(--ck-u) * .2); }
.ck-sahne .ck-cubuk i{ width:calc(var(--ck-u) * .62); height:calc(var(--ck-u) * .75); border-radius:1px; background:rgba(255,255,255,.12);
  transform:skewX(-22deg); }
.ck-sahne .ck-oge.ck-on .ck-cubuk i{ background:var(--ck-yesil); }
.ck-sahne .ck-oge.ck-off .ck-cubuk i:first-child{ background:var(--ck-kirmizi); }
.ck-sahne .ck-oge.ck-on.ck-uyarili .ck-cubuk i:last-child{ background:var(--ck-amber); }
.ck-sahne .ck-oge.ck-suzuldu{ display:none !important; }
.ck-sahne .ck-bos{ position:absolute; inset:0; display:none; align-items:center; justify-content:center;
  --c:var(--ck-metin-3); font-size:max(10px, calc(var(--ck-u) * 1.2)); }
.ck-sahne .ck-cark.ck-bos-var .ck-bos{ display:flex; }
.ck-sahne .ck-ray{ position:absolute; right:0; top:calc(var(--ck-u) * 7); bottom:calc(var(--ck-u) * 4);
  width:calc(var(--ck-u) * 1.1); min-width:7px; border-radius:99px; background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.05); cursor:pointer; touch-action:none; }
.ck-sahne .ck-ray:hover{ background:rgba(255,255,255,.08); }
.ck-sahne .ck-ray-tutamak{ position:absolute; left:-1px; right:-1px; top:0; height:calc(var(--ck-u) * 5); border-radius:99px;
  background:linear-gradient(180deg, var(--ck-vurgu-acik), var(--ck-vurgu)); opacity:.7;
  box-shadow:0 0 12px rgba(46,196,182,.45); }

/* ── Sağ panel (seçili lokasyon) ── */
/* Panel alt çubuk satırına da uzanır: altı Sunucu/Sistem çubuğuyla aynı hizada (19.11.2026) */
.ck-sahne .ck-panel{ grid-column:4; grid-row:1 / -1; position:relative; z-index:2; min-height:0; display:flex; flex-direction:column;
  border-radius:calc(var(--ck-u) * 2); overflow:hidden;
  background:linear-gradient(180deg, rgba(24,68,78,.78), rgba(8,30,38,.84));
  border:1px solid var(--ck-cam-kenar);
  box-shadow:0 30px 60px -30px rgba(0,0,0,.7), inset 0 1px 0 rgba(255,255,255,.06); }
.ck-sahne .ck-panel-ic{ flex:1 1 auto; min-height:0; overflow-y:auto; overflow-x:hidden;
  padding:calc(var(--ck-u) * 1.7) calc(var(--ck-u) * 1.7) calc(var(--ck-u) * 1.4);
  font-size:max(9px, calc(var(--ck-u) * 1.12)); scrollbar-width:thin; scrollbar-color:rgba(134,232,220,.25) transparent; }
.ck-sahne .ck-p-bos{ height:100%; display:flex; align-items:center; justify-content:center; --c:var(--ck-metin-3); }
.ck-sahne .ck-p-ust{ display:flex; align-items:center; gap:7px; --c:var(--ck-metin-2); font-size:max(9px, calc(var(--ck-u) * 1.1)); }
.ck-sahne .ck-p-ust .ai{ width:calc(var(--ck-u) * 2) !important; height:calc(var(--ck-u) * 2) !important; }
.ck-sahne .ck-p-baslik{ margin-top:calc(var(--ck-u) * .8); font-size:max(14px, calc(var(--ck-u) * 2.1)); font-weight:600;
  line-height:1.2; --c:#ffffff; }
.ck-sahne .ck-p-alt{ margin-top:2px; --c:var(--ck-metin-2); }
.ck-sahne .ck-p-kutu{ margin-top:calc(var(--ck-u) * 1.1); padding:calc(var(--ck-u) * .9) calc(var(--ck-u) * 1.1);
  border-radius:calc(var(--ck-u) * 1.1); background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08); }
.ck-sahne .ck-p-durum{ display:flex; align-items:center; gap:calc(var(--ck-u) * 1); }
.ck-sahne .ck-p-durum-metin{ flex:1; min-width:0; --c:var(--ck-metin-2); }
.ck-sahne .ck-dr{ display:inline-block; padding:1px 7px; border-radius:5px; font-weight:700; font-size:.92em;
  letter-spacing:.4px; margin-bottom:3px; }
.ck-sahne .ck-dr.ck-on{ --c:#9ff3cd; background:rgba(61,220,151,.14); border:1px solid rgba(61,220,151,.4); }
.ck-sahne .ck-dr.ck-off{ --c:#ffb8ae; background:rgba(240,106,90,.15); border:1px solid rgba(240,106,90,.42); }
.ck-sahne .ck-dr.ck-yok{ --c:var(--ck-metin-2); background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); }
.ck-sahne .ck-p-dugme{ flex-shrink:0; display:inline-flex; align-items:center; gap:5px; padding:calc(var(--ck-u) * .6) calc(var(--ck-u) * 1.1);
  border-radius:8px; background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.12); cursor:pointer;
  font-weight:600; --c:var(--ck-metin); white-space:nowrap; transition:background .2s ease, border-color .2s ease; }
.ck-sahne .ck-p-dugme:hover{ background:rgba(46,196,182,.2); border-color:rgba(134,232,220,.45); }
.ck-sahne .ck-p-buyuk{ background:linear-gradient(135deg, rgba(46,196,182,.14), rgba(91,155,255,.06) 60%, rgba(255,255,255,.03));
  border-color:rgba(134,232,220,.2); }
.ck-sahne .ck-p-buyuk-ust{ display:flex; align-items:center; justify-content:space-between; gap:8px; --c:var(--ck-metin-2); }
.ck-sahne .ck-p-cip{ padding:1px 6px; border-radius:4px; font-size:.9em; font-weight:600; --c:#ffe3a8;
  background:rgba(242,180,65,.14); border:1px solid rgba(242,180,65,.4); white-space:nowrap; }
.ck-sahne .ck-p-buyuk-orta{ display:flex; align-items:flex-end; gap:calc(var(--ck-u) * 1.2); margin-top:4px; }
.ck-sahne .ck-p-sayi{ font-size:max(24px, calc(var(--ck-u) * 3.9)); font-weight:600; line-height:1; letter-spacing:-.5px;
  --c:#ffffff; font-variant-numeric:tabular-nums; white-space:nowrap; }
.ck-sahne .ck-p-sayi small{ font-size:.38em; font-weight:600; margin-left:4px; --c:var(--ck-metin-2); letter-spacing:0; }
.ck-sahne .ck-p-egilim{ font-size:.92em; font-weight:700; --c:var(--ck-metin-3); white-space:nowrap; padding-bottom:3px; }
.ck-sahne .ck-p-egilim.ck-artis{ --c:#ffb8ae; }
.ck-sahne .ck-p-egilim.ck-azalis{ --c:#9ff3cd; }
.ck-sahne .ck-grafik{ flex:1; min-width:0; height:calc(var(--ck-u) * 4.2); }
.ck-sahne .ck-grafik svg{ display:block; width:100%; height:100%; }
.ck-sahne .ck-grafik rect{ fill:rgba(134,232,220,.38); }
.ck-sahne .ck-grafik rect.ck-g-son{ fill:var(--ck-amber); }
.ck-sahne .ck-grafik-bos{ font-size:.9em; --c:var(--ck-metin-3); text-align:right; }
.ck-sahne .ck-p-not{ margin-top:4px; font-size:.86em; --c:var(--ck-metin-3); }
.ck-sahne .ck-p-izgara{ display:grid; grid-template-columns:1fr 1fr; gap:calc(var(--ck-u) * .8); margin-top:calc(var(--ck-u) * 1.0); }
.ck-sahne .ck-p-izgara.ck-p-izgara-3{ grid-template-columns:repeat(3, minmax(0, 1fr)); gap:calc(var(--ck-u) * .6); }
.ck-sahne .ck-p-izgara-3 .ck-p-hucre{ padding:calc(var(--ck-u) * .6) calc(var(--ck-u) * .75); }
.ck-sahne .ck-p-izgara-3 .ck-p-hucre b{ font-size:max(12px, calc(var(--ck-u) * 1.6)); }
.ck-sahne .ck-p-izgara-3 .ck-p-hucre .ai{ width:calc(var(--ck-u) * 1.6) !important; height:calc(var(--ck-u) * 1.6) !important; }
.ck-sahne .ck-p-izgara-3 .ck-p-hucre-et{ font-size:.9em; }
.ck-sahne .ck-p-bolum-not{ margin-left:auto; font-weight:500; letter-spacing:0; --c:var(--ck-metin-3); font-size:.9em; }
.ck-sahne .ck-p-olcum{ margin-top:4px; max-height:calc(var(--ck-u) * 19); overflow-y:auto; padding-right:4px;
  display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:4px 10px; align-items:start;
  scrollbar-width:thin; scrollbar-color:rgba(134,232,220,.28) transparent; }
.ck-sahne .ck-p-olc-kol{ display:flex; flex-direction:column; gap:4px; min-width:0; }
.ck-sahne .ck-p-og-b{ font-size:.82em; font-weight:700; letter-spacing:1.2px; --c:var(--ck-vurgu-acik); padding:2px 0 2px;
  border-bottom:1px solid rgba(134,232,220,.14); margin-bottom:2px; }
.ck-sahne .ck-p-oc{ display:flex; justify-content:space-between; gap:6px; padding:1px 0; font-size:.92em; --c:var(--ck-metin-2); }
.ck-sahne .ck-p-oc > span:last-child{ --c:var(--ck-metin); font-weight:600; font-variant-numeric:tabular-nums; white-space:nowrap; }
.ck-sahne .ck-p-oc small{ margin-left:2px; --c:var(--ck-metin-3); font-weight:500; }
.ck-sahne .ck-p-ocn{ display:inline-block; width:5px; height:5px; border-radius:50%; background:var(--ck-yesil); margin-right:5px; vertical-align:1px; }
.ck-sahne .ck-p-oc-bayat .ck-p-ocn{ background:#f59e0b; box-shadow:0 0 0 2px rgba(245,158,11,.22); }
.ck-sahne .ck-p-oc-bayat > span:last-child{ opacity:.6; }
.ck-sahne .ck-p-oto-ust{ display:flex; align-items:center; gap:calc(var(--ck-u) * .7); margin:4px 0 4px; flex-wrap:wrap; }
.ck-sahne .ck-p-oto-durum{ display:flex; flex-direction:column; line-height:1.15; margin-right:auto; }
.ck-sahne .ck-p-oto-durum b{ font-weight:800; letter-spacing:.6px; --c:#ffffff; }
.ck-sahne .ck-p-oto-durum span{ font-size:.86em; --c:var(--ck-amber); }
.ck-sahne .ck-p-oto .ck-p-dugme{ padding:3px 8px; font-size:.9em; gap:4px; }
.ck-sahne .ck-p-oto .ck-p-dugme .ai{ width:13px !important; height:13px !important; }
.ck-sahne .ck-anahtar{ position:relative; width:34px; height:19px; border-radius:19px; flex-shrink:0; cursor:pointer;
  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.18); transition:background .25s ease; }
.ck-sahne .ck-anahtar i{ position:absolute; top:2px; left:2px; width:13px; height:13px; border-radius:50%; background:#e8f1f2;
  transition:transform .25s ease; }
.ck-sahne .ck-anahtar.ck-acik{ background:var(--ck-yesil); border-color:var(--ck-yesil); box-shadow:0 0 10px rgba(61,220,151,.45); }
.ck-sahne .ck-anahtar.ck-acik i{ transform:translateX(15px); }
.ck-sahne .ck-anahtar.ck-kilit{ opacity:.5; cursor:not-allowed; }
.ck-sahne .ck-p-hucre{ padding:calc(var(--ck-u) * .8) calc(var(--ck-u) * 1.0); border-radius:calc(var(--ck-u) * 1);
  background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08); min-width:0; }
.ck-sahne .ck-p-hucre-ust{ display:flex; align-items:center; gap:6px; }
.ck-sahne .ck-p-hucre .ai{ width:calc(var(--ck-u) * 2) !important; height:calc(var(--ck-u) * 2) !important; flex-shrink:0; }
.ck-sahne .ck-p-hucre b{ font-size:max(13px, calc(var(--ck-u) * 1.9)); font-weight:600; --c:#ffffff; white-space:nowrap;
  font-variant-numeric:tabular-nums; }
.ck-sahne .ck-p-hucre b small{ font-size:.55em; --c:var(--ck-metin-2); margin-left:3px; }
.ck-sahne .ck-p-hucre-et{ margin-top:2px; --c:var(--ck-metin-2); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ck-sahne .ck-yok{ --c:var(--ck-metin-3); font-weight:500; }
.ck-sahne .ck-p-bolum{ display:flex; align-items:center; gap:7px; margin-top:calc(var(--ck-u) * 1.4);
  font-weight:700; letter-spacing:.6px; --c:var(--ck-metin); }
.ck-sahne .ck-p-bolum .ai{ width:calc(var(--ck-u) * 1.8) !important; height:calc(var(--ck-u) * 1.8) !important; }
.ck-sahne .ck-p-bolum a{ margin-left:auto; font-weight:600; letter-spacing:0; --c:var(--ck-vurgu-acik); cursor:pointer; }
.ck-sahne .ck-p-satir{ display:flex; justify-content:space-between; gap:10px; padding:3px 0;
  border-bottom:1px solid rgba(255,255,255,.06); --c:var(--ck-metin-2); }
.ck-sahne .ck-p-satir:last-child{ border-bottom:0; }
.ck-sahne .ck-p-satir > span:last-child{ --c:var(--ck-metin); font-weight:600; text-align:right; font-variant-numeric:tabular-nums; }
.ck-sahne .ck-p-satir .ck-iyi{ --c:#9ff3cd; } .ck-sahne .ck-p-satir .ck-kotu{ --c:#ffb8ae; } .ck-sahne .ck-p-satir .ck-dikkat{ --c:#ffe3a8; }
.ck-sahne .ck-p-uyari{ margin-top:4px; padding:4px 8px; border-radius:6px; border-left:2px solid var(--ck-amber);
  background:rgba(242,180,65,.08); --c:#f6e2b8; line-height:1.35; }
.ck-sahne .ck-p-uyari.ck-r{ border-left-color:var(--ck-kirmizi); background:rgba(240,106,90,.09); --c:#ffd2cb; }
.ck-sahne .ck-p-analiz{ --c:var(--ck-metin-2); line-height:1.5; }
.ck-sahne .ck-p-analiz b{ --c:var(--ck-metin); font-weight:600; }
/* Başlık kartı: ad solda, bağlantı durumu + Detay sağda (19.11.2026) */
.ck-sahne .ck-p-kafa{ display:flex; align-items:center; justify-content:space-between; gap:calc(var(--ck-u) * 1.2); margin-top:0; }
.ck-sahne .ck-p-kafa-sol{ flex:1 1 auto; min-width:0; }
.ck-sahne .ck-p-kafa .ck-p-baslik{ margin-top:calc(var(--ck-u) * .4); overflow:hidden; text-overflow:ellipsis; }
.ck-sahne .ck-p-kafa-sag{ flex-shrink:0; display:flex; flex-direction:column; align-items:flex-end; gap:calc(var(--ck-u) * .5); text-align:right; }
.ck-sahne .ck-p-son{ font-size:.86em; --c:var(--ck-metin-2); white-space:nowrap; }
/* Detaydan taşınan mini kartlar (HVAC & Bakım / Setler / Sistem sağlığı) */
.ck-sahne .ck-p-izgara.ck-p-izgara-4{ grid-template-columns:repeat(4, minmax(0, 1fr)); gap:calc(var(--ck-u) * .6); }
.ck-sahne .ck-p-mini{ padding:calc(var(--ck-u) * .6) calc(var(--ck-u) * .75); min-width:0; }
.ck-sahne .ck-p-mini .ck-p-hucre-et{ margin:0 0 3px; font-size:.8em; font-weight:700; letter-spacing:.6px; text-transform:uppercase; --c:var(--ck-metin-3); }
.ck-sahne .ck-p-mini .ck-p-hucre-ust{ align-items:flex-start; }
.ck-sahne .ck-p-mini .ai{ width:calc(var(--ck-u) * 1.6) !important; height:calc(var(--ck-u) * 1.6) !important; }
.ck-sahne .ck-p-mini b{ font-size:max(11px, calc(var(--ck-u) * 1.45)); white-space:normal; line-height:1.2; overflow-wrap:anywhere; }
.ck-sahne .ck-p-mini b small{ font-size:.75em; }
.ck-sahne .ck-p-saglik .ck-p-mini b{ font-size:max(10px, calc(var(--ck-u) * 1.12)); font-weight:700; }
.ck-sahne .ck-p-mini b.ck-r{ --c:#ffb8ae; } .ck-sahne .ck-p-mini b.ck-y{ --c:#ffe3a8; } .ck-sahne .ck-p-mini b.ck-g{ --c:#9ff3cd; }
.ck-sahne :is(.ck-p-mini-ac, .ck-p-bolum-ac) > summary{ list-style:none; cursor:pointer; }
.ck-sahne :is(.ck-p-mini-ac, .ck-p-bolum-ac) > summary::-webkit-details-marker{ display:none; }
.ck-sahne .ck-p-mini-ac > summary{ position:relative; padding-right:14px; }
.ck-sahne :is(.ck-p-mini-ac, .ck-p-bolum-ac) > summary::after{ content:"▾"; --c:var(--ck-metin-3); transition:transform .2s ease; }
.ck-sahne .ck-p-mini-ac > summary::after{ position:absolute; right:0; top:0; }
.ck-sahne .ck-p-bolum-ac > summary::after{ margin-left:6px; }
.ck-sahne :is(.ck-p-mini-ac, .ck-p-bolum-ac)[open] > summary::after{ transform:rotate(180deg); }
.ck-sahne .ck-p-mini-ac:hover, .ck-sahne .ck-p-mini-ac[open]{ border-color:var(--ck-cam-kenar-2); }
.ck-sahne .ck-p-mini-liste{ margin-top:calc(var(--ck-u) * .5); display:flex; flex-direction:column; gap:3px; max-height:calc(var(--ck-u) * 16); overflow-y:auto; }
.ck-sahne .ck-p-mini-liste .ck-p-uyari{ margin-top:0; padding:3px 6px; font-size:.86em; line-height:1.3; }
.ck-sahne .ck-p-bolum-ac .ck-p-acilir-say{ margin-left:8px; }
.ck-sahne .ck-p-acilir-say{ padding:0 7px; border-radius:99px; font-size:.86em; font-weight:700;
  --c:#ffd2cb; background:rgba(240,106,90,.16); border:1px solid rgba(240,106,90,.35); }
.ck-sahne .ck-p-acilir-say.ck-y{ --c:#ffe3a8; background:rgba(245,180,60,.14); border-color:rgba(245,180,60,.35); }
.ck-sahne .ck-p-acilir-ic{ max-height:calc(var(--ck-u) * 20); overflow-y:auto; }
.ck-sahne .ck-p-mini-alt{ margin-top:3px; font-size:.82em; line-height:1.25; --c:var(--ck-metin-3); overflow-wrap:anywhere; }

/* ── Sağ üst çipler, alt orta düğmeler ── */
.ck-sahne .ck-ust{ position:absolute; z-index:3; top:calc(var(--ck-u) * 1.3); right:calc(var(--ck-u) * 2.6);
  display:flex; gap:calc(var(--ck-u) * .8); }
.ck-sahne .ck-cip, .ck-sahne .ck-dugme{ display:inline-flex; align-items:center; gap:calc(var(--ck-u) * .7); cursor:pointer;
  border-radius:99px; font-weight:600; white-space:nowrap; --c:var(--ck-metin);
  background:rgba(14,46,56,.82); border:1px solid var(--ck-cam-kenar);
  transition:background .2s ease, border-color .2s ease; }
.ck-sahne .ck-cip{ padding:calc(var(--ck-u) * .55) calc(var(--ck-u) * 1.3); font-size:max(9.5px, calc(var(--ck-u) * 1.12)); }
.ck-sahne .ck-cip .ai, .ck-sahne .ck-dugme .ai{ width:calc(var(--ck-u) * 1.8) !important; height:calc(var(--ck-u) * 1.8) !important; }
.ck-sahne .ck-cip:hover, .ck-sahne .ck-dugme:hover{ background:rgba(46,196,182,.18); border-color:rgba(134,232,220,.45); }
.ck-sahne .ck-sayac{ min-width:18px; text-align:center; padding:0 5px; border-radius:99px; font-size:.92em; font-weight:800; }
.ck-sahne .ck-sayac.ck-r{ --c:#fff; background:rgba(240,106,90,.85); }
.ck-sahne .ck-sayac.ck-y{ --c:#2b1d00; background:var(--ck-amber); }
.ck-sahne .ck-sayac.ck-g{ --c:#062018; background:var(--ck-yesil); }
.ck-sahne .ck-alt{ grid-column:1 / -1; grid-row:2; justify-self:center; position:relative; z-index:3;
  display:flex; gap:calc(var(--ck-u) * .8); margin-top:calc(var(--ck-u) * 1.2); padding:calc(var(--ck-u) * .6);
  border-radius:99px; background:rgba(8,32,40,.86); border:1px solid var(--ck-cam-kenar);
  box-shadow:0 18px 40px -22px rgba(0,0,0,.8), 0 0 0 1px rgba(46,196,182,.05);
  }
.ck-sahne .ck-dugme{ padding:calc(var(--ck-u) * .75) calc(var(--ck-u) * 1.9); font-size:max(10px, calc(var(--ck-u) * 1.22)); }
/* Tema düğmesi: karanlıkta "Aydınlık"a geçişi, aydınlıkta "Karanlık"a geçişi gösterir */
.ck-sahne .ck-tema .ck-tema-koyu{ display:none; }
.ck-sahne .ck-dugme.ck-cikis:hover{ background:rgba(240,106,90,.2); border-color:rgba(240,106,90,.5); }

/* ── Açılır katman perdesi ── */
.ck-sahne .ck-perde{ position:absolute; inset:0; z-index:20; background:rgba(2,10,14,.6); opacity:0; pointer-events:none;
  transition:opacity .25s ease; }
body:is(.ck-kontrol-acik, .ck-harita-acik, .ck-uyari-acik) .ck-sahne .ck-perde{ opacity:1; pointer-events:auto; }
.ck-sahne .ck-katman-kapat{ position:absolute; z-index:21; display:none; align-items:center; justify-content:center;
  width:34px; height:34px; border-radius:50%; cursor:pointer; font-size:20px; line-height:1;
  background:rgba(14,46,56,.9); border:1px solid var(--ck-cam-kenar-2); --c:#ffffff; }
.ck-sahne .ck-katman-kapat:hover{ background:rgba(240,106,90,.5); }
/* Pop-up'ın sağ üst köşesinin hemen dışında */
body.ck-uyari-acik .ck-sahne .ck-katman-kapat{ display:flex; top:calc(9vh - 44px); right:calc(50% - min(280px, 46vw)); }
body.ck-kontrol-acik .ck-sahne .ck-katman-kapat{ display:flex; top:calc(9vh - 44px); right:calc(50% - min(320px, 47vw)); }
body.ck-harita-acik .ck-sahne .ck-katman-kapat{ display:flex; top:calc(9vh - 44px); right:calc(50% - min(590px, 45vw)); }

/* ── Dar ekran: kartlar üstte, çark ortada, panel altta; sahne kendi içinde kayar ── */
@media (max-width:900px){
  .ck-sahne{ display:flex; flex-direction:column; gap:14px; overflow-y:auto; overflow-x:hidden;
    padding:48px 16px 18px; --ck-u:6.5px; }
  .ck-sahne svg.ck-baglar{ display:none; }
  .ck-sahne .ck-ust{ position:static; justify-content:center; flex-wrap:wrap; order:-1; }
  .ck-sahne .ck-logo-alan{ flex:none; }
  .ck-sahne .ck-disk{ width:min(52vw, 220px); }
  .ck-sahne .ck-kartlar{ flex:none; display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; }
  .ck-sahne .ck-cark-alan{ flex:none; height:62vh; min-height:360px; }
  .ck-sahne .ck-ara{ align-self:stretch; width:auto; margin-right:calc(var(--ck-u) * 2.4); }
  .ck-sahne .ck-panel{ flex:none; overflow:visible; }
  .ck-sahne .ck-panel-ic{ overflow:visible; }
  .ck-sahne .ck-alt{ flex-wrap:wrap; justify-content:center; border-radius:16px; margin-top:0; }
}
@media (prefers-reduced-motion: reduce){
  .ck-sahne *, .ck-sahne *::before, .ck-sahne *::after{ animation:none !important; transition:none !important; }
}
</style>
"""


# ── Veri ──────────────────────────────────────────────────────────────────

def _sayi(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None   # NaN → None


def duz_metin(s) -> str:
    """Uyarı mesajı (HTML / kaçışlı gelebilir) → tek satır düz metin."""
    return " ".join(_html.unescape(re.sub(r"<[^>]*>", "", str(s or ""))).split())


def _json_sozluk(x) -> dict:
    if isinstance(x, str):
        try:
            import json as _js
            x = _js.loads(x)
        except Exception:
            x = {}
    return x if isinstance(x, dict) else {}


def _derece(x) -> str:
    return ("%g°C" % x) if isinstance(x, (int, float)) and not isinstance(x, bool) else "—"


def saha_ozeti(bakim_ozet, hvac_ozet) -> dict:
    """Lokasyon kartındaki HVAC & Bakım, Yürürlükteki Setler ve Sistem Sağlığı.
    Detay sayfasındaki (pages/lokasyon_detay.py) AYNI heartbeat alanları ve AYNI
    kurallar; yalnız düz veriye çevrilir (yeni sayı üretilmez)."""
    b, hv = _json_sozluk(bakim_ozet), _json_sozluk(hvac_ozet)

    def _ad(c):
        return duz_metin(c.get("ad", c.get("name", str(c))) if isinstance(c, dict) else c)

    ar_l, bk_l = b.get("arizali_cihazlar") or [], b.get("bakimda_cihazlar") or []
    kr, uy, nr = hv.get("kritik") or [], hv.get("uyari") or [], hv.get("normal") or []
    if kr or uy:
        hv_l = [["r", _ad(c), duz_metin(c.get("sorun", "") if isinstance(c, dict) else "")] for c in kr] \
             + [["y", _ad(c), duz_metin(c.get("sorun", "") if isinstance(c, dict) else "")] for c in uy]
        hk, hu = len(kr), len(uy)
    else:
        hv_l = [["r", _ad(c), ""] for c in ar_l]
        hk, hu = len(ar_l), 0
    s = {
        "ariza": int(b.get("toplam_ariza") or 0), "ariza_l": [_ad(c) for c in ar_l][:8],
        "bakim": int(b.get("toplam_bakim") or 0), "bakim_l": [_ad(c) for c in bk_l][:8],
        "hv_kritik": hk, "hv_uyari": hu, "hv_normal": len(nr), "hv_l": hv_l[:8],
        "set": None, "oto": None, "oz": None, "gb": None,
    }
    o = b.get("oto") if isinstance(b.get("oto"), dict) else {}
    st_ = o.get("setler") if isinstance(o.get("setler"), dict) else {}
    if st_:
        fcu = st_.get("A_BLOK_FCU_SET", st_.get("B_BLOK_FCU_SET"))
        ahu = st_.get("ZON1_KLIMA_SANTRALI_SET", st_.get("ZON2_KLIMA_SANTRALI_SET"))
        s["set"] = {"chiller": _derece(st_.get("chiller")), "ch_mod": _CH_MOD.get(o.get("chiller_mod"), "—"),
                    "kol": "%s / %s" % (_derece(st_.get("GUNDUZ_KOLLEKTOR_SET")), _derece(st_.get("GECE_KOLLEKTOR_SET"))),
                    "dig_mod": _DIG_MOD.get(o.get("diger_mod"), "—"),
                    "fcu": _derece(fcu), "ahu": _derece(ahu)}
    if o:
        sonuc = str(o.get("sonuc", ""))
        dg = (o.get("dogrulama") or {}).get("sonuc")
        dgm = {"uygulanmadi": ["r", "Set cihazda UYGULANMADI"], "bekliyor": ["y", "Doğrulama bekleniyor"],
               "uygulandi": ["g", "Setler cihazda doğrulandı"]}.get(dg)
        s["oto"] = {"iyi": sonuc in ("yazildi", "gecis_yok", "kapali", "mesgul"),
                    "metin": duz_metin(o.get("metin") or sonuc or "—"),
                    "zaman": str(o.get("zaman") or "")[11:16], "dg": dgm}
    oz = b.get("oz_test") or {}
    if isinstance(oz, dict) and oz:
        s["oz"] = {"gecti": oz.get("durum") == "GECTI",
                   "metin": "%s/%s %s" % (oz.get("gecen"), oz.get("toplam"), "geçti" if oz.get("durum") == "GECTI" else "KALDI"),
                   "kalan": ", ".join(str(d).replace("test_", "").replace(".py", "")
                                      for d in (oz.get("kalan_dosyalar") or [])[:2]),
                   "zaman": str(oz.get("zaman") or "")[:16].replace("T", " ")}
    gb = b.get("geri_bildirim") or {}
    if isinstance(gb, dict) and gb:
        hz = gb.get("ogrenmeye_hazir_kural") or []
        s["gb"] = {"sayi": int(gb.get("geri_bildirim") or 0), "uyg": int(gb.get("uygulandi") or 0),
                   "red": int(gb.get("uygulanmadi") or 0),
                   "alt": "%s öneri kaydı · %s" % (gb.get("kayit", 0),
                                                   ("öğrenmeye hazır: " + ", ".join(map(str, hz[:2]))) if hz
                                                   else "öğrenme beklemede")}
    return s


def kw_metin(x, ond=0):
    """1234.5 → '1.235' (app_merkez.kw_metin ile aynı biçim); None → '—'."""
    if x is None:
        return "—"
    s = f"{x:,.{ond}f}"
    if ond:
        tam, kesir = s.split(".")
        return tam.replace(",", ".") + "," + kesir
    return s.replace(",", ".")


def veri_hazirla(hastaneler: dict, sira: list, canli: dict, baglanti: dict, sicaklik: dict,
                 oto_saglik: dict, oto_sorun, uyari_map: dict, genel: dict, cihazlar: dict = None,
                 saha: dict = None) -> dict:
    """Sahnenin (çark + panel) verisi. SAF fonksiyon; yalnız gelen veriyi düzenler.

    sira      : lokasyon kimlikleri çarktaki sırayla
    canli     : CANLI ({lok: {"enerji", "sebeke", ...}}) — canlı ölçümü olmayan lok yok
    baglanti  : {lok: (çevrimiçi mi, kaç dk önce | None)}
    sicaklik  : {lok: {"set", "dis"}} (chiller set / dış hava, günlük veri)
    oto_saglik: {lok: bakim_ozet.oto} ; oto_sorun(o) → (kod, metin) | (None, None)
    uyari_map : {lok: [(önem, mesaj), ...]}
    genel     : OTO SET genel durumu, dış hava, zaman vb. (olduğu gibi aktarılır)
    """
    lok = {}
    sayim = {"on": 0, "off": 0, "yok": 0}
    for i, lid in enumerate(sira):
        h = hastaneler.get(lid) or {}
        on, dk = baglanti.get(lid, (False, None))
        durum = "yok" if dk is None else ("on" if on else "off")
        sayim[durum] += 1
        c = canli.get(lid) or {}
        o = oto_saglik.get(lid)
        oto = None
        if isinstance(o, dict):
            try:
                _kod, _sorun = oto_sorun(o)
            except Exception:
                _kod, _sorun = None, None
            oto = {"sonuc": str(o.get("sonuc") or ""), "metin": duz_metin(o.get("metin")),
                   "zaman": str(o.get("zaman") or "")[11:16],
                   "chiller": _CH_MOD.get(o.get("chiller_mod"), o.get("chiller_mod") or ""),
                   "diger": _DIG_MOD.get(o.get("diger_mod"), o.get("diger_mod") or ""),
                   "sorun": duz_metin(_sorun) if _sorun else ""}
        s = sicaklik.get(lid) or {}
        lok[lid] = {
            "isim": h.get("isim", lid), "kisa": h.get("kisa", lid), "renk": h.get("renk", "#2a78d6"),
            "m2": _sayi(h.get("m2")), "durum": durum, "dk": round(dk) if dk is not None else None,
            "canli": {a: _sayi(c.get(a)) for a in CANLI_ALANLAR},
            "hava": {"set": _sayi(s.get("set")), "dis": _sayi(s.get("dis"))} if s else None,
            "oto": oto,
            "uyari": [{"s": "r" if sv == "r" else "y", "m": duz_metin(m)} for sv, m in (uyari_map.get(lid) or [])],
            "olcum": (cihazlar or {}).get(lid) or [],
            # saha: {lok: (bakim_ozet, hvac_ozet)} — lokasyonlar tablosu (detaydakiyle aynı)
            "saha": saha_ozeti(*((saha or {}).get(lid) or ({}, {}))),
        }
    sirali = [l for l in sira if lok[l]["canli"]["enerji"] is not None]
    for n, l in enumerate(sirali, 1):
        lok[l]["sira"] = n
    return {"sira": list(sira), "lok": lok, "sayim": sayim, "genel": genel or {},
            "toplam": toplamlar(canli), "kalemler": [[k, e, b] for k, e, b, *_ in KALEMLER]}


def canli_birlestir(canli: dict, satirlar: list, ozet_fn) -> dict:
    """CANLI'ya kojen / kazan doğalgazı ekler. Ayrı toplam YAZILMAZ: aynı
    canli_ozet_hesapla (tazelik kuralı dahil) yalnız ilgili gaz satırlarıyla
    çağrılır, sonucun "dogalgaz" alanı alınır."""
    sonuc = {l: dict(v) for l, v in (canli or {}).items()}
    for alan, onek in GAZ_ONEK.items():
        try:
            o = ozet_fn([r for r in (satirlar or []) if str(r.get("cihaz") or "").upper().startswith(onek)])
        except Exception:
            o = {}
        for l, v in o.items():
            if l in sonuc and v.get("dogalgaz") is not None:
                sonuc[l][alan] = v["dogalgaz"]
    return sonuc


def toplamlar(canli: dict) -> dict:
    """Kart değerleri: her kalemin tüm lokasyonlardaki toplamı (ölçülen yoksa None)."""
    t = {}
    for k, *_ in KALEMLER:
        d = [_sayi(v.get(k)) for v in (canli or {}).values() if _sayi(v.get(k)) is not None]
        t[k] = sum(d) if d else None
    return t


def cihaz_gruplari(satirlar: list, ci, esik_sn: int = 120) -> dict:
    """Ölçümler bölümü: {lok: [{"a": grup, "b": başlık, "u": birim, "c": [[kısa ad, kW, cihaz, yaş_sn]]}]}.
    Canlı İzleme sekmesiyle AYNI gruplama (canli_izleme.gruplara_ayir) ve aynı
    tazelik kuralı (taze_ayir). 24.11.2026: eski (esik_sn'den yaşlı / zamanı okunamayan)
    sayaç listeden DÜŞMEZ — değeri None ("—", turuncu nokta) ve yaşıyla kalır; hangi
    sayaçtan veri alınamadığı görülsün. Taze sayacın yaşı None (yeşil nokta)."""
    lok_satir = {}
    for r in satirlar or []:
        if r.get("lokasyon_id") and r.get("cihaz"):
            lok_satir.setdefault(r["lokasyon_id"], []).append(r)
    sonuc = {}
    for lok, rs in lok_satir.items():
        try:
            taze, eski = ci.taze_ayir(rs, esik_sn=esik_sn)
        except Exception:
            taze, eski = [], [(r["cihaz"], None) for r in rs]
        deger = {r["cihaz"]: _sayi(r.get("kw")) for r in taze}
        yas = {}
        for ad, y in eski:
            if ad not in deger:
                deger[ad] = None
                yas[ad] = round(y) if y is not None else -1   # -1: zamanı okunamadı
        gruplar = []
        for anahtar, baslik, cihazlar in ci.gruplara_ayir(list(deger)):
            gruplar.append({"a": anahtar, "b": baslik, "u": ci.birim(anahtar),
                            "c": [[ci.kisa_ad(c), deger[c], c, yas.get(c)] for c in cihazlar]})
        if gruplar:
            sonuc[lok] = gruplar
    return sonuc


def cihaz_degerleri(gruplar: dict) -> dict:
    """tazele_betigi için {lok: {cihaz: kW}}."""
    return {l: {c[2]: c[1] for g in gs for c in g["c"]} for l, gs in (gruplar or {}).items()}


def canli_ozet(canli: dict) -> dict:
    """tazele_betigi için: {lok: {alan: sayı}} (yalnız ölçülen alanlar)."""
    return {l: {a: _sayi(v.get(a)) for a in CANLI_ALANLAR if _sayi(v.get(a)) is not None}
            for l, v in (canli or {}).items()}


# ── HTML ──────────────────────────────────────────────────────────────────

def _canli_span(lok: str, alan: str, deger, ond: int = 0, carpan: float = None) -> str:
    """Akış betiğinin bulacağı sayı. Değer yoksa "—" (data-deger YOK → akmaz;
    tazeleme değer getirirse canlanır)."""
    faz = f"ck-{'enerji' if alan == 'wm2' else alan}-{lok}"
    ek = f' data-carpan="{carpan:.6f}"' if carpan else ""
    if deger is None:
        return (f'<span class="canli-sayi" data-ck-lok="{lok}" data-ck-alan="{alan}"{ek} '
                f'data-ond="{ond}" data-faz="{faz}">—</span>')
    v = deger * (carpan or 1.0)
    return (f'<span class="canli-sayi" data-ck-lok="{lok}" data-ck-alan="{alan}"{ek} '
            f'data-deger="{v:.3f}" data-ond="{ond}" data-faz="{faz}">{kw_metin(v, ond)}</span>')


def oge_html(lid: str, v: dict, arama: str) -> str:
    """Çarktaki bir hastane: ad + anlık kW + kojen üretim + durum çubuğu (+ uyarı)."""
    c = v["canli"]
    durum = v["durum"]
    uy = v["uyari"]
    sinif = f"ck-oge ck-{durum}" + (" ck-uyarili" if uy else "")
    sira = f'<span class="ck-sira">#{v["sira"]}</span>' if v.get("sira") else ""
    if durum == "yok" and c["enerji"] is None:
        rozet = '<span class="ck-rz ck-rz-yok">kurulmadı</span>'
    else:
        # Seçili karta göre TEK değer kutusu: her kalem ayrı rozette, CSS yalnız
        # seçili kalemi gösterir (satırda hiçbir zaman yan yana çoklu kalem yok).
        # Varsayılan (Anlık Toplam) seçiliyken yanında kojen üretimi de görünür.
        rozet = "".join(
            f'<span class="ck-rz ck-deger" data-kalem="{k}"><b>{_canli_span(lid, k, c.get(k), 0)}</b>'
            f'{_html.escape(b)}<i class="ck-rz-et">{_html.escape(KISA_ETIKET.get(k, ""))}</i></span>'
            for k, _e, b, *_ in KALEMLER)
        if c.get("kojen") is not None:
            rozet += (f'<span class="ck-rz ck-rz-koj ck-koj-ek"><b>{_canli_span(lid, "kojen", c["kojen"], 0)}</b>'
                      f'kW<i class="ck-rz-et">kojen</i></span>')
        if durum == "off":
            rozet += '<span class="ck-rz ck-rz-off">çevrimdışı</span>'
    rozet += '<span class="ck-cubuk" aria-hidden="true"><i></i><i></i><i></i></span>'
    if uy:
        kr = any(u["s"] == "r" for u in uy)
        rozet += (f'<span class="ck-rz ck-rz-uy {"ck-r" if kr else "ck-y"}" '
                  f'title="{len(uy)} uyarı">{len(uy)}</span>')
    ad = _html.escape(v["kisa"])
    return (f'<div class="{sinif}" data-lok="{lid}" data-ara="{_html.escape(arama)}" role="option" '
            f'aria-label="{ad}"><span class="ck-nokta"></span><div class="ck-oge-ic">'
            f'<div class="ck-ad">{ad}{sira}</div><div class="ck-rozetler">{rozet}</div></div></div>')


def ozet_kart_html(sira: int, etiket: str, deger, birim: str, anahtar: str, ozet_anahtar: str,
                   ikon_html: str, aktif: bool = False) -> str:
    """Kalem kartı (cam). TIK: kalemi seçer (çark bu kalemin değerini gösterir).
    Özet detayına GİDİLMEZ — "›" oku, çift tık ve Shift+Enter kaldırıldı (kullanıcı
    kararı 19.11.2026). Değer = tüm lokasyonların toplamı; ölçülmüyorsa "canlı sayaç yok"."""
    if deger is None:
        sayi = ('<span class="ck-kart-sayi"><span class="canli-sayi" data-ck-lok="_top" '
                f'data-ck-alan="{anahtar}" data-ond="0" data-faz="ck-top-{anahtar}">canlı sayaç yok</span></span>')
    else:
        sayi = (f'<span class="ck-kart-sayi"><span class="canli-sayi" data-ck-lok="_top" data-ck-alan="{anahtar}" '
                f'data-deger="{deger:.3f}" data-ond="0" data-faz="ck-top-{anahtar}">{kw_metin(deger)}</span>'
                f'<small>{_html.escape(birim)}</small></span>')
    sinif = "ck-kart" + (" ck-aktif" if aktif else "") + ("" if deger is not None else " ck-pasif")
    return (f'<div class="{sinif}" data-kalem="{anahtar}" data-ozet="{ozet_anahtar}" role="button" tabindex="0" '
            f'title="{_html.escape(etiket)} — tık: çarkta göster" style="--sira:{sira};">'
            f'<span class="ck-kart-ikon">{ikon_html}</span>'
            f'<span class="ck-kart-govde">{sayi}<span class="ck-kart-etiket">{_html.escape(etiket)}</span></span></div>')


def _logo_html(veri: dict) -> str:
    sayim = veri.get("sayim", {})
    g = veri.get("genel", {})
    toplam = sum(sayim.values())
    # Haritadaki Genel Müdürlük logosunun AYNISI (app_merkez: binaSvg): beyaz A, üstünden
    # geçen ışık, kenarında dolaşan açık mavi çizgi
    a_svg = (f'<svg class="ck-a" viewBox="0 0 100 100" aria-label="Acıbadem Genel Müdürlük" role="img">'
             f'<defs><clipPath id="ckAKes"><path d="{GM_A}"/></clipPath>'
             '<linearGradient id="ckIsik" x1="0" x2="1" y1="0" y2="0">'
             '<stop offset="0" stop-color="#7dd3fc" stop-opacity="0"/>'
             '<stop offset=".5" stop-color="#e0f2fe" stop-opacity=".95"/>'
             '<stop offset="1" stop-color="#7dd3fc" stop-opacity="0"/></linearGradient></defs>'
             f'<path d="{GM_A}" fill="#ffffff"/>'
             '<g clip-path="url(#ckAKes)"><rect x="-40" y="0" width="34" height="100" fill="url(#ckIsik)" transform="skewX(-18)">'
             '<animateTransform attributeName="transform" type="translate" additive="sum" values="0 0;150 0;150 0" '
             'keyTimes="0;.55;1" dur="3.2s" repeatCount="indefinite"/></rect></g>'
             f'<path d="{GM_A}" fill="none" stroke="#7dd3fc" stroke-width="2" stroke-linejoin="round" '
             f'pathLength="300" stroke-dasharray="46 254"><animate attributeName="stroke-dashoffset" '
             f'from="0" to="-300" dur="4s" repeatCount="indefinite"/></path></svg>')
    zaman = _html.escape(str(g.get("zaman") or ""))
    return ('<div class="ck-logo-alan"><div class="ck-disk">'
            '<div class="ck-yorunge y3"><i></i></div><div class="ck-yorunge y2"><i></i></div>'
            '<div class="ck-yorunge y1"></div>'
            '<div class="ck-marka"><b>ACIBADEM</b><span>SAĞLIK GRUBU</span></div>'
            f'<div class="ck-kure">{a_svg}</div>'
            '<div class="ck-disk-alt">'
            f'<span class="ck-rozet">{toplam} lokasyon</span>'
            '<span class="ck-sayim">'
            f'<span title="çevrimiçi"><i style="background:var(--ck-yesil)"></i>{sayim.get("on", 0)}</span>'
            f'<span title="çevrimdışı"><i style="background:var(--ck-kirmizi)"></i>{sayim.get("off", 0)}</span>'
            f'<span title="kurulmadı"><i style="background:var(--ck-gri)"></i>{sayim.get("yok", 0)}</span>'
            '</span></div></div>'
            '<div class="ck-canli-etiket"><span class="ck-canli-nokta"></span>Enerji Canlı İzleme'
            + (f' · {zaman}' if zaman else "") + '</div></div>')


def sahne_html(veri: dict, ozet_kartlar: list, ikonlar: dict, arama_metni=None,
               izleyici: bool = False, surum: str = "") -> str:
    """Tüm sahne (tek satır HTML — markdown boş satırda HTML'i bölmesin).

    ozet_kartlar: ozet_kart_html çıktıları (5 adet, sırayla)
    ikonlar     : {"alarm", "oto", "harita", "ayar", "yonetim", "cikis", "ara"...: html}
    arama_metni : lokasyon araması için metin normalleştirici (canli_izleme.arama_metni)
    """
    norm = arama_metni or (lambda s: str(s).lower())
    g = veri.get("genel", {})
    ogeler = "".join(
        oge_html(l, veri["lok"][l], norm(l + " " + veri["lok"][l]["isim"] + " " + veri["lok"][l]["kisa"]))
        for l in veri["sira"])
    toplam_uy = int(g.get("uyari_toplam") or 0)
    sayac_sinif = "ck-r" if g.get("uyari_kritik") else ("ck-y" if toplam_uy else "ck-g")
    ust = ('<div class="ck-ust">'
           f'<a class="ck-cip" href="#" role="button" data-ck-eylem="uyarilar" title="Canlı uyarılar listesi">'
           f'{ikonlar.get("alarm", "")}Uyarılar<span class="ck-sayac {sayac_sinif}">{toplam_uy}</span></a>'
           f'<a class="ck-cip" href="#" role="button" data-ck-eylem="kontrol" '
           f'title="OTO SET, dış hava & chiller set, saha durumu">{ikonlar.get("oto", "")}OTO SET · Saha</a>'
           f'<a class="ck-cip" href="#" role="button" data-ck-eylem="harita" title="Hastane enerji ağı haritası">'
           f'{ikonlar.get("harita", "")}Harita</a></div>')
    ayar = ("" if izleyici else
            f'<a class="ayar-ac ck-dugme" href="#" title="Sunucu ayarları" aria-label="Sunucu ayarları">'
            f'{ikonlar.get("ayar", "")}Sunucu Ayarları</a>')
    alt = ('<nav class="ck-alt" aria-label="Sistem">' + ayar
           + f'<a class="ck-dugme" href="#" role="button" data-ck-eylem="sistem" title="Yönetim — sunucu ve veri durumu">'
             f'{ikonlar.get("yonetim", "")}Sistem</a>'
           # Karanlık / aydınlık tema geçişi (tema_acik_demo.betik dinler; seçim tarayıcıda saklanır)
           + '<a class="ck-dugme ck-tema" href="#" role="button" data-ck-eylem="tema" title="Karanlık / aydınlık tema">'
             '<span class="ck-tema-acik">☀ Aydınlık</span><span class="ck-tema-koyu">☾ Karanlık</span></a>'
           + f'<a class="ck-dugme ck-cikis" href="#" role="button" data-ck-eylem="cikis" title="Oturumu kapat">'
             f'{ikonlar.get("cikis", "")}Oturumu Kapat</a></nav>')
    cark = ('<div class="ck-cark-alan">'
            '<label class="ck-ara"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/>'
            '<path d="M20 20l-3.5-3.5"/></svg>'
            '<input class="ck-ara-kutu" type="search" placeholder="Lokasyon ara" aria-label="Lokasyon ara" autocomplete="off">'
            f'<span class="ck-ara-say">{len(veri["sira"])} lokasyon</span></label>'
            '<a class="ck-sirala" href="#" role="button" data-ck-eylem="sirala" '
            'title="Listeyi seçili kalemin değerine göre sırala / eski sıraya dön">⇅ değere göre</a>'
            '<div class="ck-cark" tabindex="0" role="listbox" aria-label="Hastaneler — tekerlek, sürükleme ya da ok tuşlarıyla çevirin">'
            + ogeler + '<div class="ck-bos">Aramayla eşleşen lokasyon yok.</div></div>'
            '<div class="ck-ray" title="Listeyi kaydır"><div class="ck-ray-tutamak"></div></div></div>')
    panel = ('<aside class="ck-panel" aria-label="Seçili lokasyon" aria-live="polite">'
             '<div class="ck-panel-ic"><div class="ck-p-bos">Lokasyon seçin</div></div></aside>')
    veri_attr = _html.escape(json.dumps(veri, ensure_ascii=False, default=str), quote=True)
    return (f'<div class="ck-sahne" data-kalem="enerji" data-surum="{_html.escape(surum)}" data-veri="{veri_attr}">'
            '<svg class="ck-baglar" aria-hidden="true"></svg>'
            + _logo_html(veri)
            + '<div class="ck-kartlar">' + "".join(ozet_kartlar) + '</div>'
            + cark + panel + ust + alt
            + '<div class="ck-perde" data-ck-eylem="kapat"></div>'
            + '<a class="ck-katman-kapat" href="#" role="button" data-ck-eylem="kapat" title="Kapat (Esc)" aria-label="Kapat">×</a>'
            + '</div>')


# ── Betikler ──────────────────────────────────────────────────────────────

def tazele_betigi(canli: dict, durum: dict, cihaz: dict = None) -> str:
    """15 sn tazeleme (sayfa yeniden çizilmez): çarktaki / paneldeki sayıların
    data-deger'ini ve lokasyon durumunu yeniler. Değeri gelmeyen sayı "—" olur
    (mevcut tazele_betigi ile aynı kural). canli: CANLI benzeri; durum: {lok: bool}."""
    veri = {"canli": canli_ozet(canli), "durum": {k: bool(v) for k, v in (durum or {}).items()},
            "toplam": toplamlar(canli), "cihaz": cihaz or {}}
    return """
<script>
(function () {
  var veri = %s, W = window.parent, d;
  try { d = W.document; } catch (e) { return; }
  var S = W.__synCark;
  if (S) { S.canli = veri.canli; S.durum = veri.durum; S.cihaz = veri.cihaz; S.toplam = veri.toplam; }
  d.querySelectorAll('.ck-sahne .canli-sayi[data-ck-lok]').forEach(function (el) {
    var lok = el.getAttribute('data-ck-lok'), alan = el.getAttribute('data-ck-alan');
    var x = lok === '_top' ? veri.toplam[alan]
      : (alan.indexOf('c:') === 0 ? (veri.cihaz[lok] || {})[alan.slice(2)] : (veri.canli[lok] || {})[alan === 'wm2' ? 'enerji' : alan]);
    if (x == null) {
      ['data-deger', 'data-onceki', 'data-t', 'data-sure'].forEach(function (a) { el.removeAttribute(a); });
      el.textContent = '\\u2014';
      return;
    }
    var c = parseFloat(el.getAttribute('data-carpan') || '1');
    el.setAttribute('data-deger', (x * c).toFixed(3));
  });
  Object.keys(veri.durum).forEach(function (lok) {
    var el = d.querySelector('.ck-sahne .ck-oge[data-lok="' + lok + '"]');
    if (!el) { return; }
    el.classList.remove('ck-on', 'ck-off', 'ck-yok');
    el.classList.add(veri.durum[lok] ? 'ck-on' : 'ck-off');
  });
  if (S && S.panel) { S.panel(); }
  if (S && S.sirala && S.siraYenile) { S.siraYenile(); }
})();
</script>
""" % json.dumps(veri, ensure_ascii=False)


def _gecis_stil() -> str:
    """Geçiş stilini head'e ekleyen JS (detay_tema_demo ile ortak; döngüsel içe
    aktarma olmasın diye burada, çağrıldığında yüklenir)."""
    import detay_tema_demo as _dt
    return _dt.stil_ekle_js()


def betik(ikonlar: dict = None) -> str:
    """Çark motoru (0 px bileşende çalışır, ana belgede tek kopya tutar).

    * Motor W.__synCark'ta yaşar ve betik her çalıştığında yeniden kurulur
      (dinleyiciler betik çerçevesinin işlevleridir; çerçeve kalkınca ölürler).
      Eski motorun zamanlayıcıları kapatılır, dinleyicileri benim() ile susar.
      Sayfa yeniden çizilince 400 ms'lik denetim yeni sahneye bağlanır; seçili
      lokasyon, arama metni ve grafik izi korunur.
    * Etkileşim: tekerlek (birikimli, 130 ms sonra yapışır), sol tık / dokunmatik
      sürükleme (pointer events + pointer capture; bırakınca hız × 0,32 s kadar
      atalet, sonra en yakın öğe), sağdaki ray, ok tuşları / PageUp-Down / Enter.
    * Seçili = ortadaki öğe. Başka öğeye tık → o öğe ortaya döner. Seçiliye tık,
      çift tık, Enter ya da paneldeki "Detay" → gizli_detay_<lok> düğmesi.
    * prefers-reduced-motion: geçişler animasyonsuz (doğrudan yerine oturur).
    """
    return r"""
<script>
(function () {
  var W = window.parent, d;
  try { d = W.document; } catch (e) { return; }
  var SURUM = '__SURUM__';
  __GECIS_STIL__
  W.__synCarkIkon = __IKON__;   // paneldeki simgeler (ikonlar.py çıktısı)
  // Her çalışmada motor YENİDEN kurulur: dinleyiciler bu çerçevenin işlevleridir
  // ve çerçeve sayfadan kalkınca (ör. detaydan dönüş) ölür. Eskisinin
  // zamanlayıcı / dinleyicileri kapatılır; seçim, arama ve iz devralınır.
  var eski = W.__synCark;
  if (eski) {
    try {
      W.clearInterval(eski.aralik); W.clearInterval(eski.ornekAralik);
      if (eski.raf) { W.cancelAnimationFrame(eski.raf); }
      if (eski.boyut) { W.removeEventListener('resize', eski.boyut); }
      if (eski.tus) { d.removeEventListener('keydown', eski.tus); }
    } catch (e) {}
  }
  var AZ = !!(W.matchMedia && W.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var K = __K__, IZ_UZUN = 48;
  var S = W.__synCark = {surum: SURUM, pos: 0, hedef: 0, secili: eski ? eski.secili : null,
    sorgu: eski ? (eski.sorgu || '') : '', iz: (eski && eski.iz) || {}, canli: {}, durum: {}, cihaz: {},
    liste: [], ogeler: [], raf: 0, aktifKart: (eski && eski.aktifKart) || 'enerji', sirala: !!(eski && eski.sirala),
    sonSec: null, fan: [], logoBag: []};
  function benim() { return W.__synCark === S; }   // eski motorun dinleyicisi iş yapmasın

  function yaz(x, ond) { return Number(x).toLocaleString('tr-TR', {minimumFractionDigits: ond, maximumFractionDigits: ond}); }
  function kac(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
  // Sayaç yaşı (sn) → "45 sn" / "12 dk" / "3 sa" / "2 gün"
  function yasYaz(sn) { return sn < 60 ? sn + ' sn' : (sn < 3600 ? Math.round(sn / 60) + ' dk'
    : (sn < 86400 ? Math.round(sn / 3600) + ' sa' : Math.round(sn / 86400) + ' gün')); }
  var HARF = {'İ': 'i', 'I': 'i', 'ı': 'i', 'Ş': 's', 'ş': 's', 'Ğ': 'g', 'ğ': 'g', 'Ü': 'u', 'ü': 'u', 'Ö': 'o', 'ö': 'o', 'Ç': 'c', 'ç': 'c'};
  function norm(s) { return String(s || '').replace(/[İIıŞşĞğÜüÖöÇç]/g, function (c) { return HARF[c]; }).toLowerCase().trim().replace(/\s+/g, ' '); }
  function mod(a, n) { return ((a % n) + n) % n; }
  function dongusel() { return S.liste.length > 2 * K + 1; }
  function sinirla(v) { var n = S.liste.length; if (!n || dongusel()) { return v; } return Math.max(0, Math.min(n - 1, v)); }
  function seciliIdx() {
    var n = S.liste.length; if (!n) { return -1; }
    var r = Math.round(S.pos); return dongusel() ? mod(r, n) : Math.max(0, Math.min(n - 1, r));
  }
  function ofset(i) { var n = S.liste.length, o = i - S.pos; if (dongusel()) { o = mod(o, n); if (o > n / 2) { o -= n; } } return o; }
  function sayiOku(t) { var v = parseFloat(String(t || '').replace(/\./g, '').replace(',', '.')); return isNaN(v) ? null : v; }

  // ── Mevcut mekanizmalara köprü (gizli Streamlit düğmeleri; yoksa eski href yolu) ──
  // ── Lokasyona geçiş (detay_tema_demo.GECIS_JS, ana belgede yaşayan motor):
  // tıklama anında ana sahne bulanıklaşıp kararır, seçili öğenin yerinden cam
  // iskelet panel sağdaki detay paneli yerine büyür; detay gelince içerik oturur.
  function detay(lok, kaynak) {
    if (!lok) { return; }
    var b = d.querySelector('.st-key-ck_detay_' + lok + ' button') || d.querySelector('.st-key-gizli_detay_' + lok + ' button');
    if (!b) { W.location.search = '?detay=' + encodeURIComponent(lok); return; }
    try {
      if (W.__ckGecis) {
        var v = (S.veri && S.veri.lok[lok]) || {};
        var r = (kaynak || S.el.querySelector('.ck-panel')).getBoundingClientRect();
        W.__ckGecis.ileri(String(v.isim || lok).toLocaleUpperCase('tr-TR'), {left: r.left, top: r.top, width: r.width, height: r.height});
      }
    } catch (e) {}
    b.click();
  }
  // Geri dönüşte motor sahnenin bağlanmasını bekler; burada yalnız denetletilir
  function geriGiris() { if (W.__ckGecis) { W.__ckGecis.denetle(); } }
  function ozetAc(k) {
    var b = d.querySelector('.st-key-gizli_ozet_' + k + ' button');
    if (b) { b.click(); } else { W.location.search = '?ozet=' + encodeURIComponent(k); }
  }
  function katmanKapat() { d.body.classList.remove('ck-kontrol-acik', 'ck-harita-acik', 'ck-uyari-acik'); }
  function katman(ad, hedef) {
    var sinif = {harita: 'ck-harita-acik', uyari: 'ck-uyari-acik'}[ad] || 'ck-kontrol-acik';
    var acik = d.body.classList.contains(sinif);
    katmanKapat();
    if (acik && !hedef) { return; }
    d.body.classList.add(sinif);
    if (ad === 'kontrol' || ad === 'uyari') {
      var kol = d.querySelector('[data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret) > [data-testid="stColumn"]:nth-child(3)');
      if (!kol) { return; }
      var h = hedef ? kol.querySelector(hedef) : null;
      W.setTimeout(function () {
        var y = h ? (h.getBoundingClientRect().top - kol.getBoundingClientRect().top + kol.scrollTop - 8) : 0;
        kol.scrollTo({top: Math.max(0, y), behavior: AZ ? 'auto' : 'smooth'});
      }, 60);
    }
  }
  function eylem(ad) {
    if (ad === 'sistem') { var y = d.querySelector('.st-key-yonetim_btn button'); if (y) { y.click(); } else { W.location.search = '?yonetim=1'; } }
    else if (ad === 'cikis') { var c = d.querySelector('.st-key-cikis_btn button'); if (c) { c.click(); } }
    else if (ad === 'uyarilar') { katman('uyari', null); }
    else if (ad === 'kontrol') { katman('kontrol', '.st-key-oto_set_karti'); }
    else if (ad === 'harita') { katman('harita'); }
    else if (ad === 'kapat') { katmanKapat(); }
    else if (ad === 'detay') { detay(S.secili, S.el.querySelector('.ck-panel')); }
    else if (ad === 'sirala') { S.sirala = !S.sirala; var sb = S.el.querySelector('.ck-sirala'); if (sb) { sb.classList.toggle('ck-acik', S.sirala); } siraUygula(true); }
    else if (ad === 'oto-anahtar' || ad === 'oto-saat' || ad === 'oto-kayit') {
      // Mevcut OTO SET düğmeleri (sağ sütun; demoda yazma yok, oturum içi kural aynen)
      var sec = {'oto-anahtar': '.st-key-oto_switch_on button, .st-key-oto_switch_off button',
                 'oto-saat': '.st-key-oto_saat_kart button', 'oto-kayit': '.st-key-oto_liste_kart button'}[ad];
      var b = d.querySelector(sec); if (b && !b.disabled) { b.click(); }
    }
  }
  // ── Kalem seçimi (kart tek tık) ve değere göre sıralama ──
  function deger(lok, k) {
    if (S.canli && Object.keys(S.canli).length) { var c = S.canli[lok]; return c && c[k] != null ? c[k] : null; }
    var v = S.veri && S.veri.lok[lok]; return v && v.canli ? (v.canli[k] == null ? null : v.canli[k]) : null;
  }
  function kalemSec(k) {
    if (!k || k === S.aktifKart) { return; }
    S.aktifKart = k;
    S.el.setAttribute('data-kalem', k);
    S.el.querySelectorAll('.ck-kart').forEach(function (x) { x.classList.toggle('ck-aktif', x.getAttribute('data-kalem') === k); });
    bagCiz();
    if (S.sirala) { siraUygula(true); }
  }
  function siraUygula(anim) {
    var taban = S.taban || S.ogeler;
    var k = S.aktifKart;
    S.ogeler = !S.sirala ? taban.slice() : taban.slice().sort(function (a, b) {
      var x = deger(a.getAttribute('data-lok'), k), y = deger(b.getAttribute('data-lok'), k);
      if (x == null && y == null) { return 0; } if (x == null) { return 1; } if (y == null) { return -1; } return y - x;
    });
    if (anim && !AZ) {
      S.cark.classList.add('ck-siralaniyor');
      W.clearTimeout(S.siraZ); S.siraZ = W.setTimeout(function () { S.cark.classList.remove('ck-siralaniyor'); }, 650);
    }
    suz();
  }
  S.siraYenile = function () { if (S.sirala && S.el) { siraUygula(true); } };

  // ── Yerleşim: yay üzerinde dizilim ──
  function yerlestir() {
    var c = S.cark; if (!c) { return; }
    var H = c.clientHeight, G = c.clientWidth; if (!H || !G) { return; }
    var R = H * 0.62, tmax = Math.asin(Math.min(0.97, H * 0.46 / R)), adim = tmax / K;
    // Ortadaki öğe çarkın sol kenarından G*0.34 içeride: yay dışa doğru açılır
    var taban = Math.max(R * (1 - Math.cos(tmax)) + 16, G * 0.34);
    var sec = seciliIdx();
    S.liste.forEach(function (el, i) {
      var o = ofset(i), a = Math.abs(o);
      if (a > K + 0.6) {
        if (el.__ckGor !== false) { el.style.visibility = 'hidden'; el.style.opacity = '0'; el.__ckGor = false; }
        el.classList.remove('ck-merkez');
        return;
      }
      var t = o * adim, x = taban - R * (1 - Math.cos(t)), y = H / 2 + R * Math.sin(t);
      var s = Math.max(0.56, 1.1 - 0.072 * a), op = Math.max(0, 1 - Math.pow(a / (K + 0.9), 1.6));
      el.style.visibility = 'visible'; el.__ckGor = true;
      el.style.transform = 'translate(' + x.toFixed(1) + 'px,' + y.toFixed(1) + 'px) translateY(-50%) scale(' + s.toFixed(3) + ')';
      el.style.opacity = op.toFixed(3);
      el.style.zIndex = String(100 - Math.round(a * 10));
      el.__ckX = x; el.__ckY = y; el.__ckOp = op;
      if ((i === sec) !== el.classList.contains('ck-merkez')) { el.classList.toggle('ck-merkez', i === sec); }
    });
    if (sec !== S.sonSec) {
      S.sonSec = sec;
      var se = S.liste[sec];
      S.secili = se ? se.getAttribute('data-lok') : S.secili;
      if (se) { se.setAttribute('aria-selected', 'true'); }
      S.liste.forEach(function (e2, j) { if (j !== sec) { e2.removeAttribute('aria-selected'); } });
      panel();
    }
    bagCiz(); ray();
  }
  function kare(t) {
    S.raf = 0;
    var dt = S.sonT ? Math.min(0.05, (t - S.sonT) / 1000) : 0.016; S.sonT = t;
    if (!S.surukle) {
      var f = AZ ? 1 : 1 - Math.exp(-dt * 9);
      S.pos += (S.hedef - S.pos) * f;
      if (Math.abs(S.hedef - S.pos) < 0.0008) { S.pos = S.hedef; }
    }
    yerlestir();
    if (S.surukle || S.pos !== S.hedef) { S.raf = W.requestAnimationFrame(kare); } else { S.sonT = 0; }
  }
  function oynat() { if (!S.raf) { S.raf = W.requestAnimationFrame(kare); } }
  function git(h) { S.hedef = sinirla(h); oynat(); }

  // ── Bağlantı çizgileri (SVG) ──
  var NS = 'http://www.w3.org/2000/svg';
  function yol(sinif) { var p = d.createElementNS(NS, 'path'); p.setAttribute('class', sinif); p.setAttribute('pathLength', '100'); return p; }
  function havuz() {
    var svg = S.svg; if (!svg) { return; }
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    S.fan = []; S.logoBag = [];
    for (var i = 0; i < 2 * K + 3; i++) {
      var a = yol('ck-bag'), b = yol('ck-akis');
      b.style.animationDelay = (-(i * 0.37) % 3.4).toFixed(2) + 's';
      svg.appendChild(a); svg.appendChild(b); S.fan.push({a: a, b: b});
    }
    S.el.querySelectorAll('.ck-kart').forEach(function (k, i) {
      var a = yol('ck-bag ck-bag-logo'), b = yol('ck-akis');
      b.style.animationDelay = (-(i * 0.6)).toFixed(2) + 's';
      svg.appendChild(a); svg.appendChild(b); S.logoBag.push({a: a, b: b, k: k});
    });
  }
  function egri(ax, ay, bx, by) {
    var mx = ax + (bx - ax) * 0.5;
    return 'M' + ax.toFixed(1) + ' ' + ay.toFixed(1) + 'C' + mx.toFixed(1) + ' ' + ay.toFixed(1) + ' '
      + mx.toFixed(1) + ' ' + by.toFixed(1) + ' ' + bx.toFixed(1) + ' ' + by.toFixed(1);
  }
  function bagCiz() {
    var svg = S.svg; if (!svg || !S.el) { return; }
    var sr = S.el.getBoundingClientRect();
    if (!svg.getBoundingClientRect().width) { return; }   // dar ekranda gizli
    svg.setAttribute('viewBox', '0 0 ' + sr.width.toFixed(0) + ' ' + sr.height.toFixed(0));
    var kure = S.el.querySelector('.ck-kure');
    var kr = kure ? kure.getBoundingClientRect() : null;
    S.logoBag.forEach(function (g) {
      if (!kr) { return; }
      var r = g.k.getBoundingClientRect();
      var dd = egri(kr.right - sr.left - 2, kr.top + kr.height / 2 - sr.top, r.left - sr.left, r.top + r.height / 2 - sr.top);
      var akt0 = g.k.getAttribute('data-kalem') === S.aktifKart;
      g.a.setAttribute('d', dd); g.b.setAttribute('d', akt0 ? dd : '');
      var akt = g.k.getAttribute('data-kalem') === S.aktifKart;
      g.a.classList.toggle('ck-bag-aktif', akt);
    });
    var kart = S.el.querySelector('.ck-kart[data-kalem="' + S.aktifKart + '"]');
    var j = 0;
    if (kart && S.cark) {
      var k = kart.getBoundingClientRect(), cr = S.cark.getBoundingClientRect();
      var ax = k.right - sr.left, ay = k.top + k.height / 2 - sr.top;
      S.liste.forEach(function (el) {
        if (!el.__ckGor || j >= S.fan.length) { return; }
        var p = S.fan[j++];
        var dd = egri(ax, ay, cr.left - sr.left + el.__ckX - 3, cr.top - sr.top + el.__ckY);
        p.a.setAttribute('d', dd); p.b.setAttribute('d', el.classList.contains('ck-merkez') ? dd : '');
        var m = el.classList.contains('ck-merkez');
        p.a.style.opacity = (m ? 1 : 0.18 + 0.7 * el.__ckOp).toFixed(3);
        p.b.style.opacity = (m ? 1 : 0.15 + 0.55 * el.__ckOp).toFixed(3);
        if (m !== p.a.classList.contains('ck-bag-merkez')) { p.a.classList.toggle('ck-bag-merkez', m); }
      });
    }
    for (; j < S.fan.length; j++) { S.fan[j].a.setAttribute('d', ''); S.fan[j].b.setAttribute('d', ''); }
  }
  function ray() {
    var r = S.ray, t = S.tutamak, n = S.liste.length; if (!r || !t) { return; }
    var oran = n > 1 ? (dongusel() ? mod(S.pos, n) / (n - 1) : S.pos / (n - 1)) : 0;
    oran = Math.max(0, Math.min(1, oran));
    t.style.transform = 'translateY(' + ((r.clientHeight - t.offsetHeight) * oran).toFixed(1) + 'px)';
  }

  // ── Arama (yazdıkça süzer) ──
  function suz() {
    var kutu = S.el.querySelector('.ck-ara-kutu');
    var q = norm(kutu ? kutu.value : S.sorgu); S.sorgu = kutu ? kutu.value : S.sorgu;
    S.liste = [];
    S.ogeler.forEach(function (el) {
      var uy = !q || (el.getAttribute('data-ara') || '').indexOf(q) !== -1;
      el.classList.toggle('ck-suzuldu', !uy);
      if (uy) { S.liste.push(el); } else { el.__ckGor = false; el.classList.remove('ck-merkez'); }
    });
    var idx = -1;
    S.liste.forEach(function (el, i) { if (el.getAttribute('data-lok') === S.secili) { idx = i; } });
    S.pos = S.hedef = Math.max(0, idx);
    S.sonSec = null;
    S.cark.classList.toggle('ck-bos-var', !S.liste.length);
    var say = S.el.querySelector('.ck-ara-say');
    if (say) { say.textContent = (q ? S.liste.length + ' / ' + S.ogeler.length : S.ogeler.length) + ' lokasyon'; }
    yerlestir();
  }

  // ── Panel (seçili lokasyon) ──
  function cs(lok, alan, x, ond, carpan) {
    var faz = 'ck-' + (alan === 'wm2' ? 'enerji' : alan) + '-' + lok;
    var ek = carpan ? ' data-carpan="' + carpan.toFixed(6) + '"' : '';
    var bas = '<span class="canli-sayi" data-ck-lok="' + kac(lok) + '" data-ck-alan="' + alan + '"' + ek
      + ' data-ond="' + ond + '" data-faz="' + kac(faz) + '"';
    if (x == null) { return bas + '>—</span>'; }
    var v = x * (carpan || 1);
    // İlk yazı: listede aynı sayı akıyorsa onun o anki değeri (bir saniye beklemesin)
    var ayni = S.el.querySelector('.ck-oge[data-lok="' + lok + '"] .canli-sayi[data-ck-alan="' + alan + '"]');
    var metin = (ayni && !carpan && sayiOku(ayni.textContent) != null) ? ayni.textContent : yaz(v, ond);
    return bas + ' data-deger="' + v.toFixed(3) + '">' + kac(metin) + '</span>';
  }
  function panel() {
    var kap = S.el && S.el.querySelector('.ck-panel-ic'); if (!kap) { return; }
    // Cihaz listesi aynı lokasyonda açık kalır; başka lokasyona geçince kapalı başlar
    // Açılır kartlar / uyarılar aynı lokasyonda açık kalır; başka lokasyona geçince kapalı başlar
    if (S.acikLok !== S.secili) { S.acik = {}; S.acikLok = S.secili; }
    else { S.acik = S.acik || {}; kap.querySelectorAll('details[data-ac]').forEach(function (x) { S.acik[x.getAttribute('data-ac')] = x.open; }); }
    function acikMi(a) { return S.acik && S.acik[a] ? ' open' : ''; }
    function satirlar(l) {
      return l.map(function (x) { return '<div class="ck-p-uyari' + (x[0] === 'r' ? ' ck-r' : '') + '">' + kac(x[1]) + (x[2] ? ' — ' + kac(x[2]) : '') + '</div>'; }).join('');
    }
    var lid = S.secili, v = lid && S.veri && S.veri.lok[lid];
    if (!v) { kap.innerHTML = '<div class="ck-p-bos">' + (S.liste.length ? 'Lokasyon seçin' : 'Eşleşen lokasyon yok') + '</div>'; return; }
    var c = {}, a; for (a in v.canli) { c[a] = v.canli[a]; }
    if (S.canli && Object.keys(S.canli).length) {   // 15 sn tazeleme geldiyse onun değerleri
      var yeni = S.canli[lid] || {}; for (a in c) { c[a] = yeni[a] == null ? null : yeni[a]; }
    }
    var g = S.veri.genel || {}, ik = S.veri.ikon || {};
    var dur = (S.durum && S.durum[lid] != null) ? (S.durum[lid] ? 'on' : 'off') : v.durum;
    var DUR = {on: 'ÇEVRİMİÇİ', off: 'ÇEVRİMDIŞI', yok: 'KURULMADI'};
    var dmetin = dur === 'yok' ? 'Lokasyon programı kurulmadı / bağlantı kaydı yok'
      : (v.dk != null ? 'Son bağlantı ' + (v.dk < 1 ? 'az önce' : v.dk + ' dk önce') : '');
    var m2 = v.m2, wm2 = (c.enerji != null && m2) ? 1000 / m2 : null;
    var h = '';
    // Başlık kartı: lokasyon adı solda, bağlantı durumu + Detay sağda (aynı kart, 19.11.2026)
    h += '<div class="ck-p-kutu ck-p-kafa"><div class="ck-p-kafa-sol">'
      + '<div class="ck-p-ust">' + (ik.hastane || '') + '<span>Hastane' + (v.sira ? ' · tüketim sırası #' + v.sira : '') + '</span></div>'
      + '<div class="ck-p-baslik">' + kac(v.isim) + '</div>'
      + '<div class="ck-p-alt">' + kac(v.kisa) + (m2 ? ' · ' + yaz(m2, 0) + ' m²' : '') + '</div></div>'
      + '<div class="ck-p-kafa-sag"><span class="ck-dr ck-' + dur + '">' + DUR[dur] + '</span>'
      + '<span class="ck-p-son">' + kac(dmetin) + '</span>'
      + '<a class="ck-p-dugme" href="#" role="button" data-ck-eylem="detay">Detay ›</a></div></div>';
    // Üst kart: ANLIK TOPLAM TÜKETİM = canli_ozet_hesapla "enerji" (şebeke + kojen; şebeke
    // sayacı yoksa trafo toplamı) — burada yeniden hesaplanmaz, yalnız etiketlenir
    var notu = c.enerji == null ? 'canlı sayaç yok'
      : (c.sebeke != null ? (c.kojen != null ? 'şebeke + kojen' : 'yalnız şebeke (kojen yok)') : 'trafo toplamı');
    h += '<div class="ck-p-kutu ck-p-buyuk"><div class="ck-p-buyuk-ust"><span>Anlık Toplam Tüketim</span>'
      + (wm2 ? '<span class="ck-p-cip">' + cs(lid, 'wm2', c.enerji, 1, wm2) + ' W/m²</span>' : '') + '</div>'
      + '<div class="ck-p-buyuk-orta"><div><div class="ck-p-sayi">' + cs(lid, 'enerji', c.enerji, 0) + '<small>kW</small></div>'
      + '<div class="ck-p-egilim"></div></div><div class="ck-grafik"></div></div>'
      + '<div class="ck-p-not">' + notu + ' · grafik: ekranda akan değer, son 48 sn</div></div>';
    // 6 kart (3×2)
    function hucre(ikon, alan, x, birim, et) {
      return '<div class="ck-p-hucre"><div class="ck-p-hucre-ust">' + (ik[ikon] || '') + '<b>' + cs(lid, alan, x, 0)
        + (x != null ? '<small>' + birim + '</small>' : '') + '</b></div><div class="ck-p-hucre-et">' + et
        + (x == null ? ' · sayaç yok' : '') + '</div></div>';
    }
    h += '<div class="ck-p-izgara ck-p-izgara-3">' + hucre('sebeke', 'sebeke', c.sebeke, 'kW', 'Şebeke tüketim')
      + hucre('kojen', 'kojen', c.kojen, 'kW', 'Kojen üretim') + hucre('sogutma', 'sogutma', c.sogutma, 'kW', 'Soğutma')
      + hucre('su', 'su', c.su, 'm³/h', 'Su') + hucre('dogalgaz', 'dogalgaz_kojen', c.dogalgaz_kojen, 'm³/h', 'Kojen doğalgaz')
      + hucre('kazan', 'dogalgaz_kazan', c.dogalgaz_kazan, 'm³/h', 'Kazan doğalgaz') + '</div>';
    function satir(et, deger, sinif) { return '<div class="ck-p-satir"><span>' + et + '</span><span' + (sinif ? ' class="' + sinif + '"' : '') + '>' + deger + '</span></div>'; }
    // Ölçümler: Canlı İzleme sekmesiyle aynı gruplar (TRDP / soğutma / MCC / kojen / gaz / su)
    var og = v.olcum || [];
    h += '<div class="ck-p-bolum">' + (ik.termometre || '') + 'Ölçümler<span class="ck-p-bolum-not">canlı sayaçlar</span></div>';
    if (og.length) {
      // İki sütun: solda enerji kaynağı / MCC / kojen; sağda soğutma, şebeke ve
      // şebekenin ALTINDA doğalgaz ve su (kullanıcı kararı 19.11.2026)
      var SAG = {sogutma: 1, sebeke: 1, dogalgaz: 1, su: 1}, kol = {sol: '', sag: ''};
      og.forEach(function (gr) {
        var g = '<div class="ck-p-og"><div class="ck-p-og-b">' + kac(gr.b) + '</div>';
        gr.c.forEach(function (cc) {
          var yeniC = S.cihaz && S.cihaz[lid] && S.cihaz[lid][cc[2]] !== undefined ? S.cihaz[lid][cc[2]] : cc[1];
          // Yeşil: son 2 dk içinde okundu; turuncu: veri alınamıyor (24.11.2026)
          var bayat = yeniC == null;
          var ipucu = bayat ? (cc[3] != null && cc[3] >= 0 ? 'Veri alınamıyor — son okuma ' + yasYaz(cc[3]) + ' önce'
                                                           : 'Veri alınamıyor') : 'Canlı — son 2 dk içinde okundu';
          g += '<div class="ck-p-oc' + (bayat ? ' ck-p-oc-bayat' : '') + '" title="' + kac(ipucu) + '"><span><i class="ck-p-ocn"></i>' + kac(cc[0]) + '</span><span>'
            + cs(lid, 'c:' + cc[2], yeniC, 1) + '<small>' + kac(gr.u) + '</small></span></div>';
        });
        kol[SAG[gr.a] ? 'sag' : 'sol'] += g + '</div>';
      });
      h += '<div class="ck-p-olcum"><div class="ck-p-olc-kol">' + kol.sol + '</div><div class="ck-p-olc-kol">' + kol.sag + '</div></div>';
    } else { h += '<div class="ck-p-not">Bu lokasyonda okunan canlı sayaç yok.</div>'; }
    // OTO SET — bu panelden yönetilir (mevcut OTO SET düğmeleri; demoda yazma yok)
    var o = v.oto, hv = v.hava || {};
    var ozel = (g.ozel || []).indexOf(lid) !== -1;
    var setSinif = hv.set != null && (hv.set < 6 || hv.set > 9) ? 'ck-dikkat' : '';
    var izl = !!g.izleyici;
    h += '<div class="ck-p-bolum">' + (ik.oto || '') + 'OTO SET</div><div class="ck-p-oto">'
      + '<div class="ck-p-oto-ust">'
      + '<a href="#" role="switch" aria-checked="' + (g.oto_aktif ? 'true' : 'false') + '" class="ck-anahtar' + (g.oto_aktif ? ' ck-acik' : '') + (izl ? ' ck-kilit' : '')
      + '" data-ck-eylem="oto-anahtar" title="' + (g.oto_aktif ? 'Senaryo AKTİF — kapatmak için tıkla' : 'Senaryo KAPALI — açmak için tıkla') + '"><i></i></a>'
      + '<span class="ck-p-oto-durum"><b>' + (g.oto_aktif ? 'AKTİF' : 'KAPALI') + '</b><span>' + (g.donem === 'gunduz' ? 'GÜNDÜZ' : 'GECE')
      + (g.sonraki ? ' · sıradaki ' + kac(g.sonraki) : '') + '</span></span>'
      + '<a href="#" role="button" class="ck-p-dugme" data-ck-eylem="oto-saat" title="Geçiş saatleri">' + (ik.saat || '')
      + (ozel ? 'özel saat' : kac(g.g_saat) + ' · ' + kac(g.ge_saat)) + '</a>'
      + '<a href="#" role="button" class="ck-p-dugme" data-ck-eylem="oto-kayit" title="Geçiş kayıtları">' + (ik.kayit || '')
      + (g.kayit ? g.kayit + ' kayıt' : 'kayıt yok') + '</a></div>'
      + (o ? satir('Saha (' + kac(o.zaman || '—') + ')', kac(o.sorun || o.metin || o.sonuc || '—'), o.sorun ? 'ck-kotu' : '') : satir('Saha', 'durum bildirilmedi', 'ck-dikkat'))
      + (o && (o.chiller || o.diger) ? satir('Mod', kac([o.chiller, o.diger].filter(Boolean).join(' · '))) : '')
      + satir('Chiller set', hv.set != null ? yaz(hv.set, 1) + ' °C' : '—', setSinif)
      + satir('Dış hava', (hv.dis != null ? yaz(hv.dis, 1) + ' °C' : '—') + (g.dis_hava != null ? ' · İst. ' + yaz(g.dis_hava, 1) + ' °C' : ''))
      + (g.son_gecis ? satir('Son geçiş', kac(g.son_gecis)) : '')
      + '</div>';
    // Uyarılar: YALNIZ bu lokasyonun (merkez / sunucu uyarıları üstteki genel rozette)
    var uy = v.uyari || [];
    // Açılır liste (19.11.2026): başlığa tıklayınca açılır
    if (uy.length) {
      h += '<details class="ck-p-bolum-ac" data-ac="uyari"' + acikMi('uyari') + '><summary class="ck-p-bolum">' + (ik.alarm || '') + 'Uyarılar'
        + '<span class="ck-p-acilir-say' + (uy.some(function (u) { return u.s === 'r'; }) ? '' : ' ck-y') + '">' + uy.length + '</span></summary>'
        + '<div class="ck-p-acilir-ic">' + satirlar(uy.map(function (u) { return [u.s, u.m, '']; })) + '</div></details>';
    } else {
      h += '<div class="ck-p-bolum">' + (ik.alarm || '') + 'Uyarılar (0)</div><div class="ck-p-not">Bu lokasyon için açık uyarı yok.</div>';
    }
    // Durum özeti: yalnız ekrandaki değerlerden türetilir (yeni veri üretmez)
    var oz = [];
    if (c.enerji != null && c.kojen != null && c.enerji > 0) { oz.push('Kojen anlık enerjinin <b>%' + yaz(100 * c.kojen / c.enerji, 0) + '</b>\'ini karşılıyor.'); }
    if (c.enerji != null && c.sogutma != null && c.enerji > 0) { oz.push('Soğutma yükü toplamın <b>%' + yaz(100 * c.sogutma / c.enerji, 0) + '</b>\'i.'); }
    if (wm2) {
      var top = 0, n = 0;
      Object.keys(S.veri.lok).forEach(function (l) {
        var lv = S.veri.lok[l], e = (S.canli && S.canli[l] && S.canli[l].enerji != null) ? S.canli[l].enerji : lv.canli.enerji;
        if (e != null && lv.m2) { top += e * 1000 / lv.m2; n++; }
      });
      if (n > 1) { oz.push('Son ölçümde yoğunluk <b>' + yaz(c.enerji * wm2, 1) + ' W/m²</b> · canlı lokasyon ortalaması ' + yaz(top / n, 1) + ' W/m².'); }
    }
    if (dur === 'off') { oz.push('Lokasyon çevrimdışı' + (v.dk != null ? ' (son bağlantı ' + v.dk + ' dk önce)' : '') + '.'); }
    if (c.enerji == null) { oz.push('Bu lokasyonda şu an canlı sayaç verisi yok.'); }
    h += '<div class="ck-p-bolum">' + (ik.zeka || '') + 'Durum özeti</div><div class="ck-p-kutu ck-p-analiz">'
      + (oz.length ? oz.join('<br>') : 'Gösterilecek anlık değer yok.') + '</div>';
    // Detaydan taşındı (19.11.2026): HVAC & Bakım, Yürürlükteki Setler, Sistem Sağlığı.
    // Değerler lokasyon heartbeat'inden (saha_ozeti) — detaydakiyle aynı alanlar.
    var sh = v.saha || {};
    // liste verilirse kartın KENDİSİ açılır (details): tıklayınca cihazlar kartın içinde listelenir
    function mini(ikon, et, deger, alt, renk, liste, ac) {
      var ic = '<div class="ck-p-hucre-et">' + et + '</div>'
        + '<div class="ck-p-hucre-ust">' + (ik[ikon] || '') + '<b' + (renk ? ' class="ck-' + renk + '"' : '') + '>' + deger + '</b></div>'
        + (alt ? '<div class="ck-p-mini-alt">' + alt + '</div>' : '');
      if (liste && liste.length) {
        return '<details class="ck-p-hucre ck-p-mini ck-p-mini-ac" data-ac="' + ac + '"' + acikMi(ac) + '><summary>' + ic + '</summary>'
          + '<div class="ck-p-mini-liste">' + satirlar(liste) + '</div></details>';
      }
      return '<div class="ck-p-hucre ck-p-mini">' + ic + '</div>';
    }
    var hvSorun = (sh.hv_kritik || 0) + (sh.hv_uyari || 0), hvOz = [];
    if (sh.hv_kritik) { hvOz.push(sh.hv_kritik + ' kritik'); }
    if (sh.hv_uyari) { hvOz.push(sh.hv_uyari + ' uyarı'); }
    if (sh.hv_normal) { hvOz.push(sh.hv_normal + ' normal'); }
    h += '<div class="ck-p-bolum">' + (ik.bakim || '') + 'HVAC & Bakım durumu</div><div class="ck-p-izgara ck-p-izgara-3">'
      + mini('ariza', 'Arızalı cihaz', String(sh.ariza || 0), sh.ariza ? '' : 'arıza yok', sh.ariza ? 'r' : 'g',
             (sh.ariza_l || []).map(function (a) { return ['r', a, '']; }), 'ariza')
      + mini('bakim', 'Bakımdaki', String(sh.bakim || 0), sh.bakim ? '' : 'bakımda cihaz yok', sh.bakim ? 'y' : 'g',
             (sh.bakim_l || []).map(function (a) { return ['y', a, '']; }), 'bakim')
      + mini('hvac', 'HVAC analiz', String(hvSorun), hvOz.length ? hvOz.join(' · ') : 'tümü normal',
             sh.hv_kritik ? 'r' : (sh.hv_uyari ? 'y' : 'g'), sh.hv_l || [], 'hvac')
      + '</div>';
    var st = sh.set;
    h += '<div class="ck-p-bolum">' + (ik.ayar_set || '') + 'Yürürlükteki setler</div>';
    if (st) {
      h += '<div class="ck-p-izgara ck-p-izgara-4">' + mini('chiller', 'Chiller', kac(st.chiller), kac(st.ch_mod))
        + mini('kollektor', 'Kollektör', kac(st.kol), 'gündüz / gece · ' + kac(st.dig_mod))
        + mini('fcu', 'FCU', kac(st.fcu), 'A/B blok') + mini('ahu', 'AHU', kac(st.ahu), 'Zon-1/2 santral') + '</div>';
    } else { h += '<div class="ck-p-not">Lokasyon yürürlükteki setleri bildirmedi.</div>'; }
    var so = sh.oto, sz = sh.oz, sg = sh.gb;
    h += '<div class="ck-p-bolum">' + (ik.saglik || '') + 'Sistem sağlığı</div><div class="ck-p-izgara ck-p-izgara-3 ck-p-saglik">'
      + (so ? mini('oto', 'Oto-set', kac(so.metin), (so.zaman ? 'son tur ' + kac(so.zaman) : '') + (so.dg ? (so.zaman ? ' · ' : '') + kac(so.dg[1]) : ''),
                   so.iyi ? 'g' : 'r') : mini('oto', 'Oto-set', 'Bildirim gelmedi', '', ''))
      + (sz ? mini('zeka', 'Mekanik Zeka öz testi', kac(sz.metin), kac(sz.kalan || sz.zaman), sz.gecti ? 'g' : 'r')
            : mini('zeka', 'Mekanik Zeka öz testi', 'Henüz çalışmadı', '', ''))
      + (sg ? mini('oneri', 'Öneri geri bildirimi', sg.sayi + ' <small>· ✓' + sg.uyg + ' · ✗' + sg.red + '</small>', kac(sg.alt), '')
            : mini('oneri', 'Öneri geri bildirimi', 'Bildirim gelmedi', '', ''))
      + '</div>';
    kap.innerHTML = h;
    grafik();
  }
  function grafik() {
    var kap = S.el && S.el.querySelector('.ck-panel .ck-grafik'); if (!kap) { return; }
    var a = S.iz[S.secili] || [], eg = S.el.querySelector('.ck-panel .ck-p-egilim');
    if (a.length < 2) { kap.innerHTML = '<div class="ck-grafik-bos">akış bekleniyor…</div>'; if (eg) { eg.textContent = ''; } return; }
    var mn = Math.min.apply(null, a), mx = Math.max.apply(null, a), ar = (mx - mn) || 1, n = IZ_UZUN, w = 100 / n;
    var s = '<svg viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">';
    for (var j = 0; j < n; j++) {
      var v = a[j - (n - a.length)];
      if (v == null) { continue; }
      var hh = 4 + 26 * (v - mn) / ar;
      s += '<rect' + (j === n - 1 ? ' class="ck-g-son"' : '') + ' x="' + (j * w + w * 0.2).toFixed(2) + '" y="' + (30 - hh).toFixed(2)
        + '" width="' + (w * 0.6).toFixed(2) + '" height="' + hh.toFixed(2) + '" rx="0.4"/>';
    }
    kap.innerHTML = s + '</svg>';
    if (eg && a.length > 10) {
      var ref = a[a.length - 11], son = a[a.length - 1], f = ref ? (son - ref) / Math.abs(ref) * 100 : 0;
      eg.className = 'ck-p-egilim' + (f > 0.05 ? ' ck-artis' : (f < -0.05 ? ' ck-azalis' : ''));
      eg.textContent = (f > 0.05 ? '▲ ' : (f < -0.05 ? '▼ ' : '')) + '%' + yaz(Math.abs(f), 1) + ' · 10 sn';
    }
  }
  function ornekle() {
    if (!S.el) { return; }
    S.ogeler.forEach(function (el) {
      var sp = el.querySelector('.canli-sayi[data-ck-alan="enerji"]'); if (!sp) { return; }
      var lok = el.getAttribute('data-lok'), v = sayiOku(sp.textContent);
      var a = S.iz[lok] = S.iz[lok] || [];
      if (v == null) { a.length = 0; return; }
      a.push(v); if (a.length > IZ_UZUN) { a.shift(); }
    });
    grafik();
  }

  // ── Olaylar ──
  function dinle(sahne) {
    function on(tip, fn, sec) { sahne.addEventListener(tip, function (ev) { if (benim()) { fn(ev); } }, sec); }
    on('click', function (ev) {
      var t = ev.target;
      if (!t.closest) { return; }
      if (t.closest('a.ayar-ac')) { return; }            // mevcut ayarlar betiği yakalar
      var e = t.closest('[data-ck-eylem]');
      if (e) { ev.preventDefault(); eylem(e.getAttribute('data-ck-eylem')); return; }
      var k = t.closest('.ck-kart[data-kalem]');
      if (k && ev.button === 0) { ev.preventDefault(); kalemSec(k.getAttribute('data-kalem')); }
    });
    // Kalem kartından özet detayına gidiş YOK (kullanıcı kararı 19.11.2026)
    on('input', function (ev) { if (ev.target.classList && ev.target.classList.contains('ck-ara-kutu')) { suz(); } });
    on('wheel', function (ev) {
      if (!ev.target.closest || !ev.target.closest('.ck-cark-alan')) { return; }
      ev.preventDefault();
      var dy = ev.deltaY * (ev.deltaMode === 1 ? 33 : (ev.deltaMode === 2 ? 400 : 1));
      S.hedef = sinirla(S.hedef + dy / 110);
      W.clearTimeout(S.tekerZ);
      S.tekerZ = W.setTimeout(function () { git(Math.round(S.hedef)); }, 130);
      oynat();
    }, {passive: false});
    on('pointerdown', function (ev) {
      if (ev.button !== 0) { return; }
      var r = ev.target.closest && ev.target.closest('.ck-ray');
      var c = !r && ev.target.closest && ev.target.closest('.ck-cark');
      if (!r && !c) { return; }
      ev.preventDefault();
      var hedefEl = r || c;
      try { hedefEl.setPointerCapture(ev.pointerId); } catch (e) {}
      if (c) { c.focus({preventScroll: true}); }
      S.surukle = {ray: !!r, el: hedefEl, id: ev.pointerId, y0: ev.clientY, x0: ev.clientX, pos0: S.pos, t0: Date.now(),
                   oge: c ? ev.target.closest('.ck-oge') : null, oynadi: false, iz: [[Date.now(), S.pos]]};
      if (r) { rayKonum(ev.clientY); }
      S.cark.classList.add('ck-surukleniyor');
      oynat();
    });
    function rayKonum(y) {
      var r = S.ray.getBoundingClientRect(), n = S.liste.length; if (n < 2) { return; }
      var f = Math.max(0, Math.min(1, (y - r.top) / r.height));
      S.pos = S.hedef = f * (n - 1);
      oynat();
    }
    on('pointermove', function (ev) {
      var s = S.surukle; if (!s || ev.pointerId !== s.id) { return; }
      if (s.ray) { rayKonum(ev.clientY); return; }
      var dy = ev.clientY - s.y0;
      if (Math.abs(dy) > 5 || Math.abs(ev.clientX - s.x0) > 5) { s.oynadi = true; }
      var adimPx = Math.max(18, S.cark.clientHeight / (2 * K + 1) * 1.15);
      S.pos = S.hedef = sinirla(s.pos0 - dy / adimPx);
      s.iz.push([Date.now(), S.pos]); if (s.iz.length > 6) { s.iz.shift(); }
      oynat();
    });
    function birak(ev) {
      var s = S.surukle; if (!s || ev.pointerId !== s.id) { return; }
      S.surukle = null;
      S.cark.classList.remove('ck-surukleniyor');
      try { s.el.releasePointerCapture(ev.pointerId); } catch (e) {}
      if (s.ray) { git(Math.round(S.pos)); return; }
      if (!s.oynadi && ev.type === 'pointerup') { tikla(s.oge); return; }
      // Atalet: son ~100 ms'lik hız (öğe/sn) × 0,32 sn ileri, sonra en yakın öğe
      var simdi = Date.now(), ilk = s.iz[0];
      for (var i = 0; i < s.iz.length; i++) { if (simdi - s.iz[i][0] <= 120) { ilk = s.iz[i]; break; } }
      var dt = (simdi - ilk[0]) / 1000, v = dt > 0.008 ? (S.pos - ilk[1]) / dt : 0;
      v = Math.max(-40, Math.min(40, v));
      git(Math.round(S.pos + (AZ ? 0 : v * 0.32)));
    }
    on('pointerup', birak);
    on('pointercancel', birak);
    on('keydown', function (ev) {
      if (ev.target.classList && ev.target.classList.contains('ck-kart') && (ev.key === 'Enter' || ev.key === ' ')) {
        ev.preventDefault();
        kalemSec(ev.target.getAttribute('data-kalem'));
        return;
      }
      if (!ev.target.classList || !ev.target.classList.contains('ck-cark')) { return; }
      var h = Math.round(S.hedef), k = ev.key;
      if (k === 'ArrowDown') { git(h + 1); } else if (k === 'ArrowUp') { git(h - 1); }
      else if (k === 'PageDown') { git(h + 5); } else if (k === 'PageUp') { git(h - 5); }
      else if (k === 'Home' && !dongusel()) { git(0); } else if (k === 'End' && !dongusel()) { git(S.liste.length - 1); }
      else if (k === 'Enter' || k === ' ') { detay(S.secili, S.el.querySelector('.ck-oge.ck-merkez')); }
      else { return; }
      ev.preventDefault();
    });
  }
  function tikla(oge) {
    if (!oge) { return; }
    var i = S.liste.indexOf(oge); if (i < 0) { return; }
    var simdi = Date.now(), cift = S.sonTik && S.sonTik.oge === oge && simdi - S.sonTik.t < 380;
    S.sonTik = {oge: oge, t: simdi};
    var merkezde = i === seciliIdx() && Math.abs(S.hedef - S.pos) < 0.05;
    if (cift || merkezde) { S.sonTik = null; detay(oge.getAttribute('data-lok'), oge); return; }
    git(Math.round(S.pos + ofset(i)));
  }

  // ── Bağlan / denetle ──
  function bagla(sahne, srm) {
    S.el = sahne; S.srm = srm;
    try { S.veri = JSON.parse(sahne.getAttribute('data-veri') || '{}'); } catch (e) { S.veri = {lok: {}, genel: {}}; }
    S.veri.lok = S.veri.lok || {};
    S.veri.ikon = W.__synCarkIkon || {};
    S.canli = {}; S.durum = {};
    S.cark = sahne.querySelector('.ck-cark'); S.svg = sahne.querySelector('svg.ck-baglar');
    S.ray = sahne.querySelector('.ck-ray'); S.tutamak = sahne.querySelector('.ck-ray-tutamak');
    S.ogeler = Array.prototype.slice.call(S.cark.querySelectorAll('.ck-oge'));
    var kutu = sahne.querySelector('.ck-ara-kutu');
    if (kutu && S.sorgu && kutu.value !== S.sorgu) { kutu.value = S.sorgu; }
    if (sahne.__ckDinle !== S) { dinle(sahne); sahne.__ckDinle = S; }
    sahne.setAttribute('data-kalem', S.aktifKart);
    sahne.querySelectorAll('.ck-kart').forEach(function (x) { x.classList.toggle('ck-aktif', x.getAttribute('data-kalem') === S.aktifKart); });
    var sb = sahne.querySelector('.ck-sirala'); if (sb) { sb.classList.toggle('ck-acik', !!S.sirala); }
    S.taban = Array.prototype.slice.call(S.cark.querySelectorAll('.ck-oge'));
    if (!S.secili && S.veri.sira && S.veri.sira.length) { S.secili = S.veri.sira[0]; }
    havuz();
    siraUygula(false);
    panel();
    geriGiris();
  }
  function kontrol() {
    var sahne = d.querySelector('.ck-sahne');
    if (!sahne) {
      if (S.el) { S.el = null; katmanKapat(); }
      return;
    }
    var srm = sahne.getAttribute('data-surum');
    if (sahne !== S.el || srm !== S.srm || !S.cark || !S.cark.isConnected) { bagla(sahne, srm); }
  }
  S.kontrol = kontrol; S.panel = panel;
  function boyut() { if (S.el) { yerlestir(); } }
  function tus(ev) { if (ev.key === 'Escape') { katmanKapat(); } }
  W.addEventListener('resize', boyut);
  d.addEventListener('keydown', tus);
  S.aralik = W.setInterval(kontrol, 400);
  S.ornekAralik = W.setInterval(ornekle, 1000);
  S.boyut = boyut; S.tus = tus;
  kontrol();
})();
</script>
""".replace("__GECIS_STIL__", _gecis_stil()).replace("__SURUM__", str(SURUM)).replace("__K__", str(CARK_YARI)).replace(
        "__IKON__", json.dumps(ikonlar or {}, ensure_ascii=False).replace("</", "<\\/"))
