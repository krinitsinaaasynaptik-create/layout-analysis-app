import mimetypes
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .area_dashboard import build_area_dashboard, export_area_dashboard_csv, export_area_dashboard_xlsx
from .config import BASE_DIR, IMAGE_DIR, ensure_dirs
from .db import (
    create_manual_merge,
    delete_manual_merge,
    fetch_report_rows,
    fetch_manual_merges,
    init_db,
    update_layout_tags,
)
from .price_dynamics import build_price_dynamics_report, export_price_dynamics_csv
from .refresh_service import run_refresh
from .report import build_compare_report, build_csv, build_report


ensure_dirs()
init_db()

app = FastAPI(title="Анализ вариативности планировок ССК")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/data-images", StaticFiles(directory=IMAGE_DIR), name="data-images")

def _run_refresh(objectiv_access_token: str, ksm_session_id: str, developer_id: Optional[str] = None) -> JSONResponse:
    try:
        payload = run_refresh(objectiv_access_token, ksm_session_id, developer_id, include_report=True)
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)
    return JSONResponse(payload, status_code=200 if payload.get("ok") else 500)


@app.get("/image-files/{filename:path}")
def image_file(filename: str) -> FileResponse:
    path = IMAGE_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    media_type = _guess_image_media_type(path)
    return FileResponse(path, media_type=media_type)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "market.html",
        {
            "request": request,
            "report": build_report(
                _period_days(request),
                project_id=_project_id(request),
                calc_mode=_calc_mode(request),
                developer_id=_developer_id(request),
                developer_scope=_market_mode(request),
                include_group_metrics=False,
                include_similar_layouts=False,
            ),
        },
    )


@app.get("/developers/{developer_id}", response_class=HTMLResponse)
def developer_page(request: Request, developer_id: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "developer.html",
        {
            "request": request,
            "report": build_report(
                _period_days(request),
                developer_id=developer_id,
                project_id=_project_id(request),
                history_project_id=_history_project_id(request),
                history_house_id=_history_house_id(request),
                rooms=_rooms(request),
                include_group_metrics=False,
                include_similar_layouts=False,
            ),
        },
    )


@app.get("/developers/{developer_id}/price-history", response_class=HTMLResponse)
def developer_price_history(request: Request, developer_id: str) -> HTMLResponse:
    base_report = build_report(
        _period_days(request),
        developer_id=developer_id,
        project_id=_project_id(request),
        history_project_id=_history_project_id(request),
        rooms=_rooms(request),
        include_group_metrics=False,
        include_similar_layouts=False,
    )
    selected_house_ids = _history_house_ids(request)
    house_options = base_report.get("filters", {}).get("history_house_options") or []
    option_ids = {str(item.get("id") or "") for item in house_options}
    if selected_house_ids:
        selected_house_ids = [house_id for house_id in selected_house_ids if house_id in option_ids]
    if not selected_house_ids:
        selected_house_ids = [str(item.get("id") or "") for item in house_options if item.get("id")]
    charts = []
    for house_id in selected_house_ids:
        item_report = build_report(
            _period_days(request),
            developer_id=developer_id,
            project_id=_project_id(request),
            history_project_id=base_report.get("filters", {}).get("history_project_id") or _history_project_id(request),
            history_house_id=house_id,
            rooms=_rooms(request),
            include_group_metrics=False,
            include_similar_layouts=False,
        )
        history = item_report.get("project_price_history") or {}
        if history.get("selected_house_id"):
            charts.append(history)
    base_report["price_history_grid"] = {
        "charts": charts,
        "selected_house_ids": selected_house_ids,
    }
    base_report["filters"]["history_house_ids"] = selected_house_ids
    return templates.TemplateResponse(
        "developer_price_history.html",
        {
            "request": request,
            "report": base_report,
        },
    )


@app.get("/layouts", response_class=HTMLResponse)
def layouts(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "report": build_report(
                _period_days(request),
                developer_scope="competitors",
                include_group_metrics=True,
                include_similar_layouts=False,
            ),
        },
    )


@app.get("/developers/{developer_id}/layouts", response_class=HTMLResponse)
def developer_layouts(request: Request, developer_id: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "report": build_report(
                _period_days(request),
                developer_id=developer_id,
                project_id=_project_id(request),
                rooms=_rooms(request),
                include_group_metrics=True,
                include_similar_layouts=False,
            ),
        },
    )


