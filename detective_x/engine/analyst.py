"""The Deduction Engine — a small machine-learning model, written from scratch.

No numpy, no scikit-learn, no installations. Two classifiers are trained at
runtime on the whole case corpus and then combined:

  * Gaussian Naive Bayes over eight continuous features
  * Logistic regression trained by batch gradient descent

Training uses leave-one-case-out: when the model scores the case the player is
currently working, that case is removed from the training set first. The model
therefore cannot recognise the answer it was told; it has to generalise the
pattern of what guilt looks like across the other investigations.

Feature vector, per suspect:

  0  base suspicion, scaled
  1  total effective weight of active evidence pointing at them
  2  share of the case's implicating evidence that points at them
  3  count of contradictions they are caught in
  4  mean reliability of the evidence against them
  5  proportion of that evidence which is confirmed (>=90% reliable)
  6  whether any evidence against them has been cleared as a red herring
  7  how many distinct evidence types point at them
"""

from __future__ import annotations

import math
from collections import defaultdict

from ..models.case import Case
from .deduction import _is_active, compute_suspicion, find_contradictions

FEATURE_NAMES = (
    "base suspicion",
    "weight of evidence",
    "share of evidence",
    "contradictions",
    "evidence reliability",
    "confirmed proportion",
    "cleared as red herring",
    "variety of evidence",
)

N_FEATURES = len(FEATURE_NAMES)


# --------------------------------------------------------------------------
# Feature extraction
# --------------------------------------------------------------------------
def extract_features(
    case: Case,
    found: set[str],
    contradictions: set[str],
) -> dict[str, list[float]]:
    """Turn the current state of an investigation into one vector per suspect."""
    weight: dict[str, float] = defaultdict(float)
    reliabilities: dict[str, list[float]] = defaultdict(list)
    confirmed: dict[str, int] = defaultdict(int)
    cleared: dict[str, int] = defaultdict(int)
    types: dict[str, set[str]] = defaultdict(set)

    for eid in found:
        try:
            ev = case.evidence_by_id(eid)
        except Exception:
            continue
        if not ev.implicates:
            continue
        if _is_active(ev, found):
            weight[ev.implicates] += ev.effective_weight
            reliabilities[ev.implicates].append(ev.reliability)
            types[ev.implicates].add(ev.type.name)
            if ev.is_confirmed:
                confirmed[ev.implicates] += 1
        else:
            cleared[ev.implicates] += 1

    total_weight = sum(weight.values()) or 1.0
    contradiction_count: dict[str, int] = defaultdict(int)
    for cid in contradictions:
        contradiction_count[cid.split(":", 1)[0]] += 1

    vectors: dict[str, list[float]] = {}
    for suspect in case.suspects:
        sid = suspect.id
        rels = reliabilities[sid]
        n = len(rels)
        vectors[sid] = [
            suspect.base_suspicion / 100.0,
            min(1.0, weight[sid] / 120.0),
            weight[sid] / total_weight,
            min(1.0, contradiction_count[sid] / 3.0),
            (sum(rels) / n / 100.0) if n else 0.0,
            (confirmed[sid] / n) if n else 0.0,
            1.0 if cleared[sid] else 0.0,
            min(1.0, len(types[sid]) / 4.0),
        ]
    return vectors


def _training_rows(cases: list[Case]) -> tuple[list[list[float]], list[int]]:
    """Build a training set from complete knowledge of each case."""
    X: list[list[float]] = []
    y: list[int] = []
    for case in cases:
        full = {ev.id for ev in case.evidence}
        contradictions = find_contradictions(case, full)
        vectors = extract_features(case, full, contradictions)
        for sid, vec in vectors.items():
            X.append(vec)
            y.append(1 if sid == case.culprit_id else 0)
    return X, y


# --------------------------------------------------------------------------
# Gaussian Naive Bayes
# --------------------------------------------------------------------------
class GaussianNaiveBayes:
    def __init__(self) -> None:
        self.priors: dict[int, float] = {}
        self.means: dict[int, list[float]] = {}
        self.variances: dict[int, list[float]] = {}
        self.trained = False

    def fit(self, X: list[list[float]], y: list[int]) -> "GaussianNaiveBayes":
        by_class: dict[int, list[list[float]]] = defaultdict(list)
        for vec, label in zip(X, y):
            by_class[label].append(vec)

        total = len(X) or 1
        for label, rows in by_class.items():
            n = len(rows)
            self.priors[label] = n / total
            means, variances = [], []
            for j in range(N_FEATURES):
                column = [row[j] for row in rows]
                mu = sum(column) / n
                var = sum((v - mu) ** 2 for v in column) / n
                means.append(mu)
                variances.append(max(var, 1e-4))  # smoothing floor
            self.means[label] = means
            self.variances[label] = variances
        self.trained = bool(by_class)
        return self

    def _log_likelihood(self, vec: list[float], label: int) -> float:
        total = math.log(max(self.priors.get(label, 1e-9), 1e-9))
        means = self.means[label]
        variances = self.variances[label]
        for j in range(N_FEATURES):
            var = variances[j]
            diff = vec[j] - means[j]
            total += -0.5 * math.log(2 * math.pi * var) - (diff * diff) / (2 * var)
        return total

    def probability(self, vec: list[float]) -> float:
        """P(guilty | features), by normalising the two class log-likelihoods."""
        if not self.trained or 1 not in self.means or 0 not in self.means:
            return 0.5
        guilty = self._log_likelihood(vec, 1)
        innocent = self._log_likelihood(vec, 0)
        highest = max(guilty, innocent)
        g = math.exp(guilty - highest)
        i = math.exp(innocent - highest)
        return g / (g + i)


