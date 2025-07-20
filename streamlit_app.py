# -*- coding: utf-8 -*-

import streamlit as st
import requests
import urllib.parse
import html
from datetime import datetime, timedelta, timezone
import email.utils as eut
import time
import re # 정규표현식 모듈 추가

# scikit-learn 임포트 (자동 그룹화에 필요)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity # 이 임포트는 더 이상 직접 사용되지 않지만, 다른 곳에서 사용될 가능성을 위해 유지

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

# --- 자동 그룹화 기능 추가 ---
def preprocess_text(text):
    """텍스트 전처리: HTML 태그 제거, 특수문자 제거, 소문자 변환"""
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text) # HTML 태그 제거
    text = re.sub(r'[^\w\s]', '', text) # 특수문자 제거 (알파벳, 숫자, 언더스코어, 공백 제외)
    return text.lower()

def get_common_keywords_in_group(articles_in_group):
    """그룹 내 기사들의 공통 키워드를 추출"""
    if not articles_in_group:
        return []

    # 모든 기사들의 매칭된 키워드 집합을 가져와서 교집합을 찾음
    # 각 기사의 'matched' 필드는 이미 set으로 변환되어 있다고 가정
    if not articles_in_group[0].get('matched'): # 첫 기사에 매칭 키워드가 없으면 빈 세트로 시작
        common_keywords_set = set()
    else:
        common_keywords_set = set(articles_in_group[0]['matched'])
    
    for i in range(1, len(articles_in_group)):
        if articles_in_group[i].get('matched'):
            common_keywords_set.intersection_update(set(articles_in_group[i]['matched']))
        else: # 중간에 매칭 키워드 없는 기사가 있으면 공통 키워드 없음
            common_keywords_set = set()
            break
            
    return sorted(list(common_keywords_set))

def auto_group_articles(articles, max_group_size=3, similarity_threshold=0.7): # <--- similarity_threshold를 0.7로 변경
    """
    기사들을 자동으로 그룹화하고, 각 그룹의 기사 수를 제한합니다.
    """
    if len(articles) < 2: # 그룹화할 기사가 2개 미만이면 그룹 생성 안 함
        return []

    # 텍스트 데이터 준비 (제목 + 내용)
    texts = []
    for art in articles:
        # 'desc' 필드가 없을 경우를 대비하여 기본값 설정
        combined_text = preprocess_text(art['title'] + " " + art.get('desc', ''))
        texts.append(combined_text)

    if not texts or all(not t.strip() for t in texts): # 모든 텍스트가 비어있거나 공백만 있는 경우
        return []

    # TF-IDF 벡터화
    # max_features를 사용하여 너무 많은 특성으로 인한 메모리 문제를 방지
    vectorizer = TfidfVectorizer(max_features=1000, stop_words=None) # 한국어 불용어는 직접 처리하거나, gensim 등 사용
    try:
        tfidf_matrix = vectorizer.fit_transform(texts)
    except ValueError: # 모든 문서가 비어있거나 단어가 없는 경우
        return []

    # AgglomerativeClustering (응집형 계층적 클러스터링)
    # distance_threshold: 클러스터 병합을 중단할 거리 임계값 (1 - 유사도)
    # metric='cosine': 코사인 유사도를 거리 척도로 사용 (모델이 내부적으로 계산)
    # linkage='average': 평균 연결법 (클러스터 간 평균 거리를 사용)
    
    # 유사도 임계값을 거리 임계값으로 변환 (1 - 유사도)
    model = AgglomerativeClustering(n_clusters=None, metric='cosine', linkage='average', distance_threshold=1 - similarity_threshold)
    
    # Sparse data error 해결: .toarray()를 사용하여 dense array로 변환
    # 명시적인 변수 할당으로 더욱 확실하게 dense array 전달
    dense_tfidf_matrix = tfidf_matrix.toarray()
    labels = model.fit_predict(dense_tfidf_matrix) # <--- dense_tfidf_matrix 전달

    # 클러스터 결과 정리
    clusters = {}
    for i, label in enumerate(labels):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(articles[i])

    grouped_results = []
    for group_id, cluster_articles in clusters.items():
        # 그룹 내 기사 수가 1개인 경우는 제외 (그룹으로 간주하지 않음)
        if len(cluster_articles) < 2:
            continue
        
        # 기사 수가 max_group_size를 초과하면, 키워드 출현 횟수가 많은 순으로 정렬하여 상위 N개만 선택
        # kw_count 필드가 없는 경우를 대비하여 0으로 기본값 설정
        if len(cluster_articles) > max_group_size:
            # 매칭된 키워드 개수가 많은 순으로 정렬하여 선택
            cluster_articles.sort(key=lambda x: len(x.get('matched', [])), reverse=True)
            cluster_articles = cluster_articles[:max_group_size]
        
        # 그룹 내 공통 키워드 추출
        common_kws = get_common_keywords_in_group(cluster_articles)
        
        grouped_results.append({
            'group_id': group_id,
            'articles': cluster_articles,
            'common_keywords': common_kws
        })
    
    # 그룹 내 기사 수(descending), 그룹 ID(ascending)로 정렬
    grouped_results.sort(key=lambda x: (-len(x['articles']), x['group_id']))
    
    return grouped_results

