# -*- coding: utf-8 -*-

import streamlit as st
import requests
import urllib.parse
import html
from datetime import datetime, timedelta, timezone
import email.utils as eut
from bs4 import BeautifulSoup
import feedparser
from langdetect import detect

# API 키 로드
NAVER_CLIENT_ID = st.secrets.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = st.secrets.get("NAVER_CLIENT_SECRET")

# 언론사 매핑
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
        # 서브도메인 처리: 매핑 키와 정확히 일치하거나 해당 키로 끝나면 매핑
        for key, name in press_name_map.items():
            if domain == key or domain.endswith("." + key):
                return domain, name
        # 매핑되지 않으면 도메인 자체 반환
        return domain, domain
    except Exception:
        return None, None
    except:
        return None, None


def convert_to_mobile_link(url):
    if "n.news.naver.com/article" in url:
        return url.replace("n.news.naver.com/article", "n.news.naver.com/mnews/article")
    return url


def search_news(query):
    enc = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/news.json?query={enc}&display=30&sort=date"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json().get("items", [])
    return []


def parse_pubdate(pubdate_str):
    try:
        dt = datetime(*eut.parsedate(pubdate_str)[:6], tzinfo=timezone(timedelta(hours=9)))
        return dt
    except:
        return None

# 세션 초기화
if "final_articles" not in st.session_state:
    st.session_state.final_articles = []
if "selected_keys" not in st.session_state:
    st.session_state.selected_keys = []
if "copied_text" not in st.session_state:
    st.session_state.copied_text = ""

# UI: 제목 및 옵션
st.title("📰 뉴스검색기")
search_mode = st.radio("🗂️ 검색 유형 선택", ["전체", "동영상만", "주요언론사만"])
st.markdown(
    f"<span style='color:gray;'>🕒 현재 시각: {datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S')} (4시간 이내 뉴스만 검색해요)</span>",
    unsafe_allow_html=True
)

def_keywords = ["육군", "국방", "외교", "안보", "북한",
                "신병교육대", "훈련", "간부", "장교",
                "부사관", "병사", "용사", "군무원"]
input_keywords = st.text_input("🔍 키워드 입력 (쉼표로 구분)", ", ".join(def_keywords))
keyword_list = [k.strip() for k in input_keywords.split(",") if k.strip()]

# 검색 버튼
if st.button("🔍 뉴스 검색"):
    with st.spinner("뉴스 검색 중..."):
        now = datetime.now(timezone(timedelta(hours=9)))
        url_map = {}

        for kw in keyword_list:
            items = search_news(kw)
            for a in items:
                title = html.unescape(a["title"]).replace("<b>", "").replace("</b>", "")
                desc = html.unescape(a.get("description", "")).replace("<b>", "").replace("</b>", "")
                url = a["link"]
                pub = parse_pubdate(a.get("pubDate", "")) or datetime.min.replace(tzinfo=timezone(timedelta(hours=9)))
                domain, press = extract_press_name(a.get("originallink") or url)

                # 4시간 필터
                if not pub or (now - pub > timedelta(hours=4)):
                    continue

                # 모드별 필터
                if search_mode == "주요언론사만" and press not in press_name_map.values():
                    continue
                if search_mode == "동영상만":
                    if press not in press_name_map.values():
                        continue
                    video_keys = ["영상", "동영상", "영상보기", "보러가기", "뉴스영상", "영상뉴스", "클릭하세요", "바로보기"]
                    video_text = any(k in desc for k in video_keys) or any(k in title for k in video_keys)
                    video_url = any(p in url for p in ["/v/", "/video/", "vid="])
                    if not (video_text or video_url):
                        continue

                # 중복 URL 관리 및 키워드 매핑
                if url not in url_map:
                    url_map[url] = {
                        "title": title,
                        "url": url,
                        "press": press,
                        "pubdate": pub,
                        "matched": set([kw])
                    }
                else:
                    url_map[url]["matched"].add(kw)

        # 결과 정리
        articles = []
        for v in url_map.values():
            v["matched"] = sorted(v["matched"])
            articles.append(v)
        sorted_list = sorted(articles, key=lambda x: x['pubdate'], reverse=True)
        st.session_state.final_articles = sorted_list
        st.session_state.selected_keys = [a['url'] for a in sorted_list]

# 결과 출력
if st.session_state.final_articles:
    st.subheader("🧾 기사 미리보기 및 복사")
    col1, _ = st.columns([0.3, 0.7])
    with col1:
        if st.button("✅ 전체 선택"):
            st.session_state.selected_keys = [a['url'] for a in st.session_state.final_articles]
        if st.button("❌ 전체 해제"):
            st.session_state.selected_keys = []

    result_texts = []
    for art in st.session_state.final_articles:
        key = art['url']
        checked = key in st.session_state.selected_keys
        pub_str = art['pubdate'].strftime('%Y-%m-%d %H:%M')
        matched = ", ".join(art['matched'])

        st.markdown(
            f"<div style='user-select: text;'>■ {art['title']} ({art['press']})</div>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<div style='color:gray;font-size:13px;'>🕒 {pub_str} | 키워드: {matched}</div>",
            unsafe_allow_html=True
        )
        new_check = st.checkbox("선택", value=checked, key=key)
        if new_check and key not in st.session_state.selected_keys:
            st.session_state.selected_keys.append(key)
        elif not new_check and key in st.session_state.selected_keys:
            st.session_state.selected_keys.remove(key)

        col_preview, col_copy = st.columns([0.75, 0.25])
        with col_preview:
            st.markdown(f"[📎 기사 바로보기]({convert_to_mobile_link(art['url'])})")
        with col_copy:
            if st.button("📋 1건 복사", key=key + "_copy"):
                ctext = f"[{art['press']}] {art['title']}\n{convert_to_mobile_link(art['url'])}"
                st.session_state.copied_text = ctext

        if st.session_state.get("copied_text", "").startswith(f"[{art['press']}] {art['title']}"):
            st.text_area("복사된 내용", st.session_state.copied_text, height=80)

        if key in st.session_state.selected_keys:
            result_texts.append(f"■ {art['title']} ({art['press']})\n{convert_to_mobile_link(art['url'])}")

    final_txt = "\n\n".join(result_texts)
    st.text_area("📝 복사할 뉴스 목록", final_txt, height=300)
    st.download_button("📄 복사 내용 다운로드 (.txt)", final_txt, file_name="news.txt")
    st.markdown("📋 위 텍스트를 직접 복사하거나 다운로드 버튼을 눌러 저장하세요.")

