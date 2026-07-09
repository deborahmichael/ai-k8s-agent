from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.history_service import get_history_error, get_history_item, is_history_enabled, list_history, save_investigation
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
        result = investigate_namespace(namespace=namespace, resource_name=resource_name)
        history_id = None
        try:
            history_id = save_investigation(result)
        except Exception:
            history_id = None
        result["history_saved"] = bool(history_id)
        result["history_id"] = history_id
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history")
def history(limit: int = Query(default=settings.history_limit, ge=1, le=100)) -> dict[str, object]:
    if not is_history_enabled():
        return {"enabled": False, "items": []}

    items = list_history(limit=limit)
    response: dict[str, object] = {"enabled": True, "items": items}
    error = get_history_error()
    if error and not items:
        response["error"] = error
    return response


@app.get("/api/history/{history_id}")
def history_item(history_id: str) -> dict[str, object]:
    if not is_history_enabled():
        return {"enabled": False, "item": None}

    item = get_history_item(history_id)
    response: dict[str, object] = {"enabled": True, "item": item}
    error = get_history_error()
    if item is None:
        response["error"] = error or "History item not found"
    return response