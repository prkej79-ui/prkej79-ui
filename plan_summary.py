"""조회 사실과 제안을 분리한 여행 계획. 자유 생성으로 사실을 추가하지 않습니다."""

import re

from planner import preparations
from research_validation import validate_research
from evidence_flow import build_evidence_flow


def escape(text):
    return re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", str(text))


def build_plan_summary(result: dict) -> dict:
    shared = result["input"]
    a, b = result["A"], result["B"]
    validation = validate_research(result)
    places, weather = validation["places"], validation["weather"]
    sources = [{"name": place["name"], "url": place["url"]} for place in places]
    sources += [{"name": "Open-Meteo", "url": url} for url in sorted({row["source"] for row in weather})]
    facts = {"places": places, "weather": weather}
    tips = preparations(weather)
    schedule = []
    time_slots = ("오전", "오후", "늦은 오후")
    days = [row["date"] for row in weather]
    count = min(len(places), max(1, len(days)) * 3)
    for i, place in enumerate(places[:count]):
        schedule.append({"day": i // 3 + 1, "time": time_slots[i % 3], "place_index": i + 1})

    lines = [f"### {escape(shared['region'])} 여행 계획",
             f"입력 조건: 날짜 **{escape(shared['travel_date'] or '미정')}** · 취향·동행인 **{escape(shared['tastes'] or '별도 조건 없음')}**."]
    if places:
        lines += ["조회된 장소를 아래 순서와 시간대로 방문하는 일정을 제안합니다. 방문 순서와 시간대는 확정 정보가 아닙니다.",
                  "입력한 취향·동행 조건에 각 장소가 적합한지는 별도 확인이 필요합니다.",
                  "#### 방문 순서·시간대 제안"]
        for day_number in sorted({item["day"] for item in schedule}):
            day = days[day_number - 1] if days else f"{day_number}일차"
            sentences = []
            for item in (stop for stop in schedule if stop["day"] == day_number):
                place = places[item["place_index"] - 1]
                sentences.append(f"{item['time']}에는 [{escape(place['name'])}]({place['url']})에 방문하는 것을 제안합니다.")
            lines.append(f"**{day} (일정 제안)**: " + " ".join(sentences))
        if len(places) > count:
            lines.append("나머지 조회 장소는 아래 대체 후보로 두고 관심에 따라 바꿔 방문할 수 있습니다.")
    else:
        if a["status"] == "error":
            lines.append("**장소 조회 실패**: 장소 인증 또는 검색 오류로 일정을 만들지 않았습니다. 아래의 유효한 날씨 결과는 별도로 확인할 수 있습니다.")
        else:
            lines.append("지도에서 확인한 장소가 없어 방문 순서를 구성하지 않았습니다. 지역과 검색 조건을 바꿔 다시 조사해 주세요.")
    lines.append("#### 조회 사실 · 장소와 출처")
    for place in places:
        lines.append(f"- [{escape(place['name'])}]({place['url']}): {escape(place['address'])}. 출처: 카카오 장소 검색.")
    if not places:
        lines.append("확인된 장소 없음.")
    lines.append("#### 조회 사실 · 날씨")
    if weather:
        def shown(value, unit):
            return "미제공" if value is None else f"{value}{unit}"
        for row in weather:
            lines.append(f"- **{row['date']}({row['weekday']})**: 최고 {shown(row['high_c'], '°C')}, "
                         f"최저 {shown(row['low_c'], '°C')}, 최대 강수확률 {shown(row['rain_probability_pct'], '%')}. "
                         f"[Open-Meteo]({row['source']}) · 조회 시각(KST): {row['fetched_at']}.")
        location = b["execution"].get("weather_location", {})
        lines.append(f"날씨 조회 기준: {escape(location.get('name', ''))} · 위도 {weather[0]['latitude']}, 경도 {weather[0]['longitude']}. 지역 전체의 모든 장소가 같은 날씨라는 뜻은 아닙니다.")
    else:
        reason = "날씨·준비물 확인 필요: 조사 결과의 지역 또는 날짜·좌표가 일치하지 않아 해당 날씨를 근거에서 제외했습니다." if validation["warnings"] else {"out_of_range": "예보 없음 — 확인 필요: 요청 날짜가 예보 범위 밖이므로 예보가 없습니다.",
                  "date_mismatch": "반환 날짜가 요청 날짜와 달라 날씨 값을 사용하지 않았습니다.",
                  "needs_date": "날씨·준비물 확인 필요: 날짜가 정해지지 않아 날씨를 조회하지 않았습니다."}.get(b["status"], "날씨·준비물 확인 필요: 날씨 조회 실패로 요청 날짜의 예보를 확인하지 못했습니다.")
        lines.append(reason + " 다른 날짜나 현재 날씨로 대신 채우지 않았습니다.")
    lines.append("#### 준비물 제안")
    lines.extend([f"- {tip}" for tip in tips] or ["확인된 예보로부터 추가할 기상 관련 준비물 제안이 없습니다."])
    lines.append("영업시간·구간별 이동 시간은 조회하지 않아 계획에 넣지 않았습니다. 장소의 실내 여부·메뉴·주차 등 미확인 조건은 방문 전 확인해 주세요.")
    status = "warning" if validation["warnings"] else "ok" if places and weather else "partial"
    return {"status": status, "text": "\n\n".join(lines),
            "facts": facts, "suggestions": {"schedule": schedule, "preparations": tips}, "source": sources,
            "warnings": validation["warnings"], "validation": {key: value for key, value in validation.items() if key not in ("places", "weather")},
            "evidence_flow": build_evidence_flow(result, validation, facts, status, sources)}
