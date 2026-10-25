"""Поиск дубликатов: одно и то же событие из разных источников."""
from __future__ import annotations

from typing import Protocol, Sequence, TypeVar

from rapidfuzz import fuzz

from eventbot.pipeline.normalize import norm_key

THRESHOLD = 88


class _HasTitleDate(Protocol):
    title: str
    starts_at: object


T = TypeVar("T", bound=_HasTitleDate)


def similarity(a: str, b: str) -> float:
    ka, kb = norm_key(a), norm_key(b)
    if not ka or not kb:
        return 0.0
    score = fuzz.token_sort_ratio(ka, kb)
    # token_set_ratio даёт 100, если одно название — подмножество другого.
    # Для однословных названий это слишком щедро («Data» vs «Data Driven»).
    if min(len(ka.split()), len(kb.split())) >= 2:
        score = max(score, fuzz.token_set_ratio(ka, kb))
    return score


def same_day(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs((a - b).total_seconds()) <= 36 * 3600


def find_duplicate(item: _HasTitleDate, candidates: Sequence[T]) -> T | None:
    best, best_score = None, 0.0
    for c in candidates:
        if not same_day(item.starts_at, c.starts_at):
            continue
        s = similarity(item.title, c.title)
        if s >= THRESHOLD and s > best_score:
            best, best_score = c, s
    return best
