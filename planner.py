"""하나의 공통 입력을 사용하는 독립적인 장소·날씨 조사 역할."""

from pydantic import BaseModel, ConfigDict, Field

from chat_flow import RequestPlan, answer_places, run_turn
from web_research import attach_web_research


class PlannerInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    region: str = Field(min_length=1)
    travel_date: str = ""
    tastes: str = ""


def preparations(weather: list[dict]) -> list[str]:
    """확인된 예보 수치에 근거한 간단한 준비물 제안. 예보가 없으면 만들지 않습니다."""
    tips = []
    if any(row.get("rain_probability_pct") is not None and row["rain_probability_pct"] >= 40 for row in weather):
        tips.append("최대 강수확률 40% 이상인 날이 있어 우산이나 우비를 준비하는 편이 좋습니다.")
    if any(row.get("low_c") is not None and row["low_c"] <= 10 for row in weather):
        tips.append("최저기온 10°C 이하인 날이 있어 따뜻한 겉옷을 준비하는 편이 좋습니다.")
    if any(row.get("high_c") is not None and row["high_c"] >= 28 for row in weather):
        tips.append("최고기온 28°C 이상인 날이 있어 물과 모자를 준비하는 편이 좋습니다.")
    return tips


def run_planner(region: str, travel_date: str, tastes: str, llm_factory, *, include_web=False) -> dict:
    # 실행할 때마다 새로 생성합니다. 이전 지역·날짜를 세션 또는 역할 결과에서 가져오지 않습니다.
    shared = PlannerInput(region=region.strip(), travel_date=travel_date.strip(), tastes=tastes.strip())
    keyword = next((kind for kind in ("카페", "식당", "숙소", "박물관", "미술관") if kind in shared.tastes), "관광지")
    a_question = f"{shared.region}에서 {shared.tastes or '여행'} 조건으로 갈 장소를 찾아줘"
    a = run_turn(a_question, [], llm_factory, "장소 검색", prepared_plan=RequestPlan(
        action="place", region=shared.region, place_type=keyword,
        query=f"{shared.region} {shared.tastes} {keyword}".strip()))
    attach_web_research(a, include_web)
    b_question = f"{shared.region} {shared.travel_date} 날씨 알려줘"
    b = run_turn(b_question, [], llm_factory, "장소 검색", prepared_plan=RequestPlan(
        action="weather", region=shared.region, place_type="날씨", query=shared.region))
    places = answer_places(a)
    weather = b.get("weather", [])

    def envelope(role, status, source, data, execution):
        return {"role": role, "input": shared.model_dump(), "status": status,
                "source": source, "data": data, "execution": execution}

    role_a = envelope("A 장소 조사", "error" if a["error"] else "ok" if places else "empty",
                      [{"name": "카카오맵", "url": place["url"]} for place in places],
                      {"places": places}, a)
    role_b = envelope("B 날씨·준비물 조사", b.get("weather_status", "error" if b["error"] else "unavailable"),
                      [{"name": "Open-Meteo", "url": url} for url in sorted({row["source"] for row in weather})],
                      {"weather": weather, "preparations": preparations(weather)}, b)
    result = {"input": shared.model_dump(), "A": role_a, "B": role_b,
              "web_research": a.get('web_research')}
    from plan_summary import build_plan_summary
    result["plan"] = build_plan_summary(result)
    return result
