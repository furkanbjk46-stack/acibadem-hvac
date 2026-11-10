#!/usr/bin/env python3
"""sql_durumu.py testi (Yönetim > SQL (canlı) sekmesinin hesap kısmı). Ağ gerekmez."""
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sql_durumu as S  # noqa: E402

gecti = kaldi = 0


def c(ad, kosul, ek=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓ " + ad)
    else:
        kaldi += 1
        print("  ✗ %s  %s" % (ad, ek))


SIMDI = datetime(2026, 11, 10, 14, 0, tzinfo=S.IST)

print("zaman")
c("timestamptz metni (+00) → İstanbul", S.zaman("2026-11-10 10:50:51+00") == datetime(2026, 11, 10, 13, 50, 51, tzinfo=S.IST))
c("ISO Z → İstanbul", S.zaman("2026-11-10T10:00:00Z").hour == 13)
c("ISO +00:00 mikro saniyeli", S.zaman("2026-11-10T07:52:29.871563+00:00").hour == 10)
c("saat dilimsiz (ping_zamani) İstanbul kabul edilir", S.zaman("2026-11-10T13:51:34.990996").hour == 13)
c("yalnız tarih → o günün sonu", S.zaman("2026-11-09") == datetime(2026, 11, 9, 23, 59, tzinfo=S.IST))
c("boş / bozuk → None", S.zaman(None) is None and S.zaman("bozuk") is None)

print("once / calisma_suresi")
c("dakika", S.once(SIMDI - timedelta(minutes=5), SIMDI) == "5 dk önce")
c("saat (virgüllü)", S.once(SIMDI - timedelta(minutes=150), SIMDI) == "2,5 saat önce")
c("gün", S.once(SIMDI - timedelta(days=3), SIMDI) == "3 gün önce")
c("çalışma süresi (03:47 UTC = 06:47 İstanbul)", S.calisma_suresi("2026-10-15T03:47:31+00:00", SIMDI) == "26 gün 7 saat",
  S.calisma_suresi("2026-10-15T03:47:31+00:00", SIMDI))


def veri(**ek):
    v = {"tablolar": [
        {"tablo": "canli_guc", "rls": True, "politika": 6, "son_kayit": "2026-11-10 10:58:00+00",
         "satir": 32, "sutun": 6},
        {"tablo": "energy_data", "rls": True, "politika": 6, "son_kayit": "2026-11-09", "satir": 1237,
         "sutun": 75},
        {"tablo": "ai_analizler", "rls": True, "politika": 0, "son_kayit": "2026-11-09 09:14:28+00"},
        {"tablo": "bos", "rls": True, "politika": 1, "son_kayit": None},
    ], "bekleyen_kilit": 0, "istatistik": {"kilitlenme": 0},
        "baglantilar": [{"kullanici": "authenticator", "uygulama": "PostgREST 16.5", "adet": 3},
                        {"kullanici": "canliizlemedev", "uygulama": "psql", "adet": 1}]}
    v.update(ek)
    return v


YEDEK = [{"ad": "synapse_db_20261110_013001.dump", "bayt": 1398781,
          "zaman": datetime(2026, 11, 10, 1, 30, 1, tzinfo=S.IST)}]

print("uyarilar")
u = S.uyarilar(veri(), YEDEK, (14e9, 96e9, 78e9), SIMDI)
c("sağlıklı durumda tek 'iyi' satırı", [x[0] for x in u] == ["iyi"], u)
c("'iyi' metni yedeği yalnızca görüldüyse söyler",
  "yedeği" in u[0][2] and "yedeği" not in S.uyarilar(veri(), None, None, SIMDI)[0][2])
v = veri()
v["tablolar"][0]["rls"] = False
c("RLS kapalı tablo → kritik", any(x[0] == "kritik" and "canli_guc" in x[1] for x in S.uyarilar(v, YEDEK, None, SIMDI)))
v = veri()
v["tablolar"][0]["son_kayit"] = "2026-11-10 10:30:00+00"
c("canlı veri 30 dk eski → dikkat", any("Canlı güç" in x[1] for x in S.uyarilar(v, YEDEK, None, SIMDI)))
v = veri()
v["tablolar"][1]["son_kayit"] = "2026-11-07"
c("günlük enerji 3 gün eski → dikkat", any("enerji" in x[1] for x in S.uyarilar(v, YEDEK, None, SIMDI)))
c("dünün enerji satırı normal", not any("enerji" in x[1] for x in S.uyarilar(veri(), YEDEK, None, SIMDI)))
c("bekleyen kilit → dikkat", any("kilit" in x[1] for x in S.uyarilar(veri(bekleyen_kilit=2), YEDEK, None, SIMDI)))
_eski = [dict(YEDEK[0], zaman=SIMDI - timedelta(hours=30))]
c("30 saatlik yedek → dikkat", any(x[0] == "dikkat" and "yedeği" in x[1] for x in S.uyarilar(veri(), _eski, None, SIMDI)))
_cok = [dict(YEDEK[0], zaman=SIMDI - timedelta(hours=60))]
c("60 saatlik yedek → kritik", any(x[0] == "kritik" and "yedeği" in x[1] for x in S.uyarilar(veri(), _cok, None, SIMDI)))
c("yedek klasörü boş → dikkat", any("görülemedi" in x[1] for x in S.uyarilar(veri(), [], None, SIMDI)))
c("yedek bilinmiyorsa (None) uyarı yok", not any("yedek" in x[1].lower() for x in S.uyarilar(veri(), None, None, SIMDI)))
c("disk %92 → kritik", any(x[0] == "kritik" and "disk" in x[1] for x in S.uyarilar(veri(), YEDEK, (92, 100, 8), SIMDI)))
c("disk %85 → dikkat", any(x[0] == "dikkat" and "disk" in x[1] for x in S.uyarilar(veri(), YEDEK, (85, 100, 15), SIMDI)))

print("tablo_satirlari")
ts = S.tablo_satirlari(veri(), SIMDI)
c("son kayda göre sıralı, kaydı olmayan en sonda", [t["Tablo"] for t in ts] == ["canli_guc", "energy_data", "ai_analizler", "bos"],
  [t["Tablo"] for t in ts])
c("zaman damgalı tablo: 'dk önce'", ts[0]["Ne zaman"] == "2 dk önce" and ts[0]["Son kayıt"] == "10.11 13:58", ts[0])
c("tarih sütunlu tablo: 'dün'", ts[1]["Ne zaman"] == "dün" and ts[1]["Son kayıt"] == "09.11.2026", ts[1])
c("kuralsız RLS tablo 'yalnız merkez'", ts[2]["Erişim"] == "🔒 yalnız merkez")
c("iç alan (_z) gösterilmez", all("_z" not in t for t in ts))

print("baglanti_ozeti")
c("toplam ve dağılım", S.baglanti_ozeti(veri()) == (4, "PostgREST 3, psql 1"), S.baglanti_ozeti(veri()))

print("yedekler / disk")
with tempfile.TemporaryDirectory() as d:
    for ad in ("synapse_db_20261109_013001.dump", "synapse_db_20261110_013001.dump",
               "synapse_TAM_20261110_013001.tar.gz", "enerji_db_20261108_020001.dump"):
        open(os.path.join(d, ad), "wb").write(b"x" * 10)
    y = S.yedekler(d)
    c("yalnız synapse_db dökümleri, yeniden eskiye", [x["ad"] for x in y] ==
      ["synapse_db_20261110_013001.dump", "synapse_db_20261109_013001.dump"], y)
    c("boyut ve saat okunur", y[0]["bayt"] == 10 and y[0]["zaman"].hour == 1)
c("olmayan klasör → []", S.yedekler(os.path.join(tempfile.gettempdir(), "yok_boyle_klasor")) == [])
c("disk okunur", S.disk(os.path.dirname(os.path.abspath(__file__))) is not None)

print("oku (sunucusuz)")
_v, _ms, _h = S.oku("http://127.0.0.1:9", "x", zaman_asimi=2)
c("ulaşılamayan sunucu → bağlantı hatası, istisna yok", _v is None and _h.startswith("baglanti"), _h)

print("\n%d geçti, %d kaldı" % (gecti, kaldi))
sys.exit(1 if kaldi else 0)
