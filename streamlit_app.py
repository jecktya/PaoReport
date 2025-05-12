# -*- coding: utf-8 -*-

import streamlit as st
import requests
import urllib.parse
import html
from datetime import datetime, timedelta
import email.utils as eut

NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]

press_name_map = {
    "chosun.com": "조선일보", "yna.co.kr": "연합뉴스", "hani.co.kr": "한겨레",
    "joongang.co.kr": "중앙일보", "mbn.co.kr": "MBN", "kbs.co.kr": "KBS",
    "sbs.co.kr": "SBS", "ytn.co.kr": "YTN", "donga.com": "동아일보",
    "segye.com": "세계일보", "munhwa.com": "문화일보", "newsis.com": "뉴시스",
    "naver.com": "네이버", "daum.net": "다음", "kukinews.com": "국민일보",
    "kookbang.dema.mil.kr": "국방일보", "edaily.co.kr": "이데일리",
    "news1.kr": "뉴스1", "mbnmoney.mbn.co.kr": "MBN", "news.kmib.co.kr": "국민일보",
    "jtbc.co.kr": "JTBC"
}

def extract_press_name(url):
    try:
        domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
        return domain, press_name_map.get(domain, domain)
    except Exception as e:
        return None, None

def convert_to_mobile_link(url):
    if "n.news.naver.com/article" in url:
        return url.replace("n.news.naver.com/article", "n.news.naver.com/mnews/article")
    return url

def search_news(query):
    enc_query = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/news.json?query={enc_query}&display=30&sort=date"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json().get("items", [])
    return []

def parse_pubdate(pubdate_str):
    try:
        return datetime(*eut.parsedate(pubdate_str)[:6])
    except Exception:
        return None

if "final_articles" not in st.session_state:
    st.session_state.final_articles = []
if "selected_keys" not in st.session_state:
    st.session_state.selected_keys = []
if "copied_text" not in st.session_state:
    st.session_state.copied_text = ""

st.title("📰 네이버 뉴스 검색기")
search_mode = st.radio("🗂️ 검색 유형 선택", ["전체", "동영상만 (최근 4시간)", "주요언론사만"])

def_keywords = ["육군", "국방", "외교", "안보", "북한",
                "신병교육대", "훈련", "간부", "장교",
                "부사관", "병사", "용사", "군무원"]
input_keywords = st.text_input("🔍 키워드 입력 (쉼표로 구분)", ", ".join(def_keywords))
keyword_list = [k.strip() for k in input_keywords.split(",") if k.strip()]

if st.button("🔍 뉴스 검색"):
    with st.spinner("뉴스 검색 중..."):
        now = datetime.utcnow()
        all_articles = []
        for keyword in keyword_list:
            items = search_news(keyword)
            for a in items:
                title = html.unescape(a["title"]).replace("<b>", "").replace("</b>", "")
                desc = html.unescape(a.get("description", "")).replace("<b>", "").replace("</b>", "")
                url = a["link"]
                pubdate = parse_pubdate(a.get("pubDate", ""))
                domain, press = extract_press_name(a.get("originallink") or url)

                if search_mode == "주요언론사만" and press not in press_name_map.values():
                    continue
                if search_mode == "동영상만 (최근 4시간)":
                    if not pubdate or (now - pubdate > timedelta(hours=4)):
                        continue
                    if press not in press_name_map.values():
                        continue
                    if not ("동영상" in desc or "영상" in desc or any(kw in title for kw in ["영상", "동영상", "영상보기"])):
                        continue

                article = {
                    "title": title,
                    "url": url,
                    "press": press,
                    "pubdate": pubdate,
                    "key": url
                }
                all_articles.append(article)

        unique_articles = {a["url"]: a for a in all_articles}
        sorted_articles = sorted(unique_articles.values(), key=lambda x: x["pubdate"] or datetime.min, reverse=True)
        st.session_state.final_articles = sorted_articles
        st.session_state.selected_keys = [a["key"] for a in sorted_articles]

if st.session_state.final_articles:
    st.subheader("🧾 기사 미리보기 및 복사")

    col1, col2 = st.columns([0.3, 0.7])
    with col1:
        if st.button("✅ 전체 선택"):
            st.session_state.selected_keys = [a["key"] for a in st.session_state.final_articles]
        if st.button("❌ 전체 해제"):
            st.session_state.selected_keys = []

    result_lines = []
    for article in st.session_state.final_articles:
        key = article["key"]
        checked = key in st.session_state.selected_keys
        pub_str = article["pubdate"].strftime("%Y-%m-%d %H:%M") if article["pubdate"] else "시간 없음"
            st.markdown(f"<div style='user-select: text;'>■ {article['title']} ({article['press']})</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:gray;font-size:13px;'>🕒 {pub_str}</div>", unsafe_allow_html=True)
    new_check = st.checkbox("선택", value=checked, key=key)

        if new_check and key not in st.session_state.selected_keys:
            st.session_state.selected_keys.append(key)
        elif not new_check and key in st.session_state.selected_keys:
            st.session_state.selected_keys.remove(key)

        col_preview, col_copy = st.columns([0.75, 0.25])
        with col_preview:
            st.markdown(f"[📎 기사 바로보기]({convert_to_mobile_link(article['url'])})")
        with col_copy:
            if st.button(f"📋 1건 복사", key=key + "_copy"):
                st.session_state["copied_text"] = f"[{article['press']}] {article['title']}\n{convert_to_mobile_link(article['url'])}"

        if st.session_state.get("copied_text") and st.session_state["copied_text"].startswith(f"[{article['press']}] {article['title']}"):
            st.text_area("복사된 내용", st.session_state["copied_text"], height=80)

        if key in st.session_state.selected_keys:
            result_lines.append(f"■ {article['title']} ({article['press']})\n{convert_to_mobile_link(article['url'])}")

    final_text = "\n\n".join(result_lines)
    st.text_area("📝 복사할 뉴스 목록", final_text, height=300)
    st.download_button("📄 복사 내용 다운로드 (.txt)", final_text, file_name="news.txt")
    st.markdown("📋 위 텍스트를 직접 복사하거나 다운로드 버튼을 눌러 저장하세요.")
