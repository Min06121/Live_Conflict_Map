import csv
import os
import time
from googlesearch import search
from requests_html import HTMLSession # HTMLSession을 제대로 임포트

# --- 함수 정의 ---
def search_google_for_urls(query, num_to_fetch=5, language='en'): # 기본 언어를 'en'으로 설정
    """주어진 검색어로 구글 검색을 실행하고 결과 URL 목록을 반환하는 함수."""
    print(f"\nSearching Google for '{query}' (max {num_to_fetch} results, lang: {language})...")
    try:
        # googlesearch 라이브러리의 search 함수 사용
        # num_results는 일부 버전에서 사용될 수 있으나, 공식적인 googlesearch 라이브러리는 num을 주로 사용
        # 여기서는 num_results를 내부적으로 num으로 매핑하거나, 라이브러리가 이를 지원한다고 가정
        # 또는, 가장 기본적인 search(query, lang=language)만 사용하고 결과 수를 라이브러리 기본값에 맡길 수도 있음
        # 여기서는 num_results를 그대로 사용하되, 라이브러리가 이를 num으로 이해한다고 가정
        search_results_urls = list(search(query, lang=language, num_results=num_to_fetch))
        print(f"Found {len(search_results_urls)} URLs.")
        return search_results_urls
    except Exception as e:
        print(f"Error during Google search for '{query}': {e}")
        return []

def crawl_article_data(url_to_crawl):
    """주어진 URL에서 뉴스 기사의 제목, 발행일, 본문을 크롤링하고 딕셔너리로 반환합니다."""
    print(f"\nAttempting to crawl: {url_to_crawl}")
    session = HTMLSession() # 각 크롤링마다 새 세션 사용
    article_data = {
        "title": "Title not found",
        "published_date": "Published date not found",
        "url": url_to_crawl,
        "body": "Body not found"
    }
    try:
        response = session.get(url_to_crawl, timeout=20) # 타임아웃 증가
        response.raise_for_status() # HTTP 오류 시 예외 발생

        # 제목 추출 (더 많은 일반적인 경우 고려)
        title_selectors = ['h1', 'header h1', 'h2.article-title', 'h1.entry-title'] # 다양한 선택지
        for selector in title_selectors:
            title_element = response.html.find(selector, first=True)
            if title_element:
                article_data["title"] = title_element.text.strip()
                break
        
        # 발행일 추출 (더 많은 메타 태그 및 일반적인 패턴 고려)
        date_selectors_meta = [
            'meta[property="article:published_time"]',
            'meta[name="pubdate"]',
            'meta[name="creation_date"]',
            'meta[name="cXenseParse:recs:publishtime"]',
            'meta[name="dcterms.created"]',
            'meta[name="date"]'
        ]
        date_found = False
        for selector in date_selectors_meta:
            meta_date_element = response.html.find(selector, first=True)
            if meta_date_element and 'content' in meta_date_element.attrs and meta_date_element.attrs['content']:
                article_data["published_date"] = meta_date_element.attrs['content'].strip()
                date_found = True
                break
        
        if not date_found: # 화면에 보이는 날짜 시도 (더 일반적인 선택자)
            # time 태그는 datetime 속성을 가질 가능성이 높음
            time_element = response.html.find('time', first=True)
            if time_element and time_element.attrs.get('datetime'):
                article_data["published_date"] = time_element.attrs['datetime'].strip()
            elif time_element: # datetime 속성이 없으면 텍스트라도
                 article_data["published_date"] = time_element.text.strip()
            else: # 그 외 일반적인 클래스명 시도
                date_display_elements = response.html.find('span[class*="date"], div[class*="date"], p[class*="date"]', first=True)
                if date_display_elements:
                    article_data["published_date"] = date_display_elements.text.strip()

        # 본문 내용 추출 (더 많은 일반적인 컨테이너 및 <p> 태그 조합)
        article_body_parts = []
        content_selectors = ['article', 'main', 'div.story-content', 'div.article-content', 
                             'div.entry-content', 'div.post-content', 'div.content', 'div.body', 
                             'section[class*="article-body"]']
        
        content_container = None
        for selector in content_selectors:
            content_container = response.html.find(selector, first=True)
            if content_container:
                break
        
        if content_container: # 특정 컨테이너를 찾았으면 그 안의 p 태그
            paragraph_elements = content_container.find('p')
        else: # 못 찾았으면 전체 문서에서 p 태그 (최후의 수단)
            paragraph_elements = response.html.find('p')

        if paragraph_elements:
            for p_element in paragraph_elements:
                # 짧은 p 태그 (예: 캡션, 광고 링크 등)는 제외하는 로직 추가 가능
                if len(p_element.text.strip()) > 50 : # 예: 50자 이상인 문단만 포함
                    article_body_parts.append(p_element.text.strip())
        
        if article_body_parts:
            article_data["body"] = "\n".join(article_body_parts)
        
        print(f"Crawling for '{article_data['title'][:30]}...' completed.")

    except Exception as e:
        print(f"Error crawling {url_to_crawl}: {e}")
    finally:
        session.close() # 세션 종료
        return article_data

