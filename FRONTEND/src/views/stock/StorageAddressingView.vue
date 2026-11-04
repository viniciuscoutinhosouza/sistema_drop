<template>
  <div class="storage-addressing">
    <div class="d-flex justify-content-between align-items-center mb-2 flex-wrap">
      <h1 class="h4 mb-0"><i class="fas fa-map-marked-alt mr-2"></i>Endereçamento de Estoque</h1>
      <div v-if="isAdmin" class="form-inline">
        <label class="mr-2 small text-muted">Galpão</label>
        <select v-model="warehouseId" class="form-control form-control-sm" @change="reloadAll">
          <option :value="null" disabled>Selecione…</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name }}</option>
        </select>
      </div>
    </div>

    <ul class="nav nav-tabs mb-3">
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'estrutura' }" href="#" @click.prevent="tab = 'estrutura'">Estrutura</a></li>
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'mapa' }" href="#" @click.prevent="tab = 'mapa'; loadReconciliation()">Mapa & Reconciliação</a></li>
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'inventario' }" href="#" @click.prevent="tab = 'inventario'; loadToCount(); loadDivergences()">Inventário</a></li>
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'caixas' }" href="#" @click.prevent="tab = 'caixas'; loadBoxes()">Caixas</a></li>
    </ul>

    <div v-if="isAdmin && !warehouseId" class="alert alert-info">Selecione um galpão para começar.</div>

    <!-- ════ ESTRUTURA ════ -->
    <div v-else-if="tab === 'estrutura'" class="row">
      <div class="col-md-7">
        <div class="card">
          <div class="card-header d-flex justify-content-between align-items-center">
            <span>
              <i class="fas fa-sitemap mr-1"></i>Árvore de endereços
              <button class="btn btn-sm btn-link text-info p-0 ml-1" title="Como funciona a Árvore de Endereçamento?"
                      @click="showHelp = true"><i class="fas fa-question-circle"></i></button>
            </span>
            <div v-if="canConfig">
              <button class="btn btn-sm btn-outline-primary mr-1" @click="openNodeModal(null)"><i class="fas fa-plus"></i> Área/Raiz</button>
              <button class="btn btn-sm btn-outline-secondary" @click="openBulkModal(null)"><i class="fas fa-layer-group"></i> Gerar em massa</button>
            </div>
          </div>
          <div v-if="canMove" class="px-2 py-1 border-top bg-light d-flex align-items-center flex-wrap" style="gap:6px">
            <small class="text-muted"><i class="fas fa-qrcode mr-1"></i>Etiquetas de caixa das marcadas:</small>
            <select v-model="labelSize" class="form-control form-control-sm" style="width:auto">
              <option value="100x50">100 × 50 mm</option>
              <option value="100x150">100 × 150 mm</option>
            </select>
            <button class="btn btn-sm btn-outline-primary" :disabled="!selectedLocIds.length || printingBatch" @click="printSelectedBoxLabels">
              <i class="fas" :class="printingBatch ? 'fa-spinner fa-spin' : 'fa-print'"></i>
              Emitir<span v-if="selectedLocIds.length"> ({{ selectedLocIds.length }})</span>
            </button>
            <button v-if="selectedLocIds.length" class="btn btn-sm btn-link text-muted p-0" @click="selectedLocIds = []">limpar</button>
          </div>
          <div class="card-body p-2" style="max-height: 70vh; overflow:auto">
            <p v-if="!tree.length" class="text-muted small mb-0">Nenhum endereço ainda. Crie uma área ou gere em massa.</p>
            <StorageNode
              v-for="n in tree" :key="n.id" :node="n" :depth="0" :can-config="canConfig"
              :can-move="canMove" :selected-id="selectedNode && selectedNode.id" :selected-ids="selectedLocIds"
              @select="selectNode" @add="openNodeModal" @bulk="openBulkModal" @toggle="toggleLoc"
              @edit="n => openNodeModal(n, true)" @remove="removeNode" @label="printLocationLabel" />
          </div>
        </div>
      </div>

      <div class="col-md-5">
        <div class="card">
          <div class="card-header">
            <i class="fas fa-box-open mr-1"></i>
            <span v-if="selectedNode">{{ selectedNode.full_code }}</span>
            <span v-else class="text-muted">Selecione um endereço</span>
          </div>
          <div class="card-body p-2">
            <template v-if="selectedNode">
              <div v-if="!selectedNode.is_storable" class="alert alert-warning py-2 small mb-2">
                Este nó é organizacional (não armazenável). Produtos ficam nos nós-folha marcados como armazenáveis.
              </div>
              <div v-else>
                <button v-if="canMove" class="btn btn-sm btn-primary mb-2 mr-2" @click="openAllocModal(null)"><i class="fas fa-plus"></i> Endereçar produto aqui</button>
                <button v-if="canMove && nodeContents.length" class="btn btn-sm btn-outline-warning mb-2" @click="openTransfer('node')"><i class="fas fa-dolly"></i> Esvaziar para…</button>
                <p v-if="!nodeContents.length" class="text-muted small">Nada endereçado aqui.</p>
                <table v-else class="table table-sm table-hover">
                  <thead><tr><th>Produto</th><th class="text-right">Qtd</th><th>Caixas</th><th></th></tr></thead>
                  <tbody>
                    <tr v-for="a in nodeContents" :key="a.id">
                      <td>
                        <div class="small"><strong>{{ a.product && a.product.sku }}</strong></div>
                        <div class="small text-muted">{{ a.product && a.product.title }}</div>
                        <span v-if="a.lot" class="badge badge-info">Lote {{ a.lot.lot_code }}<span v-if="a.lot.expiry_date"> · val {{ a.lot.expiry_date }}</span></span>
                      </td>
                      <td class="text-right">{{ a.qty_units }}<div class="small text-muted" v-if="a.loose_units">({{ a.loose_units }} soltas)</div></td>
                      <td class="small">
                        <span v-for="p in a.packs" :key="p.id" class="d-block">{{ p.box_count }}×{{ p.units_per_box }}<span v-if="p.label"> ({{ p.label }})</span></span>
                        <span v-if="a.packs_over" class="text-danger">⚠ caixas &gt; qtd</span>
                      </td>
                      <td class="text-nowrap">
                        <button v-if="canMove" class="btn btn-xs btn-link p-0 mr-2" title="Editar" @click="openAllocModal(a)"><i class="fas fa-edit"></i></button>
                        <button v-if="canMove" class="btn btn-xs btn-link p-0 mr-2" title="Transferir" @click="openTransfer('alloc', a)"><i class="fas fa-dolly"></i></button>
                        <button v-if="canMove && a.packs.length" class="btn btn-xs btn-link p-0 mr-2" title="Etiquetas de caixa" @click="printBoxLabels(a)"><i class="fas fa-qrcode"></i></button>
                        <button v-if="canMove" class="btn btn-xs btn-link text-danger p-0" title="Remover" @click="removeAlloc(a)"><i class="fas fa-trash"></i></button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- ════ MAPA & RECONCILIAÇÃO ════ -->
    <div v-else-if="tab === 'mapa'" class="row">
      <div class="col-md-5">
        <div class="card">
          <div class="card-header"><i class="fas fa-barcode mr-1"></i>Bipar / buscar código</div>
          <div class="card-body">
            <div class="input-group">
              <input v-model="scanCode" class="form-control" placeholder="EAN, código interno, LOC-… ou BOX-…" @keyup.enter="doScan">
              <div class="input-group-append"><button class="btn btn-primary" @click="doScan"><i class="fas fa-search"></i></button></div>
            </div>
            <div v-if="scanResult" class="mt-3 small">
              <div class="font-weight-bold">{{ scanLabel }}</div>
              <pre class="bg-light p-2 mt-1" style="max-height:40vh;overflow:auto">{{ scanResult }}</pre>
            </div>
          </div>
        </div>
      </div>
      <div class="col-md-7">
        <div class="card">
          <div class="card-header d-flex justify-content-between">
            <span><i class="fas fa-balance-scale mr-1"></i>Reconciliação (endereçado × saldo)</span>
            <button class="btn btn-sm btn-outline-secondary" @click="loadReconciliation"><i class="fas fa-sync"></i></button>
          </div>
          <div class="card-body p-2" style="max-height:70vh;overflow:auto">
            <p class="small text-muted">Diferença = <strong>sem endereço</strong> (estoque ainda não alocado). Negativo = endereçado além do saldo.</p>
            <table class="table table-sm">
              <thead><tr><th>Produto</th><th class="text-right">Endereçado</th><th class="text-right">Saldo</th><th class="text-right">Sem endereço</th></tr></thead>
              <tbody>
                <tr v-for="i in recon" :key="i.product_type + i.product_id" :class="{ 'table-warning': i.sem_endereco !== 0 }">
                  <td class="small"><strong>{{ i.sku }}</strong><div class="text-muted">{{ i.title }}</div></td>
                  <td class="text-right">{{ i.addressed }}</td>
                  <td class="text-right">{{ i.stock }}</td>
                  <td class="text-right" :class="{ 'text-danger': i.over, 'text-success': i.sem_endereco === 0 }">{{ i.sem_endereco }}</td>
                </tr>
                <tr v-if="!recon.length"><td colspan="4" class="text-center text-muted small">Nada endereçado ainda.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ════ INVENTÁRIO POR ENDEREÇO ════ -->
    <div v-else-if="tab === 'inventario'" class="row">
      <div class="col-md-4">
        <div class="card">
          <div class="card-header d-flex justify-content-between">
            <span><i class="fas fa-clipboard-list mr-1"></i>A contar</span>
            <button class="btn btn-sm btn-outline-secondary" @click="loadToCount"><i class="fas fa-sync"></i></button>
          </div>
          <div class="card-body p-0" style="max-height:70vh;overflow:auto">
            <p class="small text-muted px-2 pt-2 mb-1">Nunca contado primeiro, depois mais antigo.</p>
            <table class="table table-sm table-hover mb-0">
              <tbody>
                <tr v-for="l in toCount" :key="l.id" style="cursor:pointer" :class="{ 'table-active': countPanel.loc && countPanel.loc.id === l.id }" @click="openCount(l)">
                  <td class="small"><strong>{{ l.full_code }}</strong>
                    <div class="text-muted">{{ l.last_counted_at ? ('contado ' + fmtDate(l.last_counted_at)) : 'nunca contado' }}</div></td>
                </tr>
                <tr v-if="!toCount.length"><td class="text-center text-muted small">Sem endereços armazenáveis.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="col-md-8">
        <!-- Painel de contagem -->
        <div v-if="countPanel.loc" class="card mb-3">
          <div class="card-header d-flex justify-content-between align-items-center">
            <span><i class="fas fa-boxes mr-1"></i>Contar: {{ countPanel.loc.full_code }}</span>
            <button class="btn btn-xs btn-link text-muted" @click="countPanel.loc = null">fechar</button>
          </div>
          <div class="card-body">
            <p class="small text-muted">Informe a quantidade <strong>física contada</strong> de cada item. Corrige o endereço, <u>não</u> o saldo contábil — divergências aparecem abaixo e na Reconciliação.</p>
            <table class="table table-sm">
              <thead><tr><th>Produto</th><th>Lote</th><th class="text-right" style="width:120px">Contado</th><th></th></tr></thead>
              <tbody>
                <tr v-for="(r, idx) in countPanel.lines" :key="idx">
                  <td class="small"><strong>{{ r.sku || (r.product_type + ' #' + r.product_id) }}</strong><div class="text-muted">{{ r.title }}</div></td>
                  <td class="small">{{ r.lot_id || '—' }}</td>
                  <td><input type="number" min="0" v-model.number="r.counted_units" class="form-control form-control-sm text-right"></td>
                  <td><button v-if="r._added" class="btn btn-xs btn-link text-danger" @click="countPanel.lines.splice(idx,1)"><i class="fas fa-times"></i></button></td>
                </tr>
                <tr v-if="!countPanel.lines.length"><td colspan="4" class="text-center text-muted small">Endereço vazio — adicione o que encontrou.</td></tr>
              </tbody>
            </table>
            <div class="input-group input-group-sm mb-2">
              <input v-model="countPanel.scan" class="form-control" placeholder="Achou algo não listado? bipe EAN/código interno" @keyup.enter="addFoundProduct">
              <div class="input-group-append"><button class="btn btn-outline-primary" @click="addFoundProduct">Adicionar</button></div>
            </div>
            <div class="text-right">
              <button class="btn btn-sm btn-primary" :disabled="!countPanel.lines.length || countPanel.saving" @click="submitCount">
                <i class="fas fa-save"></i> Confirmar contagem
              </button>
            </div>
            <div v-if="countPanel.result.length" class="mt-3">
              <h6 class="small text-muted">Resultado da contagem</h6>
              <table class="table table-sm">
                <thead><tr><th>Produto</th><th class="text-right">Δ</th><th class="text-right">Endereçado</th><th class="text-right">Saldo</th><th class="text-right">Sem end.</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in countPanel.result" :key="i" :class="{ 'table-danger': r.over }">
                    <td class="small">{{ r.product_type }} #{{ r.product_id }}<span v-if="r.lot_id" class="text-muted"> · lote {{ r.lot_id }}</span></td>
                    <td class="text-right" :class="r.delta > 0 ? 'text-success' : (r.delta < 0 ? 'text-danger' : 'text-muted')">{{ r.delta > 0 ? '+' : '' }}{{ r.delta }}</td>
                    <td class="text-right">{{ r.addressed_total }}</td>
                    <td class="text-right">{{ r.stock_quantity }}</td>
                    <td class="text-right">{{ r.unaddressed }}</td>
                  </tr>
                </tbody>
              </table>
              <p v-if="countPanel.result.some(r => r.over)" class="small text-danger mb-0">
                <i class="fas fa-exclamation-triangle"></i> Há item com <strong>endereçado &gt; saldo contábil</strong> — físico lançado além do contábil. Abra um inventário contábil para reconciliar o saldo.
              </p>
            </div>
          </div>
        </div>
        <div v-else class="alert alert-info">Escolha um endereço à esquerda para contar.</div>

        <!-- Divergências recentes -->
        <div class="card">
          <div class="card-header d-flex justify-content-between">
            <span><i class="fas fa-history mr-1"></i>Ajustes recentes de inventário</span>
            <button class="btn btn-sm btn-outline-secondary" @click="loadDivergences"><i class="fas fa-sync"></i></button>
          </div>
          <div class="card-body p-2" style="max-height:40vh;overflow:auto">
            <table class="table table-sm mb-0">
              <thead><tr><th>Quando</th><th>Produto</th><th>Lote</th><th class="text-right">Δ</th></tr></thead>
              <tbody>
                <tr v-for="m in divergences" :key="m.id">
                  <td class="small text-muted">{{ fmtDate(m.created_at) }}</td>
                  <td class="small">{{ m.product_type }} #{{ m.product_id }}</td>
                  <td class="small">{{ m.lot_id || '—' }}</td>
                  <td class="text-right" :class="m.delta_units > 0 ? 'text-success' : 'text-danger'">{{ m.delta_units > 0 ? '+' : '' }}{{ m.delta_units }}</td>
                </tr>
                <tr v-if="!divergences.length"><td colspan="4" class="text-center text-muted small">Nenhum ajuste ainda.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ════ CAIXAS (box tracking — Fase 3c) ════ -->
    <div v-else-if="tab === 'caixas'" class="row">
      <div class="col-md-4">
        <div class="card">
          <div class="card-header"><i class="fas fa-qrcode mr-1"></i>Localizar caixa (QR)</div>
          <div class="card-body">
            <div class="input-group input-group-sm mb-2">
              <input v-model="boxLocate" class="form-control" placeholder="BOX-… (bipe ou digite)" @keyup.enter="locateBox">
              <div class="input-group-append"><button class="btn btn-outline-primary" @click="locateBox"><i class="fas fa-search"></i></button></div>
            </div>
            <div v-if="boxLocateResult" class="small border rounded p-2">
              <div><strong>{{ boxLocateResult.allocation && boxLocateResult.allocation.product && boxLocateResult.allocation.product.title }}</strong></div>
              <div class="text-muted">SKU {{ boxLocateResult.allocation && boxLocateResult.allocation.product && boxLocateResult.allocation.product.sku }} · {{ boxLocateResult.units_per_box }} un/caixa</div>
              <div>Endereço: <strong>{{ boxLocateResult.allocation && boxLocateResult.allocation.location_full_code }}</strong></div>
              <div>Status: <span :class="boxStatusClass(boxLocateResult.status)">{{ boxStatusLabel(boxLocateResult.status) }}</span></div>
            </div>
          </div>
        </div>
      </div>
      <div class="col-md-8">
        <div class="card">
          <div class="card-header d-flex justify-content-between align-items-center">
            <span><i class="fas fa-boxes mr-1"></i>Registro de caixas</span>
            <select v-model="boxStatusFilter" class="form-control form-control-sm w-auto" @change="loadBoxes">
              <option value="closed">Fechadas</option>
              <option value="open">Abertas</option>
              <option value="">Todas</option>
            </select>
          </div>
          <div class="card-body p-2" style="max-height: 70vh; overflow:auto">
            <table class="table table-sm table-hover mb-0">
              <thead><tr><th>Caixa</th><th>Produto</th><th>Endereço</th><th class="text-center">Un</th><th>Status</th><th></th></tr></thead>
              <tbody>
                <tr v-for="b in boxes" :key="b.id">
                  <td class="small"><code>{{ b.token }}</code></td>
                  <td class="small">{{ b.product && b.product.title }}<br><span class="text-muted">{{ b.product && b.product.sku }}</span></td>
                  <td class="small">{{ b.location_full_code }}</td>
                  <td class="text-center">{{ b.units_per_box }}</td>
                  <td><span :class="boxStatusClass(b.status)">{{ boxStatusLabel(b.status) }}</span></td>
                  <td class="text-right">
                    <template v-if="canMove && b.status === 'closed'">
                      <button class="btn btn-xs btn-link p-0 mr-2" title="Mover caixa" @click="openMoveBox(b)"><i class="fas fa-dolly"></i></button>
                      <button class="btn btn-xs btn-link p-0 text-warning" title="Abrir caixa" @click="doOpenBox(b)"><i class="fas fa-box-open"></i></button>
                    </template>
                  </td>
                </tr>
                <tr v-if="!boxes.length"><td colspan="6" class="text-center text-muted small">Nenhuma caixa neste filtro.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: criar/editar nó -->
    <div v-if="nodeModal.open" class="modal-backdrop-custom" @click.self="nodeModal.open = false">
      <div class="modal-card">
        <h5>{{ nodeModal.id ? 'Editar endereço' : (nodeModal.parent ? 'Novo sub-endereço' : 'Nova área/raiz') }}</h5>
        <p v-if="nodeModal.parent" class="small text-muted">Dentro de: {{ nodeModal.parent.full_code }}</p>
        <div class="form-group"><label class="small">Tipo de nível (Sala, Armário, Estante, Coluna, Altura, Pallet…)</label>
          <input v-model="nodeModal.level_type" class="form-control form-control-sm"></div>
        <div class="form-group"><label class="small">Identificação (nome, número ou letra)</label>
          <input v-model="nodeModal.code" class="form-control form-control-sm"></div>
        <div class="form-group" v-if="!nodeModal.parent"><label class="small">Tipo de área</label>
          <select v-model="nodeModal.area_kind" class="form-control form-control-sm">
            <option :value="null">—</option><option value="pallet">Porta-pallet</option><option value="cabinet">Armários</option><option value="other">Outra</option>
          </select></div>
        <div class="form-check mb-2"><input type="checkbox" class="form-check-input" id="stor" v-model="nodeModal.is_storable">
          <label class="form-check-label small" for="stor">Armazenável (recebe produto)</label></div>
        <div class="form-group"><label class="small">Sequência de picking (rota)</label>
          <input type="number" v-model.number="nodeModal.pick_sequence" class="form-control form-control-sm"></div>
        <div class="text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="nodeModal.open = false">Cancelar</button>
          <button class="btn btn-sm btn-primary" @click="saveNode">Salvar</button>
        </div>
      </div>
    </div>

    <!-- Modal: gerar em massa -->
    <div v-if="bulkModal.open" class="modal-backdrop-custom" @click.self="bulkModal.open = false">
      <div class="modal-card">
        <h5>Gerar em massa</h5>
        <p v-if="bulkModal.parent" class="small text-muted">Dentro de: {{ bulkModal.parent.full_code }}</p>
        <div class="form-group"><label class="small">Tipo de nível (ex.: Estante)</label>
          <input v-model="bulkModal.level_type" class="form-control form-control-sm"></div>
        <div class="form-group"><label class="small">Esquema de identificação</label>
          <select v-model="bulkModal.scheme.type" class="form-control form-control-sm">
            <option value="numeric">Faixa numérica (1 a 8)</option>
            <option value="letter">Faixa de letras (A a F)</option>
            <option value="named">Lista de nomes (Mickey, Pateta…)</option>
          </select></div>
        <div v-if="bulkModal.scheme.type === 'numeric'" class="form-row">
          <div class="col"><label class="small">De</label><input type="number" v-model.number="bulkModal.scheme.start" class="form-control form-control-sm"></div>
          <div class="col"><label class="small">Até</label><input type="number" v-model.number="bulkModal.scheme.end" class="form-control form-control-sm"></div>
          <div class="col"><label class="small">Qtd. dígitos</label><input type="number" v-model.number="bulkModal.scheme.pad" class="form-control form-control-sm"></div>
        </div>
        <div v-else-if="bulkModal.scheme.type === 'letter'" class="form-row">
          <div class="col"><label class="small">De</label><input v-model="bulkModal.scheme.start" maxlength="1" class="form-control form-control-sm"></div>
          <div class="col"><label class="small">Até</label><input v-model="bulkModal.scheme.end" maxlength="1" class="form-control form-control-sm"></div>
        </div>
        <div v-else class="form-group"><label class="small">Nomes separados por vírgula</label>
          <input v-model="bulkModal.namesCsv" class="form-control form-control-sm" placeholder="Mickey, Pateta, Donald"></div>
        <div class="form-check mb-2"><input type="checkbox" class="form-check-input" id="bstor" v-model="bulkModal.is_storable">
          <label class="form-check-label small" for="bstor">Marcar os gerados como armazenáveis</label></div>
        <div class="text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="bulkModal.open = false">Cancelar</button>
          <button class="btn btn-sm btn-primary" @click="saveBulk">Gerar</button>
        </div>
      </div>
    </div>

    <!-- Modal: alocar produto -->
    <div v-if="allocModal.open" class="modal-backdrop-custom" @click.self="allocModal.open = false">
      <div class="modal-card">
        <h5 class="d-flex justify-content-between align-items-center">
          <span>{{ allocModal.id ? 'Editar alocação' : 'Endereçar produto' }}</span>
          <button class="btn btn-sm btn-link text-info p-0" title="Como funciona? Como vira estoque?"
                  @click="showAllocHelp = true"><i class="fas fa-question-circle"></i></button>
        </h5>
        <p class="small text-muted">Em: {{ selectedNode && selectedNode.full_code }}</p>
        <div v-if="!allocModal.id" class="form-group">
          <label class="small">Localizar produto (bipe EAN, SKU ou código interno)</label>
          <div class="input-group">
            <input v-model="allocModal.scan" class="form-control form-control-sm" placeholder="EAN, SKU ou código interno" @keyup.enter="resolveAllocProduct">
            <div class="input-group-append"><button class="btn btn-sm btn-outline-primary" @click="resolveAllocProduct">Buscar</button></div>
          </div>
        </div>
        <div v-if="allocModal.product" class="alert alert-light py-2 small">
          <strong>{{ allocModal.product.sku }}</strong> — {{ allocModal.product.title }}
          <span v-if="allocModal.product.is_traceable" class="badge badge-warning ml-1">rastreável</span>
          <button v-if="!allocModal.product.main_ean && allocModal.canInternal" class="btn btn-xs btn-outline-secondary float-right" @click="genInternal">Gerar código interno</button>
        </div>
        <div class="form-row">
          <div class="form-group col"><label class="small">Quantidade (unidades)</label>
            <input type="number" v-model.number="allocModal.qty_units" class="form-control form-control-sm"></div>
          <div class="form-group col"><label class="small">Ordem de picking</label>
            <input type="number" v-model.number="allocModal.pick_order" class="form-control form-control-sm"></div>
        </div>
        <div v-if="allocModal.product && allocModal.product.is_traceable" class="form-group">
          <label class="small">Lote (id) <span class="text-muted">— informe o lote rastreável</span></label>
          <input type="number" v-model.number="allocModal.lot_id" class="form-control form-control-sm">
        </div>
        <label class="small d-block">Composição de caixas <span v-if="allocModal.defaults.length" class="text-muted">(padrões: <a v-for="d in allocModal.defaults" :key="d.id" href="#" class="mr-2" @click.prevent="addPack(d.units_per_box, d.label)">{{ d.units_per_box }}un</a>)</span></label>
        <div v-for="(p, idx) in allocModal.packs" :key="idx" class="form-row align-items-end mb-1">
          <div class="col"><input type="number" v-model.number="p.box_count" class="form-control form-control-sm" placeholder="caixas"></div>
          <div class="col-1 text-center">×</div>
          <div class="col"><input type="number" v-model.number="p.units_per_box" class="form-control form-control-sm" placeholder="un/caixa"></div>
          <div class="col"><input v-model="p.label" class="form-control form-control-sm" placeholder="rótulo"></div>
          <div class="col-auto"><button class="btn btn-xs btn-link text-danger" @click="allocModal.packs.splice(idx,1)"><i class="fas fa-times"></i></button></div>
        </div>
        <button class="btn btn-xs btn-outline-secondary mb-2" @click="addPack()"><i class="fas fa-plus"></i> caixa</button>
        <div class="text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="allocModal.open = false">Cancelar</button>
          <button class="btn btn-sm btn-primary" :disabled="!allocModal.product" @click="saveAlloc">Salvar</button>
        </div>
      </div>
    </div>

    <!-- Modal: transferir / esvaziar -->
    <div v-if="transferModal.open" class="modal-backdrop-custom" @click.self="transferModal.open = false">
      <div class="modal-card">
        <h5>{{ transferModal.mode === 'node' ? 'Esvaziar endereço' : 'Transferir' }}</h5>
        <p v-if="transferModal.mode === 'alloc'" class="small text-muted">
          <strong>{{ transferModal.alloc.product && transferModal.alloc.product.sku }}</strong> —
          {{ transferModal.alloc.qty_units }} un em {{ selectedNode && selectedNode.full_code }}</p>
        <p v-else class="small text-muted">Move todas as {{ nodeContents.length }} alocações de
          {{ selectedNode && selectedNode.full_code }} para outro endereço.</p>
        <div class="form-group">
          <label class="small">Endereço de destino</label>
          <select v-model.number="transferModal.to_location_id" class="form-control form-control-sm">
            <option :value="null" disabled>Selecione…</option>
            <option v-for="l in storableLocs.filter(x => x.id !== (selectedNode && selectedNode.id))" :key="l.id" :value="l.id">{{ l.full_code }}</option>
          </select>
        </div>
        <div v-if="transferModal.mode === 'alloc'" class="form-group">
          <label class="small">Quantidade (máx {{ transferModal.alloc.qty_units }})</label>
          <input type="number" min="1" :max="transferModal.alloc.qty_units" v-model.number="transferModal.qty_units" class="form-control form-control-sm">
          <small class="text-muted">Parcial chega como unidade solta no destino.</small>
        </div>
        <div class="text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="transferModal.open = false">Cancelar</button>
          <button class="btn btn-sm btn-primary" :disabled="!transferModal.to_location_id || transferModal.saving" @click="submitTransfer">Transferir</button>
        </div>
      </div>
    </div>

    <!-- Modal: mover caixa (box tracking — Fase 3c) -->
    <div v-if="moveBoxModal.open" class="modal-backdrop-custom" @click.self="moveBoxModal.open = false">
      <div class="modal-card">
        <h5>Mover caixa</h5>
        <p class="small text-muted">
          <code>{{ moveBoxModal.box.token }}</code> — {{ moveBoxModal.box.units_per_box }} un de
          <strong>{{ moveBoxModal.box.product && moveBoxModal.box.product.sku }}</strong>,
          hoje em {{ moveBoxModal.box.location_full_code }}. A caixa inteira muda de endereço mantendo o mesmo QR.</p>
        <div class="form-group">
          <label class="small">Endereço de destino</label>
          <select v-model.number="moveBoxModal.to_location_id" class="form-control form-control-sm">
            <option :value="null" disabled>Selecione…</option>
            <option v-for="l in storableLocs.filter(x => x.id !== moveBoxModal.box.location_id)" :key="l.id" :value="l.id">{{ l.full_code }}</option>
          </select>
        </div>
        <div class="text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="moveBoxModal.open = false">Cancelar</button>
          <button class="btn btn-sm btn-primary" :disabled="!moveBoxModal.to_location_id || moveBoxModal.saving" @click="submitMoveBox">Mover</button>
        </div>
      </div>
    </div>

    <StorageHelpModal v-if="showHelp" @close="showHelp = false" />
    <StorageAllocHelpModal v-if="showAllocHelp" @close="showAllocHelp = false" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import StorageNode from '@/components/stock/StorageNode.vue'
