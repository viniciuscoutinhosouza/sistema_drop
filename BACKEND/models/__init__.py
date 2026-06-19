# Importar todos os modelos para garantir registro no SQLAlchemy ORM
from models.cmig import (  # noqa: F401
    CMIG,
    CMIGAdministrator,
    CMIGProduct,
    CMIGProductComponent,
    CMIGProductImage,
)
from integrations.eship.config import EShipConfig  # noqa: F401 — módulo isolado eShip
from models.competitor_analysis import CompetitorAnalysis  # noqa: F401
from models.dre import DREEntry, DRESnapshot  # noqa: F401
from models.financial import FinancialTransaction  # noqa: F401
from models.fiscal import (  # noqa: F401
    CFOPCode,
    CMIGFiscalConfig,
    DFeSyncLog,
    ICMSRate,
    Invoice,
    InvoiceEvent,
    InvoiceItem,
    NCMCode,
)
from models.full_stock import FullCnpj, FullStock  # noqa: F401
from models.go import GO  # noqa: F401
from models.integration import (  # noqa: F401
    AccountBalance,
    AccountTransaction,
    MarketplaceAccount,
    OTPVerification,
)
from models.inventory import Inventory, InventoryItem  # noqa: F401
from models.messages import (  # noqa: F401
    AIConfig,
    CMIGAIConfig,
    ConversationMessage,
    ConversationThread,
)
from models.nfe_config import NFeConfig  # noqa: F401
from models.notification import Notification  # noqa: F401
from models.order import Order, OrderItem  # noqa: F401
from models.person import Person  # noqa: F401
from models.picking import (  # noqa: F401
    PickingCart,
    PickingCartItem,
    PickingCartOrder,
)
from models.product import (  # noqa: F401
    CatalogProduct,
    CatalogProductComponent,
    CatalogProductImage,
    CatalogProductVariant,
    Category,
    DropshipperProduct,
    DropshipperProductImage,
    MLFullTariff,
    ProductListing,
)
from models.return_ import Return  # noqa: F401
from models.scheduler_job_execution import SchedulerJobExecution  # noqa: F401
from models.smtp_config import SMTPConfig  # noqa: F401
from models.stock_adjustment import StockManualAdjustment  # noqa: F401
from models.user import (  # noqa: F401
    AccessPlan,
    AccountAdministrator,
    ACProfile,
    ACSubscription,
    RefreshToken,
    User,
)
from models.warehouse import Warehouse  # noqa: F401
from models.webhook import WebhookEvent  # noqa: F401
