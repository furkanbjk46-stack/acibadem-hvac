# -*- coding: utf-8 -*-
"""
SYNAPSE — Animasyonlu simgeler (TEK KAYNAK)
==========================================

Her metriğin TEK simgesi, TEK animasyonu ve TEK rengi burada tanımlıdır.
Ana ekran (Global Özet, Canlı Uyarılar) ve lokasyon Dashboard'u (Özet,
Kojen & Kaynak, HVAC & Bakım, Yürürlükteki Setler) simgeyi buradan alır;
böylece örneğin "soğutma" her ekranda aynı dönen kar tanesidir.

Kullanım:
    import ikonlar
    st.markdown(ikonlar.CSS, unsafe_allow_html=True)      # sayfada bir kez
    ikonlar.ikon("sogutma")              # metriğin kendi rengiyle, 22 px
    ikonlar.ikon("ariza", boyut=30)
    ikonlar.RENK["sogutma"]              # kart çerçevesi vb. için aynı renk

Simgeler satır içi SVG'dir (dış dosya / internet gerekmez). Animasyonlar
CSS ile yapılır; "hareketi azalt" tercihi açık cihazlarda durur.
"""

# Modül sürümü: Streamlit modülleri süreç boyunca önbellekte tutar; sayfa
# yeni sürümü isterken eski modül yüklü kalırsa yeniden yüklenir (bkz. çağıranlar).
SURUM = 3

# Metrik → renk. Çerçeve, simge ve vurgu rengi her yerde AYNI.
RENK = {
    "enerji":    "#f59e0b",   # toplam enerji / tüketim
    "dogalgaz":  "#eb6834",
    "sogutma":   "#2a78d6",   # soğutma tüketimi + chiller set
    "su":        "#0ea5e9",
    "kojen":     "#0ca30c",
    "sebeke":    "#4a3aa7",
    "mcc":       "#c98500",
    "kazan":     "#d03b3b",
    "trdp":      "#256abf",
    "verim":     "#c98500",   # kWh/m²
    "takvim":    "#0ca30c",   # dönem toplamı
    "kollektor": "#14b8a6",
    "fcu":       "#6366f1",
    "ahu":       "#0f766e",
    "ariza":     "#d03b3b",
    "bakim":     "#c98500",
    "hvac":      "#d03b3b",
    "alarm":     "#d03b3b",
    "oto":       "#133273",   # OTO SET
    "zeka":      "#7c3aed",   # mekanik zeka / AI analiz
    "oneri":     "#0ea5e9",   # öneri geri bildirimi
    "saglik":    "#e11d48",   # sistem sağlığı
    "gunduz":    "#f59e0b",
    "gece":      "#4a3aa7",
    "saat":      "#133273",
    "kayit":     "#133273",
    "termometre": "#c98500",
    "tamam":     "#0ca30c",
    "hata":      "#d03b3b",
    "geri":      "#133273",
    "grafik":    "#2a78d6",   # Dashboard sekmesi
    "ayar":      "#133273",
    "yonetim":   "#2a78d6",
    "cikis":     "#d03b3b",
}

# Aynı şeyin farklı adları — hepsi aynı simgeye düşer
_TAKMA = {"chiller": "sogutma", "tuketim": "enerji", "kojen_karsilama": "kojen",
          "canli": "enerji"}

