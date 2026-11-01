import os
import re
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="LOVER 클랜전 결과 조회",
    page_icon="🛡️",
    layout="wide"
)

# --- 1. 승급 / 강등 판정 함수 ---
def evaluate_status(val_k4):
    if pd.isna(val_k4):
        return "데이터 없음", "#808080"
    if val_k4 >= 2.5:
        return "🟦 2단계 승급", "#00B0F0"
    elif val_k4 >= 1.5:
        return "🟩 1단계 승급", "#92D050"
    elif val_k4 < -4.0:
        return "🟥 2단계 강등", "#FF0000"
    elif val_k4 < -2.5:
        return "🟧 1단계 강등", "#FFC000"
    else:
        return "⬜ 유지", "#808080"


# --- 2. 데이터 로드 및 정제 ---
@st.cache_data
def load_clan_data(file_path: str, mtime: float):
    if not os.path.exists(file_path):
        return None, []

    xls = pd.ExcelFile(file_path)
    
    # YYMMDD 형식의 날짜 시트 추출 및 정렬
    date_pattern = re.compile(r"^\d{6}$")
    date_sheets = [s for s in xls.sheet_names if date_pattern.match(str(s).strip())]
    date_sheets.sort(key=lambda x: datetime.strptime(x, "%y%m%d"))
    
    if len(date_sheets) < 2:
        return None, date_sheets

    recent_sheets = date_sheets[-2:]  # [지난 주 최종, 이번 주 중간]
    sheets_data = {}

    for s_name in recent_sheets:
        df = pd.read_excel(xls, sheet_name=s_name)
        df.columns = [str(c).strip() for c in df.columns]

        # 유효 유저 필터링
        df = df[df["닉네임"].notna() & df["주간점수"].notna()].copy()
        df = df[pd.to_numeric(df["주간점수"], errors="coerce").notna()].copy()

        df["순수닉네임"] = df["닉네임"].astype(str).apply(lambda x: re.sub(r"\(.*?\)", "", x).strip())

        # 수치형 변환
        target_cols = (
            [f"{i}일차" for i in range(1, 7)] +
            [f"{i}일차환산" for i in range(1, 7)] +
            ["총 기부", "추천 기부", "주간점수", "기준1", "기준2", "기준3", "기준4"]
        )
        for col in target_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # 기준4 기반 판정 결과 부여
        df["판정결과"] = df["기준4"].apply(lambda x: evaluate_status(x)[0])
        sheets_data[s_name] = df

    return sheets_data, recent_sheets


# --- 3. 앱 실행부 ---
FILE_PATH = "포지마스터_LOVER.xlsx"

if not os.path.exists(FILE_PATH):
    st.error(f"'{FILE_PATH}' 파일을 찾을 수 없습니다. 레포지토리에 파일이 존재하는지 확인해주세요.")
    st.stop()

file_mtime = os.path.getmtime(FILE_PATH)
data_dict, recent_weeks = load_clan_data(FILE_PATH, file_mtime)

if not data_dict or len(recent_weeks) < 2:
    st.error("분석 가능한 날짜 시트(YYMMDD)가 2개 이상 존재하지 않습니다.")
    st.stop()

prev_week_name = recent_weeks[0]    # 지난 주 최종 결과 시트
current_week_name = recent_weeks[1] # 이번 주 중간 집계 시트

st.title("🛡️ LOVER 클랜전 개인 결과 조회 시스템")

# [1단계] 주차 선택
st.markdown("#### 1. 조회할 주차를 선택하세요")
view_type = st.radio(
    label="조회 유형",
    options=["지난 주 최종 결과", "이번 주 중간 집계 결과"],
    horizontal=True,
    label_visibility="collapsed"
)

selected_sheet_name = prev_week_name if view_type == "지난 주 최종 결과" else current_week_name
current_df = data_dict[selected_sheet_name]

# [2단계] 닉네임 선택/입력 (선택 전까지 점수 미노출)
st.markdown("#### 2. 닉네임을 선택하거나 입력하세요")
user_options = ["(선택하세요)"] + sorted(current_df["순수닉네임"].unique().tolist())
selected_user = st.selectbox(
    label="닉네임 선택",
    options=user_options,
    label_visibility="collapsed"
)

# 닉네임을 선택하기 전에는 점수를 일체 표시하지 않음
if selected_user == "(선택하세요)":
    st.info("👆 위 목록에서 본인의 닉네임을 선택하면 상세 결과가 표시됩니다.")
    st.stop()

# --- 3. 상세 결과 표출 ---
user_row = current_df[current_df["순수닉네임"] == selected_user]

if user_row.empty:
    st.warning("선택한 주차에 해당 닉네임의 기록이 존재하지 않습니다.")
    st.stop()

u = user_row.iloc[0]
status_label, status_color = evaluate_status(u.get("기준4", 0))

st.markdown("---")
st.subheader(f"📊 [{selected_user}] 님의 {view_type} (`{selected_sheet_name}`)")

# [기부량 및 승급/강등 결과 배너]
col1, col2, col3, col4 = st.columns(4)
col1.metric("주간 획득 점수", f"{int(u.get('주간점수', 0)):,} 점")
col2.metric("총 기부량", f"{int(u.get('총 기부', 0)):,} 회")
col3.metric("추천 기부량", f"{int(u.get('추천 기부', 0)):,} 회")

with col4:
    st.markdown("**현재 승급 / 강등 상태**")
    st.markdown(
        f"""
        <div style="
            background-color: {status_color}22;
            border: 2px solid {status_color};
            border-radius: 8px;
            padding: 8px 14px;
            text-align: center;
            font-size: 1.15rem;
            font-weight: bold;
            color: {status_color if status_color != '#FFC000' else '#D97706'};
        ">
            {status_label}
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

# [기준 1, 2, 3, 4 점수 카드]
st.markdown("##### 📌 종합 산출 기준 점수")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("기준 1 (환산점수 합계)", f"{u.get('기준1', 0):.2f}")
kpi2.metric("기준 2 (전투력 환산 Z)", f"{u.get('기준2', 0):.2f}")
kpi3.metric("기준 3 (기부 환산 Z)", f"{u.get('기준3', 0):.2f}")
kpi4.metric("기준 4 (종합 환산점수)", f"{u.get('기준4', 0):.2f}")

st.markdown("---")

# [1~6일차 점수 및 일차별 환산점수 테이블]
st.markdown("##### 📅 1~6일차 상세 획득 점수 및 환산점수")

day_cols = [f"{i}일차" for i in range(1, 7)]
conv_cols = [f"{i}일차환산" for i in range(1, 7)]

raw_scores = [f"{int(u.get(d, 0)):,} 점" if u.get(d, 0) > 0 else "-" for d in day_cols]
conv_scores = [f"{u.get(c, 0):.2f}" if u.get(c, 0) != 0 else "-" for c in conv_cols]

detail_df = pd.DataFrame(
    [raw_scores, conv_scores],
    index=["획득 점수 (원점수)", "일차별 환산점수"],
    columns=[f"{i}일차" for i in range(1, 7)]
)

st.dataframe(detail_df, use_container_width=True)
