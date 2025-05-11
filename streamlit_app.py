import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

NAVER_SEARCH_URL = "https://search.naver.com/search.naver"
VIDEO_INDICATOR = "video_thumb"  # HTML class that indicates it's a video

def get_articles(keywords):
    headers = {"User-Agent": "Mozilla/5.0"}
    now = datetime.now()
    recent_articles = []

    for keyword in keywords:
        params = {
            "where": "news",
            "query": keyword,
            "sm": "tab_opt",
            "sort": 1,  # 최신순
        }

        response = requests.get(NAVER_SEARCH_URL, params=params, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        news_items = soup.select("ul.list_news > li")

        for item in news_items:
            try:
                if VIDEO_INDICATOR not in str(item):
                    continue

                title_tag = item.select_one("a.news_tit")
                title = title_tag["title"]
                url = title_tag["href"]
                press_name = item.select_one("a.info.press").text.strip()

                time_tag = item.select_one("span.info")
                time_text = time_tag.text if time_tag else ""
                if "전" not in time_text:
                    continue  # skip non-relative times like 날짜

                # Check if it's within 4 hours
                match = re.search(r"(\d+)(분|시간) 전", time_text)
                if not match:
                    continue

                value, unit = int(match.group(1)), match.group(2)
                if (unit == "시간" and value <= 4) or (unit == "분"):
                    recent_articles.append({
                        "title": title,
                        "url": url,
                        "press": press_name,
                        "key": f"{keyword}_{title}"  # unique key for Streamlit
                    })
            except Exception:
                continue
    return recent_articles

# ----- Streamlit App -----
st.title("📰 Naver 군 관련 동영상 뉴스 검색기")
st.markdown("최근 4시간 이내 영상 뉴스를 검색합니다.")

default_keywords = ["육군", "국방", "외교", "안보", "북한",
                    "신병교육대", "훈련", "간부", "장교",
                    "부사관", "병사", "용사", "군무원"]

custom_keywords = st.text_input("키워드 입력 (쉼표로 구분)", ", ".join(default_keywords))
keyword_list = [k.strip() for k in custom_keywords.split(",") if k.strip()]

if st.button("🔍 뉴스 검색"):
    with st.spinner("뉴스를 검색 중입니다..."):
        articles = get_articles(keyword_list)

    if not articles:
        st.warning("해당 조건의 뉴스가 없습니다.")
    else:
        st.subheader("🧾 검색된 기사 미리보기 (선택하세요)")
        selected_keys = []

        for article in articles:
            key = article["key"]
            with st.container():
                cols = st.columns([0.85, 0.15])
                with cols[0]:
                    st.markdown(f"**{article['title']}** ({article['press']})")
                with cols[1]:
                    selected = st.checkbox("선택", value=True, key=key)
                    if selected:
                        selected_keys.append(key)

        if st.button("✅ 결과 생성"):
            st.subheader("📄 선택된 뉴스 결과")
            for article in articles:
                if article["key"] in selected_keys:
                    st.markdown(f"■ {article['title']} ({article['press']})")
                    st.markdown(f"{article['url']}\n")

