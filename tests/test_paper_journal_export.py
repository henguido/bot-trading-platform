from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models
from backend.app.auth import get_current_user, get_db
from backend.routes.transacciones_routes import router


def _app_con_datos():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        u1 = models.User(nombre="uno", email="uno@example.com", password_hash="x")
        u2 = models.User(nombre="dos", email="dos@example.com", password_hash="x")
        db.add_all([u1, u2])
        db.flush()
        l1 = models.PaperLedger(usuario_id=u1.id, initial_capital_usd=500.0)
        l2 = models.PaperLedger(usuario_id=u2.id, initial_capital_usd=500.0)
        db.add_all([l1, l2])
        db.flush()
        db.add_all([
            models.PaperOperacion(
                ledger_id=l1.id,
                symbol="BTCUSDT",
                side="BUY",
                reference_price=100.0,
                fill_price=100.1,
                base_quantity=0.1,
                quote_gross=10.01,
                fee_usd=0.01,
                quote_net=10.02,
                slippage_bps=10.0,
                fee_taker_bps=10.0,
                strategy="=FORMULA",
                expected_edge_bps=40.0,
                expected_cost_bps=20.0,
                expected_net_bps=20.0,
                creada_en=datetime(2026, 8, 27, 12, 0, 0),
            ),
            models.PaperOperacion(
                ledger_id=l2.id,
                symbol="ETHUSDT",
                side="BUY",
                reference_price=200.0,
                fill_price=200.2,
                base_quantity=0.05,
                quote_gross=10.01,
                fee_usd=0.01,
                quote_net=10.02,
                slippage_bps=10.0,
                fee_taker_bps=10.0,
                strategy="OTRO_USUARIO",
                creada_en=datetime(2026, 8, 27, 12, 0, 0),
            ),
        ])
        db.commit()
        user_id = u1.id

    app = FastAPI()
    app.include_router(router)

    def db_override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def user_override():
        with Session() as db:
            return db.get(models.User, user_id)

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = user_override
    return TestClient(app), engine


def test_export_json_aisla_usuario_y_conserva_economia():
    client, engine = _app_con_datos()
    try:
        r = client.get("/api/paper/journal/export?formato=json")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "PAPER"
        assert body["count"] == 1
        assert len(body["operations"]) == 1
        op = body["operations"][0]
        assert op["symbol"] == "BTCUSDT"
        assert op["strategy"] == "=FORMULA"
        assert op["expected_net_bps"] == 20.0
        assert "ETHUSDT" not in r.text
        assert "OTRO_USUARIO" not in r.text
    finally:
        engine.dispose()


def test_export_csv_tiene_headers_y_neutraliza_formula_injection():
    client, engine = _app_con_datos()
    try:
        r = client.get("/api/paper/journal/export?formato=csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert r.headers["content-disposition"] == "attachment; filename=paper-journal.csv"
        assert r.headers["x-paper-operation-count"] == "1"
        assert "symbol,side,reference_price" in r.text
        assert "BTCUSDT" in r.text
        assert "'=FORMULA" in r.text
        assert "ETHUSDT" not in r.text
    finally:
        engine.dispose()


def test_export_formato_invalido_falla_con_422():
    client, engine = _app_con_datos()
    try:
        r = client.get("/api/paper/journal/export?formato=xlsx")
        assert r.status_code == 422
    finally:
        engine.dispose()
