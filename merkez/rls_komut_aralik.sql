-- ════════════════════════════════════════════════════════════════════════════
-- komutlar — NOKTA BAZLI DEĞER ARALIĞI (29.10.2026, kullanıcı onaylı)
-- ════════════════════════════════════════════════════════════════════════════
-- Ortak anon anahtarla komutlar'a satır eklenebiliyor (OTO SET buna muhtaç).
-- Bu tetikleyici, aralık dışı setpoint'i tabloya HİÇ yazdırmaz.
-- Sahadaki ikinci katman: hvac/deneme/bacnet_writer.py NOKTA_ARALIKLARI —
-- iki liste BİREBİR aynı olmalı (test_bacnet_writer.py karşılaştırır).
--   CH<n>_REM_SET .................. 6.0 – 12.0 °C  (chiller çıkış seti)
--   GUNDUZ/GECE_KOLLEKTOR_SET ...... 8.0 – 18.0 °C
--   <harf>_BLOK_FCU_SET ............ 8.0 – 18.0 °C
--   ZON<n>_KLIMA_SANTRALI_SET ...... 6.0 – 16.0 °C
--   diğer noktalar ................. 5.0 – 40.0 °C  (genel sınır)
-- YALNIZ YÜRÜTÜLECEK komutlar (durum = 'bekliyor') denetlenir: saha yalnız
-- bunları BACnet'e yazar. OTO SET'in sonuçlanmış kayıtları (tamamlandi / hata —
-- reddettiği aralık dışı değerin İZİ dahil) serbest yazılır; yoksa tek bir
-- red kaydı aynı turdaki bütün kayıtları düşürürdü. Bekleyen bir komutun
-- değerini/noktasını değiştiren ya da durumu 'bekliyor'a çeviren UPDATE de
-- denetlenir. service_role da denetlenir.
-- Tekrar çalıştırılabilir.
-- ════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.hvac_komut_aralik()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
  _d numeric;
  _alt numeric := 5.0;
  _ust numeric := 40.0;
BEGIN
  IF NEW.durum IS DISTINCT FROM 'bekliyor' THEN
    RETURN NEW;                       -- yürütülmeyecek kayıt (sonuç / iz)
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.durum = 'bekliyor'
     AND NEW.hedef_deger IS NOT DISTINCT FROM OLD.hedef_deger
     AND NEW.nokta_adi IS NOT DISTINCT FROM OLD.nokta_adi THEN
    RETURN NEW;                       -- değer değişmedi
  END IF;
  IF NEW.hedef_deger IS NULL THEN
    RETURN NEW;                       -- okuma komutu (değer yok)
  END IF;
  BEGIN
    _d := NEW.hedef_deger::numeric;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'Gecersiz komut degeri: %', NEW.hedef_deger;
  END;

  IF    NEW.nokta_adi ~ '^CH\d+_REM_SET$'                THEN _alt := 6.0;  _ust := 12.0;
  ELSIF NEW.nokta_adi ~ '^(GUNDUZ|GECE)_KOLLEKTOR_SET$'  THEN _alt := 8.0;  _ust := 18.0;
  ELSIF NEW.nokta_adi ~ '^[A-Z]_BLOK_FCU_SET$'           THEN _alt := 8.0;  _ust := 18.0;
  ELSIF NEW.nokta_adi ~ '^ZON\d+_KLIMA_SANTRALI_SET$'    THEN _alt := 6.0;  _ust := 16.0;
  END IF;

  IF _d < _alt OR _d > _ust THEN
    RAISE EXCEPTION 'Komut reddedildi: % = % (izinli % - % C)', NEW.nokta_adi, _d, _alt, _ust;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS hvac_komut_aralik_trg ON public.komutlar;
CREATE TRIGGER hvac_komut_aralik_trg
  BEFORE INSERT OR UPDATE ON public.komutlar
  FOR EACH ROW EXECUTE FUNCTION public.hvac_komut_aralik();

-- Aralıklar (test_bacnet_writer.py bu satırları da okur):
--   '^CH\d+_REM_SET$' 6.0 AND 12.0
--   '^(GUNDUZ|GECE)_KOLLEKTOR_SET$' 8.0 AND 18.0
--   '^[A-Z]_BLOK_FCU_SET$' 8.0 AND 18.0
--   '^ZON\d+_KLIMA_SANTRALI_SET$' 6.0 AND 16.0

-- Kontrol: tetikleyici kurulu mu
SELECT tgname FROM pg_trigger WHERE tgrelid = 'public.komutlar'::regclass AND NOT tgisinternal;
