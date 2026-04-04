# forecast_engine.py
# Tüketim Tahmin ve Çok Yıllık Trend Analizi Motoru
# ML (RandomForest/GradientBoosting) + Trend bazlı hibrit projeksiyon
# Aylık agregasyon ile eğitim — R² > 0.7 hedef

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import os
import json
import pickle
import calendar
import math
from datetime import date, datetime

import pandas as pd
import numpy as np

try:
    from location_manager import get_manager as _get_loc_mgr
    _lm = _get_loc_mgr()
    SETTINGS_FILE = _lm.get_data_path("configs/hvac_settings.json")
    ENERGY_CSV = _lm.get_data_path("energy_data.csv")
    ML_MODEL_FILE = _lm.get_data_path("configs/ml_forecast_model.pkl")
except Exception:
    SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "hvac_settings.json")
    ENERGY_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "energy_data.csv")
    ML_MODEL_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "ml_forecast_model.pkl")

AYLAR = {
    1: "Ocak", 2: "Subat", 3: "Mart", 4: "Nisan",
    5: "Mayis", 6: "Haziran", 7: "Temmuz", 8: "Agustos",
    9: "Eylul", 10: "Ekim", 11: "Kasim", 12: "Aralik"
}

# ══════════════════════════════════════════════════════════
# Feature tanımları
# ══════════════════════════════════════════════════════════

FEATURE_COLS = [
    "ay",                    # 1-12
    "ay_sin",                # sin(2*pi*ay/12) — döngüsel mevsim
    "ay_cos",                # cos(2*pi*ay/12) — döngüsel mevsim
    "gun_sayisi",            # Aydaki gün sayısı
    "dis_hava",              # Ort. dış hava sıcaklığı (°C)
    "chiller_set",           # Ort. chiller set sıcaklığı (°C)
    "chiller_adet",          # Ort. çalışan chiller sayısı
    "absorption_adet",       # Ort. absorption chiller sayısı
    "kazan_adet",            # Ort. çalışan kazan sayısı
    "kojen_uretim",          # Toplam kojen üretimi (kWh)
    "kazan_dogalgaz",        # Toplam kazan doğalgaz (m³)
]

FEATURE_LABELS = {
    "dis_hava": "Dis Hava Sicakligi",
    "chiller_adet": "Chiller Adet",
    "chiller_set": "Chiller Set Temp",
    "kazan_adet": "Kazan Adet",
    "ay": "Ay",
    "ay_sin": "Mevsim (sin)",
    "ay_cos": "Mevsim (cos)",
    "gun_sayisi": "Gun Sayisi",
    "absorption_adet": "Absorption Chiller",
    "kojen_uretim": "Kojen Uretim",
    "kazan_dogalgaz": "Kazan Dogalgaz",
}


# ══════════════════════════════════════════════════════════
# ML Tahmin Modeli — Aylık bazda eğitim
# ══════════════════════════════════════════════════════════

