import sys
import os
import pandas as pd
import time
from dotenv import load_dotenv  # .env 파일에서 환경 변수 로드
from supabase import create_client, Client  # Supabase 클라이언트

# --- 모듈 임포트 ---
# 스크립트가 있는 디렉토리를 sys.path에 추가 (선택적, 보통은 같은 디렉토리 내 모듈은 바로 임포트 가능)
# current_script_dir = os.path.dirname(os.path.abspath(__file__))
# if current_script_dir not in sys.path:
#     sys.path.append(current_script_dir)

try:
    # google_news_crawler.py에서 DataFrame을 반환하는 함수와 NLTK 다운로더 임포트
    from google_news_crawler import run_news_collection_pipeline, download_nltk_resources_if_needed
    # preprocess_data.py에서 데이터 전처리 함수와 필요한 상수 임포트
    from preprocess_data import preprocess_and_filter_data, SPACY_MODEL_NAME, CLEANED_NLP_NEWS_CSV_DEFAULT
    print("Successfully imported pipeline modules in run_pipeline.py.")
except ImportError as e:
    print(f"FATAL ERROR: Could not import required pipeline modules: {e}")
    print("Please ensure 'google_news_crawler.py' and 'preprocess_data.py' exist in the same directory as run_pipeline.py,")
    print("or that the project directory is correctly added to PYTHONPATH.")
    exit(1) # 필수 모듈 없이는 실행 불가

# .env 파일 로드 (SUPABASE_URL, SUPABASE_SERVICE_KEY)
load_dotenv()

# --- Supabase 설정 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # service_role 키 사용 권장
DB_NEWS_TABLE_NAME = "news_articles"  # Supabase에 생성한 테이블 이름

supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Successfully connected to Supabase for data pipeline.")
    except Exception as e:
        print(f"Warning: Error connecting to Supabase in run_pipeline.py: {e}")
        print("Database operations will be skipped if connection failed.")
        supabase_client = None # 명시적으로 None 처리
else:
    print("Warning: Supabase URL or SERVICE_ROLE Key not found in .env file. Database operations will be skipped.")

# --- 파일 이름 및 경로 설정 ---
# 여러 검색어 결과를 합친 크롤링 데이터 CSV 파일 (중간 저장용)
COMBINED_CRAWLED_ARTICLES_CSV = "combined_crawled_articles.csv"
# 최종 전처리된 데이터 CSV 파일 (Supabase 입력 및 디버깅용)
# preprocess_data.py의 기본 출력 파일명을 그대로 사용
PROCESSED_DATA_FOR_DB_CSV = CLEANED_NLP_NEWS_CSV_DEFAULT


