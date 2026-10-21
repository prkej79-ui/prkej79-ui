"""검증된 계획의 표 표현. 이동 시간은 만들지 않고 방문 시간·체류 시간은 제안으로 표시합니다."""

from datetime import date

from weather_tools import WeatherError, resolve_dates


def build_chat_itinerary_rows(turn: dict) -> list[dict]:
    """기존 채팅의 코스도 마지막 지도 결과만 사용해 표로 표시합니다."""
    from chat_flow import answer_places

    if not turn.get("is_itinerary"):
        return []
    reference = turn.get("itinerary_reference_date", "")
    # 과거 대화에 기준일이 없으면 상대 날짜를 오늘 기준으로 재해석하지 않습니다.
    question = turn.get("question", "") if reference else ""
    return build_itinerary_rows({
        "input": {"travel_date": question},
        "B": {"status": "not_queried", "execution": {"weather_reference_date": reference}},
        "plan": {"facts": {"places": answer_places(turn), "weather": []},
                 "suggestions": {"schedule": turn.get("stops", [])}},
    })


def build_itinerary_rows(result: dict) -> list[dict]:
    plan = result["plan"]
    places = plan["facts"].get("places", [])
    weather = {row["date"]: row for row in plan["facts"].get("weather", [])}
    execution = result["B"]["execution"]
    try:
        reference = date.fromisoformat(execution["weather_reference_date"]) if execution.get("weather_reference_date") else None
        dates = [day.isoformat() for day in resolve_dates(result["input"]["travel_date"], reference)]
    except (WeatherError, ValueError):
        dates = []
    rows = []
    for stop in plan["suggestions"].get("schedule", []):
        index = stop["place_index"] - 1
        if not 0 <= index < len(places):
            continue
        place = places[index]
        day_index = stop["day"] - 1
        day = dates[day_index] if 0 <= day_index < len(dates) else ""
        day_label = f"{day} ({'월화수목금토일'[date.fromisoformat(day).weekday()]})" if day else f"{stop['day']}일차 (날짜 미정)"
        forecast = weather.get(day)
        if forecast:
            def value(key, unit):
                number = forecast.get(key)
                return "미제공" if number is None else f"{number}{unit}"
            weather_label = f"최고 {value('high_c', '°C')} / 최저 {value('low_c', '°C')} · 강수 {value('rain_probability_pct', '%')}"
        elif plan.get("warnings"):
            weather_label = "확인 필요 (지역·날짜 검증)"
        elif result["B"]["status"] == "out_of_range":
            weather_label = "예보 없음 (범위 밖)"
        elif not day:
            weather_label = "날짜 확인 필요"
        else:
            weather_label = "확인 필요 (예보 없음)"
        category = place.get("category", "")
        minutes = 90 if any(kind in category for kind in ("박물관", "미술관", "관광", "식물원", "수목원")) else 60
        hour = {"오전": 10, "점심": 12, "오후": 14, "늦은 오후": 16, "저녁": 18}.get(stop["time"])
        end_hour, end_minute = divmod(hour * 60 + minutes, 60) if hour is not None else (None, None)
        visit_time = f"{hour:02d}:00–{end_hour:02d}:{end_minute:02d} (제안)" if hour is not None else f"{stop['time']} (제안)"
        first_of_day = not rows or rows[-1]["일자"] != day_label
        rows.append({"일자": day_label, "이동 시간": "— (첫 방문)" if first_of_day else "미조회",
                     "장소": place["name"], "예상 방문 시간": visit_time,
                     "체류 소요시간": f"약 {minutes}분 (제안)", "날씨": weather_label, "지도": place["url"]})
    return rows
