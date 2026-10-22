"""FastAPI application entrypoint."""

from fastapi import FastAPI

from . import __version__

app = FastAPI(title="Trace API", version=__version__)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