@app.get("/market", response_class=HTMLResponse)
def market(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "market.html",
        {
            "request": request,
            "report": build_report(
                _period_days(request),
                project_id=_project_id(request),
                calc_mode=_calc_mode(request),
                developer_id=_developer_id(request),
                developer_scope=_market_mode(request),
                include_group_metrics=False,
                include_similar_layouts=False,
            ),
        },
    )


@app.get("/compare", response_class=HTMLResponse)
def compare(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "compare.html",
        {
            "request": request,
            "report": build_compare_report(
                _period_days(request),
                own_project_id=_own_project_id(request),
                competitor_id=_competitor_id(request),
                competitor_project_id=_competitor_project_id(request),
                rooms=_rooms(request),
            ),
        },
    )


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "report": build_area_dashboard(
                mode=_report_mode(request),
                period=_dashboard_period(request),
                developer_id=_developer_id(request) or "",
                project_id=_project_id(request) or "",
                rooms=_rooms(request) or "",
                market_mode=_market_mode(request),
            ),
        },
    )


@app.get("/dashboard/price-dynamics", response_class=HTMLResponse)
def price_dynamics_dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "price_dynamics.html",
        {
            "request": request,
            "report": build_price_dynamics_report(
                period=_price_dynamics_period(request),
                granularity=_price_dynamics_granularity(request),
                developer_id=_developer_id(request) or "",
                project_id=_project_id(request) or "",
                house_id=_house_id(request) or "",
                rooms=_rooms(request) or "",
                area_group=(request.query_params.get("area_group") or "").strip(),
                status_filter=_price_dynamics_status(request),
                view=(request.query_params.get("view") or "current").strip(),
            ),
        },
    )


@app.get("/layouts/{layout_id:path}", response_class=HTMLResponse)
def layout_detail(request: Request, layout_id: str) -> HTMLResponse:
    report_data = build_report(_period_days(request), include_group_metrics=True, include_similar_layouts=True)
    layout = next((item for item in report_data["layouts"] if item["group_id"] == layout_id), None)
    if not layout:
        return templates.TemplateResponse(
            "layout_detail.html",
            {"request": request, "report": report_data, "layout": None},
            status_code=404,
        )
    return templates.TemplateResponse(
        "layout_detail.html",
        {"request": request, "report": report_data, "layout": layout},
    )


@app.get("/developers/{developer_id}/layouts/{layout_id:path}", response_class=HTMLResponse)
def developer_layout_detail(request: Request, developer_id: str, layout_id: str) -> HTMLResponse:
    report_data = build_report(
        _period_days(request),
        developer_id=developer_id,
        project_id=_project_id(request),
        rooms=_rooms(request),
        include_group_metrics=True,
        include_similar_layouts=True,
    )
    layout = next((item for item in report_data["layouts"] if item["group_id"] == layout_id), None)
    if not layout:
        return templates.TemplateResponse(
            "layout_detail.html",
            {"request": request, "report": report_data, "layout": None},
            status_code=404,
        )
    return templates.TemplateResponse(
        "layout_detail.html",
        {"request": request, "report": report_data, "layout": layout},
    )


