from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.investigator import investigate_namespace
from app.settings import get_settings


app = FastAPI(title="AI Kubernetes Troubleshooting Agent MVP")
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/investigate")
def investigate(
    namespace: str = Query(..., min_length=1),
    resource_name: str = Query(..., min_length=1),
) -> dict[str, object]:
    try:
        return investigate_namespace(namespace=namespace, resource_name=resource_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
