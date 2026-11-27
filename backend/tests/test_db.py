"""Database migration, PRAGMA, constraint, cascade, and seed tests."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from app.db.engine import create_sqlite_engine, run_quick_check
from app.db.models import DataSource, Household, Member
from app.db.seed import seed_data_sources
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "household",
    "member",
    "location",
    "settings",
    "data_source",
    "aqi_observation",
    "daily_plan",
    "plan_item",
    "conversation",
    "message",
    "emission_factor",
    "activity_log",
    "report",
}


def _make_alembic_cfg(db_path: Path) -> AlembicConfig:
    cfg = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return cfg


def test_alembic_upgrade_and_downgrade_from_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "migrations.db"
    cfg = _make_alembic_cfg(db_path)

    command.upgrade(cfg, "head")
    engine = create_sqlite_engine(db_path)
    inspector = inspect(engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_sqlite_engine(db_path)
    inspector = inspect(engine)
    remaining = set(inspector.get_table_names()) - {"alembic_version"}
    assert remaining == set()
    engine.dispose()


def test_pragmas_constraints_cascades_and_seed(tmp_path: Path) -> None:
    db_path = tmp_path / "constraints.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "head")
    engine = create_sqlite_engine(db_path)

    try:
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys;")).scalar_one() == 1
            assert str(conn.execute(text("PRAGMA journal_mode;")).scalar_one()).lower() == "wal"
            assert conn.execute(text("PRAGMA busy_timeout;")).scalar_one() == 5000
            assert conn.execute(text("PRAGMA synchronous;")).scalar_one() == 1

        assert run_quick_check(engine) is True

        with Session(engine) as session:
            seed_data_sources(session)
            seed_data_sources(session)
            sources = session.exec(select(DataSource)).all()
            assert {s.id for s in sources} == {"cpcb", "open_meteo"}

        # CHECK violation
        with Session(engine) as session:
            session.add(Household(mode="x"))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        # FK violation
        with Session(engine) as session:
            session.add(Member(household_id="non-existent-id", kind="adult", count=1))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        # Cascade delete from household -> member
        with Session(engine) as session:
            household = Household(mode="local")
            session.add(household)
            session.commit()
            session.refresh(household)
            household_id = household.id

            session.add(Member(household_id=household_id, kind="child_u12", count=1))
            session.commit()

            session.delete(household)
            session.commit()

            members = session.exec(select(Member).where(Member.household_id == household_id)).all()
            assert members == []
    finally:
        engine.dispose()
