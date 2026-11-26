# -*- coding: utf-8 -*-
"""
LOKASYON DETAY — KOYU CAM TEMA + GEÇİŞ ANİMASYONU (ÇARK ARAYÜZÜ)
================================================================

app_merkez.py bunu çark arayüzü açıkken (_cark_arayuz: sunumda 17.11.2026'dan,
canlıda 23.11.2026'dan beri varsayılan) lokasyon detayında ve Sistem ekranında basar.
Veri ve hesap pages/lokasyon_detay.py'dedir; bu modül GÖRÜNÜM CSS'i ve geçiş betiğidir.
Geri dönüş: SYNAPSE_ESKI_ARAYUZ=1 → bu modül hiç yüklenmez. Adındaki "_demo" tarihseldir.

KAPSAM (tema_css)
  * Zemin, cam kartlar (.dz-kart, .cg-ozet, .cg-grup...), yazı ve vurgu renkleri
    — renkler ana ekranla AYNI palet bloğundan (ana_ekran_cark_demo.PALET_CSS).
  * Streamlit öğeleri: sekmeler, düğmeler (Geri, Excel), seçim kutusu ve listesi,
    tarih kutusu, radyo, açılır bölüm, bilgi kutusu, metrik, ayırıcı, açıklama.
  * Satır içi stiller: sayfadaki koyu yazı renkleri ve açık zeminler (hem yazıldığı
    biçim hem tarayıcının rgb() biçimi) koyu temaya eşlenir; durum renkleri
    (yeşil / kırmızı / amber / lokasyon rengi) korunur.
  * Plotly: eksen / başlık / gösterge yazıları ve ızgara çizgileri (zemin zaten saydam).
  * Kapsam DIŞI: st.dataframe (tuval çizimi, CSS ile boyanmaz), tarih seçicinin
    açılır takvimi (açık kalır).

DÜZEN: detay ekranın SAĞINDA yüksek cam panel (--ck-dp-* değişkenleri); solda
  çark ekranının bulanık, karartılmış izi (_iz_svg, sabit arka plan).

GEÇİŞ (GECIS_CSS + GECIS_JS — motor ANA BELGEDE yaşar, betik çerçevesiyle ölmez)
  İleri (tıklama anında, yeniden çizim beklenmeden): ana sahne bulanıklaşıp
  kararır, hafif küçülüp uzaklaşır; seçili öğenin yerinden iskelet cam panel
  (parıldayan yer tutucular) sağdaki detay paneli yerine büyür (440 ms). Detay
  çizilince içerik aynı yerdeki panelde belirir, iskelet söner (420 ms).
  Geri: panel iskelete döner ve çark ekranındaki sağ panelin yerine küçülür
  (550 ms); ana sahne netleşerek gelir (660 ms).
  Hız: tıklamalar on_click'li görünmez düğmelere gider (detay_ac / geri_ac):
  durum yeniden çizimden ÖNCE yazılır, ara bir ana ekran / detay çizimi olmaz.
  Durum gövde sınıflarıyla taşınır; geçiş sürerken sayfa değişimi (eski 3 sütun,
  açık zemin) opacity ile gizlenir. Emniyet: kaplama 16 sn, sahne 6 sn sonra
  CSS ile kendiliğinden açılır. prefers-reduced-motion: yalnız yumuşak geçiş.
"""

import re

import ana_ekran_cark_demo as _cark

SURUM = 28  # app_merkez bu sayıyla açık süreçte modülü yeniden yükler

KOK = ('body:has(.st-key-detay_tema_demo):not(:has(.st-key-ozet_gecis_katmani))'
       ':not(:has(.st-key-yonetim_katmani))')
DETAY = ".st-key-detay_gecis_katmani"

# Sayfadaki koyu yazı renkleri → koyu zeminde okunur karşılıkları
_YAZI_ESLE = {
    "#0f1f3d": "var(--ck-metin)", "#133273": "var(--ck-metin)", "#24324d": "var(--ck-metin)",
    "#46536b": "var(--ck-metin-2)", "#8b97ab": "var(--ck-metin-3)", "#9aa2b1": "var(--ck-metin-3)",
    "#2a78d6": "var(--ck-mavi)", "#006300": "#9ff3cd", "#b42525": "#ffb8ae", "#8a5a00": "#ffe3a8",
}
# Açık zeminler → cam
_ZEMIN_ESLE = ("#fafaf8", "#ffffff", "#fff", "#f1f0ed", "#eef3fb", "#f3f6fb", "#f6f8fc", "#f8fafd")


def _rgb(h: str) -> str:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "rgb(%d, %d, %d)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _satir_ici_kurallar() -> str:
    """Satır içi stil eşlemesi. Seçici hem yazıldığı biçimi (color:#46536b) hem
    tarayıcının yazdığı biçimi (color: rgb(70, 83, 107)) yakalar."""
    k = []
    for hx, yeni in _YAZI_ESLE.items():
        sec = ", ".join("§ D [style*=\"%s\"]" % s for s in (
            "color:%s" % hx, "color: %s" % hx, "color: %s" % _rgb(hx)))
        k.append("%s{ color:%s !important; }" % (sec, yeni))
    zs = []
    for hx in _ZEMIN_ESLE:
        zs += ["background:%s;" % hx, "background: %s;" % hx,
               "background-color: %s" % _rgb(hx), "background: %s" % _rgb(hx)]
    k.append(", ".join("§ D [style*=\"%s\"]" % s for s in zs)
             + "{ background:rgba(255,255,255,.045) !important; border-color:var(--ck-cam-kenar) !important;"
               " box-shadow:none !important; }")
    k.append("§ D [style*=\"rgba(243,246,251\"], § D [style*=\"rgba(243, 246, 251\"]"
             "{ background:rgba(255,255,255,.05) !important; }")
    return "\n".join(k)


