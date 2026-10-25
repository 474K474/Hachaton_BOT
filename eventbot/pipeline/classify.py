"""Разметка событий правилами: тип, аудитория, город.

v1 — словари ключевых слов. Сюда же позже встанет LLM-разметка для спорных случаев.
"""
from __future__ import annotations

import re

_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("hackathon", [
        r"хакатон", r"hackathon", r"\bcup\b", r"контест", r"contest", r"чемпионат",
        r"олимпиад", r"\bctf\b", r"соревновани",
    ]),
    ("conference", [
        r"конференц", r"\bconf\b", r"conference", r"саммит", r"summit", r"форум", r"forum",
        r"фестивал", r"\bfest\b", r"\bnight\b", r"\bdays?\b", r"\bдни\b", r"\bdriven\b",
    ]),
    ("meetup", [
        r"митап", r"meetup", r"meet\s?up", r"встреч", r"воркшоп", r"workshop",
        r"мастер-класс", r"открыт\w* лекци", r"\bdojo\b", r"\bмит\b",
    ]),
]

_AUDIENCE_RULES: dict[str, list[str]] = {
    "dev": [
        r"бэкенд", r"бекенд", r"backend", r"фронтенд", r"frontend", r"разработ", r"developer",
        r"программ", r"python", r"\bjava\b", r"golang", r"kotlin", r"swift", r"\bios\b",
        r"android", r"мобильн", r"mobile", r"devops", r"\bsre\b", r"инфраструктур",
        r"security", r"безопасност", r"\bqa\b", r"тестировани", r"highload", r"архитектур",
        r"c\+\+", r"\brust\b", r"javascript", r"\bjs\b", r"react", r"deep tech", r"алгоритм",
        r"\bcode\b", r"кодинг", r"cloud", r"облач", r"базы данных", r"database",
    ],
    "data": [
        r"\bml\b", r"machine learning", r"машинн\w* обучени", r"\bdata\b", r"данны[хм]",
        r"\bai\b", r"\bии\b", r"нейросет", r"\bllm\b", r"\bnlp\b", r"computer vision",
        r"рекомендательн", r"аналитик", r"analytics",
    ],
    "pm": [
        r"продукт", r"product", r"\bpm\b", r"проджект", r"project", r"менеджм", r"management",
        r"менеджер", r"manager", r"agile", r"scrum", r"тимлид", r"team\s?lead", r"руковод",
        r"\bcto\b", r"\bcpo\b", r"delivery", r"управлени\w* (?:проект|команд|продукт)",
    ],
}

_CITY_RULES: dict[str, list[str]] = {
    "spb": [r"санкт-петербург", r"петербург", r"\bспб\b", r"питер", r"\bspb\b", r"petersburg"],
    "msk": [r"москв", r"\bмск\b", r"moscow"],
    "online": [r"онлайн", r"online", r"трансляци", r"\bzoom\b", r"дистанционн"],
}


def _hit(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def detect_type(title: str, context: str = "") -> str:
    for text in (title, context):
        for etype, patterns in _TYPE_RULES:
            if _hit(text, patterns):
                return etype
    return "other"


def detect_audience(text: str) -> list[str]:
    return sorted(a for a, patterns in _AUDIENCE_RULES.items() if _hit(text, patterns))


def detect_cities(text: str) -> list[str]:
    return sorted(c for c, patterns in _CITY_RULES.items() if _hit(text, patterns))


_IT_MARKERS = _AUDIENCE_RULES["dev"] + _AUDIENCE_RULES["data"] + [
    r"\bит\b", r"\bit\b", r"айти", r"tech", r"технолог", r"хакатон", r"hackathon",
]


def looks_it_related(text: str) -> bool:
    """Для агрегаторов общего профиля (Timepad): отсеять не-IT."""
    return _hit(text, _IT_MARKERS)
