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

# --- 1. 데이터 로드 및 정제 ---
@st.cache_data
def load_clan_data(file_path: str, mtime: float):
    if not os.path.exists(file_path):
        return None, []

    xls = pd.ExcelFile(file_path)
    
    # YYMMDD 형식의 날짜 시트만 추출 및 정렬
    date_pattern = re.compile(r"^\d{6}$")
    date_sheets = [s for s in xls.sheet_names if date_pattern.match(str(s).strip())]
    date_sheets.sort(key=lambda x: datetime.strptime(x, "%y%m%d"))
    
    if len(date_sheets) < 2:
        return None, date_sheets

    recent_sheets = date_sheets[-2:]  # [지난 주(직전주), 이번 주(최근주)]
    sheets_data = {}

    for s_name in recent_sheets:
        df = pd.read_excel(xls, sheet_name=s_name)
        df.columns = [str(c).strip() for c in df.columns]

        # 유효 유저 필터링 (닉네임과 주간점수가 있는 행)
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

        # 기준 4 종합 순위 산출 (승급/강등 판정용)
        if "기준4" in df.columns:
            df["종합순위"] = df["기준4"].rank(ascending=False, method="min").astype(int)

        sheets_data[s_name] = df

    return sheets_data, recent_sheets


# --- 2. 앱 실행 및 단계별 선택 UI ---
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

# [2단계] 닉네임 선택/입력 (선택 전까지 점수 표시 차단)
st.markdown("#### 2. 닉네임을 선택하거나 입력하세요")
user_options = ["(선택하세요)"] + sorted(current_df["순수닉네임"].unique().tolist())
selected_user = st.selectbox(
    label="닉네임 선택",
    options=user_options,
    label_visibility="collapsed"
)

# 닉네임을 고르지 않은 상태에서는 화면에 결과를 전혀 띄우지 않음
if selected_user == "(선택하세요)":
    st.info("👆 위 목록에서 본인의 닉네임을 선택하면 상세 결과가 표시됩니다.")
    st.stop()

# --- 3. 상세 결과 표출 (닉네임 선택 완료 시점) ---
user_row = current_df[current_df["순수닉네임"] == selected_user]

if user_row.empty:
    st.warning("선택한 주차에 해당 닉네임의 기록이 존재하지 않습니다.")
    st.stop()

u = user_row.iloc[0]

st.markdown("---")
st.subheader(f"📊 [{selected_user}] 님의 {view_type} (`{selected_sheet_name}`)")

# [상태 요약 카드: 기부량 / 종합 순위 / 승급·강등 여부]
total_members = len(current_df)
user_rank = int(u["종합순위"]) if "종합순위" in u else 0

# --- 승급/강등 임시 판정 로직 (기준을 알려주시면 즉시 교체 가능) ---
# 예: 종합순위 상위 5명 승급, 하위 5명 강등/주의
if user_rank <= 5:
    status_text = "🟢 승급권"
elif user_rank > total_members - 5:
    status_text = "🔴 강등/방출권"
else:
    status_text = "⚪ 유지"

top_c1, top_c2, top_c3, top_c4 = st.columns(4)
top_c1.metric("총 기부량", f"{int(u.get('총 기부', 0)):,} 회")
top_c2.metric("추천 기부량", f"{int(u.get('추천 기부', 0)):,} 회")
top_c3.metric("종합 랭킹 (기준4)", f"{user_rank} 위 / {total_members}명")
top_c4.metric("현재 승급/강등 상태", status_text)

# [기준 1, 2, 3, 4 점수 카드]
st.markdown("##### 📌 종합 산출 기준 점수")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("기준 1 (환산점수 합계)", f"{u.get('기준1', 0):.2f}")
kpi2.metric("기준 2 (전투력 환산 Z)", f"{u.get('기준2', 0):.2f}")
kpi3.metric("기준 3 (기부 환산 Z)", f"{u.get('기준3', 0):.2f}")
kpi4.metric("기준 4 (종합 합산점수)", f"{u.get('기준4', 0):.2f}")

st.markdown("---")

# [1~6일차 일일 점수 및 환산점수 비교 테이블]
st.markdown("##### 📅 1~6일차 상세 결과 및 환산점수")

day_labels = [f"{i}일차" for i in range(1, 7)]
raw_scores = [u.get(f"{i}일차", 0) for i in range(1, 7)]
conv_scores = [u.get(f"{i}일차환산", 0) for i in range(1, 7)]

detail_df = pd.DataFrame({
    "구분": day_labels,
    "획득 점수 (원점수)": raw_scores,
    "환산점수": conv_scores
})

st.dataframe(
    detail_df.T,  # 모바일에서 한눈에 보기 편하도록 가로형 배치
    use_container_width=True
)
