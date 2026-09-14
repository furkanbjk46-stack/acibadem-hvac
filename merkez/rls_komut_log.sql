-- ============================================================================
--  OTO-SET KOMUT LOGU — komutlar tablosu RLS
--  Supabase Dashboard → SQL Editor → yapıştır → Run
-- ============================================================================
--
--  NEDEN:
--  Oto-set lokasyona taşınınca (v7.0) setler doğrudan BACnet'e yazılmaya
--  başladı ve "hangi noktaya kaç derece gitti, cihaz kabul etti mi" bilgisi
--  Ayarlar → Uzaktan Kontrol → Son komutlar listesinden kayboldu.
--  Lokasyon artık her geçişten SONRA nokta başına bir satır ekliyor.
--
--  GÜVENLİK — iki kural:
--
--  1) INSERT: lokasyon anahtarı (anon, GitHub'da açık) YALNIZCA
--     sonuçlanmış ("tamamlandi" / "hata" / "dogrulanamadi") ve "OTO-SET"
--     önekli kayıt ekleyebilir. "bekliyor" kayıt EKLEYEMEZ — lokasyon yalnızca
--     "bekliyor" komutları sahaya yazdığı için bu yoldan sahaya komut
--     gönderilemez. Kötü niyetli biri en fazla sahte log satırı ekleyebilir.
--
--  2) UPDATE (mevcut açığı KAPATIR): anon güncelleme şu an sınırsız. Açık
--     anahtarla eski bir komut "bekliyor"a geri çekilip hedef değeri
--     değiştirilebilir ve lokasyon onu sahaya yazar. Artık anon yalnızca
--     "bekliyor" durumundaki bir satırı SONUÇLANMIŞ bir duruma çekebilir
--     (lokasyonun komutu işledikten sonra yaptığı tam olarak budur).
--     1. kuraldaki log satırları da bu yüzden sonradan "bekliyor"a çevrilemez.
--
--  Merkez portal service_role kullandığı için RLS'ten etkilenmez: elle komut
--  göndermek ("bekliyor" ekleme) aynen çalışır.
-- ============================================================================

-- 1) Oto-set log satırı ekleme
DROP POLICY IF EXISTS hvac_komutlar_log_ins ON public.komutlar;
CREATE POLICY hvac_komutlar_log_ins ON public.komutlar
    FOR INSERT TO anon
    WITH CHECK (
        durum IN ('tamamlandi', 'hata', 'dogrulanamadi')
        AND hata_mesaji LIKE 'OTO-SET%'
    );

-- 2) Güncellemeyi "bekliyor → sonuçlanmış" yönüne daralt
DROP POLICY IF EXISTS hvac_komutlar_upd ON public.komutlar;
CREATE POLICY hvac_komutlar_upd ON public.komutlar
    FOR UPDATE TO anon
    USING (durum = 'bekliyor')
    WITH CHECK (durum IN ('tamamlandi', 'hata', 'dogrulanamadi', 'suresi_doldu'));

-- ============================================================================
--  DOĞRULAMA — çalıştırdıktan sonra bunu koş
-- ============================================================================
SELECT policyname, cmd, roles, qual, with_check
FROM pg_policies
WHERE schemaname = 'public' AND tablename = 'komutlar'
ORDER BY cmd, policyname;

-- Beklenen:
--   hvac_komutlar_log_ins  INSERT  {anon}  with_check: durum IN (...) AND hata_mesaji LIKE 'OTO-SET%'
--   hvac_komutlar_sel      SELECT  {anon}
--   hvac_komutlar_upd      UPDATE  {anon}  qual: durum = 'bekliyor'  with_check: durum IN (...)
