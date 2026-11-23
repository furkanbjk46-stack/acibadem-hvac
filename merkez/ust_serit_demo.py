# -*- coding: utf-8 -*-
"""
ÜST ŞERİT — YALNIZ SUNUM (DEMO) MODU
====================================

Ana ekranda "ACIBADEM SAĞLIK GRUBU" başlığının hemen altında, tek sırada altı
büyük kart: Global Özet'in beş kalemi (Toplam Enerji, Doğalgaz, Soğutma, Su,
Kojen Üretim) + Canlı Uyarılar. app_merkez.py bunu yalnız `_demo_modu()`
açıkken çağırır; canlı portalın ekranı bu modülden etkilenmez.

KORUNAN İŞLEVLER
  * Özet kartları yine `<a class="ozet-kart" data-ozet=... href="?ozet=...">`:
    tıklama gizli `gizli_ozet_<anahtar>` düğmesine yönlendirilir (betik aşağıda,
    sol sütundaki köprüyle aynı; `data-baglandi` ile iki kez bağlanmaz).
  * Sayılar `.canli-sayi[data-faz="ozet-<anahtar>"]`: saniyelik akış
    (canli_izleme.akis_betigi) ve 15 sn tazeleme (tazele_betigi) bunları bulur.
  * Canlı sayacı olmayan kalemde sayı UYDURULMAZ: "canlı sayaç yok", soluk kart,
    animasyon yok.
  * Uyarı kartı, sağ sütundaki listeyi (aynı HTML) açılır pencerede gösterir.

ANİMASYON (sakin, kurumsal; prefers-reduced-motion'da hepsi kapanır)
  * Giriş: kartlar sırayla hafifçe yükselerek belirir.
  * Canlı nokta: atan yeşil nokta (ikonlar.nokta).
  * Simge: ikonlar.ikon'un kendi küçük hareketi + arkasında nefes alan hale.
  * Sayı değişince: kısa, yumuşak bir "tık" (2 px kayma + renk tonu) ve eğilim oku.
  * İz: kartın altında, ekranda GÖSTERİLEN son değerlerden çizilen ince çizgi
    (yeni veri üretmez; yalnız akan sayının geçmişini çizer).
"""

import html as _html
import re

SURUM = 14   # 11: tek ekran (kaydırmasız), ekrana oranlı kompakt düzen — ekran_css. app_merkez bu sayıyla yeniden yükler.

KART_RENK_VARSAYILAN = "#2a78d6"