# --- Supabase 저장용 데이터 포맷 함수 ---
def format_dataframe_for_supabase(input_df: pd.DataFrame):
    """
    입력 DataFrame (preprocess_data.py의 출력)을 Supabase 테이블 스키마에 맞게 포맷합니다.
    - 컬럼명 매핑
    - 데이터 타입 변환 (특히 published_date)
    - 누락값 처리 (NaN -> 빈 문자열 또는 None)
    - Supabase 테이블에 정의된 컬럼만 선택
    """
    if not isinstance(input_df, pd.DataFrame) or input_df.empty:
        print("Formatting warning: Input DataFrame is empty or not a DataFrame. Returning empty list.")
        return []
        
    df_to_format = input_df.copy()
    
    # preprocess_data.py의 출력 컬럼명 예시 (실제 출력과 일치해야 함):
    # 'Title', 'Published Date', 'URL', 'Body_Snippet', 
    # 'Relevance_Score', 'Image_URL', 'Country_ISO_Code', 'Full_Body'
    
    # Supabase 'news_articles' 테이블 컬럼명 (목표):
    # title, published_date, url, body, relevance_score, image_url, country_iso_code
    column_mapping = {
        'Title': 'title',
        'Published Date': 'published_date',    # preprocess_data.py에서 YYYY-MM-DD 형식으로 출력됨
        'URL': 'url',
        'Body_Snippet': 'body',              # 뉴스 요약본을 'body' 컬럼에 저장
        # 'Full_Body': 'full_body_content',  # 전체 본문을 다른 컬럼에 저장하고 싶다면
        'Relevance_Score': 'relevance_score',
        'Image_URL': 'image_url',
        'Country_ISO_Code': 'country_iso_code'
    }
    df_to_format.rename(columns=column_mapping, inplace=True)

    # 1. published_date: TIMESTAMPTZ 타입에 맞게 ISO 8601 형식 (UTC 자정)으로 변환
    if 'published_date' in df_to_format.columns:
        df_to_format['published_date'] = pd.to_datetime(df_to_format['published_date'], errors='coerce')
        df_to_format['published_date'] = df_to_format['published_date'].apply(
            lambda x: x.strftime('%Y-%m-%dT00:00:00Z') if pd.notnull(x) else None
        )
    else:
        df_to_format['published_date'] = None # 컬럼 없으면 None으로 채움 (DB에서 nullable이어야 함)

    # 2. relevance_score: 숫자형 변환, NaN은 0.0으로
    if 'relevance_score' in df_to_format.columns:
        df_to_format['relevance_score'] = pd.to_numeric(df_to_format['relevance_score'], errors='coerce').fillna(0.0)
    else:
        df_to_format['relevance_score'] = 0.0

    # 3. 텍스트 필드 (image_url, country_iso_code, body, title, url): NaN/None을 빈 문자열로, 문자열 타입으로 변환
    text_columns_for_db = ['title', 'url', 'body', 'image_url', 'country_iso_code']
    for col in text_columns_for_db:
        if col in df_to_format.columns:
            df_to_format[col] = df_to_format[col].fillna('').astype(str)
        else: # DataFrame에 해당 컬럼이 아예 없는 경우 (이전 단계 문제)
            print(f"Formatting Warning: Column '{col}' is missing in DataFrame. Adding as empty string.")
            df_to_format[col] = ''
            
    # 4. Supabase 테이블에 실제로 있는 컬럼만 선택하여 레코드 리스트 생성
    # 이 리스트는 Supabase 테이블의 실제 컬럼과 정확히 일치해야 합니다.
    # (id, created_at 등 자동 생성/관리되는 컬럼은 여기서 제외)
    final_db_columns = ['title', 'published_date', 'url', 'body', 'relevance_score', 'image_url', 'country_iso_code']
    
    # DataFrame에 최종 컬럼들이 모두 있는지 확인, 없으면 빈 값으로 추가
    for db_col in final_db_columns:
        if db_col not in df_to_format.columns:
            print(f"Formatting Warning: Expected DB column '{db_col}' not found in DataFrame. Adding with default (None or empty).")
            if db_col == 'published_date':
                 df_to_format[db_col] = None
            elif db_col == 'relevance_score':
                 df_to_format[db_col] = 0.0
            else:
                 df_to_format[db_col] = ''


    records_list = df_to_format[final_db_columns].to_dict(orient='records')
    
    # 추가 검증: url이 비어있는 레코드는 제외 (DB에서 NOT NULL UNIQUE 제약조건 위반 방지)
    valid_records = [rec for rec in records_list if rec.get('url')]
    if len(valid_records) < len(records_list):
        print(f"Formatting Warning: {len(records_list) - len(valid_records)} records removed due to missing URL.")
        
    return valid_records


def save_data_to_supabase(db_client: Client, table_name: str, data_records_list: list):
    """데이터 레코드 리스트를 Supabase 테이블에 저장합니다 (upsert 사용)."""
    if not db_client:
        print("Supabase client is not initialized. Skipping database save operation.")
        return False
    if not data_records_list:
        print("No valid records provided to save to Supabase.")
        return True # 작업할 데이터가 없는 것은 오류가 아님

    try:
        print(f"Attempting to upsert {len(data_records_list)} records into Supabase table '{table_name}' (on_conflict='url')...")
        # Supabase 테이블의 'url' 컬럼에 UNIQUE 제약조건이 설정되어 있어야 upsert가 올바르게 작동합니다.
        response = db_client.table(table_name).upsert(data_records_list, on_conflict='url').execute()
        
        # supabase-py v1.x 이후, 에러는 response.error 로, 성공 시 데이터는 response.data 로 접근
        if hasattr(response, 'error') and response.error:
            print(f"ERROR during Supabase upsert: {response.error}")
            # 문제 해결을 위해 첫 번째 레코드 샘플 출력
            if data_records_list:
                print(f"Sample of first record that might have caused error: {data_records_list[0]}")
            return False
        else:
            num_processed = len(response.data) if hasattr(response, 'data') and response.data else "unknown (check Supabase logs)"
            print(f"Successfully upserted/processed records in Supabase. Response count/length: {num_processed}")
            return True
    except Exception as e:
        print(f"An unexpected exception occurred during Supabase upsert operation: {e}")
        return False

