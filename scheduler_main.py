import schedule
import time
import subprocess
import sys
import os

PIPELINE_SCRIPT_NAME = "run_pipeline.py"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PIPELINE_SCRIPT_PATH = os.path.join(BASE_DIR, PIPELINE_SCRIPT_NAME)

def run_the_pipeline():
    """run_pipeline.py 스크립트를 실행하는 함수"""
    current_time_start = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print(f"[{current_time_start}] Attempting to run pipeline: '{PIPELINE_SCRIPT_NAME}'...")
    log_entries = [f"[{current_time_start}] Pipeline run initiated."]
    success = False
    try:
        result = subprocess.run(
            [sys.executable, PIPELINE_SCRIPT_PATH], 
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=3600 # 파이프라인 전체 실행 시간 제한 (예: 1시간)
        )
        current_time_done = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entries.append(f"[{current_time_done}] Pipeline '{PIPELINE_SCRIPT_NAME}' executed successfully.")
        if result.stdout.strip():
            log_entries.append(f"Pipeline STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip():
            log_entries.append(f"Pipeline STDERR (Warning/Info):\n{result.stderr.strip()}")
        success = True
        
    except FileNotFoundError:
        current_time_err = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entries.append(f"[{current_time_err}] Error: Script '{PIPELINE_SCRIPT_PATH}' not found.")
    except subprocess.CalledProcessError as e:
        current_time_err = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entries.append(f"[{current_time_err}] Error: Script '{PIPELINE_SCRIPT_NAME}' failed with return code {e.returncode}.")
        if e.stdout: log_entries.append(f"Stdout from failed script:\n{e.stdout.strip()}")
        if e.stderr: log_entries.append(f"Stderr from failed script:\n{e.stderr.strip()}")
    except subprocess.TimeoutExpired:
        current_time_err = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entries.append(f"[{current_time_err}] Error: Pipeline '{PIPELINE_SCRIPT_NAME}' timed out after 1 hour.")
    except Exception as e:
        current_time_err = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_entries.append(f"[{current_time_err}] An unknown error occurred while running '{PIPELINE_SCRIPT_NAME}': {e}")
    finally:
        log_output = "\n".join(log_entries)
        print(log_output) # 콘솔에도 전체 로그 출력
        # 간단한 파일 로깅 (매 실행 시 덮어쓰기, 필요시 추가 모드 'a'로 변경)
        with open("scheduler_pipeline_log.txt", "a", encoding="utf-8") as log_file: # 추가 모드로 변경
            log_file.write(log_output + "\n" + "-"*70 + "\n")
        
        if success:
             print(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Pipeline run logged.")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Pipeline run failed. Check scheduler_pipeline_log.txt for details.")
        print("-" * 70)


# --- 스케줄 등록 ---
# 매일 새벽 3시에 run_the_pipeline 함수를 실행하도록 설정 (예시)
schedule.every().day.at("03:00").do(run_the_pipeline)

# # 테스트를 위한 다른 주기 예시:
# schedule.every(5).minutes.do(run_the_pipeline) # 5분마다 (파이프라인 실행 시간보다 길게)
# schedule.every(30).seconds.do(run_the_pipeline) # 매우 짧은 테스트용 (권장하지 않음)

start_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
print(f"[{start_time_str}] Scheduler started. Pipeline '{PIPELINE_SCRIPT_NAME}' is scheduled according to defined jobs.")
print(f"Next scheduled run for daily job at 03:00 is: {schedule.next_run()}") # 다음 실행 시간 표시
print("This terminal window must remain open for the scheduler to work. Press Ctrl+C to stop.")
print("-" * 70)

# # 스케줄러 시작 시 즉시 한번 실행하고 싶다면 아래 주석 해제:
# print("Running pipeline once immediately upon scheduler start...")
# run_the_pipeline()
# print("-" * 70)

# --- 스케줄 실행 루프 ---
try:
    while True:
        schedule.run_pending()
        time.sleep(1)
except KeyboardInterrupt:
    print("\nScheduler stopped by user (Ctrl+C).")
except Exception as e:
    print(f"An unexpected error occurred in the scheduler loop: {e}")
finally:
    print("Scheduler finished.")
    


