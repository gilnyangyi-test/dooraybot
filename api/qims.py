import os
import json  # 💡 문제 1 해결: json 모듈 임포트 추가
import httpx
from fastapi import APIRouter, Request
from api.common import pack

router = APIRouter()

@router.post("/dooray/qims")
async def qims_report_command(req: Request):
    github_token = os.environ.get("GITHUB_TOKEN")
    gist_id = os.environ.get("GIST_ID")

    if not github_token or not gist_id:
        return pack({
            "responseType": "ephemeral",
            "text": "⚠️ GITHUB_TOKEN 또는 GIST_ID 환경변수가 설정되지 않았습니다."
        })

    url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        # 비동기로 GitHub Gist 데이터 가져오기
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            gist_data = response.json()
            
        # Gist 내의 'qims_data.json' 파일 내용 파싱
        content_str = gist_data["files"]["qims_data.json"]["content"]
        data = json.loads(content_str)
            
    except Exception as e:
        return pack({
            "responseType": "inChannel",
            "text": f"⚠️ GitHub에서 QIMS 데이터를 가져오지 못했습니다.\n(상세 오류: {str(e)})"
        })

    # 💡 문제 2 해결: 들여쓰기를 함수 내부에 맞게 정확히 정렬
    updated_at = data.get('updated_at', '알 수 없음')
    weekly_cnt = int(data.get('weekly_cnt', 0))
    yearly_cnt = int(data.get('yearly_cnt', 0))
    qmark_weekly_cnt = int(data.get('qmark_weekly_cnt', 0))
    qmark_yearly_cnt = int(data.get('qmark_yearly_cnt', 0))

    # 두레이 메시지로 출력
    return pack({
        "responseType": "inChannel",
        "text": (
            f"📊 [QIMS] 주간 현황 리포트\n\n"
            f"최종 동기화 시간: {updated_at}\n"
            f"주간 정적분석 건수 (최근 7일) : {weekly_cnt:,}건\n"
            f"올해 누적 정적분석 건수 : {yearly_cnt:,}건\n"
            f"주간 Q-mark 인증 건수 (최근 7일) : {qmark_weekly_cnt:,}건\n"
            f"올해 누적 Q-mark 인증 건수 : {qmark_yearly_cnt:,}건"
        )
    })
