import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import socketio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings
from socket_manager import sio

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("MIG ECOMMERCE API starting...")
    from tasks.scheduler import start_scheduler
    start_scheduler()
    yield
    # Shutdown
    from tasks.scheduler import stop_scheduler
    stop_scheduler()
    print("MIG ECOMMERCE API shutting down...")


app = FastAPI(
    title="MIG ECOMMERCE API",
    description="Sistema de Gestão de Dropshipping – MIG ECOMMERCE",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register routers
from routers import (
    auth,
    users,
    dashboard,
    financial,
    catalog,
    supplier_products,
    products,
    kits,
    orders,
    manual_orders,
    integrations,
    returns,
    notifications,
    webhooks,
)

PREFIX = "/api/v1"

app.include_router(auth.router,              prefix=f"{PREFIX}/auth",           tags=["Auth"])
app.include_router(users.router,             prefix=f"{PREFIX}/users",          tags=["Users"])
app.include_router(dashboard.router,         prefix=f"{PREFIX}/dashboard",      tags=["Dashboard"])
app.include_router(financial.router,         prefix=f"{PREFIX}/financial",      tags=["Financial"])
app.include_router(catalog.router,           prefix=f"{PREFIX}/catalog",        tags=["Catalog"])
app.include_router(supplier_products.router, prefix=f"{PREFIX}/supplier",       tags=["Supplier"])
app.include_router(products.router,          prefix=f"{PREFIX}/products",       tags=["Products"])
app.include_router(kits.router,              prefix=f"{PREFIX}/kits",           tags=["Kits"])
app.include_router(orders.router,            prefix=f"{PREFIX}/orders",         tags=["Orders"])
app.include_router(manual_orders.router,     prefix=f"{PREFIX}/manual-orders",  tags=["ManualOrders"])
app.include_router(integrations.router,      prefix=f"{PREFIX}/integrations",   tags=["Integrations"])
app.include_router(returns.router,           prefix=f"{PREFIX}/returns",        tags=["Returns"])
app.include_router(notifications.router,     prefix=f"{PREFIX}/notifications",  tags=["Notifications"])
app.include_router(webhooks.router,          prefix=f"{PREFIX}/webhooks",       tags=["Webhooks"])


@app.get("/")
async def root():
    return {"status": "ok", "system": "MIG ECOMMERCE"}


# Mount Socket.io as ASGI sub-application at /ws
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