def serit_css() -> str:
    """Şeridin stil bloğu. Seçiciler `.us-serit` altında: genel span/div rengini
    zorlayan kuralın (app_merkez, !important) önüne geçmek için iki sınıf derinliği."""
    return """
<style>
.st-key-ust_serit_demo{ position:relative; margin:0 0 4px; gap:0 !important; }
/* Yalnız uyarı listesi açıkken alttaki haritanın / sütunların ÜSTÜNE çıkar */
.st-key-ust_serit_demo:has(.us-liste[open]){ z-index:20; }
/* 0 px betik çerçevesi tıklama yakalamasın (altındaki arama kutusunu örtüyordu) */
.st-key-ust_serit_demo [data-testid="stElementContainer"]:has(> iframe){
  position:absolute !important; height:0 !important; overflow:hidden !important; pointer-events:none !important; }
.us-serit{ display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); gap:12px; width:100%; }
@media (max-width:1180px){ .us-serit{ grid-template-columns:repeat(3, minmax(0, 1fr)); } }
@media (max-width:640px){ .us-serit{ grid-template-columns:repeat(2, minmax(0, 1fr)); gap:9px; } }
@media (max-width:380px){ .us-serit{ grid-template-columns:1fr; } }

@keyframes usGiris{ from{opacity:0; transform:translateY(10px);} to{opacity:1; transform:none;} }
@keyframes usHale{ 0%,100%{transform:scale(.86); opacity:.55;} 50%{transform:scale(1.08); opacity:1;} }
@keyframes usTikYukari{ 0%{transform:translateY(2px); opacity:.82;} 100%{transform:none; opacity:1;} }
@keyframes usTikAsagi{ 0%{transform:translateY(-2px); opacity:.82;} 100%{transform:none; opacity:1;} }
@keyframes usIsik{ 0%{transform:translateX(-120%);} 100%{transform:translateX(220%);} }
@keyframes usUyariNabiz{ 0%,100%{box-shadow:0 10px 24px -18px var(--k), 0 0 0 0 rgba(208,59,59,0);}
                         50%{box-shadow:0 10px 24px -18px var(--k), 0 0 0 4px rgba(208,59,59,.10);} }

.us-serit .us-kart{
  --k:#2a78d6; position:relative; display:flex !important; flex-direction:column; min-width:0;
  box-sizing:border-box; min-height:148px; padding:14px 16px 12px; border-radius:14px;
  background:#ffffff; border:1.5px solid var(--k); text-decoration:none !important;
  box-shadow:0 10px 24px -18px var(--k); overflow:hidden;
  animation:usGiris .5s cubic-bezier(.2,.7,.2,1) both; animation-delay:calc(var(--sira, 0) * 70ms);
  transition:transform .18s ease, box-shadow .18s ease;
}
/* Üstte kart renginde ince bant; üzerinden yavaş bir ışık geçer (yalnız canlı kartta) */
.us-serit .us-kart::before{ content:""; position:absolute; left:0; right:0; top:0; height:3px; background:var(--k);
  border-radius:12px 12px 0 0; }
.us-serit .us-uyari::after{ display:none; }
.us-serit .us-kart.us-canli::after{ content:""; position:absolute; top:0; left:0; width:40%; height:3px;
  background:linear-gradient(90deg, transparent, rgba(255,255,255,.85), transparent);
  animation:usIsik 4.5s ease-in-out infinite; animation-delay:calc(var(--sira, 0) * 600ms); }
.us-serit a.us-kart{ cursor:pointer; }
.us-serit a.us-kart:hover{ transform:translateY(-2px); box-shadow:0 14px 28px -18px var(--k); }
.us-serit a.us-kart:focus-visible{ outline:2px solid #133273; outline-offset:2px; }

.us-serit .us-ust{ display:flex; align-items:center; gap:9px; min-width:0; }
.us-serit .us-simge{ position:relative; flex-shrink:0; width:34px; height:34px; display:flex;
  align-items:center; justify-content:center; }
.us-serit .us-simge::before{ content:""; position:absolute; inset:0; border-radius:50%;
  background:radial-gradient(circle, color-mix(in srgb, var(--k) 20%, transparent) 0%, transparent 70%); }
.us-serit .us-canli .us-simge::before{ animation:usHale 3.2s ease-in-out infinite; }
.us-serit .us-simge > *{ position:relative; }
.us-serit .us-etiket{ flex:1; min-width:0; font-size:11px !important; font-weight:800 !important;
  letter-spacing:1.3px; text-transform:uppercase; color:#46536b !important;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.us-serit .us-ok{ font-size:13px !important; color:#133273 !important; opacity:.5; flex-shrink:0; }
.us-serit a.us-kart:hover .us-ok{ opacity:1; }

.us-serit .us-deger{ display:flex; align-items:baseline; gap:6px; margin-top:12px; min-width:0; }
.us-serit .us-sayi{ display:inline-block; font-size:31px !important; font-weight:800 !important;
  line-height:1.05; letter-spacing:-.5px; color:#0f1f3d !important; font-variant-numeric:tabular-nums;
  white-space:nowrap; }
.us-serit .us-sayi .canli-sayi{ color:inherit !important; font:inherit !important; }
.us-serit .us-sayi.us-tik-yukari{ animation:usTikYukari .35s ease-out; }
.us-serit .us-sayi.us-tik-asagi{ animation:usTikAsagi .35s ease-out; }
.us-serit .us-birim{ font-size:12px !important; font-weight:700 !important; color:#46536b !important; white-space:nowrap; }
.us-serit .us-egilim{ font-size:11px !important; font-weight:800 !important; margin-left:auto;
  color:#9aa3b2 !important; transition:color .4s ease, opacity .4s ease; opacity:0; }
.us-serit .us-egilim.us-e-yukari{ color:#c25b12 !important; opacity:1; }
.us-serit .us-egilim.us-e-asagi{ color:#2a78d6 !important; opacity:1; }

.us-serit .us-alt{ display:flex; align-items:center; gap:6px; margin-top:6px; font-size:10.5px !important;
  color:#46536b !important; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }
.us-serit .us-alt > span:last-child{ overflow:hidden; text-overflow:ellipsis; color:#46536b !important; }
.us-serit .us-iz{ display:block; width:100%; height:26px; margin-top:auto; padding-top:6px; }
.us-serit .us-iz svg{ display:block; width:100%; height:20px; overflow:visible; }

/* Canlı sayacı yok: soluk, hareketsiz */
.us-serit .us-kart.us-pasif{ background:#f6f7f9; border-style:dashed; box-shadow:none;
  border-color:color-mix(in srgb, var(--k) 45%, #c9ced8); }
.us-serit .us-kart.us-pasif .us-simge{ filter:grayscale(.6); opacity:.65; }
.us-serit .us-kart.us-pasif .us-simge .ai, .us-serit .us-kart.us-pasif .us-simge .ai *{ animation:none !important; }
.us-serit .us-yok{ font-size:14px !important; font-weight:700 !important; color:#9aa3b2 !important; }

/* Uyarı kartı */
.us-serit .us-uyari{ cursor:default; overflow:visible; }
.us-serit .us-uyari.us-uyari-var{ background:linear-gradient(180deg, color-mix(in srgb, var(--k) 7%, #fff) 0%, #fff 60%); }
.us-serit .us-uyari.us-kritik{ animation:usGiris .5s cubic-bezier(.2,.7,.2,1) both, usUyariNabiz 2.8s ease-in-out 1s infinite;
  animation-delay:calc(var(--sira, 0) * 70ms), 1s; }
.us-serit .us-uyari .us-sayi{ color:var(--k) !important; }
.us-serit .us-uyari.us-uyari-yok .us-sayi{ font-size:22px !important; }
.us-serit .us-ozet-satir{ margin-top:6px; font-size:10.5px !important; font-weight:600 !important;
  color:#24324d !important; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.us-serit .us-liste{ margin-top:auto; padding-top:6px; position:relative; }
.us-serit .us-liste > summary{ list-style:none; cursor:pointer; display:inline-flex; align-items:center; gap:5px;
  font-size:10.5px !important; font-weight:700 !important; color:#133273 !important; user-select:none; }
.us-serit .us-liste > summary::-webkit-details-marker{ display:none; }
.us-serit .us-liste > summary::after{ content:"▾"; transition:transform .2s ease; }
.us-serit .us-liste[open] > summary::after{ transform:rotate(180deg); }
.us-serit .us-liste .us-kapa, .us-serit .us-liste[open] .us-ac{ display:none; }
.us-serit .us-liste[open] .us-kapa{ display:inline; }
.us-serit .us-acilir{ position:absolute; right:-17px; top:calc(100% + 8px); z-index:30;
  width:min(360px, calc(100vw - 32px)); box-sizing:border-box; padding:10px; border-radius:12px;
  background:#ffffff; border:1px solid rgba(19,50,115,.16); box-shadow:0 22px 48px -20px rgba(15,31,61,.45);
  animation:usGiris .2s ease-out both; }

.us-not{ font-size:9px !important; color:#6b7280 !important; margin:6px 2px 0; text-align:right; }

@media (max-width:1180px){ .us-serit .us-sayi{ font-size:28px !important; } }
@media (max-width:640px){ .us-serit .us-kart{ min-height:128px; padding:12px; }
  .us-serit .us-sayi{ font-size:24px !important; } .us-serit .us-acilir{ right:auto; left:-13px; } }

@media (prefers-reduced-motion: reduce){
  .us-serit .us-kart, .us-serit .us-kart::after, .us-serit .us-simge::before,
  .us-serit .us-sayi, .us-serit .us-acilir, .us-serit .us-uyari.us-kritik,
  .us-serit .us-simge .ai, .us-serit .us-simge .ai *, .us-serit .ai-nokta{ animation:none !important; }
  .us-serit .us-kart{ transition:none; }
}
</style>
"""


