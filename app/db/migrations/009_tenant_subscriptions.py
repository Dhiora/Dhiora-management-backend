"""
Migration 009: Create core.tenant_subscriptions for Razorpay tenant (ERP/AI) subscriptions.

Run once:
  python -m app.db.migrations.009_tenant_subscriptions
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import engine


CREATE_TENANT_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS core.tenant_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
    subscription_plan_id UUID REFERENCES core.subscription_plans(id) ON DELETE SET NULL,
    category VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    razorpay_order_id VARCHAR(255),
    razorpay_payment_id VARCHAR(255),
    razorpay_signature VARCHAR(1024),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);
"""

CREATE_INDEX_TENANT_SUBSCRIPTIONS_TENANT = """
CREATE INDEX IF NOT EXISTS ix_tenant_subscriptions_tenant_id ON core.tenant_subscriptions(tenant_id);
"""


async def run_migration(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(CREATE_TENANT_SUBSCRIPTIONS))
        await conn.execute(text(CREATE_INDEX_TENANT_SUBSCRIPTIONS_TENANT))
    print("Migration 009_tenant_subscriptions done.")


if __name__ == "__main__":
    asyncio.run(run_migration(engine))
