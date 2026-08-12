-- ============================================================================
--  SUPABASE RLS GÜVENLİK POLİTİKALARI — HVAC & Enerji Portalı
--  Supabase Dashboard → SQL Editor → yapıştır → Run
-- ============================================================================
--
--  NEDEN GEREKLİ:
--  publishable (anon) anahtar merkez_config.json içinde ve GitHub'da AÇIK.
--  RLS kapalı olduğu için bu anahtarı bilen herkes tablolara yazabiliyordu.
--  Test edilen açıklar: komutlar'a INSERT (hastane BMS'ine setpoint yazma),
--  bakim_kartlari/lokasyonlar UPDATE, bildirimler DELETE (iz temizleme).
--
--  TASARIM İLKESİ:
--  Sahadaki lokasyon PC'leri ve merkez portal anon anahtarla çalışıyor.
--  Bu yüzden anon'a "ihtiyacı olan kadar" izin verilir, fazlası kapatılır.
--  service_role RLS'i otomatik bypass eder → yayınlama/bakım scriptleri
--  (guncelleme_yayinla.py, temizle.py) etkilenmez, politika gerekmez.
--
--  AŞAMA 1  : Şimdi çalıştırılır. Mevcut hiçbir özelliği bozmaz.
--  AŞAMA 2  : Streamlit secrets service_role'a çevrildikten SONRA çalıştırılır.
-- ============================================================================


-- ####################  AŞAMA 1 — ŞİMDİ ÇALIŞTIR  ####################
-- Bozulma riski YOK: her politika, koddaki mevcut kullanıma birebir karşılık gelir.

-- ── 1) RLS'i tüm tablolarda aç ────────────────────────────────────────────
ALTER TABLE public.lokasyonlar        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guncellemeler      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.komutlar           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lokasyon_noktalar  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bakim_kartlari     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bildirimler        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_analizler       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dis_hava_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.oto_mod_log        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ayarlar            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lisanslar          ENABLE ROW LEVEL SECURITY;

-- Eski/çakışan politikaları temizle (tekrar çalıştırılabilir olsun diye)
--
-- DİKKAT: Filtre yalnızca AŞAĞIDAKİ TABLO LİSTESİYLE sınırlıdır.
-- İlk sürümde sadece 'hvac_%' desenine bakılıyordu; bu, adı tesadüfen aynı
-- desene uyan public.hvac_summary tablosunun KENDİ politikalarını da sildi ve
-- lokasyonların günlük HVAC özet gönderimini bozdu (rls_guvenlik_asama1b.sql
-- ile geri yüklendi). Tablo listesi olmadan bu bloğu çalıştırma.
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT schemaname, tablename, policyname FROM pg_policies
           WHERE schemaname = 'public'
             AND policyname LIKE 'hvac\_%'
             AND tablename IN ('lokasyonlar','guncellemeler','komutlar','lokasyon_noktalar',
                               'bakim_kartlari','bildirimler','ai_analizler','dis_hava_log',
                               'oto_mod_log','ayarlar','lisanslar')
  LOOP
    EXECUTE format('DROP POLICY %I ON %I.%I', r.policyname, r.schemaname, r.tablename);
  END LOOP;
END $$;


-- ── 2) lokasyonlar — heartbeat (cloud_sync.send_heartbeat upsert) ─────────
CREATE POLICY hvac_lokasyonlar_sel ON public.lokasyonlar FOR SELECT TO anon USING (true);
CREATE POLICY hvac_lokasyonlar_ins ON public.lokasyonlar FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY hvac_lokasyonlar_upd ON public.lokasyonlar FOR UPDATE TO anon USING (true) WITH CHECK (true);
-- DELETE politikası YOK → anon lokasyon silemez.


-- ── 3) guncellemeler — KOD DAĞITIMI (en kritik tablo) ─────────────────────
-- Lokasyon: bekleyen yamayı okur, uygulayınca durum='tamamlandi' yazar.
-- INSERT politikası YOK → anon yeni yama yayınlayamaz (uzaktan kod çalıştırma
-- vektörü kapalı; yayınlamayı guncelleme_yayinla.py service_role ile yapar).
CREATE POLICY hvac_guncellemeler_sel ON public.guncellemeler FOR SELECT TO anon USING (true);
CREATE POLICY hvac_guncellemeler_upd ON public.guncellemeler FOR UPDATE TO anon USING (true) WITH CHECK (true);

