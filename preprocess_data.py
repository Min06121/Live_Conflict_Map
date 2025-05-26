import pandas as pd
from bs4 import BeautifulSoup
import spacy
# from spacy.matcher import Matcher # 현재 버전에서는 Matcher 직접 사용 안 함
import re
import json # GeoJSON 파일 로드용
import os   # 파일 경로 확인용

# --- spaCy 영어 모델 로드 ---
NLP_EN = None
SPACY_MODEL_NAME = "en_core_web_sm"
try:
    NLP_EN = spacy.load(SPACY_MODEL_NAME)
    print(f"spaCy English model '{SPACY_MODEL_NAME}' loaded successfully in preprocess_data.py.")
except OSError:
    print(f"spaCy model '{SPACY_MODEL_NAME}' not found. Please run: python -m spacy download {SPACY_MODEL_NAME}")
    NLP_EN = None # 명시적으로 None 설정
except Exception as e:
    print(f"An error occurred while loading the spaCy model in preprocess_data.py: {e}")
    NLP_EN = None

# --- 설정값 ---
RELEVANCE_THRESHOLD = 2.0 # 관련도 점수 임계값 (조정 가능)
MIN_TEXT_LENGTH_FOR_SCORING = 30 # 점수 계산을 위한 최소 텍스트 길이
MAX_BODY_SNIPPET_LENGTH = 250   # 뉴스 요약본 최대 길이
CLEANED_NLP_NEWS_CSV_DEFAULT = "cleaned_nlp_news.csv" # 이 스크립트의 기본 출력 파일명

# GeoJSON 파일 경로 (프로젝트 루트에 있다고 가정)
# 이 파일은 국가명과 ISO_A2 코드를 매핑하는 데 사용됩니다.
# script.js에서 사용하는 COUNTRIES_GEOJSON_URL과 동일한 내용의 로컬 파일이어야 합니다.
GEOJSON_FILE_PATH = "countries_geo.json" 

# --- 국가명-ISO 코드 매핑 및 국가명 리스트 ---
COUNTRY_ISO_MAP = {} # {'united states': 'US', 'south korea': 'KR', ...} (소문자 국가명 기준)
ALL_COUNTRY_NAMES_LOWER = set() # {'united states', 'south korea', ...} (매칭용 소문자 국가명 세트)

def load_country_data_from_geojson(geojson_path):
    """GeoJSON 파일에서 국가명과 ISO_A2 코드를 로드하여 매핑 및 이름 세트 생성."""
    global COUNTRY_ISO_MAP, ALL_COUNTRY_NAMES_LOWER
    # 경로가 절대 경로가 아니면, 이 스크립트 파일 위치 기준으로 구성
    if not os.path.isabs(geojson_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        geojson_path = os.path.join(script_dir, geojson_path)

    if not os.path.exists(geojson_path):
        print(f"Error: GeoJSON file for country mapping ('{geojson_path}') not found.")
        return

    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)
        
        for feature in geojson_data.get('features', []):
            properties = feature.get('properties', {})
            # GeoJSON 파일의 속성명에 따라 'ADMIN' 또는 'name' 등을 사용
            country_name = properties.get('ADMIN') or properties.get('NAME') or properties.get('name') 
            iso_a2 = properties.get('ISO_A2')
            
            if country_name and iso_a2 and iso_a2 != "-99": # 유효한 ISO A2 코드만
                country_name_lower = str(country_name).lower().strip()
                iso_a2_upper = str(iso_a2).upper().strip()
                
                COUNTRY_ISO_MAP[country_name_lower] = iso_a2_upper
                ALL_COUNTRY_NAMES_LOWER.add(country_name_lower)
                
                # 추가적인 일반적인 이름 변형 (예시)
                if "united states of america" in country_name_lower:
                    for variant in ["united states", "u.s.", "usa", "america"]:
                        COUNTRY_ISO_MAP[variant] = "US"
                        ALL_COUNTRY_NAMES_LOWER.add(variant)
                if "united kingdom" in country_name_lower:
                     for variant in ["u.k.", "great britain", "britain"]:
                        COUNTRY_ISO_MAP[variant] = "GB"
                        ALL_COUNTRY_NAMES_LOWER.add(variant)
                # (다른 국가들의 일반적인 별칭이나 약칭도 필요에 따라 추가)

        if COUNTRY_ISO_MAP:
            print(f"Successfully loaded {len(COUNTRY_ISO_MAP)} country-ISO mappings from '{geojson_path}'.")
        else:
            print(f"Warning: No country-ISO mappings loaded from '{geojson_path}'. Country extraction may not be effective.")
    except Exception as e:
        print(f"An error occurred loading country mappings from '{geojson_path}': {e}")

