"""A·B 원결과를 비교하는 플래너 화면."""

import streamlit as st

from planner import run_planner
from plan_summary import build_plan_summary
from itinerary_table import build_itinerary_rows
from itinerary_ui import render_itinerary_table
from ui_cards import summary_html, render_place_card, render_weather_cards
from place_map import render_places_map
from web_research import render_web_research


def render_planner(llm_factory, render_answer):
    st.subheader("여행 플래너")
    st.caption("지역·날짜·취향을 한 번 입력하면 두 역할이 같은 조건으로 독립 조사합니다. 원결과와 출처를 그대로 보여줍니다.")
    with st.form("planner_input"):
        region = st.text_input("지역", placeholder="예: 경주")
        travel_date = st.text_input("여행 날짜", placeholder="예: 3일 뒤, 이번 주 토요일, YYYY-MM-DD")
        tastes = st.text_input("취향·동행인", placeholder="예: 부모님과 실내 관람, 디저트 카페")
        include_web = st.checkbox('웹 검색 참고 자료 함께 보기', value=False)
        submitted = st.form_submit_button("두 역할로 조사", type="primary")
    if submitted:
        if not region.strip():
            st.info("조사할 지역을 입력해 주세요.")
        else:
            with st.spinner("같은 입력으로 장소와 날씨를 조사하고 있어요..."):
                st.session_state.planner_result = run_planner(region, travel_date, tastes, llm_factory, include_web=include_web)
    result = st.session_state.get("planner_result")
    if not result:
        return
    # 기존 세션 원결과도 현재 검증 규칙으로 대조합니다. API 재호출은 하지 않습니다.
    result["plan"] = build_plan_summary(result)
    st.caption("아래는 마지막으로 실행한 입력과 조사 결과입니다. 조건을 바꿨다면 ‘두 역할로 조사’를 다시 눌러주세요.")
    shared = result["input"]
    st.html(summary_html([("여행 지역", shared['region']), ("여행 날짜", shared['travel_date'] or '미정'),
                          ("취향·동행인", shared['tastes'] or '별도 조건 없음')]))
    if result.get("plan"):
        for warning in result["plan"].get("warnings", []):
            st.warning(f"불일치 경고: {warning} 날씨 확인 필요 — 잘못된 날씨는 최종 계획에 반영하지 않았습니다.")
        rows = build_itinerary_rows(result)
        if rows:
            render_itinerary_table(rows)
        else:
            st.info("장소 조회 실패로 일정표를 만들지 않았습니다." if result['A']['status'] == 'error' else "확인된 장소가 없어 일정표를 만들지 않았습니다.")
            if result["plan"]["facts"].get("weather"):
                st.write("별도로 확인된 날씨")
                st.dataframe([{"날짜": row["date"], "최고 °C": row["high_c"], "최저 °C": row["low_c"],
                               "강수확률 %": row["rain_probability_pct"]} for row in result["plan"]["facts"]["weather"]], hide_index=True)
        render_places_map(result["plan"]["facts"]["places"], key="planner-map",
                          stops=result['plan']['suggestions']['schedule'])
        render_web_research(result.get('web_research'))
        tips = result["plan"]["suggestions"].get("preparations", [])
        if tips:
            st.write("준비물 제안: " + " / ".join(tips))
        if result["plan"]["facts"].get("weather"):
            render_weather_cards(result["plan"]["facts"]["weather"])
            row = result["plan"]["facts"]["weather"][0]
            st.caption(f"날씨 출처: Open-Meteo · 조회 시각(KST): {row['fetched_at']}")
        with st.expander("장소 카드 · 지도와 방문 정보"):
            for number, place in enumerate(result["plan"]["facts"]["places"], 1):
                render_place_card(place, number)
        with st.expander("글로 된 계획과 장소 주소·출처"):
            st.markdown(result["plan"]["text"])
        with st.expander("원결과 → 검사 → 계획"):
            st.caption("각 단계는 같은 공통 입력 식별자로 연결됩니다. 실제 조회 결과와 검사 판정만 표시하며 내부 생각 전문은 기록하지 않습니다.")
            for step in result["plan"].get("evidence_flow", []):
                st.write(f"{step['step']}. {step['stage']}")
                st.json(step, expanded=False)
        with st.expander("계획의 조회 사실과 제안 구분"):
            st.json({key: result["plan"][key] for key in ("status", "facts", "suggestions", "source")}, expanded=False)
            if result["plan"].get("validation"):
                st.json({"종합 전 대조": result["plan"]["validation"]}, expanded=False)
    with st.expander("A·B 조사 원결과 자세히 보기"):
        st.json({"공통 입력": result["input"]}, expanded=False)
        columns = st.columns(2)
        for column, key, heading in zip(columns, ("A", "B"), ("A 장소 조사 원결과", "B 날씨·준비물 원결과")):
            with column:
                role = result[key]
                st.subheader(heading)
                st.caption(f"status: {role['status']}")
                if key == "B" and result.get("plan", {}).get("warnings"):
                    st.caption("아래는 조사 원결과입니다. 불일치한 날씨는 위 최종 계획과 준비물 제안에 사용하지 않았습니다.")
                st.json({field: role[field] for field in ("role", "input", "status", "source")}, expanded=True)
                render_answer(role["execution"], show_map=False)
                for tip in role["data"].get("preparations", []):
                    st.write(f"준비물 제안: {tip}")
                with st.expander("구조화된 원결과"):
                    st.json({field: value for field, value in role.items() if field != "execution"}, expanded=True)
