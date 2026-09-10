"""Opt-in isolated profiling wrapper; no normal application imports this module."""

import json
import time
from collections import Counter, deque
from contextvars import ContextVar
from functools import wraps

import fastapi.routing
from fastapi import Request
from performance_probe import app
from sqlalchemy import event

from backend.app.db import database
from backend.app.ml.registry import ArtifactRegistry, ModelCache
from ml.training.cash_flow import CashFlowModel
from ml.training.payment_risk import PaymentRiskModel
from ml.training.segmentation import SegmentationModel
from ml.training.transaction import TransactionModel

current = ContextVar("stage10_metrics", default=None)
records = deque(maxlen=20000)


def add(name, value):
    metrics = current.get()
    if metrics is not None:
        metrics[name] += value


original_get = database.engine.pool._do_get


def pool_get():
    start = time.perf_counter()
    try:
        return original_get()
    finally:
        add("pool_acquire_seconds", time.perf_counter() - start)


database.engine.pool._do_get = pool_get
original_db = database.get_db


async def profiled_db(request: Request):
    generator = original_db(request)
    start = time.perf_counter()
    try:
        try:
            session = await anext(generator)
        finally:
            add("admission_seconds", time.perf_counter() - start)
        yield session
    finally:
        await generator.aclose()


app.dependency_overrides[original_db] = profiled_db


@event.listens_for(database.engine, "before_cursor_execute")
def before(conn, cursor, statement, parameters, context, many):
    context._stage10_start = time.perf_counter()
    add("queries", 1)


@event.listens_for(database.engine, "after_cursor_execute")
def after(conn, cursor, statement, parameters, context, many):
    add("query_seconds", time.perf_counter() - context._stage10_start)


@event.listens_for(database.engine, "checkout")
def checkout(dbapi, record, proxy):
    record.info["stage10_start"] = time.perf_counter()
    record.info["stage10_metrics"] = current.get()


@event.listens_for(database.engine, "checkin")
def checkin(dbapi, record):
    metrics = record.info.pop("stage10_metrics", None)
    start = record.info.pop("stage10_start", None)
    if metrics is not None and start is not None:
        metrics["hold_seconds"] += time.perf_counter() - start


original_serialize = fastapi.routing.serialize_response


@wraps(original_serialize)
async def serialize(*args, **kwargs):
    start = time.perf_counter()
    try:
        return await original_serialize(*args, **kwargs)
    finally:
        add("serialization_seconds", time.perf_counter() - start)


fastapi.routing.serialize_response = serialize


def instrument(cls, method, metric):
    original = getattr(cls, method)

    @wraps(original)
    def measured(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            add(metric, time.perf_counter() - start)
            add(metric + "_calls", 1)

    setattr(cls, method, measured)


for model, method in [
    (TransactionModel, "predict"),
    (PaymentRiskModel, "predict"),
    (SegmentationModel, "predict"),
    (CashFlowModel, "forecast"),
]:
    instrument(model, method, "inference_seconds")
instrument(ArtifactRegistry, "load", "model_load_seconds")
instrument(ModelCache, "get_or_load", "model_cache_seconds")


class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        metrics = Counter()
        token = current.set(metrics)
        start = time.perf_counter()

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                metrics["status"] = message["status"]
                message["headers"].append(
                    (b"x-stage10", json.dumps(dict(metrics)).encode())
                )
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            metrics["total_seconds"] = time.perf_counter() - start
            route = scope.get("route")
            records.append({"endpoint": getattr(route, "path", "unknown"), **metrics})
            current.reset(token)


app.add_middleware(MetricsMiddleware)


@app.get("/__stage10", include_in_schema=False)
async def snapshot():
    return list(records)
