// -*- coding: utf-8 -*-
import { useEffect } from 'react'

/**
 * Realtime SSE Stream 구독 훅
 * 백엔드로부터 'refresh' 이벤트가 전송되면 전달받은 콜백 함수를 실행합니다.
 */
export function useRealtime(onRefresh: () => void) {
  useEffect(() => {
    const eventSource = new EventSource('/api/realtime/stream')

    eventSource.onmessage = (event) => {
      if (event.data === 'refresh') {
        onRefresh()
      }
    }

    eventSource.onerror = () => {
      // EventSource가 자동으로 재접속을 시도합니다.
    }

    return () => {
      eventSource.close()
    }
  }, [onRefresh])
}
