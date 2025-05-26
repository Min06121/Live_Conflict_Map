import os
from flask import Flask, jsonify, request
from flask_cors import CORS # 다른 도메인에서의 요청 허용
from supabase import create_client, Client # Supabase 클라이언트
from dotenv import load_dotenv # .env 파일 로드
from datetime import datetime, timezone # 날짜/시간 객체 및 UTC
import pandas as pd # 날짜 파싱 등에 간혹 유용하게 사용
import pytz # 시간대 변환 라이브러리

# .env 파일에서 환경 변수 로드 (SUPABASE_URL, SUPABASE_SERVICE_KEY)
load_dotenv()

# --- Flask 애플리케이션 초기화 ---
app = Flask(__name__)
# 개발 중에는 모든 도메인 허용, 프로덕션에서는 특정 도메인만 허용하도록 설정 필요
CORS(app) 
# 예: CORS(app, resources={r"/api/*": {"origins": ["http://localhost:8000", "https://your-production-domain.com"]}})


# --- Supabase 클라이언트 초기화 ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") # .env 파일에서 가져옴 (service_role 키 권장)
NEWS_TABLE_NAME_IN_DB = "news_articles" # Supabase에 생성한 테이블 이름

supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Successfully connected to Supabase for API server.")
    except Exception as e:
        print(f"Error connecting to Supabase for API server: {e}")
        # supabase_client는 None으로 유지되어 API 호출 시 에러 반환됨
else:
    print("API Server FATAL ERROR: Supabase URL or SERVICE_ROLE Key not found in .env file. API cannot function.")
    # 실제 운영 시에는 여기서 서버가 시작되지 않도록 처리할 수도 있음

# --- 시간대 설정 (미국 동부 시간) ---
US_EASTERN_TIMEZONE_STR = 'America/New_York'
try:
    US_EASTERN_TZ = pytz.timezone(US_EASTERN_TIMEZONE_STR)
except pytz.exceptions.UnknownTimeZoneError:
    print(f"Error: Timezone '{US_EASTERN_TIMEZONE_STR}' not found. Defaulting to UTC for news item timestamps.")
    US_EASTERN_TZ = pytz.utc # 폴백으로 UTC 사용

# --- 프론트엔드 응답 형식 변환 함수 ---
def format_news_item_for_frontend(db_news_item):
    """Supabase에서 가져온 DB 뉴스 항목을 프론트엔드가 사용할 JSON 객체 형식으로 변환합니다."""
    
    published_date_from_db = db_news_item.get('published_date') # TIMESTAMPTZ (UTC) 형식의 문자열 또는 None
    formatted_display_time = "Date N/A" # 기본값

    if published_date_from_db:
        try:
            # DB에서 온 UTC 시간 문자열을 datetime 객체로 파싱
            # Supabase는 보통 ISO 8601 형식 (예: '2023-10-26T10:00:00+00:00')으로 반환
            dt_utc = pd.to_datetime(published_date_from_db).replace(tzinfo=timezone.utc)
            # dt_utc = datetime.fromisoformat(str(published_date_from_db).replace('Z', '+00:00')) # 다른 파싱 방법
            
            # 설정된 미국 시간대로 변환
            dt_us_eastern = dt_utc.astimezone(US_EASTERN_TZ)
            
            # 프론트엔드 표시 형식 (예: "May 26, 2025, 12:41 AM EDT")
            formatted_display_time = dt_us_eastern.strftime('%b %d, %Y, %I:%M %p %Z') 
        except Exception as e:
            print(f"Warning: Could not parse/convert date '{published_date_from_db}' (item id: {db_news_item.get('id')}, url: {db_news_item.get('url')}): {e}")
            # 파싱 실패 시, 원본 날짜의 YYYY-MM-DD 부분만 사용 시도 (DB가 DATE 타입일 경우)
            if isinstance(published_date_from_db, str) and len(published_date_from_db) >= 10:
                formatted_display_time = published_date_from_db[:10] 
            else:
                formatted_display_time = "Invalid Date Format"

    return {
        "id": db_news_item.get('id'), # Supabase 테이블의 PK (보통 uuid 또는 bigint)
        "time": formatted_display_time, # 미국 시간으로 포맷된 시간 문자열
        "title": str(db_news_item.get('title', 'Untitled News')),
        "link": str(db_news_item.get('url', '#')),
        "description": str(db_news_item.get('body', 'No description available.')), # DB의 'body' 컬럼 (요약본)
        "relevance_score": float(db_news_item.get('relevance_score', 0.0)),
        "image_url": str(db_news_item.get('image_url', '')), # 이미지 URL
        "location": str(db_news_item.get('country_iso_code', '')) # 국가 ISO 코드 (프론트엔드에서는 'location' 키로 사용 가능)
    }

