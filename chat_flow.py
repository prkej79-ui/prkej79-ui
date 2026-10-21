"""대화 문맥, 질문 분류와 장소 도구 실행 기록을 관리합니다."""

import json
import re
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import Literal

from config import SYSTEM_PROMPT
from kakao_search import PlaceSearchError, search_places, search_travel_info
from verified_trip import build_verified_trip, find_verified_places
from weather_flow import run_weather
from weather_tools import KST, WeatherError, today_kst
from regions import region_matches


class RequestPlan(BaseModel):
    action: Literal["place", "itinerary", "weather", "clarify", "other"]
    region: str = Field(description="현재 질문 또는 이전 대화에서 확인한 목적지 지역. 없으면 빈 문자열")
    place_type: str = Field(description="식당, 카페, 관광지, 숙소 등 찾는 장소 종류")
    query: str = Field(description="대명사를 이전 문맥으로 풀어 쓴 짧은 검색어. 목적지 지역과 종류·방문 조건 포함")


def small_talk(question: str) -> str | None:
    text = re.sub(r"[\s.!?~ㅋㅎㅠㅜ♥😊👋]", "", question).lower()
    if text in {"안녕", "안녕하세요", "안녕하세용", "안뇽", "반가워", "반갑습니다", "하이", "hello", "hi", "좋은아침", "굿모닝"}:
        return "안녕하세요! 어느 지역의 여행지나 식당을 찾으시나요? 날짜 없이 지역과 원하는 장소만 알려주셔도 됩니다."
    if text in {"고마워", "감사", "감사합니다", "고맙습니다", "고마워요", "잘가", "수고했어"}:
        return "도움이 되었다니 기뻐요. 다른 여행지나 장소가 궁금하면 말씀해 주세요."
    return None


def context_question(question: str, history: list[dict]) -> str:
    # 최근 10회만 모델에 전달합니다. 지도 결과와 도구 인자는 이력에 키를 포함하지 않습니다.
    return json.dumps({"이전대화_참고자료": [
        {"질문": turn["question"], "답변": turn.get("message", ""),
         "지역": turn.get("region", ""), "날씨날짜": turn.get("weather_dates", []),
         "날씨날짜확인중": turn.get("awaiting_weather_date", False), "장소": (
             [turn["places"][stop["place_index"] - 1] for stop in turn["stops"]]
             if turn.get("stops") else turn.get("places", []))}
        for turn in history[-10:]
    ], "현재질문": question}, ensure_ascii=False)


def answer_places(turn: dict) -> list[dict]:
    """실행 기록이 있으면 마지막 도구 반환을 답변 장소의 유일한 근거로 사용합니다."""
    traces = turn.get("traces", [])
    if traces and traces[-1].get("결과 종류") == "weather":
        return []
    if traces and "결과" in traces[-1]:
        return traces[-1]["결과"]
    return turn.get("places", [])  # 업데이트 전 세션 기록 호환


