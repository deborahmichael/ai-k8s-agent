from fastapi import FastAPI, HTTPException, Query

from app.investigator import investigate_namespace


app = FastAPI(title="AI Kubernetes Troubleshooting Agent MVP")


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