_SVG = {
    # Şimşek — parlayıp söner
    "enerji": ('<path d="M13 2 4 14h7l-1 8 9-12h-7z" fill="currentColor" fill-opacity=".18"/>'
               '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>'),
    # Alev — titrer
    "dogalgaz": ('<path d="M12 3c1 3 5 5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2.5-5 .3 1.8 1.2 2.6 2 3'
                 ' 0-3-1-5.5.5-8z" fill="currentColor" fill-opacity=".18"/>'
                 '<path d="M12 3c1 3 5 5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2.5-5 .3 1.8 1.2 2.6 2 3'
                 ' 0-3-1-5.5.5-8z"/>'),
    # Kar tanesi — yavaşça döner
    "sogutma": ('<path d="M12 2v20M4.2 7l15.6 10M4.2 17 19.8 7"/>'
                '<path d="m9.5 3.5 2.5 2 2.5-2M9.5 20.5l2.5-2 2.5 2M3.8 10.3l3.1-.7-.9-3'
                'M20.2 13.7l-3.1.7.9 3M3.8 13.7l3.1.7-.9 3M20.2 10.3l-3.1-.7.9-3"/>'),
    # Damla — süzülür
    "su": ('<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" fill="currentColor"'
           ' fill-opacity=".18"/><path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>'
           '<path d="M9 14.5a3 3 0 0 0 3 3"/>'),
    # Dişli — döner
    "kojen": ('<circle cx="12" cy="12" r="3.2"/>'
              '<path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1'
              'M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/><circle cx="12" cy="12" r="6.3"/>'),
    # Fiş — kıvılcım yanıp söner
    "sebeke": ('<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5"/>'
               '<path class="ai-kivilcim" d="m13 9.5-2 2.5h2l-2 2.5" stroke-width="1.6"/>'),
    # Pano — ışıklar sırayla yanar
    "mcc": ('<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 17h8"/>'
            '<circle class="ai-led ai-led1" cx="8" cy="8" r="1.3" fill="currentColor"/>'
            '<circle class="ai-led ai-led2" cx="12" cy="8" r="1.3" fill="currentColor"/>'
            '<circle class="ai-led ai-led3" cx="16" cy="8" r="1.3" fill="currentColor"/>'
            '<path d="M8 12.5h8"/>'),
    # Kazan — içindeki alev titrer
    "kazan": ('<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8 7h8"/>'
              '<path class="ai-ic-alev" d="M12 10c.7 1.6 2.6 2.6 2.6 5a2.6 2.6 0 0 1-5.2 0c0-1.4.8-2.1'
              ' 1.3-2.6.2.9.6 1.3 1 1.5 0-1.5-.5-2.8.3-3.9z"/>'),
    # Trafo — iki bobin, akım dalgası
    "trdp": ('<circle cx="8.5" cy="12" r="5"/><circle cx="15.5" cy="12" r="5"/>'
             '<path class="ai-dalga" d="M2 12h2.5M19.5 12H22"/>'),
    # m² — ızgara, köşegen ölçü çizgisi kayar
    "verim": ('<rect x="4" y="4" width="16" height="16" rx="1.5"/>'
              '<path d="M4 12h16M12 4v16" stroke-opacity=".35"/>'
              '<path class="ai-olcu" d="M6.5 17.5 17.5 6.5"/>'),
    # Takvim — sayfa çevrilir
    "takvim": ('<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>'
               '<rect class="ai-sayfa" x="7" y="12.5" width="4" height="4" rx=".6" fill="currentColor"/>'),
    # Kollektör — dairesel akış okları döner
    "kollektor": ('<path d="M20 12a8 8 0 0 1-13.7 5.6M4 12a8 8 0 0 1 13.7-5.6"/>'
                  '<path d="M17.7 2.8v3.8h-3.8M6.3 21.2v-3.8h3.8"/>'),
    # FCU — fan kanatları döner
    "fcu": ('<circle cx="12" cy="12" r="9.5" stroke-opacity=".35"/>'
            '<g class="ai-fan"><path d="M12 12c0-3 1-6 3.5-6.5 1.6-.3 2.3 1.3 1.3 2.5-1.2 1.4-3 2.5-4.8 4'
            'M12 12c3 0 6 1 6.5 3.5.3 1.6-1.3 2.3-2.5 1.3-1.4-1.2-2.5-3-4-4.8'
            'M12 12c0 3-1 6-3.5 6.5-1.6.3-2.3-1.3-1.3-2.5 1.2-1.4 3-2.5 4.8-4'
            'M12 12c-3 0-6-1-6.5-3.5-.3-1.6 1.3-2.3 2.5-1.3 1.4 1.2 2.5 3 4 4.8"/></g>'
            '<circle cx="12" cy="12" r="1.2" fill="currentColor"/>'),
    # AHU — santral kutusu, hava dalgaları akar
    "ahu": ('<rect x="2.5" y="6" width="12" height="12" rx="1.5"/>'
            '<circle cx="8.5" cy="12" r="3.2"/><path d="M8.5 8.8v6.4M5.3 12h6.4" stroke-opacity=".5"/>'
            '<path class="ai-hava ai-hava1" d="M16.5 9c1.5-1 3-1 4.5 0"/>'
            '<path class="ai-hava ai-hava2" d="M16.5 12c1.5-1 3-1 4.5 0"/>'
            '<path class="ai-hava ai-hava3" d="M16.5 15c1.5-1 3-1 4.5 0"/>'),
    # Arıza — üçgen içinde ünlem, sallanır ve nabız gibi atar
    "ariza": ('<path d="M10.3 3.6 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0z"'
              ' fill="currentColor" fill-opacity=".14"/>'
              '<path d="M10.3 3.6 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0z"/>'
              '<path class="ai-unlem" d="M12 9v5M12 17.4v.01" stroke-width="2.4"/>'),
    # Bakım — İngiliz anahtarı, somun sıkar gibi sallanır
    "bakim": ('<path d="M14.7 6.3a4.2 4.2 0 0 0-5.6 5.4l-6.2 6.2a1.6 1.6 0 0 0 2.3 2.3l6.2-6.2'
              'a4.2 4.2 0 0 0 5.4-5.6l-2.6 2.6-2.3-.6-.6-2.3z" fill="currentColor" fill-opacity=".16"/>'
              '<path d="M14.7 6.3a4.2 4.2 0 0 0-5.6 5.4l-6.2 6.2a1.6 1.6 0 0 0 2.3 2.3l6.2-6.2'
              'a4.2 4.2 0 0 0 5.4-5.6l-2.6 2.6-2.3-.6-.6-2.3z"/>'),
    # HVAC analiz — nabız çizgisi akar
    "hvac": ('<rect x="2.5" y="4" width="19" height="16" rx="2.5" stroke-opacity=".35"/>'
             '<path class="ai-nabiz" d="M4 12h3.5l2-4.5 3.5 9 2.2-4.5H20"/>'),
    # Alarm — tepe lambası, ışık halkası döner ve titrer
    "alarm": ('<path d="M6.5 19v-6a5.5 5.5 0 0 1 11 0v6" fill="currentColor" fill-opacity=".16"/>'
              '<path d="M6.5 19v-6a5.5 5.5 0 0 1 11 0v6M4 19h16v2.5H4zM12 10v4"/>'
              '<path class="ai-isik" d="M12 2v2M4.2 5.2l1.4 1.4M19.8 5.2l-1.4 1.4M1.8 12h2M20.2 12h2"/>'),
    # OTO SET — robot; anteni yanıp söner, gözleri kırpar
    "oto": ('<rect x="4.5" y="8" width="15" height="11.5" rx="3" fill="currentColor" fill-opacity=".12"/>'
            '<rect x="4.5" y="8" width="15" height="11.5" rx="3"/><path d="M12 4.5V8M2.5 12.5v3M21.5 12.5v3M9 16.5h6"/>'
            '<circle class="ai-anten" cx="12" cy="3.6" r="1.3" fill="currentColor"/>'
            '<g class="ai-goz"><circle cx="9.2" cy="12.6" r="1.25" fill="currentColor"/>'
            '<circle cx="14.8" cy="12.6" r="1.25" fill="currentColor"/></g>'),
    # Mekanik zeka / AI — çip, çevresinde kıvılcımlar döner
    "zeka": ('<rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" fill-opacity=".12"/>'
             '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>'
             '<path d="M9.5 3v3.5M14.5 3v3.5M9.5 17.5V21M14.5 17.5V21M3 9.5h3.5M3 14.5h3.5M17.5 9.5H21M17.5 14.5H21"/>'
             '<path class="ai-kivilcim" d="M12 9.2l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" fill="currentColor"/>'),
    # Öneri geri bildirimi — konuşma balonu, içinde noktalar sırayla
    "oneri": ('<path d="M4 5.5h16a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 3.5V17.5H4A1.5 1.5 0 0 1 2.5 16V7A1.5 1.5 0 0 1 4 5.5z"'
              ' fill="currentColor" fill-opacity=".12"/>'
              '<path d="M4 5.5h16a1.5 1.5 0 0 1 1.5 1.5v9a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 3.5V17.5H4A1.5 1.5 0 0 1 2.5 16V7A1.5 1.5 0 0 1 4 5.5z"/>'
              '<circle class="ai-led ai-led1" cx="8" cy="11.5" r="1.1" fill="currentColor"/>'
              '<circle class="ai-led ai-led2" cx="12" cy="11.5" r="1.1" fill="currentColor"/>'
              '<circle class="ai-led ai-led3" cx="16" cy="11.5" r="1.1" fill="currentColor"/>'),
    # Sistem sağlığı — kalp, içinde nabız; kalp atar
    "saglik": ('<path d="M12 20.5s-8-4.7-8-10.6A4.4 4.4 0 0 1 12 7.3a4.4 4.4 0 0 1 8 2.6c0 5.9-8 10.6-8 10.6z"'
               ' fill="currentColor" fill-opacity=".14"/>'
               '<path d="M12 20.5s-8-4.7-8-10.6A4.4 4.4 0 0 1 12 7.3a4.4 4.4 0 0 1 8 2.6c0 5.9-8 10.6-8 10.6z"/>'
               '<path class="ai-nabiz" d="M6 12.5h3l1.5-2.5 2 5 1.5-2.5H18" stroke-width="1.6"/>'),
    # Gündüz — güneş, ışınları döner
    "gunduz": ('<circle cx="12" cy="12" r="4" fill="currentColor" fill-opacity=".25"/><circle cx="12" cy="12" r="4"/>'
               '<g class="ai-isinlar"><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6'
               'M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/></g>'),
    # Gece — ay, yıldız yanıp söner
    "gece": ('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" fill="currentColor" fill-opacity=".18"/>'
             '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'
             '<path class="ai-yildiz" d="M17 3.5v3M15.5 5h3" stroke-width="1.5"/>'),
    # Saat — akrep/yelkovan döner
    "saat": ('<circle cx="12" cy="12" r="9"/>'
             '<path class="ai-yelkovan" d="M12 12V6.5"/><path class="ai-akrep" d="M12 12h3.5"/>'
             '<circle cx="12" cy="12" r="1" fill="currentColor"/>'),
    # Kayıt — pano, satırlar sırayla yazılır
    "kayit": ('<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 2.8h6v2.6H9z"/>'
              '<path class="ai-satir ai-satir1" d="M8.5 10h7"/><path class="ai-satir ai-satir2" d="M8.5 13.5h7"/>'
              '<path class="ai-satir ai-satir3" d="M8.5 17h4.5"/>'),
    # Termometre — cıva yükselip alçalır
    "termometre": ('<path d="M10 4.5a2 2 0 0 1 4 0v9.3a4 4 0 1 1-4 0z"/>'
                   '<circle cx="12" cy="17" r="2" fill="currentColor"/>'
                   '<path class="ai-civa" d="M12 15.5V8" stroke-width="2.2"/>'),
    # Tamam — onay işareti çizilir
    "tamam": ('<circle cx="12" cy="12" r="9.5" fill="currentColor" fill-opacity=".12"/>'
              '<path class="ai-ciz" d="m7.5 12.5 3 3 6-6.5" stroke-width="2.4"/>'),
    # Hata — çarpı sallanır
    "hata": ('<circle cx="12" cy="12" r="9.5" fill="currentColor" fill-opacity=".12"/>'
             '<path d="m8.5 8.5 7 7M15.5 8.5l-7 7" stroke-width="2.4"/>'),
    # Geri — ok sola itilir
    "geri": '<path d="M19 12H5M11 6l-6 6 6 6" stroke-width="2.2"/>',
    # Ayarlar — kaydırıcılar
    "ayar": ('<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/>'
             '<circle class="ai-dugme ai-dugme1" cx="15" cy="6" r="2"/>'
             '<circle class="ai-dugme ai-dugme2" cx="9" cy="12" r="2"/>'
             '<circle class="ai-dugme ai-dugme3" cx="17" cy="18" r="2"/>'),
    # Yönetim — sunucu dolabı, ışıklar sırayla yanar
    "yonetim": ('<rect x="4" y="3.5" width="16" height="7" rx="1.6"/><rect x="4" y="13.5" width="16" height="7" rx="1.6"/>'
                '<circle class="ai-led ai-led1" cx="8" cy="7" r="1.1" fill="currentColor"/>'
                '<circle class="ai-led ai-led2" cx="8" cy="17" r="1.1" fill="currentColor"/>'
                '<path d="M12 7h5M12 17h5" stroke-opacity=".5"/>'),
    # Çıkış — güç simgesi
    "cikis": '<path d="M12 3v8"/><path d="M6.6 6.6a7.5 7.5 0 1 0 10.8 0"/>',
    # Grafik — çubuklar büyüyüp küçülür
    "grafik": ('<path d="M3 21h18" />'
               '<rect class="ai-cubuk ai-cubuk1" x="5" y="11" width="3.2" height="10" rx=".8" fill="currentColor" fill-opacity=".25"/>'
               '<rect class="ai-cubuk ai-cubuk2" x="10.4" y="6" width="3.2" height="15" rx=".8" fill="currentColor" fill-opacity=".25"/>'
               '<rect class="ai-cubuk ai-cubuk3" x="15.8" y="9" width="3.2" height="12" rx=".8" fill="currentColor" fill-opacity=".25"/>'),
}