class MLPredictor:
    """GradientBoosting/RandomForest tabanlı aylık tüketim tahmini."""

    MIN_MONTHS = 12  # En az 12 aylık veri olmalı

    def __init__(self):
        self.model_total = None
        self.model_grid = None
        self.r2_total = 0.0
        self.r2_grid = 0.0
        self.feature_importance = {}
        self.train_samples = 0
        self.train_months = 0
        self.is_trained = False
        self._load_model()

    # ─── Kaydet / Yükle ───
    def _load_model(self):
        try:
            if os.path.exists(ML_MODEL_FILE):
                with open(ML_MODEL_FILE, "rb") as f:
                    data = pickle.load(f)
                
                # P2: Feature uyumsuzluk kontrolü
                saved_features = data.get("feature_cols", [])
                if saved_features and saved_features != FEATURE_COLS:
                    import logging
                    logging.warning(
                        f"Model feature uyumsuzluğu: kayıtlı={saved_features}, mevcut={FEATURE_COLS}. "
                        f"Model yeniden eğitilecek."
                    )
                    self.is_trained = False
                    return
                
                self.model_total = data.get("model_total")
                self.model_grid = data.get("model_grid")
                self.r2_total = data.get("r2_total", 0)
                self.r2_grid = data.get("r2_grid", 0)
                self.feature_importance = data.get("feature_importance", {})
                self.train_samples = data.get("train_samples", 0)
                self.train_months = data.get("train_months", 0)
                self.is_trained = self.model_total is not None
        except Exception as e:
            import logging
            logging.warning(f"ML model yükleme hatası: {e}")
            self.is_trained = False

    def _save_model(self):
        try:
            os.makedirs(os.path.dirname(ML_MODEL_FILE), exist_ok=True)
            data = {
                "model_total": self.model_total,
                "model_grid": self.model_grid,
                "r2_total": self.r2_total,
                "r2_grid": self.r2_grid,
                "feature_importance": self.feature_importance,
                "train_samples": self.train_samples,
                "train_months": self.train_months,
                "trained_at": datetime.now().isoformat(),
                "feature_cols": FEATURE_COLS,  # P2: Feature versiyonlama
            }
            with open(ML_MODEL_FILE, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            import logging
            logging.warning(f"ML model kaydetme hatası: {e}")

    # ─── Aylık Agregasyon ───
    def _aggregate_monthly(self, df: pd.DataFrame) -> pd.DataFrame:
        """Günlük veriyi aylık feature matrisine dönüştür."""
        monthly = df.groupby(["Yil", "Ay"]).agg({
            "Toplam_Hastane_Tuketim_kWh": "sum",
            "Sebeke_Tuketim_kWh": "sum",
            "Dis_Hava_Sicakligi_C": "mean",
            "Chiller_Set_Temp_C": "mean",
            "Chiller_Adet": "mean",
            "Absorption_Chiller_Adet": "mean",
            "Kazan_Adet": "mean",
            "Kojen_Uretim_kWh": "sum",
            "Kazan_Dogalgaz_m3": "sum",
            "Tarih": "count",
        }).rename(columns={"Tarih": "gun_sayisi"}).reset_index()
        return monthly

    def _build_features(self, monthly: pd.DataFrame) -> pd.DataFrame:
        """Aylık aggregated veriden feature matrisini oluştur."""
        X = pd.DataFrame()
        X["ay"] = monthly["Ay"].astype(float)
        X["ay_sin"] = np.sin(2 * np.pi * X["ay"] / 12)
        X["ay_cos"] = np.cos(2 * np.pi * X["ay"] / 12)
        X["gun_sayisi"] = monthly["gun_sayisi"].astype(float)
        X["dis_hava"] = monthly["Dis_Hava_Sicakligi_C"].fillna(0).astype(float)
        X["chiller_set"] = monthly["Chiller_Set_Temp_C"].fillna(7).astype(float)
        X["chiller_adet"] = monthly["Chiller_Adet"].fillna(0).astype(float)
        X["absorption_adet"] = monthly["Absorption_Chiller_Adet"].fillna(0).astype(float)
        X["kazan_adet"] = monthly["Kazan_Adet"].fillna(0).astype(float)
        X["kojen_uretim"] = monthly["Kojen_Uretim_kWh"].fillna(0).astype(float)
        X["kazan_dogalgaz"] = monthly["Kazan_Dogalgaz_m3"].fillna(0).astype(float)
        return X

    # ─── Eğitim ───
    def train(self, df: pd.DataFrame) -> Dict:
        """Modeli aylık aggregated veriyle eğit."""
        if df.empty:
            return {"success": False, "reason": "Veri yok"}

        monthly = self._aggregate_monthly(df)
        # Eksik ayları filtrele (en az 15 günlük veri olsun)
        monthly = monthly[monthly["gun_sayisi"] >= 15]

        if len(monthly) < self.MIN_MONTHS:
            return {"success": False, "reason": f"Yetersiz ay verisi ({len(monthly)}/{self.MIN_MONTHS})"}

        try:
            from sklearn.ensemble import GradientBoostingRegressor
            from sklearn.model_selection import cross_val_score

            X = self._build_features(monthly)
            y_total = monthly["Toplam_Hastane_Tuketim_kWh"].fillna(0)
            y_grid = monthly["Sebeke_Tuketim_kWh"].fillna(0)

            # Toplam tüketim modeli
            self.model_total = GradientBoostingRegressor(
                n_estimators=150, max_depth=5, min_samples_split=3,
                learning_rate=0.1, random_state=42,
            )
            self.model_total.fit(X, y_total)

            # Leave-one-out CV (az veri için daha iyi)
            cv_folds = min(5, len(X))
            cv_total = cross_val_score(self.model_total, X, y_total, cv=cv_folds, scoring="r2")
            self.r2_total = float(np.mean(cv_total))

            # Şebeke modeli
            self.model_grid = GradientBoostingRegressor(
                n_estimators=150, max_depth=5, min_samples_split=3,
                learning_rate=0.1, random_state=42,
            )
            self.model_grid.fit(X, y_grid)
            cv_grid = cross_val_score(self.model_grid, X, y_grid, cv=cv_folds, scoring="r2")
            self.r2_grid = float(np.mean(cv_grid))

            # Feature importance
            importances = self.model_total.feature_importances_
            self.feature_importance = {
                FEATURE_COLS[i]: float(importances[i])
                for i in range(len(FEATURE_COLS))
            }

            self.train_samples = len(df)
            self.train_months = len(monthly)
            self.is_trained = True
            self._save_model()

            return {
                "success": True,
                "r2_total": self.r2_total,
                "r2_grid": self.r2_grid,
                "samples": self.train_samples,
                "months": self.train_months,
                "feature_importance": self.feature_importance,
            }
        except Exception as e:
            return {"success": False, "reason": str(e)}

    # ─── Tahmin ───
    def predict_month_from_history(self, df: pd.DataFrame, year: int, month: int) -> Dict:
        """
        Geçmiş verideki o ayın ortalama koşullarını kullanarak
        aylık toplam tüketim tahmini.
        """
        if not self.is_trained:
            return {}

        # Aynı ayın geçmişteki verileri
        past = df[df["Ay"] == month]
        if past.empty:
            return {}

        gun = calendar.monthrange(year, month)[1]
        avg_hava = float(past["Dis_Hava_Sicakligi_C"].fillna(0).mean())
        avg_set = float(past.get("Chiller_Set_Temp_C", pd.Series([7])).fillna(7).mean())
        avg_ch = float(past.get("Chiller_Adet", pd.Series([0])).fillna(0).mean())
        avg_ab = float(past.get("Absorption_Chiller_Adet", pd.Series([0])).fillna(0).mean())
        avg_kz = float(past.get("Kazan_Adet", pd.Series([0])).fillna(0).mean())
        avg_kojen = float(past["Kojen_Uretim_kWh"].fillna(0).sum()) / max(len(past["Yil"].unique()), 1)
        avg_gas = float(past["Kazan_Dogalgaz_m3"].fillna(0).sum()) / max(len(past["Yil"].unique()), 1)

        X = pd.DataFrame([{
            "ay": float(month),
            "ay_sin": math.sin(2 * math.pi * month / 12),
            "ay_cos": math.cos(2 * math.pi * month / 12),
            "gun_sayisi": float(gun),
            "dis_hava": avg_hava,
            "chiller_set": avg_set,
            "chiller_adet": avg_ch,
            "absorption_adet": avg_ab,
            "kazan_adet": avg_kz,
            "kojen_uretim": avg_kojen,
            "kazan_dogalgaz": avg_gas,
        }])

        pred_total = float(self.model_total.predict(X)[0])
        pred_grid = float(self.model_grid.predict(X)[0])

        return {
            "total_kwh": max(pred_total, 0),
            "grid_kwh": max(pred_grid, 0),
            "kojen_kwh": max(pred_total - pred_grid, 0),
            "avg_conditions": {
                "dis_hava": round(avg_hava, 1),
                "chiller_set": round(avg_set, 1),
                "chiller_adet": round(avg_ch, 1),
                "kazan_adet": round(avg_kz, 1),
            }
        }

    def predict_scenario(self, dis_hava: float, chiller_set: float,
                         chiller_adet: float, absorption_adet: float,
                         kazan_adet: float, kojen_uretim: float,
                         kazan_dogalgaz: float, ay: int,
                         gun_sayisi: int = None) -> Dict:
        """Senaryo tahmini — kullanıcının girdiği parametrelerle."""
        if not self.is_trained:
            return {"error": "Model henuz egitilmedi"}

        if gun_sayisi is None:
            gun_sayisi = calendar.monthrange(2026, ay)[1]

        X = pd.DataFrame([{
            "ay": float(ay),
            "ay_sin": math.sin(2 * math.pi * ay / 12),
            "ay_cos": math.cos(2 * math.pi * ay / 12),
            "gun_sayisi": float(gun_sayisi),
            "dis_hava": dis_hava,
            "chiller_set": chiller_set,
            "chiller_adet": chiller_adet,
            "absorption_adet": absorption_adet,
            "kazan_adet": kazan_adet,
            "kojen_uretim": kojen_uretim,
            "kazan_dogalgaz": kazan_dogalgaz,
        }])

        pred_total = max(float(self.model_total.predict(X)[0]), 0)
        pred_grid = max(float(self.model_grid.predict(X)[0]), 0)

        return {
            "aylik_toplam": pred_total,
            "aylik_sebeke": pred_grid,
            "aylik_kojen": max(pred_total - pred_grid, 0),
            "gunluk_toplam": pred_total / gun_sayisi if gun_sayisi > 0 else 0,
            "gunluk_sebeke": pred_grid / gun_sayisi if gun_sayisi > 0 else 0,
            "gun_sayisi": gun_sayisi,
        }

    def get_model_info(self) -> Dict:
        return {
            "is_trained": self.is_trained,
            "r2_total": self.r2_total,
            "r2_grid": self.r2_grid,
            "train_samples": self.train_samples,
            "train_months": self.train_months,
            "feature_importance": self.feature_importance,
            "model_file": ML_MODEL_FILE,
            "model_exists": os.path.exists(ML_MODEL_FILE),
        }


# ══════════════════════════════════════════════════════════
# Ana Tahmin Motoru
# ══════════════════════════════════════════════════════════

class ConsumptionForecastEngine:
    """Hibrit tahmin motoru: ML + Trend bazlı fallback."""

    def __init__(self, building_area_m2: float = None):
        self.building_area = building_area_m2 or self._load_building_area()
        self.df = self._load_data()
        self.ml = MLPredictor()

    def _load_building_area(self) -> float:
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return float(json.load(f).get("BUILDING_AREA_M2", 0))
        except Exception:
            pass
        return 0

    def _load_data(self) -> pd.DataFrame:
        try:
            if not os.path.exists(ENERGY_CSV):
                return pd.DataFrame()
            df = pd.read_csv(ENERGY_CSV)
            df["Tarih"] = pd.to_datetime(df["Tarih"], format="%Y-%m-%d")
            df["Yil"] = df["Tarih"].dt.year
            df["Ay"] = df["Tarih"].dt.month
            return df
        except Exception:
            return pd.DataFrame()

    def train_model(self) -> Dict:
        """ML modelini eğit."""
        if self.df.empty:
            return {"success": False, "reason": "Veri yok"}
        return self.ml.train(self.df)

    def auto_train_if_needed(self) -> Dict:
        """Model yoksa veya yeni veri eklenmişse otomatik eğit."""
        if not self.ml.is_trained:
            return self.train_model()
        if len(self.df) > self.ml.train_samples + 20:
            return self.train_model()
        return {"success": True, "reason": "Model guncel"}

    # ─── Çok Yıllık Özet ───
    def get_yearly_summary(self) -> List[Dict]:
        if self.df.empty:
            return []
        results = []
        for year in sorted(self.df["Yil"].unique()):
            ydf = self.df[self.df["Yil"] == year]
            days = len(ydf)
            if days < 180 and year != self.df["Yil"].max():
                continue
            total = float(ydf["Toplam_Hastane_Tuketim_kWh"].fillna(0).sum())
            grid = float(ydf.get("Sebeke_Tuketim_kWh", pd.Series([0])).fillna(0).sum())
            kojen = float(ydf.get("Kojen_Uretim_kWh", pd.Series([0])).fillna(0).sum())
            chiller = float(ydf.get("Chiller_Tuketim_kWh", pd.Series([0])).fillna(0).sum())
            area = self.building_area if self.building_area > 0 else 1
            results.append({
                "year": year, "days": days,
                "total_kwh": total, "grid_kwh": grid, "kojen_kwh": kojen,
                "chiller_kwh": chiller,
                "kwh_per_m2": total / area, "grid_per_m2": grid / area,
                "chiller_per_m2": chiller / area, "area_m2": area,
            })
        return results

    # ─── Aylık Tahmin ───
    def get_monthly_forecast(self, target_year: int) -> List[Dict]:
        if self.df.empty:
            return []

        self.auto_train_if_needed()
        use_ml = self.ml.is_trained

        years = sorted(self.df["Yil"].unique())
        full_years = [y for y in years if len(self.df[self.df["Yil"] == y]) >= 300]

        forecasts = []
        for m in range(1, 13):
            entry = {
                "month": m,
                "month_name": AYLAR.get(m, str(m)),
                "method": "ml" if use_ml else "trend",
            }

            # ML tahmini
            if use_ml:
                ml_pred = self.ml.predict_month_from_history(self.df, target_year, m)
                entry["forecast_total"] = ml_pred.get("total_kwh", 0)
                entry["forecast_grid"] = ml_pred.get("grid_kwh", 0)
                entry["avg_conditions"] = ml_pred.get("avg_conditions", {})

            # Trend referans
            if len(full_years) >= 2:
                prev_year = full_years[-2]
                last_year = full_years[-1]
                prev_data = self.df[(self.df["Yil"] == prev_year) & (self.df["Ay"] == m)]
                last_data = self.df[(self.df["Yil"] == last_year) & (self.df["Ay"] == m)]

                prev_total = float(prev_data["Toplam_Hastane_Tuketim_kWh"].fillna(0).sum()) if not prev_data.empty else 0
                last_total = float(last_data["Toplam_Hastane_Tuketim_kWh"].fillna(0).sum()) if not last_data.empty else 0
                prev_grid = float(prev_data.get("Sebeke_Tuketim_kWh", pd.Series([0])).fillna(0).sum()) if not prev_data.empty else 0
                last_grid = float(last_data.get("Sebeke_Tuketim_kWh", pd.Series([0])).fillna(0).sum()) if not last_data.empty else 0

                trend_total = (last_total - prev_total) / prev_total if prev_total > 0 else 0
                trend_grid = (last_grid - prev_grid) / prev_grid if prev_grid > 0 else 0

                entry["prev_year"] = prev_year
                entry["last_year"] = last_year
                entry["prev_total"] = prev_total
                entry["last_total"] = last_total
                entry["prev_grid"] = prev_grid
                entry["last_grid"] = last_grid
                entry["trend_total_pct"] = trend_total * 100
                entry["trend_grid_pct"] = trend_grid * 100

                if not use_ml:
                    entry["forecast_total"] = last_total * (1 + trend_total / 2)
                    entry["forecast_grid"] = last_grid * (1 + trend_grid / 2)
            else:
                for k in ("prev_year", "last_year", "prev_total", "last_total",
                          "prev_grid", "last_grid", "trend_total_pct", "trend_grid_pct"):
                    entry[k] = 0

            # Gerçekleşen
            target_data = self.df[(self.df["Yil"] == target_year) & (self.df["Ay"] == m)]
            if not target_data.empty:
                actual_days = len(target_data)
                month_days = calendar.monthrange(target_year, m)[1]
                raw_total = float(target_data["Toplam_Hastane_Tuketim_kWh"].fillna(0).sum())
                raw_grid = float(target_data.get("Sebeke_Tuketim_kWh", pd.Series([0])).fillna(0).sum())

                if actual_days >= month_days - 3:
                    entry["actual_total"] = raw_total
                    entry["actual_grid"] = raw_grid
                else:
                    entry["actual_total"] = raw_total / actual_days * month_days if actual_days > 0 else None
                    entry["actual_grid"] = raw_grid / actual_days * month_days if actual_days > 0 else None
                entry["actual_days"] = actual_days
                entry["is_partial"] = actual_days < month_days - 3
            else:
                entry["actual_total"] = None
                entry["actual_grid"] = None
                entry["actual_days"] = 0
                entry["is_partial"] = False

            # Sapma
            ft = entry.get("forecast_total", 0)
            if entry["actual_total"] is not None and ft > 0:
                entry["deviation_total_pct"] = (entry["actual_total"] - ft) / ft * 100
            else:
                entry["deviation_total_pct"] = None

            forecasts.append(entry)

        return forecasts

    # ─── Tasarruf Hesabı ───
    def calculate_savings(self, year: int) -> Dict:
        if self.df.empty or self.building_area <= 0:
            return {}
        years = sorted(self.df["Yil"].unique())
        full_years = [y for y in years if len(self.df[self.df["Yil"] == y]) >= 300]
        if year not in years or len(full_years) < 2:
            return {}
        idx = full_years.index(year) if year in full_years else -1
        prev_year = full_years[idx - 1] if idx > 0 else full_years[-2]
        if prev_year == year:
            return {}

        curr = self.df[self.df["Yil"] == year]
        prev = self.df[self.df["Yil"] == prev_year]
        if curr.empty or prev.empty:
            return {}

        curr_total = float(curr["Toplam_Hastane_Tuketim_kWh"].fillna(0).sum())
        prev_total = float(prev["Toplam_Hastane_Tuketim_kWh"].fillna(0).sum())
        curr_grid = float(curr.get("Sebeke_Tuketim_kWh", pd.Series([0])).fillna(0).sum())
        prev_grid = float(prev.get("Sebeke_Tuketim_kWh", pd.Series([0])).fillna(0).sum())

        return {
            "year": year, "prev_year": prev_year,
            "area_m2": self.building_area,
            "expected_total": prev_total, "curr_total": curr_total,
            "savings_total_kwh": prev_total - curr_total,
            "savings_total_pct": ((prev_total - curr_total) / prev_total * 100) if prev_total > 0 else 0,
            "expected_grid": prev_grid, "curr_grid": curr_grid,
            "savings_grid_kwh": prev_grid - curr_grid,
            "savings_grid_pct": ((prev_grid - curr_grid) / prev_grid * 100) if prev_grid > 0 else 0,
        }

    # ─── Sonraki Ay ───
    def predict_next_month(self) -> Dict:
        today = date.today()
        target_month = today.month + 1
        target_year = today.year
        if target_month > 12:
            target_month = 1
            target_year += 1

        forecasts = self.get_monthly_forecast(target_year)
        for f in forecasts:
            if f["month"] == target_month:
                result = {
                    "year": target_year,
                    "month": target_month,
                    "month_name": f["month_name"],
                    "forecast_total": f.get("forecast_total", 0),
                    "forecast_grid": f.get("forecast_grid", 0),
                    "trend_total_pct": f.get("trend_total_pct", 0),
                    "trend_grid_pct": f.get("trend_grid_pct", 0),
                    "method": f.get("method", "trend"),
                    "per_m2": f.get("forecast_total", 0) / self.building_area if self.building_area > 0 else 0,
                }
                if "avg_conditions" in f:
                    result["avg_conditions"] = f["avg_conditions"]
                return result
        return {}

    # ─── Senaryo Tahmini ───
    def scenario_predict(self, dis_hava: float, chiller_set: float,
                         chiller_adet: int, kazan_adet: int,
                         ay: int, absorption_adet: int = 0,
                         kar_eritme: bool = False,
                         kojen_uretim: float = None,
                         kazan_dogalgaz: float = None) -> Dict:
        """Senaryo tahmini — parametrelerle."""
        self.auto_train_if_needed()
        if not self.ml.is_trained:
            return {"error": "Model henuz egitilmedi"}

        # Kojen/dogalgaz default: o ayın ortalaması
        if kojen_uretim is None:
            past = self.df[self.df["Ay"] == ay]
            kojen_uretim = float(past["Kojen_Uretim_kWh"].fillna(0).sum()) / max(len(past["Yil"].unique()), 1)
        if kazan_dogalgaz is None:
            past = self.df[self.df["Ay"] == ay]
            kazan_dogalgaz = float(past["Kazan_Dogalgaz_m3"].fillna(0).sum()) / max(len(past["Yil"].unique()), 1)

        return self.ml.predict_scenario(
            dis_hava=dis_hava, chiller_set=chiller_set,
            chiller_adet=float(chiller_adet), absorption_adet=float(absorption_adet),
            kazan_adet=float(kazan_adet),
            kojen_uretim=kojen_uretim, kazan_dogalgaz=kazan_dogalgaz,
            ay=ay,
        )

    # ─── Tam Analiz Paketi ───
    def full_analysis(self, target_year: int) -> Dict:
        return {
            "yearly_summary": self.get_yearly_summary(),
            "monthly_forecast": self.get_monthly_forecast(target_year),
            "savings": self.calculate_savings(target_year),
            "next_month": self.predict_next_month(),
            "building_area": self.building_area,
            "model_info": self.ml.get_model_info(),
        }