_TEMA = """
§{ PALET background:var(--ck-zemin-1) !important; }
html:has(.st-key-detay_tema_demo){ background:#03141a !important; }
§ [data-testid="stAppViewContainer"], § [data-testid="stAppViewContainer"] > div:first-child,
§ [data-testid="stAppViewContainer"] > div:first-child > div:first-child{
  background:
    radial-gradient(ellipse 50% 45% at 15% 12%, rgba(46,196,182,.10), transparent 62%),
    radial-gradient(ellipse 45% 50% at 88% 8%, rgba(91,155,255,.07), transparent 66%),
    linear-gradient(160deg, var(--ck-zemin-2) 0%, var(--ck-zemin-1) 55%, #020d11 100%) !important;
  background-attachment:fixed !important; }
§ [data-testid="stHeader"]{ background:transparent !important; }

/* ── Kompozisyon: solda ana ekranın bulanık izi, sağda yüksek cam panel ── */
§ [data-testid="stAppViewContainer"]::before{ content:""; position:fixed; inset:-30px; z-index:0; pointer-events:none;
  background:url("IZ_SVG") left center / auto 100% no-repeat;
  filter:blur(7px) brightness(.62) saturate(.85); opacity:.95;
  will-change:transform; transform:translateZ(0); }
/* Bulanık iz kendi katmanında bir kez çizilir; her karede yeniden bulanıklaştırılmaz (24.11.2026) */
§ [data-testid="stMain"]{ position:relative; z-index:1; }
§:not(.ck-geri-surer) [data-testid="stMainBlockContainer"]{
  margin:var(--ck-dp-ust, 50px) var(--ck-dp-sag, 1.6vw) var(--ck-dp-alt, 1.4vh) var(--ck-dp-sol, 27vw) !important;
  width:auto !important; max-width:none !important; box-sizing:border-box; flex:0 0 auto !important;
  align-self:stretch !important; min-width:0 !important;
  height:calc(100vh - var(--ck-dp-ust, 50px) - var(--ck-dp-alt, 1.4vh)) !important;
  height:calc(100dvh - var(--ck-dp-ust, 50px) - var(--ck-dp-alt, 1.4vh)) !important; min-height:0 !important;
  overflow:hidden !important; display:flex !important; flex-direction:column;
  padding:calc(var(--ck-u) * 1.3) calc(var(--ck-u) * 2) calc(var(--ck-u) * 1.2) !important; border-radius:22px;
  background:linear-gradient(180deg, rgba(22,62,72,.93), rgba(7,28,35,.95)) !important;
  border:1px solid rgba(150,225,225,.30);
  box-shadow:0 40px 90px -30px rgba(0,0,0,.85), 0 0 0 6px rgba(46,196,182,.05), inset 0 1px 0 rgba(255,255,255,.07); }
§ .st-key-detay_gecis_katmani{ padding-top:2px !important; animation:none !important; }

/* ── TEK EKRAN: panel görünür yüksekliğe kilitli; sayfa kaymaz, yalnız sekme
   içeriği panelin İÇİNDE kayar. Başlık, sekmeler, özet şeridi ve grafik ilk
   bakışta görünür (grafik yüksekliği lokasyon_detay._dz_gh ile ekrana oranlı). ── */
§ [data-testid="stMain"]{ overflow:hidden !important; }
§ [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"]{ flex:1 1 auto; min-height:0; gap:0 !important; }
§ [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:has(> .st-key-detay_gecis_katmani),
§ .st-key-detay_gecis_katmani, § .st-key-detay_gecis_katmani > [data-testid="stLayoutWrapper"]:has(> .st-key-detay_sekmeler),
§ .st-key-detay_sekmeler, § .st-key-detay_sekmeler > [data-testid="stTabs"],
§ .st-key-detay_sekmeler > [data-testid="stTabs"] > div{
  flex:1 1 auto; min-height:0; display:flex !important; flex-direction:column; }
§ .st-key-detay_gecis_katmani{ gap:calc(var(--ck-u) * .6) !important; }
§ .st-key-detay_sekmeler [data-testid="stTabPanel"]{ flex:1 1 auto; min-height:0; overflow-y:auto !important; overflow-x:hidden;
  padding:calc(var(--ck-u) * 1) calc(var(--ck-u) * 1.2) !important; scrollbar-width:thin; scrollbar-color:rgba(134,232,220,.28) transparent; }
§ .st-key-detay_sekmeler [data-testid="stTabPanel"]:is([hidden], [inert], [data-inert="true"]){ display:none !important; }
/* Pasif sekme react-aria ile data-inert="true" alır (hidden değil); grafik seçince Canlı İzleme paneli de görünüyordu (19.11.2026) */
/* Sağ üstteki Sistem ayarları / Yönetim / Çıkış yalnız ana ekranda (çark alt çubuğu); detayda gizli (19.11.2026) */
§ .st-key-cikis_kutusu{ display:none !important; }
/* Sunumda tek sekme (Canlı İzleme ana ekran kartında): sekme şeridi gizli */
§ .st-key-detay_sekmeler :is([role="tablist"], [data-baseweb="tab-list"], [data-baseweb="tab-border"]){ display:none !important; }
/* Başlık satırı kompakt */
§ D .dz-baslik{ font-size:clamp(15px, calc(var(--ck-u) * 2.3), 22px) !important; letter-spacing:2px !important; }
§ D .dz-ust{ font-size:max(7px, calc(var(--ck-u) * .9)) !important; letter-spacing:4px !important; }
§ D > [data-testid="stLayoutWrapper"]:first-of-type div[style*="padding:8px 0"], § D > [data-testid="stLayoutWrapper"] div[style*="padding: 8px 0"]{
  padding:2px 0 !important; }
§ D [data-testid="stTab"]{ padding-top:calc(var(--ck-u) * .6) !important; padding-bottom:calc(var(--ck-u) * .6) !important; }
§ D .sec{ margin-top:calc(var(--ck-u) * .6) !important; padding:2px 0 calc(var(--ck-u) * .5) !important;
  margin-bottom:calc(var(--ck-u) * .6) !important; font-size:max(9px, calc(var(--ck-u) * 1.15)) !important; }

/* ── Dashboard: ÖZET tek sıra şerit, grafik altında kalan alanı alır ── */
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim){
  flex-wrap:wrap !important; row-gap:calc(var(--ck-u) * .6) !important; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) > [data-testid="stColumn"]{
  flex:1 1 100% !important; width:100% !important; min-width:100% !important; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) > [data-testid="stColumn"]:first-child > [data-testid="stVerticalBlock"]{
  display:grid !important; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:calc(var(--ck-u) * .8) !important; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) > [data-testid="stColumn"]:first-child > [data-testid="stVerticalBlock"] > :first-child{
  grid-column:1 / -1; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) > [data-testid="stColumn"]:first-child .dz-kart{
  margin-bottom:0 !important; height:100%; box-sizing:border-box; padding:calc(var(--ck-u) * .8) calc(var(--ck-u) * 1.1) !important; gap:9px !important; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) > [data-testid="stColumn"]:first-child .dz-kart .ai{
  width:calc(var(--ck-u) * 2.4) !important; height:calc(var(--ck-u) * 2.4) !important; }
§ D .dz-et{ font-size:max(8px, calc(var(--ck-u) * 1)) !important; letter-spacing:1px !important; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
§ D .dz-alt{ font-size:max(8px, calc(var(--ck-u) * .95)) !important; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
/* Grafik sütunu: Excel düğmesi başlık satırına alınır (dikey yer kazanır) */
§ D [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] .st-key-grafik_secim) > [data-testid="stVerticalBlock"]{ position:relative; }
§ D [data-testid="stLayoutWrapper"]:has(> [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > .st-key-grafik_excel){
  position:absolute !important; right:0; width:100px !important; z-index:2;
  top:max(0px, min(calc(var(--ck-u) * .6 + 2px + max(9px, var(--ck-u) * 1.15) * .8 - 11px),
                   calc(var(--ck-u) * 1.1 + 2px + max(9px, var(--ck-u) * 1.15) * 1.6 - 24px))); }
/* top:-4px kaydırılan kutunun üst kenarında düğmenin yarısını kesiyordu (24.11.2026).
   Konum (24.11.2026): düğme (22 px) GRAFİK yazısıyla aynı hizada ortalanır, alt kenarı
   başlık çizgisinin üstünde kalır. .sec: üst boşluk .6u + 2px, yazı max(9px,1.15u) × 1.6
   satır yüksekliği, alt boşluk .5u → çizgi; ekran küçükse üstten taşmasın diye en az 0. */
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > .st-key-grafik_excel) > [data-testid="stColumn"]:first-child{ display:none !important; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > .st-key-grafik_excel) > [data-testid="stColumn"]{ width:100% !important; flex:1 1 100% !important; }
§ D [data-testid="stColumn"]:has(.st-key-grafik_secim) > [data-testid="stVerticalBlock"]{ gap:calc(var(--ck-u) * .7) !important; }
§ D .st-key-grafik_excel button{ min-height:22px !important; height:22px !important; padding:0 12px !important;
  display:flex !important; }   /* satır içi düğme taban çizgisine oturup 2-3 px aşağı kayıyordu */
/* Yazı düğmenin ortasında: dış kap 14 px / 22,4 px satır kutusuyla yazıyı taban çizgisine
   indiriyor, alttan taşırıyordu (24.11.2026) — kap ve yazı aynı boy, satır yüksekliği 1 */
§ D .st-key-grafik_excel button > div, § D .st-key-grafik_excel button span,
§ D .st-key-grafik_excel button [data-testid="stMarkdownContainer"]{ height:100% !important; display:flex !important;
  align-items:center !important; justify-content:center !important; font-size:12px !important; line-height:1 !important; }
§ D .st-key-grafik_excel button span[style*="contents"]{ display:contents !important; }
§ D .st-key-grafik_excel button p{ font-size:12px !important; line-height:1 !important; margin:0 !important; display:block !important; }
/* Canlı İzleme satırları dar sütunda kesilmesin: sabit 86/60/92 px ızgara yerine
   ad (daralabilir) · çubuk (esnek) · değer (sığdığı kadar) */
§ D .cg-liste:not(.cg-liste-blok){ grid-template-columns:minmax(0, max-content) minmax(14px, 1fr) max-content !important;
  column-gap:calc(var(--ck-u) * .6) !important; }
§ D .cg-liste .cg-cip{ min-width:0 !important; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  font-size:max(9px, calc(var(--ck-u) * 1.05)) !important; }
§ D .cg-liste .cg-dg{ white-space:nowrap; text-align:right; }
§ D .cg-liste .cg-dg .canli-sayi{ font-size:clamp(11px, calc(var(--ck-u) * 1.5), 15px) !important; }
§ D .cg-liste .cg-yas{ font-size:max(8px, calc(var(--ck-u) * .85)) !important; }

/* ── Dashboard TEK EKRAN (kaydırmasız): sol = özet şeridi + grafik, sağ = yan sütun
   (kojen & kaynak, bakım, setler, sistem sağlığı) KENDİ kutusunda ince kaydırmayla.
   Sekme paneli kaymaz; grafik yüksekliği ekrana oranlı (lokasyon_detay._dz_gh). ── */
§ .st-key-detay_sekmeler [data-testid="stTabPanel"]:not([hidden]):not([inert]):not([data-inert="true"]):has(.st-key-dz_yan){ overflow:hidden !important;
  display:flex !important; flex-direction:column; }
§ .st-key-detay_sekmeler [data-testid="stTabPanel"]:has(.st-key-dz_yan) > [data-testid="stVerticalBlock"]{
  flex:1 1 auto; min-height:0; display:grid !important; grid-template-columns:minmax(0, 1fr) clamp(300px, 34%, 500px);
  grid-template-rows:minmax(0, 1fr); column-gap:calc(var(--ck-u) * 1.5) !important; row-gap:0 !important; }
§ .st-key-detay_sekmeler [data-testid="stTabPanel"]:has(.st-key-dz_yan) > [data-testid="stVerticalBlock"] > *{
  grid-column:1; grid-row:1; min-width:0; min-height:0; }
§ .st-key-detay_sekmeler [data-testid="stTabPanel"]:has(.st-key-dz_yan) > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:has(> .st-key-dz_yan){
  grid-column:2; overflow-y:auto; overflow-x:hidden; padding:0 4px 0 calc(var(--ck-u) * 1.3);
  border-left:1px solid rgba(134,232,220,.12); scrollbar-width:thin; scrollbar-color:rgba(134,232,220,.28) transparent; }
§ D .st-key-dz_yan{ gap:calc(var(--ck-u) * .6) !important; }
/* ── 19.11.2026: grafik solda tüm yükseklik (uzun içerik — KPI Özet vb. — kendi içinde kayar);
   özet kartları sağ sütunun başında kojen & kaynak gibi kompakt ızgarada, çerçeveli kart içinde ── */
§ .st-key-detay_sekmeler [data-testid="stTabPanel"]:has(.st-key-dz_yan) > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:has(> .st-key-dz_grafik){
  overflow-y:auto; overflow-x:hidden; padding-right:calc(var(--ck-u) * .4);
  scrollbar-width:thin; scrollbar-color:rgba(134,232,220,.28) transparent; }
§ D .st-key-dz_grafik{ position:relative; gap:calc(var(--ck-u) * .7) !important; }
§ D .st-key-dz_ozet{ display:grid !important; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:calc(var(--ck-u) * .6) !important;
  padding:calc(var(--ck-u) * .9) !important; border-radius:calc(var(--ck-u) * 1.4);
  background:rgba(255,255,255,.035); border:1px solid var(--ck-cam-kenar); }
§ D .st-key-dz_ozet > *{ min-width:0; }
§ D .st-key-dz_ozet > :first-child{ grid-column:1 / -1; }
§ D .st-key-dz_ozet .sec{ margin:0 !important; }
§ D .st-key-dz_ozet .dz-kart{ margin-bottom:0 !important; height:100%; box-sizing:border-box; }
§ D .st-key-dz_yan div:is([style*="grid-template-columns:repeat("], [style*="grid-template-columns: repeat("]){
  padding:calc(var(--ck-u) * .9) !important; border-radius:calc(var(--ck-u) * 1.4);
  background:rgba(255,255,255,.035); border:1px solid var(--ck-cam-kenar); }
/* 26.11.2026: özet + kojen & kaynak kartları yan sütunun boyunu doldurur — altında boşluk kalmaz,
   kartlar grafik sütunuyla aynı yerde biter. Fazla yükseklik satır sayısıyla orantılı paylaşılır
   (özet 3 satır : kaynak 5 satır); içerik sığmazsa küçülmez, sütun eskisi gibi kendi içinde kayar. */
§ D .st-key-dz_yan > [data-testid="stLayoutWrapper"]:first-child{ flex:3 0 auto !important; }   /* özet kabı */
§ D .st-key-dz_yan .st-key-dz_ozet{ height:100%; grid-template-rows:auto; grid-auto-rows:1fr; align-items:stretch !important; }
§ D .st-key-dz_yan .st-key-dz_ozet > [data-testid="stElementContainer"]{ display:flex !important; flex-direction:column; }
§ D .st-key-dz_yan .st-key-dz_ozet > [data-testid="stElementContainer"] :is([data-testid="stMarkdown"], [data-testid="stMarkdown"] > div, [data-testid="stMarkdownContainer"]){
  flex:1 1 auto !important; display:flex !important; flex-direction:column; width:100%; }
§ D .st-key-dz_yan .st-key-dz_ozet .dz-kart{ flex:1 1 auto; }
/* Kaynak ızgarası yan sütunun SON öğesi (lokasyon_detay: tek ekranda ızgaradan sonra kap kapanır).
   :has(div[style*=...]) KULLANILMAZ: her DOM değişikliğinde tüm sayfa stilini yeniden hesaplatıyor,
   geri dönüşte iskelet ~3 sn fazla bekliyordu (26.11.2026 ölçüm: 74 ms → 0,2 ms / değişiklik) */
§ D .st-key-dz_yan > [data-testid="stElementContainer"]:last-child{
  flex:5 0 auto !important; display:flex !important; flex-direction:column; }
§ D .st-key-dz_yan > [data-testid="stElementContainer"]:last-child :is([data-testid="stMarkdown"], [data-testid="stMarkdown"] > div, [data-testid="stMarkdownContainer"]){
  flex:1 1 auto !important; display:flex !important; flex-direction:column; width:100%; }
§ D .st-key-dz_yan div:is([style*="grid-template-columns:repeat("], [style*="grid-template-columns: repeat("]){ flex:1 1 auto; grid-auto-rows:1fr; }
/* Streamlit metin kutusuna -16px alt boşluk verir; sıkı düzende kartlar üst üste biniyordu (18.11.2026) */
§ D [data-testid="stMarkdownContainer"]{ margin-bottom:0 !important; }
§ D .st-key-dz_yan .sec{ margin-top:calc(var(--ck-u) * .4) !important; }
§ D .st-key-dz_yan div[style*="margin-top:18px"], § D .st-key-dz_yan div[style*="margin-top: 18px"]{ margin-top:0 !important; }
§ D .st-key-dz_yan [data-testid="stHorizontalBlock"]{ flex-wrap:wrap !important; gap:calc(var(--ck-u) * .6) !important; }
§ D .st-key-dz_yan [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{
  flex:1 1 100% !important; width:100% !important; min-width:100% !important; }
§ D .st-key-dz_yan div:is([style*="grid-template-columns:repeat("], [style*="grid-template-columns: repeat("]){
  grid-template-columns:repeat(2, minmax(0, 1fr)) !important; gap:calc(var(--ck-u) * .6) !important; margin-bottom:0 !important; }
§ D .st-key-dz_yan .dz-kart{ padding:calc(var(--ck-u) * .65) calc(var(--ck-u) * .9) !important; gap:7px !important;
  border-radius:calc(var(--ck-u) * 1.1) !important; min-width:0; }
§ D .st-key-dz_yan .dz-kart .ai{ width:calc(var(--ck-u) * 2) !important; height:calc(var(--ck-u) * 2) !important; flex-shrink:0; }
§ D .st-key-dz_yan .dz-dg{ font-size:clamp(12px, calc(var(--ck-u) * 1.75), 18px) !important; }
§ D .st-key-dz_yan :is(details, [style*="border-radius:16px"], [style*="border-radius: 16px"]){
  padding:calc(var(--ck-u) * .8) calc(var(--ck-u) * 1.1) !important; border-radius:calc(var(--ck-u) * 1.1) !important; }
§ D .st-key-dz_yan [style*="font-size:26px"], § D .st-key-dz_yan [style*="font-size: 26px"]{ font-size:clamp(15px, calc(var(--ck-u) * 2.1), 22px) !important; }
§ D .st-key-dz_yan [style*="font-size:15px"], § D .st-key-dz_yan [style*="font-size: 15px"]{ font-size:max(11px, calc(var(--ck-u) * 1.35)) !important; }
§ D .st-key-dz_yan .ai[width="34"], § D .st-key-dz_yan svg[width="34"]{ width:calc(var(--ck-u) * 2.6) !important; height:calc(var(--ck-u) * 2.6) !important; }
/* ── Canlı İzleme TEK EKRAN: üst şerit tek sıra; gruplar çok sütunlu kompakt ızgara,
   kalan yüksekliği doldurur; uzun cihaz listesi grubun İÇİNDE ince kaydırmayla ── */
§ .st-key-detay_sekmeler [data-testid="stTabPanel"]:not([hidden]):not([inert]):not([data-inert="true"]):has(.cg-sarmal){ overflow:hidden !important;
  display:flex !important; flex-direction:column; }
§ .st-key-detay_sekmeler [data-testid="stTabPanel"] :is([data-testid="stVerticalBlock"], [data-testid="stLayoutWrapper"],
  [data-testid="stElementContainer"], [data-testid="stMarkdown"], [data-testid="stMarkdown"] > div,
  [data-testid="stMarkdownContainer"]):has(.cg-sarmal){
  flex:1 1 auto !important; min-height:0 !important; display:flex !important; flex-direction:column; width:100% !important; }
§ D .cg-serit{ display:grid !important; grid-template-columns:repeat(auto-fit, minmax(104px, 1fr)); gap:calc(var(--ck-u) * .7) !important;
  margin-bottom:calc(var(--ck-u) * .8) !important; flex:0 0 auto; }
§ D .cg-serit > *{ width:auto !important; min-width:0 !important; margin:0 !important; }
§ D .cg-serit .cg-ozet{ padding:calc(var(--ck-u) * .6) calc(var(--ck-u) * .9) !important; border-radius:calc(var(--ck-u) * 1.1) !important; }
§ D .cg-serit .cg-ozet-ikili{ grid-column:span 2; display:flex !important; gap:calc(var(--ck-u) * .6) !important; }
§ D .cg-serit .cg-ozet-ikili .cg-ic{ flex:1 1 0; min-width:0; padding:calc(var(--ck-u) * .4) calc(var(--ck-u) * .7) !important; }
§ D :is(.cg-ozet-et, .cg-ozet-alt){ font-size:max(8px, calc(var(--ck-u) * .95)) !important; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
§ D .cg-ozet-et{ letter-spacing:1px !important; text-transform:uppercase; }
§ D .cg-ozet-dg{ font-size:clamp(14px, calc(var(--ck-u) * 2.1), 24px) !important; line-height:1.15 !important; white-space:nowrap; }
§ D .cg-sarmal{ flex:1 1 auto; min-height:0; display:grid !important; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr));
  grid-auto-rows:minmax(0, 1fr); gap:calc(var(--ck-u) * .8) !important; overflow:hidden; margin:0 !important; }
§ D .cg-sarmal > .cg-grup{ width:auto !important; min-width:0 !important; min-height:0; max-height:none !important; margin:0 !important;
  display:flex !important; flex-direction:column; overflow:hidden; padding:calc(var(--ck-u) * .8) calc(var(--ck-u) * 1) !important;
  border-radius:calc(var(--ck-u) * 1.2) !important; }
§ D .cg-grup h4{ font-size:max(9px, calc(var(--ck-u) * 1.1)) !important; letter-spacing:1.4px !important; padding:0 0 calc(var(--ck-u) * .4) !important;
  margin:0 0 calc(var(--ck-u) * .3) !important; }
§ D .cg-grup [data-testid="stHeadingWithActionElements"]{ margin:0 !important; }
§ D .cg-grup :is(.cg-ack, .cg-dip){ font-size:max(8px, calc(var(--ck-u) * .9)) !important; flex:0 0 auto; }
§ D .cg-grup .cg-toplam{ font-size:clamp(13px, calc(var(--ck-u) * 1.9), 21px) !important; }
§ D .cg-grup .cg-liste{ flex:1 1 auto; min-height:0; max-height:none !important; overflow-y:auto !important; overflow-x:hidden;
  font-size:max(9px, calc(var(--ck-u) * 1.05)) !important; scrollbar-width:thin; }
§ D .cg-alt{ flex:0 0 auto; margin-top:calc(var(--ck-u) * .5) !important; font-size:max(8px, calc(var(--ck-u) * .9)) !important; }
/* Sol sütun: özet şeridi kompakt (tek sıra), grafik altında */
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) > [data-testid="stColumn"]:first-child > [data-testid="stVerticalBlock"]{
  grid-template-columns:repeat(3, minmax(0, 1fr)) !important; gap:calc(var(--ck-u) * .6) !important; } /* 3×2: sayılar sığsın */
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) .dz-dg{
  font-size:clamp(13px, calc(var(--ck-u) * 2), 21px) !important; white-space:nowrap; }
/* Özet kartları üst üste binmesin: kart taşmaz, uzun etiket/değer kart içinde kalır */
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) .dz-kart{
  min-width:0 !important; overflow:hidden !important; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) .dz-kart > div{
  min-width:0 !important; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) .dz-dg span{
  font-size:.62em !important; }
§ D [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .dz-kart):has(> [data-testid="stColumn"] .st-key-grafik_secim) .dz-kart{
  padding:calc(var(--ck-u) * .6) calc(var(--ck-u) * .9) !important; gap:7px !important; }
§ .st-key-ck_detay_geri{ position:fixed !important; left:-9999px !important; top:0 !important; width:1px !important;
  height:1px !important; overflow:hidden !important; }
§ .st-key-detay_tema_demo{ gap:0 !important; }
§ .st-key-detay_tema_demo [data-testid="stElementContainer"]{ height:0 !important; margin:0 !important; overflow:hidden; }
@media (max-width:1000px){ § [data-testid="stAppViewContainer"]::before{ opacity:.4; } }
§ ::-webkit-scrollbar-track{ background:transparent; }
§ ::-webkit-scrollbar-thumb{ background:rgba(134,232,220,.22); }
/* Simülasyon etiketi koyu zeminde */
§ div:is([style*="position:fixed;top:10px;left:18px"], [style*="position: fixed; top: 10px; left: 18px"]){
  background:rgba(242,180,65,.14) !important; border-color:rgba(242,180,65,.45) !important; }
§ div:is([style*="position:fixed;top:10px;left:18px"], [style*="position: fixed; top: 10px; left: 18px"]) *{ color:#f2c66d !important; }
/* Sağ üst düğmeler (ayarlar / yönetim / çıkış): koyu cam */
§ .st-key-cikis_kutusu .stButton button, § .st-key-cikis_kutusu a.ayar-ac{
  background:rgba(14,46,56,.7) !important; border:1px solid var(--ck-cam-kenar) !important;
  box-shadow:0 10px 22px -14px rgba(0,0,0,.8) !important; }
§ .st-key-cikis_kutusu .stButton button p::before, § .st-key-cikis_kutusu a.ayar-ac::before{ background:#cfe7ea !important; }
§ .st-key-cikis_kutusu .stButton button:hover, § .st-key-cikis_kutusu a.ayar-ac:hover{
  background:rgba(46,196,182,.3) !important; border-color:rgba(134,232,220,.5) !important; }

/* ── Yazı: varsayılan açık; sınıfla / satır içinde renk verilenler korunur ── */
:where(§ D) :is(p,li,span,div,label,td,th,small,b,strong,h1,h2,h3,h4,h5,summary):is(p,li,span,div,label,td,th,small,b,strong,h1,h2,h3,h4,h5,summary){
  color:var(--ck-metin); }
§ D .sec{ color:var(--ck-vurgu-acik) !important; border-bottom-color:rgba(134,232,220,.14) !important; }
§ D .dz-ust{ background:linear-gradient(90deg, var(--ck-vurgu), #d4fbf5, var(--ck-vurgu)) !important;
  background-size:200% 100% !important; -webkit-background-clip:text !important; background-clip:text !important; }
§ D .dz-baslik{ filter:drop-shadow(0 0 16px rgba(46,196,182,.35)) !important; }
§ D div[style*="height:1px"][style*="background"], § D div[style*="height: 1px"][style*="background"]{
  background:rgba(134,232,220,.12) !important; }

/* ── Cam kartlar ── */
§ D :is(.dz-kart, .cg-ozet, .cg-grup){
  background:linear-gradient(180deg, rgba(24,68,78,.50), rgba(10,36,44,.55)) !important;
  border:1px solid var(--ck-cam-kenar) !important;
  box-shadow:0 18px 40px -26px rgba(0,0,0,.85), inset 0 1px 0 rgba(255,255,255,.05) !important;}
§ D :is(.cg-ic, .cg-altkart){ background:rgba(255,255,255,.045) !important; border-color:rgba(255,255,255,.08) !important; }
§ D :is(.dz-et, .cg-ozet-et, .cg-ack, .cg-alt, .dz-alt, .dz-br, .cg-br, .dz-not, .cg-ozet-alt){ color:var(--ck-metin-2) !important; }
§ D :is(.dz-dg, .cg-ozet-dg, .cg-toplam, .cg-dg, .dz-satir-ad){ color:#ffffff !important; }
§ D .dz-dg{ font-size:clamp(17px, 1.55vw, 24px) !important; white-space:nowrap; }
§ D :is(.cg-grup h4, .cg-altkart-bas){ color:var(--ck-vurgu-acik) !important; border-bottom-color:rgba(255,255,255,.08) !important; }
§ D :is(.cg-dip, .cg-yas, .cg-bos-not, .cg-dg-yok, .cg-altkart-bekle .cg-altkart-tp){ color:var(--ck-metin-3) !important; }
§ D .cg-dip{ border-top-color:rgba(255,255,255,.07) !important; }
§ D .cg-liste > .cg-satir > *{ border-bottom-color:rgba(255,255,255,.06) !important; }
§ D .cg-cip{ background:rgba(255,255,255,.06) !important; border-color:rgba(255,255,255,.12) !important; color:var(--ck-metin) !important; }
§ D .cg-cip.cg-yok{ color:var(--ck-metin-3) !important; background:rgba(255,255,255,.03) !important; }
§ D .cg-cip-ust{ background:rgba(46,196,182,.14) !important; border-color:rgba(134,232,220,.35) !important; color:var(--ck-vurgu-acik) !important; }
§ D :is(.cg-liste, .cg-sarmal, .sabah-kaydir, [style*="overflow"]){ scrollbar-color:rgba(134,232,220,.28) transparent !important; }
§ D *::-webkit-scrollbar-thumb{ background:rgba(134,232,220,.28) !important; }
§ D *::-webkit-scrollbar-track{ background:transparent !important; }
§ D .cg-iz{ background:rgba(255,255,255,.08) !important; box-shadow:none !important; }
§ D .cg-bos .cg-tire{ border-top-color:rgba(255,255,255,.16) !important; }
§ D .cg-alt-ayrac{ color:var(--ck-metin-3) !important; }
§ D .dz-satir{ background:color-mix(in srgb, var(--k) 12%, rgba(10,36,44,.7)) !important;
  border-color:color-mix(in srgb, var(--k) 40%, transparent) !important; }
§ D .dz-cip{ background:color-mix(in srgb, var(--k) 18%, transparent) !important;
  color:color-mix(in srgb, var(--k) 45%, #ffffff) !important; }
§ D details > summary{ color:var(--ck-metin); }

/* ── Sekmeler ── */
§ D [data-testid="stTabs"] [data-baseweb="tab-list"]{ border-bottom:1px solid rgba(134,232,220,.14) !important; }
§ D [data-testid="stTabs"] [data-baseweb="tab"], § D [data-testid="stTabs"] [role="tab"]{ color:var(--ck-metin-2) !important; }
§ D [data-testid="stTabs"] [role="tab"] p{ color:inherit !important; }
§ D [data-testid="stTabs"] [aria-selected="true"]{ color:var(--ck-vurgu-acik) !important;
  box-shadow:inset 0 -2px 0 var(--ck-vurgu), 0 6px 16px -10px rgba(46,196,182,.7) !important; }
§ D [data-testid="stTabs"] [data-baseweb="tab-highlight"]{ background-color:var(--ck-vurgu) !important;
  box-shadow:0 -2px 10px rgba(46,196,182,.6) !important; }
§ D [data-testid="stTabs"] [data-baseweb="tab-border"]{ background:rgba(134,232,220,.12) !important; }
§ D [data-testid="stTabs"] .react-aria-SelectionIndicator{ background:var(--ck-vurgu) !important; box-shadow:0 0 10px rgba(46,196,182,.6); }
§ D [data-testid="stTabs"] [data-baseweb="tab-panel"]{
  background:linear-gradient(180deg, rgba(16,52,62,.42), rgba(6,24,30,.42)) !important;
  border:1px solid var(--ck-cam-kenar) !important; border-top:none !important; border-radius:0 0 18px 18px !important; }

/* ── Düğmeler (Geri, Excel, Yeniden çiz...) ── */
§ D :is(.stButton, .stDownloadButton) > button{
  background:rgba(14,46,56,.72) !important; color:var(--ck-metin) !important;
  border:1px solid var(--ck-cam-kenar) !important; box-shadow:0 10px 24px -16px rgba(0,0,0,.8) !important; }
§ D :is(.stButton, .stDownloadButton) > button:hover{ background:rgba(46,196,182,.22) !important; border-color:rgba(134,232,220,.5) !important; }
§ D :is(.stButton, .stDownloadButton) > button p{ color:inherit !important; }
§ D :is(.stButton, .stDownloadButton) > button:disabled{ opacity:.45; }

/* ── Seçim / tarih / sayı kutuları ── */
§ D [data-baseweb="select"] > div, § D .st-key-grafik_secim [data-baseweb="select"] > div,
§ D .st-key-grafik_secim [data-testid="stSelectbox"] [role="group"],
§ D [data-baseweb="input"], § D [data-baseweb="base-input"], § D [data-testid="stDateInput"] input,
§ D [data-testid="stNumberInput"] input, § D [data-testid="stTextInput"] input{
  background:rgba(255,255,255,.05) !important; border-color:var(--ck-cam-kenar) !important;
  color:var(--ck-metin) !important; box-shadow:none !important; }
§ D :is([data-testid="stDateInput"], [data-testid="stNumberInput"], [data-testid="stTextInput"]) div{
  background-color:transparent !important; border-color:var(--ck-cam-kenar) !important; }
§ D :is([data-testid="stDateInput"], [data-testid="stNumberInput"], [data-testid="stTextInput"]) button{
  background:rgba(255,255,255,.05) !important; color:var(--ck-metin) !important; }
§ D [data-baseweb="select"] *, § D .st-key-grafik_secim [data-baseweb="select"] *,
§ D .st-key-grafik_secim [data-testid="stSelectbox"] input, § D [data-baseweb="input"] input,
§ D :is([data-testid="stDateInput"], [data-testid="stNumberInput"], [data-testid="stTextInput"]) input{
  color:var(--ck-metin) !important; -webkit-text-fill-color:var(--ck-metin) !important; }
§ D [data-baseweb="select"] svg{ fill:var(--ck-metin-2) !important; }
/* Tarih kutusu (Streamlit 1.66): görünen tarih <input> değil, gün/ay/yıl parçaları
   (span role=spinbutton) — koyu varsayılan renkte okunmuyordu (24.11.2026) */
§ D [data-testid="stDateInput"] [role="group"] span{ color:var(--ck-metin) !important; -webkit-text-fill-color:var(--ck-metin) !important; }
§ D [data-testid="stDateInput"] [role="group"] span:not([role="spinbutton"]){ opacity:.55; }
§ D [data-testid="stDateInput"] [role="spinbutton"]:focus{ background:rgba(46,196,182,.28) !important; border-radius:4px; outline:none; }
§ [data-baseweb="popover"]:has([role="listbox"]) > div, § [data-testid="stSelectboxVirtualDropdown"],
§ [data-testid="stSelectboxVirtualDropdown"] [role="listbox"]{
  background:#0b2a33 !important; border:1px solid var(--ck-cam-kenar) !important; }
§ [data-testid="stSelectboxVirtualDropdown"] [role="option"] > div, § [data-baseweb="popover"] [role="option"]{ color:var(--ck-metin) !important; }
§ [data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover > div,
§ [data-testid="stSelectboxVirtualDropdown"] [role="option"][data-focused="true"] > div,
§ [data-baseweb="popover"] [role="option"]:hover{ background:rgba(46,196,182,.14) !important; }
§ [data-testid="stSelectboxVirtualDropdown"] [role="option"][aria-selected="true"] > div{
  background:rgba(46,196,182,.22) !important; color:#ffffff !important; box-shadow:inset 3px 0 0 var(--ck-vurgu) !important; }

/* ── Diğer Streamlit öğeleri ── */
§ D [data-testid="stRadio"] label, § D [data-testid="stRadio"] p, § D [data-testid="stWidgetLabel"] p{ color:var(--ck-metin) !important; }
§ D [data-testid="stExpander"], § D [data-testid="stExpander"] details{
  background:rgba(255,255,255,.04) !important; border-color:var(--ck-cam-kenar) !important; }
§ D [data-testid="stExpander"] summary, § D [data-testid="stExpander"] summary *{ color:var(--ck-metin) !important; }
§ D [data-testid="stAlert"], § D [data-testid="stAlert"] > div{
  background:rgba(255,255,255,.05) !important; border-color:var(--ck-cam-kenar) !important; }
§ D [data-testid="stAlert"] *{ color:var(--ck-metin) !important; }
§ D [data-testid="stCaptionContainer"], § D [data-testid="stCaptionContainer"] *{ color:var(--ck-metin-3) !important; }
§ D [data-testid="stMetricValue"], § D [data-testid="stMetricValue"] *{ color:var(--ck-vurgu-acik) !important; }
§ D [data-testid="stMetricLabel"], § D [data-testid="stMetricLabel"] *{ color:var(--ck-metin-2) !important; }
§ D [data-testid="metric-container"]{ background:rgba(255,255,255,.04) !important; border-color:var(--ck-cam-kenar) !important; }
§ D hr{ border-color:rgba(134,232,220,.15) !important; }

/* ── Plotly: yazılar ve ızgara (zemin zaten saydam) ── */
§ D .js-plotly-plot :is(.xtick, .ytick, .y2tick) text,
§ D .js-plotly-plot :is(.g-xtitle, .g-ytitle, .g-y2title, .gtitle) text,
§ D .js-plotly-plot .legendtext, § D .js-plotly-plot .annotation-text{ fill:#b9cdd1 !important; }
§ D .js-plotly-plot :is(.gridlayer, .zerolinelayer) path{ stroke:rgba(255,255,255,.07) !important; }
§ D .js-plotly-plot .legend .bg{ fill:transparent !important; }
§ D .js-plotly-plot .pielayer .slicetext text{ fill:#ffffff !important; }

SATIR_ICI
"""


