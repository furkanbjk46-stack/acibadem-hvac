-- ============================================================================
--  OTO-SET LOKASYONA TASINDI — GEREKEN RLS IZINLERI
--  Supabase Dashboard → SQL Editor → yapıştır → Run
-- ============================================================================
--
--  NEDEN GEREKLİ:
--  Oto-set kararı artık merkez portalda değil, lokasyon PC'sinde veriliyor
--  (Streamlit Cloud uygulamayı uyuttuğu için setler saatinde gitmiyordu).
--  Lokasyon anon/publishable anahtarla çalışıyor ve şu iki şeye ihtiyacı var:
--
--    1) KURALI OKUMAK   : oto_set_aktif, oto_gunduz_saat, oto_gece_saat
--    2) DENETIM IZI     : oto_mod_log'a geçiş kaydı yazmak
--
--  GÜVENLİK: Yetkiler DAR tutuldu.
--    * ayarlar tablosunda yalnızca 'oto_' ile başlayan satırlar OKUNABİLİR;
--      m2_degerler gibi diğer ayarlar kapalı kalır. YAZMA verilmez —
--      lokasyon kendi durumunu yerel dosyada tutuyor (configs/oto_set_durum.json).
--    * komutlar tablosuna anon INSERT AÇILMADI. Lokasyon setpoint'i doğrudan
--      BACnet'e yazıyor; GitHub'da açık olan anahtarla hastane BMS'ine komut
--      yazma açığı KAPALI KALIYOR.
-- ============================================================================

-- 1) Kural okuma — yalnızca oto_ ile başlayan ayarlar
DROP POLICY IF EXISTS hvac_ayarlar_oto_sel ON public.ayarlar;
CREATE POLICY hvac_ayarlar_oto_sel ON public.ayarlar
    FOR SELECT TO anon
    USING (key LIKE 'oto\_%');

-- 2) Denetim izi — geçiş kaydı yazma
DROP POLICY IF EXISTS hvac_otomod_ins ON public.oto_mod_log;
CREATE POLICY hvac_otomod_ins ON public.oto_mod_log
    FOR INSERT TO anon
    WITH CHECK (true);

-- Merkez portal service_role kullandığı için RLS'i bypass eder;
-- oto_mod_log okuması ve ayarlar yazması (saat değiştirme) etkilenmez.

-- ============================================================================
--  DOĞRULAMA — çalıştırdıktan sonra bunu koş
-- ============================================================================
SELECT tablename, policyname, cmd, roles
FROM pg_policies
WHERE schemaname = 'public' AND tablename IN ('ayarlar', 'oto_mod_log', 'komutlar')
ORDER BY tablename, cmd, policyname;

-- Beklenen:
--   ayarlar      : hvac_ayarlar_oto_sel  SELECT  {anon}
--   oto_mod_log  : hvac_otomod_ins       INSERT  {anon}
--   komutlar     : SELECT + UPDATE var, INSERT YOK  (guvenlik icin boyle kalmali)
