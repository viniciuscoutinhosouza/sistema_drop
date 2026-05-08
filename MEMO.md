Quero que vc refatore a pagina de "Kits" da seguinte forma:

O que é um KIT?
O KIT é um produto CMIG, composto de outros produtos CMIG, de uma conta CMIG , onde o usuario vai cadastrar mais de uma unidade de um produto ou varios Produtos. Ou seja, por exemplo: 
kit 1: 5 unidades do produto "A"; 
kit 2; 2 unidades do produto "A" + 3 unidades do produto "B"

Quando o Operador Logistico for separar o pedido, deve separar as quantidades de cada produto no mesmo pedido. E a Nota Fiscal será emitida uma nota para todos os itens

Como Criar?
O usuario ao criar um Kit, vai estar criando um Produto CMIG - Composto,  apenas para a conta CMIG selecionada. Depois do Produto composto criado a publicação do anuncio deve sequir identica com a publicação de um produto.

Para criar um Produto CMIG Composto o Usuario deve Adicionar os produtos ou do Catalogo PG ou produtos da CMIG (Os kits podem ser montados com produtos dos dois catalogos), informar a quantidade de cada produto adicionado. O estoque do Prod CMIG Composto, será sempre calculado conforme a quantidade do Produtos real, e a quantidade do item adicionado.

Apenas o usuario UGO pode criar Prod PG Compostos, apenas com os produtos do catalogo PG


veja se ficou clara a explicação, planeje a implementação e me apresente. Caso tenha duvidas pode fazer quantas perguntas forem necessárias


