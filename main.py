import requests
import streamlit as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# 기본 설정
# ---------------------------------------------------------

st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)


# ---------------------------------------------------------
# 한국 시간 기준으로 '어제' 날짜를 계산하는 함수
# 배포 서버가 다른 나라 시간이어도 한국 시간을 기준으로 합니다.
# ---------------------------------------------------------

def get_yesterday_kst():
    kst = ZoneInfo("Asia/Seoul")
    now_kst = datetime.now(kst)
    yesterday = now_kst.date() - timedelta(days=1)

    # KOBIS API가 요구하는 YYYYMMDD 형식으로 변환
    return yesterday.strftime("%Y%m%d")


# ---------------------------------------------------------
# KOBIS API에서 박스오피스 데이터를 가져오는 함수
#
# cache_data를 사용해서 같은 날짜를 다시 조회하면
# 1시간 동안 API를 다시 호출하지 않습니다.
# ---------------------------------------------------------

@st.cache_data(ttl=3600)
def fetch_box_office(target_date):
    # Streamlit Secrets에서 인증키를 가져옵니다.
    # 실제 인증키를 코드에 직접 작성하지 않습니다.
    try:
        kobis_key = st.secrets["KOBIS_KEY"]
    except Exception:
        return {
            "ok": False,
            "message": (
                "KOBIS_KEY를 찾을 수 없습니다. "
                "Streamlit Cloud의 앱 설정 → Secrets에 "
                "`KOBIS_KEY = \"발급받은 인증키\"`가 등록되어 있는지 확인하세요."
            ),
        }

    params = {
        "key": kobis_key,
        "targetDt": target_date,
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=10,
        )

        # HTTP 오류가 있으면 예외 발생
        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        return {
            "ok": False,
            "message": (
                "KOBIS API 요청에 실패했습니다.\n\n"
                f"오류 내용: {e}\n\n"
                "인터넷 연결, KOBIS API 주소, 인증키 및 API 서비스 상태를 "
                "확인해 주세요."
            ),
        }

    try:
        data = response.json()
    except ValueError:
        return {
            "ok": False,
            "message": (
                "KOBIS API의 응답을 JSON으로 읽을 수 없습니다. "
                "잠시 후 다시 시도하거나 KOBIS API 상태를 확인해 주세요."
            ),
        }

    # 인증키가 틀린 경우에도 HTTP 상태코드는 200일 수 있으므로
    # faultInfo가 있는지 반드시 별도로 확인합니다.
    if "faultInfo" in data:
        fault_info = data["faultInfo"]

        # faultInfo가 객체이거나 문자열인 경우 모두 처리
        if isinstance(fault_info, dict):
            fault_code = fault_info.get("faultCode", "")
            fault_message = fault_info.get("message", "")
            detail = f"{fault_code} {fault_message}".strip()
        else:
            detail = str(fault_info)

        return {
            "ok": False,
            "message": (
                "KOBIS API에서 오류를 반환했습니다.\n\n"
                f"{detail}\n\n"
                "특히 인증키가 정확한지, KOBIS에서 발급받은 API 키가 "
                "활성 상태인지 확인해 주세요."
            ),
        }

    # 예상한 응답 구조가 있는지 확인
    box_office_result = data.get("boxOfficeResult")

    if not isinstance(box_office_result, dict):
        return {
            "ok": False,
            "message": (
                "KOBIS 응답에 boxOfficeResult가 없습니다. "
                "조회 날짜나 API 응답 형식을 확인해 주세요."
            ),
        }

    movie_list = box_office_result.get("dailyBoxOfficeList", [])

    # 영화 목록이 비어 있는 경우
    if not movie_list:
        return {
            "ok": False,
            "message": (
                f"{target_date} 날짜의 일일 박스오피스 영화 목록이 없습니다.\n\n"
                "조회 날짜가 올바른지, 해당 날짜의 박스오피스 집계가 "
                "완료되었는지, KOBIS API가 정상적으로 응답했는지 확인해 주세요."
            ),
        }

    return {
        "ok": True,
        "data": movie_list,
    }


# ---------------------------------------------------------
# 문자열로 받은 숫자를 실제 숫자로 변환하는 함수
# 숫자가 비어 있거나 변환되지 않는 경우 0으로 처리합니다.
# ---------------------------------------------------------

