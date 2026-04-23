"""Migration 013: Create stationary schema and resell tables.

Tables created:
  stationary.resell_payments  — Razorpay listing-fee order tracking
  stationary.resell_items     — Resale item listings
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine

_STATEMENTS = [
    "CREATE SCHEMA IF NOT EXISTS stationary",

    """CREATE TABLE IF NOT EXISTS stationary.resell_payments (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id   UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        order_id    VARCHAR(100) NOT NULL UNIQUE,
        payment_id  VARCHAR(100),
        signature   VARCHAR(500),
        seller_type VARCHAR(20)  NOT NULL CHECK (seller_type IN ('STUDENT', 'PARENT')),
        seller_id   VARCHAR(100) NOT NULL,
        amount      INTEGER      NOT NULL,
        currency    VARCHAR(10)  NOT NULL DEFAULT 'INR',
        status      VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'PAID', 'FAILED')),
        txn_id      VARCHAR(50)  UNIQUE,
        expires_at  TIMESTAMPTZ,
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    )""",

    """CREATE INDEX IF NOT EXISTS idx_resell_payments_tenant
        ON stationary.resell_payments (tenant_id)""",

    """CREATE INDEX IF NOT EXISTS idx_resell_payments_txn_id
        ON stationary.resell_payments (txn_id)
        WHERE txn_id IS NOT NULL""",

    """CREATE TABLE IF NOT EXISTS stationary.resell_items (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id       UUID           NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        title           VARCHAR(255)   NOT NULL,
        description     TEXT,
        category        VARCHAR(100)   NOT NULL,
        condition       VARCHAR(20)    NOT NULL
                            CHECK (condition IN ('NEW', 'LIKE_NEW', 'GOOD', 'FAIR')),
        price           NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
        seller_type     VARCHAR(20)    NOT NULL CHECK (seller_type IN ('STUDENT', 'PARENT')),
        seller_id       VARCHAR(100)   NOT NULL,
        payment_txn_id  VARCHAR(50)    NOT NULL,
        images          JSONB          NOT NULL DEFAULT '[]',
        status          VARCHAR(30)    NOT NULL DEFAULT 'PENDING_APPROVAL'
                            CHECK (status IN (
                                'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'SOLD', 'INACTIVE'
                            )),
        is_active       BOOLEAN        NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
        CONSTRAINT fk_resell_item_txn
            FOREIGN KEY (payment_txn_id)
            REFERENCES stationary.resell_payments (txn_id)
    )""",

    """CREATE INDEX IF NOT EXISTS idx_resell_items_tenant
        ON stationary.resell_items (tenant_id)""",

    """CREATE INDEX IF NOT EXISTS idx_resell_items_status
        ON stationary.resell_items (tenant_id, status)
        WHERE is_active = TRUE""",

    """CREATE INDEX IF NOT EXISTS idx_resell_items_seller
        ON stationary.resell_items (tenant_id, seller_type, seller_id)
        WHERE is_active = TRUE""",
]


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        for stmt in _STATEMENTS:
            await conn.execute(text(stmt))
    print("Migration 013_create_stationary_resell_tables done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
