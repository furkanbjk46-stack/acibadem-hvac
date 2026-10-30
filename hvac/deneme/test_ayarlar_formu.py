# -*- coding: utf-8 -*-
"""Ayarlar ekranı — form ile motor birbirini tutuyor mu?

SAHADAN GELEN HATA (17.10.2026): "Kaydet çalışmıyor."
Sebep tek değildi:
  1) HTML'deki min/max ELLE yazılmıştı ve sunucudaki CONFIG_LIMITS ile
     tutmuyordu (ekran 1-20 kabul ediyor, sunucu 4-8 istiyordu).
  2) Sunucu 422 + {"detail": ...} dönüyordu; ekran data.message okuyordu →
     kullanıcı "Ayarlar kaydedilemedi: undefined" görüyordu, sebebi değil.
  3) Reddedilen kayıttan SONRA Chiller/FCU ayarları yine de yazılıyordu —
     yarısı kaydedilmiş bir ayar takımı kalıyordu.
  4) populateSettingsForm elle tutulan anahtar listesi kullanıyordu; listede
     olmayan alan HTML'deki değerle kalıyordu.

Bu test dördünün de geri gelmesini engeller ve ayrıca motorun okuduğu her
sınırlı ayarın ekranda GÖRÜNÜR olmasını şart koşar: görünmeyen bir ayar
aralık dışı kalırsa kullanıcı hiçbir şeyi kaydedemez ve nedenini bulamaz.
"""
import os
import re
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

