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

# --- 1. 승급 / 강등 기본 판정 함수 ---
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


# --- 2. 방출 위험 판정 함수 (R4, R5 특수 룰) ---
def check_release_risk(rank: str, status_label: str, is_interim: bool) -> tuple[bool, str]:
    is_1_demote = "1단계 강등" in status_label
    is_2_demote = "2단계 강등" in status_label

    # R5: 1단계 또는 2단계 강등 시 방출
    if rank == "R5" and (is_1_demote or is_2_demote):
        if is_interim:
            reason = "R5 계급은 1/2단계 강등 시 클랜 규정에 따라 방출 대상입니다. (현재 성적 유지 시 방출 위험)"
        else:
            reason = "R5 계급에서 1/2단계 강등되어 방출 기준에 해당합니다."
        return True, reason

    # R4: 2단계 강등 시 방출
    elif rank == "R4" and is_2_demote:
        if is_interim:
            reason = "R4 계급은 2단계 강등 시 클랜 규정에 따라 방출 대상입니다. (현재 성적 유지 시 방출 위험)"
        else:
            reason = "R4 계급에서 2단계 강등되어 방출 기준에 해당합니다."
        return True, reason

    return False, ""


# --- 3. 계급 추출 및 정규화 함수 ---
def get_rank_mapping(xls):
    if "의결권" not in xls.sheet_names:
        return {}
    
    df_vote = pd.read_excel(xls, sheet_name="의결권")
    df_vote = df_vote[df_vote["닉네임"].notna() & df_vote["계급"].notna()].copy()
    
    rank_map = {}
    for _, row in df_vote.iterrows():
        nick = str(row["닉네임"]).strip().lower()
        rank = str(row["계급"]).strip()
        rank_map[nick] = rank
    return rank_map


def resolve_member_rank(nick: str, rank_map: dict) -> str:
    cleaned = re.sub(r"\(.*?\)", "", str(nick)).strip().lower()
    
    # 완전 일치
    if cleaned in rank_map:
        return rank_map[cleaned]
    
    # 3회 이상 반복 문자 오타 보정 (예: HONGGO...ON)
    norm_nick = re.sub(r"(.)\1{2,}", r"\1\1\1", cleaned)
    for k, v in rank_map.items():
        if re.sub(r"(.)\1{2,}", r"\1\1\1", k) == norm_nick:
            return v
            
    # 명단에 없으면 기본 R5
    return "R5"


# --- 4. 데이터 로드 및 정제 ---
@st.cache_data
def load_clan_data(file_path: str, mtime: float):
    if not os.path.exists(file_path):
        return None, [], {}

    xls = pd.ExcelFile(file_path)
    rank_map = get_rank_mapping(xls)
    
    date_pattern = re.compile(r"^\d{6}$")
    date_sheets = [s for s in xls.sheet_names if date_pattern.match(str(s).strip())]
    date_sheets.sort(key=lambda x: datetime.strptime(x, "%y%m%d"))
    
    if len(date_sheets) < 2:
        return None, date_sheets, rank_map

    recent_sheets = date_sheets[-2:]
    sheets_data = {}

    for s_name in recent_sheets:
        df = pd.read_excel(xls, sheet_name=s_name)
        df.columns = [str(c).strip() for c in df.columns]

        df = df[df["닉네임"].notna() & df["주간점수"].notna()].copy()
        df = df[pd.to_numeric(df["주간점수"], errors="coerce").notna()].copy()

        df["순수닉네임"] = df["닉네임"].astype(str).apply(lambda x: re.sub(r"\(.*?\)", "", x).strip())
        df["현재계급"] = df["순수닉네임"].apply(lambda n: resolve_member_rank(n, rank_map))

        target_cols = (
            [f"{i}일차" for i in range(1, 7)] +
            [f"{i}일차환산" for i in range(1, 7)] +
            ["총 기부", "추천 기부", "주간점수", "기준1", "기준2", "기준3", "기준4"]
        )
        for col in target_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        df["판정결과"] = df["기준4"].apply(lambda x: evaluate_status(x)[0])
        sheets_data[s_name] = df

    return sheets_data, recent_sheets, rank_map


# --- 5. 앱 화면 표출부 ---
FILE_PATH = "포지마스터_LOVER.xlsx"

if not os.path.exists(FILE_PATH):
    st.error(f"'{FILE_PATH}' 파일을 찾을 수 없습니다. GitHub 레포지토리에 파일이 있는지 확인해주세요.")
    st.stop()

file_mtime = os.path.getmtime(FILE_PATH)
data_dict, recent_weeks, rank_map = load_clan_data(FILE_PATH, file_mtime)

