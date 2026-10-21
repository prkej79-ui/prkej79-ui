"""기존 장소 결과와 분리한 선택형 웹검색 참고 자료."""

from datetime import datetime
from urllib.parse import urlsplit

import streamlit as st

from kakao_search import search_travel_info
from weather_tools import KST


def safe_web_url(url):
    try:
        parsed = urlsplit(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (ValueError, TypeError):
        return False


def attach_web_research(turn, enabled=False):
    if not enabled or not turn.get('region') or turn.get('error'):
        return turn
    # 인사·날씨·지역 확인 질문에는 불필요한 추가 검색을 하지 않습니다.
    if turn.get('request_plan', {}).get('action') not in ('place', 'itinerary'):
        return turn
    if turn.get('web_research'):
        return turn
    keyword = f"{turn['region']} {turn.get('request_plan', {}).get('place_type', '')} 여행 방문 정보"
    research = {'query': keyword, 'source': 'Daum 웹 검색 API', 'status': 'running', 'results': [],
                'fetched_at': datetime.now(KST).isoformat(timespec='seconds')}
    try:
        research['results'] = [dict(row) for row in search_travel_info(keyword) if safe_web_url(row.get('url', ''))]
        research['status'] = 'success' if research['results'] else 'empty'
    except Exception:
        # 예외 원문·키·인증 헤더는 실행 기록 및 화면에 저장하지 않습니다.
        research['status'] = 'error'
    turn['web_research'] = research
    return turn


def render_web_research(research):
    if not research:
        return
    records = research.get('results', [])
    with st.expander(f"웹 검색 참고 자료 · {len(records)}건"):
        st.caption(f"출처: {research['source']} · 상태: {research['status']} · 조회(KST): {research['fetched_at']}")
        st.text(f"검색어: {research['query']}")
        if research['status'] == 'error':
            st.info('웹 검색에 실패했습니다. 기존 장소·날씨 결과는 유지하며 다른 정보로 채우지 않았습니다.')
        elif not records:
            st.info('웹 검색 참고 자료를 찾지 못했습니다.')
        for i, row in enumerate(records, 1):
            st.text(f"{i}. {row.get('title', '제목 없음')}\n{row.get('summary', '')}")
            if row.get('date'):
                st.caption(f"검색 결과 문서 시각: {row['date']}")
            if safe_web_url(row.get('url', '')):
                st.link_button(f'{i}. 웹 검색 원문 보기', row['url'])
        st.caption('검색 결과 요약은 참고 자료이며 실제 영업·가격·메뉴를 보장하지 않습니다. 장소 존재 여부는 카카오 검색, 날씨는 날짜 검증된 예보만 근거로 사용합니다. 추가 웹 검색은 별도 기록이며 기존 장소 도구 호출 한도에 포함되지 않습니다.')
