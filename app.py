"""대화 문맥과 지도 검증을 지원하는 국내여행 챗봇."""

import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from chat_flow import answer_places, run_comparison, run_turn
from config import OPENAI_MODEL
from planner_ui import render_planner
from itinerary_table import build_chat_itinerary_rows
from itinerary_ui import render_itinerary_table
from ui_cards import summary_html, render_place_card, render_weather_cards
from autumn_theme import render_autumn_theme
from place_map import render_places_map
from web_research import attach_web_research, render_web_research


load_dotenv(Path(__file__).with_name(".env"), override=True)
st.set_page_config(page_title="국내여행 챗봇", page_icon="✈️", layout="wide")
st.html("<style>" + Path(__file__).with_name("chat_theme.css").read_text(encoding="utf-8") + "</style>")
render_autumn_theme()
st.html('<div class="trip-brand">TRAVEL COMPANION · 국내여행 플래닝</div>')
st.title("✈️ 국내여행 챗봇")
st.html('<p class="trip-intro">가고 싶은 곳부터 하루의 일정까지, 지도에서 확인한 장소로 계획하세요.</p>')
view = st.radio("화면", ["여행 챗봇", "여행 플래너"], horizontal=True)
st.caption("장소 검색은 날짜 없이 · 코스는 일정표로 · 장소와 날씨를 함께 조사하려면 ‘여행 플래너’")
st.session_state.setdefault("travel_history", [])
st.caption("같은 세션의 최근 10회 대화를 참고합니다. 대화와 검색 자료는 OpenAI에 전달됩니다.")
if st.button("대화 초기화"):
    st.session_state.travel_history = []


def create_llm():
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise ValueError("API configuration missing")
    return ChatOpenAI(model=OPENAI_MODEL, temperature=0, timeout=30, max_retries=1)


def render_answer(turn, *, map_key="answer", show_map=True):
    places = answer_places(turn)
    table_rows = build_chat_itinerary_rows(turn)
    if table_rows:
        render_itinerary_table(table_rows)
        st.caption("이 채팅 코스에서는 날씨를 함께 조회하지 않았습니다. 날씨 포함 일정표는 ‘여행 플래너’에서 지역·날짜를 입력해 확인하세요.")
    if turn.get("error"):
        st.error(turn["message"])
    else:
        st.write(turn["message"])
    if turn.get("weather_status"):
        st.caption(f"날씨 상태: {turn['weather_status']}")
    traces = turn.get("traces", [])
    if traces and traces[-1].get("결과 종류") == "weather" and traces[-1].get("결과"):
        weather = traces[-1]["결과"]
        render_weather_cards(weather)
        def shown(value):
            return "미제공" if value is None else value
        st.dataframe([{"날짜": row["date"], "요일": row["weekday"],
                       "최고 °C": shown(row["high_c"]), "최저 °C": shown(row["low_c"]),
                       "최대 강수확률 %": shown(row["rain_probability_pct"])} for row in weather], hide_index=True)
        location = turn.get("weather_location", {})
        st.text(f"조회 기준: {location.get('name', '')} · {location.get('address', '')}")
        if location.get("url", "").startswith(("https://place.map.kakao.com/", "http://place.map.kakao.com/")):
            st.link_button("날씨 조회 기준 장소 지도", location["url"])
        st.caption(f"좌표: 위도 {weather[0]['latitude']}, 경도 {weather[0]['longitude']} · 조회 시각(KST): {weather[0]['fetched_at']}")
        st.markdown("출처: [Open-Meteo](https://open-meteo.com/). 일별 예보이며 실제 날씨와 달라질 수 있습니다.")
    if turn.get("rejected_count"):
        st.warning(f"이름과 지역이 일치하지 않은 후보 {turn['rejected_count']}개를 제외했습니다.")
    if show_map:
        render_places_map(places, key=map_key, stops=turn.get('stops', []))
    render_web_research(turn.get('web_research'))
    stops = [stop for stop in turn.get("stops", []) if 1 <= stop["place_index"] <= len(places)]
    selected = {stop["place_index"] for stop in stops}
    # 마지막 도구 결과 전체를 표시합니다. 코스에 배정되지 않은 장소도 누락하지 않습니다.
    stops += [{"place_index": i} for i in range(1, len(places) + 1) if i not in selected]
    def render_place_details():
        for index, stop in enumerate(stops, 1):
            place = places[stop["place_index"] - 1]
            label = f"{stop['day']}일차 · {stop['time']} · {stop.get('purpose', '')} | " if turn.get("is_itinerary") and "day" in stop else ""
            render_place_card(place, index, label.rstrip(" |"))
    if table_rows:
        with st.expander("장소별 주소·연락처와 대체 후보"):
            render_place_details()
    else:
        render_place_details()
    if places:
        st.caption("상호·주소는 카카오 장소 API 조회 결과입니다. 현재 영업 여부와 메뉴·가격·주차 등 방문 조건은 매장에 확인하세요. 코스 시간대는 제안입니다.")
    with st.expander(f"실행 기록 · 도구 호출 {len(turn['traces'])}회 / 한도 {turn.get('tool_limit', 3)}회"):
        st.caption(f"종료 사유: {turn.get('end_reason', '이전 버전의 실행')}")
        if not turn["traces"]:
            st.caption("외부 검색 도구 호출 없음 (0회)")
        else:
            st.dataframe([
                {key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                 for key, value in trace.items() if key not in ("결과", "하위 API 호출")}
                for trace in turn["traces"]
            ], hide_index=True)
            for trace in turn["traces"]:
                st.caption(f"{trace.get('순서', '')}. {trace['도구']} 호출 → 반환 {trace['결과 수']}개 → {trace.get('다음 동작', '')}")
                st.json({"반환 결과": trace.get("결과", []), "하위 API 호출": trace.get("하위 API 호출", [])}, expanded=False)
            st.caption("호출 한도는 에이전트 도구 단위입니다. 여행코스 검색·지도 검증은 웹 검색과 지도 조회를 묶은 도구이며, 실제 API 호출은 하위 기록에서 확인합니다. 내부 생각 전문은 저장하지 않습니다.")