# ── TEK EKRAN DÜZENİ (yalnız sunum ana ekranı, geniş ve yeterince yüksek ekran) ──
# Ekran %100 iken sayfa kaydırması olmasın: ana kap görünür yüksekliğe (100dvh)
# kilitlenir; başlık + kart şeridi içeriği kadar (yükseklikleri vh'ye bağlı
# clamp ile ölçeklenir), alttaki üç sütun KALAN yüksekliği alır. Uzun içerik
# (lokasyon listesi, sağ sütundaki OTO SET / dış hava / analiz) kendi kutusunda
# kayar. Tablet / dar ekran (≤1180 px) ve çok kısa ekran (<560 px) eski akışta
# kalır. Lokasyon detayı, özet detayı ve yönetim ekranında hiçbir kural
# uygulanmaz (o ekranlar şeridi zaten çizmez; geçiş anında kalan eski öğeler
# için katman anahtarlarıyla da dışlanır).
EKRAN_MEDYA = "(min-width:1181px) and (min-height:560px)"
_EKRAN_KOK = ('body:has(.st-key-ust_serit_demo):not(:has(.st-key-detay_gecis_katmani))'
              ':not(:has(.st-key-ozet_gecis_katmani)):not(:has(.st-key-yonetim_katmani))')
_ANA = '[data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret)'

