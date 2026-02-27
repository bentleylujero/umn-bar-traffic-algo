"""RandomForest wait-time regression model.

The train/test split is time-based: the last TEST_SPLIT_DAYS of observations
form the held-out test set.  This mirrors real deployment (we never have
future data when predicting).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
from sklearn.pipeline import Pipeline

from config.settings import RANDOM_SEED, RF_MAX_DEPTH, RF_N_ESTIMATORS, TEST_SPLIT_DAYS

log = logging.getLogger(__name__)


class WaitTimeModel:
    """RandomForest regressor with a time-based train/test split.

    Parameters
    ----------
    feature_cols : list[str]
        Column names to use as predictors.
    test_split_days : int
        Number of trailing days reserved for evaluation.
    """

    def __init__(
        self,
        feature_cols: list[str],
        target_col: str = "wait_minutes",
        test_split_days: int = TEST_SPLIT_DAYS,
    ) -> None:
        self.feature_cols = feature_cols
        self.target_col = target_col
        self.test_split_days = test_split_days

        self._pipeline: Optional[Pipeline] = None
        self.train_metrics: dict = {}
        self.test_metrics: dict = {}
        self.feature_importances_: Optional[pd.Series] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def fit(
        self,
        df: pd.DataFrame,
        sample_weight: "np.ndarray | None" = None,
    ) -> "WaitTimeModel":
        """Fit the model.  df must have observed_at, wait_minutes, and all
        columns in feature_cols.

        Parameters
        ----------
        sample_weight : array-like, optional
            Per-row training weights aligned with *df* (before the train/test
            split).  Rows in the test split are ignored.  Pass higher weights
            for drinking-holiday rows so the RF fits those observations more tightly.
        """
        df = df.copy()
        df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
        df = df.sort_values("observed_at").reset_index(drop=True)

        cutoff = df["observed_at"].max() - timedelta(days=self.test_split_days)
        train_mask = df["observed_at"] <= cutoff
        train = df[train_mask]
        test = df[~train_mask]

        if len(train) < 10:
            log.warning(
                "Only %d training rows — model quality may be poor.", len(train)
            )

        X_train = train[self.feature_cols]
        y_train = train[self.target_col]
        w_train = sample_weight[train_mask.values] if sample_weight is not None else None

        self._pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("rf", RandomForestRegressor(
                n_estimators=RF_N_ESTIMATORS,
                max_depth=RF_MAX_DEPTH,
                random_state=RANDOM_SEED,
                n_jobs=-1,
            )),
        ])
        # Pass sample_weight through the pipeline via the rf step name
        fit_params = {}
        if w_train is not None:
            fit_params["rf__sample_weight"] = w_train
        self._pipeline.fit(X_train, y_train, **fit_params)

        # Training metrics
        y_train_pred = self._pipeline.predict(X_train)
        self.train_metrics = _metrics(y_train, y_train_pred)

        # Test metrics (only if enough test data)
        if len(test) >= 5:
            X_test = test[self.feature_cols]
            y_test = test[self.target_col]
            y_test_pred = self._pipeline.predict(X_test)
            self.test_metrics = _metrics(y_test, y_test_pred)
        else:
            self.test_metrics = {}
            log.info("Not enough test rows (%d) — skipping test evaluation.", len(test))

        # Feature importances
        rf: RandomForestRegressor = self._pipeline.named_steps["rf"]
        self.feature_importances_ = pd.Series(
            rf.feature_importances_,
            index=self.feature_cols,
            name="importance",
        ).sort_values(ascending=False)

        log.info(
            "WaitTimeModel trained on %d rows. Train MAE=%.2f, Test MAE=%s",
            len(train),
            self.train_metrics.get("mae", float("nan")),
            self.test_metrics.get("mae", "n/a"),
        )
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict wait minutes for rows in *df*."""
        self._check_fitted()
        return self._pipeline.predict(df[self.feature_cols])  # type: ignore[union-attr]

    def predict_one(self, feature_dict: dict) -> float:
        """Predict for a single observation given as a dict."""
        self._check_fitted()
        row = pd.DataFrame([feature_dict])[self.feature_cols]
        return float(self._pipeline.predict(row)[0])  # type: ignore[union-attr]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _check_fitted(self) -> None:
        if self._pipeline is None:
            raise RuntimeError("Call fit() before predict().")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _metrics(y_true: pd.Series, y_pred: np.ndarray) -> dict:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
    }
