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
        "lira-sign": "enerji", "user-check": "oto", "fire": "kazan", "home": "harita"
    };

    var HAREKET = {
        "cloud-download-alt": "syn-an-asagi", "file-download": "syn-an-asagi", "download": "syn-an-asagi",
        "cloud-upload-alt": "syn-an-yukari", "upload": "syn-an-yukari", "file-upload": "syn-an-yukari",
        "vial": "syn-an-sallan", "flask": "syn-an-sallan", "edit": "syn-an-sallan",
        "sync-alt": "syn-an-don", "redo": "syn-an-don", "undo": "syn-an-don"
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
            if (!svg) {
                // Synapse karşılığı olmayan simge: yine de hareketli olsun
                i.classList.add(HAREKET[ad(i)] || "syn-an-nefes");
                continue;
            }
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


    // ── Kapasite göstergesi (ortalama vana %) ─────────────────────────────
    window.synKapasite = function (tur, ort, renk) {
        var bar = document.getElementById(tur + "CapacityBar");
        var deger = document.getElementById(tur + "CapacityValue");
        if (!bar) { return; }
        if (ort === null || isNaN(ort)) {
            bar.classList.add("syn-bos");
            bar.style.width = "100%";
            if (deger) { deger.style.setProperty("--c", "#c9d2e0"); }
            return;
        }
        bar.classList.remove("syn-bos");
        bar.style.setProperty("--c", renk);
        bar.style.width = Math.max(2, Math.min(100, ort)) + "%";
        if (deger) { deger.style.setProperty("--c", renk); }
    };

    // ── Talep / üretim kW: çubuk + sayı sayma animasyonu ──────────────────
    function say(el, hedef) {
        if (!el) { return; }
        var bas = parseFloat(el.dataset.synV);
        if (isNaN(bas)) { bas = 0; }
        el.dataset.synV = hedef;
        var t0 = null, sure = 700;
        function adim(t) {
            if (t0 === null) { t0 = t; }
            var k = Math.min(1, (t - t0) / sure);
            k = 1 - Math.pow(1 - k, 3);
            el.textContent = Math.round(bas + (hedef - bas) * k) + " kW";
            if (k < 1) { requestAnimationFrame(adim); }
        }
        requestAnimationFrame(adim);
    }
    window.synKw = function (tur, talep, uretim) {
        var enb = Math.max(talep || 0, uretim || 0, 1);
        if (talep !== null && talep !== undefined) {
            say(document.getElementById(tur + "_kw_talep"), talep);
            document.getElementById(tur + "_kw_talep_bar").style.width = (talep / enb * 100) + "%";
        } else {
            document.getElementById(tur + "_kw_talep_bar").style.width = "0%";
        }
        say(document.getElementById(tur + "_kw_uretim"), uretim || 0);
        document.getElementById(tur + "_kw_uretim_bar").style.width = ((uretim || 0) / enb * 100) + "%";
    };

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
