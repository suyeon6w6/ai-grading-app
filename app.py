# -*- coding: utf-8 -*-
"""
서논술형 답안 자동 채점 웹앱
실행: streamlit run app.py

레이아웃
--------
- 화면 상단 탭(세트1 / 세트2 / 세트3)으로 세트를 직관적으로 선택.
- 사이드바에서 문항(서·논술형1~3) 선택.
- 모범 답안은 기본적으로 숨겨져 있고, expander를 클릭해야만 펼쳐짐.

※ 입력 텍스트 영역과 채점 버튼은 st.form()으로 묶여 있습니다.
   (일반 버튼은 텍스트 입력 직후 바로 클릭하면 방금 입력한 값이 아직
    위젯에 반영되기 전 상태로 읽혀 "채점 결과가 안 뜨는 것처럼" 보이는
    경우가 있어, form으로 제출 시점에만 값을 한 번에 읽어옵니다.)
"""

import streamlit as st
from grading_data import SETS
from grading_engine import grade_q1_blank, grade_q2_pair, grade_q3_pair

st.set_page_config(page_title="서논술형 자동 채점", layout="wide")

st.title("📝 서논술형 답안 자동 채점 연습")
st.caption("2회 시험 대비 · 서·논술형 1~3 자동 채점 도구 (규칙 기반 1차 스크리닝)")

with st.sidebar:
    st.header("문항 선택")
    q_type = st.radio("문항", ["서·논술형1 (빈칸 채우기)", "서·논술형2 (설명 방법 문장)", "서·논술형3 (영상 스토리보드)"])
    st.divider()
    st.info(
        "⚠️ 이 채점 결과는 **1차 자동 스크리닝**입니다.\n\n"
        "'명칭-서술 불일치 의심' 등 플래그가 뜨는 경우는 "
        "반드시 채점자(교사)가 최종 확인해야 합니다."
    )


def show_verdict(passed, reason=""):
    if passed:
        st.success(f"✅ 통과  {('- ' + reason) if reason else ''}")
    else:
        st.error(f"❌ 미충족  {('- ' + reason) if reason else ''}")


def render_q1(set_key, current_set):
    st.subheader(f"{current_set['label']} · 서·논술형1 — 빈칸 채우기")
    q1_config = current_set["q1"]

    with st.form(key=f"form_q1_{set_key}"):
        cols = st.columns(len(q1_config))
        answers = {}
        for col, (blank_name, cfg) in zip(cols, q1_config.items()):
            with col:
                answers[blank_name] = st.text_area(f"{blank_name} 답안", height=100)
        submitted = st.form_submit_button("채점하기", use_container_width=True)

    if submitted:
        st.markdown("### 채점 결과")
        all_pass = True
        for blank_name, cfg in q1_config.items():
            result = grade_q1_blank(answers[blank_name], cfg)
            all_pass = all_pass and result["pass"]
            st.markdown(f"**{blank_name}** — 내가 쓴 답: _{answers[blank_name] or '(미입력)'}_")
            show_verdict(result["pass"], result["reason"])
            with st.expander("세부 판정 근거 보기"):
                st.json(result["detail"])
        st.divider()
        st.markdown(f"### 종합: {'✅ 전체 통과' if all_pass else '❌ 일부 미충족'}")

    st.divider()
    with st.expander("📌 모범 답안 보기 (클릭해서 확인)"):
        for blank_name, cfg in q1_config.items():
            st.markdown(f"**{blank_name}**")
            st.markdown(f"모범 답안 예시: {cfg.get('sample_answer', '(준비 중)')}")
            if cfg.get("hint"):
                st.caption(cfg["hint"])
            st.markdown("---")