# Her simgenin animasyonu (CSS sınıfı). Süreler yavaş tutuldu: ekranda
# onlarca simge aynı anda oynuyor, göz yormasın.
CSS = """
<style>
.ai{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;line-height:0;
    vertical-align:middle;}
/* Renk CSS değişkeniyle SVG'ye bağlanır: sayfadaki genel "span rengi"
   kuralları (ör. ana ekranın koyu yazı rengi) simgeyi boyamasın. */
.ai svg{width:100%;height:100%;overflow:visible;fill:none;stroke-width:1.9;
    stroke-linecap:round;stroke-linejoin:round;
    color:var(--ai-renk, currentColor) !important; stroke:var(--ai-renk, currentColor) !important;}
.ai svg *{transform-box:fill-box;}

@keyframes ai-parla{0%,100%{opacity:1;filter:drop-shadow(0 0 0 currentColor);}
  50%{opacity:.55;filter:drop-shadow(0 0 4px currentColor);}}
@keyframes ai-titre{0%,100%{transform:scale(1,1) skewX(0);}25%{transform:scale(.96,1.05) skewX(2deg);}
  50%{transform:scale(1.03,.95) skewX(-2deg);}75%{transform:scale(.98,1.04) skewX(1deg);}}
@keyframes ai-don{to{transform:rotate(360deg);}}
@keyframes ai-suz{0%,100%{transform:translateY(0);}50%{transform:translateY(2.5px);}}
@keyframes ai-yanson{0%,40%,100%{opacity:.25;}20%{opacity:1;}}
@keyframes ai-kay{0%{stroke-dashoffset:24;}100%{stroke-dashoffset:0;}}
@keyframes ai-cevir{0%,100%{transform:scaleY(1);opacity:1;}50%{transform:scaleY(.15);opacity:.5;}}
@keyframes ai-salla{0%,100%{transform:rotate(0);}20%{transform:rotate(-7deg);}40%{transform:rotate(6deg);}
  60%{transform:rotate(-4deg);}80%{transform:rotate(2deg);}}
@keyframes ai-atis{0%,100%{transform:scale(1);opacity:1;}50%{transform:scale(1.25);opacity:.6;}}
@keyframes ai-anahtar{0%,100%{transform:rotate(0);}30%{transform:rotate(-28deg);}60%{transform:rotate(8deg);}}
@keyframes ai-akis{0%{opacity:0;transform:translateX(-3px);}40%{opacity:1;}100%{opacity:0;transform:translateX(3px);}}
@keyframes ai-isik{0%,100%{opacity:.2;}50%{opacity:1;}}

.ai-enerji svg{animation:ai-parla 1.8s ease-in-out infinite;}
.ai-dogalgaz svg{animation:ai-titre 1.2s ease-in-out infinite;transform-origin:50% 90%;}
.ai-sogutma svg{animation:ai-don 9s linear infinite;}
.ai-su svg{animation:ai-suz 2.2s ease-in-out infinite;}
.ai-kojen svg{animation:ai-don 6s linear infinite;}
.ai-sebeke .ai-kivilcim{animation:ai-yanson 1.4s ease-in-out infinite;}
.ai-mcc .ai-led{animation:ai-yanson 1.8s ease-in-out infinite;}
.ai-mcc .ai-led2{animation-delay:.6s;} .ai-mcc .ai-led3{animation-delay:1.2s;}
.ai-kazan .ai-ic-alev{animation:ai-titre 1.1s ease-in-out infinite;transform-origin:50% 100%;}
.ai-trdp .ai-dalga{animation:ai-yanson 1.2s ease-in-out infinite;}
.ai-trdp svg{animation:ai-parla 2.6s ease-in-out infinite;}
.ai-verim .ai-olcu{stroke-dasharray:4 3;animation:ai-kay 1.6s linear infinite;}
.ai-takvim .ai-sayfa{animation:ai-cevir 2.4s ease-in-out infinite;transform-origin:50% 0;}
.ai-kollektor svg{animation:ai-don 4s linear infinite;}
.ai-fcu .ai-fan{animation:ai-don 2.4s linear infinite;transform-origin:50% 50%;}
.ai-ahu .ai-hava{animation:ai-akis 1.8s ease-in-out infinite;}
.ai-ahu .ai-hava2{animation-delay:.3s;} .ai-ahu .ai-hava3{animation-delay:.6s;}
.ai-ariza svg{animation:ai-salla 1.6s ease-in-out infinite;transform-origin:50% 100%;}
.ai-ariza .ai-unlem{animation:ai-atis .8s ease-in-out infinite;transform-origin:50% 50%;}
.ai-bakim svg{animation:ai-anahtar 2s ease-in-out infinite;transform-origin:20% 80%;}
.ai-hvac .ai-nabiz{stroke-dasharray:30;animation:ai-kay 1.8s linear infinite;}
.ai-alarm svg{animation:ai-salla 1.4s ease-in-out infinite;transform-origin:50% 100%;}
.ai-alarm .ai-isik{animation:ai-isik .7s ease-in-out infinite;}

@keyframes ai-kirp{0%,90%,100%{transform:scaleY(1);}95%{transform:scaleY(.1);}}
@keyframes ai-ciz{0%{stroke-dashoffset:16;}60%,100%{stroke-dashoffset:0;}}
@keyframes ai-itis{0%,100%{transform:translateX(0);}50%{transform:translateX(-3px);}}
@keyframes ai-boy{0%,100%{transform:scaleY(1);}50%{transform:scaleY(.55);}}
@keyframes ai-civa{0%,100%{transform:scaleY(1);}50%{transform:scaleY(.55);}}
@keyframes ai-nefes{0%,100%{transform:scale(1);}50%{transform:scale(1.12);}}
@keyframes ai-kaydir{0%,100%{transform:translateX(0);}50%{transform:translateX(-3px);}}
@keyframes ai-yazi{0%{stroke-dashoffset:8;opacity:.3;}50%,100%{stroke-dashoffset:0;opacity:1;}}

.ai-oto .ai-anten{animation:ai-yanson 1.4s ease-in-out infinite;}
.ai-oto .ai-goz{animation:ai-kirp 3.5s ease-in-out infinite;transform-origin:50% 50%;}
.ai-oto svg{animation:ai-suz 2.6s ease-in-out infinite;}
.ai-zeka .ai-kivilcim{animation:ai-atis 1.4s ease-in-out infinite;transform-origin:50% 50%;}
.ai-zeka svg{animation:ai-parla 2.4s ease-in-out infinite;}
.ai-oneri .ai-led{animation:ai-yanson 1.5s ease-in-out infinite;}
.ai-oneri .ai-led2{animation-delay:.5s;} .ai-oneri .ai-led3{animation-delay:1s;}
.ai-saglik svg{animation:ai-nefes 1.1s ease-in-out infinite;}
.ai-saglik .ai-nabiz{stroke-dasharray:30;animation:ai-kay 1.8s linear infinite;}
.ai-gunduz .ai-isinlar{animation:ai-don 10s linear infinite;transform-origin:50% 50%;transform-box:view-box;}
.ai-gece .ai-yildiz{animation:ai-isik 1.6s ease-in-out infinite;}
.ai-gece svg{animation:ai-suz 3s ease-in-out infinite;}
.ai-saat .ai-yelkovan{animation:ai-don 4s linear infinite;transform-origin:12px 12px;transform-box:view-box;}
.ai-saat .ai-akrep{animation:ai-don 48s linear infinite;transform-origin:12px 12px;transform-box:view-box;}
.ai-kayit .ai-satir{stroke-dasharray:8;animation:ai-yazi 2.4s ease-in-out infinite;}
.ai-kayit .ai-satir2{animation-delay:.4s;} .ai-kayit .ai-satir3{animation-delay:.8s;}
.ai-termometre .ai-civa{animation:ai-civa 2.6s ease-in-out infinite;transform-origin:50% 100%;}
.ai-tamam .ai-ciz{stroke-dasharray:16;animation:ai-ciz 2.4s ease-out infinite;}
.ai-hata svg{animation:ai-salla 1.4s ease-in-out infinite;transform-origin:50% 50%;}
.ai-geri svg{animation:ai-itis 1.4s ease-in-out infinite;}
.ai-ayar .ai-dugme{animation:ai-kaydir 2.4s ease-in-out infinite;}
.ai-ayar .ai-dugme2{animation-delay:.5s;animation-direction:reverse;} .ai-ayar .ai-dugme3{animation-delay:1s;}
.ai-yonetim .ai-led{animation:ai-yanson 1.6s ease-in-out infinite;} .ai-yonetim .ai-led2{animation-delay:.8s;}
.ai-cikis svg{animation:ai-parla 2s ease-in-out infinite;}
.ai-grafik .ai-cubuk{animation:ai-boy 1.8s ease-in-out infinite;transform-origin:50% 100%;}
.ai-grafik .ai-cubuk2{animation-delay:.3s;} .ai-grafik .ai-cubuk3{animation-delay:.6s;}

/* Canlı / bağlı göstergesi: atan nokta */
@keyframes ai-nokta{0%,100%{opacity:1;transform:scale(1);box-shadow:0 0 0 0 var(--ai-renk);}
  50%{opacity:.55;transform:scale(.8);box-shadow:0 0 0 4px transparent;}}
.ai-nokta{display:inline-block;flex-shrink:0;border-radius:50%;background:var(--ai-renk,#0ca30c);
  animation:ai-nokta 1.6s ease-in-out infinite;}

/* Düğme / sekme etiketleri: SVG konamayan yerlerde maske ile simge (bkz. etiket_css) */
.ai-etk::before{content:"";display:inline-block;flex-shrink:0;vertical-align:-3px;margin-right:6px;
  background:var(--ai-renk);-webkit-mask:var(--ai-maske) center/contain no-repeat;
  mask:var(--ai-maske) center/contain no-repeat;}

/* Durum "sorun yok" iken simge sakin durur (ör. arıza = 0) */
.ai.ai-sakin svg, .ai.ai-sakin svg *{animation:none !important;}

@media (prefers-reduced-motion: reduce){ .ai svg, .ai svg *, .ai-nokta{animation:none !important;} }
</style>
"""