# 스크립트 로드 시 국가 매핑 정보 준비
if NLP_EN: # NLP 모델이 로드되었을 때만 국가 매핑 시도 (NER에 필요)
    load_country_data_from_geojson(GEOJSON_FILE_PATH)


# --- 텍스트 클리닝, 정규화, 요약 함수 ---
def clean_html_text(raw_html):
    if not raw_html or pd.isna(raw_html): return ""
    try:
        return BeautifulSoup(str(raw_html), "html.parser").get_text(separator=" ", strip=True)
    except Exception:
        return str(raw_html) # 이미 텍스트이거나 파싱 불가 시 원본 반환

def normalize_iso_date(date_str):
    if not date_str or pd.isna(date_str): return None
    try:
        # 입력이 이미 datetime 객체일 수도 있음 (google_news_crawler.py 수정에 따라)
        if isinstance(date_str, pd.Timestamp) or hasattr(date_str, 'strftime'):
            dt_obj = pd.to_datetime(date_str, errors='coerce')
        else: # 문자열일 경우
            dt_obj = pd.to_datetime(str(date_str), errors='coerce')
        
        return dt_obj.strftime('%Y-%m-%d') if pd.notnull(dt_obj) else None
    except Exception:
        return None

def create_text_snippet(full_text, max_length=MAX_BODY_SNIPPET_LENGTH):
    if not full_text or pd.isna(full_text): return ""
    text = str(full_text).strip()
    if len(text) <= max_length:
        return text
    # 마지막 단어가 잘리지 않도록 공백 기준으로 자르고 "..." 추가
    snippet = text[:max_length]
    last_space = snippet.rfind(' ')
    return snippet[:last_space] + "..." if last_space > 0 else snippet + "..."

# --- 관련도 점수 계산 함수 (키워드 기반) ---
# 실제 키워드와 가중치는 프로젝트의 상세 요구사항에 맞게 정의해야 합니다.
# 이 KEYWORD_CONFIG는 이전 답변에서 제공된 상세 버전을 사용하거나, 직접 정의해야 합니다.
KEYWORD_CONFIG = {
    "direct_combat": {"keywords": ["war", "battle", "invasion", "airstrike", "shelling", "offensive", "fighting", "combat"], "weight": 3.0, "ner_tags": ["EVENT", "NORP", "GPE"]},
    "military_ops": {"keywords": ["military", "troops", "forces", "deployment", "mobilization", "defense", "weapon"], "weight": 2.0, "ner_tags": ["ORG", "NORP"]},
    "casualties_impact": {"keywords": ["casualties", "killed", "wounded", "refugees", "displacement", "humanitarian crisis", "civilians"], "weight": 2.5, "ner_tags": ["PERSON", "GPE"]},
    "diplomacy_tension": {"keywords": ["ceasefire", "negotiation", "sanctions", "escalation", "tensions", "conflict resolution", "diplomacy"], "weight": 1.5, "ner_tags": ["EVENT", "GPE", "ORG"]},
    "geopolitical_context": {"keywords": ["geopolitics", "border dispute", "territory", "sovereignty", "insurgency", "uprising"], "weight": 1.0, "ner_tags": ["LOC", "GPE"]},
}
NEGATIVE_KEYWORDS = {"peace talks": -1.0, "peace agreement": -2.0, "sports match": -3.0, "war on drugs": -2.0, "trade war": -2.0, "historical war": -1.5}
TITLE_MULTIPLIER = 1.5