_EKRAN_KURALLAR = """
/* ── KÖK ÖLÇEK ── Tüm boyutlar tek birimden (--se-u) türetilir; birim görünür
   yükseklik ve genişliğin küçüğüne oranlıdır (1920×940'ta ≈8 px, 1366×650'de
   ≈5,5 px). İnce ayar tek yerden: --se-olcek (1 = varsayılan; 0.9 daha küçük). */
§{ --se-olcek:1;
   --se-u:calc(clamp(5.5px, min(.85vh, .48vw), 10px) * var(--se-olcek));
   --se-kart-h:calc(clamp(84px, 11vh, 120px) * var(--se-olcek));
   --se-sayi:calc(clamp(19px, min(2.7vh, 1.5vw), 30px) * var(--se-olcek));
   --se-simge:calc(var(--se-u) * 2.6); --se-ic:calc(var(--se-u) * 1.1); --se-ara:calc(var(--se-u) * 1.2);
   --se-yazi:max(9px, calc(var(--se-u) * 1.3)); --se-kucuk:max(8.5px, calc(var(--se-u) * 1.15)); }
/* Ana kap görünür yüksekliğe kilitli; kalan alanı üç sütunlu düzen alır */
§ [data-testid="stMainBlockContainer"]{ height:100vh; height:100dvh; box-sizing:border-box;
  display:flex !important; flex-direction:column; padding-top:calc(var(--se-u) * .8) !important;
  padding-bottom:4px !important; overflow:hidden; }
§ [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"]{ flex:1 1 auto; min-height:0; }
/* Alt bilgi satırı (ACIBADEM ENERJİ YÖNETİM SİSTEMİ · tarih) sıkışık */
§ [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] [data-testid="stMarkdownContainer"] > div[style*="border-top"]{
  margin-top:4px !important; padding:3px 0 0 !important; line-height:1.3; font-size:9px; }
§ [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(div[style*="border-top"]) [data-testid="stMarkdownContainer"]{
  margin-bottom:0 !important; }
§ [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:has(> [data-testid="stHorizontalBlock"] .ana-duzen-isaret){
  flex:1 1 0; min-height:0; margin-top:var(--se-ara); }
§ ANA{ height:100%; min-height:0; align-items:stretch !important; gap:var(--se-ara) !important; }
§ ANA > [data-testid="stColumn"]{ height:100%; min-height:0; display:flex; flex-direction:column; }
§ ANA > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]{ flex:1 1 0; min-height:0; gap:0 !important; }
/* Görünmez öğeler (stil, 0 px betik) dikey yer almasın */
§ ANA [data-testid="stElementContainer"]:has(> iframe[srcdoc]){ position:absolute !important; height:0 !important; }
/* Bölüm başlıkları (LOKASYON DURUMU, HASTANE ENERJİ AĞI) küçük */
§ ANA .sec{ font-size:var(--se-yazi) !important; margin-bottom:calc(var(--se-u) * .6) !important;
  padding-bottom:calc(var(--se-u) * .5) !important; gap:calc(var(--se-u) * .7) !important; }
§ ANA .sec .ai{ width:calc(var(--se-u) * 1.9) !important; height:calc(var(--se-u) * 1.9) !important; }
§ ANA .st-key-lok_arama input{ height:calc(var(--se-u) * 3.4); min-height:24px; font-size:var(--se-yazi); }

/* SOL: lokasyon listesi kalan yüksekliği alır, kendi içinde kayar; kartlar kompakt */
§ ANA > [data-testid="stColumn"]:nth-child(1) [data-testid="stElementContainer"]:has(.lok-scroll){
  flex:1 1 0; min-height:0; margin-top:calc(var(--se-u) * .6); position:relative; }
§ ANA .lok-scroll{ position:absolute !important; inset:0; height:auto !important; max-height:none !important;
  box-sizing:border-box; align-content:start; gap:calc(var(--se-u) * .9) !important;
  grid-template-columns:repeat(auto-fill, minmax(max(132px, calc(var(--se-u) * 19)), 1fr)) !important; }
§ ANA .lok-scroll a.lok-kart{ padding:calc(var(--se-u) * .9) calc(var(--se-u) * 1.1) !important;
  border-radius:calc(var(--se-u) * 1.3) !important; }
§ ANA .lok-scroll a.lok-kart > div{ gap:calc(var(--se-u) * 1.1) !important; }
§ ANA .lok-scroll a.lok-kart > div > div:first-child{ width:calc(var(--se-u) * 4.2) !important;
  height:calc(var(--se-u) * 4.2) !important; }
§ ANA .lok-scroll a.lok-kart > div > div:first-child > div:nth-child(2){ font-size:calc(var(--se-u) * 2.7) !important; }
§ ANA .lok-scroll a.lok-kart .lok-nokta{ width:calc(var(--se-u) * 1.1) !important; height:calc(var(--se-u) * 1.1) !important;
  top:0 !important; right:0 !important; }
§ ANA .lok-scroll a.lok-kart .lok-sira{ top:3px !important; left:5px !important; font-size:7px !important; }
§ ANA .lok-scroll a.lok-kart > div > div:nth-child(2){ line-height:1.25; }
§ ANA .lok-scroll a.lok-kart > div > div:nth-child(2) > div:first-child{ font-size:var(--se-yazi) !important; }
§ ANA .lok-scroll a.lok-kart .lok-durum{ font-size:max(7.5px, calc(var(--se-u) * .95)) !important;
  margin-bottom:calc(var(--se-u) * .3) !important; }
§ ANA .lok-scroll a.lok-kart > div > div:nth-child(2) > div:nth-child(3){ margin-bottom:calc(var(--se-u) * .3) !important; }
§ ANA .lok-scroll a.lok-kart > div > div:nth-child(2) > div:nth-child(3) > span:first-child{
  font-size:max(13px, calc(var(--se-u) * 2)) !important; }
§ ANA .lok-scroll a.lok-kart > div > div:nth-child(2) > div:nth-child(4){ padding:1px calc(var(--se-u) * .7) !important; }
§ ANA .lok-scroll a.lok-kart > div > div:nth-child(2) > div:nth-child(4) > span:last-child{ font-size:var(--se-kucuk) !important; }

/* ORTA: harita kalan yüksekliği alır (çizim betiğinin verdiği piksel boyu geçersiz) */
§ ANA > [data-testid="stColumn"]:nth-child(2) [data-testid="stElementContainer"]:has(> iframe[src^="data:"]){
  flex:1 1 0 !important; min-height:0; height:auto !important; }
§ ANA iframe[src^="data:"]{ display:block; height:100% !important; }

/* SAĞ: OTO SET ve altındakiler sütunun içinde kayar; kartlar sıkı */
§ ANA > [data-testid="stColumn"]:nth-child(3) > [data-testid="stVerticalBlock"]{
  max-height:none !important; overflow-y:auto !important; overflow-x:hidden; padding-right:3px;
  scrollbar-width:thin; scrollbar-color:rgba(19,50,115,.35) transparent; }
§ ANA > [data-testid="stColumn"]:nth-child(3) > [data-testid="stVerticalBlock"] > :has(.st-key-dis_hava_karti, .st-key-sabah_analiz_karti, .alrt-y){
  margin-top:var(--se-ara); }
§ ANA [class*="_karti"][class*="st-key-"]{ margin-bottom:0 !important; border-radius:calc(var(--se-u) * 1.4) !important; }
§ ANA .st-key-oto_set_karti > div, § ANA .st-key-dis_hava_karti > div, § ANA .st-key-sabah_analiz_karti > div{
  padding-left:calc(var(--se-u) * 1.3) !important; padding-right:calc(var(--se-u) * 1.3) !important; }
§ ANA .st-key-oto_set_karti > div:first-child, § ANA .st-key-dis_hava_karti > div:first-child,
§ ANA .st-key-sabah_analiz_karti > div:first-child{ padding-top:calc(var(--se-u) * 1.1) !important; }
§ ANA .st-key-oto_set_karti > div:last-child, § ANA .st-key-dis_hava_karti > div:last-child,
§ ANA .st-key-sabah_analiz_karti > div:last-child{ padding-bottom:calc(var(--se-u) * 1.1) !important; }
§ ANA .st-key-oto_set_karti [data-testid="stVerticalBlock"]{ gap:calc(var(--se-u) * .7) !important; }
/* Kart başlıkları (OTO SET, DIŞ HAVA, sabah analizi) küçük */
§ ANA [class*="_karti"] div:is([style*="justify-content:space-between;gap:8px;margin-bottom:10px"], [style*="justify-content: space-between; gap: 8px; margin-bottom: 10px"]){
  margin-bottom:calc(var(--se-u) * .7) !important; }
§ ANA [class*="_karti"] span:is([style*="font-size:15px;font-weight:800"], [style*="font-size: 15px; font-weight: 800"]){ font-size:max(11px, calc(var(--se-u) * 1.55)) !important;
  gap:calc(var(--se-u) * .7) !important; }
§ ANA [class*="_karti"] span:is([style*="font-size:15px;font-weight:800"], [style*="font-size: 15px; font-weight: 800"]) .ai{ width:calc(var(--se-u) * 2.3) !important;
  height:calc(var(--se-u) * 2.3) !important; }
§ ANA .st-key-oto_saat_kart button, § ANA .st-key-oto_liste_kart button{
  height:max(38px, calc(var(--se-u) * 5.4)) !important; min-height:max(38px, calc(var(--se-u) * 5.4)) !important; }
/* SAHA DURUMU listesi daha kısa; uzun içerik kendi kutusunda kayar */
§ ANA .st-key-oto_set_karti div:is([style*="overflow-y:auto"], [style*="overflow-y: auto"]){ max-height:calc(var(--se-u) * 13) !important; }
§ ANA .st-key-oto_set_karti div:is([style*="border-radius:10px;padding:7px 10px;margin-top:10px"], [style*="border-radius: 10px; padding: 7px 10px; margin-top: 10px"]){
  margin-top:calc(var(--se-u) * .8) !important; padding:calc(var(--se-u) * .6) calc(var(--se-u) * 1) !important; }

/* BAŞLIK: tek ince satır (ACIBADEM SAĞLIK GRUBU · ENERJİ CANLI İZLEME) */
§ .bs-kutu{ display:flex !important; align-items:center; justify-content:center; flex-wrap:nowrap;
  gap:calc(var(--se-u) * 1.6); padding:0 0 calc(var(--se-u) * .4) !important; min-height:max(30px, calc(var(--se-u) * 3.6)); }
/* Sağ üstteki sabit düğmeler (ayarlar, yönetim, çıkış) başlık bandına sığsın, KPI kartlarının üstüne binmesin */
§ div.st-key-cikis_kutusu{ top:4px !important; gap:6px !important; }
§ .st-key-cikis_kutusu .stButton button, § .st-key-cikis_kutusu a.ayar-ac{ width:26px !important; height:26px !important;
  min-height:26px !important; border-radius:7px !important; }
§ [data-testid="stMarkdownContainer"]:has(> .bs-kutu){ margin-bottom:0 !important; }
§ .bs-ana{ font-size:clamp(16px, calc(var(--se-u) * 2.6), 26px) !important; line-height:1.1 !important;
  letter-spacing:calc(var(--se-u) * .4) !important; }
§ .bs-cizgi{ width:1px !important; height:calc(var(--se-u) * 2.2) !important; margin:0 !important;
  background:rgba(42,120,214,.45) !important; animation:none !important; }
§ .bs-alt{ font-size:max(9px, calc(var(--se-u) * 1.25)) !important; letter-spacing:2px !important; }
/* Simülasyon etiketi (sabit, sol üst) daha küçük */
§ div:is([style*="position:fixed;top:10px;left:18px"], [style*="position: fixed; top: 10px; left: 18px"]){ top:8px !important; font-size:8.5px !important;
  padding:3px 9px !important; letter-spacing:1.2px !important; }

/* KPI ŞERİDİ: kompakt kartlar; yükseklik ve yazılar görünür alana oranlı */
§ .st-key-ust_serit_demo{ margin:0 !important; }
/* Streamlit yazı kabının -16 px alt payı kartları alttaki sütunların üstüne bindiriyordu */
§ .st-key-ust_serit_demo [data-testid="stMarkdownContainer"]:has(> .us-serit){ margin-bottom:0 !important; }
§ .us-serit{ gap:var(--se-ara) !important; }
§ .us-serit .us-kart{ min-height:var(--se-kart-h); padding:var(--se-ic) calc(var(--se-u) * 1.5) calc(var(--se-ic) - 2px);
  border-radius:calc(var(--se-u) * 1.4); }
§ .us-serit .us-ust{ gap:calc(var(--se-u) * .8); }
§ .us-serit .us-simge{ width:var(--se-simge); height:var(--se-simge); }
§ .us-serit .us-simge .ai{ width:calc(var(--se-simge) * .72) !important; height:calc(var(--se-simge) * .72) !important; }
§ .us-serit .us-etiket{ font-size:max(9px, calc(var(--se-u) * 1.3)) !important; letter-spacing:1px; }
§ .us-serit .us-deger{ margin-top:calc(var(--se-u) * .7); }
§ .us-serit .us-sayi{ font-size:var(--se-sayi) !important; }
§ .us-serit .us-birim{ font-size:max(9.5px, calc(var(--se-u) * 1.4)) !important; }
§ .us-serit .us-alt, § .us-serit .us-liste > summary{ font-size:var(--se-kucuk) !important; }
§ .us-serit .us-alt{ margin-top:calc(var(--se-u) * .4); }
§ .us-serit .us-iz{ height:calc(var(--se-u) * 2); padding-top:calc(var(--se-u) * .4); }
§ .us-serit .us-iz svg{ height:calc(var(--se-u) * 1.6); }
§ .us-serit .us-uyari.us-uyari-yok .us-sayi{ font-size:calc(var(--se-sayi) * .72) !important; }
/* Uyarı kartı: özet satırı gizli (liste açılır pencerede), liste düğmesi sayının sağında */
§ .us-serit .us-ozet-satir{ display:none; }
§ .us-serit .us-uyari .us-liste{ position:absolute; right:calc(var(--se-u) * 1.5); margin:0; padding:0;
  top:calc(var(--se-ic) + var(--se-simge) + var(--se-u) * .7 + var(--se-sayi) * .5 - 7px); }
§ .us-serit .us-uyari .us-acilir{ right:calc(var(--se-u) * -1.5); }
/* "Anlık değerler" notu dikey yer almasın (başlık bandına sığmıyor) */
§ .us-not{ display:none; }
/* Kısa ekranda iz çizgisi gizlenir: sayı, birim, etiket ve alt satır kalır */
@media (max-height:820px){
  § .us-serit .us-iz{ display:none; }
}
"""