if not data_dict or len(recent_weeks) < 2:
    st.error("분석 가능한 날짜 시트(YYMMDD)가 2개 이상 존재하지 않습니다.")
    st.stop()

prev_week_name, current_week_name = recent_weeks[0], recent_weeks[1]

st.title("🛡️ LOVER 클랜전 개인 결과 조회 시스템")

# [1단계] 주차 선택
st.markdown("#### 1. 조회할 주차를 선택하세요")
view_type = st.radio(
    label="조회 유형",
    options=["지난 주 최종 결과", "이번 주 중간 집계 결과"],
    horizontal=True,
    label_visibility="collapsed"
)

is_interim = (view_type == "이번 주 중간 집계 결과")
selected_sheet_name = current_week_name if is_interim else prev_week_name
current_df = data_dict[selected_sheet_name]

# [2단계] 닉네임 선택 (선택 전까지 점수 미노출)
st.markdown("#### 2. 닉네임을 선택하거나 입력하세요")
user_options = ["(선택하세요)"] + sorted(current_df["순수닉네임"].unique().tolist())
selected_user = st.selectbox(
    label="닉네임 선택",
    options=user_options,
    label_visibility="collapsed"
)

if selected_user == "(선택하세요)":
    st.info("👆 위 목록에서 본인의 닉네임을 선택하면 상세 결과가 표시됩니다.")
    st.stop()

# --- 3. 결과 상세 화면 ---
user_row = current_df[current_df["순수닉네임"] == selected_user]

if user_row.empty:
    st.warning("선택한 주차에 해당 닉네임의 기록이 존재하지 않습니다.")
    st.stop()

u = user_row.iloc[0]
user_rank_title = u.get("현재계급", "R5")
status_label, status_color = evaluate_status(u.get("기준4", 0))

# 방출 위험 여부 확인
is_danger, danger_reason = check_release_risk(user_rank_title, status_label, is_interim)

st.markdown("---")
st.subheader(f"📊 [{user_rank_title}] {selected_user} 님의 {view_type} (`{selected_sheet_name}`)")

# [기본 정보 카드]
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("현재 계급", user_rank_title)
col2.metric("주간 획득 점수", f"{int(u.get('주간점수', 0)):,} 점")
col3.metric("총 기부량", f"{int(u.get('총 기부', 0)):,} 회")
col4.metric("추천 기부량", f"{int(u.get('추천 기부', 0)):,} 회")

with col5:
    st.markdown("**현재 판정 상태**")
    badge_bg = "#EF444422" if is_danger else f"{status_color}22"
    badge_border = "#EF4444" if is_danger else status_color
    badge_text_color = "#DC2626" if is_danger else (status_color if status_color != "#FFC000" else "#D97706")
    badge_label = f"{status_label} (🚨 방출 위험)" if is_danger else status_label

    st.markdown(
        f"""
        <div style="
            background-color: {badge_bg};
            border: 2px solid {badge_border};
            border-radius: 8px;
            padding: 8px 10px;
            text-align: center;
            font-size: 1.0rem;
            font-weight: bold;
            color: {badge_text_color};
        ">
            {badge_label}
        </div>
        """,
        unsafe_allow_html=True
    )

# [방출 위험 경고 알림 배너]
if is_danger:
    st.markdown("<br>", unsafe_allow_html=True)
    if is_interim:
        st.error(
            f"🚨 **방출 위험 경고**: **[{user_rank_title}] {selected_user}** 님은 현재 중간 집계 기준 **{status_label}**권입니다. "
            f"\n\n{danger_reason} 클랜전 참여 및 기부로 점수를 끌어올려 강등권을 탈출해주세요!"
        )
    else:
        st.error(
            f"🚨 **방출 대상 확인**: **[{user_rank_title}] {selected_user}** 님은 지난 주 최종 집계 결과 **{status_label}**을 기록하여 방출 기준에 해당되었습니다."
        )

st.markdown("<br>", unsafe_allow_html=True)

# [기준 1, 2, 3, 4 점수 카드]
st.markdown("##### 📌 종합 산출 기준 점수")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("기준 1 (환산점수 합계)", f"{u.get('기준1', 0):.2f}")
kpi2.metric("기준 2 (클랜전 환산 Z)", f"{u.get('기준2', 0):.2f}")
kpi3.metric("기준 3 (기부 환산 Z)", f"{u.get('기준3', 0):.2f}")
kpi4.metric("기준 4 (최종 환산점수)", f"{u.get('기준4', 0):.2f}")

st.markdown("---")

# [1~6일차 상세 테이블]
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
