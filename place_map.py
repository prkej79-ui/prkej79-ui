"""조회 결과의 실제 좌표만 사용하는 Streamlit 지도."""

import math
from hashlib import sha256
import json

import pydeck as pdk
import streamlit as st

from ui_cards import is_place_url
from distance_calc import valid_coordinates, straight_distance_km, distance_label, itinerary_distances
from navigation import render_navigation


def map_points(places):
    points, seen = [], set()
    for number, place in enumerate(places, 1):
        url = place.get('url', '')
        if not is_place_url(url) or url in seen or not place.get('name') or not place.get('address'):
            continue
        coords = valid_coordinates(place)
        if coords is None:
            continue
        latitude, longitude = coords
        seen.add(url)
        points.append({'number': number, 'label': str(number), 'name': place['name'],
                       'address': place['address'], 'url': url,
                       'latitude': latitude, 'longitude': longitude})
    return points


def map_view(points):
    latitudes = [p['latitude'] for p in points]
    longitudes = [p['longitude'] for p in points]
    # 배치만 계산합니다. 도로 경로·소요시간을 추정하거나 좌표를 생성하지 않습니다.
    span = max(max(longitudes) - min(longitudes), (max(latitudes) - min(latitudes)) * 1.5, .005)
    zoom = max(2, min(14, math.log2(240 / span)))
    return pdk.ViewState(latitude=(min(latitudes) + max(latitudes)) / 2,
                         longitude=(min(longitudes) + max(longitudes)) / 2,
                         zoom=zoom, pitch=0)


def render_places_map(places, *, key, stops=None):
    if not places:
        return
    st.subheader('여행 장소 지도')
    points = map_points(places)
    if not points:
        st.info('유효한 장소 좌표가 없어 지도에 표시하지 않았습니다. 장소를 다시 검색하면 좌표를 확인할 수 있습니다.')
        return
    fingerprint = sha256(json.dumps(points, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    deck = pdk.Deck(
        map_style=None, map_provider='carto', initial_view_state=map_view(points),
        layers=[pdk.Layer('ScatterplotLayer', id='places', data=points,
                          get_position='[longitude, latitude]', get_fill_color=[185, 71, 34, 220],
                          get_line_color=[255, 255, 255], stroked=True, line_width_min_pixels=2,
                          get_radius=100, radius_min_pixels=13, radius_max_pixels=13, pickable=True),
                pdk.Layer('TextLayer', id='labels', data=points,
                          get_position='[longitude, latitude]', get_text='label',
                          get_size=13, get_color=[255, 255, 255], pickable=False)],
        tooltip={'text': '{number}. {name}\n{address}'},
    )
    st.pydeck_chart(deck, height=370, width='stretch', key=f'{key}-{fingerprint}',
                    alt='카카오 장소 검색에서 확인한 여행 장소의 위치 지도')
    choice = st.selectbox('지도 장소 상세', options=range(len(points)),
                          format_func=lambda i: f"{points[i]['number']}. {points[i]['name']}",
                          key=f'{key}-detail-{fingerprint}')
    place = points[choice]
    st.text(f"{place['number']}. {place['name']}\n주소: {place['address']}")
    st.link_button('선택한 장소를 카카오맵에서 보기', place['url'])
    render_navigation(place, key=f'{key}-{fingerprint}')
    if len(points) >= 2:
        with st.expander('장소 간 직선거리 계산'):
            left, right = st.columns(2)
            labels = lambda i: f"{points[i]['number']}. {points[i]['name']}"
            with left:
                start = st.selectbox('거리 출발 장소', range(len(points)), format_func=labels,
                                     key=f'{key}-from-{fingerprint}')
            with right:
                end = st.selectbox('거리 도착 장소', range(len(points)), index=1, format_func=labels,
                                   key=f'{key}-to-{fingerprint}')
            st.metric('선택한 두 장소의 직선거리', distance_label(straight_distance_km(points[start], points[end])))
    segments = itinerary_distances(places, stops or [])
    if segments:
        st.write('일정 순서별 구간 직선거리')
        st.dataframe(segments, hide_index=True, width='stretch')
    st.caption('거리는 조회된 위도·경도로 계산한 구면 직선거리이며 도로·도보 경로 거리가 아닙니다. 거리에서 이동 시간을 추정하지 않습니다.')
    st.caption(f'좌표 확인 {len(points)}곳 · 마커에 마우스를 올리면 장소명·주소를 볼 수 있습니다. 아래 목록에서 장소를 선택하면 상세 링크가 표시됩니다. 확대·축소와 드래그가 가능합니다.')
    if len(points) < len(places):
        st.caption('좌표 누락·유효하지 않은 값·중복 장소는 지도에서 제외했습니다. 기존 장소 안내는 유지합니다.')
    st.caption('위치 출처: 카카오 장소 API · 배경지도: CARTO / OpenStreetMap. 카카오맵 자체를 내장한 지도는 아니며, 경로·이동 시간은 조회하지 않습니다.')
