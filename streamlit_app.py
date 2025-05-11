import streamlit as st
import requests
import urllib.parse

# ✅ secrets.toml에서 API 키 불러오기
NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]

# ✅ 언론사 도메인 추출 함수
def extract_press_name(url):
    try:
        domain = urllib.parse.urlparse(url).netloc
        if "naver.com" in domain:
            return "네이버"
        elif "daum.net" in domain:
            return "다음"
        else:
            return domain.replace("www.", "")
    except:
        return "출처 미상"

# ✅ 뉴스 검색 함수 (Open API)
def search_news(query):
    enc_query = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/news.json?query={enc_query}&display=20&sort=date"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json()
        return data["items"]
    else:
        return []

# ✅ 상태 초기화
if "final_articles" not in st.session_state:
    st.session_state.final_articles = []
if "selected_keys" not in st.session_state:
    st.session_state.selected_keys = []

# ----- Streamlit App 시작 -----
st.title("📰 네이버 뉴스 검색기 (Open API 기반)")
st.markdown("Naver Open API를 이용해 군 관련 뉴스 검색")

default_keywords = ["육군", "국방", "외교", "안보", "북한",
                    "신병교육대", "훈련", "간부", "장교",
                    "부사관", "병사", "용사", "군무원"]

input_keywords = st.text_input("🔍 검색 키워드 (쉼표로 구분)", ", ".join(default_keywords))
keyword_list = [k.strip() for k in input_keywords.split(",") if k.strip()]

if st.button("🔍 뉴스 검색"):
    with st.spinner("뉴스 검색 중..."):
        all_articles = []
        for keyword in keyword_list:
            items = search_news(keyword)
            for a in items:
                title = a["title"].replace("<b>", "").replace("</b>", "")
                url = a["link"]
                press = extract_press_name(a.get("originallink") or a.get("link"))
                article = {
                    "title": title,
                    "url": url,
                    "press": press,
                    "key": url  # 중복 제거 기준
                }
                all_articles.append(article)

        # ✅ 중복 제거: URL 기준
        unique_articles = {a["url"]: a for a in all_articles}
        st.session_state.final_articles = list(unique_articles.values())
        st.session_state.selected_keys = [a["key"] for a in st.session_state.final_articles]

# ✅ 기사 미리보기 (선택 UI)
if st.session_state.final_articles:
    st.subheader("🧾 기사 미리보기 (중복 제거됨)")
    for article in st.session_state.final_articles:
        key = article["key"]
        cols = st.columns([0.85, 0.15])
        with cols[0]:
            st.markdown(f"**{article['title']}** ({article['press']})")
        with cols[1]:
            checked = st.checkbox("✅", value=key in st.session_state.selected_keys, key=key)
            if checked and key not in st.session_state.selected_keys:
                st.session_state.selected_keys.append(key)
            elif not checked and key in st.session_state.selected_keys:
                st.session_state.selected_keys.remove(key)

# ✅ 결과 출력
if st.button("📄 선택된 결과 출력"):
    st.subheader("📌 선택된 뉴스 결과")
    for article in st.session_state.final_articles:
        if article["key"] in st.session_state.selected_keys:
            st.markdown(f" ■ {article['title']} ({article['press']})")
            st.markdown(f"{article['url']}\n")