def ekran_css() -> str:
    """Tek ekran (kaydırmasız) düzenin stil bloğu. Yalnız sunum ana ekranında,
    şerit kabının içinde basılır; canlı portalda hiç çağrılmaz."""
    kurallar = _EKRAN_KURALLAR.replace("ANA", _ANA).replace("§", _EKRAN_KOK)
    return f"<style>\n@media {EKRAN_MEDYA}{{\n{kurallar}}}\n</style>"


def ozet_kart_html(sira: int, etiket: str, deger, alt_metin: str, birim: str, anahtar: str,
                   gecis_oznitelik: str, deger_metin: str, ikon_html: str, nokta_html: str,
                   renk: str = None) -> str:
    """Bir Global Özet kalemi. deger None → "canlı sayaç yok" (soluk, animasyonsuz).

    deger_metin: ilk çizimdeki yazı (kw_metin(deger)); gecis_oznitelik:
    gecis_ozellik() çıktısı (geçiş yoksa boş). Öznitelikler sol sütundaki
    eski kartla AYNI biçimde yazılır (data-deger .2f, data-ond 0, data-faz ozet-*).
    """
    k = renk or KART_RENK_VARSAYILAN
    canli = deger is not None
    if canli:
        govde = (f'<div class="us-deger"><span class="us-sayi">'
                 f'<span class="canli-sayi" data-deger="{deger:.2f}" data-ond="0" '
                 f'data-faz="ozet-{anahtar}"{gecis_oznitelik}>{deger_metin}</span></span>'
                 f'<span class="us-birim">{_html.escape(birim)}</span>'
                 f'<span class="us-egilim" aria-hidden="true"></span></div>')
        alt = (f'<div class="us-alt">{nokta_html}<span>{_html.escape(alt_metin)}</span></div>'
               if alt_metin else "")
        iz = '<div class="us-iz" aria-hidden="true"></div>'
    else:
        govde = '<div class="us-deger"><span class="us-yok">canlı sayaç yok</span></div>'
        alt = '<div class="us-alt"><span>sayaç bağlanınca dolar</span></div>'
        iz = ""
    sinif = "ozet-kart us-kart " + ("us-canli" if canli else "us-pasif")
    return (f'<a class="{sinif}" data-ozet="{anahtar}" href="?ozet={anahtar}" target="_self" '
            f'title="{_html.escape(etiket)} karşılaştırmasını aç" style="--k:{k};--sira:{sira};">'
            f'<div class="us-ust"><span class="us-simge">{ikon_html}</span>'
            f'<span class="us-etiket">{_html.escape(etiket)}</span><span class="us-ok">›</span></div>'
            f'{govde}{alt}{iz}</a>')


