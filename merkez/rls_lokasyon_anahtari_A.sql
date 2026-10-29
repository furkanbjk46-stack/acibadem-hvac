-- ════════════════════════════════════════════════════════════════════════════
-- LOKASYON ANAHTARI — AŞAMA A (29.10.2026) · yalnız EKLER, mevcut hiçbir şeyi bozmaz
-- ════════════════════════════════════════════════════════════════════════════
-- Her lokasyon PC'si kendi imzalı anahtarıyla (JWT: role=authenticated,
-- lokasyon_id=<lokasyon>) bağlanacak. Bu politikalar o anahtara YALNIZ KENDİ
-- lokasyonunun satırlarında izin verir. Anon politikalarına DOKUNULMAZ —
-- lokasyonlar anahtara geçene kadar her şey bugünkü gibi çalışır.
-- (Aşama D'de anon yazma politikaları kaldırılacak.)
--
-- Tablo → lokasyon sütunu: energy_data/hvac_summary/bakim_kartlari/canli_guc/
-- lokasyonlar/lisanslar → lokasyon_id · komutlar/lokasyon_noktalar/bildirimler
-- → lokasyon · guncellemeler → hedef · oto_mod_log → lokasyonlar
-- Tekrar çalıştırılabilir. service_role etkilenmez.
-- 29.10.2026'da Supabase'de çalıştırıldı (29 politika); Maslak anahtarıyla
-- canlı denendi: kendi satırı okunur/yazılır, başka lokasyon görünmez/yazılamaz.
-- ════════════════════════════════════════════════════════════════════════════

-- Anahtardaki lokasyon (yoksa NULL → hiçbir satıra uymaz)
CREATE OR REPLACE FUNCTION public.hvac_lok() RETURNS text
LANGUAGE sql STABLE AS $$ SELECT nullif(auth.jwt() ->> 'lokasyon_id', '') $$;

-- Önceki A çalıştırmasının politikalarını temizle (yalnız hvac_lok_ önekli)
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT tablename, policyname FROM pg_policies
           WHERE schemaname = 'public' AND policyname LIKE 'hvac\_lok\_%'
  LOOP
    EXECUTE format('DROP POLICY %I ON public.%I', r.policyname, r.tablename);
  END LOOP;
END $$;

-- canli_guc: rls_canli_guc.sql authenticated'a TÜM satırları açmıştı → anon'a indir
DROP POLICY IF EXISTS hvac_canli_guc_sel ON public.canli_guc;
DROP POLICY IF EXISTS hvac_canli_guc_ins ON public.canli_guc;
DROP POLICY IF EXISTS hvac_canli_guc_upd ON public.canli_guc;
CREATE POLICY hvac_canli_guc_sel ON public.canli_guc FOR SELECT TO anon USING (true);
CREATE POLICY hvac_canli_guc_ins ON public.canli_guc FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY hvac_canli_guc_upd ON public.canli_guc FOR UPDATE TO anon USING (true) WITH CHECK (true);

-- ── lokasyon_id sütunlu tablolar: kendi satırında tam yetki ──
CREATE POLICY hvac_lok_energy_sel ON public.energy_data FOR SELECT TO authenticated USING (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_energy_ins ON public.energy_data FOR INSERT TO authenticated WITH CHECK (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_energy_upd ON public.energy_data FOR UPDATE TO authenticated USING (lokasyon_id = hvac_lok()) WITH CHECK (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_energy_del ON public.energy_data FOR DELETE TO authenticated USING (lokasyon_id = hvac_lok());

CREATE POLICY hvac_lok_hvacsum_sel ON public.hvac_summary FOR SELECT TO authenticated USING (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_hvacsum_ins ON public.hvac_summary FOR INSERT TO authenticated WITH CHECK (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_hvacsum_del ON public.hvac_summary FOR DELETE TO authenticated USING (lokasyon_id = hvac_lok());

CREATE POLICY hvac_lok_kart_sel ON public.bakim_kartlari FOR SELECT TO authenticated USING (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_kart_ins ON public.bakim_kartlari FOR INSERT TO authenticated WITH CHECK (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_kart_upd ON public.bakim_kartlari FOR UPDATE TO authenticated USING (lokasyon_id = hvac_lok()) WITH CHECK (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_kart_del ON public.bakim_kartlari FOR DELETE TO authenticated USING (lokasyon_id = hvac_lok());

CREATE POLICY hvac_lok_canli_sel ON public.canli_guc FOR SELECT TO authenticated USING (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_canli_ins ON public.canli_guc FOR INSERT TO authenticated WITH CHECK (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_canli_upd ON public.canli_guc FOR UPDATE TO authenticated USING (lokasyon_id = hvac_lok()) WITH CHECK (lokasyon_id = hvac_lok());

CREATE POLICY hvac_lok_lok_sel ON public.lokasyonlar FOR SELECT TO authenticated USING (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_lok_ins ON public.lokasyonlar FOR INSERT TO authenticated WITH CHECK (lokasyon_id = hvac_lok());
CREATE POLICY hvac_lok_lok_upd ON public.lokasyonlar FOR UPDATE TO authenticated USING (lokasyon_id = hvac_lok()) WITH CHECK (lokasyon_id = hvac_lok());

CREATE POLICY hvac_lok_lisans_sel ON public.lisanslar FOR SELECT TO authenticated USING (lokasyon_id = hvac_lok());

-- ── lokasyon sütunlu tablolar ──
CREATE POLICY hvac_lok_komut_sel ON public.komutlar FOR SELECT TO authenticated USING (lokasyon = hvac_lok());
CREATE POLICY hvac_lok_komut_ins ON public.komutlar FOR INSERT TO authenticated WITH CHECK (lokasyon = hvac_lok());
CREATE POLICY hvac_lok_komut_upd ON public.komutlar FOR UPDATE TO authenticated USING (lokasyon = hvac_lok()) WITH CHECK (lokasyon = hvac_lok());

CREATE POLICY hvac_lok_nokta_sel ON public.lokasyon_noktalar FOR SELECT TO authenticated USING (lokasyon = hvac_lok());

CREATE POLICY hvac_lok_bildirim_sel ON public.bildirimler FOR SELECT TO authenticated USING (lokasyon IN (hvac_lok(), 'all'));
CREATE POLICY hvac_lok_bildirim_ins ON public.bildirimler FOR INSERT TO authenticated WITH CHECK (lokasyon = hvac_lok());
CREATE POLICY hvac_lok_bildirim_upd ON public.bildirimler FOR UPDATE TO authenticated USING (lokasyon IN (hvac_lok(), 'all')) WITH CHECK (lokasyon IN (hvac_lok(), 'all'));

-- ── guncellemeler: kendi (ya da 'all') yamasını okur, durumunu yazar ──
--    (içerik/versiyon değişimi hvac_guncelleme_koru tetikleyicisiyle zaten engelli)
CREATE POLICY hvac_lok_yama_sel ON public.guncellemeler FOR SELECT TO authenticated USING (hedef IN (hvac_lok(), 'all'));
CREATE POLICY hvac_lok_yama_upd ON public.guncellemeler FOR UPDATE TO authenticated USING (hedef IN (hvac_lok(), 'all')) WITH CHECK (hedef IN (hvac_lok(), 'all'));

-- ── oto_mod_log: kendi kaydını ekler ──
CREATE POLICY hvac_lok_otolog_ins ON public.oto_mod_log FOR INSERT TO authenticated WITH CHECK (lokasyonlar = hvac_lok());

-- ── ayarlar: OTO SET ayarlarını okur (global) ──
CREATE POLICY hvac_lok_ayar_sel ON public.ayarlar FOR SELECT TO authenticated USING (key LIKE 'oto\_%');

-- Tablo yetkileri (politikalar ayrıca süzer)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.energy_data, public.hvac_summary, public.bakim_kartlari TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.canli_guc, public.lokasyonlar, public.komutlar, public.bildirimler TO authenticated;
GRANT SELECT, UPDATE ON public.guncellemeler TO authenticated;
GRANT SELECT ON public.lokasyon_noktalar, public.lisanslar, public.ayarlar TO authenticated;
GRANT INSERT ON public.oto_mod_log TO authenticated;

NOTIFY pgrst, 'reload schema';

-- Kontrol: eklenen politika sayısı (beklenen 29)
SELECT count(*) AS hvac_lok_politika FROM pg_policies WHERE schemaname = 'public' AND policyname LIKE 'hvac\_lok\_%';
