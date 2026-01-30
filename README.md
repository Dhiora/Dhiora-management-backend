## Management Backend - Auth Service

This project is a multi-tenant, workflow-driven SaaS backend built with **FastAPI** and **PostgreSQL**.

This iteration focuses on **Register** and **Login** APIs with:
- Multi-tenant support (`tenant_id` everywhere)
- JWT-based authentication
- Role-based and module-based access via database
- Production-oriented error handling

### Setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set environment variables (or use a `.env` file):

- `DATABASE_URL` – PostgreSQL DSN (e.g. `postgresql+asyncpg://user:pass@host:5432/dbname`)
- `JWT_SECRET_KEY` – strong random string
- `JWT_ALGORITHM` – typically `HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES` – e.g. `15`
- `REFRESH_TOKEN_EXPIRE_DAYS` – e.g. `7`

4. Run the app:

```bash
uvicorn app.main:app --reload
```

The auth endpoints will be available under `/api/v1/auth`.