def uyari_ozeti(lok_ile_uyari: list) -> dict:
    """[(lok_id, [(önem, mesaj), ...]), ...] → kartın sayıları. SAF fonksiyon.

    toplam: uyarı satırı sayısı · lokasyon: uyarısı olan yer sayısı ·
    kritik: önemi "r" olan satır sayısı · son: gösterilecek ilk mesaj (listede
    en üstteki yerin önce kritik, yoksa ilk mesajı — sağ sütundaki sırayla aynı).
    """
    toplam = sum(len(u) for _, u in lok_ile_uyari)
    kritik = sum(1 for _, u in lok_ile_uyari for s, _m in u if s == "r")
    son = ""
    if lok_ile_uyari:
        ilk = lok_ile_uyari[0][1]
        son = next((m for s, m in ilk if s == "r"), ilk[0][1] if ilk else "")
    # Mesajlar listede HTML olarak basılır (bazıları kaçışlı gelir: &#x27; vb.);
    # tek satırlık özet için düz metne çevrilir, karta yazılırken yeniden kaçışlanır.
    son_metin = " ".join(_html.unescape(re.sub(r"<[^>]*>", "", son)).split())
    return {"toplam": toplam, "lokasyon": len(lok_ile_uyari), "kritik": kritik, "son": son,
            "son_metin": son_metin}


