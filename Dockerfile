FROM python:3.11-slim

# 타임존 서울 설정 (거래소 API 시각 동기화 필수)
ENV TZ=Asia/Seoul
RUN apt-get update && apt-get install -y tzdata curl gnupg \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Node.js 및 upbit CLI 설치 (업비트 연동용)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @upbit-official/upbit-cli \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 라이브러리 설치 (캐시 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ ./src/

# 빌드 메타데이터 기록 (이미지 생성 시각 자동 캡처)
ARG VERSION="dev"
ARG GIT_SHA="unknown"
RUN BUILD_DATE=$(date +"%Y-%m-%d %H:%M KST") && \
    printf 'BUILD_DATE = "%s"\nVERSION = "%s"\nGIT_SHA = "%s"\n' \
    "$BUILD_DATE" "$VERSION" "$GIT_SHA" > src/build_info.py

# 도커 로그 실시간 확인 설정
ENV PYTHONUNBUFFERED=1

CMD ["python", "src/main.py"]