# 세션 상태 초기화
if "final_articles" not in st.session_state:
    st.session_state.final_articles = [] # 초기 검색 결과 (필터링 전)
if "selected_keys" not in st.session_state:
    st.session_state.selected_keys = [] # 일반 선택 체크박스 상태
if "manual_grouped_keys" not in st.session_state: # 수동 그룹화 체크박스 상태를 위한 새로운 세션 상태
    st.session_state.manual_grouped_keys = []
if "copied_text" not in st.session_state:
    st.session_state.copied_text = ""
# 자동 그룹화 관련 세션 상태
if "auto_groups" not in st.session_state:
    st.session_state.auto_groups = [] # 자동 생성된 그룹 목록
if "selected_display_mode" not in st.session_state: # 'selected_group_id' -> 'selected_display_mode'로 변경
    st.session_state.selected_display_mode = "all_individual" # 기본값: 모든 개별 기사 표시

# current_display_articles를 전역적으로 초기화하여 NameError 방지
current_display_articles = [] # 이 변수는 "전체 선택/해제" 버튼의 범위를 결정합니다.

# UI: 제목 및 옵션
st.title("📰 뉴스검색기")
search_mode = st.radio("🗂️ 검색 유형 선택", ["전체", "주요언론사만"], index=1)
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

                if not pub or (now - pub > timedelta(hours=4)):
                    continue

                if search_mode == "주요언론사만" and press not in press_name_map.values():
                    continue
                
                # 키워드 매칭 및 카운트 (auto_group_articles 함수에서 사용될 kw_count와 matched를 위해)
                kwcnt = {}
                for k in keyword_list: # 사용자가 입력한 모든 키워드를 대상으로 매칭
                    pat = re.compile(re.escape(k), re.IGNORECASE)
                    c = pat.findall(title + " " + desc)
                    if c: kwcnt[k] = len(c)

                if url not in url_map:
                    url_map[url] = {
                        "title": title,
                        "url": url,
                        "press": press,
                        "pubdate": pub, # datetime 객체 유지
                        "matched": set(kwcnt.keys()), # 매칭된 키워드만 저장
                        "desc": desc, # 자동 그룹화를 위해 description 추가
                        "kw_count": sum(kwcnt.values()) # 키워드 총 출현 횟수
                    }
                else:
                    url_map[url]["matched"].update(kwcnt.keys())
                    url_map[url]["kw_count"] += sum(kwcnt.values())
            
            time.sleep(0.1)

        articles = []
        for v in url_map.values():
            if search_mode == "주요언론사만" and not v["matched"]:
                continue
            elif search_mode == "전체" and not v["matched"]:
                continue
            
            v["matched"] = sorted(list(v["matched"])) # set을 list로 변환하여 저장
            articles.append(v)
        
        sorted_list = sorted(articles, key=lambda x: x['pubdate'], reverse=True)
        st.session_state.final_articles = sorted_list
        st.session_state.selected_keys = [a['url'] for a in sorted_list] # 초기에는 모든 기사 선택
        st.session_state.manual_grouped_keys = [] # 수동 그룹화 상태 초기화
        
        # 자동 그룹화 실행 및 결과 저장
        st.session_state.auto_groups = auto_group_articles(sorted_list)
        st.session_state.selected_display_mode = "all_individual" # 그룹 선택 초기화

