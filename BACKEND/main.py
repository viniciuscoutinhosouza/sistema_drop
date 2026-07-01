import sys

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os as _os
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import models  # noqa: F401 — registra todos os ORM models no SQLAlchemy
from config import get_settings
from logging_filters import install_log_redaction
from socket_manager import sio

# Redige token/segredos das query strings nos logs (o token JWT do WebSocket vinha em texto
# claro no access log do uvicorn). Idempotente; instalado o quanto antes.
install_log_redaction()

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("MIG ECOMMERCE API starting...")
    # Reforça a redação anexando o filtro também aos handlers já criados pelo uvicorn
    # (pega records que sobem por propagação de loggers-filho não listados).
    install_log_redaction(include_handlers=True)

    # Executor default do asyncio: usado por asyncio.to_thread nas chamadas
    # bloqueantes NÃO-banco (SEFAZ mTLS, geração de DANFE/PDF, email). O banco tem
    # executor PRÓPRIO (database._DB_EXECUTOR). Sem este ajuste o default fica em
    # ~5 threads (min(32, cpu+4)) numa VM de 1 vCPU — gargalo do incidente 2026-07-01.
    import asyncio as _asyncio
    from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor

    _asyncio.get_running_loop().set_default_executor(
        _ThreadPoolExecutor(
            max_workers=settings.ASYNCIO_DEFAULT_EXECUTOR_WORKERS,
            thread_name_prefix="io",
        )
    )

    from tasks.scheduler import start_scheduler

    start_scheduler()
    yield
    # Shutdown
    from tasks.scheduler import stop_scheduler

    stop_scheduler()
    print("MIG ECOMMERCE API shutting down...")


app = FastAPI(
    title="MIG ECOMMERCE API",
    description="Sistema de Gestão de Contas de Marketplace – MIG ECOMMERCE",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Import and register routers
from routers import (
    admin_api_console,
    ai_config,
    anuncios,
    auth,
    campaign_ads,
    catalog,
    cfop,
    claims,
    cmig_reports,
    cmigs,
    competitor_analysis,
    dashboard,
    financial,
    fiscal_config,
    full_cnpjs,
    goes,
    integrations,
    inventories,
    invites,
    invoices,
    listings,
    manual_orders,
    marketplace_settings,
    media,
    message_templates,
    messages,
    ncm,
    notifications,
    orders,
    people,
    product_categories,
    products,
    profiles,
    returns,
    sales_report,
    scheduler_monitoring,
    separation,
    settings_email,
    simulator,
    stock,
    supplier_products,
    users,
    warehouse,
    webhooks,
)

PREFIX = "/api/v1"

app.include_router(auth.router, prefix=f"{PREFIX}/auth", tags=["Auth"])
app.include_router(users.router, prefix=f"{PREFIX}/users", tags=["Users"])
app.include_router(dashboard.router, prefix=f"{PREFIX}/dashboard", tags=["Dashboard"])
app.include_router(financial.router, prefix=f"{PREFIX}/financial", tags=["Financial"])
app.include_router(catalog.router, prefix=f"{PREFIX}/catalog", tags=["Catalog"])
app.include_router(supplier_products.router, prefix=f"{PREFIX}/pg", tags=["PG - Produto Geral"])
app.include_router(products.router, prefix=f"{PREFIX}/products", tags=["Products"])
app.include_router(orders.router, prefix=f"{PREFIX}/orders", tags=["Orders"])
app.include_router(manual_orders.router, prefix=f"{PREFIX}/manual-orders", tags=["ManualOrders"])
app.include_router(integrations.router, prefix=f"{PREFIX}/accounts", tags=["Accounts"])
app.include_router(
    listings.router, prefix=f"{PREFIX}/products/{{product_id}}/listings", tags=["Listings"]
)
app.include_router(returns.router, prefix=f"{PREFIX}/returns", tags=["Returns"])
app.include_router(stock.router, prefix=f"{PREFIX}/stock", tags=["Stock"])
app.include_router(inventories.router, prefix=f"{PREFIX}/inventories", tags=["Inventories"])
app.include_router(full_cnpjs.router, prefix=f"{PREFIX}/full-cnpjs", tags=["FullCNPJs"])
app.include_router(notifications.router, prefix=f"{PREFIX}/notifications", tags=["Notifications"])
app.include_router(webhooks.router, prefix=f"{PREFIX}/webhooks", tags=["Webhooks"])
app.include_router(warehouse.router, prefix=f"{PREFIX}/warehouse", tags=["Warehouse"])
app.include_router(goes.router, prefix=f"{PREFIX}/goes", tags=["GOs"])
app.include_router(cmigs.router, prefix=f"{PREFIX}/cmigs", tags=["CMIGs"])
app.include_router(anuncios.router, prefix=f"{PREFIX}/anuncios", tags=["Anuncios"])
app.include_router(campaign_ads.router, prefix=f"{PREFIX}/campaign-ads", tags=["CampaignAds"])
app.include_router(claims.router)
app.include_router(message_templates.router)
app.include_router(
    product_categories.router,
    prefix=f"{PREFIX}/product-categories",
    tags=["ProductMarketplaceCategories"],
)
app.include_router(simulator.router, prefix=f"{PREFIX}/simulator", tags=["Simulator"])
app.include_router(competitor_analysis.router, prefix=f"{PREFIX}/competitor-analysis", tags=["CompetitorAnalysis"])
app.include_router(people.router, prefix=f"{PREFIX}/people", tags=["People"])
app.include_router(
    fiscal_config.router, prefix=f"{PREFIX}/cmigs/{{cmig_id}}/fiscal-config", tags=["FiscalConfig"]
)
app.include_router(
    cmig_reports.router, prefix=f"{PREFIX}/cmigs/{{cmig_id}}/reports", tags=["CMIGReports"]
)
app.include_router(sales_report.router, prefix=f"{PREFIX}/reports", tags=["Reports"])
app.include_router(invoices.router, prefix=f"{PREFIX}/invoices", tags=["Invoices"])
app.include_router(cfop.router, prefix=f"{PREFIX}/cfop", tags=["CFOP"])
app.include_router(ncm.router, prefix=f"{PREFIX}/ncm", tags=["NCM"])
app.include_router(invites.router, prefix=f"{PREFIX}/invites", tags=["Invites"])
app.include_router(
    admin_api_console.router,
    prefix=f"{PREFIX}/admin/api-console",
    tags=["AdminAPIConsole"],
)
app.include_router(messages.router)
app.include_router(ai_config.router)
app.include_router(marketplace_settings.router)
app.include_router(media.router)
app.include_router(
    scheduler_monitoring.router, prefix=f"{PREFIX}/scheduler", tags=["SchedulerMonitoring"]
)
app.include_router(profiles.router, prefix=f"{PREFIX}/profiles", tags=["Profiles"])
app.include_router(separation.router, prefix=f"{PREFIX}/separation", tags=["Separation"])
app.include_router(
    settings_email.router, prefix=f"{PREFIX}/settings/email", tags=["SettingsEmail"]
)

# Módulo isolado de integração eShip (WMS)
from integrations.eship.router import router as eship_router  # noqa: E402

app.include_router(eship_router, prefix=f"{PREFIX}/integrations/eship", tags=["eShip"])


_os.makedirs("static/uploads/cmig-products", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return {"status": "ok", "system": "MIG ECOMMERCE"}


# Mount Socket.io as ASGI sub-application at /ws/socket.io
socket_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="ws/socket.io")
