# Railway Deployment

This guide deploys the existing DataPulse services from the repository root.
It keeps the existing application logic and uses Railway's managed PostgreSQL
service for durable warehouse storage.

## Deployment findings

| Area | Finding |
|---|---|
| Warehouse API | FastAPI instance `app` in `app/api/app.py`; route module is `app/api/routes.py`. |
| Dashboard | Streamlit entry point `dashboard/app.py`. |
| Mock source API | FastAPI instance `app` in `app/api/mock_app.py`; its health endpoint is `/health`. |
| Database connection | `app/warehouse/connection.py` creates the SQLAlchemy engine from `DATABASE_URL`. If it is unset, the code falls back to a SQLite file under the project root. |
| Dockerfile | One multi-purpose `Dockerfile`; it installs `requirements.txt`, copies the repository, and defaults to `python main.py --pipeline`. Each Railway web service must override that default start command. |
| Dependencies | `requirements.txt` is installed by the Dockerfile. Python 3.12 is the image runtime. `pyproject.toml` has a separate, smaller dependency list; use `requirements.txt` for this Docker deployment. There is no dependency lockfile. |
| Database initialization | The API lifespan and pipeline loader call SQLAlchemy `Base.metadata.create_all`; repeating it is safe for existing tables. This is not a schema migration system and does not alter existing tables. |
| SQL scripts | `sql/schema/01_init_warehouse.sql` and `sql/migrations/02_expand_surrogate_keys_to_bigint.sql` are manual SQL, not automatically run by the application. The DDL script uses a `warehouse` schema, while the ORM uses its default schema. Do not separately run that DDL for the Railway deployment described here. |
| Health checks | Warehouse API: `/health` (also tests the database); mock source API: `/health`; Streamlit dashboard: `/`. The pipeline job has no HTTP health endpoint. |
| Local files | `data/raw/customers.csv` is a tracked pipeline input. Quarantine CSV/JSONL files, exported reports, and logs are written to local directories and are not durable across Railway redeploys. Quarantine records are also stored in PostgreSQL. |
| Existing deployment defaults | `main.py --api` binds to the configured default `127.0.0.1:8001`; `main.py --source-api` binds to `127.0.0.1:8000`; dashboard defaults to Streamlit's port. These development launchers do not use Railway's `PORT`. Use the Railway start commands below, which bind to `0.0.0.0` and read `$PORT`. |

### Environment variables read by the application

All names below are read in `app/config/settings.py`. Values shown as defaults
are development defaults, not safe production connection settings.

The Docker build installs `requirements.txt`, not the dependency list in
`pyproject.toml`. Keep this distinction in mind if dependency metadata is
updated later; dependency versions currently use minimum bounds rather than a
lockfile.

| Variable | Code default | Railway use |
|---|---|---|
| `APP_NAME` | `DataPulse` | Optional. |
| `APP_ENV` | `development` | Dockerfile sets `production`; keep that value for deployed services. |
| `DEBUG` | `false` | Optional; leave disabled. |
| `LOG_LEVEL` | `INFO` | Optional. |
| `RANDOM_SEED` | `42` | Optional; affects generated source data. |
| `DATABASE_URL` | SQLite file in the project root | **Required** for API, dashboard, and pipeline. Reference the Railway PostgreSQL service's `DATABASE_URL`; do not use SQLite or a localhost URL. |
| `DB_ECHO` | `false` | Optional; leave disabled unless SQL logging is intentionally needed. |
| `POSTGRES_DB` | `datapulse_dw` | Used by the Compose setup; the application engine does not build its connection from this variable. |
| `POSTGRES_USER` | `datapulse` | Used by the Compose setup; use Railway's `DATABASE_URL` in deployed application services. |
| `POSTGRES_PASSWORD` | `datapulse_secure_pass` | Local Compose default only. Do not use this sample password in production. |
| `POSTGRES_HOST` | `localhost` | Local Compose default; not used by the SQLAlchemy engine. |
| `POSTGRES_PORT` | `5432` | Local Compose default; not used by the SQLAlchemy engine. |
| `API_HOST` | `127.0.0.1` | Development launcher default; Railway web commands below bind to `0.0.0.0` directly. |
| `API_PORT` | `8000` | Local mock-source port default. |
| `API_BASE_URL` | `http://<API_HOST>:<API_PORT>` | Only needed if explicitly using HTTP ingestion from a separately deployed source API. The normal pipeline uses an in-process mock ASGI client. |
| `APP_API_PORT` | `8001` | Development launcher default; use `APP_API_BASE_URL` for the dashboard's API connection. |
| `APP_API_BASE_URL` | `http://<API_HOST>:<APP_API_PORT>` | Required by the dashboard to reach the application API. Set it to the API service's Railway private URL. |
| `API_TIMEOUT_SECONDS` | `10.0` | Optional; used for HTTP source requests. |
| `API_PAGE_SIZE` | `50` | Optional. |
| `BATCH_SIZE` | `500` | Optional. |
| `RETRY_ATTEMPTS` | `3` | Optional. |
| `RETRY_BACKOFF_FACTOR` | `0.5` | Optional. |
| `INJECT_DIRTY_DATA_RATIO` | `0.08` | Optional; used by the mock data generator. |

