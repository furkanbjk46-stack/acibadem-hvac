# -*- coding: utf-8 -*-
"""Synapse lisans yönetimi (008): bekleyen talepler, uyarı metni, onay çağrısı. Ağ yok."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import lisans_yonetim as LY  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


T = [{"id": "1", "lokasyon_id": "atasehir", "makine_id": "UUID-AAAA", "makine_adi": "<script>x</script>",
      "durum": "bekliyor"},
     {"id": "2", "lokasyon_id": "maslak", "makine_id": "UUID-B", "makine_adi": "PC", "durum": "onaylandi"},
     {"id": "3", "lokasyon_id": "yanlis_ad", "makine_id": "UUID-C", "makine_adi": None, "durum": "bekliyor"}]
H = {"atasehir": {"kisa": "ATAŞEHİR", "isim": "Acıbadem Ataşehir"}, "maslak": {"kisa": "MASLAK"}}

c("yalnız bekleyen talepler", [t["id"] for t in LY.bekleyenler(T)] == ["1", "3"])
u = LY.canli_uyarilar(T, H)
c("ana sayfa uyarısı lokasyon başına", set(u) == {"atasehir", "yanlis_ad"}, u)
c("PC'den gelen ad HTML olarak basılmaz (kaçışlanır)",
  "<script>" not in u["atasehir"][0][1] and "&lt;script&gt;" in u["atasehir"][0][1], u["atasehir"])
c("listede olmayan lokasyon da görünür (kimlik yanlış yazılmış olabilir)", "yanlis_ad" in u["yanlis_ad"][0][1])
c("bilinen sonuç kodları anlaşılır mesaj", LY.mesaj("onaylandi")[0] == "ok" and LY.mesaj("sifre_yanlis")[0] == "hata")
c("bilinmeyen sonuç hata olarak gösterilir", LY.mesaj("hata: HTTP 404")[0] == "hata")

cagri = []
LY._istek = lambda url, key, yol, veri=None, zaman=20: (cagri.append((yol, veri)), "onaylandi")[1]
r = LY.karar_ver("https://x", "k", "1", "onayla", "gizli-sifre")
c("onay veritabanı işlevine gider (şifre parametre olarak)",
  r == "onaylandi" and cagri[-1] == ("rpc/lisans_karar", {"p_talep": "1", "p_karar": "onayla",
                                                         "p_sifre": "gizli-sifre", "p_not": None}), cagri)
LY.aktiflik("https://x", "k", "L1", False, "s")
c("pasife alma işlevi", cagri[-1] == ("rpc/lisans_aktiflik", {"p_lisans": "L1", "p_aktif": False, "p_sifre": "s"}))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