def renk(ad: str) -> str:
    ad = _TAKMA.get(ad, ad)
    return RENK.get(ad, "#2a78d6")


def ikon(ad: str, boyut: int = 22, renk_: str = None, sakin: bool = False) -> str:
    """Animasyonlu simge HTML'i. Bilinmeyen ad → boş metin (sayfa bozulmaz)."""
    ad = _TAKMA.get(ad, ad)
    govde = _SVG.get(ad)
    if not govde:
        return ""
    r = renk_ or RENK.get(ad, "#2a78d6")
    return ('<span class="ai ai-%s%s" style="width:%dpx;height:%dpx;--ai-renk:%s;color:%s;">'
            '<svg viewBox="0 0 24 24" aria-hidden="true">%s</svg></span>'
            % (ad, " ai-sakin" if sakin else "", boyut, boyut, r, r, govde))


# Maske simgelerinde (düğme / sekme etiketi) bütün simge hareket eder;
# parça animasyonu (ör. LED sırası) maske içinde çalışmaz.
_ETIKET_ANIM = {
    "saat": "ai-salla 2s ease-in-out infinite", "kayit": "ai-suz 2.2s ease-in-out infinite",
    "geri": "ai-itis 1.4s ease-in-out infinite", "grafik": "ai-nefes 1.8s ease-in-out infinite",
    "enerji": "ai-parla 1.8s ease-in-out infinite", "sogutma": "ai-don 9s linear infinite",
    "kojen": "ai-don 6s linear infinite", "oto": "ai-suz 2.6s ease-in-out infinite",
    "ayar": "ai-salla 2.4s ease-in-out infinite", "yonetim": "ai-nefes 1.8s ease-in-out infinite",
    "cikis": "ai-parla 2s ease-in-out infinite", "dogalgaz": "ai-titre 1.2s ease-in-out infinite",
    "su": "ai-suz 2.2s ease-in-out infinite", "trdp": "ai-parla 2.6s ease-in-out infinite",
    "takvim": "ai-nefes 2.4s ease-in-out infinite", "verim": "ai-nefes 2s ease-in-out infinite",
    "sebeke": "ai-parla 1.6s ease-in-out infinite", "mcc": "ai-nefes 1.8s ease-in-out infinite",
    "kazan": "ai-titre 1.2s ease-in-out infinite",
}