-- REPLAY KORUMASI: anon yalnızca 'durum' alanını değiştirebilir ve
-- 'tamamlandi' -> 'bekliyor' geri çevirip eski yamayı yeniden yürütemez.
-- (RLS WITH CHECK içinde OLD görülemediği için trigger ile yapılır.)
-- NOT: SECURITY DEFINER KULLANILMAZ. Kullanılsaydı current_user fonksiyon
-- sahibine (postgres) dönüşür, service_role tespiti her zaman doğru çıkar ve
-- koruma işlevsiz kalırdı. INVOKER (varsayılan) ile current_user gerçek
-- bağlantı rolüdür (anon / service_role).
CREATE OR REPLACE FUNCTION public.hvac_guncelleme_koru()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
  _rol text;
BEGIN
  -- Rol tespiti iki yoldan: bağlantı rolü (yeni sb_secret anahtarları) ve
  -- JWT claim (eski anahtar formatı). Biri tutarsa service_role kabul edilir.
  _rol := current_user;
  IF _rol IN ('service_role', 'postgres', 'supabase_admin') THEN
    RETURN NEW;  -- yayınlama scripti (guncelleme_yayinla.py) serbest
  END IF;

  BEGIN
    IF coalesce(current_setting('request.jwt.claims', true)::json ->> 'role', '') = 'service_role' THEN
      RETURN NEW;
    END IF;
  EXCEPTION WHEN OTHERS THEN
    NULL;  -- claim yoksa/parse edilemezse anon kabul edilir
  END;

  IF NEW.dosyalar IS DISTINCT FROM OLD.dosyalar
     OR NEW.hedef  IS DISTINCT FROM OLD.hedef
     OR NEW.versiyon IS DISTINCT FROM OLD.versiyon THEN
    RAISE EXCEPTION 'Yama icerigi degistirilemez (yalnizca durum guncellenebilir)';
  END IF;

  IF OLD.durum = 'tamamlandi' AND NEW.durum = 'bekliyor' THEN
    RAISE EXCEPTION 'Tamamlanmis yama yeniden kuyruga alinamaz (replay korumasi)';
  END IF;

  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS hvac_guncelleme_koru_trg ON public.guncellemeler;
CREATE TRIGGER hvac_guncelleme_koru_trg
  BEFORE UPDATE ON public.guncellemeler
  FOR EACH ROW EXECUTE FUNCTION public.hvac_guncelleme_koru();


-- ── 4) komutlar — BMS SETPOINT (en kritik yazma yolu) ─────────────────────
-- Lokasyon: bekleyen komutu okur, çalıştırınca durum/hata_mesaji/executed_at yazar.
-- Merkez portal (şu an publishable): INSERT ediyor → AŞAMA 2'de kapatılacak.
CREATE POLICY hvac_komutlar_sel ON public.komutlar FOR SELECT TO anon USING (true);
CREATE POLICY hvac_komutlar_upd ON public.komutlar FOR UPDATE TO anon USING (true) WITH CHECK (true);
CREATE POLICY hvac_komutlar_ins ON public.komutlar FOR INSERT TO anon WITH CHECK (true);  -- AŞAMA 2'de KALDIRILACAK
-- DELETE politikası YOK → komut geçmişi (denetim izi) silinemez.


-- ── 5) lokasyon_noktalar — BMS topolojisi (gateway IP / MAC / obj) ────────
-- Lokasyon collector'ı okumak zorunda. Yazma hiçbir yerde yapılmıyor → kapalı.
CREATE POLICY hvac_noktalar_sel ON public.lokasyon_noktalar FOR SELECT TO anon USING (true);


-- ── 6) bakim_kartlari — dijital bakım kartları (cloud_sync delta senkron) ─
CREATE POLICY hvac_kartlar_sel ON public.bakim_kartlari FOR SELECT TO anon USING (true);
CREATE POLICY hvac_kartlar_ins ON public.bakim_kartlari FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY hvac_kartlar_upd ON public.bakim_kartlari FOR UPDATE TO anon USING (true) WITH CHECK (true);
-- DELETE politikası YOK → kart silinemez.


