from fastapi import FastAPI

from api.hi import router as hi_router
from api.coffee import router as coffee_router
from api.vacation import router as vacation_router
# 새로 추가된 qims 라우터 임포트
from api.qims import router as qims_router
from api.meeting import router as meeting_router
from api.test import router as test_router

app = FastAPI(title="Dooray Bot")

app.include_router(hi_router)
app.include_router(coffee_router)
# vacation.py에도 동일한 /dooray/test 경로가 있어 전용 test 라우터를 먼저 등록한다.
app.include_router(test_router)
app.include_router(vacation_router)
# 새로 추가된 qims 라우터를 앱에 등록
app.include_router(qims_router)
app.include_router(meeting_router)

@app.get("/")
async def root():
    return {"message": "Dooray bot API is running"}