@traceable(name="국내여행 챗봇 요청", run_type="chain")
def run_turn(question: str, history: list[dict], llm_factory, search_mode: str, query_override: str = "",
             *, tool_limit: int = 3, retry: bool = True, prepared_plan: RequestPlan | None = None) -> dict:
    tool_limit = max(1, min(tool_limit, 3))
    result = {"question": question, "message": "", "region": "", "places": [], "stops": [],
              "is_itinerary": False, "traces": [], "rejected_count": 0, "error": False,
              "tool_limit": tool_limit, "end_reason": "", "request_plan": None,
              "itinerary_reference_date": today_kst().isoformat()}
    if not question.strip():
        result["message"] = "국내여행 관련 질문을 입력해 주세요."
        result["end_reason"] = "빈 입력: 호출 없이 종료"
        return result
    greeting = small_talk(question)
    if greeting:
        result["message"] = greeting
        result["end_reason"] = "단순 인사·감사: 호출 없이 응답"
        return result

    def tool_call(name, query, function, region, place_type, reason):
        entry = {"순서": len(result["traces"]) + 1,
                 "도구": name, "인자": {"지역": region, "장소 종류": place_type, "검색어": query},
                 "status": "running", "결과 수": 0, "결과": [], "호출 사유": reason,
                 "다음 동작": "", "판정 근거": "", "하위 API 호출": [],
                 "조회 시각(KST)": datetime.now(KST).isoformat(timespec="seconds")}
        result["traces"].append(entry)
        try:
            records = function(query, entry)
            # 도구 반환 스냅샷: 이후 답변을 만들기 위해 이 기록을 고치지 않습니다.
            entry["결과"] = [dict(place) for place in records]
            entry["status"] = ("ok" if entry.get("결과 종류") == "weather" else "success") if records else "empty"
            entry["결과 수"] = len(records)
            return records
        except Exception as error:
            entry["status"] = error.status if isinstance(error, WeatherError) else "error"
            if isinstance(error, WeatherError) and error.details:
                entry["날짜 검증"] = error.details
            entry["다음 동작"] = "종료"
            entry["판정 근거"] = "도구 오류: 확인되지 않은 정보로 대체하지 않음"
            raise

    try:
        llm = llm_factory()
        context = context_question(question, history)
        plan = prepared_plan.model_copy() if prepared_plan else llm.with_structured_output(RequestPlan).invoke([
            SystemMessage(content=SYSTEM_PROMPT + f"\n한국 기준 오늘 날짜: {today_kst().isoformat()}\n[현재 단계: 검색 계획]\n" + (
                "국내여행 질문의 검색 계획을 작성하세요. 이전 대화는 대명사·생략된 지역과 방문 조건을 "
                "이해하는 참고 자료입니다. 현재 질문의 변경 사항을 우선하세요. "
                "장소를 찾거나 추천해달라는 요청은 place, 일정·코스 요청은 itinerary입니다. "
                "지역과 종류가 있으면 즉시 검색하며, 날짜는 장소 검색의 필수 조건이 아닙니다. "
                "날짜만 부족하다는 이유로 clarify를 선택하지 마세요. "
                "이전 문맥에도 지역이 없어서 검색이 불가능할 때만 clarify를 선택하세요. "
                "인사나 감사가 포함돼도 여행 질문이 함께 있으면 해당 질문을 처리하세요. "
                "여행과 무관하거나 해외여행이면 other입니다. 메뉴명은 상호로 만들지 마세요."
                "날씨·기온·강수확률 질문은 날짜가 없어도 weather입니다. 직전 날씨 질문의 날짜·지역을 "
                "되묻는 상황이면 '이번 주 토요일', '경주' 같은 후속 답변도 weather로 분류하세요. "
                "날씨일 때 query에는 지역 또는 정확한 장소명만 쓰고 날짜·날씨 표현을 넣지 마세요. "
                "좌표와 구체 날짜·예보 수치는 생성하지 마세요."
            )), HumanMessage(content=context),
        ])
        result["request_plan"] = plan.model_dump()
        result["region"] = plan.region
        if plan.action == "weather":
            return run_weather(result, question, plan, history, tool_call)
        if plan.action == "other":
            result["message"] = "국내여행 관련 장소나 여행코스를 질문해 주세요."
            result["end_reason"] = "국내여행 요청 아님"
            return result
        if not plan.region.strip():
            result["message"] = "어느 지역에서 찾으시나요? 지역명과 원하는 장소 종류를 알려주세요. 날짜는 없어도 됩니다."
            result["end_reason"] = "지역 확인 필요"
            return result
        if plan.action == "clarify":
            # 지역이 확인되면 날짜 등 부가 조건을 되묻지 않고 장소를 검색합니다.
            plan.action = "place"
        query = query_override.strip() or plan.query.strip() or f"{plan.region} {plan.place_type}"
        if plan.region not in query:
            query = f"{plan.region} {query}"

        def api_call(entry, name, keyword, function):
            call = {"도구": name, "검색어": keyword, "status": "running", "결과 수": 0}
            entry["하위 API 호출"].append(call)
            try:
                records = function(keyword)
                call.update({"status": "success" if records else "empty", "결과 수": len(records)})
                return records
            except Exception:
                call["status"] = "error"
                raise

        def place_tool(keyword, entry):
            records = api_call(entry, "카카오 장소 API", keyword, search_places)
            return [p for p in records if p["name"] and p["address"]
                    and region_matches(plan.region, p["address"])
                    and p["url"].startswith(("https://place.map.kakao.com/", "http://place.map.kakao.com/"))]

        def itinerary_tool(keyword, entry):
            records = api_call(entry, "Daum 웹 검색 API", keyword, search_travel_info)
            result['web_research'] = {'query': keyword, 'source': 'Daum 웹 검색 API',
                                      'status': 'success' if records else 'empty', 'results': [dict(row) for row in records],
                                      'fetched_at': entry['조회 시각(KST)']}
            entry['웹 검색 참고 자료'] = [dict(row) for row in records]
            if not records:
                return []
            places, rejected = find_verified_places(
                llm, context, records,
                place_search=lambda text: api_call(entry, "카카오 장소 API", text, search_places))
            result["rejected_count"] += len(rejected)
            return places

        direct = plan.action == "place" or search_mode == "장소 검색"
        tool = place_tool if direct else itinerary_tool
        tool_name = "카카오 장소 검색" if direct else "여행코스 검색·지도 검증"
        # 취향·동행인 문장은 유지해 추천 문맥으로 쓰되, 검색 실패 시 지역·업종으로 단순화합니다.
        kind = next((word for word in ("카페", "식당", "맛집", "숙소", "박물관", "미술관", "관광지")
                     if word in plan.place_type), plan.place_type.strip() or "관광지")
        simple = f"{plan.region} {kind}" if direct else f"{plan.region} 여행코스"
        alias = {"카페": "커피전문점", "식당": "음식점", "맛집": "음식점", "숙소": "호텔", "관광지": "관광명소"}.get(kind, kind)
        alternative = f"{plan.region.split()[-1]} {alias}" if direct else f"{plan.region} 가볼만한곳"
        queries = list(dict.fromkeys([query, simple, alternative])) if retry else [query]
        places = []
        for attempt, keyword in enumerate(queries[:tool_limit]):
            reason = "현재 질문의 검색 계획" if attempt == 0 else "직전 도구의 검증 결과 0개: 취향 표현을 빼고 지역·종류 중심으로 재검색"
            places = tool_call(tool_name, keyword, tool, plan.region, plan.place_type, reason)
            last = result["traces"][-1]
            if places:
                result["end_reason"] = "검증된 장소 확보: 마지막 도구 결과로 답변"
                last.update({"다음 동작": "답변", "판정 근거": "검증 결과 1개 이상"})
                break
            more = attempt + 1 < min(len(queries), tool_limit)
            last.update({"다음 동작": "재검색" if more else "종료",
                         "판정 근거": "검증 결과 0개, 남은 호출 가능" if more else "검증 결과 0개, 호출 한도 또는 검색어 소진"})
        if not places:
            result["end_reason"] = "호출 한도 도달" if len(result["traces"]) >= tool_limit else "재검색어 소진" if retry else "1회 실행 종료"
        places = answer_places(result)
        if not places:
            result["message"] = "요청에 맞는 장소를 카카오맵에서 확인하지 못했습니다. 존재하지 않는다는 뜻은 아닙니다. 지역명과 정확한 상호로 다시 검색해 주세요."
            return result
        if plan.action == "place":
            # 날짜와 무관한 장소 질문은 추가 일정 생성 없이 조회 결과를 그대로 안내합니다.
            result["places"] = places
            result["message"] = "카카오맵에서 조회한 장소입니다. 메뉴 판매 여부와 방문 조건 충족 여부는 매장에 확인해 주세요."
            if len(result["traces"]) > 1:
                result["message"] = "검색어를 간결하게 바꿔 찾은 장소입니다. 마지막 검색 결과만 안내합니다. 동행인의 취향이나 방문 조건에 맞는지는 별도 확인이 필요합니다."
        else:
            result["places"] = places
            trip = build_verified_trip(llm, SYSTEM_PROMPT, context, places)
            if not trip.stops:
                result["message"] = "세부 코스 대신 마지막 도구에서 확인한 장소를 안내합니다."
                return result
            # 사용된 장소와 번호만 저장해 이후 화면 갱신에도 같은 지도 링크를 유지합니다.
            result["places"] = places
            result["stops"] = [stop.model_dump() for stop in trip.stops]
            result["is_itinerary"] = trip.is_itinerary
            result["message"] = "카카오맵에서 확인한 장소로 구성한 여행코스입니다."
    except (PlaceSearchError, WeatherError) as error:
        result["message"] = str(error)
        result["error"] = not isinstance(error, WeatherError) or error.status != "out_of_range"
        result["end_reason"] = "검색 도구 오류로 종료"
        if isinstance(error, WeatherError):
            result["weather_status"] = result["status"] = error.status
            result["weather"] = []
            result["end_reason"] = {"out_of_range": "예보 범위 밖: API 호출 없이 종료",
                                    "date_mismatch": "반환 날짜 불일치: 날씨 값 폐기"}.get(error.status, "날씨 조회 오류로 종료")
    except Exception:
        result["message"] = "답변 생성 중 오류가 발생했습니다. API 설정과 네트워크를 확인해 주세요."
        result["error"] = True
        result["end_reason"] = "처리 오류로 종료"
    return result


def run_comparison(question, history, llm_factory, search_mode, query_override=""):
    """같은 질문·이력·검색 계획을 사용해 한도만 바꿉니다."""
    baseline = run_turn(question, history, llm_factory, search_mode, query_override,
                        tool_limit=1, retry=False)
    plan = RequestPlan(**baseline["request_plan"]) if baseline.get("request_plan") else None
    repeated = run_turn(question, history, llm_factory, search_mode, query_override,
                        tool_limit=3, retry=True, prepared_plan=plan)
    repeated["comparison"] = baseline
    return repeated
