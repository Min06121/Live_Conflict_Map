import schedule
import time

def job():
    print(f"작업 실행 중입니다! 현재 시간: {time.ctime()}")

# 1. 스케줄 등록: 5초마다 job 함수를 실행하도록 설정
schedule.every(5).seconds.do(job)

# 2. 다른 스케줄 예시 (주석 처리됨 - 필요시 해제해서 테스트 가능)
# schedule.every(1).minutes.do(job) # 1분마다 실행
# schedule.every().hour.do(job) # 매시간 실행
# schedule.every().day.at("10:30").do(job) # 매일 10:30에 실행
# schedule.every().monday.do(job) # 매주 월요일에 실행
# schedule.every().wednesday.at("13:15").do(job) # 매주 수요일 13:15에 실행

print("스케줄러 시작... (5초마다 메시지가 출력됩니다. 중지하려면 Ctrl+C를 누르세요)")

# 3. 스케줄 실행 루프
count = 0
while True:
    schedule.run_pending() # 등록된 스케줄 중에 실행할 시간이 된 작업이 있는지 확인하고 실행
    time.sleep(1)          # 1초 대기 (CPU 사용량을 줄이기 위해)
    
    # 테스트를 위해 30초(6번 실행) 후에 자동으로 멈추도록 추가 (선택 사항)
    # count += 1
    # if count > 30: # 약 30초간 실행
    #     print("테스트 스케줄러 자동 종료.")
    #     break