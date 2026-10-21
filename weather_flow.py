"""날짜 확인 → 카카오 좌표 → Open-Meteo 조회 순서를 강제합니다."""

from datetime import date
import weather_tools
from regions import region_matches

from weather_tools import WeatherError, coordinates, fetch_weather, resolve_dates, validate_forecast_dates


def run_weather(result, question, plan, history, tool_call):
    result["is_weather"] = True
    reference = weather_tools.today_kst()
    result["weather_reference_date"] = reference.isoformat()
    dates = resolve_dates(question, reference)
    if not dates and history and history[-1].get("awaiting_weather_region"):
        dates = [date.fromisoformat(value) for value in history[-1].get("weather_dates", [])]
    result["weather_dates"] = [day.isoformat() for day in dates]
    if not dates:
        result.update(message="언제의 날씨를 확인할까요? 오늘, 내일, 이번 주 토요일 또는 YYYY-MM-DD 형식으로 알려주세요.",
                      end_reason="날씨 날짜 확인 필요: 도구 호출 없이 종료", awaiting_weather_date=True,
                      weather_status="needs_date", status="needs_date")
        return result
    validate_forecast_dates(dates)
    if not plan.region.strip():
        result.update(message="어느 지역의 날씨를 확인할까요?", end_reason="날씨 지역 확인 필요",
                      awaiting_weather_region=True)
        return result
    from kakao_search import search_places

    def coordinate_search(query, entry):
        records = search_places(query)
        return [p for p in records if region_matches(plan.region, p["address"])
                and p["url"].startswith(("https://place.map.kakao.com/", "http://place.map.kakao.com/"))]

    query = plan.query.strip() or plan.region
    # 날짜·취향 문장이 아닌 장소 검색 인자로만 좌표를 찾습니다.
    if any(word in query for word in ("날씨", "기온", "강수", "요일", "내일", "오늘")):
        query = plan.region
    if plan.region not in query:
        query = f"{plan.region} {query}"
    places = tool_call("카카오 날씨 기준 장소 검색", query, coordinate_search, plan.region, "날씨 기준 위치", "날씨 조회에 필요한 실제 장소 좌표 확보")
    entry = result["traces"][-1]
    if not places:
        entry.update({"다음 동작": "종료", "판정 근거": "지역에 일치하는 지도 결과 없음"})
        result.update(message="날씨 조회에 사용할 장소를 찾지 못했습니다. 지역명 또는 정확한 장소명을 알려주세요.", end_reason="날씨 좌표 검색 결과 없음")
        return result
    candidates = []
    for place in places:
        try:
            lat, lon = coordinates(place)
            candidates.append((place, lat, lon))
        except WeatherError:
            continue
    if not candidates:
        entry.update({"다음 동작": "종료", "판정 근거": "검색 결과의 좌표 누락 또는 오류"})
        raise WeatherError("카카오 검색 결과에 유효한 좌표가 없습니다. 좌표를 추측하지 않고 조회를 중단했습니다.")
    place, latitude, longitude = candidates[0]
    result["weather_location"] = place
    if len(result["traces"]) >= result["tool_limit"]:
        entry.update({"다음 동작": "종료", "판정 근거": "호출 한도 도달: 좌표만 확인, 날씨 API 미호출"})
        result.update(message="장소 좌표는 확인했지만 호출 한도에 도달해 날씨를 조회하지 않았습니다.", end_reason="호출 한도 도달")
        return result
    entry.update({"다음 동작": "날씨 조회", "판정 근거": "카카오 검색 결과의 유효한 좌표 확보"})

    def weather_query(_, trace):
        trace["결과 종류"] = "weather"
        trace["인자"] = {"latitude": latitude, "longitude": longitude,
                         "날짜": result["weather_dates"], "timezone": "Asia/Seoul",
                         "출처": "https://api.open-meteo.com/v1/forecast"}
        records = fetch_weather(latitude, longitude, dates)
        returned = [row.get("date") for row in records]
        if any(not isinstance(day, str) for day in returned) or sorted(returned) != result["weather_dates"]:
            raise WeatherError("날짜 확인 필요: 반환 날짜가 요청 날짜와 달라 날씨 값을 표시하지 않습니다.",
                               "date_mismatch", {"요청 날짜": result["weather_dates"], "반환 날짜": returned})
        return records

    records = tool_call("Open-Meteo 일별 날씨 조회", "", weather_query, plan.region, "날씨", "지도에서 반환된 좌표와 계산된 날짜로 예보 조회")
    result["traces"][-1].update({"다음 동작": "답변", "판정 근거": "요청 날짜의 기온·강수확률 반환"})
    result.update(weather=records, message="선택한 날짜의 일별 예보입니다. 조회 기준 장소와 날짜를 확인해 주세요.",
                  end_reason="Open-Meteo 반환 날짜 일치 확인 후 날씨 답변", weather_status="ok", status="ok")
    return result