def _iz_svg() -> str:
    """Detay sayfasının sol arka planı: çark ekranının sadeleştirilmiş izi (logo
    dairesi, 5 kart, yay üzerindeki öğeler ve bağlantı çizgileri). CSS ile
    bulanıklaştırılıp karartılır — geçişte arkada kalan ana ekran hissi."""
    import math
    from urllib.parse import quote
    p = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900">',
         '<defs><radialGradient id="k" cx=".36" cy=".3" r=".75"><stop offset="0" stop-color="#7fb0ff"/>'
         '<stop offset=".3" stop-color="#2f64c8"/><stop offset=".65" stop-color="#133273"/>'
         '<stop offset="1" stop-color="#0a1b46"/></radialGradient>'
         '<radialGradient id="h" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#2ec4b6" stop-opacity=".25"/>'
         '<stop offset="1" stop-color="#2ec4b6" stop-opacity="0"/></radialGradient></defs>',
         '<circle cx="250" cy="450" r="250" fill="#08262e"/>',
         '<circle cx="250" cy="450" r="300" fill="url(#h)"/>']
    for r, o in ((200, .22), (165, .14), (125, .3)):
        p.append('<circle cx="250" cy="450" r="%d" fill="none" stroke="#86e8dc" stroke-opacity="%.2f" stroke-width="2"/>' % (r, o))
    p.append('<circle cx="250" cy="450" r="82" fill="url(#k)"/>')
    p.append('<path d="M226 476L250 424L274 476L267 476L250 441L233 476Z" fill="#ffffff" fill-opacity=".9"/>')
    kx, kw = 430, 190
    for i in range(5):
        y = 290 + i * 80
        p.append('<path d="M332 450 C380 450 380 %d %d %d" fill="none" stroke="#86e8dc" stroke-opacity=".3" stroke-width="2"/>'
                 % (y, kx, y))
        p.append('<rect x="%d" y="%d" width="%d" height="58" rx="12" fill="#10323c" stroke="#86e8dc" stroke-opacity="%s" stroke-width="2"/>'
                 % (kx, y - 29, kw, ".75" if i == 0 else ".25"))
        p.append('<rect x="%d" y="%d" width="70" height="14" rx="4" fill="#e8f1f2" fill-opacity=".55"/>' % (kx + 46, y - 14))
    R, cx = 420, 760
    for i in range(-7, 8):
        t = math.radians(i * 7)
        x = cx - R * (1 - math.cos(t)) + 160
        y = 450 + R * math.sin(t)
        op = max(.15, 1 - abs(i) / 8.5)
        p.append('<path d="M%d 290 C%d 290 %d %.0f %.0f %.0f" fill="none" stroke="#86e8dc" stroke-opacity="%.2f" stroke-width="1.5"/>'
                 % (kx + kw, kx + kw + 90, kx + kw + 90, y, x, y, op * .35))
        p.append('<circle cx="%.0f" cy="%.0f" r="7" fill="#86e8dc" fill-opacity="%.2f"/>' % (x, y, op))
        p.append('<rect x="%.0f" y="%.0f" width="%d" height="12" rx="3" fill="#e8f1f2" fill-opacity="%.2f"/>'
                 % (x + 16, y - 16, 120 - abs(i) * 6, op * .6))
        p.append('<rect x="%.0f" y="%.0f" width="60" height="9" rx="3" fill="#3ddc97" fill-opacity="%.2f"/>'
                 % (x + 16, y + 2, op * .45))
    p.append("</svg>")
    return "data:image/svg+xml," + quote("".join(p))