def uyari_kart_html(sira: int, lok_ile_uyari: list, liste_html: str, ikon_html: str,
                    nokta_html: str) -> str:
    """Canlı Uyarılar kartı. liste_html: sağ sütunda gösterilen listenin AYNISI
    (açılır pencerede). Uyarı yoksa yeşil "uyarı yok"."""
    oz = uyari_ozeti(lok_ile_uyari)
    if not oz["toplam"]:
        return (f'<div class="us-kart us-uyari us-uyari-yok us-canli" style="--k:#0ca30c;--sira:{sira};">'
                f'<div class="us-ust"><span class="us-simge">{ikon_html}</span>'
                f'<span class="us-etiket">Canlı Uyarılar</span></div>'
                f'<div class="us-deger"><span class="us-sayi">Uyarı yok</span></div>'
                f'<div class="us-alt">{nokta_html}<span>Tüm sistemler normal</span></div></div>')
    kritik = oz["kritik"] > 0
    k = "#d03b3b" if kritik else "#c98500"
    alt = f'{oz["lokasyon"]} lokasyon' + (f' · {oz["kritik"]} kritik' if kritik else "")
    return (f'<div class="us-kart us-uyari us-uyari-var{" us-kritik" if kritik else ""} us-canli" '
            f'style="--k:{k};--sira:{sira};">'
            f'<div class="us-ust"><span class="us-simge">{ikon_html}</span>'
            f'<span class="us-etiket">Canlı Uyarılar</span></div>'
            f'<div class="us-deger"><span class="us-sayi">{oz["toplam"]}</span>'
            f'<span class="us-birim">uyarı</span></div>'
            f'<div class="us-alt">{nokta_html}<span>{_html.escape(alt)}</span></div>'
            f'<div class="us-ozet-satir" title="{_html.escape(oz["son_metin"])}">'
            f'{_html.escape(oz["son_metin"])}</div>'
            f'<details class="us-liste"><summary><span class="us-ac">Listeyi aç</span>'
            f'<span class="us-kapa">Listeyi kapat</span></summary>'
            f'<div class="us-acilir">{liste_html}</div></details></div>')


def serit_html(kartlar: list, not_metin: str = "") -> str:
    alt = f'<div class="us-not">{_html.escape(not_metin)}</div>' if not_metin else ""
    return '<div class="us-serit">' + "".join(kartlar) + "</div>" + alt


