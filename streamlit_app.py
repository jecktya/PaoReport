# -*- coding: utf-8 -*-

import streamlit as st
import requests
import urllib.parse
import html
from datetime import datetime, timedelta, timezone
import email.utils as eut
import time # time 모듈 추가 (API 호출 간 지연을 위해)

# API 키 로드
# Streamlit Secrets를 사용하여 환경 변수에서 안전하게 API 키를 가져옵니다.
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
    """
    주어진 URL에서 도메인과 해당 언론사 이름을 추출합니다.
    매핑된 언론사 이름이 없으면 도메인 자체를 언론사 이름으로 반환합니다.
    """
    try:
        domain = urllib.parse.urlparse(url).netloc.replace("www.", "")
        for key, name in press_name_map.items():
            if domain == key or domain.endswith("." + key):
                return domain, name
        return domain, domain
    except Exception:
        return None, None


def convert_to_mobile_link(url):
    """
    네이버 뉴스 PC 버전 링크를 모바일 버전 링크로 변환합니다.
    """
    if "n.news.naver.com/article" in url:
        return url.replace("n.news.naver.com/article", "n.news.naver.com/mnews/article")
    return url


def search_news(query):
    """
    네이버 뉴스 검색 API를 호출하여 뉴스 기사를 검색합니다.
    display=100은 한 번에 가져올 기사 수를 의미합니다.
    """
    enc = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/news.json?query={enc}&display=100&sort=date" # display 100으로 변경
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("items", [])
    except requests.exceptions.RequestException as e:
        st.error(f"뉴스 검색 중 오류 발생: {e}")
        return []


def parse_pubdate(pubdate_str):
    """
    API 응답의 발행일 문자열을 datetime 객체로 파싱합니다.
    """
    try:
        dt_tuple = eut.parsedate(pubdate_str)
        if dt_tuple:
            dt = datetime(*dt_tuple[:6], tzinfo=timezone(timedelta(hours=9)))
            return dt
        return None
    except Exception:
        return None

# --- Streamlit UI 시작 ---

# 세션 상태 초기화
if "final_articles" not in st.session_state:
    st.session_state.final_articles = [] # 초기 검색 결과 (필터링 전)
if "selected_keys" not in st.session_state:
    st.session_state.selected_keys = [] # 일반 선택 체크박스 상태
if "grouped_keys" not in st.session_state: # 기사 묶음 포함 체크박스 상태를 위한 새로운 세션 상태
    st.session_state.grouped_keys = []
if "copied_text" not in st.session_state:
    st.session_state.copied_text = ""

# UI: 제목 및 옵션
st.title("📰 뉴스검색기")

# "동영상만" 옵션 삭제 및 기본값을 "주요언론사만"으로 변경
search_mode = st.radio("🗂️ 검색 유형 선택", ["전체", "주요언론사만"], index=1) # index=1로 "주요언론사만" 기본 선택
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

                # 모드별 필터 (동영상 필터는 제거됨)
                if search_mode == "주요언론사만" and press not in press_name_map.values():
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
            
            time.sleep(0.1) # 각 키워드 검색 후 0.1초 지연 (API 호출 제한 방지)

        # 결과 정리 (초기 검색 시에는 2개 이상 키워드 필터 적용 안 함)
        articles = []
        for v in url_map.values():
            # '주요언론사만' 모드일 때는 1개 이상 키워드 포함 시 통과
            if search_mode == "주요언론사만" and not v["matched"]:
                continue
            # '전체' 모드에서는 1개 이상 키워드 포함 시 통과
            elif search_mode == "전체" and not v["matched"]:
                continue
            
            v["matched"] = sorted(list(v["matched"]))
            articles.append(v)
        
        sorted_list = sorted(articles, key=lambda x: x['pubdate'], reverse=True)
        st.session_state.final_articles = sorted_list # 필터링 전 모든 기사 저장
        st.session_state.selected_keys = [a['url'] for a in sorted_list] # 초기에는 모든 기사 선택 상태로 시작
        st.session_state.grouped_keys = [] # 기사 묶음 포함 체크박스 상태 초기화

# --- 결과 표시 및 복사 섹션 ---
if st.session_state.final_articles:
    st.subheader("🧾 기사 미리보기 및 복사")
    
    col_select_all, _ = st.columns([0.3, 0.7])
    with col_select_all:
        if st.button("✅ 전체 선택"):
            st.session_state.selected_keys = [a['url'] for a in st.session_state.final_articles]
            st.session_state.grouped_keys = [] # 전체 선택 시 기사 묶음 포함도 초기화
        if st.button("❌ 전체 해제"):
            st.session_state.selected_keys = []
            st.session_state.grouped_keys = []

    # 복사할 기사들을 담을 리스트 초기화
    # 묶음 기사 (selected_keys에 있고 grouped_keys에 있으며 2개 이상 키워드)
    grouped_copy_items = []
    # 일반 선택 기사 (selected_keys에 있지만 grouped_keys에는 없는)
    other_selected_copy_items = []

    for art in st.session_state.final_articles:
        key = art['url']
        
        # Streamlit은 체크박스 상태를 key로 관리하므로, 직접 session_state를 업데이트하는 함수를 사용합니다.
        def update_selection(item_key):
            if st.session_state[f"checkbox_{item_key}"]:
                if item_key not in st.session_state.selected_keys:
                    st.session_state.selected_keys.append(item_key)
            else:
                if item_key in st.session_state.selected_keys:
                    st.session_state.selected_keys.remove(item_key)

        def update_grouping(item_key):
            if st.session_state[f"group_checkbox_{item_key}"]:
                if item_key not in st.session_state.grouped_keys:
                    st.session_state.grouped_keys.append(item_key)
            else:
                if item_key in st.session_state.grouped_keys:
                    st.session_state.grouped_keys.remove(item_key)

        # 기사 제목과 언론사 표시 (UI 표시용)
        st.markdown(
            f"<div style='user-select: text;'>■ {art['title']} ({art['press']})</div>",
            unsafe_allow_html=True
        )
        # 발행일과 매칭된 키워드 표시
        st.markdown(
            f"<div style='color:gray;font-size:13px;'>🕒 {art['pubdate'].strftime('%Y-%m-%d %H:%M')} | 키워드: {', '.join(art['matched'])}</div>",
            unsafe_allow_html=True
        )
        
        # 체크박스 컬럼 분리
        col_checkbox_select, col_checkbox_group = st.columns([0.2, 0.8])

        with col_checkbox_select:
            st.checkbox(
                "선택", 
                value=(key in st.session_state.selected_keys), 
                key=f"checkbox_{key}", 
                on_change=update_selection, 
                args=(key,)
            )
        
        with col_checkbox_group:
            # '그룹 만들기' 체크박스를 항상 활성화 (disabled=False)
            st.checkbox(
                "그룹 만들기", # 이름 변경: '기사 묶음 포함' -> '그룹 만들기'
                value=(key in st.session_state.grouped_keys), 
                key=f"group_checkbox_{key}", 
                on_change=update_grouping, 
                args=(key,),
                disabled=False, # 항상 활성화
                help="비슷한 기사들을 그룹으로 지정합니다." # 도움말 텍스트 변경
            )

        # 기사 바로보기 링크 및 1건 복사 버튼
        col_preview, col_copy = st.columns([0.75, 0.25])
        with col_preview:
            st.markdown(f"[📎 기사 바로보기]({convert_to_mobile_link(art['url'])})")
        with col_copy:
            if st.button("📋 1건 복사", key=f"copy_{key}"):
                # 1건 복사는 그냥 선택된 기사 형식으로 (■ 제목 (언론사))
                ctext = f"■ {art['title']} ({art['press']})\n{convert_to_mobile_link(art['url'])}"
                st.session_state.copied_text = ctext
                st.experimental_rerun()

        # 복사된 내용 표시 (가장 최근 복사된 1건만)
        if st.session_state.get("copied_text", "").startswith(f"■ {art['title']}"): # 시작 문자 '■'로 변경
            st.text_area("복사된 내용", st.session_state.copied_text, height=80, key=f"copied_area_{key}")

        # 복사할 텍스트 리스트에 추가 (기사 묶음 vs 일반 선택 분리)
        if key in st.session_state.selected_keys: # '선택'된 기사만 고려
            # 묶음 기사 형식: - 제목 (언론사)
            item_text_grouped = f"- {art['title']} ({art['press']})\n{convert_to_mobile_link(art['url'])}"
            # 그냥 선택된 기사 형식: ■ 제목 (언론사)
            item_text_normal = f"■ {art['title']} ({art['press']})\n{convert_to_mobile_link(art['url'])}"
            
            # '그룹 만들기'가 체크되었으면 묶음 목록에 추가 (키워드 개수 조건 제거)
            if key in st.session_state.grouped_keys:
                grouped_copy_items.append(item_text_grouped)
            else: # '선택'되었지만 그룹 조건은 만족하지 않는 경우 일반 목록에 추가
                other_selected_copy_items.append(item_text_normal)

    # 최종 result_texts 구성 (순서: 묶음 기사 -> 일반 선택 기사)
    result_texts = []
    if grouped_copy_items:
        result_texts.append("■ 선택된관련내용 관련") # 공통 제목
        result_texts.extend(grouped_copy_items)
    
    # 묶음 기사 뒤에 일반 선택 기사 추가
    if other_selected_copy_items:
        # 묶음 기사가 없었고 일반 선택 기사만 있다면, 제목을 붙이지 않습니다.
        # 사용자 요청에 따라 "선택된관련내용 관련" 제목은 묶음 기사에만 붙습니다.
        result_texts.extend(other_selected_copy_items)

    final_txt = "\n\n".join(result_texts)
    st.text_area("📝 복사할 뉴스 목록", final_txt, height=300)
    
    # 복사 내용 다운로드 버튼
    st.download_button("📄 복사 내용 다운로드 (.txt)", final_txt, file_name="news.txt")
    st.markdown("📋 위 텍스트를 직접 복사하거나 다운로드 버튼을 눌러 저장하세요.")
