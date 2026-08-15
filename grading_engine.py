# -*- coding: utf-8 -*-
"""
자동 채점 로직
--------------
문항1: 빈칸 채우기 (의미 요소 기반, 일부는 고유 명칭 정확 일치)
문항2: 설명 방법 활용 문장 쓰기 (관계 단위 매핑 + 방향/중복/외부지식/명칭-서술 일치 검사)
문항3: 영상 스토리보드 (필수 요소 + 대비 요소 검사)

원칙
----
- "용어가 없어도 의미가 담기면 인정" -> required 그룹의 동의어 리스트로 구현.
- "선택한 설명 방법의 특성이 답안에 드러나야 함" -> METHOD_CUES로 1차 스크리닝, 신호가 전혀 없으면
  '명칭-서술 불일치 의심'으로 플래그 (자동 오답이 아니라 사람 확인 요청 - 신호 기반 오탐 방지).
- "오개념 방지" -> 각 관계 단위(U/V/W)의 요소가 반대 단위와 뒤바뀌어 매핑되면 방향 오류로 자동 처리.
- "결론 방향 확인" -> conclusion_required / conclusion_reversal 로 구현 (세트3 문항1 ㉡, ㉢).
"""

import re
from grading_data import METHOD_CUES, METHOD_NORMALIZE


def _contains_any(text, synonyms):
    return any(syn in text for syn in synonyms)


def _check_groups(text, groups):
    """groups: [[syn,...], [syn,...], ...] -> (전체충족여부, 그룹별충족여부리스트)"""
    results = [_contains_any(text, g) for g in groups]
    return all(results), results


# ---------------------------------------------------------------------------
# 문항1 채점
# ---------------------------------------------------------------------------
def grade_q1_blank(text, config):
    text = (text or "").strip()
    detail = {}

    if not text:
        return {"pass": False, "reason": "미작성", "detail": {}}

    # 세트3 ㉡처럼 결론+근거 이중 요구가 있는 경우
    if config.get("dual_requirement"):
        concl_ok, concl_detail = _check_groups(text, config["conclusion_required"])
        reason_ok, reason_detail = _check_groups(text, config["reason_required"])
        reversed_ = _contains_any(text, config.get("conclusion_reversal", []))
        detail["결론_충족"] = concl_ok
        detail["근거_충족"] = reason_ok
        detail["결론_반대_감지"] = reversed_
        if reversed_:
            return {"pass": False, "reason": "결론 방향 반대(예술로 인정하는 취지로 서술됨)", "detail": detail}
        if concl_ok and reason_ok:
            return {"pass": True, "reason": "결론·근거 모두 충족", "detail": detail}
        missing = []
        if not concl_ok:
            missing.append("결론(예술로 보기 어렵다는 판단)")
        if not reason_ok:
            missing.append("근거(감정/철학 없음)")
        return {"pass": False, "reason": f"누락: {', '.join(missing)}", "detail": detail}

    # 고유 명칭 정확 일치형 (세트1 ㉢)
    if "exact_terms" in config:
        exact_ok = any(t in text for t in config["exact_terms"])
        confusable_hit = _contains_any(text, config.get("confusable", []))
        detail["정확명칭_포함"] = exact_ok
        detail["혼동개념_포함"] = confusable_hit
        if confusable_hit and not exact_ok:
            return {"pass": False, "reason": "혼동 개념(반대 개념)의 명칭을 사용함", "detail": detail}
        if exact_ok:
            return {"pass": True, "reason": "정확한 명칭 일치", "detail": detail}
        return {"pass": False, "reason": "고유 명칭 불일치(유의어/설명형 불인정)", "detail": detail}

    # 일반 의미 요소 그룹형
    ok, group_results = _check_groups(text, config["required"])
    detail["요소별_충족"] = group_results
    reversal_hit = _contains_any(text, config.get("reversal", []))
    detail["방향_반대_감지"] = reversal_hit
    if reversal_hit:
        return {"pass": False, "reason": "방향 반대 표현 감지(반대 개념으로 서술됨)", "detail": detail}
    if ok:
        return {"pass": True, "reason": "필수 의미 요소 모두 충족", "detail": detail}
    missing_idx = [i for i, r in enumerate(group_results) if not r]
    return {"pass": False, "reason": f"필수 요소 {len(missing_idx)}개 누락", "detail": detail}


# ---------------------------------------------------------------------------
# 문항2 채점
# ---------------------------------------------------------------------------
def _extract_label(sentence):
    """문장 끝 괄호에서 설명 방법 명칭 추출 및 정규화"""
    m = re.findall(r"\(([^()]+)\)\s*$", sentence.strip())
    if not m:
        return None, sentence.strip()
    raw_label = m[-1].strip()
    body = sentence.strip()[: sentence.strip().rfind("(")].strip()
    norm = METHOD_NORMALIZE.get(raw_label, raw_label)
    return norm, body


def _map_to_units(body_text, units):
    """문장 본문이 어떤 관계 단위(U1/U2 등)의 condition/method에 매핑되는지 판정"""
    mapping = {}
    for uname, u in units.items():
        cond_hit = _contains_any(body_text, u["condition"])
        method_hit = _contains_any(body_text, u["method"])
        mapping[uname] = {"condition": cond_hit, "method": method_hit}
    return mapping


def grade_q2_sentence(sentence, method_stated, units, forbidden_external):
    """
    단일 문장 채점.
    method_stated: 괄호에서 추출된(정규화된) 설명 방법명
    """
    detail = {}
    label, body = _extract_label(sentence)

    if label is None:
        return {"pass": False, "reason": "괄호 안 설명 방법 명칭 미기재", "detail": detail}

    # 1) 명칭-서술 방식 일치 1차 스크리닝
    cues = METHOD_CUES.get(label, [])
    cue_hit = _contains_any(body, cues) if cues else True
    detail["명칭-서술_신호_일치"] = cue_hit
    if not cue_hit:
        detail["flag"] = "명칭-서술 불일치 의심 (채점자 확인 필요)"

    # 2) 외부지식(잔여) 검사
    ext_hit = _contains_any(body, forbidden_external)
    detail["외부지식_감지"] = ext_hit
    if ext_hit:
        return {"pass": False, "reason": "지문에 없는 외부 지식/배경지식 삽입 감지", "detail": detail, "label": label}

    # 3) 관계 단위 매핑 + 방향(오개념) 오류 검사
    mapping = _map_to_units(body, units)
    detail["단위_매핑"] = mapping

    fully_matched_units = [u for u, m in mapping.items() if m["condition"] and m["method"]]
    mismatched = [
        u for u, m in mapping.items()
        if (m["condition"] and not m["method"]) or (not m["condition"] and m["method"])
    ]

    if fully_matched_units:
        return {
            "pass": True,
            "reason": f"관계 단위 완전 매핑: {', '.join(fully_matched_units)}",
            "detail": detail,
            "label": label,
        }

    if mismatched:
        # 조건은 A단위인데 방법은 B단위인 경우 -> 오개념(방향 뒤바뀜)
        return {
            "pass": False,
            "reason": "조건과 방법이 서로 다른 개념에서 뒤섞임(오개념/방향 오류)",
            "detail": detail,
            "label": label,
        }

    return {
        "pass": False,
        "reason": "지문의 관계 단위 어디에도 매핑되지 않음",
        "detail": detail,
        "label": label,
    }


def grade_q2_pair(sentence1, sentence2, units, forbidden_external):
    """(1),(2) 두 문장을 함께 채점 - 중복 라벨 검사 포함"""
    label1, _ = _extract_label(sentence1)
    label2, _ = _extract_label(sentence2)

    result1 = grade_q2_sentence(sentence1, label1, units, forbidden_external)
    result2 = grade_q2_sentence(sentence2, label2, units, forbidden_external)

    duplicate = (label1 is not None and label1 == label2)

    overall_pass = result1["pass"] and result2["pass"] and not duplicate
    reasons = []
    if duplicate:
        reasons.append(f"(1)과 (2)에 동일한 설명 방법('{label1}') 중복 사용 - 조건 위반")
    if not result1["pass"]:
        reasons.append(f"(1) 미충족: {result1['reason']}")
    if not result2["pass"]:
        reasons.append(f"(2) 미충족: {result2['reason']}")

    return {
        "pass": overall_pass,
        "duplicate_label": duplicate,
        "sentence1": result1,
        "sentence2": result2,
        "summary": "모두 충족" if overall_pass else " / ".join(reasons),
    }


# ---------------------------------------------------------------------------
# 문항3 채점
# ---------------------------------------------------------------------------
def grade_q3_element(text, required_groups, contrast_forbidden):
    text = (text or "").strip()
    if not text:
        return {"pass": False, "reason": "미작성", "required_ok": False, "contrast_ok": False}

    required_ok, group_results = _check_groups(text, required_groups)
    contrast_violation = _contains_any(text, contrast_forbidden)
    contrast_ok = not contrast_violation

    if not required_ok:
        return {
            "pass": False,
            "reason": "필수 요소 누락",
            "required_ok": False,
            "contrast_ok": contrast_ok,
            "group_results": group_results,
        }
    if not contrast_ok:
        return {
            "pass": False,
            "reason": "장면1과 대비되지 않음(유사한 연출 요소 포함)",
            "required_ok": True,
            "contrast_ok": False,
            "group_results": group_results,
        }
    return {
        "pass": True,
        "reason": "필수 요소 충족 + 장면1과 대비 확인됨",
        "required_ok": True,
        "contrast_ok": True,
        "group_results": group_results,
    }


def grade_q3_pair(text_a, text_b, config):
    result_a = grade_q3_element(text_a, config["A_required"], config["A_contrast_forbidden"])
    result_b = grade_q3_element(text_b, config["B_required"], config["B_contrast_forbidden"])
    overall = result_a["pass"] and result_b["pass"]
    return {"pass": overall, "A": result_a, "B": result_b}
