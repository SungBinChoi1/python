# 설치 및 실행 가이드 (Miniconda + PyCharm)

---

## 0. 준비 파일

같은 폴더 안에 아래 파일 있어야함.

```text
careerly.py
itunion.py
okky.py
requirements.txt
```

---

## 1. Miniconda 설치

다운로드:  
https://www.anaconda.com/download/success

Windows 64-bit Installer 설치

### 설치 옵션

- Installation Type: Just Me
- Location: 기본값 유지
- Add to PATH: 체크 해제

일반 Python 별도 설치 불필요  
Miniconda에 Python 포함

---

## 2. PyCharm 설치

다운로드:  
https://www.jetbrains.com/ko-kr/pycharm/download/?section=windows

설치 참고:  
https://dolpali.tistory.com/345

위 링크에서 **2. 파이참 Community 버전 설치하기 까지만 참고**  
3번 이후 아나콘다 설치 부분은 해당 없음

---

## 3. 프로젝트 열기

1. PyCharm 실행  
2. Open 클릭  
3. `.py` 파일 있는 폴더 선택  

좌측에 파일 목록 보이면 정상

---

## 4. 인터프리터 설정

### 설정 열기

```bash
Ctrl + Alt + S
```

### Python Interpreter 이동

```bash
Project → Python Interpreter
```

### 인터프리터 추가

```bash
톱니바퀴 → Add Interpreter
Conda Environment 선택
```

### New Environment 생성

- Python Version: 3.11  
- Environment Name: crawler  
- Location 기본값  

완료 후 상단에

```text
Python 3.11 (crawler)
```

표시되면 정상

---

## 5. 패키지 설치

터미널 열기

```bash
Alt + F12
```

설치

```bash
pip install -r requirements.txt
```

playwright 오류 시

```bash
playwright install chromium
```

---

## 6. 실행 방법

### PyCharm에서 실행

```bash
Ctrl + Shift + F10
```

또는 우클릭 → Run

### 터미널에서 실행

```bash
python itunion.py
python okky.py
python careerly.py
```

---

## 7. 실행 시 콘솔 출력 예시

### itunion.py

```text
=== IT노조 크롤러 시작 ===
시작일 입력 (YYYY-MM-DD): 2026-01-01
종료일 입력 (YYYY-MM-DD): 2026-01-31
페이지 1 수집 중...
...
총 124건 저장
파일 저장: itunion_20260101_20260131_20260226_0930.csv
```

---

### okky.py

```text
=== OKKY 크롤러 시작 ===
시작일 입력 (YYYY-MM-DD): 2026-01-01
종료일 입력 (YYYY-MM-DD): 2026-01-31
...
총 238건 저장 완료
파일 저장: okky_20260101_20260131_20260226_0942.csv
```

---

### careerly.py
(카카오톡 로그인 기준)
```text
=== Careerly 크롤러 시작 ===
이메일 입력:
비밀번호 입력:
로그인 성공
Posts 수집 중...
QnA 수집 중...
총 156건 저장 완료
파일 저장: careerly_20260101_20260131_20260226_0958.csv
```

---

## 8. 결과 파일 예시

실행 폴더에 아래 형태로 생성됨

```text
itunion_YYYYMMDD_YYYYMMDD_YYYYMMDD_HHMM.csv
okky_YYYYMMDD_YYYYMMDD_YYYYMMDD_HHMM.csv
careerly_YYYYMMDD_YYYYMMDD_YYYYMMDD_HHMM.csv
```

엑셀 컬럼 예시

```text
title | author | date | url | content
```

---

## 9. 주의사항

- System Interpreter 사용 금지
- Python 중복 설치 시 환경 꼬일 수 있음
- 인터프리터 연결 확인 필요

확인

```bash
where python
```

정상 경로 예시

```text
...miniconda3\envs\crawler\python.exe
```
