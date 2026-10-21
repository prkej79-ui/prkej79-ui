"""카카오 로컬 장소 검색. 키와 API 원문 오류는 외부에 노출하지 않습니다."""

import os
import re
from html import unescape

import requests


class PlaceSearchError(Exception):
    """사용자에게 표시 가능한 검색 오류."""


def search_travel_info(query: str) -> list[dict[str, str]]:
    """Daum 웹 검색에서 여행코스와 여행 정보의 제목·요약·출처를 조회합니다."""
    if not query.strip():
        return []
    api_key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not api_key:
        raise PlaceSearchError(".env의 KAKAO_REST_API_KEY를 설정해 주세요.")
    try:
        response = requests.get(
            "https://dapi.kakao.com/v2/search/web",
            headers={"Authorization": f"KakaoAK {api_key}"},
            params={"query": query.strip(), "size": 5, "sort": "accuracy"},
            timeout=10,
        )
        if response.status_code in (401, 403):
            raise PlaceSearchError("카카오 인증 또는 Daum 검색 사용 권한을 확인해 주세요.")
        if response.status_code == 429:
            raise PlaceSearchError("카카오 검색 사용량 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.")
        response.raise_for_status()
        return [
            {
                "title": unescape(re.sub(r"<[^>]*>", "", doc.get("title", ""))),
                "summary": unescape(re.sub(r"<[^>]*>", "", doc.get("contents", ""))),
                "url": doc.get("url", ""),
                "date": doc.get("datetime", ""),
            }
            for doc in response.json()["documents"]
        ]
    except PlaceSearchError:
        raise
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        raise PlaceSearchError("여행 정보 검색에 실패했습니다. 네트워크와 카카오 API 설정을 확인해 주세요.") from None


def search_places(query: str) -> list[dict[str, str]]:
    query = query.strip()
    if not query:
        return []
    api_key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not api_key:
        raise PlaceSearchError(".env의 KAKAO_REST_API_KEY를 설정해 주세요.")
    try:
        response = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {api_key}"},
            params={"query": query, "size": 5},
            timeout=10,
        )
        if response.status_code in (401, 403):
            raise PlaceSearchError("카카오 인증 또는 사용 권한을 확인해 주세요. REST API 키와 카카오맵 API 사용 설정을 확인하세요.")
        if response.status_code == 429:
            raise PlaceSearchError("카카오 검색 사용량 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.")
        response.raise_for_status()
        documents = response.json()["documents"]
        return [
            {
                "name": place.get("place_name", ""),
                "address": place.get("road_address_name") or place.get("address_name", ""),
                "category": place.get("category_name", ""),
                "phone": place.get("phone", ""),
                "url": place.get("place_url", ""),
                "longitude": place.get("x", ""),
                "latitude": place.get("y", ""),
            }
            for place in documents
        ]
    except PlaceSearchError:
        raise
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        raise PlaceSearchError("장소 검색에 실패했습니다. 네트워크와 카카오 API 설정을 확인해 주세요.") from None