def run_news_collection_pipeline(search_query, csv_filename="crawled_news.csv", num_articles_per_query=5):
    """주어진 검색어로 뉴스를 크롤링하고 지정된 CSV 파일에 추가(append)합니다."""
    print(f"\n=== Starting news collection for query: '{search_query}' ===")
    found_urls = search_google_for_urls(search_query, num_to_fetch=num_articles_per_query, language='en')
    
    if found_urls:
        csv_header = ["Title", "Published Date", "URL", "Body"] # Body Snippet 대신 전체 Body 저장 시도
        file_exists = os.path.isfile(csv_filename)
        
        print(f"\nSaving crawled data to '{csv_filename}' (append mode)...")
        
        with open(csv_filename, mode='a', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            if not file_exists or os.path.getsize(csv_filename) == 0:
                writer.writerow(csv_header)
            
            for i, url in enumerate(found_urls):
                # 구글 검색 후 바로 크롤링하므로 URL 간 time.sleep은 여기서는 생략.
                # 필요하다면 crawl_article_data 내부나 이 루프에 추가 가능.
                # search_google_for_urls 함수 내부에 이미 pause=2.0 (기본값) 있음.
                # if i > 0: time.sleep(1) # 크롤링 간 간격

                data = crawl_article_data(url)
                # Body 전체를 저장하도록 변경 (snippet은 전처리에서 생성)
                row_to_write = [data["title"], data["published_date"], data["url"], data["body"]]
                writer.writerow(row_to_write)
        
        print(f"\nData saving for query '{search_query}' completed. Check '{csv_filename}'.")
    else:
        print(f"No URLs found for query '{search_query}'.")

# --- 메인 실행 부분 (이 파일을 직접 실행할 경우에만 작동) ---
if __name__ == "__main__":
    # 이 스크립트를 직접 테스트할 때 사용할 검색어 및 파일 이름
    test_query = "latest global conflict updates" 
    test_csv_file = "test_crawled_news.csv" # 테스트 시에는 다른 파일에 저장하여 원래 데이터 보호

    print(f"Running single test for query: '{test_query}'")
    print(f"Output will be saved to: '{test_csv_file}' (if this script is run directly)")
    
    # 이전 테스트 파일이 있다면 삭제 (매번 새로운 테스트 결과를 위해)
    if os.path.exists(test_csv_file):
        os.remove(test_csv_file)
        print(f"'{test_csv_file}' deleted for a fresh test run.")
        
    run_news_collection_pipeline(test_query, csv_filename=test_csv_file, num_articles_per_query=3) # 테스트는 3개만
    
    print("\nThis script is primarily designed to be imported and used by 'run_pipeline.py'.")
    print("For direct testing, it used the test_query and test_csv_file variables above.")
    
