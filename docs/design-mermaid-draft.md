sequenceDiagram
    participant User as 관리자 (Telegram)
    participant Bot as SUTT-Bot (Container)
    participant Upbit as 업비트 API
    participant DB as state.json (Persistence)

    Note over User, Bot: [1단계: 주문 접수 및 보안 검증]
    User->>Bot: /grid [코인, 시작가, 끝가, 분할수, 총액]
    activate Bot
    Bot->>Bot: Chat ID 보안 검증 (Authorized?)
    
    alt 미승인 사용자
        Bot-->>User: 🚨 접근 차단 메시지
    else 승인된 관리자
        Note over Bot, Upbit: [2단계: 거미줄 분할 주문 실행]
        Bot->>Bot: 호가별 분할 주문서 계산
        
        rect rgb(240, 240, 240)
            loop 분할수(N) 만큼 반복
                Bot->>Upbit: 지정가 매수 요청 (buy_limit_order)
                Upbit-->>Bot: 접수 완료 (UUID 반환)
                Note right of Bot: 0.2초 간격 (Rate Limit 준수)
            end
        end

        Bot->>DB: 모든 UUID 및 주문 정보 저장
        Bot-->>User: ✅ N건 분할 주문 전송 완료 알림
    end
    deactivate Bot

    Note over Bot, Upbit: [3단계: 실시간 체결 모니터링 (Background)]
    loop 무한 루프 (5초 주기)
        activate Bot
        Bot->>DB: 추적 중인 주문 목록 로드
        
        Note over Bot, Upbit: API 최적화: Ticker별 미체결 목록 일괄 조회
        Bot->>Upbit: 미체결 주문 목록 조회 (state='wait')
        Upbit-->>Bot: 현재 대기 중인 UUID 목록 반환
        
        loop 추적 중인 주문별 대조
            alt UUID가 미체결 목록에서 사라짐
                Bot->>Upbit: 해당 UUID 단건 상세 조회 (get_order)
                Upbit-->>Bot: 최종 상태 반환 (done / cancel)
                
                alt state == 'done' (체결 완료)
                    Bot-->>User: 🎯 🎉 체결 성공 상세 알림 푸시
                else state == 'cancel' (사용자 취소)
                    Note over Bot: 로그 기록 및 추적 제외
                end
                
                Bot->>DB: 추적 목록에서 해당 주문 제거 (상태 갱신)
            else UUID가 여전히 미체결 목록에 존재
                Note over Bot: 계속 추적 유지
            end
        end
        deactivate Bot
    end