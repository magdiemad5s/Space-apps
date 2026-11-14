"""Simple, pickle-safe baselines with no learned future information."""
import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight


class EncodedXGBClassifier(ClassifierMixin, BaseEstimator):
    """Keep string labels at the service boundary and use integers internally.

    The fitted native XGBClassifier is available as ``estimator_`` for TreeSHAP.
    """
    def __init__(self, n_estimators=200, max_depth=4, learning_rate=.05,
                 min_child_weight=5, subsample=.85, colsample_bytree=.9,
                 reg_lambda=5., random_state=20261114, n_jobs=2):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.min_child_weight = min_child_weight
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.reg_lambda = reg_lambda
        self.random_state = random_state
        self.n_jobs = n_jobs

    def fit(self, X, y):
        from xgboost import XGBClassifier
        self.label_encoder_ = LabelEncoder().fit(y)
        self.classes_ = self.label_encoder_.classes_
        self.n_features_in_ = X.shape[1]
        self.estimator_ = XGBClassifier(
            n_estimators=self.n_estimators, max_depth=self.max_depth,
            learning_rate=self.learning_rate, min_child_weight=self.min_child_weight,
            subsample=self.subsample, colsample_bytree=self.colsample_bytree,
            reg_lambda=self.reg_lambda, random_state=self.random_state,
            n_jobs=self.n_jobs, tree_method="hist", device="cpu",
            objective="multi:softprob", eval_metric="mlogloss")
        self.estimator_.fit(X, self.label_encoder_.transform(y),
                            sample_weight=compute_sample_weight("balanced", y))
        return self

    def predict(self, X):
        return self.label_encoder_.inverse_transform(self.estimator_.predict(X).astype(int))

    def predict_proba(self, X):
        return self.estimator_.predict_proba(X)


class PersistenceRegressor(RegressorMixin, BaseEstimator):
    def __init__(self, column):
        self.column = column

    def fit(self, X, y=None):
        self.n_features_in_ = X.shape[1]
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        return self

    def predict(self, X):
        return np.asarray(X[self.column], dtype=float)


class PersistenceClassifier(ClassifierMixin, BaseEstimator):
    """Tomorrow's demo fatigue category is assumed equal to today's score band."""
    def __init__(self, column="self_report_fatigue_score"):
        self.column = column

    def fit(self, X, y=None):
        self.classes_ = np.asarray(["high", "low", "moderate"], dtype=object)
        self.n_features_in_ = X.shape[1]
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        return self

    def predict(self, X):
        score = np.asarray(X[self.column], dtype=float)
        return np.where(score < 4, "low", np.where(score < 7, "moderate", "high"))

    def predict_proba(self, X):
        return (self.predict(X)[:, None] == self.classes_[None, :]).astype(float)