# --- API 엔드포인트 정의: /api/news ---
@app.route('/api/news', methods=['GET'])
def get_news_feed_data():
    """뉴스 데이터를 조회하여 JSON 형태로 반환합니다. 페이징, 날짜/키워드/국가 필터링 지원."""
    if not supabase_client:
        return jsonify({"error": "Database connection not available. Please check server logs."}), 500

    try:
        # 요청 파라미터 가져오기 (프론트엔드 script.js와 일치)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('limit', 10, type=int) # script.js의 NEWS_ITEMS_PER_PAGE와 맞춤
        offset = (page - 1) * per_page
        
        date_filter = request.args.get('date')           # 형식: YYYY-MM-DD
        keyword_filter = request.args.get('keyword')     # 검색할 키워드 문자열
        country_iso_filter = request.args.get('country_iso') # 필터링할 국가의 ISO A2 코드

        # Supabase 쿼리 빌더 시작
        query_builder = supabase_client.table(NEWS_TABLE_NAME_IN_DB).select(
            "id, title, published_date, url, body, relevance_score, image_url, country_iso_code", # 필요한 모든 컬럼 명시
            count="exact" # 전체 결과 수를 함께 가져옴 (페이징용)
        )

        # 필터 적용
        if date_filter:
            # Supabase DB의 'published_date' 컬럼이 TIMESTAMPTZ (UTC로 저장)라고 가정
            # 해당 날짜의 UTC 시작(00:00:00Z)과 끝(23:59:59.999999Z)으로 범위 검색
            try:
                # 날짜 문자열 유효성 검사 (간단하게)
                datetime.strptime(date_filter, '%Y-%m-%d') 
                start_utc_str = f"{date_filter}T00:00:00Z"
                end_utc_str = f"{date_filter}T23:59:59.999999Z"
                query_builder = query_builder.gte('published_date', start_utc_str)
                query_builder = query_builder.lte('published_date', end_utc_str)
                print(f"API: Applying date filter for (UTC): {start_utc_str} to {end_utc_str}")
            except ValueError:
                print(f"API Warning: Invalid date format for filter: '{date_filter}'. Ignoring date filter.")
        
        if keyword_filter and keyword_filter.strip():
            # PostgreSQL의 ilike (대소문자 무시) 또는 더 강력한 Full-Text Search (fts) 사용
            # 여기서는 title 또는 body에 키워드가 포함된 경우 (간단한 형태)
            search_pattern = f"%{keyword_filter.strip()}%"
            query_builder = query_builder.or_(f"title.ilike.{search_pattern},body.ilike.{search_pattern}")
            print(f"API: Applying keyword filter: '{keyword_filter.strip()}'")
            
        if country_iso_filter and country_iso_filter.strip():
            # 국가 ISO 코드로 필터링 (DB에는 대문자로 저장되어 있다고 가정)
            query_builder = query_builder.eq('country_iso_code', country_iso_filter.strip().upper())
            print(f"API: Applying country ISO code filter: '{country_iso_filter.strip().upper()}'")

        # 정렬: 1순위 관련도 점수 (높은 순), 2순위 발행일 (최신 순)
        # nulls_last=True: null 값을 가진 필드를 정렬 시 마지막으로 보냄
        query_builder = query_builder.order('relevance_score', desc=True, nulls_last=True)
        query_builder = query_builder.order('published_date', desc=True, nulls_last=True)
        
        # 페이징 적용
        query_builder = query_builder.range(offset, offset + per_page - 1)

        # 쿼리 실행
        response = query_builder.execute()

        # 응답 처리
        if hasattr(response, 'data') and response.data is not None:
            formatted_news_list = [format_news_item_for_frontend(item) for item in response.data]
            total_items_count = response.count if hasattr(response, 'count') else len(formatted_news_list)
            
            return jsonify({
                "news": formatted_news_list,
                "total_count": total_items_count,
                "page": page,
                "per_page": per_page
            })
        elif hasattr(response, 'error') and response.error:
            print(f"Supabase API query error: {response.error}")
            return jsonify({"error": "Failed to retrieve news data from database.", "details": str(response.error)}), 500
        else: # 데이터가 없는 경우 (정상적일 수 있음)
            return jsonify({"news": [], "total_count": 0, "page": page, "per_page": per_page})

    except Exception as e:
        print(f"API Server Exception in /api/news: {e}")
        # 프로덕션에서는 실제 에러 내용을 사용자에게 노출하지 않는 것이 좋음
        return jsonify({"error": "An unexpected error occurred on the API server."}), 500

# --- 서버 실행 (이 파일을 직접 실행할 경우) ---
if __name__ == '__main__':
    # 디버그 모드는 개발 중에만 사용, 프로덕션에서는 False로 설정하고 Gunicorn 등 WSGI 서버 사용
    # host='0.0.0.0'으로 설정하면 로컬 네트워크 내 다른 기기에서도 접속 가능 (개발 시 유용)
    app.run(host='0.0.0.0', port=5001, debug=True) 
    print(f"Flask API server for news started on http://0.0.0.0:5001 (Debug mode: {app.debug})")
    