# --- 메인 파이프라인 실행 함수 ---
def execute_full_news_data_pipeline():
    start_pipeline_time = time.time()
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === Starting Full News Data Pipeline ===")
    overall_pipeline_status_ok = True # 전체 파이프라인 성공 여부 플래그

    # --- 단계 0: 환경 점검 ---
    print("\n--- Step 0: Environment & Prerequisites Check ---")
    try:
        download_nltk_resources_if_needed() # google_news_crawler에서 가져온 함수
        import spacy # spaCy 로드 시도 (preprocess_data.py에서도 로드하지만, 여기서 한번 더 확인)
        spacy.load(SPACY_MODEL_NAME) 
        print("NLTK and spaCy environment appear to be OK.")
    except Exception as e:
        print(f"FATAL ERROR during environment pre-check (NLTK/spaCy): {e}.")
        print("Pipeline cannot continue without these prerequisites.")
        return False # 필수 환경 없으면 파이프라인 중단

    # --- 단계 1: 뉴스 크롤링 (여러 검색어 결과 종합) ---
    print(f"\n--- Step 1: News Crawling ---")
    # 검색어 목록은 외부 설정 파일(예: JSON, YAML)에서 읽어오는 것이 더 좋음
    news_search_queries = [
        "global conflict overview", "ukraine war updates", "middle east security situation", 
        "political instability in africa", "asia pacific tensions", "global humanitarian aid efforts",
        "major international disputes"
    ]
    articles_to_fetch_per_query = 7 # 테스트 시에는 2-3개로 줄여서 사용

    all_crawled_dataframes_list = []
    crawling_step_success = True
    for i, query_term in enumerate(news_search_queries):
        print(f"\nCrawling for query {i+1}/{len(news_search_queries)}: '{query_term}'...")
        try:
            # run_news_collection_pipeline은 DataFrame을 반환 (google_news_crawler.py 수정됨)
            df_from_query = run_news_collection_pipeline(query_term, num_articles_to_fetch=articles_to_fetch_per_query)
            if df_from_query is not None and not df_from_query.empty:
                all_crawled_dataframes_list.append(df_from_query)
                print(f"Crawled {len(df_from_query)} articles for '{query_term}'.")
            else:
                print(f"No articles found or DataFrame was empty for query '{query_term}'.")
        except Exception as e:
            print(f"ERROR during news crawling for query '{query_term}': {e}")
            crawling_step_success = False # 크롤링 중 에러 발생 시 플래그 설정
            # 여기서 break 할 수도 있지만, 다른 쿼리는 계속 시도하도록 둠

    if not all_crawled_dataframes_list:
        print("CRITICAL: No articles were crawled from any query. Aborting pipeline.")
        return False # 크롤링된 데이터가 전혀 없으면 중단
    if not crawling_step_success:
        print("Warning: Some crawling queries may have failed. Proceeding with available data.")
        overall_pipeline_status_ok = False # 전체 성공은 아님을 표시

    # 모든 검색어 결과를 하나의 DataFrame으로 합치고 URL 기준 중복 제거
    master_crawled_df = pd.concat(all_crawled_dataframes_list, ignore_index=True)
    if 'url' in master_crawled_df.columns: # 'url' 컬럼명 확인
        master_crawled_df.drop_duplicates(subset=['url'], keep='first', inplace=True)
    else: # 'URL' 등 다른 이름일 경우 대비 (google_news_crawler.py의 반환 컬럼명 확인 필요)
        print("Warning: 'url' column not found for deduplication. Check crawler output.")
        # master_crawled_df.drop_duplicates(subset=['URL'], keep='first', inplace=True)

    # 합쳐진 크롤링 결과를 CSV로 저장 (디버깅 및 중간 저장용)
    try:
        master_crawled_df.to_csv(COMBINED_CRAWLED_ARTICLES_CSV, index=False, encoding='utf-8-sig')
        print(f"All crawled data combined ({len(master_crawled_df)} unique articles after deduplication) and saved to '{COMBINED_CRAWLED_ARTICLES_CSV}'.")
    except Exception as e:
        print(f"Error saving combined crawled data to CSV: {e}")
        overall_pipeline_status_ok = False


    # --- 단계 2: 데이터 전처리 및 NLP 분석 ---
    print(f"\n--- Step 2: Data Preprocessing & NLP Analysis ---")
    preprocessing_step_success = False
    if os.path.exists(COMBINED_CRAWLED_ARTICLES_CSV) and os.path.getsize(COMBINED_CRAWLED_ARTICLES_CSV) > 0:
        try:
            # preprocess_and_filter_data는 COMBINED_CRAWLED_ARTICLES_CSV를 입력으로 받고,
            # PROCESSED_DATA_FOR_DB_CSV (기본값: "cleaned_nlp_news.csv")에 결과를 저장
            preprocess_and_filter_data(COMBINED_CRAWLED_ARTICLES_CSV, PROCESSED_DATA_FOR_DB_CSV)
            
            if not os.path.exists(PROCESSED_DATA_FOR_DB_CSV) or os.path.getsize(PROCESSED_DATA_FOR_DB_CSV) == 0:
                print(f"Warning: Preprocessing completed, but output file '{PROCESSED_DATA_FOR_DB_CSV}' is empty or not created.")
                # 전처리 결과가 없으면 DB 저장 불가
            else:
                print(f"Data preprocessing completed. Output saved to '{PROCESSED_DATA_FOR_DB_CSV}'.")
                preprocessing_step_success = True
        except Exception as e:
            print(f"ERROR during data preprocessing: {e}")
            overall_pipeline_status_ok = False
    else:
        print(f"Combined crawled news CSV ('{COMBINED_CRAWLED_ARTICLES_CSV}') not found or empty. Skipping preprocessing.")
        overall_pipeline_status_ok = False # 전처리할 데이터가 없으므로 실패 간주


    # --- 단계 3: Supabase에 데이터 저장 ---
    db_save_step_success = False
    if overall_pipeline_status_ok and preprocessing_step_success and supabase_client and \
       os.path.exists(PROCESSED_DATA_FOR_DB_CSV) and \
       os.path.getsize(PROCESSED_DATA_FOR_DB_CSV) > 0:
        print(f"\n--- Step 3: Saving Processed Data to Supabase ---")
        try:
            processed_df_for_db = pd.read_csv(PROCESSED_DATA_FOR_DB_CSV, keep_default_na=False, na_values=['']) # NaN 처리 명시적
            if not processed_df_for_db.empty:
                records_to_upsert = format_dataframe_for_supabase(processed_df_for_db)
                if records_to_upsert: # 포맷팅 후 유효한 레코드가 있을 때만 저장 시도
                    if save_data_to_supabase(supabase_client, DB_NEWS_TABLE_NAME, records_to_upsert):
                        db_save_step_success = True
                    else:
                        overall_pipeline_status_ok = False # DB 저장 실패
                else:
                    print("No valid records to save to Supabase after formatting.")
                    db_save_step_success = True # 저장할 데이터가 없는 것은 오류가 아님
            else:
                print(f"'{PROCESSED_DATA_FOR_DB_CSV}' is empty after reading. Nothing to save to Supabase.")
                db_save_step_success = True # 저장할 데이터 없는 것 오류 아님
        except pd.errors.EmptyDataError:
            print(f"Warning: Processed CSV '{PROCESSED_DATA_FOR_DB_CSV}' is empty (read as empty). Nothing to save to Supabase.")
            db_save_step_success = True
        except Exception as e:
            print(f"ERROR reading processed CSV for Supabase or during save operation: {e}")
            overall_pipeline_status_ok = False
    elif not supabase_client:
        print("\nSupabase client not available, database save operation skipped.")
    elif overall_pipeline_status_ok and preprocessing_step_success:
         print(f"\nProcessed CSV ('{PROCESSED_DATA_FOR_DB_CSV}') not found or empty. Skipping Supabase save.")
    
    if not db_save_step_success and overall_pipeline_status_ok and preprocessing_step_success and supabase_client:
        # DB 저장이 실제로 시도되었어야 했는데 실패한 경우
        overall_pipeline_status_ok = False


    # 파이프라인 종료 로깅
    total_pipeline_duration_seconds = time.time() - start_pipeline_time
    final_status_message = "Successfully" if overall_pipeline_status_ok else "with ERRORS or INCOMPLETELY"
    
    print(f"\n\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] === Full News Data Pipeline Completed {final_status_message}! (Duration: {total_pipeline_duration_seconds:.2f} seconds) ===")
    if overall_pipeline_status_ok:
        print(f"  - Combined crawled data was processed from '{COMBINED_CRAWLED_ARTICLES_CSV}'.")
        print(f"  - Final processed data for DB is in '{PROCESSED_DATA_FOR_DB_CSV}'.")
        print(f"  - Data has been saved/updated in Supabase table '{DB_NEWS_TABLE_NAME}'.")
        print("\n  API server (api_server.py) can now serve this updated data to the frontend.")
    else:
        print("  Pipeline did not complete successfully. Please review the logs above for detailed error messages.")
    
    return overall_pipeline_status_ok

# --- 스크립트 직접 실행 시 ---
if __name__ == "__main__":
    # 이 스크립트가 직접 실행될 때 파이프라인 실행
    pipeline_run_succeeded = execute_full_news_data_pipeline()
    
    if pipeline_run_succeeded:
        print("\nPipeline execution finished with overall success indicator TRUE.")
    else:
        print("\nPipeline execution finished with overall success indicator FALSE. Check logs.")
        