def tema_css() -> str:
    """Detay sayfasının koyu cam teması. Kök: detay tema kabı olan gövde
    (yalnız demoda basılır); özet / yönetim katmanında uygulanmaz."""
    k = (_TEMA.replace("SATIR_ICI", _satir_ici_kurallar()).replace("PALET", _cark.PALET_CSS)
         .replace("IZ_SVG", _iz_svg())
         .replace(" D ", " " + DETAY + " ").replace(" D)", " " + DETAY + ")").replace("§", KOK))
    return "<style>\n" + k + "</style>"


def _ust_kurallar(css: str) -> list:
    """CSS metnini en üst seviye kurallara böler (iç içe @media blokları tek parça kalır)."""
    d, bas, kur = 0, 0, []
    for i, ch in enumerate(css):
        if ch == "{":
            d += 1
        elif ch == "}":
            d -= 1
            if d == 0:
                kur.append(css[bas:i + 1].strip())
                bas = i + 1
    return kur


_ICERIK_DESEN = re.compile(r"^(/\*.*?\*/\s*)*(:where\(§ D\)|§ D )", re.S)
_ACILIR_DESEN = re.compile(r"^(/\*.*?\*/\s*)*§ \[data-(baseweb=\"popover\"|testid=\"stSelectboxVirtualDropdown\")", re.S)


