# Copy APP

**언어:** 한국어 · [모든 언어](../../README.md#languages) · [English](../../README.md)

Copy APP은 탈옥한 iPhone에 설치된 앱의 패키지, UI, 샌드박스 및 실행 중 동작의 증거를 수집합니다. 출처가 연결된 분석 보고서를 만들고, 선택한 기능을 독립적인 iOS 앱으로 구현해 실제 기기에서 비교하도록 돕습니다.

## 작동 방식

Coding Agent가 Mac의 Copy APP CLI를 실행합니다. OpenSSH, Frida, iOS MCP 또는 선택 사항인 iCTRL을 통해 지정한 iPhone에서 증거를 모읍니다. 필요할 때 Mac의 Ghidra나 Hopper로 네이티브 코드를 분석합니다. 검토된 보고서와 `feature-spec.json`을 바탕으로 새 앱을 만든 뒤, 같은 iPhone에서 원본과 새 앱의 동작 및 스크린샷을 비교합니다. [아키텍처 그림과 전체 설치 안내](../../README.md#how-it-works)는 영어 문서를 참조하세요.

## 빠른 시작

Mac에 Python 3.9 이상을 준비하고 탈옥한 iPhone을 USB로 연결하여 신뢰한 다음 실행하세요.

```sh
git clone https://github.com/everettjf/copyapp.git
cd copyapp
sh scripts/bootstrap-macos.sh
.venv/bin/copyapp onboard
```

먼저 [USB 조사 절차](../../README.md#install-and-run-your-first-survey)를 완료하세요. 심층 분석에는 기기의 SSH, Frida 및 UI 서비스가 추가로 필요합니다.

## 원칙과 기여

해석 전에 증거를 남기고 모르는 부분을 명시합니다. 선택한 흐름의 검증이 앱 전체의 동등성을 뜻하지는 않습니다. 재현 가능한 버그, 테스트, UI 스크립트, 번역 기여를 환영합니다. IPA, 자격 증명, 기기의 원본 데이터를 커밋하지 마세요. [기여 안내](../../CONTRIBUTING.md)를 읽어 주세요.

현재 검증된 기기는 iOS 16.1.1의 iPhone XR입니다. iOS 17과 26은 아직 검증하지 않았습니다. 문서 언어는 CLI나 보고서의 언어를 바꾸지 않습니다.
