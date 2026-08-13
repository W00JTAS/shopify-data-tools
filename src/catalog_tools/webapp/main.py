"""Lekki panel webowy nad `catalog_tools`: kategoryzacja i konsolidacja
wariantów w przeglądarce, z zapisem wyniku lokalnie (pobranie pliku).

Uruchomienie:

    uvicorn catalog_tools.webapp.main:app --reload

Panel nie trzyma stanu na serwerze poza cache'em modelu — każde żądanie
niesie własny plik CSV, wynik wraca w odpowiedzi jako tekst CSV, a "zapis
lokalnie" to zwykłe pobranie pliku przez przeglądarkę. Brak plików tymczasowych
do sprzątania, brak bazy danych — to jest cała złożoność, jakiej to narzędzie
potrzebuje.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import requests
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import consolidate, pipeline
from ..llm_fallback import DEFAULT_HOST, DEFAULT_MODEL, ResponseCache
from ..rule_proposer import ProposalError, propose_rules

app = FastAPI(title="Catalog Tools")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _read_csv(file: UploadFile, sep: str) -> pd.DataFrame:
    content = file.file.read()
    try:
        return pd.read_csv(io.BytesIO(content), sep=sep, dtype=str)
    except Exception as exc:  # plik uszkodzony albo zły separator — komunikat, nie 500
        raise HTTPException(400, f"Nie udało się wczytać CSV (separator {sep!r}?): {exc}") from exc


@app.post("/api/preview")
async def preview(file: UploadFile, sep: str = Form(";")):
    frame = _read_csv(file, sep)
    return {"columns": list(frame.columns), "row_count": len(frame)}


@app.post("/api/categorize/propose-rules")
async def categorize_propose_rules(
    file: UploadFile,
    column: str = Form(...),
    sep: str = Form(";"),
    target_count: int = Form(12),
):
    frame = _read_csv(file, sep)
    if column not in frame.columns:
        raise HTTPException(400, f"Brak kolumny {column!r}. Dostępne: {list(frame.columns)}")

    categories = sorted(c for c in frame[column].dropna().unique() if str(c).strip())
    try:
        proposal = propose_rules(categories, target_count=target_count)
    except ProposalError as exc:
        raise HTTPException(502, str(exc)) from exc

    return {
        "rules": proposal.rules,
        "unmapped": proposal.unmapped,
        "unique_categories": len(categories),
        "target_categories": len(proposal.rules["mapowanie"]),
    }


@app.post("/api/categorize/run")
async def categorize_run(
    file: UploadFile,
    column: str = Form(...),
    sep: str = Form(";"),
    rules: str = Form(...),
    use_llm: bool = Form(False),
):
    frame = _read_csv(file, sep)
    if column not in frame.columns:
        raise HTTPException(400, f"Brak kolumny {column!r}. Dostępne: {list(frame.columns)}")
    try:
        rules_dict = json.loads(rules)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"Reguły nie są poprawnym JSON-em: {exc}") from exc

    cache = ResponseCache() if use_llm else None
    try:
        result, summary = pipeline.categorize_frame(frame, column, rules_dict, use_llm=use_llm, cache=cache)
    finally:
        if cache:
            cache.close()

    return {"summary": summary, "csv": result.to_csv(index=False)}


@app.post("/api/consolidate/run")
async def consolidate_run(file: UploadFile, fetch_images: bool = Form(False)):
    import csv as csv_module

    text = file.file.read().decode("utf-8")
    rows = list(csv_module.DictReader(io.StringIO(text)))
    if not rows:
        raise HTTPException(400, "Plik CSV jest pusty albo nie ma nagłówka.")

    fetcher = None
    if fetch_images:
        def fetcher(url: str) -> bytes | None:  # noqa: E306
            try:
                resp = requests.get(url, timeout=10)
                return resp.content if resp.ok else None
            except requests.RequestException:
                return None

    result = consolidate.consolidate(rows, image_fetcher=fetcher)
    summary = {
        "groups_consolidated": result.groups_consolidated,
        "groups_passthrough": result.groups_passthrough,
        "rows_out": len(result.rows),
    }
    return {"summary": summary, "unresolved": result.unresolved, "csv": pipeline.consolidated_rows_to_csv(result.rows)}


@app.get("/api/health")
async def health():
    """Sprawdza, czy lokalna Ollama odpowiada — panel pokazuje to jako status,
    żeby 'AI proponuje reguły' nie zawodziło bez wyjaśnienia."""
    try:
        requests.get(f"{DEFAULT_HOST}/api/tags", timeout=2)
        return {"ollama": True, "model": DEFAULT_MODEL}
    except requests.RequestException:
        return JSONResponse({"ollama": False, "model": DEFAULT_MODEL}, status_code=200)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
