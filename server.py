from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
import time
import os

app = FastAPI()
DB_PATH = "cat_game.db"

STAGES = [
    (0,     "눈도 못 뜨는 아기"),
    (500,   "눈 뜬 아기"),
    (1150,  "아장아장"),
    (1900,  "호기심 많은 고양이"),
    (2900,  "개구쟁이"),
    (4000,  "의젓한 고양이"),
    (5300,  "멋진 고양이"),
    (6800,  "고양이 어른"),
    (8500,  "현명한 고양이"),
    (10400, "전설의 고양이"),
]

IDLE_POINTS_PER_MIN = 10
IDLE_INTERVAL_SEC = 60


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            nickname TEXT PRIMARY KEY,
            cat_name TEXT NOT NULL,
            points REAL NOT NULL DEFAULT 0,
            click_points INTEGER NOT NULL DEFAULT 0,
            idle_points INTEGER NOT NULL DEFAULT 0,
            last_seen REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_stage(points: float) -> tuple[int, str]:
    stage = 0
    name = STAGES[0][1]
    for i, (threshold, stage_name) in enumerate(STAGES):
        if points >= threshold:
            stage = i
            name = stage_name
    return stage, name


def calc_idle_points(last_seen: float) -> int:
    elapsed_sec = time.time() - last_seen
    minutes = int(elapsed_sec // IDLE_INTERVAL_SEC)
    return minutes * IDLE_POINTS_PER_MIN


# ── Models ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    nickname: str
    cat_name: str


class ClickRequest(BaseModel):
    nickname: str


# ── Routes ──────────────────────────────────────────────

@app.post("/register")
def register(req: RegisterRequest):
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM users WHERE nickname = ?", (req.nickname,)
    ).fetchone()

    if existing:
        # 이미 등록된 유저 → 방치 포인트 계산 후 반환
        idle = calc_idle_points(existing["last_seen"])
        new_points = existing["points"] + idle
        new_idle_total = existing["idle_points"] + idle
        conn.execute(
            "UPDATE users SET points = ?, idle_points = ?, last_seen = ? WHERE nickname = ?",
            (new_points, new_idle_total, time.time(), req.nickname)
        )
        conn.commit()
        stage, stage_name = get_stage(new_points)
        conn.close()
        return {
            "nickname": existing["nickname"],
            "cat_name": existing["cat_name"],
            "points": new_points,
            "click_points": existing["click_points"],
            "idle_points": new_idle_total,
            "stage": stage,
            "stage_name": stage_name,
            "is_new": False
        }

    # 새 유저 등록
    conn.execute(
        "INSERT INTO users (nickname, cat_name, points, click_points, idle_points, last_seen) VALUES (?, ?, 0, 0, 0, ?)",
        (req.nickname, req.cat_name, time.time())
    )
    conn.commit()
    conn.close()
    return {
        "nickname": req.nickname,
        "cat_name": req.cat_name,
        "points": 0,
        "click_points": 0,
        "idle_points": 0,
        "stage": 0,
        "stage_name": STAGES[0][1],
        "is_new": True
    }


@app.post("/click")
def click(req: ClickRequest):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE nickname = ?", (req.nickname,)
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="유저 없음")

    idle = calc_idle_points(user["last_seen"])
    new_points = user["points"] + 1 + idle
    new_click = user["click_points"] + 1
    new_idle_total = user["idle_points"] + idle

    conn.execute(
        "UPDATE users SET points = ?, click_points = ?, idle_points = ?, last_seen = ? WHERE nickname = ?",
        (new_points, new_click, new_idle_total, time.time(), req.nickname)
    )
    conn.commit()
    stage, stage_name = get_stage(new_points)
    conn.close()

    return {
        "points": new_points,
        "click_points": new_click,
        "idle_points": new_idle_total,
        "stage": stage,
        "stage_name": stage_name,
    }


@app.get("/status/{nickname}")
def status(nickname: str):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE nickname = ?", (nickname,)
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="유저 없음")

    idle = calc_idle_points(user["last_seen"])
    new_points = user["points"] + idle
    new_idle_total = user["idle_points"] + idle

    conn.execute(
        "UPDATE users SET points = ?, idle_points = ?, last_seen = ? WHERE nickname = ?",
        (new_points, new_idle_total, time.time(), nickname)
    )
    conn.commit()
    stage, stage_name = get_stage(new_points)
    conn.close()

    next_threshold = STAGES[stage + 1][0] if stage < len(STAGES) - 1 else None

    return {
        "nickname": user["nickname"],
        "cat_name": user["cat_name"],
        "points": new_points,
        "click_points": user["click_points"],
        "idle_points": new_idle_total,
        "stage": stage,
        "stage_name": stage_name,
        "next_threshold": next_threshold,
    }


init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)