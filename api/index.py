from fastapi import FastAPI

from api.hi import router as hi_router
from api.coffee import router as coffee_router
from api.vacation import router as vacation_router
# 새로 추가된 qims 라우터 임포트
from api.qims import router as qims_router

app = FastAPI(title="Dooray Bot")

app.include_router(hi_router)
app.include_router(coffee_router)
app.include_router(vacation_router)
# 새로 추가된 qims 라우터를 앱에 등록
app.include_router(qims_router)

@app.get("/")
async def root():
    return {"message": "Dooray bot API is running"}