`PORT` is not read by `Settings`; the Railway start commands consume the
platform-provided `PORT` at process launch. Railway private-network and variable
references used below are platform values, not application-defined variables.
The Docker image contains `.env.example`, and `settings.py` loads it when `.env`
is absent. That example sets a SQLite `DATABASE_URL`, so explicitly provide the
Railway PostgreSQL reference to every database-using service.

## Railway service plan

Use the repository root (`.`) for every application service. Railway detects
the repository `Dockerfile`; leave the custom build command blank. The Dockerfile
installs dependencies with `pip install --no-cache-dir -r requirements.txt`.
Override its default pipeline command on web services as shown.

| Railway service | Root directory | Dockerfile | Build command | Start command | Required variables | Internal connections | Public domain | Health-check path |
|---|---|---|---|---|---|---|---|---|
| `Postgres` | Railway PostgreSQL service (not a repository directory) | Railway-managed | Railway-managed | Railway-managed | None to add manually | The application services reference `Postgres.DATABASE_URL`. Keep database access private. | No | Managed by Railway |
| `application-api` | `.` | `Dockerfile` | None; use Dockerfile | `sh -c 'exec uvicorn app.api.app:app --host 0.0.0.0 --port "$PORT"'` | `DATABASE_URL=${{Postgres.DATABASE_URL}}`; `APP_ENV=production` (already set by the Dockerfile) | Connects to `Postgres` over its internal URL. The dashboard calls this API using its private domain. | **Yes, recommended** for Swagger/API clients; the dashboard itself uses private networking. | `/health` |
| `dashboard` | `.` | `Dockerfile` | None; use Dockerfile | `sh -c 'exec streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port "$PORT"'` | `DATABASE_URL=${{Postgres.DATABASE_URL}}`; `APP_API_BASE_URL=http://${{application-api.RAILWAY_PRIVATE_DOMAIN}}:${{application-api.PORT}}` | Connects directly to `Postgres` and privately to `application-api`. | **Yes** | `/` |
| `pipeline` (optional scheduled job) | `.` | `Dockerfile` | None; use Dockerfile | `python scripts/run_pipeline.py` | `DATABASE_URL=${{Postgres.DATABASE_URL}}`; `APP_ENV=production` (already set by the Dockerfile) | Connects to `Postgres`. The normal pipeline uses the in-process mock source and does not need the mock API service. | No | Not applicable; this is a one-shot job |
| `mock-source-api` (optional) | `.` | `Dockerfile` | None; use Dockerfile | `sh -c 'exec uvicorn app.api.mock_app:app --host 0.0.0.0 --port "$PORT"'` | `APP_ENV=production` (already set by the Dockerfile); optional `RANDOM_SEED`. If keeping it private without a generated domain, set `PORT=8000` explicitly. | Not required by the normal pipeline. If HTTP ingestion is deliberately used, set `API_BASE_URL` on the calling service to `http://${{mock-source-api.RAILWAY_PRIVATE_DOMAIN}}:${{mock-source-api.PORT}}`. | No for the default deployment; generate a domain only if it must be reachable from outside Railway. | `/health` |

`Postgres` above is the exact Railway service name used in the references. If you
choose a different name, update the service-reference namespace accordingly.
Railway's private host format is `<service-name>.railway.internal`; the
`RAILWAY_PRIVATE_DOMAIN` reference resolves the actual internal hostname.

