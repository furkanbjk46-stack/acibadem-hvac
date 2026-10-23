/* SYNAPSE TASARIM KATMANI — simge değişimi ve sayı vurgusu.
   Simgeler synapse_ikon.js'ten (merkez/ikonlar.py'nin üretimi) gelir.
   Font Awesome simgesi → Synapse'in animasyonlu karşılığı. Eşleşmesi olmayan
   FA simgesine DOKUNULMAZ (ör. kaydet/sil/yükle gibi işlev simgeleri). */
(function () {
    "use strict";
    var D = window.SYNAPSE_IKON;
    if (!D) { return; }

    // CSS'i bir kez ekle (ikonlar.py'deki aynı kurallar)
    var st = document.createElement("style");
    st.id = "synapse-ikon-css";
    st.textContent = D.css;
    document.head.appendChild(st);

    // Font Awesome adı → Synapse simgesi
    var ESLE = {
        "sliders-h": "ayar", "cog": "ayar", "robot": "zeka",
        "wrench": "bakim", "tools": "bakim",
        "exclamation-triangle": "ariza", "exclamation-circle": "hata",
        "check-circle": "tamam", "check": "tamam", "check-double": "tamam",
        "wave-square": "hvac", "wind": "ahu", "fan": "fcu",
        "snowflake": "sogutma", "thermometer-half": "termometre",
        "chart-bar": "grafik", "chart-line": "grafik",
        "clock": "saat", "clipboard-list": "kayit", "tasks": "kayit",
        "tachometer-alt": "verim", "shield-alt": "saglik",
        "lira-sign": "enerji", "user-check": "oto"
    };

    function ad(i) {
        var m = /(?:^|\s)fa-([a-z0-9-]+)/.exec(i.className);
        // "fa-solid", "fa-fw" gibi ön ekleri atla
        var all = (i.className || "").split(/\s+/).filter(function (c) {
            return c.indexOf("fa-") === 0 && c !== "fa-solid" && c !== "fa-fw" && !/^fa-\d/.test(c);
        });
        return all.length ? all[0].slice(3) : (m ? m[1] : "");
    }

    function degistir(kok) {
        var liste = (kok || document).querySelectorAll("i.fas, i.fa-solid");
        for (var k = 0; k < liste.length; k++) {
            var i = liste[k];
            if (i.dataset.synGoruldu) { continue; }
            i.dataset.synGoruldu = "1";
            // Marka başlığı: Synapse'te Mekanik Zeka'nın simgesi 'zeka' (mor, kıvılcımlı)
            var syn = i.closest && i.closest(".header h1") ? "zeka" : ESLE[ad(i)];
            var svg = syn && D.svg[syn];
            if (!svg) { continue; }
            var renk = getComputedStyle(i).color;
            var s = document.createElement("span");
            s.className = "ai ai-" + syn + " ai-mz";
            s.style.setProperty("--ai-renk", renk);
            s.style.color = renk;
            s.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + svg + "</svg>";
            if (i.parentNode) { i.parentNode.replaceChild(s, i); }
        }
    }

    // KPI sayısı değişince kısa bir "sıçrama" (veri güncellendi hissi)
    function sayiIzle() {
        var liste = document.querySelectorAll(".kpi-value");
        for (var k = 0; k < liste.length; k++) {
            (function (el) {
                if (el.dataset.synIzleniyor) { return; }
                el.dataset.synIzleniyor = "1";
                el.dataset.synSon = el.textContent;
                new MutationObserver(function () {
                    if (el.textContent === el.dataset.synSon) { return; }
                    el.dataset.synSon = el.textContent;
                    el.classList.remove("syn-sicra");
                    void el.offsetWidth;            // animasyonu yeniden başlat
                    el.classList.add("syn-sicra");
                }).observe(el, { childList: true, characterData: true, subtree: true });
            })(liste[k]);
        }
    }

    function basla() {
        degistir(document);
        sayiIzle();
        // Sonradan çizilen içerik (tablo, modal, uyarı) için
        new MutationObserver(function (kayitlar) {
            for (var a = 0; a < kayitlar.length; a++) {
                var ek = kayitlar[a].addedNodes;
                for (var b = 0; b < ek.length; b++) {
                    if (ek[b].nodeType === 1) { degistir(ek[b]); }
                }
            }
        }).observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", basla);
    } else {
        basla();
    }
})();
