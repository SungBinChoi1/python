# 설치 및 실행 가이드 (Miniconda + PyCharm)

## 0. 준비 파일

같은 폴더에 아래 파일 존재

```text
careerly.py
itunion.py
okky.py
requirements.txt
```

---

## 1. Miniconda 설치

다운로드  
https://www.anaconda.com/download/success

Windows 64-bit Installer 실행

설정

- Installation Type → Just Me
- Location → 기본값
- Add to PATH → 체크 해제

Python 별도 설치하지 않음  
Miniconda Python 사용

---

## 2. PyCharm 설치

다운로드  
https://www.jetbrains.com/ko-kr/pycharm/download/?section=windows

설치 참고  
https://dolpali.tistory.com/345

위 링크에서  
2. 파이참 Community 버전 설치하기 까지만 참고  
3번 이후 아나콘다 설치 부분 사용하지 않음

설치 시 기본 옵션 사용

---

## 3. 프로젝트 열기

PyCharm 실행  
Open 클릭  
.py 파일 있는 폴더 선택  

좌측 파일 목록 표시되면 정상

---

## 4. 인터프리터 설정 (Miniconda 사용)

Ctrl + Alt + S  
Project → Python Interpreter 이동  

톱니바퀴 → Add Interpreter  
Conda Environment 선택  

설정

- Conda 실행 파일 → 자동 인식된 conda.bat 사용  
  예: C:\ProgramData\Miniconda3\condabin\conda.bat
- New environment 선택
- Environment name → crawler
- Python version → 3.11

확인 클릭

<img width="884" height="558" alt="image" src="https://github.com/user-attachments/assets/fe31ac63-8e6a-4567-bbf3-b86f1f8cc92f" />

---

### 인터프리터 경로 확인

생성 후 연결 경로 예시

```
C:\ProgramData\Miniconda3\envs\crawler\python.exe
```

---

### 연결 확인

Alt + F12

```bash
where python
python --version
```

출력 경로가 아래 형식이면 정상

```
...\Miniconda3\envs\crawler\python.exe
```

---

## 5. 패키지 설치

```bash
pip install -r requirements.txt
```

Playwright 사용 시

```bash
playwright install chromium
```

---

## 6. 실행 방법

### PyCharm 실행

```bash
Ctrl + Shift + F10
```

또는 우클릭 → Run

### 터미널 실행

```bash
python itunion.py
python okky.py
python careerly.py
```

---

## 7. 콘솔 출력 예시

### itunion.py

```text
=== IT노조 크롤러 시작 ===
시작일 입력 (YYYY-MM-DD): 2026-01-01
종료일 입력 (YYYY-MM-DD): 2026-01-31
페이지 1 수집 중...
총 124건 저장
파일 저장: itunion_20260101_20260131_20260226_0930.csv
```

### okky.py

```text
=== OKKY 크롤러 시작 ===
시작일 입력 (YYYY-MM-DD): 2026-01-01
종료일 입력 (YYYY-MM-DD): 2026-01-31
총 238건 저장 완료
파일 저장: okky_20260101_20260131_20260226_0942.csv
```

### careerly.py

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

## 8. 결과 파일

생성 파일 형식

```text
itunion_YYYYMMDD_YYYYMMDD_YYYYMMDD_HHMM.csv
okky_YYYYMMDD_YYYYMMDD_YYYYMMDD_HHMM.csv
careerly_YYYYMMDD_YYYYMMDD_YYYYMMDD_HHMM.csv
```

컬럼 구조

```text
title | author | date | url | content
```

---

## 9. 주의사항

- System Interpreter 사용하지 않음
- Python 중복 설치 시 충돌 가능
- 인터프리터 경로 반드시 확인

```bash
where python
```

정상 경로 예시

```
...\miniconda3\envs\crawler\python.exe
```