import StorageHelpModal from '@/components/stock/StorageHelpModal.vue'
import StorageAllocHelpModal from '@/components/stock/StorageAllocHelpModal.vue'

const toast = useToast()
const auth = useAuthStore()

const isAdmin = computed(() => auth.user?.role === 'admin')
const canConfig = computed(() => auth.hasAction('endereco_configurar'))
const canMove = computed(() => auth.hasAction('endereco_movimentar'))
const showHelp = ref(false)
const showAllocHelp = ref(false)

// Emissão em lote de etiquetas de caixa (endereços marcados na árvore)
const selectedLocIds = ref([])
const labelSize = ref('100x50')
const printingBatch = ref(false)
function toggleLoc(node) {
  const i = selectedLocIds.value.indexOf(node.id)
  if (i >= 0) selectedLocIds.value.splice(i, 1)
  else selectedLocIds.value.push(node.id)
}
async function printSelectedBoxLabels() {
  if (!selectedLocIds.value.length) return
  if (!confirm(`Emitir as etiquetas de caixa dos ${selectedLocIds.value.length} endereço(s) marcado(s) (incluindo sub-endereços)?\n\nAs etiquetas/QR anteriores desses endereços serão SUBSTITUÍDAS (os QR antigos deixam de funcionar).`)) return
  printingBatch.value = true
  try {
    const { data } = await api.post('/storage/box-labels/print-batch', { location_ids: selectedLocIds.value })
    if (!data.labels.length) { toast.info('Nenhuma caixa definida nos endereços marcados.'); return }
    printLabels('Etiquetas de caixa', data.labels.map(l => ({
      title: l.title, sku: l.sku, rotulo: l.rotulo, sub: `${l.units_per_box} un/caixa`,
      location: l.location, qr: l.token,
    })), { size: labelSize.value })
    toast.success(`${data.count} etiqueta(s) enviada(s) para impressão.`)
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao emitir etiquetas.') }
  finally { printingBatch.value = false }
}

const tab = ref('estrutura')
const warehouseId = ref(null)
const warehouses = ref([])
const tree = ref([])
const selectedNode = ref(null)
const nodeContents = ref([])
const recon = ref([])
const scanCode = ref('')
const scanResult = ref(null)
const scanLabel = ref('')
const toCount = ref([])
const divergences = ref([])
const countPanel = ref({ loc: null, lines: [], scan: '', result: [], saving: false })

const nodeModal = ref({ open: false })
const bulkModal = ref({ open: false, scheme: {} })
const allocModal = ref({ open: false, packs: [], defaults: [] })
const transferModal = ref({ open: false, mode: 'alloc', alloc: {}, to_location_id: null, qty_units: null, saving: false })
const storableLocs = ref([])
const boxes = ref([])
const boxStatusFilter = ref('closed')
const boxLocate = ref('')
const boxLocateResult = ref(null)
const moveBoxModal = ref({ open: false, box: {}, to_location_id: null, saving: false })

function whParam() { return warehouseId.value ? { warehouse_id: warehouseId.value } : {} }

async function loadWarehouses() {
  try { const { data } = await api.get('/warehouse'); warehouses.value = data.items || data || [] } catch { /* ignore */ }
}
async function loadTree() {
  try {
    const { data } = await api.get('/storage/locations', { params: whParam() })
    tree.value = data.tree || []
    if (!warehouseId.value && data.warehouse_id) warehouseId.value = data.warehouse_id
  } catch (e) {
    if (e?.response?.status === 400) { await loadWarehouses() } // admin precisa escolher galpão
    else toast.error(e?.response?.data?.detail || 'Falha ao carregar a árvore.')
  }
}
async function reloadAll() { selectedNode.value = null; nodeContents.value = []; selectedLocIds.value = []; await loadTree() }

async function selectNode(node) {
  selectedNode.value = node
  nodeContents.value = []
  if (node.is_storable) {
    try { const { data } = await api.get(`/storage/locations/${node.id}/contents`); nodeContents.value = data.allocations || [] }
    catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao ler o conteúdo.') }
  }
}

// ── Nó ──
function openNodeModal(nodeOrParent, isEdit) {
  // chamado como add(parent), edit(node) — distinguimos pelo 2º arg
  if (isEdit) {
    const n = nodeOrParent
    nodeModal.value = { open: true, id: n.id, parent: null, level_type: n.level_type, code: n.code,
      area_kind: n.area_kind, is_storable: n.is_storable, pick_sequence: n.pick_sequence }
  } else {
    nodeModal.value = { open: true, id: null, parent: nodeOrParent || null, level_type: '', code: '',
      area_kind: null, is_storable: false, pick_sequence: 0 }
  }
}
async function saveNode() {
  const m = nodeModal.value
  if (!m.level_type || !m.code) { toast.warning('Preencha tipo de nível e identificação.'); return }
  try {
    if (m.id) {
      await api.patch(`/storage/locations/${m.id}`, { level_type: m.level_type, code: m.code, area_kind: m.area_kind, is_storable: m.is_storable, pick_sequence: m.pick_sequence })
    } else {
      const body = { level_type: m.level_type, code: m.code, area_kind: m.area_kind, is_storable: m.is_storable, pick_sequence: m.pick_sequence }
      if (m.parent) body.parent_id = m.parent.id; else Object.assign(body, whParam())
      await api.post('/storage/locations', body)
    }
    nodeModal.value.open = false
    await loadTree()
    toast.success('Endereço salvo.')
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao salvar.') }
}
async function removeNode(node) {
  if (!confirm(`Excluir o endereço ${node.full_code}?`)) return
  try { await api.delete(`/storage/locations/${node.id}`); await loadTree(); toast.success('Excluído.') }
  catch (e) { toast.error(e?.response?.data?.detail || 'Não foi possível excluir.') }
}

// ── Bulk ──
function openBulkModal(parent) {
  bulkModal.value = { open: true, parent: parent || null, level_type: '', is_storable: !parent ? false : true,
    scheme: { type: 'numeric', start: 1, end: 5, pad: 0 }, namesCsv: '' }
}
async function saveBulk() {
  const m = bulkModal.value
  if (!m.level_type) { toast.warning('Informe o tipo de nível.'); return }
  const scheme = { ...m.scheme }
  if (scheme.type === 'named') scheme.names = (m.namesCsv || '').split(',').map(s => s.trim()).filter(Boolean)
  try {
    const body = { level_type: m.level_type, scheme, is_storable: m.is_storable }
    if (m.parent) body.parent_id = m.parent.id; else Object.assign(body, whParam())
    const { data } = await api.post('/storage/locations/bulk', body)
    bulkModal.value.open = false
    await loadTree()
    toast.success(`Criados ${data.created.length}, pulados ${data.skipped.length}.`)
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha na geração.') }
}

// ── Alocação ──
async function openAllocModal(a) {
  if (a) {
    allocModal.value = { open: true, id: a.id, product: a.product ? { ...a.product } : null,
      qty_units: a.qty_units, pick_order: a.pick_order, lot_id: a.lot_id,
      packs: a.packs.map(p => ({ box_count: p.box_count, units_per_box: p.units_per_box, label: p.label })),
      defaults: [], product_type: a.product_type, product_id: a.product_id, scan: '', canInternal: a.product_type === 'pg' || a.product_type === 'cmig' }
  } else {
    allocModal.value = { open: true, id: null, product: null, qty_units: 0, pick_order: 0, lot_id: null, packs: [], defaults: [], scan: '', canInternal: false }
  }
}
async function resolveAllocProduct() {
  const code = (allocModal.value.scan || '').trim()
  if (!code) return
  try {
    const { data } = await api.get(`/storage/scan/${encodeURIComponent(code)}`)
    if (data.kind !== 'product') { toast.warning('Código não é de produto.'); return }
    const p = data.product
    allocModal.value.product = { sku: p.sku, title: p.title, main_ean: p.main_ean, is_traceable: p.is_traceable }
    allocModal.value.product_type = p.product_type
    allocModal.value.product_id = p.product_id
    allocModal.value.canInternal = p.product_type === 'pg' || p.product_type === 'cmig'
    allocModal.value.defaults = data.pack_defaults || []
  } catch (e) { toast.error(e?.response?.data?.detail || 'Produto não encontrado.') }
}
function addPack(upb, label) { allocModal.value.packs.push({ box_count: 0, units_per_box: upb || 0, label: label || '' }) }
async function genInternal() {
  const m = allocModal.value
  try {
    const { data } = await api.post(`/storage/products/${m.product_type}/${m.product_id}/internal-code`)
    m.product.main_ean = data.ean
    toast.success(`Código interno: ${data.ean}`)
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao gerar código.') }
}
async function saveAlloc() {
  const m = allocModal.value
  const packs = m.packs.filter(p => p.box_count > 0 && p.units_per_box > 0)
  try {
    if (m.id) {
      await api.patch(`/storage/allocations/${m.id}`, { qty_units: m.qty_units, pick_order: m.pick_order, packs })
    } else {
      await api.post('/storage/allocations', {
        location_id: selectedNode.value.id, product_type: m.product_type, product_id: m.product_id,
        lot_id: m.lot_id || null, qty_units: m.qty_units, pick_order: m.pick_order, packs,
      })
    }
    allocModal.value.open = false
    await selectNode(selectedNode.value)
    toast.success('Alocação salva.')
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao salvar alocação.') }
}
async function removeAlloc(a) {
  if (!confirm('Remover esta alocação?')) return
  try { await api.delete(`/storage/allocations/${a.id}`); await selectNode(selectedNode.value); toast.success('Removida.') }
  catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao remover.') }
}

// ── Transferência entre endereços (Fase 3b) ──
async function loadStorableLocs() {
  try { const { data } = await api.get('/storage/inventory/to-count', { params: { ...whParam(), limit: 1000 } }); storableLocs.value = data.items || [] }
  catch { /* ignore */ }
}
async function openTransfer(mode, a) {
  await loadStorableLocs()
  transferModal.value = { open: true, mode, alloc: a || {}, to_location_id: null,
    qty_units: mode === 'alloc' ? (a ? a.qty_units : null) : null, saving: false }
}
async function submitTransfer() {
  const m = transferModal.value
  if (!m.to_location_id) return
  m.saving = true
  try {
    if (m.mode === 'node') {
      await api.post(`/storage/locations/${selectedNode.value.id}/transfer-all`, { to_location_id: m.to_location_id })
    } else {
      const body = { from_allocation_id: m.alloc.id, to_location_id: m.to_location_id }
      if (m.qty_units && m.qty_units < m.alloc.qty_units) body.qty_units = m.qty_units
      await api.post('/storage/transfer', body)
    }
    m.open = false
    await selectNode(selectedNode.value)
    toast.success('Transferência concluída.')
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha na transferência.') }
  finally { m.saving = false }
}

// ── Caixas (box tracking — Fase 3c) ──
function boxStatusLabel(s) { return s === 'open' ? 'Aberta' : s === 'consumed' ? 'Retirada' : 'Fechada' }
function boxStatusClass(s) { return s === 'open' ? 'badge badge-warning' : s === 'consumed' ? 'badge badge-secondary' : 'badge badge-success' }
async function loadBoxes() {
  try {
    const params = { ...whParam() }
    if (boxStatusFilter.value) params.status = boxStatusFilter.value
    const { data } = await api.get('/storage/boxes', { params })
    boxes.value = data.items || []
  } catch (e) { if (e?.response?.status !== 400) toast.error(e?.response?.data?.detail || 'Falha ao carregar as caixas.') }
}
async function locateBox() {
  const code = (boxLocate.value || '').trim()
  if (!code) return
  try { const { data } = await api.get(`/storage/scan/${encodeURIComponent(code)}`); boxLocateResult.value = data.kind === 'box' ? data : null
    if (data.kind !== 'box') toast.warning('Esse código não é de caixa.') }
  catch (e) { boxLocateResult.value = null; toast.error(e?.response?.data?.detail || 'Caixa não encontrada.') }
}
async function openMoveBox(b) {
  await loadStorableLocs()
  moveBoxModal.value = { open: true, box: b, to_location_id: null, saving: false }
}
async function submitMoveBox() {
  const m = moveBoxModal.value
  if (!m.to_location_id) return
  m.saving = true
  try {
    await api.post(`/storage/box-labels/${m.box.id}/move`, { location_id: m.to_location_id })
    m.open = false
    await loadBoxes()
    toast.success('Caixa movida.')
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao mover a caixa.') }
  finally { m.saving = false }
}
async function doOpenBox(b) {
  if (!confirm('Abrir esta caixa? O conteúdo vira unidades soltas no mesmo endereço.')) return
  try { await api.post(`/storage/box-labels/${b.id}/open`); await loadBoxes(); toast.success('Caixa aberta.') }
  catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao abrir a caixa.') }
}

// ── Reconciliação / Scan ──
async function loadReconciliation() {
  try { const { data } = await api.get('/storage/reconciliation', { params: whParam() }); recon.value = data.items || [] }
  catch (e) { if (e?.response?.status !== 400) toast.error(e?.response?.data?.detail || 'Falha na reconciliação.') }
}
async function doScan() {
  const code = (scanCode.value || '').trim()
  if (!code) return
  try {
    const { data } = await api.get(`/storage/scan/${encodeURIComponent(code)}`)
    scanLabel.value = { product: 'Produto', box: 'Caixa', location: 'Endereço' }[data.kind] || 'Resultado'
    scanResult.value = JSON.stringify(data, null, 2)
  } catch (e) { scanResult.value = null; toast.error(e?.response?.data?.detail || 'Nada encontrado.') }
}

// ── Inventário por endereço (Fase 3a) ──
function fmtDate(s) { if (!s) return ''; try { return new Date(s).toLocaleString('pt-BR') } catch { return s } }
async function loadToCount() {
  try { const { data } = await api.get('/storage/inventory/to-count', { params: whParam() }); toCount.value = data.items || [] }
  catch (e) { if (e?.response?.status !== 400) toast.error(e?.response?.data?.detail || 'Falha ao listar endereços.') }
}
async function loadDivergences() {
  try { const { data } = await api.get('/storage/allocation-movements', { params: { ...whParam(), reason: 'adjust', limit: 50 } }); divergences.value = data.items || [] }
  catch (e) { if (e?.response?.status !== 400) toast.error(e?.response?.data?.detail || 'Falha ao listar ajustes.') }
}
async function openCount(loc) {
  countPanel.value = { loc, lines: [], scan: '', result: [], saving: false }
  try {
    const { data } = await api.get(`/storage/locations/${loc.id}/contents`)
    countPanel.value.lines = (data.allocations || []).map(a => ({
      product_type: a.product_type, product_id: a.product_id, lot_id: a.lot_id,
      sku: a.product?.sku, title: a.product?.title,
      counted_units: a.qty_units, _added: false,
    }))
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao abrir o endereço.') }
}
async function addFoundProduct() {
  const code = (countPanel.value.scan || '').trim()
  if (!code) return
  try {
    const { data } = await api.get(`/storage/scan/${encodeURIComponent(code)}`)
    if (data.kind !== 'product') { toast.warning('Código não é de produto.'); return }
    const p = data.product
    if (countPanel.value.lines.some(r => r.product_type === p.product_type && r.product_id === p.product_id && !r.lot_id)) {
      toast.info('Produto já está na lista.'); countPanel.value.scan = ''; return
    }
    countPanel.value.lines.push({ product_type: p.product_type, product_id: p.product_id, lot_id: null,
      sku: p.sku, title: p.title, counted_units: 0, _added: true })
    countPanel.value.scan = ''
  } catch (e) { toast.error(e?.response?.data?.detail || 'Produto não encontrado.') }
}
async function submitCount() {
  const cp = countPanel.value
  const counts = cp.lines.map(r => ({
    product_type: r.product_type, product_id: r.product_id,
    lot_id: r.lot_id || null, counted_units: Number(r.counted_units) || 0,
  }))
  cp.saving = true
  try {
    const { data } = await api.post(`/storage/locations/${cp.loc.id}/count`, { counts })
    cp.result = data.lines || []
    toast.success('Contagem registrada.')
    await loadToCount(); await loadDivergences()
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao registrar a contagem.') }
  finally { cp.saving = false }
}

// ── Etiquetas (impressão com QR/barcode via CDN, sem dep no bundle) ──
// SEGURANÇA: os campos (full_code/level_type/sku/título/token) são dados livres do usuário e vão
// para uma nova janela mesma-origem. Escapamos TUDO (texto e atributo) e anulamos `opener` — senão
// um `code` malicioso (ex.: <img onerror>) rodaria script com acesso ao localStorage (JWT). XSS→token.
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}
function printLabels(title, items, opts = {}) {
  const w = window.open('', '_blank')
  if (!w) { toast.warning('Permita pop-ups para imprimir etiquetas.'); return }
  try { w.opener = null } catch { /* ignore */ }
  const cards = items.map(it => `
    <div class="lbl">
      ${it.location ? `<div class="loc">${esc(it.location)}</div>` : ''}
      <div class="code">${esc(it.human || it.title || it.sku || '')}</div>
      ${(it.sku && (it.title || it.human)) ? `<div class="skun">${esc(it.sku)}</div>` : ''}
      ${it.rotulo ? `<div class="rot">${esc(it.rotulo)}</div>` : ''}
      ${it.barcode ? `<svg class="bc" data-code="${esc(it.barcode)}"></svg>` : ''}
      ${it.qr ? `<div class="qr" data-code="${esc(it.qr)}"></div>` : ''}
      ${it.sub ? `<div class="sub">${esc(it.sub)}</div>` : ''}
    </div>`).join('')
  // Tamanho de etiqueta selecionável (100×50 ou 100×150). Sem `opts.size` = layout legado (220px).
  const sizes = { '100x50': [100, 50], '100x150': [100, 150] }
  const sz = opts.size && sizes[opts.size]
  const lblCss = sz
    ? `@page{size:${sz[0]}mm ${sz[1]}mm;margin:2mm} body{margin:0}
       .lbl{width:${sz[0] - 6}mm;height:${sz[1] - 6}mm;box-sizing:border-box;padding:2mm;border:1px solid #000;text-align:center;page-break-after:always;display:flex;flex-direction:column;align-items:center;justify-content:center;overflow:hidden}`
    : `.lbl{display:inline-block;border:1px solid #000;padding:8px;margin:6px;text-align:center;width:220px}`
  const qrPx = sz && sz[1] >= 150 ? 150 : 90
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jsbarcode/3.11.6/JsBarcode.all.min.js"><\/script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"><\/script>
    <style>body{font-family:sans-serif}${lblCss}
    .loc{font-size:11px;color:#333;margin-bottom:2px}
    .code{font-weight:bold;font-size:14px;margin-bottom:2px}.skun{font-size:10px;color:#555}
    .rot{font-weight:bold;font-size:12px;border:1px solid #333;border-radius:3px;padding:0 5px;margin:2px 0;display:inline-block}
    .sub{font-size:11px;margin-top:2px}.qr{display:flex;justify-content:center;margin-top:2px}</style>
    </head><body>${cards}
    <script>
      document.querySelectorAll('svg.bc').forEach(function(el){ try{ JSBarcode(el,el.dataset.code,{format:'EAN13',height:40,fontSize:12}); }catch(e){ JSBarcode(el,el.dataset.code,{height:40,fontSize:12}); } });
      document.querySelectorAll('.qr').forEach(function(el){ new QRCode(el,{text:el.dataset.code,width:${qrPx},height:${qrPx}}); });
      setTimeout(function(){ window.print(); }, 500);
    <\/script></body></html>`)
  w.document.close()
}
async function printLocationLabel(node) {
  try {
    const { data } = await api.get(`/storage/locations/${node.id}/label`)
    printLabels('Etiqueta de endereço', [{ human: data.full_code, qr: data.qr, sub: data.level_type }])
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao gerar etiqueta.') }
}
async function printBoxLabels(a) {
  if (!confirm('Gerar etiquetas das caixas desta alocação?')) return
  try {
    const { data } = await api.post(`/storage/allocations/${a.id}/box-labels`)
    const sku = data.product?.sku || ''
    printLabels('Etiquetas de caixa', data.labels.map(l => ({
      human: sku, rotulo: l.rotulo, qr: l.token, sub: `${l.units_per_box} un/caixa`,
      location: a.location_full_code,
    })), { size: labelSize.value })
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao gerar etiquetas.') }
}

onMounted(async () => {
  if (isAdmin.value) {
    await loadWarehouses()
    // Admin: auto-seleciona o 1º galpão — senão a aba Estrutura (e os botões Área/Raiz e Gerar em
    // massa) fica escondida atrás de "Selecione um galpão" até o admin notar o seletor do topo.
    if (!warehouseId.value && warehouses.value.length) warehouseId.value = warehouses.value[0].id
  }
  await loadTree()
})
</script>

<style scoped>
.btn-xs { padding: 0 .25rem; font-size: .75rem; }
.modal-backdrop-custom { position: fixed; inset: 0; background: rgba(0,0,0,.5); display:flex; align-items:center; justify-content:center; z-index: 1050; }
.modal-card { background:#fff; border-radius:6px; padding:18px; width: 480px; max-width: 94vw; max-height: 92vh; overflow:auto; }
</style>
