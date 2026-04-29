Preciso que ao criar um produto a partir do Anuncio de um marketplace, o sistema leve para o Produto CMIG os seguintes campos:
TITLE_OVERRIDE
SALE_PRICE
CATEGORY_NAME : Nome completo da Categoria, em texto, nao precisa do ID da categoria porque para cada Marketplace sera um ID diferente e será definido no envio para o Marketplace.
DESCRIPTION_OVERRIDE
ATTRIBUTE_JSON
AVAILABLE_QUANTITY
VIDEO_ID
SKU
WEIGHT_KG
HEIGHT_CM
WIDTH_CM
LENGTH_CM
PICTURES_JSON
FISCAL_JSON
>>> para cada VARIANT o sistema deve levar os campos
SKU
STOCK_QUANTITY
SALE_PRICE
ATTRIBUTE_JSON : Nesse campo o sistema deve gravar o assunto da variação, como COR, Tamanho, Voltagem, etc. e o VALOR da Variação como "Azul", "Pequeno", etc

