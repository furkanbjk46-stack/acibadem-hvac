# -*- coding: utf-8 -*-
"""RLS ASAMA 1 sonrasi dogrulama.
1) SAHA CALISIYOR MU? (anon ile gerekli islemler)
2) ACIKLAR KAPANDI MI? (anon ile saldiri denemeleri)
Tum test kayitlari __rls_test__ etiketli, sonunda service_role ile temizlenir."""
import json, os, urllib.request, urllib.error, datetime

URL = 'https://qayjwkqnnjjsnnxovhei.supabase.co/rest/v1/'
ANON = 'sb_publishable_m22uNXePA5Av6ocWHJsa5Q_OQFY36Oq'
_s = json.load(open(os.path.join('hvac', 'deneme', 'supabase_secret.json'), encoding='utf-8'))
SVC = _s.get('service_role_key') or list(_s.values())[-1]
TAG = '__rls_test__'


def req(tablo, key, q='', veri=None, method='GET'):
    h = {'apikey': key, 'Authorization': 'Bearer ' + key,
         'Content-Type': 'application/json', 'Prefer': 'return=representation'}
    d = json.dumps(veri).encode() if veri is not None else None
    r = urllib.request.Request(URL + tablo + q, data=d, headers=h, method=method)
    return json.loads(urllib.request.urlopen(r, timeout=15).read().decode() or '[]')


sonuc = []


def dene(grup, etiket, beklenen, tablo, method='GET', q='', veri=None, key=ANON):
    """beklenen: 'IZIN' veya 'RED'"""
    try:
        req(tablo, key, q, veri, method)
        gercek = 'IZIN'
        detay = ''
    except urllib.error.HTTPError as e:
        gercek = 'RED'
        try:
            detay = json.loads(e.read().decode()).get('message', '')[:48]
        except Exception:
            detay = str(e.code)
    ok = (gercek == beklenen)
    sonuc.append((grup, etiket, beklenen, gercek, ok, detay))


# ═══ 1) SAHA CALISMAYA DEVAM EDIYOR MU ═══
dene('SAHA', 'lokasyonlar heartbeat upsert', 'IZIN', 'lokasyonlar', 'POST',
     '', [{'lokasyon_id': TAG, 'durum': 'online'}])
dene('SAHA', 'guncellemeler bekleyen okuma', 'IZIN', 'guncellemeler', 'GET',
     '?durum=eq.bekliyor&select=id&limit=1')
dene('SAHA', 'komutlar bekleyen okuma', 'IZIN', 'komutlar', 'GET', '?select=id&limit=1')
dene('SAHA', 'lokasyon_noktalar okuma', 'IZIN', 'lokasyon_noktalar', 'GET', '?select=nokta_adi&limit=1')
dene('SAHA', 'bakim_kartlari upsert', 'IZIN', 'bakim_kartlari', 'POST', '',
     [{'lokasyon_id': TAG, 'cihaz': 'RLS_TEST', 'kart': {}, 'updated_by': TAG}])
dene('SAHA', 'bildirimler insert', 'IZIN', 'bildirimler', 'POST', '',
     [{'lokasyon': TAG, 'mesaj': 'test', 'gonderen': TAG, 'oncelik': 'dusuk'}])
dene('SAHA', 'lisanslar okuma', 'IZIN', 'lisanslar', 'GET', '?select=lokasyon_id&limit=1')
# komutlar INSERT: ASAMA 1'de anon'a acik (merkez publishable ile yaziyordu),
# ASAMA 2'de kapatilir (merkez service_role'a gecer). Beklenti bayrakla secilir:
#   python rls_dogrula.py            -> ASAMA 1 beklentileri
#   python rls_dogrula.py --asama2   -> ASAMA 2 beklentileri
ASAMA2 = '--asama2' in __import__('sys').argv
dene('SAHA' if not ASAMA2 else 'SALDIRI',
     'komutlar INSERT (anon ile komut uretme)',
     'RED' if ASAMA2 else 'IZIN', 'komutlar', 'POST', '',
     [{'lokasyon': TAG, 'nokta_adi': 'T', 'hedef_deger': 20, 'durum': 'tamamlandi'}])

if ASAMA2:
    # Sadece merkezin kullandigi tablolar anon'a tamamen kapali olmali
    for _t, _v in [('ayarlar', {'key': TAG, 'value': '1'}),
                   ('ai_analizler', {'metin': TAG}),
                   ('dis_hava_log', {'derece': 0, 'kaynak': TAG}),
                   ('oto_mod_log', {'tip': TAG})]:
        dene('SALDIRI', '%s anon erisimi' % _t, 'RED', _t, 'POST', '', [_v])
# GUNLUK VERI GONDERIMI — kritik
dene('SAHA', 'energy_data insert (gunluk)', 'IZIN', 'energy_data', 'POST', '',
     [{'lokasyon_id': TAG, 'Tarih': '2020-01-01'}])
dene('SAHA', 'hvac_summary insert (gunluk)', 'IZIN', 'hvac_summary', 'POST', '',
     [{'lokasyon_id': TAG}])
dene('SAHA', 'hvac_summary delete (gunluk)', 'IZIN', 'hvac_summary', 'DELETE',
     '?lokasyon_id=eq.' + TAG)
dene('SAHA', 'energy_data delete (gunluk)', 'IZIN', 'energy_data', 'DELETE',
     '?lokasyon_id=eq.' + TAG)

