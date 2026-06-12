"""Módulo isolado de integração com o eShip (WMS / Gestão Logística).

Toda a lógica de API, payloads, status e regras do eShip vive aqui. Os arquivos
do core (main, models/__init__, scheduler) só fazem o registro mínimo:
  - main.py            -> include_router(integrations.eship.router.router, ...)
  - models/__init__.py -> from integrations.eship.config import EShipConfig
  - tasks/scheduler.py -> add_job(integrations.eship.tasks.sync_eship_status, ...)

API eShip: RPC. Endpoint único `POST {base_url}/?api&funcao=webServiceXxx`,
autenticação via header `api: <apikey>`. Sem webhooks → status por polling.
"""
