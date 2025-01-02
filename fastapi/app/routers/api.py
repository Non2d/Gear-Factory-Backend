from statistics import median
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import select
from db import get_db
from pydantic import BaseModel, Field
from typing import List

from db import Base
from sqlalchemy import Column, Integer, String, Float, DateTime, TEXT, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, selectinload
from datetime import datetime, timedelta, timezone
from log_conf import logger

# 日本時間 (UTC+9)
JST = timezone(timedelta(hours=+9))

# groq
import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(
    api_key=os.getenv("GROQ_API_KEY"),
)

# routers
router = APIRouter()


# db models
class Result(Base):
    __tablename__ = "results"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(JST)
    )  # 本来はUTCで保存すべきだが、日本時間で保存する
    player_name = Column(String(255))
    total_time = Column(Float)
    deaths = Column(Integer)
    total_energy = Column(Float)
    groq_analysis = Column(TEXT)

    stage_clear_times = relationship("StageClearTime", back_populates="result")


class StageClearTime(Base):
    __tablename__ = "stage_clear_times"
    id = Column(Integer, primary_key=True, index=True)
    result_id = Column(Integer, ForeignKey("results.id"))
    stage_name = Column(String(255))
    clear_time = Column(Float)

    result = relationship("Result", back_populates="stage_clear_times")


# api schema (request)
class StageClearTimeCreate(BaseModel):
    stage_name: str
    clear_time: float

    class Config:
        orm_mode = True


class ResultCreate(BaseModel):
    player_name: str
    total_time: float
    deaths: int
    total_energy: float
    stage_clear_times: list[StageClearTimeCreate] = Field(
        ...,
        description="List of stage cleared times",
        example=[
            {"stage_name": "Stage 1", "clear_time": 120.5},
            {"stage_name": "Stage 2", "clear_time": 150.0},
            {"stage_name": "Stage 3", "clear_time": 180.75},
            {"stage_name": "Stage 4", "clear_time": 200.25},
            {"stage_name": "Stage 5", "clear_time": 220.0},
            {"stage_name": "Stage 6", "clear_time": 250.5},
        ],
    )

    class Config:
        orm_mode = True


# api schema (response)
class StageClearTimeResponse(BaseModel):
    id: int
    stage_name: str
    clear_time: float

    class Config:
        orm_mode = True


class ResultResponse(BaseModel):
    id: int
    player_name: str
    total_time: float
    deaths: int
    total_energy: float
    groq_analysis: str
    stage_clear_times: List[StageClearTimeResponse]

    class Config:
        orm_mode = True


## end points
@router.post("/results", response_model=ResultResponse)
async def create_result(request_result: ResultCreate, db: AsyncSession = Depends(get_db)):
    # basic validation
    if len(request_result.stage_clear_times) != 6:
        raise HTTPException(
            status_code=500, detail="stage_clear_times must have 6 elements."
        )

    # get clear times on each stage
    new_clear_times = []
    for clear_time in request_result.stage_clear_times:
        new_clear_time = StageClearTime(
            stage_name=clear_time.stage_name, clear_time=clear_time.clear_time
        )
        new_clear_times.append(new_clear_time)

    # get median scores
    stmt = select(Result).options(selectinload(Result.stage_clear_times))
    queried_results = await db.execute(stmt)
    queried_results = queried_results.scalars().all()
    stage_medians = {}
    deaths_median = None
    total_energy_median = None

    if queried_results:
        deaths_median = median([res.deaths for res in queried_results])
        total_energy_median = median([res.total_energy for res in queried_results])

        # ステージごとのclear_timeを格納する辞書
        stage_times = defaultdict(list)

        # データを辞書に整理
        for res in queried_results:
            for stage_clear_time in res.stage_clear_times:
                stage_times[stage_clear_time.stage_name].append(stage_clear_time.clear_time)

        # 各ステージごとに中央値を計算
        for stage_name, times in stage_times.items():
            if times:  # timesが空でない場合のみ計算
                stage_medians[stage_name] = median(times)
            else:
                stage_medians[stage_name] = None  # データがない場合

    # ログ出力
    for stage_name, median_time in stage_medians.items():
        logger.info(f"Median Time for Stage '{stage_name}': {median_time}")

    # analyse scores with groq
    stage_clear_times_str = ", ".join(
        [f"{st.stage_name}: {st.clear_time}s" for st in request_result.stage_clear_times]
    )

    groq_prompt_01 = f"Please give me a very brief advice. This player has clear times of {stage_clear_times_str}, {request_result.deaths} deaths, and total used energy of {request_result.total_energy}. Note that lower energy usage is better."
    groq_prompt_02 = f"Median scores are: clear times of {stage_medians}, {deaths_median} deaths, and total used energy of {total_energy_median}. "
    groq_prompt_03 = "Stage 1 is a basic action stage. Stage 2, 3, and 4 are basic gamble stages. Stage 5 is a dynamic gamble stage. Stage 6 is the boss battle stage."
    groq_result = await groq_analysis(groq_prompt_01 + groq_prompt_02 + groq_prompt_03)

    # save to db
    new_result = Result(
        player_name=request_result.player_name,
        total_time=request_result.total_time,
        deaths=request_result.deaths,
        total_energy=request_result.total_energy,
        groq_analysis=groq_result,
        stage_clear_times=new_clear_times,
    )
    db.add(new_result)
    await db.commit()
    await db.refresh(new_result)

    # return response
    result_with_relations = await db.execute(
        select(Result)
        .options(selectinload(Result.stage_clear_times))
        .where(Result.id == new_result.id)
    )
    result_with_relations = result_with_relations.scalar_one()
    return result_with_relations



@router.get("/results", response_model=List[ResultResponse])
async def get_results(db: AsyncSession = Depends(get_db)):
    stmt = select(Result).options(selectinload(Result.stage_clear_times))
    results = await db.execute(stmt)
    return results.scalars().all()

# レスポンス用のデータモデル
class SimpleResultResponse(BaseModel):
    player_name: str
    total_time: float
    deaths: int
    total_energy: float
    class Config:
        orm_mode = True
# ラップ用のデータモデル
class ResultsWrapper(BaseModel):
    results: List[SimpleResultResponse]
@router.get("/simple-results", response_model=ResultsWrapper)
async def get_simple_results(db: AsyncSession = Depends(get_db)):
    # SQLAlchemyクエリ
    stmt = select(Result.player_name, Result.total_time, Result.deaths, Result.total_energy)
    results = await db.execute(stmt)
    # 結果をリスト形式に変換
    results_list = results.all()
    return {"results": [
        SimpleResultResponse(
            player_name=row[0],
            total_time=row[1],
            deaths=row[2],
            total_energy=row[3],
        )
        for row in results_list
    ]}

# functions
async def groq_analysis(prompt: str):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model="llama-3.3-70b-versatile",
    )
    return chat_completion.choices[0].message.content
