from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "license api running"
    }


@app.get("/health")
def health():
    return {
        "ok": True
    }
