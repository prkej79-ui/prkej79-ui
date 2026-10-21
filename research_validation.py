"""종합 전 공통 입력·실제 지역·예보 날짜·좌표 출처의 일치 검사."""

from datetime import date
from math import isclose

from chat_flow import answer_places
from weather_tools import WeatherError, coordinates, resolve_dates, today_kst
from regions import region_matches


def validate_research(result: dict) -> dict:
    shared, a, b = result["input"], result["A"], result["B"]
    warnings, codes = [], []

    def warn(code, message):
        if code not in codes:
            codes.append(code)
            warnings.append(message)

    for key, role in (("A", a), ("B", b)):
        if role["input"] != shared:
            warn(f"{key}_input_mismatch", f"{key} 조사 입력이 공통 지역·날짜·취향과 일치하지 않습니다.")
    raw_places = answer_places(a["execution"]) if a["status"] == "ok" else []
    places = [p for p in raw_places if region_matches(shared["region"], p.get("address", ""))]
    if len(places) != len(raw_places):
        warn("place_region_mismatch", "요청 지역과 다른 장소 결과를 최종 계획에서 제외했습니다.")
    execution = b["execution"]
    traces = execution.get("traces", [])
    last = traces[-1] if traces else {}
    weather = last.get("결과", []) if b["status"] == "ok" and last.get("결과 종류") == "weather" else []
    if b["status"] == "date_mismatch":
        warn("weather_date_mismatch", "날씨 API가 반환한 날짜가 요청 날짜와 일치하지 않습니다.")
    if b["status"] == "ok":
        location = execution.get("weather_location", {})
        if not region_matches(execution.get("region", ""), location.get("address", "")) or not region_matches(shared["region"], location.get("address", "")):
            warn("weather_region_mismatch", "장소 조사 지역과 날씨 조회 지역이 일치하지 않습니다.")
        try:
            reference = date.fromisoformat(execution["weather_reference_date"]) if execution.get("weather_reference_date") else today_kst()
            expected = [day.isoformat() for day in resolve_dates(shared["travel_date"], reference)]
        except (WeatherError, ValueError):
            expected = []
        returned = [row.get("date") for row in weather]
        if not expected or not all(isinstance(day, str) for day in returned) or sorted(returned) != expected or sorted(execution.get("weather_dates", [])) != expected:
            warn("weather_date_mismatch", "여행 날짜와 날씨 결과 날짜가 일치하지 않습니다.")
        try:
            lat, lon = coordinates(location)
            if not weather or any(not isclose(float(row["latitude"]), lat, abs_tol=1e-7) or
                                  not isclose(float(row["longitude"]), lon, abs_tol=1e-7) for row in weather):
                warn("weather_coordinate_mismatch", "날씨 결과 좌표가 카카오 장소 검색의 좌표와 일치하지 않습니다.")
        except (WeatherError, KeyError, ValueError, TypeError):
            warn("weather_coordinate_mismatch", "날씨 조회 좌표의 출처를 확인할 수 없습니다.")
    usable = bool(weather) and not codes
    return {"status": "warning" if warnings else "ok", "warnings": warnings, "codes": codes,
            "weather_usable": usable, "places": places, "weather": weather if usable else []}
