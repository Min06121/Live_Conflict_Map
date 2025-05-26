import pandas as pd
import json # JSON 처리를 위한 모듈

def convert_csv_to_json(csv_filepath, json_filepath):
    """
    정제된 CSV 파일을 읽어 웹페이지 뉴스 피드에 적합한 JSON 형태로 변환하여 저장합니다.
    """
    print(f"'{csv_filepath}' 파일을 읽어 JSON으로 변환을 시작합니다...")
    try:
        df = pd.read_csv(csv_filepath, encoding='utf-8-sig')
        print(f"CSV 파일 읽기 완료. 총 {len(df)}개의 뉴스 데이터.")

        news_data_for_json = []
        for index, row in df.iterrows():
            # HTML 파일의 realNewsData 구조와 유사하게 만듭니다.
            # 'Published Date Normalized'가 YYYY-MM-DD 형식이므로, 시간 정보가 필요하면 T00:00:00Z 등을 추가할 수 있으나,
            # 현재 HTML의 날짜 필터는 YYYY-MM-DD 부분만 사용하므로 그대로 사용해도 괜찮습니다.
            news_item = {
                "id": f"crawled_news_{index}", # 고유 ID 생성
                "time": str(row.get('Published Date Normalized', '')), # YYYY-MM-DD 형식
                "title": str(row.get('Title', '제목 없음')),
                "link": str(row.get('URL', '')),
                "description": str(row.get('Body Snippet Final', '내용 없음')),
                "location": "" # 위치 정보는 현재 없으므로 빈 문자열 또는 기본값
                               # (나중에 검색어나 다른 방법으로 추론하여 채울 수 있습니다)
            }
            news_data_for_json.append(news_item)
        
        print(f"JSON으로 변환할 뉴스 항목 {len(news_data_for_json)}개 준비 완료.")

        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(news_data_for_json, f, ensure_ascii=False, indent=4)
        
        print(f"데이터를 '{json_filepath}' 파일로 성공적으로 저장했습니다.")

    except FileNotFoundError:
        print(f"오류: 입력 CSV 파일 '{csv_filepath}'을 찾을 수 없습니다. 경로를 확인해주세요.")
    except Exception as e:
        print(f"JSON 변환 중 오류가 발생했습니다: {e}")

# --- 메인 실행 부분 ---
if __name__ == "__main__":
    input_csv = "cleaned_news_stage4.csv"  # 이전 단계에서 생성된 최종 정제 CSV 파일
    output_json = "news_data.json"         # 웹페이지에서 사용할 JSON 파일 이름
    
    # 이 JSON 파일은 war_map8.html 파일과 같은 위치에 있거나,
    # war_map8.html에서 접근 가능한 경로에 있어야 합니다.
    # news_crawler_project 폴더 안에 생성될 것입니다.
    
    convert_csv_to_json(input_csv, output_json)
    