def calculate_relevance_score(title_doc, body_doc, keyword_config, negative_keywords, title_multiplier):
    if not NLP_EN: return 0.0
    score = 0.0
    
    # 텍스트에서 lemma 추출 (불용어, 구두점, 숫자 아닌 것 제외)
    def get_lemmas(doc):
        return [token.lemma_.lower() for token in doc if not token.is_stop and not token.is_punct and token.is_alpha]

    title_lemmas = get_lemmas(title_doc)
    body_lemmas = get_lemmas(body_doc)

    # 키워드 점수 계산
    for group_name, group_data in keyword_config.items():
        group_score = 0
        for keyword in group_data["keywords"]:
            # 제목에서 키워드 찾기 (부분 일치도 가능하게)
            if any(keyword in lemma_seq for lemma_seq in [" ".join(title_lemmas[i:i+len(keyword.split())]) for i in range(len(title_lemmas))]):
                group_score += group_data["weight"] * title_multiplier
            # 본문에서 키워드 찾기
            if any(keyword in lemma_seq for lemma_seq in [" ".join(body_lemmas[i:i+len(keyword.split())]) for i in range(len(body_lemmas))]):
                group_score += group_data["weight"]
        score += group_score

    # NER 엔티티 기반 점수 (선택적, 예시)
    for entity in list(title_doc.ents) + list(body_doc.ents):
        for group_data in keyword_config.values():
            if entity.label_ in group_data.get("ner_tags", []):
                score += group_data["weight"] * 0.2 # NER 태그는 가중치 약간 낮게

    # 부정 키워드 페널티
    full_text_lemmas = " " + " ".join(title_lemmas + body_lemmas) + " " # 앞뒤 공백 추가하여 정확한 단어 매칭
    for neg_keyword, penalty in negative_keywords.items():
        if f" {neg_keyword} " in full_text_lemmas:
            score += penalty
            
    return max(0, score) # 점수는 0 이상


# --- 국가 ISO 코드 추출 함수 ---
def extract_main_country_iso(title_doc, body_doc):
    """제목과 본문에서 가장 관련 있는 국가의 ISO 코드를 추출합니다."""
    if not NLP_EN or not COUNTRY_ISO_MAP: return ""
    
    mentioned_country_isos = {} # {'US': 2, 'RU': 1} (ISO 코드: 언급 빈도)

    # NER의 GPE 엔티티와 직접 매칭되는 국가명에서 ISO 코드 추출
    for doc in [title_doc, body_doc]:
        for ent in doc.ents:
            if ent.label_ == "GPE":
                entity_text_lower = ent.text.lower().strip()
                if entity_text_lower in COUNTRY_ISO_MAP:
                    iso = COUNTRY_ISO_MAP[entity_text_lower]
                    mentioned_country_isos[iso] = mentioned_country_isos.get(iso, 0) + 1
                else: # 직접 매칭 안될 시, 더 넓은 국가명 세트에서 부분 포함 확인 (느릴 수 있음)
                    for country_name_variant in ALL_COUNTRY_NAMES_LOWER:
                        if country_name_variant in entity_text_lower or entity_text_lower in country_name_variant:
                            iso = COUNTRY_ISO_MAP.get(country_name_variant)
                            if iso:
                                mentioned_country_isos[iso] = mentioned_country_isos.get(iso, 0) + 1
                                break # 하나의 GPE에 대해 하나의 ISO 매칭

    # 빈도수가 가장 높은 ISO 코드 반환, 동일 빈도 시 알파벳 순
    if mentioned_country_isos:
        return sorted(mentioned_country_isos.items(), key=lambda item: (-item[1], item[0]))[0][0]
    
    return ""


# --- 데이터 전처리 및 필터링 주 함수 ---
def preprocess_and_filter_data(input_csv_path="combined_crawled_news.csv", output_csv_path=CLEANED_NLP_NEWS_CSV_DEFAULT):
    print(f"\nStarting preprocessing for '{input_csv_path}' -> '{output_csv_path}'...")
    if not NLP_EN:
        print("spaCy NLP model not loaded. Preprocessing cannot proceed effectively.")
        # 빈 파일이라도 생성
        pd.DataFrame(columns=['Title', 'Published Date', 'URL', 'Body_Snippet', 'Relevance_Score', 'Image_URL', 'Country_ISO_Code', 'Full_Body']).to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        return

    try:
        # 입력 CSV 컬럼명은 google_news_crawler.py의 출력 컬럼명과 일치해야 함:
        # "title", "authors", "published_date", "body", "image_url", "keywords", "summary", "url"
        df = pd.read_csv(input_csv_path, encoding='utf-8-sig', keep_default_na=False, na_values=['', '#N/A', '#N/A N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN', '-nan', '1.#IND', '1.#QNAN', '<NA>', 'N/A', 'NULL', 'NaN', 'n/a', 'nan', 'null'])
        if df.empty:
            print(f"Warning: Input CSV '{input_csv_path}' is empty.")
            pd.DataFrame(columns=['Title', 'Published Date', 'URL', 'Body_Snippet', 'Relevance_Score', 'Image_URL', 'Country_ISO_Code', 'Full_Body']).to_csv(output_csv_path, index=False, encoding='utf-8-sig')
            return
    except FileNotFoundError:
        print(f"Error: Input CSV '{input_csv_path}' not found."); return
    except pd.errors.EmptyDataError:
        print(f"Warning: Input CSV '{input_csv_path}' is empty (EmptyDataError).")
        pd.DataFrame(columns=['Title', 'Published Date', 'URL', 'Body_Snippet', 'Relevance_Score', 'Image_URL', 'Country_ISO_Code', 'Full_Body']).to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        return

    processed_articles = []
    unique_urls = set()

    # 입력 DataFrame 컬럼명 소문자 변환 및 공백 제거 (일관성 위해)
    df.columns = [col.lower().replace(' ', '_') for col in df.columns]
    # 필요한 컬럼 존재 확인
    required_input_cols = ['title', 'body', 'url']
    if not all(col in df.columns for col in required_input_cols):
        print(f"Error: Input CSV must contain columns: {', '.join(required_input_cols)}")
        return

    for index, row in df.iterrows():
        url = str(row.get('url', '')).strip()
        if not url or url in unique_urls:
            continue

        title_raw = str(row.get('title', ''))
        body_raw = str(row.get('body', '')) # google_news_crawler가 newspaper3k의 article.text를 body로 저장
        
        # published_date는 google_news_crawler가 '%Y-%m-%d %H:%M:%S' 또는 빈 문자열로 저장
        published_date_raw = str(row.get('published_date', '')) 
        image_url = str(row.get('image_url', '')).strip()

        title_clean = clean_html_text(title_raw)
        body_clean = clean_html_text(body_raw)

        if not title_clean or len(body_clean) < MIN_TEXT_LENGTH_FOR_SCORING:
            continue

        title_doc = NLP_EN(title_clean[:NLP_EN.max_length]) # 길이 제한
        body_doc = NLP_EN(body_clean[:NLP_EN.max_length])  # 길이 제한

        relevance_score = calculate_relevance_score(
            title_doc, body_doc, KEYWORD_CONFIG, NEGATIVE_KEYWORDS, TITLE_MULTIPLIER
        )

        if relevance_score >= RELEVANCE_THRESHOLD:
            iso_date = normalize_iso_date(published_date_raw)
            snippet = create_text_snippet(body_clean)
            country_iso = extract_main_country_iso(title_doc, body_doc)

            processed_articles.append({
                'Title': title_clean,
                'Published Date': iso_date, # YYYY-MM-DD 형식 또는 None
                'URL': url,
                'Body_Snippet': snippet,
                'Relevance_Score': round(relevance_score, 2),
                'Image_URL': image_url if image_url and image_url.lower() != 'nan' else "",
                'Country_ISO_Code': country_iso,
                'Full_Body': body_clean # 전체 본문 (선택적 저장)
            })
            unique_urls.add(url)
    
    output_df_columns = ['Title', 'Published Date', 'URL', 'Body_Snippet', 'Relevance_Score', 'Image_URL', 'Country_ISO_Code', 'Full_Body']
    if processed_articles:
        output_df = pd.DataFrame(processed_articles)
        # 모든 컬럼이 있는지 확인하고, 없다면 빈 값으로 채움
        for col in output_df_columns:
            if col not in output_df.columns:
                output_df[col] = None # 또는 ""
        output_df = output_df[output_df_columns].fillna("") # NaN을 빈 문자열로
        output_df.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        print(f"Preprocessing finished. {len(output_df)} relevant articles saved to '{output_csv_path}'.")
    else:
        pd.DataFrame(columns=output_df_columns).to_csv(output_csv_path, index=False, encoding='utf-8-sig')
        print(f"No articles met the relevance threshold. Empty file '{output_csv_path}' saved.")

if __name__ == "__main__":
    # 이 파일을 직접 실행할 때 사용할 기본 경로 설정
    # run_pipeline.py에서 생성된 COMBINED_CRAWLED_NEWS_CSV를 입력으로 사용
    default_input = "combined_crawled_news.csv" 
    default_output = CLEANED_NLP_NEWS_CSV_DEFAULT
    
    if not NLP_EN:
        print("Cannot run preprocess_data.py directly as spaCy model failed to load.")
    else:
        print(f"Running preprocess_data.py directly: input='{default_input}', output='{default_output}'")
        if not os.path.exists(GEOJSON_FILE_PATH):
             print(f"Warning: GeoJSON file for country mapping ('{GEOJSON_FILE_PATH}') not found. Country extraction may be limited.")
        preprocess_and_filter_data(default_input, default_output)
        
