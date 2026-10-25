from eventbot.pipeline.classify import detect_audience, detect_cities, detect_type, looks_it_related


def test_types():
    assert detect_type("Хакатон по ML") == "hackathon"
    assert detect_type("Yandex Cup 2026") == "hackathon"
    assert detect_type("Practical ML Conf") == "conference"
    assert detect_type("Frontend Meetup") == "meetup"
    assert detect_type("Data Dojo") == "meetup"
    assert detect_type("Week Offer Security") == "other"
    # тип по названию важнее контекста
    assert detect_type("Хакатон", "после конференции") == "hackathon"


def test_audience():
    assert detect_audience("Я про бэкенд") == ["dev"]
    assert detect_audience("Weekend Offer ML") == ["data"]
    assert detect_audience("Product Camp для продакт-менеджеров") == ["pm"]
    assert detect_audience("Конференция") == []


def test_cities():
    assert detect_cities("Москва и онлайн") == ["msk", "online"]
    assert detect_cities("встречаемся в Санкт-Петербурге") == ["spb"]
    assert detect_cities("офис в СПб") == ["spb"]
    assert detect_cities("без места") == []


def test_it_related():
    assert looks_it_related("Митап Python-разработчиков")
    assert looks_it_related("ИТ и интернет")
    assert not looks_it_related("Мастер-класс по керамике")
