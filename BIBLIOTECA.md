 developers.mercadolibre.com

 https://developers.mercadolivre.com.br/pt_br/guia-para-produtos

 https://global-selling.mercadolibre.com/devsite/introduction-globalselling

 https://developers.mercadoenvios.com/

 https://www.mercadopago.com.br/developers/pt



Aplicação Mercado Livre

ID do aplicativo   6712718703908494
Chave de Acesso    Z6bbtskvAUc9R9EZKkpQ7cAfvUZZ6d4e




SHOPEE

https://open.shopee.com/developer-guide/4
https://open.shopee.com/documents/v2/v2.ams.get_open_campaign_added_product?module=127&type=1
https://open.shopee.com/push-mechanism/5







# Oracle ATP
ORACLE_USER=admin
ORACLE_PASSWORD=#Ehyxip0744#
ORACLE_DSN=migecommerce_tp
ORACLE_WALLET_DIR=C:/sistema_drop/Wallet_MIGECOMMERCE
ORACLE_WALLET_PASSWORD=#Ehyxip0744#


# JWT
JWT_SECRET=Sistema_de_Ecommerce_MIG
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
JWT_REFRESH_EXPIRE_DAYS=30

# Frontend CORS
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173

# Mercado Livre (App ID: 6712718703908494)
ML_APP_ID=6712718703908494
ML_CLIENT_SECRET=Z6bbtskvAUc9R9EZKkpQ7cAfvUZZ6d4e
ML_REDIRECT_URI=https://unvalued-hybrid-primal.ngrok-free.dev/api/v1/accounts/ml/callback

# Shopee
SHOPEE_PARTNER_ID=
SHOPEE_PARTNER_KEY=
SHOPEE_REDIRECT_URI=http://localhost:8000/api/v1/integrations/shopee/callback

# Platform fee per order (R$)
PLATFORM_FEE=2.00






## GITHUB

### Atualizar o Projeto Local
cd "c:\Sistema_Drop" && git pull origin master

### Atualizar o Repositorio do Github
cd "c:\Sistema_Drop" && git status && git log --oneline -3

cd "c:\Sistema_Drop" && git add -A && git commit -m 

cd "c:\Sistema_Drop" && git push origin master