import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

NAVER_SEARCH_URL = "https://search.naver.com/search.naver"

def get_recent_articles(keywords):
    headers = {"User-Agent": "Mozilla/5.0"}
    articles = []

    for keyword in keywords:
        params = {
            "where": "news",
            "query": keyword,
            "sort": 1,  # 최신순
        }

        response = requests.get(NAVER_SEARCH_URL, params=params, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        news_items = soup.select("ul.list_news > li")

        for item in news_items:
            try:
                title_tag = item.select_one("a.news_tit")
                if not title_tag:
                    continue

                title = title_tag["title"]
                url = title_tag["href"]
                press_tag = item.select_one("a.info.press")
                press_name = press_tag.text.strip() if press_tag else "Unknown"

                time_tag = item.select("span.info")[-1].text  # 마지막 info가 시간 정보인 경우가 많음
                match = re.search(r"(\d+)(분|시간) 전", time_tag)
                if not match:
                    continue

                value, unit = int(match.group(1)), match.group(2)
                if (unit == "시간" and value <= 4) or (unit == "분"):
                    articles.append({
                        "title": title,
                        "url": url,
                        "press": press_name,
                        "key": f"{title}_{url}"
                    })
            except:
                continue

    # 중복 제거 (URL 기준)
    unique_articles = {article['url']: article for article in articles}
    return list(unique_articles.values())

# ----- Streamlit App -----
st.title("📰 최근 4시간 이내 군 관련 뉴스")
st.markdown("영상 뉴스 구분 없이, 키워드 기반 최신 뉴스 검색기입니다.")

default_keywords = ["육군", "국방", "외교", "안보", "북한",
                    "신병교육대", "훈련", "간부", "장교",
                    "부사관", "병사", "용사", "군무원"]

input_keywords = st.text_input("검색 키워드 (쉼표로 구분)", ", ".join(default_keywords))
keyword_list = [k.strip() for k in input_keywords.split(",") if k.strip()]

if st.button("🔍 뉴스 검색"):
    with st.spinner("뉴스를 수집 중입니다..."):
        articles = get_recent_articles(keyword_list)

    if not articles:
        st.warning("조건에 맞는 뉴스가 없습니다.")
    else:
        st.subheader("🧾 기사 미리보기 (선택해서 결과 생성)")
        selected_keys = []

        for article in articles:
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
            for article in articles:
                if article["key"] in selected_keys:
                    st.markdown(f"■ {article['title']} ({article['press']})")
                    st.markdown(f"{article['url']}\n")
