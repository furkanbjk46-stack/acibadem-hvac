# -*- coding: utf-8 -*-
import ast, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for f in ['giris.py', 'app_merkez.py']:
    ast.parse(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), f),
                   encoding='utf-8').read())
    print('SYNTAX OK  ', f)

import giris

T = []
def c(ad, kosul): T.append((ad, bool(kosul)))

h = giris.parola_hash_uret('test1234')
c('hash formati pbkdf2_sha256', h.startswith('pbkdf2_sha256$200000$'))
c('dogru parola kabul', giris.parola_dogrula('test1234', h))
c('yanlis parola RED', not giris.parola_dogrula('test1233', h))
c('bos parola RED', not giris.parola_dogrula('', h))
c('bozuk kayit RED (cokmeden)', not giris.parola_dogrula('x', 'sacma'))
c('bos kayit RED', not giris.parola_dogrula('x', ''))
c('tuz rastgele (ayni parola farkli hash)',
  giris.parola_hash_uret('a') != giris.parola_hash_uret('a'))
c('hash icinde duz parola YOK', 'test1234' not in h)

# Kilit mekanizmasi
giris._durum['hata'] = 0
c('baslangicta kilit yok', not giris._kilitli_mi()[0])
giris._durum['hata'] = giris.KILIT_ESIGI
giris._durum['son_hata'] = time.time()
kilitli, kalan = giris._kilitli_mi()
c('esik asilinca kilit devreye girer', kilitli and kalan > 0)
giris._durum['son_hata'] = time.time() - giris.KILIT_SURE_SN - 1
c('sure dolunca kilit acilir', not giris._kilitli_mi()[0])
giris._durum['hata'] = 0

# Artan gecikme gercekten bekletiyor mu
giris._durum['hata'] = 4
t0 = time.time(); giris._hata_kaydet(); gecen = time.time() - t0
c('hatali denemede gecikme uygulanir (%.2f sn)' % gecen, gecen > 0.5)
giris._durum['hata'] = 0

# Arka plan gorseli
c('arka plan gorseli mevcut', os.path.exists(giris._ARKAPLAN))

hata = sum(1 for _, ok in T if not ok)
print()
for ad, ok in T:
    print(('PASS ' if ok else 'FAIL ') + ad)
print('\n%d/%d PASS' % (len(T) - hata, len(T)))
