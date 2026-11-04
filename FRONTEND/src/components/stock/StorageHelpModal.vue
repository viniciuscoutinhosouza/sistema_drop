<template>
  <div class="modal-backdrop-custom" @click.self="$emit('close')">
    <div class="help-card">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <h5 class="mb-0"><i class="fas fa-sitemap text-primary mr-2"></i>Como funciona a Árvore de Endereçamento</h5>
        <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
      </div>

      <!-- 1. O que é / para que serve -->
      <section>
        <h6 class="hl"><i class="fas fa-lightbulb text-warning mr-1"></i>Para que serve</h6>
        <p class="small mb-2">
          A árvore descreve <strong>onde fica cada coisa fisicamente no galpão</strong> — das áreas
          maiores (uma sala, um corredor de porta-pallet) até o menor ponto onde o produto é guardado
          (uma prateleira, um pallet, uma caixa). Com isso o sistema sabe <strong>onde pegar cada
          produto e em que ordem</strong> na separação (rota de picking) — <em>sem mexer no saldo</em>:
          é só a localização física.
        </p>
      </section>

      <!-- 2. Hierarquia (diagrama) -->
      <section>
        <h6 class="hl"><i class="fas fa-layer-group text-info mr-1"></i>A hierarquia: do maior para o menor</h6>
        <p class="small mb-2">Você encaixa níveis dentro de níveis. Cada nível tem um <strong>Tipo</strong>
          (o que é) e uma <strong>Identificação</strong> (o nome/número/letra).</p>
        <svg viewBox="0 0 560 150" class="diagram">
          <g font-size="11" text-anchor="middle">
            <rect x="5"  y="55" width="92" height="40" rx="6" class="b1"/><text x="51"  y="72">Área / Sala</text><text x="51" y="86" class="sub">Sala Mickey</text>
            <rect x="120" y="55" width="92" height="40" rx="6" class="b2"/><text x="166" y="72">Estante</text><text x="166" y="86" class="sub">01 … 08</text>
            <rect x="235" y="55" width="92" height="40" rx="6" class="b3"/><text x="281" y="72">Coluna</text><text x="281" y="86" class="sub">A … F</text>
            <rect x="350" y="55" width="92" height="40" rx="6" class="b4"/><text x="396" y="72">Altura/Prat.</text><text x="396" y="86" class="sub">1 … 5</text>
            <rect x="465" y="55" width="90" height="40" rx="6" class="b5"/><text x="510" y="72">Pallet/Caixa</text><text x="510" y="86" class="sub">guarda o produto</text>
            <g class="arrow" font-size="16">
              <text x="108" y="79">›</text><text x="223" y="79">›</text><text x="338" y="79">›</text><text x="453" y="79">›</text>
            </g>
            <text x="280" y="22" font-size="11" class="muted">maior →————————————————————→ menor</text>
            <text x="510" y="118" font-size="10" class="store">✓ Armazenável</text>
          </g>
        </svg>
        <p class="small text-muted mb-2">Você não precisa de todos os níveis — use os que o seu galpão
          tem. Dá pra ter modelos diferentes em áreas diferentes (porta-pallet num corredor, armários noutra sala).</p>
      </section>

      <!-- 3. full_code -->
      <section>
        <h6 class="hl"><i class="fas fa-barcode text-secondary mr-1"></i>O código completo (endereço)</h6>
        <p class="small mb-2">O sistema junta a identificação de cada nível, do topo até a folha, formando
          o <strong>endereço completo</strong> — é o que vai na etiqueta e no picking:</p>
        <div class="codebox">
          <span class="c1">MICKEY</span><span class="sep">-</span><span class="c2">E01</span><span class="sep">-</span><span class="c3">A</span><span class="sep">-</span><span class="c4">3</span>
          <span class="arrow2">→</span> <strong>MICKEY-E01-A-3</strong>
          <div class="small text-muted mt-1">“Sala Mickey, Estante 01, Coluna A, Altura 3”</div>
        </div>
      </section>

      <!-- 4. Campos -->
      <section>
        <h6 class="hl"><i class="fas fa-i-cursor text-success mr-1"></i>O que é cada campo</h6>
        <table class="table table-sm table-bordered small mb-2 fields">
          <tbody>
            <tr><td class="f">Tipo de nível</td><td>O que o nível É: <em>Sala, Área, Estante, Coluna, Altura, Prateleira, Pallet, Caixa…</em> É só um rótulo pra você se organizar.</td></tr>
            <tr><td class="f">Identificação</td><td>O nome/número/letra DESTE nível: <code>Mickey</code>, <code>01</code>, <code>A</code>, <code>3</code>. É o que entra no código completo.</td></tr>
            <tr><td class="f">Tipo de área <span class="badge badge-light">só na raiz</span></td><td><strong>Porta-pallet</strong> (estante→coluna→altura→pallet), <strong>Armários</strong> (salas com armários/estantes) ou <strong>Outra</strong>. Ajuda a sugerir a estrutura.</td></tr>
            <tr><td class="f">Armazenável</td><td>Marque <strong>só no menor nível</strong> — o ponto que de fato <strong>recebe produto</strong> (prateleira/pallet/caixa). Níveis intermediários (Sala, Estante) ficam desmarcados: servem só pra agrupar.</td></tr>
            <tr><td class="f">Sequência de picking</td><td>A <strong>ordem da rota</strong> de separação (1, 2, 3…). O separador percorre os endereços nessa ordem — defina seguindo o caminho físico no galpão para andar menos.</td></tr>
          </tbody>
        </table>
        <div class="mockup small">
          <div class="mock-title">Exemplo — criando “Estante 01” dentro da Sala Mickey</div>
          <div class="mock-row"><span>Tipo de nível</span><b>Estante</b></div>
          <div class="mock-row"><span>Identificação</span><b>01</b></div>
          <div class="mock-row"><span>Armazenável</span><b>☐ (não — é só agrupador)</b></div>
          <div class="mock-row"><span>Sequência de picking</span><b>2</b></div>
        </div>
      </section>

      <!-- 5. Gerar em massa -->
      <section>
        <h6 class="hl"><i class="fas fa-layer-group text-primary mr-1"></i>Gerar em massa (criar vários de uma vez)</h6>
        <p class="small mb-2">Em vez de criar Estante 01, 02, 03… uma a uma, gere a faixa inteira:</p>
        <div class="bulk-ex small">
          <div class="bulk-in">
            <div class="mock-row"><span>Tipo de nível</span><b>Estante</b></div>
            <div class="mock-row"><span>Esquema</span><b>Faixa numérica</b></div>
            <div class="mock-row"><span>De / Até / Zeros à esq.</span><b>1 / 8 / 1</b></div>
          </div>
          <div class="bulk-arrow">→</div>
          <div class="bulk-out">
            <span v-for="n in ['01','02','03','04','05','06','07','08']" :key="n" class="chip">Estante {{ n }}</span>
          </div>
        </div>
        <p class="small text-muted mt-1 mb-0">Esquemas: <strong>numérica</strong> (1 a 8, com zeros à esquerda),
          <strong>letras</strong> (A a F) ou <strong>lista de nomes</strong> (Mickey, Pateta, Donald).
          “Marcar como armazenáveis” = os gerados já recebem produto (use quando a faixa É o menor nível).</p>
      </section>

      <!-- 6. Exemplos reais -->
      <section>
        <h6 class="hl"><i class="fas fa-warehouse text-dark mr-1"></i>Dois exemplos de montagem</h6>
        <div class="row small">
          <div class="col-md-6">
            <div class="ex-card">
              <div class="ex-h"><i class="fas fa-door-open mr-1"></i>Sala com estantes</div>
              <ul class="tree">
                <li>🏠 <b>Sala</b> Mickey
                  <ul><li>🗄️ <b>Estante</b> 01 … 08
                    <ul><li>📚 <b>Prateleira</b> 1 … 5 <span class="store">✓ guarda produto</span></li></ul>
                  </li></ul>
                </li>
              </ul>
            </div>
          </div>
          <div class="col-md-6">
            <div class="ex-card">
              <div class="ex-h"><i class="fas fa-pallet mr-1"></i>Porta-pallet</div>
              <ul class="tree">
                <li>🏭 <b>Área</b> Corredor A
                  <ul><li>🗄️ <b>Estante</b> 01 … 10
                    <ul><li>🧱 <b>Coluna</b> A … C
                      <ul><li>📦 <b>Pallet</b> (altura) 1 … 4 <span class="store">✓ guarda produto</span></li></ul>
                    </li></ul>
                  </li></ul>
                </li>
              </ul>
            </div>
          </div>
        </div>
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
.help-card { background:#fff; border-radius:8px; padding:20px; width: 780px; max-width: 96vw; max-height: 92vh; overflow:auto; }
.help-card section { border-top:1px solid #eee; padding-top:10px; margin-top:10px; }
.help-card section:first-of-type { border-top:0; }
.hl { font-weight:600; margin-bottom:6px; }
.diagram { width:100%; height:auto; max-height:150px; }
.diagram .b1{fill:#e3f2fd;stroke:#90caf9}.diagram .b2{fill:#e8f5e9;stroke:#a5d6a7}.diagram .b3{fill:#fff3e0;stroke:#ffcc80}
.diagram .b4{fill:#f3e5f5;stroke:#ce93d8}.diagram .b5{fill:#fce4ec;stroke:#f48fb1}
.diagram .sub{fill:#777;font-size:9px}.diagram .arrow{fill:#999}.diagram .muted{fill:#aaa}.diagram .store{fill:#2e7d32;font-weight:600}
.codebox{background:#f8f9fa;border:1px solid #e9ecef;border-radius:6px;padding:10px 12px;font-family:monospace}
.codebox .c1{color:#1565c0}.codebox .c2{color:#2e7d32}.codebox .c3{color:#e65100}.codebox .c4{color:#6a1b9a}
.codebox .sep{color:#aaa}.codebox .arrow2{margin:0 8px;color:#999}
.fields .f{width:34%;font-weight:600;background:#fafafa;vertical-align:top}
.mockup,.ex-card{background:#f8f9fa;border:1px solid #e9ecef;border-radius:6px;padding:8px 10px}
.mock-title{font-weight:600;margin-bottom:4px}
.mock-row{display:flex;justify-content:space-between;border-bottom:1px dashed #e9ecef;padding:2px 0}
.mock-row span{color:#777}
.bulk-ex{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.bulk-in{flex:1;min-width:180px;background:#f8f9fa;border:1px solid #e9ecef;border-radius:6px;padding:6px 10px}
.bulk-arrow{font-size:20px;color:#999}
.bulk-out{flex:1;min-width:180px}
.chip{display:inline-block;background:#e8f5e9;border:1px solid #a5d6a7;border-radius:4px;padding:1px 6px;margin:2px;font-size:11px}
.ex-h{font-weight:600;margin-bottom:4px}
.tree,.tree ul{list-style:none;padding-left:14px;margin:0}
.tree li{padding:1px 0}
.store{color:#2e7d32;font-size:10px;font-weight:600}
</style>
