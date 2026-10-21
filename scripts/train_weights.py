"""Обучение весов подбора по истории приглашений (логистическая регрессия).

Вопрос, на который отвечает: «Кого из приглашённых стоит звать первым, чтобы человек подтвердил и пришёл?»
Учимся на старых приглашениях, проверяем на последних четырёх месяцах и сравниваем с ручными весами.

Данные пока синтетические (scripts/generate_synthetic_shifts.py), поэтому результат показывает, что
конвейер работает и умеет восстановить поведение из истории. Настоящие веса появятся на данных фонда.

    python3 scripts/train_weights.py
"""
import csv
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from matching_features import FEATURES, HAND_WEIGHTS      # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / 'materials/05-продукт/данные'
SPLIT = '2026-06-21'       # учимся на том, что было раньше, проверяем на последних четырёх месяцах


def load():
    rows = list(csv.DictReader(open(DATA / 'synthetic-invitations.csv', encoding='utf-8')))
    X = np.array([[float(r[k]) for k in FEATURES] for r in rows])
    y = np.array([int(r['attended']) for r in rows])
    old = np.array([r['date'] < SPLIT for r in rows])
    return X, y, old, rows


def fit(X, y, l2=0.01, steps=4000, lr=0.5):
    """Логистическая регрессия градиентным спуском: P(пришёл) = σ(b + Σ wᵢ·признакᵢ)."""
    w, b = np.zeros(X.shape[1]), 0.0
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = p - y
        w -= lr * (X.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return w, b


def auc(score, y):
    """Вероятность того, что случайный пришедший стоит в списке выше случайного не пришедшего."""
    order = np.argsort(score)
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    pos = y == 1
    return (ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())


def main():
    X, y, old, rows = load()
    w, b = fit(X[old], y[old])
    hand = X @ np.array([HAND_WEIGHTS[k] for k in FEATURES])
    learned = X @ w + b
    test = ~old
    # Потолок: насколько хорошо ранжировала бы сама скрытая модель поведения из симуляции
    import generate_synthetic_shifts as sim
    oracle = np.array([sim.ENGAGE[r['segment']] + sum(sim.TRUE_CONFIRM[k] * float(r[k]) for k in FEATURES) for r in rows])
    share = np.clip(w, 0, None) / np.clip(w, 0, None).sum()
    result = {
        'train_invitations': int(old.sum()), 'test_invitations': int(test.sum()),
        'attended_rate': round(float(y.mean()), 3),
        'auc_hand_weights': round(float(auc(hand[test], y[test])), 3),
        'auc_learned_weights': round(float(auc(learned[test], y[test])), 3),
        'auc_ceiling_true_model': round(float(auc(oracle[test], y[test])), 3),
        'hand_weights': HAND_WEIGHTS,
        'learned_weights_share': {k: round(float(s), 2) for k, s in zip(FEATURES, share)},
        'learned_coefficients': {k: round(float(c), 2) for k, c in zip(FEATURES, w)},
    }
    (DATA / 'learned-weights.json').write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n')
    print(f'Учились на {result["train_invitations"]} приглашениях, проверяли на {result["test_invitations"]}; пришли {result["attended_rate"]:.0%} приглашённых')
    print(f'Качество порядка (AUC, 0.5 — случайно, 1 — идеально): ручные веса {result["auc_hand_weights"]}, обученные {result["auc_learned_weights"]}, потолок {result["auc_ceiling_true_model"]}')
    print('Признак       ручной вес   обученная доля')
    for k in FEATURES:
        print(f'  {k:12} {HAND_WEIGHTS[k]:>8.2f}   {result["learned_weights_share"][k]:>10.2f}')


if __name__ == '__main__':
    main()
