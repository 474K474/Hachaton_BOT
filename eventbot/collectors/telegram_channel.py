"""Публичные Telegram-каналы через веб-превью t.me/s/<channel> — без авторизации.

Яндекс анонсирует события для разработчиков в @Yandex4Developers, часто дайджестом:
несколько событий в одном посте, по строке на каждое. Поэтому пост режется на
«чанки» вокруг строк с датами, и каждый чанк превращается в отдельное событие.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, Tag

from eventbot.collectors.base import Collector
from eventbot.domain import RawEvent
from eventbot.pipeline.dates import DateMatch, first_date
from eventbot.pipeline.normalize import clean_title
from eventbot.timeutil import local_to_utc

log = logging.getLogger(__name__)

_EVENT_HINT = re.compile(
    r"регистрац|митап|meetup|конференц|\bconf\b|хакатон|hackathon|событи|приходите|"
    r"ждём|ждем|трансляци|\bcup\b|offer|дайджест|встреч|воркшоп|workshop",
    re.I,
)
_LINK = re.compile(r"⟦(.*?)⟧")
_STOP_TITLE = re.compile(
    r"^(регистраци\w*|зарегистрир\w*|подробнее|ссылка|по ссылке|программа|участвовать)$"
    # строка, состоящая только из места и формата: «Москва и онлайн», «в СПб»
    r"|^(?:(?:в|во|и|или|а также|\+|/)\s*|(?:москв\w*|санкт-петербург\w*|петербург\w*|спб|питер\w*|"
    r"онлайн|офлайн|оффлайн|online|offline|гибридн\w*|формат\w*)\s*)+$",
    re.I,
)
_HEADER = re.compile(
    r"ближайш\w* (?:событи|мероприяти)|дайджест|^анонс\w*$|что почитать|что посмотреть|подборк|"
    r"^события\b",
    re.I,
)
_TITLE_SPLIT = re.compile(r"\s*(?:[,.;|]|\s[—–-]\s)\s*")


@dataclass
class Post:
    id: int
    url: str
    published: datetime  # aware
    lines: list[tuple[str, list[str]]]  # (текст строки, ссылки в строке)

    @property
    def text(self) -> str:
        return "\n".join(t for t, _ in self.lines)


class TelegramChannelCollector(Collector):
    delay = 2.0

    def __init__(self, channel: str, organizer: str, client: httpx.AsyncClient, tz: ZoneInfo, pages: int = 2):
        super().__init__(client)
        self.channel = channel
        self.organizer = organizer
        self.tz = tz
        self.pages = pages
        self.name = f"tg:{channel}"

    async def fetch(self) -> list[RawEvent]:
        posts: list[Post] = []
        before: int | None = None
        for _ in range(self.pages):
            params = {"before": before} if before else None
            resp = await self.get(f"https://t.me/s/{self.channel}", params=params)
            page = parse_channel_page(resp.text)
            if not page:
                break
            posts.extend(page)
            before = min(p.id for p in page)
        events: list[RawEvent] = []
        for post in posts:
            events.extend(extract_events(post, self.tz, self.organizer, self.name))
        return events


# ---------- парсинг HTML ----------

def parse_channel_page(html: str) -> list[Post]:
    soup = BeautifulSoup(html, "lxml")
    posts: list[Post] = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        data_post = msg.get("data-post", "")
        try:
            post_id = int(data_post.rsplit("/", 1)[1])
        except (IndexError, ValueError):
            continue
        text_div = msg.select_one("div.tgme_widget_message_text")
        time_tag = msg.select_one("a.tgme_widget_message_date time[datetime]") or msg.select_one("time[datetime]")
        if text_div is None or time_tag is None:
            continue
        try:
            published = datetime.fromisoformat(time_tag["datetime"])
        except ValueError:
            continue
        posts.append(Post(
            id=post_id,
            url=f"https://t.me/{data_post}",
            published=published,
            lines=_lines_with_links(text_div),
        ))
    return posts


def _lines_with_links(div: Tag) -> list[tuple[str, list[str]]]:
    div = BeautifulSoup(str(div), "lxml").select_one("div")  # копия, чтобы не портить исходник
    for br in div.find_all("br"):
        br.replace_with("\n")
    for a in div.find_all("a"):
        href = a.get("href", "")
        a.replace_with(f"{a.get_text()} ⟦{href}⟧" if _good_link(href) else a.get_text())
    lines = []
    for raw_line in div.get_text().split("\n"):
        links = _LINK.findall(raw_line)
        text = re.sub(r"\s+", " ", _LINK.sub("", raw_line)).strip()
        if text or links:
            lines.append((text, links))
    return lines


def _good_link(href: str) -> bool:
    if not href or href.startswith("?") or href.startswith("#"):
        return False
    # ссылки на хэштеги и сам канал не являются ссылками на событие
    return not re.match(r"https?://t\.me/(s/)?[^/]+/?(\?.*)?$", href)


# ---------- извлечение событий из поста ----------

def extract_events(post: Post, tz: ZoneInfo, organizer: str, source: str) -> list[RawEvent]:
    if not _EVENT_HINT.search(post.text):
        return []
    ref = post.published.astimezone(tz).replace(tzinfo=None)
    dated = [(i, d) for i, (text, _) in enumerate(post.lines) if (d := first_date(text, ref))]
    if not dated:
        return []

    if len(dated) == 1:
        return [_single_event(post, dated[0], tz, organizer, source)]

    # Сначала для каждой строки с датой находим строку с названием:
    # это либо она сама, либо строка над ней («Practical ML Conf» / «19 сентября, …»).
    dated_lines = {i for i, _ in dated}
    items: list[tuple[int, int, str, DateMatch]] = []  # (title_line, date_line, title, date)
    for i, d in dated:
        title, title_line = _title_from_line(post.lines[i][0], d), i
        if not title and i > 0 and (i - 1) not in dated_lines:
            title, title_line = _usable(clean_title(post.lines[i - 1][0])), i - 1
        if title:
            items.append((title_line, i, title, d))

    events = []
    for n, (title_line, i, title, d) in enumerate(items):
        # чанк события: от его названия до названия следующего, но не длиннее 3 строк
        end = items[n + 1][0] if n + 1 < len(items) else len(post.lines)
        end = min(end, i + 2)
        chunk = post.lines[title_line:end]
        url = _first_link(chunk) or post.url
        chunk_text = "\n".join(t for t, _ in chunk)
        events.append(_make(title, url, d, tz, organizer, source, chunk_text, chunk_text))
    return events


def _single_event(post: Post, item: tuple[int, DateMatch], tz, organizer, source) -> RawEvent:
    i, d = item
    # Если дата в первой строке — название обычно там же; иначе заголовок поста
    title = _title_from_line(post.lines[i][0], d) if i == 0 else ""
    if not title:
        title = next((_usable(clean_title(t)) for t, _ in post.lines if _usable(clean_title(t))), "")
    url = _first_link(post.lines) or post.url
    text = post.text
    return _make(title or "Событие", url, d, tz, organizer, source, text[:600], text)


def _make(title, url, d: DateMatch, tz, organizer, source, description, context) -> RawEvent:
    return RawEvent(
        title=title,
        url=url,
        source=source,
        starts_at=local_to_utc(d.start, tz),
        ends_at=local_to_utc(d.end, tz) if d.end else None,
        time_known=d.time_known,
        organizer=organizer,
        city_hint=context,
        description=description,
        extra_text=context,
    )


def _title_from_line(line: str, d: DateMatch) -> str:
    before = clean_title(line[: d.span[0]])
    if _usable(before):
        return _usable(before)
    after = line[d.span[1]:]
    after = re.sub(r"^\s*(?:в|с)?\s*\d{1,2}[:.]\d{2}(?:\s*[–—-]\s*\d{1,2}[:.]\d{2})?", "", after)
    for part in _TITLE_SPLIT.split(after):
        cand = _usable(clean_title(part))
        if cand:
            return cand
    return ""


def _usable(title: str) -> str:
    t = title.strip()
    if len(t) < 3 or _STOP_TITLE.match(t) or _HEADER.search(t):
        return ""
    return t


def _first_link(lines: list[tuple[str, list[str]]]) -> str | None:
    for _, links in lines:
        for link in links:
            return link
    return None
