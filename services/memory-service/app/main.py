from fastapi import FastAPI
from app.database import SessionLocal

app = FastAPI(title="QuantumLabs Memory Service")


@app.get("/")
def root():
    return {"message": "QuantumLabs Memory Service"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-health")
def db_health():
    try:
        db = SessionLocal()
        db.close()
        return {"database": "ok"}
    except Exception as e:
        return {"database": "error", "detail": str(e)}

from sqlalchemy import text

@app.get("/db-test")
def db_test():
    try:
        db = SessionLocal()
        result = db.execute(text("SELECT NOW()"))
        current_time = result.scalar()
        db.close()

        return {
            "database": "ok",
            "time": str(current_time)
        }

    except Exception as e:
        return {
            "database": "error",
            "detail": str(e)
        }


from app.qdrant_client import qdrant

@app.get("/vector-health")
def vector_health():
    try:
        collections = qdrant.get_collections()
        return {
            "vector_db": "ok",
            "collections": len(collections.collections)
        }
    except Exception as e:
        return {
            "vector_db": "error",
            "detail": str(e)
        }

from pydantic import BaseModel

class MemoryCreate(BaseModel):
    user_id: str
    content: str

@app.post("/memories")
def create_memory(memory: MemoryCreate):
    return {
        "status": "stored",
        "user_id": memory.user_id,
        "content": memory.content
    }


@app.get("/setup-db")
def setup_db():
    try:
        db = SessionLocal()
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS memories (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        db.commit()
        db.close()
        return {"setup": "ok"}
    except Exception as e:
        return {"setup": "error", "detail": str(e)}

@app.post("/memories-db")
def create_memory_db(memory: MemoryCreate):
    try:
        db = SessionLocal()

        db.execute(
            text("""
                INSERT INTO memories (user_id, content)
                VALUES (:user_id, :content)
            """),
            {
                "user_id": memory.user_id,
                "content": memory.content
            }
        )

        db.commit()
        db.close()

        return {"status": "stored_in_db"}

    except Exception as e:
        return {
            "status": "error",
            "detail": str(e)
        }

@app.get("/memories/{user_id}")
def get_memories(user_id: str):
    try:
        db = SessionLocal()

        result = db.execute(
            text("""
                SELECT id, user_id, content, created_at
                FROM memories
                WHERE user_id = :user_id
                ORDER BY created_at DESC
            """),
            {"user_id": user_id}
        )

        rows = result.fetchall()
        db.close()

        return {
            "user_id": user_id,
            "memories": [
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "content": row.content,
                    "created_at": str(row.created_at)
                }
                for row in rows
            ]
        }

    except Exception as e:
        return {
            "status": "error",
            "detail": str(e)
        }
