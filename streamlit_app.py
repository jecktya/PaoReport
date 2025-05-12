# -*- coding: utf-8 -*-

import streamlit as st
import requests
import urllib.parse
import html
from datetime import datetime, timedelta
import email.utils as eut
from bs4 import BeautifulSoup
import feedparser

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
    except Exception:
        return None, None

def convert_to_mobile_link(url):
    if "n.news.naver.com/article" in url:
        return url.replace("n.news.naver.com/article", "n.news.naver.com/mnews/article")
    return url

def search_daum_news(query):
    encoded_query = urllib.parse.quote(query)
    url = f"https://search.daum.net/search?w=news&sort=recency&q={encoded_query}"
    res = requests.get(url)
    soup = BeautifulSoup(res.text, "html.parser")
    items = []
    for tag in soup.select(".wrap_cont .tit_main.fn a"):
        title = tag.get_text(strip=True)
        link = tag.get("href")
        domain, press = extract_press_name(link)
        items.append({"title": title, "link": link, "press": press, "pubDate": datetime.utcnow().isoformat()})
    return items

def search_rss_feed(query):
    feed_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"
    feed = feedparser.parse(feed_url)
    items = []
    for entry in feed.entries:
        title = entry.title
        link = entry.link
        pubdate = datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') else datetime.utcnow()
        domain, press = extract_press_name(link)
        items.append({"title": title, "link": link, "press": press, "pubDate": pubdate})
    return items

def search_news(query):
    if search_source == "다음":
        return search_daum_news(query)
    elif search_source == "RSS":
        return search_rss_feed(query)
    # 기본 네이버
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