# --- 결과 표시 및 복사 섹션 ---
if st.session_state.final_articles:
    st.subheader("🧾 기사 미리보기 및 복사")
    
    # 결과 출력 방식 selectbox 옵션 구성
    display_mode_options = {
        "all_individual": "모든 기사 (개별 보기)",
        "no_manual_group": "그룹 없는 기사 보기", 
        "all_auto_groups": "그룹화된 기사만 보기" # 명칭 변경
    }
    
    # selectbox의 options 리스트와 default index 설정
    options_keys = list(display_mode_options.keys())
    options_values = list(display_mode_options.values())
    
    # 기본값을 "모든 기사 (개별 보기)" (all_individual)로 설정
    default_index = options_keys.index("all_individual") 

    st.session_state.selected_display_mode = st.selectbox(
        "✨ 결과 출력 방식", # 용어 변경
        options=options_keys,
        format_func=lambda x: display_mode_options[x],
        index=default_index, # 기본값 설정
        key="display_mode_selectbox"
    )

    # current_display_articles 업데이트 (전체 선택/해제 버튼의 범위)
    if st.session_state.selected_display_mode == "all_individual":
        current_display_articles = st.session_state.final_articles
    elif st.session_state.selected_display_mode == "no_manual_group":
        current_display_articles = [
            art for art in st.session_state.final_articles 
            if art['url'] not in st.session_state.manual_grouped_keys
        ]
    elif st.session_state.selected_display_mode == "all_auto_groups":
        all_auto_group_articles_flat = []
        for group in st.session_state.auto_groups:
            all_auto_group_articles_flat.extend(group['articles'])
        current_display_articles = all_auto_group_articles_flat
    # 특정 자동 그룹 선택 옵션은 이제 없으므로 제거

    # 전체 선택/해제 버튼 (current_display_articles를 기반으로 작동)
    col_select_all, _ = st.columns([0.3, 0.7])
    with col_select_all:
        if st.button("✅ 전체 선택"):
            st.session_state.selected_keys = [art['url'] for art in current_display_articles]
        if st.button("❌ 전체 해제"):
            st.session_state.selected_keys = []

    # 복사할 기사들을 담을 리스트 초기화
    final_copy_list_for_textarea = [] 

    # --- "복사할 뉴스 목록" 내용 구성 로직 ---
    if st.session_state.selected_display_mode == "all_individual":
        # '모든 기사 (개별 보기)' 선택 시: '선택'된 모든 기사를 '■' 형식으로 표시
        for art in st.session_state.final_articles: # 모든 기사 목록을 기준으로
            key = art['url']
            if key in st.session_state.selected_keys:
                final_copy_list_for_textarea.append(f"■ {art['title']} ({art['press']})\n{convert_to_mobile_link(art['url'])}")
    
    elif st.session_state.selected_display_mode == "no_manual_group":
        # '그룹 없는 기사 보기' 선택 시: 수동 그룹화되지 않은 기사 중 '선택'된 기사만 표시
        final_copy_list_for_textarea.append("■ 그룹 없는 기사 관련")
        filtered_for_copy = []
        for art in st.session_state.final_articles: # 모든 기사 목록을 기준으로
            key = art['url']
            if key in st.session_state.selected_keys and key not in st.session_state.manual_grouped_keys:
                filtered_for_copy.append(f"■ {art['title']} ({art['press']})\n{convert_to_mobile_link(art['url'])}")
        
        if filtered_for_copy:
            final_copy_list_for_textarea.extend(filtered_for_copy)
        else: # 제목만 있고 기사가 없으면
             final_copy_list_for_textarea = ["선택된 기사가 없습니다."]

    elif st.session_state.selected_display_mode == "all_auto_groups":
        # '그룹화된 기사만 보기' 선택 시: 모든 자동 그룹을 표시하고, 각 그룹 내 '선택'된 기사들을 포함
        for group in st.session_state.auto_groups:
            selected_articles_in_this_auto_group = []
            for art in group['articles']:
                key = art['url']
                if key in st.session_state.selected_keys:
                    selected_articles_in_this_auto_group.append(f"- {art['title']} ({art['press']})\n{convert_to_mobile_link(art['url'])}")
            
            if selected_articles_in_this_auto_group:
                # 자동 그룹 제목 생성
                auto_group_title = "■ 그룹 기사 관련"
                if group['common_keywords']:
                    common_kws = group['common_keywords']
                    if len(common_kws) > 2:
                        title_kws = ", ".join(common_kws[:2]) + "..."
                    else:
                        title_kws = ", ".join(common_kws)
                    auto_group_title = f"■ {title_kws} 관련"
                
                final_copy_list_for_textarea.append(auto_group_title)
                final_copy_list_for_textarea.extend(selected_articles_in_this_auto_group)
        if not final_copy_list_for_textarea: # 모든 자동 그룹에서 선택된 기사가 없으면
            final_copy_list_for_textarea = ["선택된 기사가 없습니다."]
    
    # --- 개별 기사 표시 (UI에 보이는 부분) ---
    if st.session_state.selected_display_mode == "all_auto_groups":
        # '그룹화된 기사만 보기'일 때만 보이는 마스터 체크박스 (기존 로직 유지)
        # 이 마스터 체크박스는 모든 자동 그룹의 기사를 선택/해제하는 역할
        def update_all_auto_groups_selection_master():
            all_auto_group_urls = []
            for group in st.session_state.auto_groups:
                all_auto_group_urls.extend([art['url'] for art in group['articles']])
            
            if st.session_state.select_all_auto_groups_master_checkbox:
                st.session_state.selected_keys = list(set(st.session_state.selected_keys + all_auto_group_urls))
            else:
                st.session_state.selected_keys = [url for url in st.session_state.selected_keys if url not in all_auto_group_urls]
            st.experimental_rerun() # 변경 사항 즉시 반영

        all_auto_group_urls_set = set()
        for group in st.session_state.auto_groups:
            all_auto_group_urls_set.update([art['url'] for art in group['articles']])
        
        is_all_auto_groups_selected_master = all(url in st.session_state.selected_keys for url in all_auto_group_urls_set) and len(all_auto_group_urls_set) > 0

        st.checkbox(
            "✅ 모든 자동 그룹 기사 전체 선택/해제", # 마스터 체크박스 명칭 변경
            value=is_all_auto_groups_selected_master,
            key="select_all_auto_groups_master_checkbox",
            on_change=update_all_auto_groups_selection_master
        )
        st.markdown("---") # 구분선 추가

        for group_idx, group in enumerate(st.session_state.auto_groups):
            group_title_keywords = group['common_keywords']
            group_urls = [art['url'] for art in group['articles']]
            
            # 특정 그룹의 모든 기사가 선택되었는지 확인
            is_this_group_selected = all(url in st.session_state.selected_keys for url in group_urls) and len(group_urls) > 0

            # 그룹별 선택/해제 체크박스 콜백 함수
            def update_group_selection(current_group_urls, group_checkbox_key):
                if st.session_state[group_checkbox_key]:
                    st.session_state.selected_keys = list(set(st.session_state.selected_keys + current_group_urls))
                else:
                    st.session_state.selected_keys = [url for url in st.session_state.selected_keys if url not in current_group_urls]
                st.experimental_rerun() # 변경 사항 즉시 반영

            # 그룹 제목과 그룹 선택 체크박스를 한 줄에 표시
            col_group_title, col_group_checkbox = st.columns([0.8, 0.2])
            with col_group_title:
                if group_title_keywords:
                    if len(group_title_keywords) > 2:
                        title_kws = ", ".join(group_title_keywords[:2]) + "..."
                    else:
                        title_kws = ", ".join(group_title_keywords)
                    st.markdown(f"**### 자동 그룹 {group_idx + 1}: {title_kws} 관련 ({len(group['articles'])}건)**")
                else:
                    st.markdown(f"**### 자동 그룹 {group_idx + 1} ({len(group['articles'])}건)**")
            with col_group_checkbox:
                st.checkbox(
                    "그룹 선택",
                    value=is_this_group_selected,
                    key=f"group_select_checkbox_{group_idx}",
                    on_change=update_group_selection,
                    args=(group_urls, f"group_select_checkbox_{group_idx}")
                )
            
            for art in group['articles']: # 그룹 내 기사들을 표시
                key = art['url']
                
                def update_selection(item_key):
                    if st.session_state[f"checkbox_{item_key}"]:
                        if item_key not in st.session_state.selected_keys:
                            st.session_state.selected_keys.append(item_key)
                    else:
                        if item_key in st.session_state.selected_keys:
                            st.session_state.selected_keys.remove(item_key)
                    st.experimental_rerun() # 변경 사항 즉시 반영

                def update_manual_grouping(item_key):
                    if st.session_state[f"manual_group_checkbox_{item_key}"]:
                        if item_key not in st.session_state.manual_grouped_keys:
                            st.session_state.manual_grouped_keys.append(item_key)
                    else:
                        if item_key in st.session_state.manual_grouped_keys:
                            st.session_state.manual_grouped_keys.remove(item_key)
                    st.experimental_rerun() # 변경 사항 즉시 반영

                st.markdown(
                    f"<div style='user-select: text;'>■ {art['title']} ({art['press']})</div>",
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"<div style='color:gray;font-size:13px;'>🕒 {art['pubdate']} | 키워드: {', '.join(art['matched'])}</div>",
                    unsafe_allow_html=True
                )
                
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
                    st.checkbox(
                        "그룹 만들기", 
                        value=(key in st.session_state.manual_grouped_keys), 
                        key=f"manual_group_checkbox_{key}", 
                        on_change=update_manual_grouping, 
                        args=(key,),
                        disabled=False, 
                        help="이 기사를 수동 그룹에 포함합니다." 
                    )

                col_preview, col_copy = st.columns([0.75, 0.25])
                with col_preview:
                    st.markdown(f"[📎 기사 바로보기]({convert_to_mobile_link(art['url'])})")
                with col_copy:
                    if st.button("📋 1건 복사", key=f"copy_{key}"):
                        # 1건 복사는 그냥 선택된 기사 형식으로 (■ 제목 (언론사))
                        ctext = f"■ {art['title']} ({art['press']})\n{convert_to_mobile_link(art['url'])}"
                        st.session_state.copied_text = ctext
                        st.experimental_rerun()

                if st.session_state.get("copied_text", "").startswith(f"■ {art['title']}"):
                    st.text_area("복사된 내용", st.session_state.copied_text, height=80, key=f"copied_area_{key}")
                st.markdown("---") # 그룹 내 기사 구분선
        
        if not st.session_state.auto_groups:
            st.info("자동으로 그룹화된 기사가 없습니다.")

    else: # '모든 기사 (개별 보기)' 또는 '그룹 없는 기사 보기' 선택 시
        # '그룹 없는 기사 보기'일 경우 필터링
        articles_to_display_in_loop = []
        if st.session_state.selected_display_mode == "no_manual_group":
            articles_to_display_in_loop = [
                art for art in current_display_articles if art['url'] not in st.session_state.manual_grouped_keys
            ]
            if not articles_to_display_in_loop:
                st.info("그룹 없는 기사가 없습니다.")
        else: # all_individual
            articles_to_display_in_loop = current_display_articles


        for art in articles_to_display_in_loop: # 현재 표시될 기사 목록 사용
            key = art['url']
            
            def update_selection(item_key):
                if st.session_state[f"checkbox_{item_key}"]:
                    if item_key not in st.session_state.selected_keys:
                        st.session_state.selected_keys.append(item_key)
                else:
                    if item_key in st.session_state.selected_keys:
                        st.session_state.selected_keys.remove(item_key)
                st.experimental_rerun() # 변경 사항 즉시 반영

            def update_manual_grouping(item_key):
                if st.session_state[f"manual_group_checkbox_{item_key}"]:
                    if item_key not in st.session_state.manual_grouped_keys:
                        st.session_state.manual_grouped_keys.append(item_key)
                else:
                    if item_key in st.session_state.manual_grouped_keys:
                        st.session_state.manual_grouped_keys.remove(item_key)
                st.experimental_rerun() # 변경 사항 즉시 반영

            # 기사 제목과 언론사 표시 (UI 표시용)
            st.markdown(
                f"<div style='user-select: text;'>■ {art['title']} ({art['press']})</div>",
                unsafe_allow_html=True
            )
            # 발행일과 매칭된 키워드 표시
            st.markdown(
                f"<div style='color:gray;font-size:13px;'>� {art['pubdate']} | 키워드: {', '.join(art['matched'])}</div>",
                unsafe_allow_html=True
            )
            
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
                # '그룹 만들기' 체크박스를 항상 활성화
                st.checkbox(
                    "그룹 만들기", 
                    value=(key in st.session_state.manual_grouped_keys), 
                    key=f"manual_group_checkbox_{key}", 
                    on_change=update_manual_grouping, 
                    args=(key,),
                    disabled=False, 
                    help="이 기사를 수동 그룹에 포함합니다." 
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
            if st.session_state.get("copied_text", "").startswith(f"■ {art['title']}"):
                st.text_area("복사된 내용", st.session_state.copied_text, height=80, key=f"copied_area_{key}")

    final_txt = "\n\n".join(final_copy_list_for_textarea)

    st.text_area("📝 복사할 뉴스 목록", final_txt, height=300)
    
    # 복사 내용 다운로드 버튼
    st.download_button("📄 복사 내용 다운로드 (.txt)", final_txt, file_name="news.txt")
    st.markdown("📋 위 텍스트를 직접 복사하거나 다운로드 버튼을 눌러 저장하세요.")
�
