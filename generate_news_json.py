import pandas as pd
import json # JSON 처리를 위한 모듈
import os

def create_news_json_file(csv_filepath, json_output_filepath):
    """
    정제된 CSV 파일을 읽어 뉴스 데이터를 JSON 파일로 저장합니다.
    웹페이지에서 사용할 컬럼 이름으로 매핑합니다.
    """
    print(f"Reading '{csv_filepath}' to generate JSON data file for the webpage...")
    news_data_for_json = [] # JSON으로 변환할 데이터를 담을 리스트

    try:
        if not os.path.exists(csv_filepath) or os.path.getsize(csv_filepath) == 0:
            print(f"Warning: Input CSV file '{csv_filepath}' is missing or empty.")
            # 빈 JSON 배열을 생성합니다.
        else:
            # preprocess_data.py에서 최종 저장 시 사용한 컬럼 이름들을 기준으로 읽습니다.
            # (예: 'Title', 'Published Date', 'URL', 'Body')
            df = pd.read_csv(csv_filepath, encoding='utf-8-sig', keep_default_na=False, na_values=[''])
            
            # NaN 값을 빈 문자열로 일괄 처리하고, 웹페이지에서 사용할 주요 컬럼명에 대한 기본값 설정
            expected_columns_for_web = {
                'Title': 'Untitled News',
                'Published Date': '', 
                'URL': '#',
                'Body': 'No description available.'
            }
            for col_web, default_value in expected_columns_for_web.items():
                if col_web in df.columns:
                    df[col_web] = df[col_web].fillna(default_value).astype(str)
                else: # CSV에 해당 컬럼이 없는 경우, 기본값으로 새 컬럼 생성
                    print(f"Warning: Column '{col_web}' not found in '{csv_filepath}'. Using default.")
                    df[col_web] = default_value
            
            print(f"CSV file read successfully. Total {len(df)} news items.")

            news_data_for_json = []
            for index, row in df.iterrows():
                # HTML 파일의 JavaScript에서 사용할 키 이름으로 매핑
                news_item = {
                    "id": f"final_nlp_news_en_{index}", # 고유 ID 업데이트
                    "time": row.get('Published Date', ''), # 'Published Date' 컬럼 사용 (YYYY-MM-DD 형식이어야 함)
                    "title": row.get('Title', 'Untitled News'),
                    "link": row.get('URL', '#'),
                    "description": row.get('Body', 'No description available.'), # 'Body' 컬럼 사용
                    "location": "" # 위치 정보는 현재 없으므로 빈 문자열
                }
                news_data_for_json.append(news_item)
        
        print(f"Prepared {len(news_data_for_json)} news items for JSON file.")

        # JSON 파일로 저장 (UTF-8 인코딩, indent로 가독성 확보)
        with open(json_output_filepath, 'w', encoding='utf-8') as f:
            json.dump(news_data_for_json, f, ensure_ascii=False, indent=4)
        
        print(f"Successfully saved JSON file with news data to '{json_output_filepath}'.")

    except FileNotFoundError: 
        print(f"Error: Input CSV file '{csv_filepath}' not found. Please check the path.")
        # 입력 CSV 파일이 없을 경우 빈 JSON 배열을 포함하는 파일 생성
        with open(json_output_filepath, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)
        print(f"Created an empty '{json_output_filepath}' due to missing input CSV.")
    except Exception as e:
        print(f"An error occurred during JSON file generation: {e}")
        try:
            # 그 외 예외 발생 시에도 빈 JSON 배열을 포함하는 파일 생성 시도
            with open(json_output_filepath, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=4)
            print(f"Created an empty '{json_output_filepath}' due to an error.")
        except Exception as e_fallback:
            print(f"Failed to create even an empty '{json_output_filepath}': {e_fallback}")

# --- 메인 실행 부분 (이 파일을 직접 실행할 경우) ---
if __name__ == "__main__":
    # 이 스크립트가 직접 실행될 때 사용할 기본 경로 설정
    # preprocess_data.py의 최종 NLP 처리된 영어 뉴스 CSV 파일 이름
    default_input_csv = "cleaned_nlp_english_news.csv" 
    # 웹페이지에서 사용할 JSON 파일 이름
    default_output_json_file = "news_data.json" 
    
    print(f"Running {__file__} directly for testing purposes.")
    print(f"Input CSV (default): {default_input_csv}")
    print(f"Output JSON (default): {default_output_json_file}")
    
    create_news_json_file(default_input_csv, default_output_json_file)
    
    