def icerik_css(kok: str, kapsam: str, palet: bool = True) -> str:
    """Detay temasının İÇERİK kuralları (yazı, cam kart, düğme, sekme, kutu, satır içi
    açık renk eşlemesi) başka bir kapsam için: pop-up'lar (uyarılar, OTO SET, harita,
    sunucu ayarları) ve Sistem ekranı aynı görünsün. Sayfa düzeni kuralları alınmaz.
    kok: gövde seçicisi (yalnız demo ekranında eşleşmeli); kapsam: içerik kabı."""
    ham = _TEMA.replace("SATIR_ICI", _satir_ici_kurallar())
    kurallar = _ust_kurallar(ham)
    # İçerik kuralları iç içe (CSS nesting) yazılır: uzun kök + kapsam seçicisi yüzlerce
    # kez tekrarlanmaz, sayfa hafif kalır. "§ D x" → "& x", ":where(§ D)" → ":where(&)"
    ic = "\n".join(k for k in kurallar if _ICERIK_DESEN.match(k))
    ic = ic.replace(":where(§ D)", ":where(&)").replace("§ D ", "& ")
    acilir = "\n".join(k for k in kurallar if _ACILIR_DESEN.match(k)).replace("§", kok)
    k = "%s %s{\n%s\n}\n%s" % (kok, kapsam, ic, acilir)
    # Palet değişkenleri kapsamın kendisinde tanımlı olsun (gövdede tanımlı değilse)
    return ("%s %s{ %s }\n" % (kok, kapsam, _cark.PALET_CSS) if palet else "") + k


