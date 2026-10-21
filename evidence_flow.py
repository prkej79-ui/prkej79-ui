"""내부 생각 대신 원결과 → 검사 → 계획의 입력과 근거 연결을 기록합니다."""

from copy import deepcopy
import hashlib
import json

from chat_flow import answer_places


def build_evidence_flow(result, validation, facts, status, sources):
    encoded = json.dumps(result["input"], ensure_ascii=False, sort_keys=True).encode("utf-8")
    input_id = hashlib.sha256(encoded).hexdigest()[:16]
    roles = []
    for key in ("A", "B"):
        role = result[key]
        traces = role["execution"].get("traces", [])
        last = traces[-1] if traces else {}
        records = (last.get("결과", []) if last.get("결과 종류") == "weather" else []) if key == "B" else answer_places(role["execution"])
        roles.append({"role": key, "input": deepcopy(role["input"]), "status": role["status"],
                      "source": deepcopy(role["source"]), "tool_calls": len(traces),
                      "last_tool": last.get("도구"), "last_status": last.get("status"),
                      "records": deepcopy(records)})
    return [
        {"step": 1, "stage": "원결과", "input_id": input_id, "input": deepcopy(result["input"]),
         "status": {key: result[key]["status"] for key in ("A", "B")}, "roles": roles},
        {"step": 2, "stage": "검사", "input_id": input_id, "from_step": 1,
         "status": validation["status"], "codes": list(validation["codes"]),
         "warnings": list(validation["warnings"]), "weather_usable": validation["weather_usable"],
         "adopted_place_urls": [place["url"] for place in facts["places"]],
         "adopted_weather_dates": [row["date"] for row in facts["weather"]],
         "excluded_place_count": max(0, len(roles[0]["records"]) - len(facts["places"])),
         "excluded_weather_count": max(0, len(roles[1]["records"]) - len(facts["weather"]))},
        {"step": 3, "stage": "계획", "input_id": input_id, "from_step": 2,
         "status": status, "facts": deepcopy(facts), "source": deepcopy(sources),
         "suggestions_separated_from_facts": True},
    ]
