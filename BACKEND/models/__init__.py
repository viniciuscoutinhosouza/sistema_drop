# Importar todos os modelos para garantir registro no SQLAlchemy ORM
from models.user import User, ACProfile, RefreshToken, AccessPlan, ACSubscription, AccountAdministrator
from models.go import GO
from models.warehouse import Warehouse
from models.product import Category, CatalogProduct, CatalogProductImage, CatalogProductVariant, DropshipperProduct, DropshipperProductImage, ProductListing
from models.cmig import CMIG, CMIGAdministrator, CMIGProduct, CMIGProductImage
from models.nfe_config import NFeConfig
from models.integration import MarketplaceAccount, AccountBalance, AccountTransaction, OTPVerification
from models.order import Order, OrderItem
from models.kit import Kit, KitComponent
from models.financial import FinancialTransaction
from models.notification import Notification
from models.return_ import Return
from models.webhook import WebhookEvent