YONETIM_KOK = "body:has(.st-key-yonetim_katmani)"


def yonetim_css() -> str:
    """YALNIZ SUNUM: Sistem (yönetim) ekranı — koyu zemin, ortada cam panel, içerik
    detay sayfasıyla aynı temada. Yalnız yönetim katmanı açıkken eşleşir."""
    s = YONETIM_KOK
    zemin = (s + "{ " + _cark.PALET_CSS + " background:var(--ck-zemin-1) !important; }\n"
             "html:has(.st-key-yonetim_katmani){ background:#03141a !important; }\n"
             + s + ' :is([data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"]){\n'
             "  background:radial-gradient(ellipse 50% 45% at 15% 12%, rgba(46,196,182,.10), transparent 62%),\n"
             "    linear-gradient(160deg, var(--ck-zemin-2) 0%, var(--ck-zemin-1) 55%, #020d11 100%) !important; }\n"
             + s + ' [data-testid="stMainBlockContainer"]{ max-width:min(1280px, 92vw) !important; margin:118px auto 28px !important; /* üst başlığın altında */\n'
             "  padding:22px 28px 26px !important; border-radius:22px;\n"
             "  background:linear-gradient(180deg, rgba(14,48,58,.92), rgba(5,24,30,.94));\n"
             "  border:1px solid rgba(134,232,220,.28); box-shadow:0 40px 90px -30px rgba(0,0,0,.85); }\n")
    # ck-yonetim-tema: app_merkez genel yazı kuralı bu işaret varken yönetim içeriğini zorlamaz
    return ("<style>\n" + zemin + icerik_css(s, ".st-key-yonetim_katmani") + "</style>"
            '<span class="ck-yonetim-tema"></span>')


