# -*- coding: utf-8 -*-
"""Oturum jetonu guvenlik testleri — cerezle gelen jeton uydurulabiliyor mu?
   python merkez/test_jeton.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import giris

H = giris.parola_hash_uret('DogruParola123')
H2 = giris.parola_hash_uret('BaskaParola456')   # parola degistirilmis hali

T = []
def c(ad, kosul): T.append((ad, bool(kosul)))

# ── Normal akis ──
j = giris._jeton_uret(H, 3600)
c('gecerli jeton kabul edilir', giris._jeton_gecerli(j, H))
c('jeton icinde parola YOK', 'DogruParola123' not in j)
c('jeton icinde karma YOK', H.split('$')[-1] not in j)

# ── Saldiri denemeleri ──
son, rast, imza = j.split('.')
c('imza degistirilirse RED',
  not giris._jeton_gecerli('%s.%s.%s' % (son, rast, 'f' * 64), H))
c('sure uzatilirsa (imza eski) RED',
  not giris._jeton_gecerli('%d.%s.%s' % (int(son) + 99999, rast, imza), H))
c('rastgele deger degistirilirse RED',
  not giris._jeton_gecerli('%s.%s.%s' % (son, 'deadbeef', imza), H))
c('imzasiz uydurma jeton RED',
  not giris._jeton_gecerli('%d.abc.xyz' % (int(time.time()) + 3600), H))
c('bos jeton RED', not giris._jeton_gecerli('', H))
c('sacma metin RED (cokmeden)', not giris._jeton_gecerli('merhaba', H))
c('sadece imza kismi RED', not giris._jeton_gecerli(imza, H))

# ── Sure dolmasi ──
eski = giris._jeton_uret(H, -1)
c('suresi dolmus jeton RED', not giris._jeton_gecerli(eski, H))

# ── Parola degisimi eski oturumlari dusurur ──
c('parola degisince eski jeton RED', not giris._jeton_gecerli(j, H2))

# ── Baska bir kurulumun jetonu gecmez ──
c('farkli karma ile uretilen jeton RED',
  not giris._jeton_gecerli(giris._jeton_uret(H2, 3600), H))

# ── Jetonlar birbirinin ayni olmamali ──
c('her jeton benzersiz', giris._jeton_uret(H, 60) != giris._jeton_uret(H, 60))

hata = sum(1 for _, ok in T if not ok)
for ad, ok in T:
    print(('PASS ' if ok else 'FAIL ') + ad)
print('\n%d/%d PASS' % (len(T) - hata, len(T)))
sys.exit(1 if hata else 0)
