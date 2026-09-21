import streamlit as st
import requests
import pandas as pd
import datetime
import pytz

# 페이지 기본 설정
st.set_page_config(page_title="박스오피스 대시보드", page_icon="🎬", layout="wide")

# ---------------------------------------------------------
# 1. 한국 시간 기준 '어제' 날짜 계산하기
# ---------------------------------------------------------
def get_yesterday_kst():
    """배포 서버의 시간대와 무관하게 항상 한국 시간 기준의 '어제'를 구합니다."""
    kst = pytz.timezone('Asia/Seoul')
    today_kst = datetime.datetime.now(kst).date()
    yesterday_kst = today_kst - datetime.timedelta(days=1)
    return yesterday_kst

# ---------------------------------------------------------
# 2. API 데이터 가져오기 및 캐싱(기억하기)
# ---------------------------------------------------------
# @st.cache_data를 사용하여 1시간(3600초) 동안 동일한 날짜의 결과를 기억합니다.
@st.cache_data(ttl=3600, show_spinner="데이터를 가져오는 중입니다...")
def fetch_boxoffice_data(target_dt_str, api_key):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": target_dt_str
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() 
        
        data = response.json()
        
        # 에러 응답(faultInfo) 처리
        if "faultInfo" in data:
            error_msg = data["faultInfo"].get("message", "알 수 없는 API 오류가 발생했습니다.")
            return None, f"API 오류가 발생했습니다. (사유: {error_msg})\n스트림릿 클라우드의 Secrets에 KOBIS_KEY가 정확히 입력되었는지 확인해주세요."
            
        # 영화 목록이 비어있을 때 (요청하신 에러 메시지로 변경)
        boxoffice_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
        if not boxoffice_list:
            return None, "그날은 아직 집계 전입니다"
            
        return boxoffice_list, None
        
    except Exception as e:
        return None, f"데이터 요청 중 네트워크 오류가 발생했습니다: {str(e)}"

# ---------------------------------------------------------
# 3. 화면 그리기 및 날짜 선택기(Calendar)
# ---------------------------------------------------------
def main():
    st.title("🍿 일일 박스오피스 순위")
    
    # 달력에서 날짜를 선택할 수 있도록 구현 (최대 선택 가능 날짜는 '어제')
    yesterday = get_yesterday_kst()
    selected_date = st.date_input(
        "조회할 날짜를 선택하세요 (한국 시간 기준)",
        value=yesterday,       # 기본값: 어제
        max_value=yesterday    # 오늘 날짜는 선택할 수 없도록 어제로 제한
    )
    
    st.divider()

    # API가 요구하는 'YYYYMMDD' 형식으로 날짜 문자열 변환
    target_dt_str = selected_date.strftime('%Y%m%d')

    # API 키 불러오기
    try:
        api_key = st.secrets["KOBIS_KEY"]
    except KeyError:
        st.error("보안 키가 설정되지 않았습니다. 스트림릿 클라우드 설정(Secrets)에서 `KOBIS_KEY`를 등록해주세요.")
        return

    # API 호출
    raw_data, error_message = fetch_boxoffice_data(target_dt_str, api_key)
    
    # 에러 메시지가 반환된 경우 화면에 표시하고 로직을 중단합니다.
    if error_message:
        st.warning(error_message)
        return

    # ---------------------------------------------------------
    # 4. 데이터 가공하기 (문자열 -> 숫자, 트로피 및 화살표 추가)
    # ---------------------------------------------------------
    df = pd.DataFrame(raw_data)
    
    # 문자로 온 숫자 데이터를 진짜 숫자로 변환
    numeric_columns = ['rank', 'rankInten', 'audiCnt', 'audiAcc', 'scrnCnt']
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col])
        
    # [조건] 누적관객 100만 명 돌파 시 트로피 이모지 추가
    df['movieNm_display'] = df.apply(
        lambda row: f"{row['movieNm']} 🏆" if row['audiAcc'] >= 1000000 else row['movieNm'], 
        axis=1
    )

    # [조건] 전일 대비 순위 증감(rankInten)에 따라 화살표 기호 생성
    def format_rank_change(inten):
        if inten > 0:
            return f"🔺 {inten}" # 빨간 위 화살표
        elif inten < 0:
            return f"🔽 {abs(inten)}" # 파란 아래 화살표
        else:
            return "-" # 변동 없음
            
    df['순위변동'] = df['rankInten'].apply(format_rank_change)
    
    # ---------------------------------------------------------
    # 5. 1위 영화 지표 카드 그리기
    # ---------------------------------------------------------
    st.subheader("🥇 오늘의 1위 영화")
    top1 = df.iloc[0] 
    
    col1, col2, col3 = st.columns(3)
    col1.metric(label="영화명", value=top1['movieNm_display'])
    col2.metric(label="하루 관객수", value=f"{top1['audiCnt']:,} 명", delta=top1['순위변동'])
    col3.metric(label="누적 관객수", value=f"{top1['audiAcc']:,} 명")
    
    st.divider()

    # ---------------------------------------------------------
    # 6. 관객수 상위 5편 막대그래프 그리기
    # ---------------------------------------------------------
    st.subheader("📊 관객수 상위 5편")
    # 그래프를 그릴 때는 원본 영화명(movieNm)을 사용해 깔끔하게 출력합니다.
    top5_df = df.head(5)[['movieNm', 'audiCnt']]
    top5_chart_data = top5_df.set_index('movieNm')
    st.bar_chart(top5_chart_data)
    
    st.divider()

    # ---------------------------------------------------------
    # 7. 전체 순위 표 보여주기
    # ---------------------------------------------------------
    st.subheader("📋 전체 박스오피스 목록")
    # 화면에 예쁘게 보여줄 열들만 추려서 새 데이터프레임을 만듭니다.
    display_df = df[['rank', '순위변동', 'movieNm_display', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
    display_df.columns = ['순위', '순위 변동', '영화명', '개봉일', '일일 관객수', '누적 관객수', '스크린수']
    
    # 순위 기준으로 정렬
    display_df = display_df.sort_values('순위')
    
    # st.dataframe을 통해 깔끔한 표로 출력합니다. (좌측 인덱스 숨김)
    st.dataframe(display_df, hide_index=True, use_container_width=True)

if __name__ == "__main__":
    main()