# ── GEÇİŞ ────────────────────────────────────────────────────────────────
# Geçiş motoru ANA BELGEDE yaşar: betik çerçevesi (iframe) sayfa değişince
# ölür, ana belgeye eklenen <script> ölmez. Motor ve stili head'e bir kez
# eklenir (id ck-gecis-stil / ck-gecis-motor-*); yalnız demo betikleri ekler.
#
# Düzen: detay sayfası ekranın SAĞINDA yüksek cam panel (--ck-dp-*); solda
# ana ekranın bulanık izi (tema_css'teki sabit arka plan). Geçişteki iskelet
# panel aynı geometriye büyür, gerçek içerik onun yerine yumuşakça oturur.
GECIS_CSS = """
:root{ --ck-dp-sol:clamp(20px, 7vw, 180px); --ck-dp-ust:50px; --ck-dp-sag:clamp(20px, 7vw, 180px); --ck-dp-alt:max(10px, 1.4vh); }
/* Panel ekranda ORTALI (18.11.2026: sol ve sağ boşluk eşit, tam ekran değil; kenarlarda bulanık ana ekran izi) */
@media (max-width:1000px){ :root{ --ck-dp-sol:12px; --ck-dp-sag:12px; } }
.ck-dp-olcu{ position:fixed; left:var(--ck-dp-sol); right:var(--ck-dp-sag); top:var(--ck-dp-ust); bottom:var(--ck-dp-alt);
  visibility:hidden; pointer-events:none; }
.ck-gecis-kaplama{ position:fixed; inset:0; z-index:999995; pointer-events:none;
  animation:ckKaplamaEmniyet .4s ease 16s forwards; }
@keyframes ckKaplamaEmniyet{ to{ opacity:0; visibility:hidden; } }
/* Perde yalnız karartır; bulanıklık ana sahnenin kendi filtresinde (backdrop-filter
   tam ekranda her karede yeniden hesaplanır, yavaş makinede takılır) */
/* HIZ (24.11.2026): geçişte yalnız transform ve opacity canlandırılır — bunları ekran
   kartı (compositor) oynatır; detay çizilirken ana iş parçacığı ~0,5 sn meşgulken de
   akıcı kalır. Önceki left/top/width/height + blur() canlandırması o sırada donuyordu. */
.ck-gecis-perde{ position:absolute; inset:0; background:rgba(2,14,18,.38); opacity:0; transition:opacity .6s ease; }
.ck-gecis-kaplama.ck-acik .ck-gecis-perde{ opacity:1; }
.ck-gecis-panel{ position:absolute; box-sizing:border-box; overflow:hidden; border-radius:22px; padding:22px 26px;
  font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;
  background:linear-gradient(180deg, rgba(22,62,72,.97), rgba(7,28,35,.98));
  border:1px solid rgba(150,225,225,.30);
  box-shadow:0 40px 90px -30px rgba(0,0,0,.85), 0 0 0 6px rgba(46,196,182,.05), inset 0 1px 0 rgba(255,255,255,.07);
  transform-origin:0 0; will-change:transform, opacity;
  transition:transform .44s cubic-bezier(.2,.75,.15,1), opacity .3s ease; }
.ck-gecis-kaplama .ck-gecis-panel *{ color:#e8f1f2 !important; box-sizing:border-box; }
.ck-gecis-kaplama .ck-gecis-panel .ck-gp-ust{ font-size:9px; letter-spacing:4px; text-transform:uppercase; color:#86e8dc !important; opacity:.8; white-space:nowrap; }
.ck-gp-ad{ margin-top:6px; font-size:22px; font-weight:800; letter-spacing:2.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ck-gp-sekme, .ck-gp-izgara, .ck-gp-satir{ display:flex; gap:10px; margin-top:18px; }
.ck-gp-sekme i{ width:96px; height:12px; }
.ck-gp-izgara{ display:grid; grid-template-columns:minmax(0,1.2fr) minmax(0,3fr); gap:12px; }
.ck-gp-izgara i{ height:58px; }
.ck-gp-izgara i:nth-child(2){ grid-row:span 3; height:auto; }
.ck-gp-satir i{ flex:1; height:70px; }
.ck-gecis-panel i{ display:block; position:relative; overflow:hidden; border-radius:10px; border:1px solid rgba(255,255,255,.06);
  background:rgba(255,255,255,.035); }
.ck-gecis-panel i::after{ content:""; position:absolute; inset:0;
  background:linear-gradient(90deg, transparent 0%, rgba(134,232,220,.13) 50%, transparent 100%);
  transform:translateX(-100%); animation:ckIskelet 1.3s linear infinite; }
@keyframes ckIskelet{ to{ transform:translateX(100%); } }
.ck-gecis-kaplama.ck-gecis-cikis{ opacity:0; transition:opacity .42s ease; }
.ck-gecis-kaplama.ck-geri .ck-gecis-panel{ transition:transform .55s cubic-bezier(.4,.05,.25,1), opacity .4s ease; }

/* Sayfa değişimi görünmesin: zemin koyu; ana sahneyi içeren üst düzey öğe dışında hepsi gizli */
body:is(.ck-gecis-surer, .ck-geri-surer, .ck-sahne-giris), body:is(.ck-gecis-surer, .ck-geri-surer, .ck-sahne-giris) :is(.stApp, [data-testid="stApp"], [data-testid="stAppViewContainer"]){
  background-color:#03141a !important; }
/* opacity (visibility değil: Streamlit iç kapları visibility:visible verip gizlemeyi deliyor) */
body:is(.ck-gecis-surer, .ck-geri-surer, .ck-sahne-giris) [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > *:not(:has(.ck-sahne)){
  opacity:0 !important; pointer-events:none !important; transition:none !important; }
/* İleri: ana sahne kararır (perde + opacity) ve hafif küçülüp uzaklaşır (blur yok: her karede tam ekran bulanıklık yavaş PC'de takılıyordu) */
body.ck-gecis-surer .ck-sahne{ transform:scale(.955) translateX(-1.5%); opacity:.55;
  will-change:transform, opacity; transition:transform .62s cubic-bezier(.2,.75,.15,1), opacity .62s ease; }
/* Detay açıldı ama yeniden çizim bitmedi: eski ana sahne (bayat öğe) detayın üstünde görünmesin */
body:not(.ck-geri-surer):not(.ck-sahne-giris):has(.st-key-detay_tema_demo) .ck-sahne{ visibility:hidden !important; }
/* Detay içeriği iskeletin yerine oturur */
body.ck-detay-giris [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"]{ animation:ckIcerikGir .42s ease both; }
@keyframes ckIcerikGir{ from{ opacity:0; transform:translateY(6px); } to{ opacity:1; transform:none; } }
/* Geri: ana sahne gelene dek gizli; gelince netleşerek girer */
body.ck-geri-surer .ck-sahne{ opacity:0; animation:ckEmniyet .45s ease 6s forwards; }
body.ck-sahne-giris .ck-sahne{ animation:ckSahneGir .66s cubic-bezier(.2,.75,.15,1) both; }
@keyframes ckSahneGir{ from{ opacity:0; transform:scale(1.035); } to{ opacity:1; transform:none; } }
@keyframes ckEmniyet{ to{ opacity:1; } }
@media (prefers-reduced-motion: reduce){
  .ck-gecis-perde{ transition:opacity .25s ease; }
  body.ck-gecis-surer .ck-sahne{ opacity:.5; transition:opacity .25s ease; }
  .ck-gecis-panel, .ck-gecis-kaplama.ck-geri .ck-gecis-panel{ transition:opacity .25s ease; }
  .ck-gecis-panel i::after{ animation:none; opacity:0; }
  body.ck-gecis-surer .ck-sahne{ transform:none; }
  @keyframes ckIcerikGir{ from{ opacity:0; } to{ opacity:1; } }
  @keyframes ckSahneGir{ from{ opacity:0; } to{ opacity:1; } }
}
"""