# ═══ 2) ACIKLAR KAPANDI MI ═══
dene('SALDIRI', 'guncellemeler INSERT (kod dagitimi)', 'RED', 'guncellemeler', 'POST', '',
     [{'versiyon': '9.9', 'hedef': 'maslak', 'dosyalar': {'x.py': 'zararli'}, 'durum': 'bekliyor'}])
dene('SALDIRI', 'lokasyon_noktalar INSERT', 'RED', 'lokasyon_noktalar', 'POST', '',
     [{'lokasyon': TAG, 'nokta_adi': 'X', 'gateway_ip': '1.1.1.1'}])


def delete_dene(etiket, tablo, alan, satir):
    """DELETE'i SATIR SAYARAK olcer.

    DIKKAT: PostgREST'te RLS bir DELETE'i engellediginde HATA DONMEZ —
    0 satir siler ve HTTP 200 verir. Bu yuzden 'istek basarili oldu'
    kanit degildir; satirin hala durup durmadigina bakilmalidir.
    (Ilk surumde bu gozden kacmis ve 4 tabloda yanlis alarm uretmisti.)"""
    f = '?%s=eq.%s' % (alan, TAG)
    try:
        req(tablo, SVC, f, method='DELETE')
        req(tablo, SVC, '', satir, 'POST')
        once = len(req(tablo, SVC, f + '&select=*'))
        try:
            req(tablo, ANON, f, method='DELETE')
        except urllib.error.HTTPError:
            pass
        sonra = len(req(tablo, SVC, f + '&select=*'))
        korundu = (once == 1 and sonra == 1)
        sonuc.append(('SALDIRI', etiket, 'RED', 'RED' if korundu else 'IZIN', korundu,
                      '' if korundu else 'satir silindi (%d -> %d)' % (once, sonra)))
        req(tablo, SVC, f, method='DELETE')
    except urllib.error.HTTPError as e:
        sonuc.append(('SALDIRI', etiket, 'RED', 'HATA', False, 'test kurulamadi: %d' % e.code))


delete_dene('bildirimler DELETE (iz temizleme)', 'bildirimler', 'gonderen',
            {'lokasyon': TAG, 'mesaj': 'test', 'gonderen': TAG, 'oncelik': 'dusuk'})
delete_dene('lokasyonlar DELETE', 'lokasyonlar', 'lokasyon_id',
            {'lokasyon_id': TAG, 'durum': 'online'})
delete_dene('bakim_kartlari DELETE', 'bakim_kartlari', 'lokasyon_id',
            {'lokasyon_id': TAG, 'cihaz': 'DEL_TEST', 'kart': {}, 'updated_by': TAG})
delete_dene('komutlar DELETE (denetim izi)', 'komutlar', 'lokasyon',
            {'lokasyon': TAG, 'nokta_adi': 'T', 'hedef_deger': 20, 'durum': 'tamamlandi'})

# Replay + yama icerigi degistirme (service ile test satiri kur)
try:
    t = req('guncellemeler', SVC, '', {'versiyon': '0.0-sec', 'hedef': TAG,
                                       'dosyalar': {'a.py': 'orijinal'}, 'durum': 'tamamlandi'}, 'POST')[0]
    dene('SALDIRI', 'guncellemeler REPLAY (tamamlandi->bekliyor)', 'RED', 'guncellemeler',
         'PATCH', '?id=eq.' + t['id'], {'durum': 'bekliyor'})
    dene('SALDIRI', 'guncellemeler yama icerigi degistirme', 'RED', 'guncellemeler',
         'PATCH', '?id=eq.' + t['id'], {'dosyalar': {'a.py': 'ZARARLI KOD'}})
    # service_role kendi is akisini yapabiliyor mu (yayinlama bozulmasin)
    dene('YAYIN', 'service_role yama icerigi guncelleme', 'IZIN', 'guncellemeler',
         'PATCH', '?id=eq.' + t['id'], {'dosyalar': {'a.py': 'yeni'}}, key=SVC)
    dene('YAYIN', 'service_role durum guncelleme', 'IZIN', 'guncellemeler',
         'PATCH', '?id=eq.' + t['id'], {'durum': 'bekliyor'}, key=SVC)
except Exception as e:
    print('test satiri kurulamadi:', e)

# ═══ RAPOR ═══
print("%-8s %-42s %-8s %-8s %s" % ('GRUP', 'TEST', 'BEKLENEN', 'GERCEK', 'SONUC'))
print('-' * 104)
hata = 0
for g, e, b, gr, ok, d in sonuc:
    hata += (not ok)
    print("%-8s %-42s %-8s %-8s %s %s" % (g, e, b, gr, 'OK' if ok else '>>> SORUN', d if not ok else ''))
print("\n%d/%d beklendigi gibi" % (len(sonuc) - hata, len(sonuc)))

# ═══ TEMIZLIK ═══
for tablo, alan in [('lokasyonlar', 'lokasyon_id'), ('bakim_kartlari', 'lokasyon_id'),
                    ('bildirimler', 'gonderen'), ('komutlar', 'lokasyon'),
                    ('guncellemeler', 'hedef'), ('energy_data', 'lokasyon_id'),
                    ('hvac_summary', 'lokasyon_id')]:
    try:
        req(tablo, SVC, '?%s=eq.%s' % (alan, TAG), method='DELETE')
    except Exception:
        pass
print("temizlik tamam")