The application API is given a public domain in this plan so Railway provisions
its HTTP port and users can open `/docs`. It remains accessible to the dashboard
through its private domain. If the API must be private-only, explicitly set a
`PORT` value on that service and use the same value in the dashboard's private
`APP_API_BASE_URL`; do not assume the development port defaults are the
platform-assigned port. The optional private-only mock service likewise needs an
explicit `PORT` value, matching the port in `API_BASE_URL`.

## Deploy

1. **Push the desired code to GitHub.** Railway deploys the GitHub branch, not
   the local working tree. In the inspected workspace, `app/warehouse/loader.py`
   has an uncommitted local change, and there are also unrelated local/generated
   changes. Decide which changes belong in the deployment and commit/push only
   those. Do not assume Railway will receive unpushed changes.
2. In Railway, create a project from the GitHub repository and select the branch
   to deploy. Add a PostgreSQL service and name it `Postgres` (or adjust the
   references above to its actual service name).
3. Add an application API service from the same repository. Set the root
   directory to `.`, use `Dockerfile`, leave the build command empty, set the
   start command and variables from the `application-api` row, and generate a
   public domain. Deploy it first. Its startup calls `create_all`; wait for
   deployment health to pass at `/health`.
4. Add the dashboard service from the same repository. Set its root directory
   to `.`, use `Dockerfile`, leave the build command empty, and configure the
   `dashboard` start command and variables. Generate a public domain. The
   dashboard reads the warehouse directly and calls the application API using
   the private URL; do not set that URL to `localhost` or the API's public URL.
5. Optionally add the `pipeline` service if runs should be scheduled
   independently of the dashboard/API. Configure it as a Railway Cron service
   using `python scripts/run_pipeline.py`, and choose the desired schedule in
   Railway. It runs once per schedule and reads the tracked
   `data/raw/customers.csv`. It does not need `API_BASE_URL` or a separately
   deployed mock source service. The dashboard's pipeline action can also invoke
   a run through the application API.
6. Only add `mock-source-api` if you need to call or inspect that separate
   service over HTTP. It is not a dependency of the default pipeline; the source
   app initializes deterministic sample data in memory on startup.
7. Verify the generated domains:
   - Application API: `https://<application-api-domain>/health` and
     `https://<application-api-domain>/docs`
   - Dashboard: `https://<dashboard-domain>/`
   - Optional mock source API: `https://<mock-source-api-domain>/health`

In the service Variables UI, use Railway reference variables rather than copying
database credentials. The key production setting is `DATABASE_URL`, and it must
resolve to the Railway PostgreSQL service, not the local SQLite fallback.
Railway PostgreSQL provides persistent database storage; do not attach an
application filesystem volume to store the warehouse.

## Persistence and schema changes

- The application creates missing ORM tables on API startup and when the
  pipeline initializes its schema. This is safe to repeat for a fresh/current
  schema.
- `create_all` does not apply or repair alterations to existing tables. Review
  and apply future schema changes as deliberate PostgreSQL migrations before
  deploying code that depends on them.
- `docker/init.sql` and `sql/schema/01_init_warehouse.sql` are for the existing
  Docker workflow, not Railway's managed database initialization. The first
  script grants permissions to a hard-coded local Compose user; the SQL schema
  script creates objects under `warehouse`, unlike the ORM's default schema.
- Local files under `data/quarantine`, `data/processed`, and `logs` are
  disposable on Railway. The pipeline also records quarantine rows in the
  database. Use an external object store if exported files need durable storage;
  no object-store integration is currently configured in this project.

Railway references: [private networking](https://docs.railway.com/networking/private-networking)
and [service variables](https://docs.railway.com/variables).

## Validation performed

- The FastAPI warehouse API returned a healthy `/health` response when launched
  on `0.0.0.0` using a `PORT` environment value.
- The Streamlit dashboard returned HTTP 200 on `/` when launched on
  `0.0.0.0` using a `PORT` environment value.
- The optional mock source API returned healthy status from `/health` on
  `0.0.0.0` using a `PORT` environment value.
- These local smoke tests used the repository's SQLite database. Docker is not
  installed in the inspected environment, and no Railway project/database
  credentials are available here, so a Docker image build and live Railway
  PostgreSQL/private-network connection could not be verified in this workspace.
