"""한국 날짜 해석과 Open-Meteo 일별 예보. 날짜·좌표·기온을 모델이 생성하지 않습니다."""

from datetime import date, datetime, timedelta
from calendar import monthrange
import math
import re
from zoneinfo import ZoneInfo

import requests


KST = ZoneInfo("Asia/Seoul")


class WeatherError(Exception):
    """사용자에게 표시 가능한 날씨 조회 오류."""

    def __init__(self, message, status="error", details=None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


def today_kst() -> date:
    return datetime.now(KST).date()


def resolve_dates(text: str, today: date | None = None) -> list[date]:
    today = today or today_kst()
    text = re.sub(r"\s+", "", text)
    values = []
    try:
        explicit = re.findall(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text)
        if explicit:
            values = [date(int(y), int(m), int(d)) for y, m, d in explicit]
        else:
            korean = re.findall(r"(?:(\d{4})년)?(\d{1,2})월(\d{1,2})일?", text)
            if korean:
                values = [date(int(y) if y else today.year, int(m), int(d)) for y, m, d in korean]
            else:
                short = re.findall(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text)
                if short:
                    values = [date(today.year, int(m), int(d)) for m, d in short]
        if not values:
            month = re.search(r"(한|두|세|\d+)(?:달|개월)(뒤|후|전)", text)
            relative_days = re.findall(r"(\d+)일(뒤|후|전)", text)
            if month:
                count = {"한": 1, "두": 2, "세": 3}.get(month[1])
                count = count if count is not None else int(month[1])
                offset = count * (-1 if month[2] == "전" else 1)
                total = today.year * 12 + today.month - 1 + offset
                year, m = divmod(total, 12)
                values.append(date(year, m + 1, min(today.day, monthrange(year, m + 1)[1])))
            for number, direction in relative_days:
                values.append(today + timedelta(days=int(number) * (-1 if direction == "전" else 1)))
            for expression, offset in (("오늘", 0), ("내일", 1), ("모레", 2), ("글피", 3), ("어제", -1), ("그제", -2)):
                if expression in text:
                    values.append(today + timedelta(days=offset))
            weekday = re.search(r"(이번주|다음주|다다음주)?([월화수목금토일])요일", text)
            if weekday:
                day = "월화수목금토일".index(weekday[2])
                if weekday[1]:
                    week = {"이번주": 0, "다음주": 1, "다다음주": 2}[weekday[1]]
                    values.append(today - timedelta(days=today.weekday()) + timedelta(days=7 * week + day))
                else:
                    values.append(today + timedelta(days=(day - today.weekday()) % 7))
            elif "주말" in text:
                week = 1 if "다음주말" in text or "다음주주말" in text else 0
                saturday = today - timedelta(days=today.weekday()) + timedelta(days=5 + 7 * week)
                values.extend([saturday, saturday + timedelta(days=1)])
    except ValueError:
        raise WeatherError("존재하지 않는 날짜입니다. YYYY-MM-DD 형식으로 날짜를 확인해 주세요.") from None
    values = sorted(set(values))
    if len(values) == 2 and any(word in text for word in ("~", "부터", "까지")):
        if (values[-1] - values[0]).days > 15:
            raise WeatherError("예보 없음: 날씨 조회 기간은 최대 16일입니다. 현재 날씨로 대신 안내하지 않습니다.", "out_of_range")
        values = [values[0] + timedelta(days=i) for i in range((values[-1] - values[0]).days + 1)]
    return values


def validate_forecast_dates(dates: list[date], today: date | None = None):
    today = today or today_kst()
    if any(day < today or day > today + timedelta(days=15) for day in dates):
        raise WeatherError("예보 없음: 요청 날짜가 조회 범위 밖입니다. 오늘부터 16일 이내 날짜를 알려주세요. 현재 날씨로 대신 안내하지 않습니다.", "out_of_range")


def coordinates(place: dict) -> tuple[float, float]:
    try:
        latitude, longitude = float(place["latitude"]), float(place["longitude"])
        if not math.isfinite(latitude) or not math.isfinite(longitude) or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
        return latitude, longitude
    except (KeyError, ValueError, TypeError):
        raise WeatherError("카카오 검색 결과에 유효한 좌표가 없습니다. 좌표를 추측하지 않고 조회를 중단했습니다.") from None


def fetch_weather(latitude: float, longitude: float, dates: list[date]) -> list[dict]:
    validate_forecast_dates(dates)
    if not dates:
        return []
    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": latitude, "longitude": longitude,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "temperature_unit": "celsius", "timezone": "Asia/Seoul",
            "start_date": min(dates).isoformat(), "end_date": max(dates).isoformat(),
        }, timeout=15)
        response.raise_for_status()
        payload = response.json()
        daily = payload["daily"]
        requested = {day.isoformat() for day in dates}
        expected = [(min(dates) + timedelta(days=i)).isoformat()
                    for i in range((max(dates) - min(dates)).days + 1)]
        if sorted(daily["time"]) != expected:
            raise WeatherError("날짜 확인 필요: 반환 날짜가 요청 날짜와 달라 해당 결과를 사용하지 않았습니다.",
                               "date_mismatch", {"요청 날짜": sorted(requested), "반환 날짜": daily["time"]})
        records = []
        fetched_at = datetime.now(KST).isoformat(timespec="seconds")
        for i, day in enumerate(daily["time"]):
            if day not in requested:
                continue
            def value(key):
                number = daily[key][i]
                if number is not None and (not isinstance(number, (int, float)) or not math.isfinite(number)):
                    raise ValueError
                return number
            high, low, rain = value("temperature_2m_max"), value("temperature_2m_min"), value("precipitation_probability_max")
            if rain is not None and not 0 <= rain <= 100:
                raise ValueError
            records.append({"date": day, "weekday": "월화수목금토일"[date.fromisoformat(day).weekday()],
                            "high_c": high, "low_c": low, "rain_probability_pct": rain,
                            "source": "https://open-meteo.com/", "fetched_at": fetched_at,
                            "latitude": latitude, "longitude": longitude, "status": "ok"})
        if {r["date"] for r in records} != requested:
            raise WeatherError("날짜 확인 필요: 요청한 날짜의 예보가 모두 반환되지 않아 결과를 사용하지 않았습니다.",
                               "date_mismatch", {"요청 날짜": sorted(requested), "반환 날짜": [r["date"] for r in records]})
        return records
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        raise WeatherError("Open-Meteo 날씨 조회에 실패했습니다. 날짜 범위와 네트워크를 확인해 주세요. 예보 수치는 임의로 만들지 않습니다.") from None
