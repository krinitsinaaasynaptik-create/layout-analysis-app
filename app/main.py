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
    fetch_manual_merges,
    finish_run,
    init_db,
    start_run,
    update_layout_tags,
)
from .grouping import build_layout_groups
from .ksm_seller_parser import KsmSellerParser
from .objectiv_house_metadata import enrich_houses_with_objectiv_metadata
from .objectiv_parser import ObjectivParser
from .parser import ZhcomParser
from .price_dynamics import build_price_dynamics_report, export_price_dynamics_csv
from .refresh_catalog import REFRESH_TARGET_BY_ID, REFRESH_TARGETS
from .report import build_compare_report, build_csv, build_report
from .sretensky_parser import PLANS_URL as SRETENSKY_URL, SretenskyParser


ensure_dirs()
init_db()

app = FastAPI(title="Анализ вариативности планировок ССК")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/data-images", StaticFiles(directory=IMAGE_DIR), name="data-images")


def _build_parser(target_id: str, objectiv_access_token: str, ksm_session_id: str):
    target = REFRESH_TARGET_BY_ID.get(target_id)
    if not target:
        raise RuntimeError("Неизвестный застройщик для обновления.")
    if target.source == "zhcom":
        return (target.id, target.name, target.developer_type, target.source_url, target.source, ZhcomParser())
    if target.source == "sretensky":
        return (target.id, target.name, target.developer_type, target.source_url, target.source, SretenskyParser())
    if target.source == "ksm_seller":
        if not ksm_session_id:
            raise RuntimeError("КСМ: нужна PHP-сессия кабинета менеджера.")
        if not objectiv_access_token:
            raise RuntimeError("КСМ: нужен токен Объектива для метаданных по домам.")
        return (
            target.id,
            target.name,
            target.developer_type,
            target.source_url,
            target.source,
            KsmSellerParser(session_id=ksm_session_id),
        )
    if not objectiv_access_token:
        raise RuntimeError(f"{target.name}: нужен токен Объектива.")
    return (
        target.id,
        target.name,
        target.developer_type,
        target.source_url,
        target.source,
        ObjectivParser(group_name=target.objectiv_group_name, access_token=objectiv_access_token),
    )


def _refresh_parsers(objectiv_access_token: str, ksm_session_id: str, developer_id: Optional[str] = None):
    target_ids = [developer_id] if developer_id else [target.id for target in REFRESH_TARGETS]
    return [_build_parser(target_id, objectiv_access_token, ksm_session_id) for target_id in target_ids]


def _run_refresh(objectiv_access_token: str, ksm_session_id: str, developer_id: Optional[str] = None) -> JSONResponse:
    try:
        parsers = _refresh_parsers(objectiv_access_token, ksm_session_id, developer_id)
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)
    run_id = start_run()
    try:
        from .db import replace_data

        total_source = 0
        total_collected = 0
        messages = []
        for item_developer_id, developer_name, developer_type, source_url, source, parser in parsers:
            try:
                houses, flats, source_total = parser.parse()
                if objectiv_access_token and item_developer_id in {"zhcom", "sretensky", "ksm"}:
                    houses = enrich_houses_with_objectiv_metadata(
                        houses,
                        developer_id=item_developer_id,
                        access_token=objectiv_access_token,
                    )
            except Exception as exc:
                raise RuntimeError(f"{developer_name}: {exc}") from exc
            groups = build_layout_groups(flats)
            replace_data(houses, flats, groups, item_developer_id, developer_name, developer_type, source_url, source)
            total_source += source_total
            total_collected += len(flats)
            if flats:
                messages.append(
                    f"{developer_name}: домов {len({flat.house_id for flat in flats})}, "
                    f"квартир {len(flats)}, планировок {len(groups)}"
                )
            else:
                messages.append(f"{developer_name}: квартир 0")
        message = "Обновлено: " + "; ".join(messages) + "."
        finish_run(run_id, "success", message, total_source, total_collected)
        return JSONResponse({"ok": True, "message": message, "report": build_report()})
    except Exception as exc:
        finish_run(run_id, "error", str(exc), 0, 0)
        return JSONResponse({"ok": False, "message": str(exc), "report": build_report()}, status_code=500)
    finally:
        for *_meta, parser in parsers:
            parser.close()


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
                rooms=_rooms(request),
                include_group_metrics=False,
                include_similar_layouts=False,
            ),
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