def serit_betigi() -> str:
    """Tıklama köprüsü + sayı geçiş animasyonu + iz çizgisi. 0 px bileşende çalışır.

    * Tıklama: sol sütundaki ozet-kart köprüsüyle aynı (gizli düğme; yoksa href).
      Şerit sayfaya köprü betiğinden SONRA eklenebildiği için birkaç kez denenir.
    * Animasyon: akış betiği .canli-sayi yazısını değiştirdikçe MutationObserver
      kısa bir "tık" sınıfı ekler ve iz için değeri saklar. Yeni değer üretilmez.
    """
    return r"""
<script>
(function () {
  var W = window.parent, d;
  try { d = W.document; } catch (e) { return; }
  var AZ = W.matchMedia && W.matchMedia('(prefers-reduced-motion: reduce)').matches;
  W.__synUstIz = W.__synUstIz || {};
  var IZ_UZUN = 40;

  // Kart tıklaması belgeye (yakalama evresinde) bağlanır: şerit öğeleri yenilense
  // de çalışır; olay karta inmeden durdurulur, böylece sol sütundaki eski köprü
  // (a.ozet-kart'a doğrudan bağlanan) aynı tıklamayı ikinci kez işlemez.
  function kart_tikla(ev) {
    var a = ev.target && ev.target.closest && ev.target.closest('.us-serit a.ozet-kart');
    if (!a || ev.button !== 0 || ev.ctrlKey || ev.metaKey || ev.shiftKey) { return; }
    var btn = d.querySelector('.st-key-gizli_ozet_' + a.getAttribute('data-ozet') + ' button');
    if (btn) { ev.preventDefault(); ev.stopPropagation(); btn.click(); }
    // btn yoksa href ile eski yol çalışır
  }
  function sayi(t) {
    var v = parseFloat(String(t || '').replace(/\./g, '').replace(',', '.'));
    return isNaN(v) ? null : v;
  }
  function ciz(kart, dizi) {
    var kutu = kart.querySelector('.us-iz');
    if (!kutu || dizi.length < 2) { return; }
    var mn = Math.min.apply(null, dizi), mx = Math.max.apply(null, dizi), ar = (mx - mn) || 1;
    var n = IZ_UZUN - 1, noktalar = [];
    var bas = IZ_UZUN - dizi.length;
    dizi.forEach(function (v, i) {
      noktalar.push(((bas + i) / n * 100).toFixed(2) + ',' + (18 - (v - mn) / ar * 16).toFixed(2));
    });
    var ilk = noktalar[0].split(',')[0], son = noktalar[noktalar.length - 1].split(',');
    kutu.innerHTML = '<svg viewBox="0 0 100 20" preserveAspectRatio="none">'
      + '<polygon points="' + ilk + ',20 ' + noktalar.join(' ') + ' ' + son[0] + ',20" fill="var(--k)" fill-opacity=".09"/>'
      + '<polyline points="' + noktalar.join(' ') + '" fill="none" stroke="var(--k)" stroke-width="1.4" '
      + 'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
      + '<circle cx="' + son[0] + '" cy="' + son[1] + '" r="1.8" fill="var(--k)"/></svg>';
  }
  function guncelle(el) {
    var kart = el.closest('.us-kart'); if (!kart) { return; }
    var k = kart.getAttribute('data-ozet'), v = sayi(el.textContent);
    var dizi = W.__synUstIz[k] = W.__synUstIz[k] || [];
    var once = dizi.length ? dizi[dizi.length - 1] : null;
    if (v == null) { dizi.length = 0; var kz = kart.querySelector('.us-iz'); if (kz) { kz.innerHTML = ''; } return; }
    if (once === v && el.__usSon === el.textContent) { return; }
    el.__usSon = el.textContent;
    dizi.push(v); if (dizi.length > IZ_UZUN) { dizi.shift(); }
    ciz(kart, dizi);
    var e = kart.querySelector('.us-egilim');
    if (e && dizi.length > 8) {
      var ref = dizi[Math.max(0, dizi.length - 11)], fark = ref ? (v - ref) / Math.abs(ref) : 0;
      e.classList.remove('us-e-yukari', 'us-e-asagi');
      if (fark > 0.004) { e.textContent = '▲'; e.classList.add('us-e-yukari'); }
      else if (fark < -0.004) { e.textContent = '▼'; e.classList.add('us-e-asagi'); }
      else { e.textContent = ''; }
    }
    if (AZ || once == null || once === v) { return; }
    var kap = el.parentNode;
    kap.classList.remove('us-tik-yukari', 'us-tik-asagi');
    void kap.offsetWidth;
    kap.classList.add(v > once ? 'us-tik-yukari' : 'us-tik-asagi');
  }
  if (W.__synUstGozcu) { W.__synUstGozcu.disconnect(); }
  var gozcu = W.__synUstGozcu = new W.MutationObserver(function (kayitlar) {
    kayitlar.forEach(function (r) {
      var el = r.target.nodeType === 3 ? r.target.parentNode : r.target;
      if (el && el.classList && el.classList.contains('canli-sayi')) { guncelle(el); }
    });
  });
  // Sayfa yeniden çizilince şerit öğeleri yenilenebilir; yeni öğeler de izlenir
  function izle() {
    d.querySelectorAll('.us-serit .canli-sayi').forEach(function (el) {
      if (el.__usGozcu === gozcu) { return; }
      el.__usGozcu = gozcu;
      gozcu.observe(el, {childList: true, characterData: true, subtree: true});
      guncelle(el);
    });
  }
  // Açılır uyarı listesi: dışarı tıklanınca / Esc ile kapanır
  // Her çizimde yeniden kurulur (eski çerçevenin dinleyicisi çerçeveyle ölür)
  if (W.__synUstDisFn) { d.removeEventListener('click', W.__synUstDisFn, true); }
  if (W.__synUstEscFn) { d.removeEventListener('keydown', W.__synUstEscFn); }
  W.__synUstDisFn = function (ev) {
    kart_tikla(ev);
    d.querySelectorAll('.us-serit .us-liste[open]').forEach(function (x) {
      if (!x.contains(ev.target)) { x.removeAttribute('open'); }
    });
  };
  W.__synUstEscFn = function (ev) {
    if (ev.key === 'Escape') { d.querySelectorAll('.us-serit .us-liste[open]').forEach(function (x) { x.removeAttribute('open'); }); }
  };
  d.addEventListener('click', W.__synUstDisFn, true);
  d.addEventListener('keydown', W.__synUstEscFn);
  // Şerit bu betikten sonra da çizilebilir / yenilenebilir: hafif aralıkla bağla
  function kur() { if (d.querySelector('.us-serit')) { izle(); } }
  if (W.__synUstAralik) { W.clearInterval(W.__synUstAralik); }
  kur();
  W.__synUstAralik = W.setInterval(kur, 1000);
})();
</script>
"""
