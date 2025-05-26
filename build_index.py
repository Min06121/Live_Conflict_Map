import pandas as pd
import re # 정규표현식 모듈

def tokenize_text(text):
    """
    텍스트를 토큰화하는 함수 (영어에 더 적합하게 수정).
    소문자로 변환, 특수문자(알파벳, 숫자, 공백 유지) 제거, 공백 기준 분리.
    """
    if not isinstance(text, str) or not text.strip() or text.lower() == 'nan':
        return []
    
    text = text.lower() # 모두 소문자로
    # 영어, 숫자, 공백을 제외한 대부분의 특수문자 제거 (하이픈 등은 유지 가능하게 조정 가능)
    text = re.sub(r'[^a-z0-9\s]', '', text) 
    tokens = text.split()
    return [token for token in tokens if token and len(token) > 1] # 한 글자짜리 토큰도 일단 제외 (선택적)

def search_from_index(query_text, index, documents_df):
    """
    주어진 검색어로 인버티드 인덱스에서 문서를 검색합니다. (간단한 OR 검색)
    """
    query_tokens = tokenize_text(query_text)
    if not query_tokens:
        print("No valid tokens in query.")
        return []

    print(f"\nSearching for query '{query_text}' (tokens: {query_tokens})...")

    result_doc_ids = set()
    found_tokens = []
    for token in query_tokens:
        if token in index:
            found_tokens.append(token)
            if not result_doc_ids: # 첫 번째 일치하는 토큰
                result_doc_ids = index[token].copy()
            else: # 이후 토큰들은 합집합 (OR 검색)
                result_doc_ids.update(index[token])
    
    if not found_tokens: # 어떤 검색어 토큰도 인덱스에 없는 경우
        print(f"None of the query tokens {query_tokens} were found in the index.")
        return []
    
    if not result_doc_ids: # 토큰은 있었으나 문서 ID 집합이 비는 경우 (이론상 잘 없음)
        print("Tokens found in index, but no matching document IDs.")
        return []

    # 검색된 문서 ID를 기반으로 원본 DataFrame에서 해당 문서 정보 가져오기
    # 컬럼 이름은 preprocess_data.py의 최종 출력 컬럼명과 일치해야 함
    results_df = documents_df.loc[list(result_doc_ids)].copy()
    
    # 반환할 컬럼 목록 (정제된 최종 컬럼명 사용)
    # generate_news_js.py 에서 HTML로 넘겨주는 키 이름들과 유사하게 맞춤
    # (Title_Final -> title, Published_Date_Normalized -> time, URL -> link)
    # 여기서는 CSV의 컬럼명 그대로 사용하고, 출력 시 가공
    return results_df[['Title_Final', 'URL', 'Published_Date_Normalized']].to_dict('records')


# --- 메인 실행 부분 ---
if __name__ == "__main__":
    # preprocess_data.py의 최종 영어 뉴스 출력 파일 이름으로 변경합니다.
    input_csv_filename = "cleaned_relevant_english_news.csv" 
    inverted_index = {} 
    documents_df = None 

    print(f"Reading '{input_csv_filename}' to build the index...")
    try:
        # CSV 읽을 때, 비어있는 문자열을 NaN으로 읽지 않도록 na_filter=False 옵션 추가
        # 또는, 결측치를 특정 문자열로 채우려면 df.fillna("", inplace=True) 사용 가능
        documents_df = pd.read_csv(input_csv_filename, encoding='utf-8-sig', keep_default_na=False, na_values=[''])
        # 주요 인덱싱 대상 컬럼들의 NaN 값을 빈 문자열로 일괄 처리
        for col in ['Title_Final', 'Body_Final']: # 정제된 최종 컬럼명 사용
            if col in documents_df.columns:
                documents_df[col] = documents_df[col].fillna("").astype(str)
            else: # 컬럼이 없는 경우 대비
                documents_df[col] = "" # 빈 컬럼으로 추가
        
        print(f"CSV file read successfully. Total {len(documents_df)} documents.")

        # 인덱스 구축: 'Title_Final'과 'Body_Final' 컬럼 사용
        for doc_id, row in documents_df.iterrows():
            title_text = row.get('Title_Final', '')
            body_text = row.get('Body_Final', '')
            
            content_to_index = title_text + " " + body_text
            tokens = tokenize_text(content_to_index)
            
            for token in tokens:
                if token not in inverted_index:
                    inverted_index[token] = set()
                inverted_index[token].add(doc_id)

        print(f"Index created successfully. Total {len(inverted_index)} unique words indexed.")
        
        if not inverted_index:
            print("Warning: The inverted index is empty. No words were indexed. Check CSV content and tokenize_text function.")
        else:
            print("\n--- Sample of Inverted Index (first 5 words) ---")
            sample_count = 0
            for word, doc_ids_set in inverted_index.items():
                print(f"Word '{word}': Document IDs {doc_ids_set}")
                sample_count += 1
                if sample_count >= 5:
                    break
        
        # --- 인덱스 생성 후 검색 테스트 ---
        while True:
            user_search_query = input("\nEnter search query (or press Enter to quit): ")
            if not user_search_query:
                break
            
            search_results = search_from_index(user_search_query, inverted_index, documents_df)
            
            if search_results:
                print(f"\n--- Search Results for '{user_search_query}' ({len(search_results)} items) ---")
                for i, result in enumerate(search_results):
                    # 컬럼 이름은 DataFrame에서 직접 가져온 것 사용
                    print(f"{i+1}. Title: {result.get('Title_Final')}")
                    print(f"   URL: {result.get('URL')}")
                    print(f"   Published Date: {result.get('Published_Date_Normalized', 'N/A')}")
                    print("-" * 20)
            else:
                print("No results found.")
        
        print("\nExiting search program.")

    except FileNotFoundError:
        print(f"Error: Input file '{input_csv_filename}' not found. Please check the path.")
    except pd.errors.EmptyDataError:
        print(f"Error: Input file '{input_csv_filename}' is empty. Cannot build index.")
    except Exception as e:
        print(f"An error occurred: {e}")
        
        