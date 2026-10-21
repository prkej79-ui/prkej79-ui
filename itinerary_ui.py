"""기존 채팅과 플래너가 함께 사용하는 일정표 화면."""

import streamlit as st


def render_itinerary_table(rows):
    st.subheader("일자별 여행 계획")
    st.dataframe(rows, hide_index=True, width="stretch", column_config={
        "장소": st.column_config.TextColumn("장소", width="medium"),
        "날씨": st.column_config.TextColumn("날씨", width="large"),
        "지도": st.column_config.LinkColumn("지도", display_text="지도 보기"),
    })
    st.caption("이동 시간은 경로를 조회하지 않아 ‘미조회’로 표시합니다. 예상 방문 시간과 체류 소요시간은 계획용 제안이며 영업시간·실측 시간이 아닙니다.")
