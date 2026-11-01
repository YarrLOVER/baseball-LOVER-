import os
import re
from datetime import datetime
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="LOVER 클랜전 전적 검색기",
    page_icon="⚔️",
    layout="wide"
)

# --- 데이터 로드 함수 (순수 pandas 기반으로 안전하게 처리) ---
@st.cache_data
def get_recent_two_weeks_data(file_path: str, mtime: float):
    if not os.path.exists(file_path):
        return None, []

    xls = pd.ExcelFile(file_path)
    
    # 1. 6자리 숫자(YYMMDD) 시트만 추출 후 날짜순 정렬
    date_pattern = re.compile(r"^\d{6}$")
    date_sheets = [s for s in xls.sheet_names if date_pattern.match(str(s).strip())]
    date_sheets.sort(key=lambda x: datetime.strptime(x, "%y%m%d"))
    
    if len(date_sheets) < 2:
        return None, date_sheets

    # 최신 2개 주차 시트 선택 (직전주, 최근주)
    recent_sheets = date_sheets[-2:]
    dfs = {}

    for s_name in recent_sheets:
        # 해당 주차 시트만 읽기
        df = pd.read_excel(xls, sheet_name=s_name)
        df.columns = [str(c).strip() for c in df.columns]

        # 닉네임과 점수가 유효한 행만 필터링 (통계/요약 행 제외)
        df = df[df["닉네임"].notna() & df["주간점수"].notna()].copy()
        df = df[pd.to_numeric(df["주간점수"], errors="coerce").notna()].copy()

        df["주간점수"] = pd.to_numeric(df["주간점수"], errors="coerce")
        df["순수닉네임"] = df["닉네임"].astype(str).apply(lambda x: re.sub(r"\(.*?\)", "", x).strip())

        # 수치형 컬럼 변환
        num_cols = ["기준1", "기준2", "기준3", "기준4"] + \
                   [f"{i}일차" for i in range(1, 7)] + \
                   [f"{i}일차환산" for i in range(1, 7)]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # 랭킹 계산
        if "기준2" in df.columns:
            df["환산순위"] = df["기준2"].rank(ascending=False, method="min").astype(int)
        df["점수순위"] = df["주간점수"].rank(ascending=False, method="min").astype(int)

        dfs[s_name] = df

    return dfs, recent_sheets


# --- 메인 실행부 ---
FILE_PATH = "포지마스터_LOVER.xlsx"

if not os.path.exists(FILE_PATH):
    st.error(f"'{FILE_PATH}' 파일을 찾을 수 없습니다. GitHub 레포지토리 최상위 경로에 파일이 있는지 확인해주세요.")
    st.stop()

# 파일 최종 수정 시간을 넘겨 파일 변경 시 캐시 자동 갱신
file_mtime = os.path.getmtime(FILE_PATH)
data_dict, recent_weeks = get_recent_two_weeks_data(FILE_PATH, file_mtime)

if not data_dict or len(recent_weeks) < 2:
    st.error("분석 가능한 날짜 시트(YYMMDD 형식)가 2개 이상 존재하지 않습니다.")
    st.stop()

prev_week, latest_week = recent_weeks[0], recent_weeks[1]
df_prev = data_dict[prev_week]
df_latest = data_dict[latest_week]

st.title(f"⚔️ LOVER 클랜전 최근 2주 비교 분석 ({prev_week} vs {latest_week})")

# 2주간 한 번이라도 참여한 유저 목록
all_users = sorted(list(set(df_latest["순수닉네임"]).union(set(df_prev["순수닉네임"]))))
selected_user = st.selectbox("조회할 닉네임을 선택하거나 입력하세요:", options=all_users)

if selected_user:
    u_latest = df_latest[df_latest["순수닉네임"] == selected_user]
    u_prev = df_prev[df_prev["순수닉네임"] == selected_user]

    score_latest = u_latest["주간점수"].values[0] if not u_latest.empty else 0
    score_prev = u_prev["주간점수"].values[0] if not u_prev.empty else 0
    score_delta = score_latest - score_prev

    conv_latest = u_latest["기준2"].values[0] if not u_latest.empty else 0.0
    conv_prev = u_prev["기준2"].values[0] if not u_prev.empty else 0.0
    conv_delta = conv_latest - conv_prev

    rank_latest = u_latest["환산순위"].values[0] if not u_latest.empty else None
    rank_prev = u_prev["환산순위"].values[0] if not u_prev.empty else None

    # 상단 요약 카드 (Delta 표시)
    st.markdown("### 📊 최근 실적 요약")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        label=f"주간점수 ({latest_week})",
        value=f"{int(score_latest):,} 점",
        delta=f"{int(score_delta):,} 점" if score_prev > 0 else "신규 참전"
    )
    c2.metric(
        label=f"환산점수 기준2 ({latest_week})",
        value=f"{conv_latest:.2f} 점",
        delta=f"{conv_delta:+.2f} 점" if conv_prev > 0 else "신규 참전"
    )

    if rank_latest and rank_prev:
        rank_diff = rank_prev - rank_latest  # 순위 상승 시 양수로 표기
        c3.metric(label=f"클랜 내 순위 ({latest_week})", value=f"{rank_latest} 위", delta=f"{rank_diff:+d} 계단")
    elif rank_latest:
        c3.metric(label=f"클랜 내 순위 ({latest_week})", value=f"{rank_latest} 위", delta="신규 참전")
    else:
        c3.metric(label=f"클랜 내 순위 ({latest_week})", value="미참여", delta=None)

    st.markdown("---")

    # 최근 2주 일차별 환산점수 비교 테이블
    st.markdown(f"### 📅 일차별 환산점수 비교 (`{prev_week}` vs `{latest_week}`)")
    days = [f"{i}일차환산" for i in range(1, 7)]

    row_prev = [u_prev[d].values[0] if not u_prev.empty and d in u_prev else 0 for d in days]
    row_latest = [u_latest[d].values[0] if not u_latest.empty and d in u_latest else 0 for d in days]

    comp_df = pd.DataFrame({
        "일차": [f"{i}일차" for i in range(1, 7)],
        f"직전주 ({prev_week})": row_prev,
        f"최근주 ({latest_week})": row_latest
    })
    comp_df["증감(Delta)"] = comp_df[f"최근주 ({latest_week})"] - comp_df[f"직전주 ({prev_week})"]

    st.dataframe(
        comp_df.style.format({
            f"직전주 ({prev_week})": "{:.2f}",
            f"최근주 ({latest_week})": "{:.2f}",
            "증감(Delta)": "{:+.2f}"
        }),
        use_container_width=True
    )
