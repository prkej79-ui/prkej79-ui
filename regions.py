"""주소의 행정구역을 분리해 표기 차이를 정규화합니다. 도로명은 지역 대조에 쓰지 않습니다."""

import re


PROVINCES = {
    "서울": ("서울특별시", "서울시", "서울"), "부산": ("부산광역시", "부산시", "부산"),
    "대구": ("대구광역시", "대구시", "대구"), "인천": ("인천광역시", "인천시", "인천"),
    "광주": ("광주광역시", "광주"), "대전": ("대전광역시", "대전시", "대전"),
    "울산": ("울산광역시", "울산시", "울산"), "세종": ("세종특별자치시", "세종시", "세종"),
    "경기": ("경기도", "경기"), "강원": ("강원특별자치도", "강원도", "강원"),
    "충북": ("충청북도", "충북"), "충남": ("충청남도", "충남"),
    "전북": ("전북특별자치도", "전라북도", "전북"), "전남": ("전라남도", "전남"),
    "경북": ("경상북도", "경북"), "경남": ("경상남도", "경남"),
    "제주": ("제주특별자치도", "제주도", "제주"),
}
PREFIXES = sorted([(alias, (canonical,)) for canonical, aliases in PROVINCES.items() for alias in aliases]
                  + [("전남광주통합특별시", ("전남", "광주"))], key=lambda item: len(item[0]), reverse=True)


def parse_region(text: str):
    remaining = re.sub(r"[,·()]", " ", text).strip()
    province = ()
    for alias, canonical in PREFIXES:
        if remaining.startswith(alias):
            tail = remaining[len(alias):]
            # '광주시'는 광주광역시가 아닌 시 이름일 수 있습니다.
            if alias == "광주" and tail.startswith("시"):
                continue
            province, remaining = canonical, tail.strip()
            break
    divisions = []
    while remaining:
        match = re.match(r"([가-힣]+?)(시|군|구)", remaining)
        if not match:
            match = re.match(r"([가-힣]+?)(읍|면|동|리)(?=\s|$)", remaining)
        if not match:
            # 접미사가 없는 '담양', '경주'도 허용하되 도로명·번지는 무시합니다.
            if not divisions:
                word = remaining.split()[0]
                if re.fullmatch(r"[가-힣]+", word) and not word.endswith(("로", "길")):
                    divisions.append(("생략", word))
            break
        divisions.append((match[2], match[1]))
        remaining = remaining[match.end():].strip()
    return province, tuple(divisions)


def region_matches(region: str, address: str) -> bool:
    expected_province, expected = parse_region(region)
    actual_province, actual = parse_region(address)
    if not expected_province and not expected:
        return False
    if expected_province and not set(expected_province).intersection(actual_province):
        return False
    for kind, name in expected:
        if not any(name == actual_name and (kind == actual_kind or kind == "생략" or actual_kind == "생략")
                   for actual_kind, actual_name in actual):
            return False
    return True


def search_region(region: str) -> str:
    """후보의 과도한 상세 주소를 제외하고 시·군·구 검색어를 만듭니다."""
    province, divisions = parse_region(region)
    main = [(kind, name) for kind, name in divisions if kind in ("시", "군", "구", "생략")]
    chosen = main or list(divisions)
    parts = [province[0]] if province else []
    parts += [name + ("" if kind == "생략" else kind) for kind, name in chosen]
    return " ".join(parts)