# Ana belgede çalışan geçiş motoru (window = ana sayfa)
GECIS_JS = r"""
(function () {
  var W = window, d = document, SURUM = '__V__';
  var E = W.__ckGecis;
  if (E && E.surum === SURUM) { return; }
  if (E) { try { E.mo.disconnect(); W.clearInterval(E.aralik); W.clearInterval(E.cubuk); d.removeEventListener('click', E.tik, true); } catch (e) {} }
  var AZ = !!(W.matchMedia && W.matchMedia('(prefers-reduced-motion: reduce)').matches);
  // Pencere yüksekliği çereze yazılır: detay grafikleri sunucuda ekrana oranlı çizilir (lokasyon_detay._dz_gh)
  function cerez() { try { d.cookie = 'ck_vh=' + W.innerHeight + '; path=/; max-age=31536000; SameSite=Lax'; } catch (e) {} }
  cerez(); W.addEventListener('resize', cerez);
  var G = W.__ckGecis = {surum: SURUM, yon: null, t0: 0, olcum: (E && E.olcum) || []};
  function kac(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); }
  // Bir sonraki kare: requestAnimationFrame; sekme arka plandaysa (rAF durur) zamanlayıcı yedeği
  function sonra(fn) { var ok = false; function c() { if (!ok) { ok = true; fn(); } } W.requestAnimationFrame(c); W.setTimeout(c, 50); }
  function kutu(p, r) { p.style.left = r.left + 'px'; p.style.top = r.top + 'px'; p.style.width = r.width + 'px'; p.style.height = r.height + 'px'; }
  // Panel yerinde (r) durur; başka bir kutunun (h) yerinde görünmesi yalnız transform ile
  // (ekran kartı oynatır, ana iş parçacığı meşgulken donmaz — 24.11.2026)
  function donus(r, h) {
    return 'translate(' + (h.left - r.left) + 'px,' + (h.top - r.top) + 'px) scale('
      + Math.max(h.width / Math.max(r.width, 1), .01) + ',' + Math.max(h.height / Math.max(r.height, 1), .01) + ')';
  }
  function hedefDetay() {
    var p = d.createElement('div'); p.className = 'ck-dp-olcu'; d.body.appendChild(p);
    var r = p.getBoundingClientRect(); d.body.removeChild(p);
    return {left: r.left, top: r.top, width: r.width, height: r.height};
  }
  function hedefAna() {   // çark ekranındaki sağ panelin yeri (ana_ekran_cark_demo ölçüleri)
    var vw = W.innerWidth, vh = W.innerHeight;
    if (vw <= 900) { return {left: 16, top: vh * 0.3, width: vw - 32, height: vh * 0.45}; }
    var U = Math.min(11, Math.max(5, Math.min(vh * 0.009, vw * 0.005)));
    var w = (vw - 5.2 * U - 3 * 1.6 * U) * 25 / 91;
    return {left: vw - 2.6 * U - w, top: 5.4 * U, width: w, height: vh - 5.4 * U - 8.4 * U};
  }
  function kaplama(isim) {
    var eski = d.querySelector('.ck-gecis-kaplama'); if (eski && eski.parentNode) { eski.parentNode.removeChild(eski); }
    var k = d.createElement('div'); k.className = 'ck-gecis-kaplama';
    k.innerHTML = '<div class="ck-gecis-perde"></div><div class="ck-gecis-panel" role="status" aria-label="Yükleniyor">'
      + '<div class="ck-gp-ust">Acıbadem Sağlık Grubu — Lokasyon Detay</div><div class="ck-gp-ad">' + kac(isim) + '</div>'
      + '<div class="ck-gp-sekme"><i></i><i></i></div>'
      + '<div class="ck-gp-izgara"><i></i><i></i><i></i><i></i></div><div class="ck-gp-satir"><i></i><i></i><i></i></div></div>';
    d.body.appendChild(k);
    return {k: k, p: k.querySelector('.ck-gecis-panel')};
  }
  // İLERİ: tıklama anında (yeniden çizim beklenmeden) başlar
  G.ileri = function (isim, kaynak) {
    // Ölçüm panel eklenmeden ÖNCE: sonradan ölçmek paneli başlangıç dönüşümü olmadan
    // biçimlendirir ve büyüme animasyonu hiç oynamaz
    var hedef = hedefDetay();
    var o = kaplama(isim);
    G.yon = 'ileri'; G.t0 = Date.now(); G.p0 = W.performance.now();
    d.body.classList.remove('ck-geri-surer', 'ck-sahne-giris', 'ck-detay-giris', 'ck-kontrol-acik', 'ck-harita-acik');
    d.body.classList.add('ck-gecis-surer');
    kutu(o.p, hedef);
    if (AZ || !kaynak) { o.p.style.opacity = '0'; }
    else { o.p.style.transform = donus(hedef, {left: kaynak.left - 8, top: kaynak.top - 6,
                                               width: Math.max(kaynak.width + 16, 200), height: Math.max(kaynak.height + 12, 70)}); }
    void o.p.offsetWidth;
    sonra(function () {
      o.k.classList.add('ck-acik');
      o.p.style.opacity = '1'; o.p.style.transform = 'none';
    });
  };
  // GERİ: detay paneli iskelete döner, çark ekranındaki panelin yerine küçülür
  G.geri = function () {
    var bc = d.querySelector('[data-testid="stMainBlockContainer"]'), r = hedefDetay();
    if (bc) { var b = bc.getBoundingClientRect(); r = {left: b.left, top: Math.max(b.top, 0), width: b.width, height: Math.min(b.bottom, W.innerHeight) - Math.max(b.top, 0)}; }
    var ad = d.querySelector('.dz-baslik');
    var o = kaplama(ad ? ad.textContent.trim() : '');
    o.k.classList.add('ck-geri', 'ck-acik'); kutu(o.p, r);
    G.yon = 'geri'; G.t0 = Date.now(); G.p0 = W.performance.now();
    d.body.classList.remove('ck-gecis-surer', 'ck-detay-giris', 'ck-sahne-giris');
    d.body.classList.add('ck-geri-surer');
    void o.p.offsetWidth;
    sonra(function () { o.p.style.transform = donus(r, hedefAna()); });
  };
  function hazir() {
    if (G.yon === 'ileri') {
      // Hız (18.11.2026): çizimin bitmesi (eski sahnenin DOM'dan kalkması) beklenmez —
      // başlık ve ilk kartlar gelince açılır; kalan eski sahne CSS ile gizli (GECIS_CSS)
      return !!(d.querySelector('.st-key-detay_tema_demo') && d.querySelector('.st-key-detay_gecis_katmani .st-key-detay_geri')
                && d.querySelector('.st-key-detay_gecis_katmani .dz-kart'));
    }
    if (G.yon === 'geri') {
      var S = W.__synCark;
      // Sahne gelir gelmez motoru bağla: 400 ms'lik denetim aralığı beklenmez (24.11.2026)
      var sh = d.querySelector('.ck-sahne');
      if (S && S.kontrol && sh && S.el !== sh) { try { S.kontrol(); } catch (e) {} }
      return !!(!d.querySelector('.st-key-detay_tema_demo') && S && S.el && S.el.isConnected && S.liste && S.liste.length);
    }
    return false;
  }
  function bitir() {
    var yon = G.yon; if (!yon) { return; }
    G.yon = null;
    G.olcum.push({yon: yon, ms: Math.round(W.performance.now() - G.p0)});
    if (G.olcum.length > 20) { G.olcum.shift(); }
    var k = d.querySelector('.ck-gecis-kaplama');
    if (yon === 'ileri') {
      d.body.classList.remove('ck-gecis-surer'); d.body.classList.add('ck-detay-giris');
      W.setTimeout(function () { d.body.classList.remove('ck-detay-giris'); }, 700);
    } else {
      d.body.classList.remove('ck-geri-surer'); d.body.classList.add('ck-sahne-giris');
      W.setTimeout(function () { d.body.classList.remove('ck-sahne-giris'); }, 800);
    }
    if (k) { k.classList.add('ck-gecis-cikis'); W.setTimeout(function () { if (k.parentNode) { k.parentNode.removeChild(k); } }, 520); }
  }
  var bekZ = 0;
  function denetle() {
    if (!G.yon) { return; }
    if (Date.now() - G.t0 > 15000) { bitir(); return; }
    if (!hazir() || bekZ) { return; }
    // En az animasyon süresi (hız, 18.11.2026: 640 → 440 ms; panel büyümesi .44 s)
    var kalan = (AZ ? 120 : (G.yon === 'ileri' ? 440 : 560)) - (Date.now() - G.t0);
    bekZ = W.setTimeout(function () {
      bekZ = 0;
      // Geri: sahne hazırsa hemen açılır. Çark sahnesi gelince ana sayfanın geri kalanı
      // (harita, çerçeveler) çizilirken kareler uzun sürüyor; iki kare beklemek ~0,9 sn
      // ekliyordu (26.11.2026). Giriş animasyonu yalnız opacity/transform: ekran kartı oynatır.
      if (hazir()) { if (G.yon === 'geri') { bitir(); } else { sonra(function () { sonra(bitir); }); } }
    }, Math.max(0, kalan));
  }
  G.denetle = denetle;
  G.mo = new W.MutationObserver(function () { if (G.yon) { denetle(); } });
  G.mo.observe(d.body, {childList: true, subtree: true});
  G.aralik = W.setInterval(denetle, 200);
  // Geri: demo geri düğmesine (on_click; detay yeniden çizilmeden ana ekran) yönlendirilir
  G.tik = function (ev) {
    var t = ev.target;
    if (!t || !t.closest || !t.closest('.st-key-detay_geri button')) { return; }
    var h = d.querySelector('.st-key-ck_detay_geri button');
    if (!h || !d.querySelector('.st-key-detay_tema_demo')) { return; }
    ev.preventDefault(); ev.stopPropagation();
    G.geri(); h.click();
  };
  d.addEventListener('click', G.tik, true);
  // Sütun animasyonu: grafik seçimi değişince Streamlit aynı Plotly kutusunu yerinde
  // günceller (yol öğeleri korunur), CSS büyüme animasyonu yeniden oynamaz. Sütun
  // şekilleri değişince (genişlik aynıyken) animasyon baştan başlatılır (19.11.2026).
  G.cubuk = W.setInterval(function () {
    if (AZ || !d.querySelector('.st-key-detay_tema_demo')) { return; }
    d.querySelectorAll('.js-plotly-plot').forEach(function (gd) {
      var ps = gd.querySelectorAll('.barlayer .point path'); if (!ps.length) { gd.__ckImza = null; return; }
      var imza = '', gen = gd.clientWidth + 'x' + gd.clientHeight;
      for (var i = 0; i < ps.length; i++) { imza += (ps[i].getAttribute('d') || '') + '|'; }
      var once = gd.__ckImza, onceGen = gd.__ckGen;
      gd.__ckImza = imza; gd.__ckGen = gen;
      if (once == null || once === imza || onceGen !== gen) { return; }
      ps.forEach(function (p) {
        try { p.getAnimations().forEach(function (a) { a.cancel(); a.play(); }); } catch (e) {}
      });
    });
  }, 250);
})();
"""


def motor_kur_js() -> str:
    """Çerçeve betiğinin (değişkenler W = ana pencere, d = ana belge) çağırdığı
    parça: geçiş stilini ve motoru ana belgenin head'ine bir kez ekler."""
    import json
    js = GECIS_JS.replace("__V__", str(SURUM))
    return ("(function(){var s=d.getElementById('ck-gecis-stil');if(!s){s=d.createElement('style');"
            "s.id='ck-gecis-stil';d.head.appendChild(s);}var c=%s;if(s.textContent!==c){s.textContent=c;}"
            "if(!W.__ckGecis||W.__ckGecis.surum!=='%s'){var m=d.createElement('script');m.id='ck-gecis-motor-'+Date.now();"
            "m.textContent=%s;d.head.appendChild(m);}})();"
            % (json.dumps(GECIS_CSS).replace("</", "<\\/"), SURUM, json.dumps(js).replace("</", "<\\/")))


# Eski adla çağrılan yerler için (ana_ekran_cark_demo._gecis_stil)
stil_ekle_js = motor_kur_js


def detay_ac(lok: str):
    """Demo çark düğmesinin on_click'i: durum betik çalışmadan ÖNCE yazılır, yeniden
    çizim doğrudan detay dalına girer (ana ekran bir kez daha çizilmez)."""
    import streamlit as st
    st.session_state["detay_lokasyon"] = lok


def geri_ac():
    """Demo geri düğmesinin on_click'i: detay sayfasındaki Geri'nin yaptığını yapar
    (detay_lokasyon silinir); ana ekran doğrudan çizilir."""
    import streamlit as st
    st.session_state.pop("detay_lokasyon", None)


def betik() -> str:
    """Detay sayfasının 0 px betiği: motoru kurar (doğrudan bağlantıyla gelindiyse)
    ve bekleyen geçişi denetletir."""
    return ("<script>(function(){var W=window.parent,d;try{d=W.document;}catch(e){return;}"
            + motor_kur_js() + "if(W.__ckGecis){W.__ckGecis.denetle();}})();</script>")
