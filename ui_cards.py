"""외부 입력을 이스케이프하는 여행 정보 HTML 카드."""

from html import escape
from urllib.parse import urlsplit

import streamlit as st


def safe_text(value):
    return escape(str(value), quote=True)


def is_place_url(url):
    try:
        parsed = urlsplit(url)
        return parsed.scheme in ("http", "https") and parsed.netloc == "place.map.kakao.com" and bool(parsed.path.strip("/"))
    except (ValueError, TypeError):
        return False


def summary_html(items):
    cards = "".join(f'<div class="trip-stat"><span>{safe_text(label)}</span><strong>{safe_text(value)}</strong></div>'
                    for label, value in items)
    return f'<section class="trip-summary" aria-label="여행 조건 요약">{cards}</section>'


def place_html(place, number, label=""):
    return f'''<article class="trip-place">
        <div class="trip-place-heading"><span class="trip-number">{safe_text(number)}</span>
        <div><span class="trip-eyebrow">{safe_text(label or '카카오 장소 검색 결과')}</span>
        <h3>{safe_text(place['name'])}</h3></div></div>
        <p>{safe_text(place.get('address') or '주소 미제공')}</p>
        <div class="trip-place-meta"><span>{safe_text(place.get('category') or '업종 미제공')}</span>
        <span>전화 {safe_text(place.get('phone') or '정보 없음')}</span></div>
        </article>'''


def weather_html(records):
    def value(row, key, unit):
        return '미제공' if row.get(key) is None else safe_text(f"{row[key]}{unit}")
    cards = []
    for row in records:
        cards.append(f'''<article class="trip-weather"><span class="trip-eyebrow">일별 예보</span>
            <h3>{safe_text(row['date'])} · {safe_text(row.get('weekday', ''))}</h3>
            <div class="trip-temperature">{value(row, 'high_c', '°C')}<small> / {value(row, 'low_c', '°C')}</small></div>
            <p>최고 / 최저 · 최대 강수확률 {value(row, 'rain_probability_pct', '%')}</p>
            <footer>출처: Open-Meteo<br>조회(KST): {safe_text(row.get('fetched_at', '미제공'))}</footer></article>''')
    return '<section class="trip-weather-grid" aria-label="조회한 날씨">' + ''.join(cards) + '</section>'


def render_place_card(place, number, label=""):
    st.html(place_html(place, number, label))
    if is_place_url(place.get('url', '')):
        st.link_button(f"{number}. 카카오맵에서 위치 보기", place['url'])
    else:
        st.caption("유효한 카카오맵 링크가 없어 지도 버튼을 표시하지 않았습니다.")


def render_weather_cards(records):
    if records:
        st.html(weather_html(records))
