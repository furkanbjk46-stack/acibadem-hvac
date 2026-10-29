# -*- coding: utf-8 -*-
"""
ENERJİ VE VERİMLİLİK PORTALI — HAREKET / ANİMASYON (28.10.2026)
================================================================

YALNIZ TASARIM: kartlar ve grafikler süzülerek gelir, kartlar üzerine
gelince hafifçe yükselir, enerji diyagramı rozeti nabız atar.

SAYILARA DOKUNULMAZ (kullanıcı kararı, 28.10.2026): değerler sabit ve
olduğu gibi gösterilir — akan/dalgalanan değer yok, 0'dan sayma yok.
Bu yüzden betik (JavaScript) yoktur, yalnız CSS. Hareket azaltma tercihi
(prefers-reduced-motion) açıksa hiçbir animasyon çalışmaz.
"""

CSS = """
<style>
@keyframes synGelis { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes synNabiz { 0%, 100% { box-shadow: 0 0 0 0 rgba(12,163,12,.35); } 50% { box-shadow: 0 0 0 6px rgba(12,163,12,0); } }

/* Gelişler: bölüm kartları, metrikler, grafikler, enerji diyagramı kartları */
[class*="st-key-kart_"],
[data-testid="stMetric"],
[data-testid="stExpander"],
#ed-root .gcard {
    animation: synGelis .6s cubic-bezier(.2,.7,.2,1) both;
}
/* Yan yana sütunlar sırayla gelsin */
[data-testid="stColumn"]:nth-child(2) > div [data-testid="stMetric"] { animation-delay: .07s; }
[data-testid="stColumn"]:nth-child(3) > div [data-testid="stMetric"] { animation-delay: .14s; }
[data-testid="stColumn"]:nth-child(4) > div [data-testid="stMetric"] { animation-delay: .21s; }
/* Grafikler DÜZ (29.10.2026): ne giriş animasyonu ne akan dolgu */
[data-testid="stPlotlyChart"], [data-testid="stPlotlyChart"] * { animation: none !important; }
[data-testid="stColumn"]:nth-child(5) > div [data-testid="stMetric"] { animation-delay: .28s; }

/* Üzerine gelince hafif yükselme */
[class*="st-key-kart_"], #ed-root .gcard {
    transition: transform .25s ease, box-shadow .25s ease !important;
}
[class*="st-key-kart_"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 28px -18px rgba(19,50,115,.35) !important;
}
#ed-root .gcard:hover {
    transform: translateY(-3px);
    box-shadow: 0 2px 4px rgba(19,50,115,.06), 0 18px 34px -18px rgba(19,50,115,.38) !important;
}
/* Enerji diyagramı rozeti hafifçe nabız atar */
#ed-root .badge { animation: synNabiz 2.6s ease-in-out infinite; }

@media (prefers-reduced-motion: reduce) {
    [class*="st-key-kart_"], [data-testid="stMetric"],
    [data-testid="stExpander"], #ed-root .gcard, #ed-root .badge { animation: none !important; transition: none !important; }
}
</style>
"""

def uygula(st, components=None):
    """Hareket CSS'ini sayfaya ekler. Betik YOK: değerler olduğu gibi gösterilir."""
    st.markdown(CSS, unsafe_allow_html=True)