-- ── 7) bildirimler — personel bildirimleri ────────────────────────────────
-- ahu_collector INSERT eder, app_portal okur ve okundu=true PATCH'ler.
-- DELETE kodda HİÇ kullanılmıyor → kapatıldı (iz temizleme engellenir).
CREATE POLICY hvac_bildirim_sel ON public.bildirimler FOR SELECT TO anon USING (true);
CREATE POLICY hvac_bildirim_ins ON public.bildirimler FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY hvac_bildirim_upd ON public.bildirimler FOR UPDATE TO anon USING (true) WITH CHECK (true);


-- ── 8) lisanslar — lisans doğrulama (lisans.py yalnızca okur) ─────────────
CREATE POLICY hvac_lisans_sel ON public.lisanslar FOR SELECT TO anon USING (true);


-- ── 9) Yalnızca MERKEZ portalın kullandığı tablolar ───────────────────────
-- Merkez şu an publishable anahtarla çalıştığı için AŞAMA 1'de açık bırakılır.
-- AŞAMA 2'de bu politikalar silinerek anon'a tamamen kapatılır.
CREATE POLICY hvac_ayarlar_all    ON public.ayarlar      FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY hvac_ai_all         ON public.ai_analizler FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY hvac_dishava_all    ON public.dis_hava_log FOR ALL TO anon USING (true) WITH CHECK (true);
CREATE POLICY hvac_otomod_all     ON public.oto_mod_log  FOR ALL TO anon USING (true) WITH CHECK (true);


-- ####################  AŞAMA 1 SONU  ####################
-- Bu noktada kapanan açıklar:
--   * guncellemeler'e anon INSERT  (uzaktan kod dağıtımı)
--   * guncellemeler replay + yama içeriği değiştirme  (trigger)
--   * lokasyonlar / bakim_kartlari / komutlar / bildirimler DELETE
--   * lokasyon_noktalar'a yazma
-- Açık KALAN (AŞAMA 2 gerekir):
--   * komutlar INSERT — merkez portal publishable anahtarla yazdığı için



-- ============================================================================
--  ####################  AŞAMA 2 — SIRAYLA YAP  ####################
--
--  ADIM A) Supabase Dashboard → Project Settings → API Keys → service_role
--          anahtarını kopyala.
--  ADIM B) Streamlit Cloud → app → Settings → Secrets → [supabase] key
--          değerini service_role anahtarıyla DEĞİŞTİR. Uygulama yeniden başlar.
--          (Streamlit secrets sunucu tarafındadır, tarayıcıya sızmaz.)
--  ADIM C) Merkez portalı aç, "Uzaktan Kontrol"den bir komut gönderip
--          çalıştığını DOĞRULA.
--  ADIM D) Ancak bundan sonra aşağıdaki bloğu çalıştır.
--
--  UYARI: ADIM B yapılmadan bu blok çalıştırılırsa merkez portalın
--         uzaktan kontrol ve ayarlar özellikleri ÇALIŞMAZ.
-- ============================================================================

/*  ---- AŞAMA 2: yorumu kaldırıp çalıştır ----

-- Merkez artık service_role kullandığı için anon'un komut ÜRETME yetkisi kalkar.
-- (Lokasyonların SELECT/UPDATE yetkisi durur — komutu okuyup sonucu yazmaya devam ederler.)
DROP POLICY IF EXISTS hvac_komutlar_ins ON public.komutlar;

-- Sadece merkezin kullandığı tablolar anon'a tamamen kapatılır.
DROP POLICY IF EXISTS hvac_ayarlar_all  ON public.ayarlar;
DROP POLICY IF EXISTS hvac_ai_all       ON public.ai_analizler;
DROP POLICY IF EXISTS hvac_dishava_all  ON public.dis_hava_log;
DROP POLICY IF EXISTS hvac_otomod_all   ON public.oto_mod_log;

*/


-- ============================================================================
--  DOĞRULAMA — çalıştırdıktan sonra bunu koş, hepsi 'true' olmalı
-- ============================================================================
SELECT c.relname AS tablo,
       c.relrowsecurity AS rls_acik,
       count(p.policyname) AS politika_sayisi
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_policies p ON p.tablename = c.relname AND p.schemaname = 'public'
WHERE n.nspname = 'public' AND c.relkind = 'r'
GROUP BY c.relname, c.relrowsecurity
ORDER BY c.relrowsecurity, c.relname;
