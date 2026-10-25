from datetime import datetime

from eventbot.pipeline.dates import find_dates, first_date

REF = datetime(2026, 9, 1)


def test_single_day():
    d = first_date("Data Dojo — 9 сентября, регистрация", REF)
    assert d.start == datetime(2026, 9, 9) and d.end is None and not d.time_known


def test_day_with_time():
    d = first_date("3 октября в 19:00 — митап", REF)
    assert d.start == datetime(2026, 10, 3, 19, 0) and d.time_known


def test_time_range():
    d = first_date("12 ноября, 19:00–22:00", REF)
    assert d.start == datetime(2026, 11, 12, 19) and d.end == datetime(2026, 11, 12, 22)


def test_range_same_month():
    d = first_date("Week Offer — 12–18 сентября", REF)
    assert d.start == datetime(2026, 9, 12) and d.end == datetime(2026, 9, 18)


def test_range_cross_month():
    d = first_date("Хакатон 30 сентября – 2 октября", REF)
    assert d.start == datetime(2026, 9, 30) and d.end == datetime(2026, 10, 2)


def test_explicit_year_and_numeric():
    assert first_date("5 марта 2027", REF).start == datetime(2027, 3, 5)
    assert first_date("старт 05.11.2026", REF).start == datetime(2026, 11, 5)


def test_year_rollover():
    # в декабре «15 января» — это уже следующий год
    d = first_date("15 января", datetime(2026, 12, 10))
    assert d.start == datetime(2027, 1, 15)


def test_no_false_positives():
    assert find_dates("Python 3.12 и 20 докладов", REF) == []
    assert first_date("31 февраля", REF) is None


def test_multiple_dates_in_order():
    dates = find_dates("5 сентября — одно, 19 сентября — другое", REF)
    assert [d.start.day for d in dates] == [5, 19]