def etiket_css(secici: str, ad: str, boyut: int = 16, renk_: str = None) -> str:
    """Düğme / sekme gibi SVG konamayan bir öğenin önüne hareketli simge koyan
    CSS kuralı. Örn: etiket_css('.st-key-oto_saat_kart button p:first-child', 'saat')"""
    from urllib.parse import quote
    ad = _TAKMA.get(ad, ad)
    govde = _SVG.get(ad, "")
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
           "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
           + govde.replace('"', "'").replace("currentColor", "black") + "</svg>")
    r = renk_ or RENK.get(ad, "#2a78d6")
    anim = _ETIKET_ANIM.get(ad, "ai-nefes 2s ease-in-out infinite")
    return ("%s::before{content:'';display:inline-block;flex-shrink:0;vertical-align:-3px;"
            "margin-right:6px;width:%dpx;height:%dpx;background:%s;"
            "-webkit-mask:url(\"data:image/svg+xml,%s\") center/contain no-repeat;"
            "mask:url(\"data:image/svg+xml,%s\") center/contain no-repeat;animation:%s;}"
            "@media (prefers-reduced-motion: reduce){%s::before{animation:none;}}"
            % (secici, boyut, boyut, r, quote(svg), quote(svg), anim, secici))


def nokta(renk_: str = "#0ca30c", boyut: int = 7) -> str:
    """Canlı / bağlı göstergesi: atan nokta."""
    return ('<span class="ai-nokta" style="width:%dpx;height:%dpx;--ai-renk:%s;"></span>'
            % (boyut, boyut, renk_))