def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------
# 화면 제목
# ---------------------------------------------------------

st.title("🎬 어제의 박스오피스")

target_date = get_yesterday_kst()

# YYYYMMDD를 사람이 읽기 좋은 YYYY-MM-DD로 표시
display_date = (
    f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
)

st.caption(f"KOBIS 일일 박스오피스 · 기준일: {display_date}")


# ---------------------------------------------------------
# API 호출
# ---------------------------------------------------------

result = fetch_box_office(target_date)


# ---------------------------------------------------------
# API 오류가 있으면 빈 화면 대신 확인할 사항을 안내합니다.
# ---------------------------------------------------------

if not result["ok"]:
    st.error(result["message"])

    st.info(
        """
        **확인할 사항**

        1. Streamlit Cloud의 **Secrets에 `KOBIS_KEY`가 등록되어 있는지**
        2. KOBIS에서 발급받은 **인증키가 정확한지**
        3. KOBIS API가 정상적으로 서비스되고 있는지
        4. 조회 대상인 **어제 날짜의 집계 데이터가 존재하는지**
        """
    )

    st.stop()


# ---------------------------------------------------------
# 영화 데이터 준비
# ---------------------------------------------------------

movies = result["data"]

# API에서 오는 숫자 문자열을 실제 정수로 변환합니다.
for movie in movies:
    movie["rank"] = to_int(movie.get("rank"))
    movie["audiCnt"] = to_int(movie.get("audiCnt"))
    movie["audiAcc"] = to_int(movie.get("audiAcc"))
    movie["scrnCnt"] = to_int(movie.get("scrnCnt"))
    movie["showCnt"] = to_int(movie.get("showCnt"))


# 순위 숫자를 기준으로 정렬
movies.sort(key=lambda movie: movie["rank"])


# ---------------------------------------------------------
# 1위 영화
# ---------------------------------------------------------

first_movie = movies[0]

st.subheader(f"🥇 1위 · {first_movie.get('movieNm', '영화명 없음')}")

st.write(
    f"개봉일: {first_movie.get('openDt') or '정보 없음'}"
)

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="어제 관객수",
        value=f"{first_movie['audiCnt']:,}명",
    )

with col2:
    st.metric(
        label="누적 관객수",
        value=f"{first_movie['audiAcc']:,}명",
    )

with col3:
    st.metric(
        label="스크린수",
        value=f"{first_movie['scrnCnt']:,}개",
    )


# ---------------------------------------------------------
# 관객수 상위 5편 막대그래프
# ---------------------------------------------------------

st.subheader("📊 관객수 상위 5편")

top5 = sorted(
    movies,
    key=lambda movie: movie["audiCnt"],
    reverse=True,
)[:5]

# 영화명을 인덱스로 하고 관객수를 값으로 하는 데이터프레임
# pandas는 Streamlit에 기본적으로 함께 설치되지만,
# 명시적으로 사용하지 않고 Streamlit의 차트 기능을 활용합니다.
chart_data = {
    movie["movieNm"]: movie["audiCnt"]
    for movie in top5
}

st.bar_chart(chart_data)


# ---------------------------------------------------------
# 전체 박스오피스 표
# ---------------------------------------------------------

st.subheader("📋 전체 순위")

table_data = []

for movie in movies:
    table_data.append(
        {
            "순위": movie["rank"],
            "영화명": movie.get("movieNm", ""),
            "개봉일": movie.get("openDt", ""),
            "관객수": movie["audiCnt"],
            "누적관객": movie["audiAcc"],
            "스크린수": movie["scrnCnt"],
        }
    )

st.dataframe(
    table_data,
    use_container_width=True,
    hide_index=True,
    column_config={
        "순위": st.column_config.NumberColumn(
            "순위",
            format="%d",
        ),
        "영화명": st.column_config.TextColumn(
            "영화명",
        ),
        "개봉일": st.column_config.TextColumn(
            "개봉일",
        ),
        "관객수": st.column_config.NumberColumn(
            "관객수",
            format="%d",
        ),
        "누적관객": st.column_config.NumberColumn(
            "누적관객",
            format="%d",
        ),
        "스크린수": st.column_config.NumberColumn(
            "스크린수",
            format="%d",
        ),
    },
)