# --------------------------------------------------------------------------
# Logistic regression
# --------------------------------------------------------------------------
class LogisticRegression:
    def __init__(self, lr: float = 0.5, epochs: int = 400, l2: float = 0.01) -> None:
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.weights = [0.0] * N_FEATURES
        self.bias = 0.0
        self.trained = False

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        exp_z = math.exp(z)
        return exp_z / (1.0 + exp_z)

    def fit(self, X: list[list[float]], y: list[int]) -> "LogisticRegression":
        n = len(X)
        if n == 0:
            return self
        for _ in range(self.epochs):
            grad_w = [0.0] * N_FEATURES
            grad_b = 0.0
            for vec, label in zip(X, y):
                pred = self.predict_one(vec)
                err = pred - label
                for j in range(N_FEATURES):
                    grad_w[j] += err * vec[j]
                grad_b += err
            for j in range(N_FEATURES):
                grad_w[j] = grad_w[j] / n + self.l2 * self.weights[j]
                self.weights[j] -= self.lr * grad_w[j]
            self.bias -= self.lr * (grad_b / n)
        self.trained = True
        return self

    def predict_one(self, vec: list[float]) -> float:
        z = self.bias + sum(w * x for w, x in zip(self.weights, vec))
        return self._sigmoid(z)

    def contributions(self, vec: list[float]) -> list[tuple[str, float]]:
        """Per-feature signed contribution, for explaining a prediction."""
        pairs = [
            (FEATURE_NAMES[j], self.weights[j] * vec[j]) for j in range(N_FEATURES)
        ]
        return sorted(pairs, key=lambda p: -abs(p[1]))


# --------------------------------------------------------------------------
# The public model
# --------------------------------------------------------------------------
class DeductionEngine:
    """Ensemble of the two classifiers above, with leave-one-case-out training."""

    def __init__(self, corpus: list[Case]) -> None:
        self.corpus = corpus
        self._cache: dict[int, tuple[GaussianNaiveBayes, LogisticRegression]] = {}

    def _models(self, exclude_case_id: int) -> tuple[GaussianNaiveBayes, LogisticRegression]:
        if exclude_case_id in self._cache:
            return self._cache[exclude_case_id]
        training = [c for c in self.corpus if c.id != exclude_case_id]
        if len(training) < 2:
            training = self.corpus
        X, y = _training_rows(training)
        nb = GaussianNaiveBayes().fit(X, y)
        lr = LogisticRegression().fit(X, y)
        self._cache[exclude_case_id] = (nb, lr)
        return nb, lr

    def assess(self, case: Case, found: set[str], contradictions: set[str]) -> dict:
        """Rank the suspects and explain the ranking."""
        nb, lr = self._models(case.id)
        vectors = extract_features(case, found, contradictions)
        rule_based = compute_suspicion(case, found, contradictions)

        rows = []
        for suspect in case.suspects:
            vec = vectors[suspect.id]
            p_nb = nb.probability(vec)
            p_lr = lr.predict_one(vec)
            blended = 0.45 * p_nb + 0.55 * p_lr
            drivers = [
                {"feature": name, "impact": round(val, 3)}
                for name, val in lr.contributions(vec)[:3]
                if abs(val) > 0.02
            ]
            rows.append(
                {
                    "suspect_id": suspect.id,
                    "name": suspect.name,
                    "naive_bayes": round(p_nb, 4),
                    "logistic": round(p_lr, 4),
                    "confidence": round(blended, 4),
                    "rule_score": rule_based.get(suspect.id, 0),
                    "drivers": drivers,
                }
            )

        total = sum(r["confidence"] for r in rows) or 1.0
        for r in rows:
            r["share"] = round(100 * r["confidence"] / total, 1)
        rows.sort(key=lambda r: -r["confidence"])

        evidence_ratio = len(found) / max(1, case.total_evidence)
        return {
            "ranking": rows,
            "trained_on": len([c for c in self.corpus if c.id != case.id]),
            "samples": sum(
                len(c.suspects) for c in self.corpus if c.id != case.id
            ),
            "coverage": round(100 * evidence_ratio),
            "certainty": _certainty_label(rows, evidence_ratio),
        }

    def accuracy(self) -> dict:
        """Leave-one-case-out accuracy across the corpus. Used by the tests."""
        hits = 0
        for case in self.corpus:
            result = self.assess(
                case,
                {ev.id for ev in case.evidence},
                find_contradictions(case, {ev.id for ev in case.evidence}),
            )
            if result["ranking"] and result["ranking"][0]["suspect_id"] == case.culprit_id:
                hits += 1
        total = len(self.corpus) or 1
        return {"correct": hits, "total": total, "accuracy": round(hits / total, 3)}


def _certainty_label(rows: list[dict], coverage: float) -> str:
    if coverage < 0.35 or len(rows) < 2:
        return "Insufficient evidence"
    gap = rows[0]["confidence"] - rows[1]["confidence"]
    if coverage > 0.8 and gap > 0.25:
        return "Strong"
    if gap > 0.15:
        return "Moderate"
    if gap > 0.06:
        return "Weak"
    return "Inconclusive"
