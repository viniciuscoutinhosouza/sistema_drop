<template>
  <div class="modal-backdrop-custom" @click.self="$emit('close')">
    <div class="help-card">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h5 class="mb-0"><i class="fas fa-dolly text-primary mr-2"></i>Como funciona a Logística / Separação</h5>
        <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
      </div>

      <!-- 1. Para que serve -->
      <section>
        <h6 class="hl"><i class="fas fa-lightbulb text-warning mr-1"></i>Para que serve</h6>
        <p class="small mb-2">
          A tela de <strong>Separação</strong> organiza o trabalho do galpão para os pedidos
          <strong>não-FULL</strong> (os FULL são despachados pela própria estrutura do Mercado Livre).
          Você junta pedidos numa <strong>Gaiola</strong> (carrinho de picking), separa os produtos,
          emite a NF-e e despacha — tudo numa rota só.
        </p>
      </section>

      <!-- 2. O fluxo — separado por marketplace (a ordem muda!) -->
      <section>
        <h6 class="hl"><i class="fas fa-route text-info mr-1"></i>O fluxo, do pedido ao despacho</h6>
        <p class="small mb-1">Os passos 1-3 são iguais; a diferença está no fim — <strong>a ordem de NF-e e
          etiqueta muda conforme o marketplace</strong>.</p>

        <!-- Mercado Livre / Venda direta -->
        <div class="mp-flow">
          <div class="mp-tag ml"><i class="fas fa-shopping-cart mr-1"></i>Mercado Livre e Venda Direta</div>
          <div class="flow small">
            <div class="step"><span class="n">1</span><div><b>Pedido elegível</b><br>entra na lista “Pedidos a separar”</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">2</span><div><b>Nova Gaiola</b><br>marque os pedidos e crie o carrinho</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">3</span><div><b>Separar / bipar</b><br>recolhe os produtos pela rota</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">4</span><div><b>Etiqueta</b><br>oficial do ML (ou interna, na venda direta)</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">5</span><div><b>NF-e</b><br>emite a nota (depois da etiqueta)</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">6</span><div><b>Entregar</b><br>dá baixa no estoque e fecha a gaiola</div></div>
          </div>
        </div>

        <!-- Shopee -->
        <div class="mp-flow mt-2">
          <div class="mp-tag shopee"><i class="fas fa-store mr-1"></i>Shopee <span class="badge badge-warning ml-1">ordem invertida</span></div>
          <div class="flow small">
            <div class="step"><span class="n">1</span><div><b>Pedido elegível</b><br>entra na lista “Pedidos a separar”</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">2</span><div><b>Nova Gaiola</b><br>marque os pedidos e crie o carrinho</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">3</span><div><b>Separar / bipar</b><br>recolhe os produtos pela rota</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">4</span><div><b>NF-e primeiro</b><br>emite a nota própria e <b>anexa na Shopee</b> (automático)</div></div>
            <span class="arr">›</span>
            <div class="step danger"><span class="n">5</span><div><b>Etiqueta = DESPACHA</b><br>gerar a etiqueta já envia o pedido na Shopee (irreversível)</div></div>
            <span class="arr">›</span>
            <div class="step"><span class="n">6</span><div><b>Entregar</b><br>fecha a gaiola (estoque Shopee baixa quando o envio é confirmado)</div></div>
          </div>
          <p class="small text-muted mt-1 mb-0">
            <i class="fas fa-exclamation-triangle text-warning mr-1"></i>Na Shopee, <strong>primeiro a
            NF-e, depois a etiqueta</strong> — a etiqueta só sai após o despacho. Se a Shopee ainda está
            validando a nota, o botão da etiqueta avisa <em>“clique de novo em instantes”</em>. Se faltar a
            NF-e, a entrega <strong>não</strong> fecha a gaiola e avisa o motivo (nada é marcado em silêncio).
          </p>
        </div>
      </section>

      <!-- 3. Quais pedidos aparecem -->
      <section>
        <h6 class="hl"><i class="fas fa-filter text-success mr-1"></i>Quais pedidos aparecem na lista</h6>
        <p class="small mb-1">Um pedido só entra em “Pedidos a separar” quando atende <strong>todos</strong>:</p>
        <table class="table table-sm table-bordered small mb-2 fields">
          <tbody>
            <tr><td class="f">Pago</td><td>Venda <strong>manual</strong> só aparece <strong>depois de paga</strong>. Pedido do <strong>Mercado Livre</strong> já é pago no marketplace — aparece assim que chega (não depende do pagamento no nosso sistema).</td></tr>
            <tr><td class="f">Não-FULL</td><td>Pedido <strong>FULL</strong> é despachado pela estrutura do ML — <strong>não</strong> entra na separação.</td></tr>
            <tr><td class="f">Shopee também entra</td><td>Pedido <strong>Shopee</strong> agora aparece e é separado aqui — com uma diferença no fim do fluxo (veja o aviso abaixo).</td></tr>
            <tr><td class="f">Ainda não despachado</td><td>Se já está <em>a caminho / entregue / cancelado</em>, sai da lista.</td></tr>
            <tr><td class="f">Fora de gaiola</td><td>Assim que você põe o pedido numa gaiola, ele sai de “a separar” e passa a viver dentro do carrinho.</td></tr>
            <tr><td class="f">Do seu galpão</td><td>Cada galpão vê só os próprios pedidos (admin vê todos).</td></tr>
          </tbody>
        </table>
        <p class="small text-muted mb-0">
          <i class="fas fa-info-circle mr-1"></i>Para pedidos ML com envio Coleta/Flex/Correios, só os
          que estão <strong>“Prontos p/ Envio”</strong> podem ir para a gaiola — os demais aparecem, mas
          aguardam o marketplace liberar.
        </p>
      </section>

      <!-- 4. Nenhum pedido aparecendo? -->
      <section>
        <h6 class="hl"><i class="fas fa-question-circle text-secondary mr-1"></i>Não aparece nenhum pedido?</h6>
        <ul class="small mb-0">
          <li>Todos os pedidos já estão <strong>dentro de gaiolas</strong> (veja em “Gaiolas / Transportadora”).</li>
          <li>Não há vendas <strong>não-FULL</strong> pendentes no período.</li>
          <li>As vendas <strong>manuais</strong> ainda não foram <strong>pagas</strong>.</li>
          <li>Você está num galpão <strong>sem pedidos</strong> no escopo.</li>
        </ul>
      </section>

      <div class="text-right mt-2">
        <button class="btn btn-sm btn-primary" @click="$emit('close')">Entendi</button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineEmits(['close'])
