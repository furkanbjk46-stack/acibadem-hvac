-- ════════════════════════════════════════════════════════════════════════════
-- canli_guc — RLS AÇ (27.10.2026, Supabase Security Advisor: "RLS Disabled in Public")
-- ════════════════════════════════════════════════════════════════════════════
-- Tablo canli_guc_tablo.sql ile RLS KAPALI ve anon'a DELETE dahil tüm izinlerle
-- açılmıştı: GitHub'da açık duran anon anahtarı bilen herkes canlı ölçümleri
-- silebilir / sahte kW yazabilirdi.
--
-- Koddaki gerçek kullanım (rls_guvenlik.sql ile aynı ilke: "ihtiyacı kadar"):
--   · lokasyon cloud_sync._canli_guc_loop → upsert (INSERT + UPDATE; ON CONFLICT
--     DO UPDATE çakışan satırı görebilmek için SELECT de ister)
--   · Synapse (app_merkez, lokasyon_detay) → SELECT
--   · DELETE kodda HİÇ yok → kapatılır.
-- service_role RLS'i bypass eder; bakım scriptleri etkilenmez.
--
-- Güvenli, tekrar çalıştırılabilir. Mevcut akışı bozmaz.
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.canli_guc ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS hvac_canli_guc_sel ON public.canli_guc;
DROP POLICY IF EXISTS hvac_canli_guc_ins ON public.canli_guc;
DROP POLICY IF EXISTS hvac_canli_guc_upd ON public.canli_guc;

CREATE POLICY hvac_canli_guc_sel ON public.canli_guc FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY hvac_canli_guc_ins ON public.canli_guc FOR INSERT TO anon, authenticated WITH CHECK (true);
CREATE POLICY hvac_canli_guc_upd ON public.canli_guc FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);
-- DELETE politikası YOK → anon canlı ölçüm silemez.

-- Fazla verilmiş tablo yetkisini de geri al (politika olmasa da kapı kapalı kalsın)
REVOKE DELETE, TRUNCATE ON TABLE public.canli_guc FROM anon, authenticated;

NOTIFY pgrst, 'reload schema';

-- Kontrol: rowsecurity = true, 3 politika
SELECT relname, relrowsecurity FROM pg_class WHERE relname = 'canli_guc';
SELECT policyname, cmd, roles FROM pg_policies WHERE tablename = 'canli_guc';