PY = open(os.path.join(BURASI, "main_portal.py"), encoding="utf-8").read()
HTML = open(os.path.join(BURASI, "static", "index.html"), encoding="utf-8").read()
ON_KOSUL = open(os.path.join(BURASI, "on_kosul.py"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── Kaynaklardan anahtarları çıkar ───────────────────────────────────────
_cfg_blok = re.search(r"^CONFIG\s*=\s*\{(.*?)^\}", PY, re.S | re.M).group(1)
CONFIG_ANAHTARLARI = re.findall(r'^\s{4}"([A-Z_0-9]+)"\s*:', _cfg_blok, re.M)
_liste_olanlar = set(re.findall(r'^\s{4}"([A-Z_0-9]+)"\s*:\s*\[', _cfg_blok, re.M))

_lim_blok = re.search(r"CONFIG_LIMITS\s*=\s*\{(.*?)\n\}", PY, re.S).group(1)
LIMITLER = {k: (float(a), float(u)) for k, a, u in
            re.findall(r'"([A-Z_0-9]+)"\s*:\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)', _lim_blok)}

# Formdaki alanlar: id="set_XXX" + min/max öznitelikleri
FORM = {}
for m in re.finditer(r'<input[^>]*id="set_([A-Za-z_0-9]+)"[^>]*>', HTML):
    etiket = m.group(0)
    FORM[m.group(1)] = {
        "min": (re.search(r'min="([-\d.]+)"', etiket) or [None, None])[1],
        "max": (re.search(r'max="([-\d.]+)"', etiket) or [None, None])[1],
    }

CHILLER_FCU = set(re.search(r"const CHILLER_FCU_KEYS = \[(.*?)\]", HTML, re.S).group(1)
                  .replace("'", "").replace("\n", "").replace(" ", "").split(","))
CHILLER_FCU.discard("")

c("CONFIG okundu", len(CONFIG_ANAHTARLARI) > 40, len(CONFIG_ANAHTARLARI))
c("CONFIG_LIMITS okundu", len(LIMITLER) >= 10, len(LIMITLER))
c("form alanları okundu", len(FORM) > 40, len(FORM))

# ── 1) Sınırlı HER ayar ekranda olmalı ───────────────────────────────────
# Görünmeyen bir ayar aralık dışıysa kayıt HER SEFERİNDE reddedilir ve
# kullanıcı hangi alanı düzelteceğini göremez — "kaydet çalışmıyor" budur.
_gorunmez = [k for k in LIMITLER if k not in FORM]
c("sınırı olan her ayar formda var", not _gorunmez, _gorunmez)

# ── 2) Formdaki her alan CANLI bir ayara karşılık gelmeli ────────────────
_hayalet = [k for k in FORM if k not in CONFIG_ANAHTARLARI and k not in CHILLER_FCU]
c("formda karşılığı olmayan alan yok", not _hayalet, _hayalet)


def _oku(yol):
    try:
        return open(os.path.join(BURASI, yol), encoding="utf-8").read()
    except OSError:
        return ""


# Ayarı OKUYABİLECEK bütün taraflar: mekanik motor, ön koşul kapısı ve
# enerji tarafı (m² ve birim fiyatlar oradan okunur).
_TUKETICILER = (PY, ON_KOSUL, _oku("app_portal.py"), _oku("daily_report.py"),
                _oku("monthly_summary_report.py"))


def _motor_okuyor_mu(anahtar):
    """Ayar gerçekten okunuyor mu (CONFIG'teki tanım satırı sayılmaz)."""
    desen = re.compile(r'(\[\s*["\']%s["\']\s*\]|\.get\(\s*["\']%s["\'])' % (anahtar, anahtar))
    return any(desen.search(k) for k in _TUKETICILER if k)


_olu = [k for k in FORM if k in CONFIG_ANAHTARLARI and not _motor_okuyor_mu(k)]
c("formda ÖLÜ ayar yok (değiştirince bir şey değişmeyen)", not _olu, _olu)

# ── 3) Ekranın kabul ettiği aralık sunucudan GENİŞ olamaz ────────────────
_genis = []
for k, (alt, ust) in LIMITLER.items():
    f = FORM.get(k)
    if not f:
        continue
    if f["min"] is None or f["max"] is None:
        _genis.append("%s: min/max yok" % k)
        continue
    if float(f["min"]) < alt or float(f["max"]) > ust:
        _genis.append("%s: ekran %s-%s, sunucu %g-%g" % (k, f["min"], f["max"], alt, ust))
c("ekran aralığı sunucu sınırını aşmıyor", not _genis, _genis)

# ── 4) Sınırlar sunucudan geliyor, ekranda kopya tutulmuyor ──────────────
c("/api/settings sınırları döndürüyor", '"limits": {k: list(v) for k, v in CONFIG_LIMITS.items()}' in PY)
c("ekran sınırları sunucudan alıp uyguluyor",
  "settingsLimits = data.limits" in HTML and "function applySettingsLimits(" in HTML)
c("alanlara aralık ipucu yazılıyor", "İzin verilen aralık:" in HTML)

# ── 5) Hata mesajı görünür olmalı ────────────────────────────────────────
c("ret sebebi kullanıcıya gösteriliyor (detail)",
  "data.detail || data.message" in HTML)
c("eski 'data.message' tek başına kullanılmıyor",
  "'Ayarlar kaydedilemedi: ' + data.message" not in HTML)
c("reddedilen alan işaretleniyor", "function markSettingFields(" in HTML
  and "markSettingFields(data.keys" in HTML)
c("sunucu reddi yapısal döner (keys/errors)",
  '"keys": [k for k in _anahtarlar if k in CONFIG]' in PY and '"errors": _hatalar' in PY)

# ── 6) Ret durumunda YARIM kayıt olmamalı ────────────────────────────────
_save = re.search(r"async function saveSettings\(\)\s*\{(.*?)\n        \}", HTML, re.S).group(1)
_ret_yeri = _save.find("if (!data.success)")
_chiller_yeri = _save.find("chiller_fcu_ayarlari")
c("ret durumunda Chiller/FCU yazılmıyor",
  _ret_yeri != -1 and _chiller_yeri != -1 and _ret_yeri < _chiller_yeri,
  (_ret_yeri, _chiller_yeri))
c("ret durumunda pencere kapanmıyor", "return;\n                }" in _save)

# ── 7) Kaydetmeden önce ekranda da denetim ───────────────────────────────
c("kaydetmeden önce aralık denetimi var", "function validateSettingsForm(" in HTML
  and "validateSettingsForm(settings)" in _save)

# ── 8) Form doldurma elle listeye bağlı olmamalı ─────────────────────────
_pop = re.search(r"function populateSettingsForm\(settings\)\s*\{(.*?)\n        \}", HTML, re.S).group(1)
c("form doldurma elle anahtar listesi kullanmıyor",
  "settingKeys" not in _pop and "Object.keys(settings)" in _pop)

# ── 9) Son bir ayın eklenen ayarları ekranda mı? ─────────────────────────
# Ön koşul kapısı (v7.9+), konfor ayrımı (v7.7) ve bakım susturması (F3)
# motorda var ama uzun süre ekranda yoktu.
for _k in ("PRESSURE_RUN_MIN_PA", "PRESSURE_FAULT_MAX_PA",
           "SENSOR_VALID_MIN_C", "SENSOR_VALID_MAX_C",
           "COMFORT_DEPARTURE", "COMFORT_CRITICAL_DEPARTURE", "COMFORT_CAPACITY_VALVE",
           "MANUAL_SUPPRESS_HOURS", "DEBOUNCE_OKUMA", "DUZELME_OKUMA",
           "TAKILI_OKUMA", "SKIP_ESKALASYON_GUN", "OAT_BIAS_MAX"):
    c("ekranda: %s" % _k, _k in FORM)

# Ön koşul kapısı ayarları motora GERÇEKTEN geçiyor mu
c("ön koşul kapısına CONFIG aktarılıyor", "cfg=self.config" in PY)
c("elle susturmaya CONFIG aktarılıyor", "elle_ok_suppress(_eq, _comp, kim=" in PY and "cfg=CONFIG" in PY)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
