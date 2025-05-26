import pandas as pd
import os
import time
from googlesearch import search
from newspaper import Article, Config as NewspaperConfig # Config 임포트 추가
import nltk

# --- NLTK 리소스 다운로드 함수 (변경 없음) ---
def download_nltk_resources_if_needed():
    """NLTK의 'punkt' 리소스가 없으면 다운로드합니다."""
    try:
        nltk.data.find('tokenizers/punkt')
    except (LookupError, nltk.downloader.DownloadError):
        print("NLTK 'punkt' resource not found. Attempting to download...")
        try:
            nltk.download('punkt', quiet=True)
            print("'punkt' resource downloaded successfully for NLTK.")
        except Exception as e:
            print(f"Failed to download 'punkt' for NLTK automatically: {e}")

# --- 구글 검색 함수 (변경 없음) ---
def search_google_for_urls(query, num_to_fetch=5, language='en', tbs='qdr:w'):
    """주어진 검색어로 구글 검색을 실행하고 결과 URL 목록을 반환합니다. (최근 1주 검색 추가)"""
    print(f"\nSearching Google for '{query}' (max {num_to_fetch} results, lang: {language}, within last week)...")
    try:
        # tbs='qdr:w' (최근 1주일), 'qdr:d' (최근 1일), 'qdr:m' (최근 1달)
        # stop 파라미터로 가져올 결과 수 지정
        search_results_urls = list(search(query, lang=language, stop=num_to_fetch, pause=2.0, tbs=tbs))
        print(f"Found {len(search_results_urls)} URLs for '{query}'.")
        return search_results_urls
    except Exception as e:
        print(f"Error during Google search for '{query}': {e}")
        return []

# --- 기사 데이터 크롤링 함수 (Newspaper3k 설정 추가 및 반환값 명확화) ---
def crawl_article_data(url_to_crawl):
    """주어진 URL에서 뉴스 기사의 주요 정보를 크롤링하고 딕셔너리로 반환합니다."""
    print(f"  Crawling article: {url_to_crawl}")
    try:
        config = NewspaperConfig()
        config.browser_user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
        config.request_timeout = 15 # 요청 타임아웃 설정 (초)
        config.memoize_articles = False # 기사 캐싱 비활성화 (매번 새로 가져오기)
        # config.fetch_images = False # 이미지는 URL만 가져오므로 False로 설정하여 속도 향상 가능

        article = Article(url_to_crawl, config=config)
        article.download()
        article.parse()
        article.nlp() # NLP 처리 (요약, 키워드 등에 필요)

        # 발행일 처리 (datetime 객체 -> 문자열, 없을 경우 빈 문자열)
        published_date_str = ""
        if article.publish_date:
            try:
                published_date_str = article.publish_date.strftime('%Y-%m-%d %H:%M:%S')
            except AttributeError: # 가끔 publish_date가 이상한 타입으로 올 때 대비
                published_date_str = str(article.publish_date)


        return {
            "title": article.title if article.title else "N/A",
            "authors": ', '.join(article.authors) if article.authors else "",
            "published_date": published_date_str,
            "body": article.text if article.text else "",
            "image_url": article.top_image if article.top_image else "", # 이미지 URL
            "keywords": ', '.join(article.keywords) if article.keywords else "", # newspaper3k가 추출한 키워드
            "summary": article.summary if article.summary else "", # newspaper3k가 생성한 요약
            "url": url_to_crawl
        }
    except Exception as e:
        print(f"    Error crawling article {url_to_crawl}: {e}")
        return { # 실패 시 빈 데이터 반환 또는 특정 값으로 채움
            "title": "Error: Could not crawl", "authors": "", "published_date": "", 
            "body": "", "image_url": "", "keywords": "", "summary": "", "url": url_to_crawl
        }

# --- 뉴스 수집 파이프라인 실행 함수 (DataFrame 반환으로 변경) ---
def run_news_collection_pipeline(search_query, num_articles_to_fetch=5, lang='en'):
    """단일 검색어에 대해 뉴스 URL을 검색하고 기사 데이터를 크롤링하여 DataFrame으로 반환합니다."""
    print(f"\n=== Starting News Collection for Query: '{search_query}' ===")
    
    found_urls = search_google_for_urls(search_query, num_to_fetch=num_articles_to_fetch, language=lang)
    
    collected_articles_data = []
    if found_urls:
        print(f"\nProcessing {len(found_urls)} articles for '{search_query}'...")
        for i, url in enumerate(found_urls):
            if url: # 유효한 URL인지 한번 더 체크
                data = crawl_article_data(url)
                collected_articles_data.append(data)
                if i < len(found_urls) - 1: # 마지막 요청이 아니면 잠시 대기
                    time.sleep(1.5) # 요청 간 간격 (조절 가능)
            else:
                print(f"  Skipping invalid URL at index {i}.")
        
        if collected_articles_data:
            df_articles = pd.DataFrame(collected_articles_data)
            print(f"\nCollection for query '{search_query}' completed. {len(df_articles)} articles processed.")
            return df_articles
        else:
            print(f"No article data could be collected for query '{search_query}'.")
            return pd.DataFrame() # 빈 DataFrame 반환
    else:
        print(f"No URLs found for query '{search_query}'.")
        return pd.DataFrame() # 빈 DataFrame 반환

# --- 메인 실행 부분 (이 파일을 직접 테스트할 때만 작동) ---
if __name__ == "__main__":
    download_nltk_resources_if_needed() # 스크립트 직접 실행 시 NLTK 리소스 다운로드 확인

    test_query = "global AI ethics concerns" 
    num_to_fetch_test = 3 # 테스트용 기사 수
    
    print(f"Running standalone test for google_news_crawler.py with query: '{test_query}'")
    
    results_df = run_news_collection_pipeline(test_query, num_articles_to_fetch=num_to_fetch_test)
    
    if not results_df.empty:
        print("\n--- Sample of Crawled Data (First 2 articles) ---")
        print(results_df.head(2).to_string())
        
        # 테스트 결과를 CSV로 저장 (선택적)
        test_output_csv = "test_crawled_output.csv"
        if os.path.exists(test_output_csv): os.remove(test_output_csv)
        results_df.to_csv(test_output_csv, index=False, encoding='utf-8-sig')
        print(f"\nTest results saved to '{test_output_csv}'")
    else:
        print("\nNo data was crawled in the standalone test.")
        