def render_q2(set_key, current_set):
    st.subheader(f"{current_set['label']} · 서·논술형2 — 설명 방법 활용 문장 쓰기")
    q2_config = current_set["q2"]

    st.markdown(f"**주어진 첫 문장:** {q2_config['given_sentence']}")
    st.caption("문장 끝에 사용한 설명 방법을 괄호로 표기해 입력하세요. 예: `...효율적이다. (비교와 대조)`")

    with st.form(key=f"form_q2_{set_key}"):
        c1, c2 = st.columns(2)
        with c1:
            sent1 = st.text_area("(1) 문장 입력", height=120)
        with c2:
            sent2 = st.text_area("(2) 문장 입력", height=120)
        submitted = st.form_submit_button("채점하기", use_container_width=True)

    if submitted:
        result = grade_q2_pair(sent1, sent2, q2_config["units"], q2_config["forbidden_external"])
        st.markdown("### 채점 결과")
        show_verdict(result["pass"], result["summary"])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**(1) 세부 결과**")
            r1 = result["sentence1"]
            st.write(f"- 판정 방법명: `{r1.get('label')}`")
            show_verdict(r1["pass"], r1["reason"])
            if r1["detail"].get("flag"):
                st.warning(r1["detail"]["flag"])
            with st.expander("세부 근거"):
                st.json(r1["detail"])
        with col2:
            st.markdown("**(2) 세부 결과**")
            r2 = result["sentence2"]
            st.write(f"- 판정 방법명: `{r2.get('label')}`")
            show_verdict(r2["pass"], r2["reason"])
            if r2["detail"].get("flag"):
                st.warning(r2["detail"]["flag"])
            with st.expander("세부 근거"):
                st.json(r2["detail"])

        if result["duplicate_label"]:
            st.error("🚫 (1)과 (2)에 동일한 설명 방법이 중복 사용되었습니다. 조건 위반으로 자동 오답 처리됩니다.")

    st.divider()
    with st.expander("📌 선택지(설명 방법)별 모범 답안 보기 (클릭해서 확인)"):
        sample_cols = st.columns(len(q2_config["sample_answers"]))
        for col, (method, sample) in zip(sample_cols, q2_config["sample_answers"].items()):
            with col:
                st.markdown(f"**{method}**")
                st.info(sample)


def render_q3(set_key, current_set):
    st.subheader(f"{current_set['label']} · 서·논술형3 — 영상 스토리보드")
    q3_config = current_set["q3"]
    st.markdown(f"**장면1(참고, 대비 대상):** {q3_config['scene1_desc']}")

    with st.form(key=f"form_q3_{set_key}"):
        c1, c2 = st.columns(2)
        with c1:
            text_a = st.text_area("시각 요소(Ⓐ) + 효과 서술", height=160)
        with c2:
            text_b = st.text_area("청각 요소(Ⓑ) + 효과 서술", height=160)
        submitted = st.form_submit_button("채점하기", use_container_width=True)

    if submitted:
        result = grade_q3_pair(text_a, text_b, q3_config)
        st.markdown("### 채점 결과")
        show_verdict(result["pass"])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**시각 요소(Ⓐ)**")
            ra = result["A"]
            show_verdict(ra["pass"], ra["reason"])
            st.write(f"- 필수 요소 충족: {ra['required_ok']} / 장면1 대비 충족: {ra['contrast_ok']}")
        with col2:
            st.markdown("**청각 요소(Ⓑ)**")
            rb = result["B"]
            show_verdict(rb["pass"], rb["reason"])
            st.write(f"- 필수 요소 충족: {rb['required_ok']} / 장면1 대비 충족: {rb['contrast_ok']}")

    st.divider()
    with st.expander("📌 모범 답안 보기 (클릭해서 확인)"):
        sample = q3_config["sample_answer"]
        st.info(f"**시각 요소(Ⓐ):** {sample['A']}\n\n**효과:** {sample['A_effect']}")
        st.info(f"**청각 요소(Ⓑ):** {sample['B']}\n\n**효과:** {sample['B_effect']}")


def render_set(set_key):
    current_set = SETS[set_key]
    if q_type.startswith("서·논술형1"):
        render_q1(set_key, current_set)
    elif q_type.startswith("서·논술형2"):
        render_q2(set_key, current_set)
    else:
        render_q3(set_key, current_set)


# ---------------------------------------------------------------------------
# 세트 탭 — 세트1 / 세트2 / 세트3 이 직관적으로 보이도록 상단 탭으로 구성
# ---------------------------------------------------------------------------
set_keys = list(SETS.keys())
tab_labels = [f"🔵 {SETS[k]['label']}" for k in set_keys]
tabs = st.tabs(tab_labels)

for tab, set_key in zip(tabs, set_keys):
    with tab:
        render_set(set_key)

st.divider()
st.caption(
    "채점 로직 요약 · 문항1: 의미 요소(동의어) 그룹 매칭 + 방향 반대 감지 | "
    "문항2: 관계 단위(조건-방법) 매핑 + 중복/외부지식/명칭-서술 불일치 감지 | "
    "문항3: 필수 요소 + 장면1 대비 요소 검사"
)
