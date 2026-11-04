<template>
  <div class="modal-backdrop-custom" @click.self="$emit('close')">
    <div class="help-card">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h5 class="mb-0"><i class="fas fa-box-open text-primary mr-2"></i>Como endereçar um produto</h5>
        <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
      </div>

      <!-- 1. O que é -->
      <section>
        <h6 class="hl"><i class="fas fa-map-marker-alt text-danger mr-1"></i>Para que serve</h6>
        <p class="small mb-2">
          Aqui você diz <strong>quanto de um produto está fisicamente NESTE endereço</strong> (ex.:
          <code>A / 1 / 01</code>). É a <strong>localização</strong> do estoque — para o separador saber
          onde pegar. <strong>Não cria nem muda saldo</strong>: o saldo do produto continua vindo das
          notas/pedidos (veja abaixo).
        </p>
      </section>

      <!-- 2. Campos -->
      <section>
        <h6 class="hl"><i class="fas fa-i-cursor text-success mr-1"></i>O que é cada campo</h6>
        <table class="table table-sm table-bordered small mb-0 fields">
          <tbody>
            <tr><td class="f">Localizar produto</td><td><strong>Bipe o EAN</strong> (código de barras) ou o <strong>código interno</strong> e clique <em>Buscar</em>. Produto sem EAN? use <em>“Gerar código interno”</em> — cria um código próprio pra etiquetar/bipar.</td></tr>
            <tr><td class="f">Quantidade (unidades)</td><td>Quantas <strong>unidades</strong> desse produto estão guardadas aqui. (Em caixas fechadas? preencha a Composição abaixo que ele soma.)</td></tr>
            <tr><td class="f">Ordem de picking</td><td>Quando o mesmo produto está em vários endereços, define <strong>qual pegar primeiro</strong>. A rota geral do galpão também respeita o <em>FEFO</em> (validade mais curta primeiro) e a sequência dos endereços.</td></tr>
            <tr><td class="f">Lote (id) <span class="badge badge-warning">rastreável</span></td><td>Só aparece em produto <strong>rastreável</strong> (lote/validade). Informe <strong>qual lote</strong> está aqui — o endereçamento acompanha o lote e o FEFO.</td></tr>
            <tr><td class="f">Composição de caixas</td><td><strong>caixas × un/caixa</strong> (+ rótulo). Ex.: <code>3 × 10</code> = 30 un em 3 caixas de 10. Pode ter várias linhas (3×10 + 1×5). Serve pra gerar <strong>etiqueta/QR das caixas fechadas</strong> e pro picking esvaziar a caixa aberta antes de abrir outra.</td></tr>
          </tbody>
        </table>
      </section>

      <!-- 3. Como se comporta como estoque (o ponto-chave) -->
      <section>
        <h6 class="hl"><i class="fas fa-balance-scale text-info mr-1"></i>Como isso se comporta como estoque</h6>
        <p class="small mb-2">O <strong>saldo</strong> do produto é calculado pelas <strong>notas fiscais e
          pedidos</strong> (entra/sai) — o endereçamento <strong>não mexe nesse número</strong>. O
          endereçamento só diz <strong>ONDE</strong> esse saldo está, distribuído pelos endereços:</p>

        <svg viewBox="0 0 540 170" class="diagram">
          <g font-size="11">
            <rect x="8" y="10" width="150" height="150" rx="8" class="total"/>
            <text x="83" y="30" text-anchor="middle" font-weight="600">Saldo do produto</text>
            <text x="83" y="45" text-anchor="middle" class="sub">(das NF-e / pedidos)</text>
            <text x="83" y="95" text-anchor="middle" font-size="30" font-weight="700" class="tot">100</text>
            <text x="83" y="120" text-anchor="middle" class="sub">unidades</text>

            <text x="200" y="90" font-size="22" class="eq">=</text>

            <rect x="230" y="14" width="140" height="40" rx="6" class="a"/><text x="238" y="32" font-size="10">📍 A / 1 / 01</text><text x="360" y="39" text-anchor="end" font-weight="700">50</text>
            <rect x="230" y="60" width="140" height="40" rx="6" class="a"/><text x="238" y="78" font-size="10">📍 B / 2 / 03</text><text x="360" y="85" text-anchor="end" font-weight="700">30</text>
            <rect x="230" y="106" width="140" height="40" rx="6" class="none"/><text x="238" y="124" font-size="10">Sem endereço</text><text x="360" y="131" text-anchor="end" font-weight="700">20</text>

            <text x="408" y="90" font-size="18" class="eq">→</text>
            <text x="455" y="78" text-anchor="middle" class="sub">endereçados</text>
            <text x="455" y="92" text-anchor="middle" font-weight="700" class="tot">80</text>
            <text x="455" y="112" text-anchor="middle" class="sub">a endereçar: 20</text>
          </g>
        </svg>
        <p class="small mb-2">A soma dos endereços + o <strong>“Sem endereço”</strong> bate sempre com o
          saldo. O que você ainda não localizou fica em <em>“Sem endereço”</em> (aba <strong>Mapa &amp;
          Reconciliação</strong>) — é a sua lista do que falta organizar.</p>

        <div class="rules small">
          <div><i class="fas fa-check text-success mr-1"></i><strong>Endereçar/editar/transferir</strong> muda só a localização — o <strong>saldo total não muda</strong> (transferência entre endereços é soma zero).</div>
          <div><i class="fas fa-route text-primary mr-1"></i>Na <strong>separação</strong>, o sistema manda o separador no endereço certo, na ordem (FEFO → ordem de picking → caixa → sequência do endereço).</div>
          <div><i class="fas fa-truck text-secondary mr-1"></i>Ao <strong>despachar</strong> o pedido, o endereço de onde saiu é <strong>debitado</strong>; se o produto <strong>voltar</strong>, é creditado de volta. (O saldo contábil é debitado pela venda, como sempre — isto é só o “de onde saiu”.)</div>
          <div><i class="fas fa-clipboard-check text-info mr-1"></i>No <strong>inventário por endereço</strong>, você conta um endereço e o sistema ajusta a quantidade DALI pra bater com o físico — corrige <strong>onde está</strong>, não o saldo contábil.</div>
        </div>
      </section>

      <!-- 4. Exemplo caixas -->
      <section>
        <h6 class="hl"><i class="fas fa-boxes text-dark mr-1"></i>Exemplo de composição de caixas</h6>
        <div class="bulk-ex small">
          <div class="bulk-in">
            <div class="mock-row"><span>Caixas × un/caixa</span><b>3 × 10</b></div>
            <div class="mock-row"><span>+ linha</span><b>1 × 5</b></div>
          </div>
          <div class="bulk-arrow">→</div>
          <div class="bulk-out">
            <span class="chip">📦 10</span><span class="chip">📦 10</span><span class="chip">📦 10</span><span class="chip open">📭 5 (aberta)</span>
            <div class="mt-1"><b>Quantidade = 35 un</b></div>
          </div>
        </div>
        <p class="small text-muted mt-1 mb-0">As caixas fechadas ganham etiqueta/QR e podem ser movidas
          inteiras. No picking, o sistema esgota a <strong>caixa aberta</strong> antes de abrir uma fechada.</p>
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
.fields .f{width:32%;font-weight:600;background:#fafafa;vertical-align:top}
.diagram{width:100%;height:auto;max-height:170px}
.diagram .total{fill:#e3f2fd;stroke:#90caf9}.diagram .a{fill:#e8f5e9;stroke:#a5d6a7}.diagram .none{fill:#fff3e0;stroke:#ffcc80}
.diagram .sub{fill:#888;font-size:9px}.diagram .tot{fill:#1565c0}.diagram .eq{fill:#999}
.rules > div{padding:3px 0;border-bottom:1px dashed #eee}
.rules > div:last-child{border-bottom:0}
.bulk-ex{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.bulk-in{flex:1;min-width:170px;background:#f8f9fa;border:1px solid #e9ecef;border-radius:6px;padding:6px 10px}
.mock-row{display:flex;justify-content:space-between;border-bottom:1px dashed #e9ecef;padding:2px 0}
.mock-row span{color:#777}
.bulk-arrow{font-size:20px;color:#999}
.bulk-out{flex:1;min-width:170px}
.chip{display:inline-block;background:#e8f5e9;border:1px solid #a5d6a7;border-radius:4px;padding:1px 6px;margin:2px;font-size:11px}
.chip.open{background:#fff3e0;border-color:#ffcc80}
</style>
