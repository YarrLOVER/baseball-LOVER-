import re
from datetime import datetime
import openpyxl
import pandas as pd
import streamlit as st

# [중요] openpyxl 문자열 필터 파싱 버그 방지 패치
def patched_set(self, instance, value):
    if isinstance(value, str):
        self.expected_type = str
    super(openpyxl.worksheet.filters.CustomFilterValueDescriptor, self).__set__(instance, value)

openpyxl.worksheet.filters.CustomFilterValueDescriptor.__set__ = patched_set


@st.cache_data
def get_recent_two_weeks_data(file_path: str):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    
    # 1. 날짜 시트(YYMMDD)만 추출 및 정렬
    date_pattern = re.compile(r"^\d{6}$")
    date_sheets = [s for s in wb.sheetnames if date_pattern.match(str(s).strip())]
    date_sheets.sort(key=lambda x: datetime.strptime(x, "%y%m%d"))
    
    if len(date_sheets) < 2:
        return None, date_sheets

    recent_sheets = date_sheets[-2:]  # [직전주, 최신주]
    dfs = {}

    for s_name in recent_sheets:
        ws = wb[s_name]
        data = list(ws.values)
        
        # '닉네임' 컬럼 위치 탐색
        header_idx = next(i for i, row in enumerate(data) if row and "닉네임" in [str(c).strip() for c in row if c])
        
        headers = [str(c).strip() if c is not None else f"col_{idx}" for idx, c in enumerate(data[header_idx])]
        df = pd.DataFrame(data[header_idx + 1:], columns=headers)
        
        # 닉네임 결측치 및 통계 행 제외
        df = df[df["닉네임"].notna() & df["주간점수"].notna()].copy()
        df["순수닉네임"] = df["닉네임"].astype(str).apply(lambda x: re.sub(r"\(.*?\)", "", x).strip())
        
        # 수치형 변환
        num_cols = ["주간점수", "기준1", "기준2", "기준3", "기준4"] + [f"{i}일차" for i in range(1, 7)] + [f"{i}일차환산" for i in range(1, 7)]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
                
        # 순위 계산
        if "기준2" in df.columns:
            df["환산순위"] = df["기준2"].rank(ascending=False, method="min").astype(int)
        df["점수순위"] = df["주간점수"].rank(ascending=False, method="min").astype(int)
        
        dfs[s_name] = df

    return dfs, recent_sheets


# 실행부
FILE_PATH = "포지마스터_LOVER.xlsx"
data_dict, recent_weeks = get_recent_two_weeks_data(FILE_PATH)

if not data_dict:
    st.error("분석 가능한 주차 시트가 2개 이상 존재하지 않습니다.")
    st.stop()

prev_week, latest_week = recent_weeks[0], recent_weeks[1]
df_prev = data_dict[prev_week]
df_latest = data_dict[latest_week]

st.title(f"⚔️ LOVER 클랜전 최근 2주 비교 분석 ({prev_week} vs {latest_week})")

# 전체 유저 목록 (2주 중 한 번이라도 참여한 유저)
all_users = sorted(list(set(df_latest["순수닉네임"]).union(set(df_prev["순수닉네임"]))))
selected_user = st.selectbox("조회할 닉네임을 선택하세요:", options=all_users)

if selected_user:
    u_latest = df_latest[df_latest["순수닉네임"] == selected_user]
    u_prev = df_prev[df_prev["순수닉네임"] == selected_user]
    
    # 점수 추출
    score_latest = u_latest["주간점수"].values[0] if not u_latest.empty else 0
    score_prev = u_prev["주간점수"].values[0] if not u_prev.empty else 0
    score_delta = score_latest - score_prev
    
    conv_latest = u_latest["기준2"].values[0] if not u_latest.empty else 0.0
    conv_prev = u_prev["기준2"].values[0] if not u_prev.empty else 0.0
    conv_delta = conv_latest - conv_prev
    
    rank_latest = u_latest["환산순위"].values[0] if not u_latest.empty else None
    rank_prev = u_prev["환산순위"].values[0] if not u_prev.empty else None

    # 지표 카드 (Delta 표시)
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
        rank_diff = rank_prev - rank_latest  # 순위는 낮아져야 상승이므로 반전
        c3.metric(label=f"클랜 내 순위 ({latest_week})", value=f"{rank_latest} 위", delta=f"{rank_diff:+d} 계단")
    elif rank_latest:
        c3.metric(label=f"클랜 내 순위 ({latest_week})", value=f"{rank_latest} 위", delta="신규 참전")
    else:
        c3.metric(label=f"클랜 내 순위 ({latest_week})", value="미참여", delta=None)

    # 2주간 일차별 환산점수 비교 테이블
    st.subheader("📅 최근 2주차 일차별 환산점수 비교")
    days = [f"{i}일차환산" for i in range(1, 7)]
    
    row_prev = [u_prev[d].values[0] if not u_prev.empty and d in u_prev else 0 for d in days]
    row_latest = [u_latest[d].values[0] if not u_latest.empty and d in u_latest else 0 for d in days]
    
    comp_df = pd.DataFrame({
        "일차": [f"{i}일차" for i in range(1, 7)],
        f"직전주 ({prev_week})": row_prev,
        f"최근주 ({latest_week})": row_latest
    })
    comp_df["증감"] = comp_df[f"최근주 ({latest_week})"] - comp_df[f"직전주 ({prev_week})"]
    
    st.dataframe(comp_df.style.format({
        f"직전주 ({prev_week})": "{:.2f}",
        f"최근주 ({latest_week})": "{:.2f}",
        "증감": "{:+.2f}"
    }), use_container_width=True)