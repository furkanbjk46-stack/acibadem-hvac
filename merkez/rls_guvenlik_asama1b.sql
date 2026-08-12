-- ============================================================================
--  AŞAMA 1B — AŞAMA 1 SONRASI DÜZELTMELER
--  Supabase → SQL Editor → yapıştır → Run
-- ============================================================================
--
--  AŞAMA 1 sonrası yapılan doğrulama testinde iki sorun tespit edildi:
--
--  SORUN 1) hvac_summary'ye anon INSERT engellendi → lokasyonların GÜNLÜK
--           HVAC özet gönderimi çalışmıyor.
--           Sebep: AŞAMA 1'deki temizlik bloğu 'hvac_%' desenine uyan
--           politikaları siliyordu; hvac_summary'nin kendi politikaları da
--           bu desene uyduğu için yanlışlıkla silindi.
--           (energy_data etkilenmedi, günlük enerji gönderimi çalışıyor.)
--
--  SORUN 2) lokasyonlar / komutlar / bakim_kartlari / bildirimler üzerinde
--           anon DELETE HÂLÂ AÇIK.
--           Sebep: bu tablolarda önceden var olan izin verici (PERMISSIVE)
--           politikalar duruyor. PostgreSQL politikaları OR'lar — yani
--           "DELETE politikası yazmamak" yetmiyor, eski geniş politikanın
--           kaldırılması gerekiyor.
-- ============================================================================


-- ── SORUN 1: hvac_summary politikalarını geri yükle ───────────────────────
-- cloud_sync.sync_hvac_summary(): önce lokasyonun satırlarını DELETE eder,
-- sonra yeni özeti batch INSERT eder. Merkez portal da okur.
DROP POLICY IF EXISTS hvac_summary_sel ON public.hvac_summary;
DROP POLICY IF EXISTS hvac_summary_ins ON public.hvac_summary;
DROP POLICY IF EXISTS hvac_summary_del ON public.hvac_summary;

CREATE POLICY hvac_summary_sel ON public.hvac_summary FOR SELECT TO anon USING (true);
CREATE POLICY hvac_summary_ins ON public.hvac_summary FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY hvac_summary_del ON public.hvac_summary FOR DELETE TO anon USING (true);
-- NOT: Buradaki DELETE bilinçlidir — günlük özet "sil ve yeniden yaz"
-- mantığıyla çalışır. Veri kaybı riski düşüktür: kaynak CSV lokasyondadır
-- ve her gün yeniden gönderilir.


-- ── SORUN 2: eski geniş politikaları kaldır ───────────────────────────────
-- Bu 4 tabloda anon'un DELETE yetkisi olmamalı (denetim izi + veri koruması).
-- AŞAMA 1'de yazdığımız hvac_* politikaları SELECT/INSERT/UPDATE ihtiyacını
-- zaten karşılıyor; dolayısıyla eski geniş politikalar güvenle kaldırılabilir.
--
-- Aşağıdaki blok, bu tablolarda DELETE yetkisi veren (FOR ALL veya FOR DELETE)
-- ve BİZE AİT OLMAYAN (hvac_ ile başlamayan) politikaları siler.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT policyname, tablename
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename IN ('lokasyonlar', 'komutlar', 'bakim_kartlari', 'bildirimler')
      AND cmd IN ('ALL', 'DELETE')
      AND policyname NOT LIKE 'hvac\_%'
  LOOP
    RAISE NOTICE 'Kaldiriliyor: %.% -> %', 'public', r.tablename, r.policyname;
    EXECUTE format('DROP POLICY %I ON public.%I', r.policyname, r.tablename);
  END LOOP;
END $$;


-- ── DOĞRULAMA: kalan politikalar ──────────────────────────────────────────
-- Beklenen: asagidaki tablolarda 'DELETE' veya 'ALL' satiri GORUNMEMELI
SELECT tablename, policyname, cmd, roles
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('lokasyonlar', 'komutlar', 'bakim_kartlari', 'bildirimler', 'hvac_summary')
ORDER BY tablename, cmd, policyname;
