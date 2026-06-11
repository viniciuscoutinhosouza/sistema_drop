<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">
              <i class="fas fa-tag text-primary mr-2"></i>Tabela NCM
            </h1>
            <small class="text-muted">Nomenclatura Comum do MERCOSUL — validação e importação do TEC</small>
          </div>
          <div class="col-sm-6 text-right">
            <span class="badge badge-pill px-3 py-2"
                  :class="dbCount > 0 ? 'badge-success' : 'badge-warning'">
              <i class="fas fa-database mr-1"></i>
              {{ dbCount > 0 ? dbCount.toLocaleString('pt-BR') + ' NCMs carregados' : 'Tabela vazia' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">

        <!-- Abas -->
        <div class="card card-primary card-outline">
          <div class="card-header p-0 pt-1 border-bottom-0">
            <ul class="nav nav-tabs" role="tablist">
              <li class="nav-item">
                <a class="nav-link" :class="{ active: tab === 'search' }"
                   href="#" @click.prevent="tab = 'search'">
                  <i class="fas fa-search mr-1"></i>Pesquisa
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" :class="{ active: tab === 'tree' }"
                   href="#" @click.prevent="openTree">
                  <i class="fas fa-sitemap mr-1"></i>Árvore
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" :class="{ active: tab === 'import' }"
                   href="#" @click.prevent="tab = 'import'">
                  <i class="fas fa-file-import mr-1"></i>Importar TEC
                  <span v-if="dbCount === 0" class="badge badge-warning ml-1">pendente</span>
                </a>
              </li>
              <li class="nav-item" v-if="isAdmin">
                <a class="nav-link" :class="{ active: tab === 'new' }"
                   href="#" @click.prevent="openNew">
                  <i class="fas fa-plus mr-1"></i>Novo NCM
                </a>
              </li>
            </ul>
          </div>

          <div class="card-body">

            <!-- ── ABA: PESQUISA ─────────────────────────────────────── -->
            <div v-show="tab === 'search'">
              <div class="row align-items-end mb-3">
                <div class="col-md-5">
                  <label class="small mb-1">Código ou descrição</label>
                  <div class="input-group input-group-sm">
                    <input v-model="search.q" class="form-control"
                           placeholder="ex: 8471 ou computador" @keyup.enter="runSearch">
                    <div class="input-group-append">
                      <button class="btn btn-primary" @click="runSearch" :disabled="searching">
                        <i class="fas" :class="searching ? 'fa-spinner fa-spin' : 'fa-search'"></i>
                      </button>
                    </div>
                  </div>
                </div>
                <div class="col-md-2">
                  <label class="small mb-1">Capítulo</label>
                  <input v-model="search.chapter" class="form-control form-control-sm"
                         maxlength="2" placeholder="ex: 84" @keyup.enter="runSearch">
                </div>
                <div class="col-md-2">
                  <label class="small mb-1">Status</label>
                  <select v-model="search.activeOnly" class="form-control form-control-sm" @change="runSearch">
                    <option :value="true">Ativos</option>
                    <option :value="false">Todos</option>
                  </select>
                </div>
                <div class="col-md-3 text-right">
                  <small class="text-muted" v-if="searchResult.total !== null">
                    {{ searchResult.total.toLocaleString('pt-BR') }} resultado(s)
                  </small>
                </div>
              </div>

              <!-- Tabela de resultados -->
              <div v-if="searching" class="text-center py-5">
                <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
              </div>

              <div v-else-if="searchResult.items.length === 0 && searchResult.total !== null"
                   class="text-center py-4 text-muted">
                <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                Nenhum NCM encontrado.
                <span v-if="dbCount === 0">
                  A tabela está vazia — importe o TEC na aba <strong>Importar TEC</strong>.
                </span>
              </div>

              <div v-else-if="searchResult.items.length > 0">
                <table class="table table-sm table-hover mb-2">
                  <thead class="thead-light">
                    <tr>
                      <th style="width:110px">Código</th>
                      <th>Descrição</th>
                      <th style="width:80px" class="text-center">Cap.</th>
                      <th style="width:80px" class="text-center">IPI %</th>
                      <th style="width:70px" class="text-center">Status</th>
                      <th v-if="isAdmin" style="width:80px"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="ncm in searchResult.items" :key="ncm.id">
                      <td>
                        <code class="text-primary">{{ formatCode(ncm.code) }}</code>
                      </td>
                      <td>{{ ncm.description }}</td>
                      <td class="text-center">
                        <span class="badge badge-light">{{ ncm.chapter }}</span>
                      </td>
                      <td class="text-center">
                        {{ ncm.ipi_rate !== null ? ncm.ipi_rate + '%' : '—' }}
                      </td>
                      <td class="text-center">
                        <span class="badge" :class="ncm.is_active ? 'badge-success' : 'badge-secondary'">
                          {{ ncm.is_active ? 'Ativo' : 'Inativo' }}
                        </span>
                      </td>
                      <td v-if="isAdmin" class="text-right">
                        <button class="btn btn-xs btn-outline-secondary" @click="openEdit(ncm)">
                          <i class="fas fa-edit"></i>
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>

                <!-- Paginação -->
                <div class="d-flex align-items-center justify-content-between">
                  <small class="text-muted">
                    Exibindo {{ searchResult.offset + 1 }}–{{ Math.min(searchResult.offset + searchResult.items.length, searchResult.total) }}
                    de {{ searchResult.total.toLocaleString('pt-BR') }}
                  </small>
                  <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-secondary"
                            :disabled="searchResult.offset === 0"
                            @click="goPage(-1)">
                      <i class="fas fa-chevron-left"></i>
                    </button>
                    <button class="btn btn-outline-secondary" disabled>
                      Pág {{ currentPage }}
                    </button>
                    <button class="btn btn-outline-secondary"
                            :disabled="searchResult.offset + PAGE_SIZE >= searchResult.total"
                            @click="goPage(1)">
                      <i class="fas fa-chevron-right"></i>
                    </button>
                  </div>
                </div>
              </div>

              <!-- Empty state inicial -->
              <div v-else class="text-center py-4 text-muted">
                <i class="fas fa-search fa-2x mb-2 d-block"></i>
                Digite um código ou descrição e pressione Enter para pesquisar.
              </div>
            </div>

            <!-- ── ABA: ÁRVORE ──────────────────────────────────────── -->
            <div v-show="tab === 'tree'">

              <div v-if="dbCount === 0" class="text-center py-5 text-muted">
                <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                Importe o TEC primeiro na aba <strong>Importar TEC</strong>.
              </div>

              <div v-else>
                <!-- Breadcrumb de navegação -->
                <nav aria-label="breadcrumb" class="mb-3">
                  <ol class="breadcrumb mb-0 bg-transparent px-0">
                    <li class="breadcrumb-item">
                      <a href="#" @click.prevent="treeGoRoot">
                        <i class="fas fa-home mr-1"></i>Seções
                      </a>
                    </li>
                    <li v-for="(crumb, i) in treeCrumbs" :key="crumb.code"
                        class="breadcrumb-item"
                        :class="{ active: i === treeCrumbs.length - 1 }">
                      <a v-if="i < treeCrumbs.length - 1"
                         href="#" @click.prevent="treeGoToCrumb(i)">
                        {{ crumb.code }}
                      </a>
                      <span v-else>{{ crumb.code }} — {{ crumb.description?.slice(0, 40) }}{{ crumb.description?.length > 40 ? '…' : '' }}</span>
                    </li>
                  </ol>
                </nav>

                <!-- Lista de nós do nível atual -->
                <div v-if="treeLoading" class="text-center py-4">
                  <i class="fas fa-spinner fa-spin fa-lg text-muted"></i>
                </div>

                <div v-else-if="treeNodes.length === 0" class="text-center py-4 text-muted">
                  Nenhum item encontrado neste nível.
                </div>

                <ul v-else class="list-group list-group-flush">
                  <li v-for="node in treeNodes" :key="node.code"
                      class="list-group-item list-group-item-action px-2 py-2"
                      :class="{ 'list-group-item-light': !node.is_leaf }"
                      style="cursor: pointer"
                      @click="treeExpand(node)">

                    <div class="d-flex align-items-center">
                      <!-- Ícone por nível -->
                      <span class="mr-2 text-center" style="width:24px; flex-shrink:0">
                        <i v-if="node.is_leaf"       class="fas fa-tag text-primary"  style="font-size:13px"></i>
                        <i v-else-if="node.code.length === 2" class="fas fa-layer-group text-dark" style="font-size:13px"></i>
                        <i v-else-if="node.code.length === 4" class="fas fa-folder text-warning"   style="font-size:13px"></i>
                        <i v-else                    class="fas fa-folder-open text-info"           style="font-size:13px"></i>
                      </span>

                      <!-- Código formatado -->
                      <code class="mr-2 font-weight-bold"
                            :class="node.is_leaf ? 'text-primary' : 'text-dark'"
                            style="min-width:80px; font-size:13px">
                        {{ formatCode(node.code) }}
                      </code>

                      <!-- Descrição -->
                      <span class="flex-grow-1 small">{{ node.description }}</span>

                      <!-- Badge de contagem + seta -->
                      <div class="d-flex align-items-center ml-2" style="flex-shrink:0">
                        <span v-if="!node.is_leaf"
                              class="badge badge-secondary mr-2"
                              style="font-size:10px"
                              :title="`${node.count} NCMs neste grupo`">
                          {{ node.count }}
                        </span>
                        <i v-if="!node.is_leaf" class="fas fa-chevron-right text-muted" style="font-size:10px"></i>
                        <i v-else class="fas fa-circle text-primary" style="font-size:8px"></i>
                      </div>
                    </div>

                  </li>
                </ul>

                <!-- Rodapé informativo -->
                <div class="text-muted small mt-2 px-1">
                  <span v-if="treeCrumbs.length === 0">
                    {{ treeNodes.length }} capítulos
                    <span v-if="treeNodes[0]?.section" class="ml-2 text-muted">
                      — clique para expandir posições
                    </span>
                  </span>
                  <span v-else-if="!treeNodes[0]?.is_leaf">
                    {{ treeNodes.length }} grupo(s) — clique para expandir
                  </span>
                  <span v-else>
                    {{ treeNodes.length }} NCM(s) — clique para copiar o código
                  </span>
                </div>
              </div>
            </div>

            <!-- ── ABA: IMPORTAÇÃO ───────────────────────────────────── -->
            <div v-show="tab === 'import'">

              <!-- ── Opção 1: Sincronizar direto do governo (recomendada) ── -->
              <div class="card card-outline card-primary mb-4">
                <div class="card-header py-2">
                  <h6 class="card-title mb-0">
                    <i class="fas fa-cloud-download-alt text-primary mr-2"></i>
                    Sincronizar do Portal Único Siscomex
                    <span class="badge badge-primary ml-2" style="font-size:10px">Recomendado</span>
                  </h6>
                </div>
                <div class="card-body">
                  <p class="small text-muted mb-3">
                    Baixa e importa a TEC completa diretamente da API pública do governo federal
                    <code>(portalunico.siscomex.gov.br)</code> — sem precisar de nenhum arquivo.
                    O sistema busca sempre a versão mais recente vigente.
                  </p>

                  <!-- Resultado do teste de conectividade -->
                  <div v-if="connectTest" class="mb-3">
                    <div class="alert py-2 mb-0"
                         :class="connectTest.ok ? 'alert-success' : 'alert-danger'">
                      <div class="d-flex align-items-center">
                        <i class="fas mr-2"
                           :class="connectTest.ok ? 'fa-check-circle' : 'fa-times-circle'"></i>
                        <span v-if="connectTest.ok" class="small">
                          Conectado — TEC vigente: <strong>{{ connectTest.vigencia }}</strong>
                          · {{ connectTest.content_length_kb }} KB · {{ connectTest.elapsed_ms }}ms
                        </span>
                        <span v-else class="small">
                          {{ connectTest.error }}
                        </span>
                      </div>
                      <div v-if="connectTest.suggestion" class="small mt-1 text-danger">
                        {{ connectTest.suggestion }}
                      </div>
                    </div>
                  </div>

                  <!-- Abas: auto-sync vs upload JSON -->
                  <ul class="nav nav-pills nav-sm mb-3">
                    <li class="nav-item">
                      <a class="nav-link py-1 px-3" :class="{ active: siscomexMode === 'auto' }"
                         href="#" @click.prevent="siscomexMode = 'auto'">
                        <i class="fas fa-sync-alt mr-1"></i>Automático
                      </a>
                    </li>
                    <li class="nav-item">
                      <a class="nav-link py-1 px-3" :class="{ active: siscomexMode === 'upload' }"
                         href="#" @click.prevent="siscomexMode = 'upload'">
                        <i class="fas fa-file-upload mr-1"></i>Eu baixo o arquivo
                      </a>
                    </li>
                  </ul>

                  <!-- Modo automático -->
                  <div v-if="siscomexMode === 'auto'">
                    <div class="row align-items-end">
                      <div class="col-md-5">
                        <div class="custom-control custom-switch mb-2">
                          <input type="checkbox" class="custom-control-input" id="siscomexOverwrite"
                                 v-model="siscomexOptions.overwrite">
                          <label class="custom-control-label small" for="siscomexOverwrite">
                            Sobrescrever NCMs existentes
                            <small class="d-block text-muted">Use na renovação anual do TEC</small>
                          </label>
                        </div>
                      </div>
                      <div class="col-md-7">
                        <button class="btn btn-outline-secondary btn-sm mr-2"
                                :disabled="testing || syncing"
                                @click="testConnectivity"
                                title="Verifica se o servidor consegue acessar o Siscomex">
                          <i class="fas mr-1"
                             :class="testing ? 'fa-spinner fa-spin' : 'fa-plug'"></i>
                          {{ testing ? 'Testando...' : 'Testar conexão' }}
                        </button>
                        <button class="btn btn-primary"
                                :disabled="syncing || testing"
                                @click="startSiscomexSync">
                          <i class="fas mr-2"
                             :class="syncing ? 'fa-spinner fa-spin' : 'fa-sync-alt'"></i>
                          {{ syncing ? 'Baixando e importando...' : 'Sincronizar agora' }}
                        </button>
                        <small v-if="!syncing && !testing" class="d-block text-muted mt-1">
                          ~10.500 NCMs · aprox. 30–60 segundos
                        </small>
                      </div>
                    </div>
                  </div>

                  <!-- Modo upload manual do JSON -->
                  <div v-else>
                    <div class="alert alert-info small mb-3 py-2">
                      <p class="mb-1 font-weight-bold">
                        <i class="fas fa-download mr-1"></i>
                        1. Baixe o arquivo no seu navegador:
                      </p>
                      <a href="https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json?perfil=PUBLICO"
                         target="_blank" rel="noopener"
                         class="btn btn-sm btn-outline-primary mb-2">
                        <i class="fas fa-external-link-alt mr-1"></i>
                        Abrir link do Siscomex
                      </a>
                      <br>
                      <small class="text-muted">
                        O arquivo tem ~3 MB e se chama <code>Tabela_NCM_Vigente_XXXXXXXX.json</code>.
                        Se o navegador mostrar texto em vez de baixar, pressione <kbd>Ctrl+S</kbd> para salvar.
                      </small>
                      <hr class="my-2">
                      <p class="mb-0">
                        <i class="fas fa-exclamation-triangle text-warning mr-1"></i>
                        <strong>Atenção:</strong> O Siscomex limita 3 downloads por hora por IP.
                        Se o arquivo baixado for pequeno (&lt; 1 MB), aguarde e tente novamente.
                      </p>
                    </div>

                    <!-- Drop zone JSON -->
                    <div class="border rounded p-3 text-center mb-3"
                         :class="[isDraggingJson ? 'border-primary bg-light' : 'border-dashed', importingJson ? 'opacity-50' : '']"
                         style="border-style: dashed !important; cursor: pointer"
                         @dragover.prevent="isDraggingJson = true"
                         @dragleave="isDraggingJson = false"
                         @drop.prevent="onDropJson"
                         @click="$refs.jsonInput.click()">
                      <input ref="jsonInput" type="file" accept=".json,application/json" class="d-none"
                             @change="onJsonSelect">
                      <div v-if="!selectedJson">
                        <i class="fas fa-file-code fa-2x text-muted mb-2 d-block"></i>
                        <p class="mb-0 small">
                          <strong>Arraste o arquivo JSON</strong> ou clique para selecionar
                        </p>
                        <small class="text-muted">Arquivo .json do Portal Único Siscomex</small>
                      </div>
                      <div v-else>
                        <i class="fas fa-check-circle fa-2x text-success mb-2 d-block"></i>
                        <p class="mb-0 font-weight-bold small">{{ selectedJson.name }}</p>
                        <small class="text-muted">{{ (selectedJson.size / 1024 / 1024).toFixed(1) }} MB</small>
                      </div>
                    </div>

                    <div class="d-flex align-items-center">
                      <div class="custom-control custom-switch mr-3">
                        <input type="checkbox" class="custom-control-input" id="jsonOverwrite"
                               v-model="siscomexOptions.overwrite">
                        <label class="custom-control-label small" for="jsonOverwrite">
                          Sobrescrever existentes
                        </label>
                      </div>
                      <button class="btn btn-primary"
                              :disabled="!selectedJson || importingJson"
                              @click="startJsonImport">
                        <i class="fas mr-1"
                           :class="importingJson ? 'fa-spinner fa-spin' : 'fa-file-import'"></i>
                        {{ importingJson ? 'Importando...' : 'Importar JSON' }}
                      </button>
                      <button v-if="selectedJson && !importingJson"
                              class="btn btn-outline-secondary btn-sm ml-2"
                              @click="selectedJson = null; syncResult = null">
                        <i class="fas fa-times"></i>
                      </button>
                    </div>

                    <div v-if="importingJson" class="mt-3">
                      <div class="progress">
                        <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary"
                             style="width: 100%"></div>
                      </div>
                      <small class="text-muted">Processando ~10.500 NCMs…</small>
                    </div>
                  </div>

                  <!-- Progresso -->
                  <div v-if="syncing" class="mt-3">
                    <div class="progress">
                      <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary"
                           style="width: 100%"></div>
                    </div>
                    <small class="text-muted">
                      Conectando ao Portal Único Siscomex e processando ~10.500 NCMs…
                    </small>
                  </div>

                  <!-- Resultado da sincronização -->
                  <div v-if="syncResult" class="mt-3">
                    <div class="alert mb-0"
                         :class="syncResult.errors > 0 ? 'alert-warning' : 'alert-success'">
                      <div class="d-flex align-items-center mb-2">
                        <i class="fas mr-2"
                           :class="syncResult.errors > 0 ? 'fa-exclamation-triangle' : 'fa-check-circle'"></i>
                        <strong>Sincronização concluída</strong>
                        <span v-if="syncResult.source_date" class="ml-2 small text-muted">
                          · {{ syncResult.source_date }}
                        </span>
                      </div>
                      <div class="row text-center">
                        <div class="col-3">
                          <div class="h4 text-success mb-0">{{ syncResult.created }}</div>
                          <small>Criados</small>
                        </div>
                        <div class="col-3">
                          <div class="h4 text-info mb-0">{{ syncResult.updated }}</div>
                          <small>Atualizados</small>
                        </div>
                        <div class="col-3">
                          <div class="h4 text-muted mb-0">{{ syncResult.skipped }}</div>
                          <small>Ignorados</small>
                        </div>
                        <div class="col-3">
                          <div class="h4 text-danger mb-0">{{ syncResult.errors }}</div>
                          <small>Erros</small>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Separador -->
              <div class="d-flex align-items-center mb-4">
                <hr class="flex-grow-1"><span class="px-3 text-muted small">ou importe via arquivo CSV</span><hr class="flex-grow-1">
              </div>

              <!-- ── Opção 2: Upload manual de CSV ── -->
              <div class="row">
                <div class="col-lg-7">

                  <!-- Drop zone -->
                  <div class="border rounded p-4 text-center mb-3"
                       :class="[isDragging ? 'border-primary bg-light' : 'border-dashed', importing ? 'opacity-50' : '']"
                       style="border-style: dashed !important; cursor: pointer"
                       @dragover.prevent="isDragging = true"
                       @dragleave="isDragging = false"
                       @drop.prevent="onDrop"
                       @click="$refs.fileInput.click()">
                    <input ref="fileInput" type="file" accept=".csv,text/csv" class="d-none"
                           @change="onFileSelect">
                    <div v-if="!selectedFile">
                      <i class="fas fa-file-csv fa-3x text-muted mb-3 d-block"></i>
                      <p class="mb-1">
                        <strong>Arraste o CSV aqui</strong> ou clique para selecionar
                      </p>
                      <small class="text-muted">
                        Arquivo .csv — separador <code>;</code> ou <code>,</code> — máx 20 MB
                      </small>
                    </div>
                    <div v-else>
                      <i class="fas fa-check-circle fa-2x text-success mb-2 d-block"></i>
                      <p class="mb-0 font-weight-bold">{{ selectedFile.name }}</p>
                      <small class="text-muted">{{ (selectedFile.size / 1024).toFixed(1) }} KB</small>
                    </div>
                  </div>

                  <!-- Opções CSV -->
                  <div class="form-group mb-3">
                    <div class="custom-control custom-switch">
                      <input type="checkbox" class="custom-control-input" id="overwriteSwitch"
                             v-model="importOptions.overwrite">
                      <label class="custom-control-label" for="overwriteSwitch">
                        Sobrescrever NCMs existentes
                        <small class="d-block text-muted">
                          Atualiza descrição e alíquota IPI de NCMs já cadastrados.
                        </small>
                      </label>
                    </div>
                  </div>

                  <!-- Botões CSV -->
                  <div class="d-flex align-items-center">
                    <button class="btn btn-secondary mr-2"
                            :disabled="!selectedFile || importing"
                            @click="startImport">
                      <i class="fas mr-1"
                         :class="importing ? 'fa-spinner fa-spin' : 'fa-upload'"></i>
                      {{ importing ? 'Importando...' : 'Importar CSV' }}
                    </button>
                    <button class="btn btn-outline-secondary mr-2"
                            v-if="selectedFile && !importing"
                            @click="clearFile">
                      <i class="fas fa-times mr-1"></i>Remover arquivo
                    </button>
                    <a class="btn btn-outline-info btn-sm"
                       href="#" @click.prevent="downloadTemplate">
                      <i class="fas fa-download mr-1"></i>Baixar template CSV
                    </a>
                  </div>

                  <!-- Progresso CSV -->
                  <div v-if="importing" class="mt-3">
                    <div class="progress">
                      <div class="progress-bar progress-bar-striped progress-bar-animated"
                           style="width: 100%"></div>
                    </div>
                    <small class="text-muted">Processando...</small>
                  </div>

                  <!-- Resultado CSV -->
                  <div v-if="importResult" class="mt-3">
                    <div class="alert"
                         :class="importResult.errors > 0 ? 'alert-warning' : 'alert-success'">
                      <h6 class="mb-2">
                        <i class="fas mr-1"
                           :class="importResult.errors > 0 ? 'fa-exclamation-triangle' : 'fa-check-circle'"></i>
                        Importação concluída
                      </h6>
                      <div class="row text-center">
                        <div class="col-3">
                          <div class="h4 text-success mb-0">{{ importResult.created }}</div>
                          <small>Criados</small>
                        </div>
                        <div class="col-3">
                          <div class="h4 text-info mb-0">{{ importResult.updated }}</div>
                          <small>Atualizados</small>
                        </div>
                        <div class="col-3">
                          <div class="h4 text-muted mb-0">{{ importResult.skipped }}</div>
                          <small>Ignorados</small>
                        </div>
                        <div class="col-3">
                          <div class="h4 text-danger mb-0">{{ importResult.errors }}</div>
                          <small>Erros</small>
                        </div>
                      </div>
                      <ul v-if="importResult.error_details?.length" class="mb-0 mt-2 small pl-3">
                        <li v-for="(e, i) in importResult.error_details" :key="i">{{ e }}</li>
                      </ul>
                    </div>
                  </div>
                </div>

                <!-- Instrução lateral -->
                <div class="col-lg-5">
                  <div class="card card-outline card-secondary h-100">
                    <div class="card-header py-2">
                      <h6 class="card-title mb-0">
                        <i class="fas fa-question-circle text-info mr-1"></i>Como obter o TEC
                      </h6>
                    </div>
                    <div class="card-body small">
                      <ol class="pl-3 mb-3">
                        <li class="mb-2">
                          Acesse o portal MDIC / SISCOMEX ou o repositório oficial do governo:
                          <br><code class="small">portalunico.siscomex.gov.br</code>
                        </li>
                        <li class="mb-2">
                          Baixe o arquivo <strong>NCM completo</strong> em formato CSV (separador <code>;</code>).
                        </li>
                        <li class="mb-2">
                          O CSV do governo tem colunas:<br>
                          <code>CO_NCM</code>, <code>NO_NCM_POR</code>, <code>CO_NCM_SECROM</code>
                          <br>O sistema mapeia automaticamente esses nomes.
                        </li>
                        <li>
                          Faça o upload aqui. Para atualização anual, marque
                          <strong>Sobrescrever</strong>.
                        </li>
                      </ol>

                      <hr class="my-2">

                      <p class="mb-1 font-weight-bold">Formato do CSV aceito:</p>
                      <pre class="small bg-light p-2 rounded mb-0" style="font-size:0.72rem">code;description;chapter;ipi_rate
84713012;Notebooks;84;0.00
85171231;Smartphones;85;0.00</pre>
                    </div>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>

      </div>
    </section>

    <!-- Modal: criar / editar NCM avulso -->
    <div v-if="showModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-tag mr-2"></i>{{ editingId ? 'Editar NCM' : 'Novo NCM' }}
            </h5>
            <button type="button" class="close" @click="closeModal"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="row">
              <div class="col-md-5 form-group">
                <label class="small">Código NCM <span class="text-danger">*</span></label>
                <input v-model="modalForm.code" class="form-control" maxlength="10"
                       placeholder="00000000" :disabled="!!editingId">
                <small class="form-text text-muted">8 dígitos (pontos são removidos automaticamente)</small>
              </div>
              <div class="col-md-4 form-group">
                <label class="small">Capítulo</label>
                <input :value="modalForm.code ? modalForm.code.replace(/\D/g,'').slice(0,2) : ''"
                       class="form-control bg-light" readonly>
              </div>
              <div class="col-md-3 form-group">
                <label class="small">Alíq. IPI %</label>
                <input v-model.number="modalForm.ipi_rate" type="number" step="0.01"
                       min="0" max="300" class="form-control" placeholder="0.00">
              </div>
            </div>
            <div class="form-group">
              <label class="small">Descrição <span class="text-danger">*</span></label>
              <input v-model="modalForm.description" class="form-control"
                     placeholder="ex: Computadores portáteis (notebooks)">
            </div>
            <div class="form-group mb-0">
              <label class="small">Seção TEC</label>
              <input v-model="modalForm.section" class="form-control" maxlength="5"
                     placeholder="ex: XVI">
            </div>
            <div v-if="editingId" class="form-group mt-2 mb-0">
              <div class="custom-control custom-switch">
                <input type="checkbox" class="custom-control-input" id="ncmActive"
                       v-model="modalForm.is_active">
                <label class="custom-control-label" for="ncmActive">Ativo</label>
              </div>
            </div>
            <div v-if="modalError" class="alert alert-danger small mt-2">{{ modalError }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeModal">Cancelar</button>
            <button class="btn btn-primary" :disabled="savingModal" @click="saveModal">
              <i class="fas" :class="savingModal ? 'fa-spinner fa-spin' : 'fa-save'"></i>
              {{ savingModal ? 'Salvando...' : 'Salvar' }}
            </button>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const authStore = useAuthStore()
const toast = useToast()

const isAdmin = computed(() => authStore.user?.role === 'admin')
const PAGE_SIZE = 50

// ── Estado geral ──────────────────────────────────────────────────────────────
const tab = ref('search')
const dbCount = ref(0)

// ── Pesquisa ──────────────────────────────────────────────────────────────────
const searching = ref(false)
const search = reactive({ q: '', chapter: '', activeOnly: true })
const searchResult = reactive({ items: [], total: null, offset: 0 })
const currentPage = computed(() => Math.floor(searchResult.offset / PAGE_SIZE) + 1)

function formatCode(code) {
  if (!code || code.length !== 8) return code
  return `${code.slice(0,4)}.${code.slice(4,6)}.${code.slice(6)}`
}

async function runSearch(resetPage = true) {
  if (resetPage) searchResult.offset = 0
  searching.value = true
  try {
    const params = {
      active_only: search.activeOnly,
      limit: PAGE_SIZE,
      offset: searchResult.offset,
    }
    if (search.q.trim())      params.q = search.q.trim()
    if (search.chapter.trim()) params.chapter = search.chapter.trim()
    const { data } = await api.get('/ncm', { params })
    searchResult.items = data.items
    searchResult.total = data.total
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro na pesquisa')
  } finally {
    searching.value = false
  }
}

async function goPage(dir) {
  searchResult.offset = Math.max(0, searchResult.offset + dir * PAGE_SIZE)
  await runSearch(false)
}

async function fetchCount() {
  try {
    const { data } = await api.get('/ncm', { params: { active_only: false, limit: 1, offset: 0 } })
    dbCount.value = data.total || 0
  } catch { /* silencioso */ }
}

// ── Importação CSV ────────────────────────────────────────────────────────────
// ── Sincronização Siscomex ────────────────────────────────────────────────────
const syncing        = ref(false)
const testing        = ref(false)
const importingJson  = ref(false)
const syncResult     = ref(null)
const connectTest    = ref(null)
const selectedJson   = ref(null)
const isDraggingJson = ref(false)
const siscomexMode   = ref('upload')   // 'auto' | 'upload' — padrão: upload (mais confiável)
const siscomexOptions = reactive({ overwrite: false })
const jsonInput = ref(null)

async function testConnectivity() {
  testing.value = true
  connectTest.value = null
  try {
    const { data } = await api.get('/ncm/test-siscomex', { timeout: 40000 })
    connectTest.value = data
    if (!data.ok) toast.error('Servidor sem acesso ao Siscomex — use importação CSV')
  } catch (e) {
    connectTest.value = {
      ok: false,
      error: e.response?.data?.detail || 'Erro ao testar conectividade',
      suggestion: 'Verifique as regras de firewall do servidor ou use a importação via CSV.',
    }
  } finally {
    testing.value = false
  }
}

function onDropJson(e) {
  isDraggingJson.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) selectedJson.value = file
}
function onJsonSelect(e) {
  const file = e.target.files?.[0]
  if (file) selectedJson.value = file
}

async function startJsonImport() {
  if (!selectedJson.value) return
  importingJson.value = true
  syncResult.value = null
  const fd = new FormData()
  fd.append('json_file', selectedJson.value)
  try {
    const { data } = await api.post(
      `/ncm/import-json?overwrite=${siscomexOptions.overwrite}`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 150000 }
    )
    syncResult.value = data
    await fetchCount()
    treeNodes.value = []
    treeCrumbs.value = []
    toast.success(`TEC importada: ${data.created} criados, ${data.updated} atualizados`)
  } catch (e) {
    const msg = e.response?.data?.detail || 'Erro ao importar JSON'
    toast.error(msg)
    syncResult.value = { errors: 1, created: 0, updated: 0, skipped: 0 }
  } finally {
    importingJson.value = false
  }
}

async function startSiscomexSync() {
  syncing.value = true
  syncResult.value = null
  try {
    const { data } = await api.post(
      `/ncm/sync-siscomex?overwrite=${siscomexOptions.overwrite}`,
      null,
      { timeout: 150000 }
    )
    syncResult.value = data
    await fetchCount()
    // Recarrega árvore se estava aberta
    if (treeNodes.value.length > 0) {
      treeNodes.value = []
      treeCrumbs.value = []
    }
    toast.success(`TEC sincronizada: ${data.created} criados, ${data.updated} atualizados`)
  } catch (e) {
    const msg = e.response?.data?.detail || 'Erro ao conectar ao Siscomex'
    toast.error(msg)
    syncResult.value = { errors: 1, created: 0, updated: 0, skipped: 0, error_details: [msg] }
  } finally {
    syncing.value = false
  }
}

// ── Importação CSV ────────────────────────────────────────────────────────────
const fileInput = ref(null)
const isDragging = ref(false)
const importing = ref(false)
const selectedFile = ref(null)
const importResult = ref(null)
const importOptions = reactive({ overwrite: false })

function onDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) setFile(file)
}
function onFileSelect(e) {
  const file = e.target.files?.[0]
  if (file) setFile(file)
}
function setFile(file) {
  if (!file.name.endsWith('.csv')) {
    toast.error('Selecione um arquivo .csv')
    return
  }
  selectedFile.value = file
  importResult.value = null
}
function clearFile() {
  selectedFile.value = null
  importResult.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function startImport() {
  if (!selectedFile.value) return
  importing.value = true
  importResult.value = null
  const fd = new FormData()
  fd.append('csv_file', selectedFile.value)
  try {
    const { data } = await api.post(
      `/ncm/import-csv?overwrite=${importOptions.overwrite}`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 }
    )
    importResult.value = data
    await fetchCount()
    toast.success(`Importação concluída: ${data.created} criados, ${data.updated} atualizados`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro durante a importação')
  } finally {
    importing.value = false
  }
}

async function downloadTemplate() {
  try {
    const resp = await api.get('/ncm/template-csv', { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = 'template_ncm_tec.csv'
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    toast.error('Erro ao baixar template')
  }
}

// ── Modal criar/editar ────────────────────────────────────────────────────────
const showModal = ref(false)
const savingModal = ref(false)
const editingId = ref(null)
const modalError = ref('')
const modalForm = reactive({
  code: '', description: '', section: '', ipi_rate: null, is_active: true,
})

function openNew() {
  editingId.value = null
  Object.assign(modalForm, { code: '', description: '', section: '', ipi_rate: null, is_active: true })
  modalError.value = ''
  showModal.value = true
  tab.value = 'search'  // manter na aba ativa
}

function openEdit(ncm) {
  editingId.value = ncm.id
  Object.assign(modalForm, {
    code: ncm.code,
    description: ncm.description,
    section: ncm.section || '',
    ipi_rate: ncm.ipi_rate,
    is_active: ncm.is_active,
  })
  modalError.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
}

async function saveModal() {
  modalError.value = ''
  if (!modalForm.description.trim()) {
    modalError.value = 'Descrição é obrigatória'
    return
  }
  savingModal.value = true
  try {
    if (editingId.value) {
      const { data } = await api.patch(`/ncm/${editingId.value}`, {
        description: modalForm.description,
        section: modalForm.section || null,
        ipi_rate: modalForm.ipi_rate,
        is_active: modalForm.is_active,
      })
      const idx = searchResult.items.findIndex(n => n.id === editingId.value)
      if (idx !== -1) searchResult.items[idx] = data
      toast.success('NCM atualizado')
    } else {
      await api.post('/ncm', {
        code: modalForm.code,
        description: modalForm.description,
        section: modalForm.section || null,
        ipi_rate: modalForm.ipi_rate,
      })
      await fetchCount()
      toast.success('NCM criado')
    }
    closeModal()
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Erro ao salvar'
  } finally {
    savingModal.value = false
  }
}

// ── Árvore NCM ───────────────────────────────────────────────────────────────
const treeNodes   = ref([])
const treeCrumbs  = ref([])   // trilha: [{code, description}]
const treeLoading = ref(false)

async function openTree() {
  tab.value = 'tree'
  if (treeNodes.value.length === 0 && dbCount.value > 0) {
    await treeFetch('')
  }
}

async function treeFetch(prefix) {
  treeLoading.value = true
  try {
    const { data } = await api.get('/ncm/tree', { params: prefix ? { prefix } : {} })
    treeNodes.value = data
  } catch (e) {
    toast.error('Erro ao carregar árvore NCM')
  } finally {
    treeLoading.value = false
  }
}

async function treeExpand(node) {
  if (node.is_leaf) {
    // Folha: copiar código para clipboard
    try {
      await navigator.clipboard.writeText(node.code)
      toast.info(`NCM ${formatCode(node.code)} copiado`)
    } catch {
      toast.info(`NCM: ${formatCode(node.code)} — ${node.description}`)
    }
    return
  }
  treeCrumbs.value.push({ code: node.code, description: node.description })
  await treeFetch(node.code)
}

async function treeGoRoot() {
  treeCrumbs.value = []
  await treeFetch('')
}

async function treeGoToCrumb(index) {
  const crumb = treeCrumbs.value[index]
  treeCrumbs.value = treeCrumbs.value.slice(0, index + 1)
  await treeFetch(crumb.code)
}

// ── Init ──────────────────────────────────────────────────────────────────────
onMounted(async () => {
  await fetchCount()
  if (dbCount.value === 0) tab.value = 'import'
})
</script>

<style scoped>
.border-dashed { border-style: dashed !important; }
</style>