</script>

<style scoped>
.modal-backdrop-custom { position: fixed; inset: 0; background: rgba(0,0,0,.5); display:flex; align-items:center; justify-content:center; z-index: 1060; }
.help-card { background:#fff; border-radius:8px; padding:20px; width: 760px; max-width: 96vw; max-height: 92vh; overflow:auto; }
.help-card section { border-top:1px solid #eee; padding-top:10px; margin-top:10px; }
.help-card section:first-of-type { border-top:0; }
.hl { font-weight:600; margin-bottom:6px; }
.fields .f{width:28%;font-weight:600;background:#fafafa;vertical-align:top}
.flow{display:flex;align-items:stretch;gap:6px;flex-wrap:wrap}
.flow .step{flex:1;min-width:120px;background:#f8f9fa;border:1px solid #e9ecef;border-radius:6px;padding:6px 8px;display:flex;gap:6px;align-items:flex-start}
.flow .n{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#0d6efd;color:#fff;font-weight:600;font-size:11px;flex:none}
.flow .arr{align-self:center;color:#999;font-size:18px}
.flow .step.danger{background:#fff4f4;border-color:#f1c2c2}
.flow .step.danger .n{background:#dc3545}
.mp-flow{border:1px solid #eee;border-radius:8px;padding:8px}
.mp-tag{display:inline-block;font-weight:600;font-size:12px;padding:2px 8px;border-radius:12px;margin-bottom:6px}
.mp-tag.ml{background:#fff3cd;color:#664d03}
.mp-tag.shopee{background:#fde2d4;color:#8a3b12}
</style>
