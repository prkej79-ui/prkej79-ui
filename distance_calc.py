"""검색 좌표로 계산하는 구면 직선거리. 도로·교통 시간은 추정하지 않습니다."""

import math


def valid_coordinates(place):
    try:
        if isinstance(place.get('latitude'), bool) or isinstance(place.get('longitude'), bool):
            return None
        lat, lon = float(place['latitude']), float(place['longitude'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -85.0511 <= lat <= 85.0511 and -180 <= lon <= 180):
            return None
        return (lat, lon) if (lat, lon) != (0, 0) else None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def straight_distance_km(start, end):
    a, b = valid_coordinates(start), valid_coordinates(end)
    if a is None or b is None:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def distance_label(km):
    if km is None:
        return '계산 불가 (좌표 없음)'
    return f'약 {km * 1000:.0f}m' if km < 1 else f'약 {km:.2f}km'


def itinerary_distances(places, stops):
    rows = []
    # 누락된 중간 장소를 건너뛰어 다른 구간의 거리로 대체하지 않습니다.
    for start, end in zip(stops, stops[1:]):
        if start['day'] != end['day']:
            continue
        i, j = start['place_index']-1, end['place_index']-1
        if not (0 <= i < len(places) and 0 <= j < len(places)):
            continue
        rows.append({'일자': f"{start['day']}일차", '출발 장소': places[i]['name'],
                     '도착 장소': places[j]['name'],
                     '직선거리': distance_label(straight_distance_km(places[i], places[j])),
                     '실제 이동 시간': '미조회'})
    return rows