@app.post("/api/refresh")
async def refresh(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    objectiv_access_token = (body.get("objectiv_access_token") or os.environ.get("OBJECTIV_ACCESS_TOKEN") or "").strip()
    ksm_session_id = (body.get("ksm_session_id") or os.environ.get("KSM_PHPSESSID") or "").strip()
    return _run_refresh(objectiv_access_token, ksm_session_id)


@app.post("/api/refresh/{developer_id}")
async def refresh_developer(developer_id: str, request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}
    objectiv_access_token = (body.get("objectiv_access_token") or os.environ.get("OBJECTIV_ACCESS_TOKEN") or "").strip()
    ksm_session_id = (body.get("ksm_session_id") or os.environ.get("KSM_PHPSESSID") or "").strip()
    return _run_refresh(objectiv_access_token, ksm_session_id, developer_id.strip())


@app.get("/api/report")
def report() -> JSONResponse:
    return JSONResponse(build_report(developer_scope="competitors"))


@app.get("/api/debug/objectiv-history/{developer_id}")
def debug_objectiv_history(
    developer_id: str,
    history_project_id: str = "",
    history_house_id: str = "",
) -> JSONResponse:
    rows = fetch_report_rows()
    history_rows = [dict(row) for row in rows.get("objectiv_project_history_monthly", [])]
    developer_rows = [row for row in history_rows if str(row.get("developer_id") or "") == developer_id]
    project_rows = [
        row for row in developer_rows
        if not history_project_id or str(row.get("project_id") or "") == history_project_id
    ]
    house_rows = [
        row for row in project_rows
        if not history_house_id or str(row.get("house_id") or "") == history_house_id
    ]
    report_data = build_report(
        developer_id=developer_id,
        history_project_id=history_project_id or None,
        history_house_id=history_house_id or None,
        include_group_metrics=False,
        include_similar_layouts=False,
    )
    project_price_history = report_data.get("project_price_history") or {}
    return JSONResponse(
        {
            "developer_id": developer_id,
            "history_project_id": history_project_id,
            "history_house_id": history_house_id,
            "history_rows_total": len(history_rows),
            "developer_rows_total": len(developer_rows),
            "project_rows_total": len(project_rows),
            "house_rows_total": len(house_rows),
            "project_rows_sample": project_rows[:10],
            "house_rows_sample": house_rows[:10],
            "selected_project_id": project_price_history.get("selected_project_id"),
            "selected_house_id": project_price_history.get("selected_house_id"),
            "available": project_price_history.get("available"),
            "message": project_price_history.get("message"),
            "series_len": len(project_price_history.get("series") or []),
            "series_sample": (project_price_history.get("series") or [])[:10],
        }
    )


@app.get("/api/manual-merges")
def manual_merges() -> JSONResponse:
    return JSONResponse({"items": fetch_manual_merges()})


@app.post("/api/manual-merge")
async def manual_merge(request: Request) -> JSONResponse:
    payload = await request.json()
    target_key = str(payload.get("target_group_key") or "")
    source_keys = [str(key) for key in payload.get("source_group_keys") or [] if key]
    note = str(payload.get("note") or "")
    report_data = build_report()
    group_by_key = {
        group["group_key"]: group
        for project in report_data["projects"]
        for house in project["houses"]
        for room in house["rooms"]
        for group in room["groups"]
    }
    target = group_by_key.get(target_key)
    sources = [group_by_key.get(key) for key in source_keys]
    if not target or not sources or any(source is None for source in sources):
        return JSONResponse({"ok": False, "message": "Не удалось найти выбранные планировки."}, status_code=400)
    if any(source["house_id"] != target["house_id"] or source["rooms"] != target["rooms"] for source in sources):
        return JSONResponse(
            {"ok": False, "message": "Объединять можно только планировки внутри одного дома и комнатности."},
            status_code=400,
        )
    create_manual_merge(target["house_id"], target["rooms"], target_key, source_keys, note)
    return JSONResponse({"ok": True, "message": "Планировки объединены.", "report": build_report()})


@app.delete("/api/manual-merge/{merge_id}")
def remove_manual_merge(merge_id: int) -> JSONResponse:
    delete_manual_merge(merge_id)
    return JSONResponse({"ok": True, "message": "Ручное объединение отменено.", "report": build_report()})


@app.post("/api/layout-tags/{layout_id:path}")
async def save_layout_tags(layout_id: str, request: Request) -> JSONResponse:
    payload = await request.json()
    tag_ids = payload.get("tag_ids") or []
    update_layout_tags(layout_id, tag_ids)
    return JSONResponse({"ok": True, "message": "Теги сохранены.", "report": build_report()})


@app.get("/api/export.csv")
def export_csv() -> PlainTextResponse:
    return PlainTextResponse(
        build_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="zhcom-layout-variability.csv"'},
    )


@app.get("/api/area-summary.csv")
def export_area_summary(request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        export_area_dashboard_csv(
            mode=_report_mode(request),
            period=_dashboard_period(request),
            developer_id=_developer_id(request) or "",
            project_id=_project_id(request) or "",
            rooms=_rooms(request) or "",
            market_mode=_market_mode(request),
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="area-summary.csv"'},
    )


@app.get("/api/area-summary.xlsx")
def export_area_summary_xlsx(request: Request) -> Response:
    return Response(
        content=export_area_dashboard_xlsx(
            mode=_report_mode(request),
            period=_dashboard_period(request),
            developer_id=_developer_id(request) or "",
            project_id=_project_id(request) or "",
            rooms=_rooms(request) or "",
            market_mode=_market_mode(request),
        ),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="area-summary.xlsx"'},
    )


@app.get("/api/price-dynamics.csv")
def export_price_dynamics(request: Request) -> PlainTextResponse:
    return PlainTextResponse(
        export_price_dynamics_csv(
            period=_price_dynamics_period(request),
            granularity=_price_dynamics_granularity(request),
            developer_id=_developer_id(request) or "",
            project_id=_project_id(request) or "",
            house_id=_house_id(request) or "",
            rooms=_rooms(request) or "",
            area_group=(request.query_params.get("area_group") or "").strip(),
            status_filter=_price_dynamics_status(request),
            view=(request.query_params.get("view") or "current").strip(),
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="price-dynamics.csv"'},
    )


def _period_days(request: Request) -> int:
    try:
        value = int(request.query_params.get("period_days", "30"))
    except ValueError:
        return 30
    return min(max(value, 1), 365)


def _developer_id(request: Request) -> Optional[str]:
    value = (request.query_params.get("developer_id") or "").strip()
    return value or None


def _project_id(request: Request) -> Optional[str]:
    value = (request.query_params.get("project_id") or "").strip()
    return value or None


def _history_project_id(request: Request) -> Optional[str]:
    value = (request.query_params.get("history_project_id") or "").strip()
    return value or None


def _history_house_id(request: Request) -> Optional[str]:
    value = (request.query_params.get("history_house_id") or "").strip()
    return value or None


def _history_house_ids(request: Request) -> list[str]:
    values = [
        value.strip()
        for value in request.query_params.getlist("history_house_id")
        if value and value.strip()
    ]
    if values:
        return values
    raw = (request.query_params.get("history_house_ids") or "").strip()
    return [value.strip() for value in raw.split(",") if value.strip()]


def _house_id(request: Request) -> Optional[str]:
    value = (request.query_params.get("house_id") or "").strip()
    return value or None


def _own_project_id(request: Request) -> Optional[str]:
    value = (request.query_params.get("own_project_id") or "").strip()
    return value or None


def _competitor_id(request: Request) -> Optional[str]:
    value = (request.query_params.get("competitor_id") or "").strip()
    return value or None


def _competitor_project_id(request: Request) -> Optional[str]:
    value = (request.query_params.get("competitor_project_id") or "").strip()
    return value or None


def _calc_mode(request: Request) -> str:
    value = (request.query_params.get("calc_mode") or "apartments").strip().lower()
    return "layouts" if value == "layouts" else "apartments"


def _rooms(request: Request) -> Optional[str]:
    value = (request.query_params.get("rooms") or "").strip().upper()
    return value or None


def _report_mode(request: Request) -> str:
    value = (request.query_params.get("mode") or "current").strip()
    return value if value in {"current", "monthly"} else "current"


def _dashboard_period(request: Request) -> str:
    value = (request.query_params.get("period") or "6m").strip()
    return value if value in {"3m", "6m", "12m", "all"} else "6m"


def _price_dynamics_period(request: Request) -> str:
    value = (request.query_params.get("period") or "90d").strip()
    return value if value in {"7d", "30d", "90d", "6m", "12m", "all"} else "90d"


def _price_dynamics_granularity(request: Request) -> str:
    value = (request.query_params.get("granularity") or "slice").strip()
    return value if value in {"slice", "day", "week", "month"} else "slice"


def _price_dynamics_status(request: Request) -> str:
    value = (request.query_params.get("status_filter") or "all").strip()
    return value if value in {"all", "growth", "decline", "new", "gone", "stable"} else "all"


def _market_mode(request: Request) -> str:
    value = (request.query_params.get("market_mode") or "all").strip()
    return value if value in {"all", "competitors", "own"} else "all"


def _guess_image_media_type(path: Path) -> str:
    sanitized_name = path.name.split("@", 1)[0]
    media_type, _ = mimetypes.guess_type(sanitized_name)
    return media_type or "application/octet-stream"