def render_turn(turn, index, *, show_map=True):
    with st.chat_message("user"):
        st.caption("나")
        st.write(turn["question"])
    with st.chat_message("assistant"):
        st.caption("여행 도우미")
        if turn.get("comparison"):
            left, right = st.columns(2)
            with left:
                st.subheader("1회 종료 실행")
                render_answer(turn["comparison"], map_key=f"chat-{index}-once", show_map=show_map)
            with right:
                st.subheader("재검색 허용 실행")
                render_answer(turn, map_key=f"chat-{index}-retry", show_map=show_map)
            st.caption("같은 질문·이전 대화·검색 계획으로 한도만 바꿔 실행했습니다. 검색 시점에 따라 반환 결과가 달라질 수 있습니다.")
        else:
            render_answer(turn, map_key=f"chat-{index}", show_map=show_map)


if view == "여행 플래너":
    render_planner(create_llm, render_answer)
    st.stop()

if st.session_state.travel_history:
    latest = st.session_state.travel_history[-1]
    st.html(summary_html([("최근 요청 지역", latest.get("region") or "미지정"),
                          ("마지막 답변 장소", f"{len(answer_places(latest))}곳"),
                          ("대화", f"{len(st.session_state.travel_history)}회")]))
st.caption("💬 내 메시지는 오른쪽 노란 말풍선, 여행 도우미의 답변은 왼쪽 흰 말풍선에 표시됩니다.")
with st.container(key="chat_thread"):
    if not st.session_state.travel_history:
        st.info("어디로 떠나고 싶으세요? 아래에 여행지나 궁금한 내용을 입력해 주세요.")
    latest_map_index = max((i for i, turn in enumerate(st.session_state.travel_history)
                            if answer_places(turn) or answer_places(turn.get("comparison", {}))), default=-1)
    for index, previous_turn in enumerate(st.session_state.travel_history):
        # WebGL 지도 수를 제한해 긴 대화에서도 브라우저 안정성을 유지합니다.
        render_turn(previous_turn, index, show_map=index == latest_map_index)

with st.form("travel_question", clear_on_submit=True):
    question = st.text_area("질문", placeholder="예: 담양 카페 찾아줘. / 경주 이번 주 토요일 날씨 알려줘.", height=110)
    with st.expander("검색 설정"):
        search_mode = st.selectbox("검색 유형", ["여행코스·정보 검색", "장소 검색"])
        search_query = st.text_input("검색어 (선택)", placeholder="비워두면 대화 문맥과 질문에서 검색어를 만듭니다.")
        compare_runs = st.checkbox("1회 종료·재검색 실행 비교", value=False)
        include_web = st.checkbox("웹 검색 참고 자료 함께 보기", value=False)
        st.caption("웹 검색을 켜면 여행 장소 질문의 참고 자료를 Daum에서 추가 조회합니다. 지도에 두 장소 이상 있으면 직선거리를 계산할 수 있습니다.")
        st.caption("기본 실행은 최대 3회입니다. 결과가 없을 때 검색어를 간결하게 바꿉니다. 비교를 켜면 같은 요청을 1회 한도와 3회 한도로 각각 실행합니다.")
        st.caption("장소 질문은 지역·장소 종류·방문 조건으로 카카오맵을 바로 검색합니다. 여행코스는 웹 검색 후보를 지도에서 확인합니다.")
    submitted = st.form_submit_button("답변 받기", type="primary")

if submitted:
    if not question.strip():
        st.info("국내여행 관련 질문을 입력해 주세요.")
    else:
        with st.spinner("질문을 확인하고 필요한 장소를 검색하고 있어요..."):
            runner = run_comparison if compare_runs else run_turn
            turn = runner(question.strip(), st.session_state.travel_history, create_llm, search_mode, search_query)
            attach_web_research(turn, include_web)
        st.session_state.travel_history.append(turn)
        # 세션 화면과 메모리가 무한히 증가하지 않도록 최근 20회를 보관합니다.
        st.session_state.travel_history = st.session_state.travel_history[-20:]
        st.rerun()
