from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from xiaoxue_api.core.module_loader import attach_feature_routers


def create_app() -> FastAPI:
    app = FastAPI(title="小雪工作台")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    boot_status = attach_feature_routers(app)
    try:
        from xiaoxue_api.modules.platform.public import configure_boot_status
        configure_boot_status(boot_status)
    except Exception:
        pass
    app.state.module_boot_status = boot_status
    _mount_static_assets(app)
    return app


def _mount_static_assets(app: FastAPI) -> None:
    graph = os.environ.get("XIAOXUE_TK_GRAPH_DIR", "/home/ubuntu/tk_graph_serve")
    if os.path.isdir(graph):
        app.mount("/tk-graph", StaticFiles(directory=graph, html=True), name="tk_graph")
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assets = os.path.join(root, "dist", "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="dist_assets")
