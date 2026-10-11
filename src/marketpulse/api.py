"""Local-only HTTP facade; no provider credentials or order endpoints."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from starlette.middleware.trustedhost import TrustedHostMiddleware

from marketpulse.service import DemoService


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: Literal["AAPL", "NVDA", "AMZN", "JPM", "XOM", "WMT"]
    session: date
    fault: Literal["NONE", "STALE", "MISSING_NEWS", "TIMEOUT", "EXPIRED", "LOW_CONFIDENCE"] = "NONE"


def create_app(data_dir: Path) -> FastAPI:
    service = DemoService(data_dir)
    app = FastAPI(title="MarketPulse synthetic replay", version="0.1.0")
    app.state.service = service
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )

    @app.middleware("http")
    async def local_request_guard(request: Request, call_next):
        # TestClient uses the synthetic peer 'testclient'. The server binds only loopback.
        if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return Response("Loopback access only", status_code=403)
        if request.method in {"POST", "PUT", "PATCH"}:
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 16384:
                    return Response("Request too large", status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    def safely(callback):
        try:
            return callback()
        except KeyError:
            raise HTTPException(404, "Record not found") from None
        except ValueError:
            raise HTTPException(
                409, "Request refused: check fixture catalog and readiness"
            ) from None
        except (OSError, RuntimeError):
            raise HTTPException(503, "Local artifact or execution unavailable") from None

    @app.get("/health/live")
    def live():
        return {"live": True, "availability_tier": "FIXTURE", "real_order_adapter_present": False}

    @app.get("/health/ready")
    def ready():
        try:
            return service.ready()
        except (ValueError, KeyError, OSError):
            raise HTTPException(503, "Initialize and verify the synthetic demo first") from None

    @app.get("/catalog")
    def catalog():
        return safely(service.catalog)

    @app.post("/predict")
    def predict(body: ForecastRequest, response: Response):
        result = safely(
            lambda: service.forecast(body.symbol, body.session.isoformat(), fault=body.fault)
        )
        if result["state"] != "COMPLETE":
            response.status_code = 202
        return result

    @app.get("/decisions/{decision_id}")
    def decision(decision_id: str):
        return safely(lambda: service.get_decision(decision_id))

    @app.post("/decisions/{decision_id}/reveal")
    def reveal(decision_id: str):
        return safely(lambda: service.reveal_outcome(decision_id))

    @app.get("/evaluation")
    def evaluation():
        return safely(service.evaluation)

    @app.get("/operations")
    def operations():
        return safely(service.operations)

    @app.post("/reconcile")
    def reconcile():
        return safely(service.reconcile)

    return app
