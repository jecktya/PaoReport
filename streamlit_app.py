import streamlit as st
import requests
import urllib.parse

# 👉 사용자 입력 키
NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]

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

# ----- Streamlit App -----
st.title("📰 네이버 뉴스 검색 (OpenAPI 기반)")
st.markdown("Naver Search Open API를 사용해 실시간 뉴스 검색")

default_keywords = ["육군", "국방", "외교", "안보", "북한",
                    "신병교육대", "훈련", "간부", "장교",
                    "부사관", "병사", "용사", "군무원"]

input_keywords = st.text_input("검색 키워드 (쉼표로 구분)", ", ".join(default_keywords))
keyword_list = [k.strip() for k in input_keywords.split(",") if k.strip()]

if st.button("🔍 뉴스 검색"):
    with st.spinner("뉴스 검색 중..."):
        all_articles = []
        for keyword in keyword_list:
            articles = search_news(keyword)
            for a in articles:
                article = {
                    "title": a["title"].replace("<b>", "").replace("</b>", ""),
                    "url": a["link"],
                    "press": a.get("originallink", "출처 없음"),
                    "key": a["link"]
                }
                all_articles.append(article)

        # 중복 제거
        unique_articles = {a["url"]: a for a in all_articles}
        final_articles = list(unique_articles.values())

    if not final_articles:
        st.warning("조건에 맞는 뉴스가 없습니다.")
    else:
        st.subheader("🧾 기사 미리보기")
        selected_keys = []

        for article in final_articles:
            key = article["key"]
            cols = st.columns([0.85, 0.15])
            with cols[0]:
                st.markdown(f"**{article['title']}** ({article['press']})")
            with cols[1]:
                checked = st.checkbox("✅", value=True, key=key)
                if checked:
                    selected_keys.append(key)

        if st.button("📄 선택된 결과 출력"):
            st.subheader("📌 선택된 뉴스")
            for article in final_articles:
                if article["key"] in selected_keys:
                    st.markdown(f"■ {article['title']} ({article['press']})")
                    st.markdown(f"{article['url']}\n")
