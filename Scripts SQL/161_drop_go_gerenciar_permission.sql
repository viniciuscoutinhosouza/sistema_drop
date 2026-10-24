-- 161_drop_go_gerenciar_permission.sql
-- Remove a permissão de ação LEGADA 'go_gerenciar' ("Gerenciar Gestores Operacionais (GO)").
-- A tela "Gestores Operacionais" foi aposentada; o cadastro de um DONO de Galpão foi mesclado
-- na tela Galpões (bloco `owner` de POST /api/v1/warehouse, admin-only). A chave saiu do catálogo
-- em services/action_permissions.py; aqui limpamos os grants órfãos já concedidos a perfis —
-- se ficassem, o GET /profiles devolveria a chave crua e a UI a reenviaria no save, sendo
-- rejeitada como chave inválida (profiles.py valida contra VALID_ACTION_KEYS).
-- IMPORTANTE: rodar JUNTO com o deploy do código (não depois) — ver H3 da auditoria.
-- Idempotente (DELETE não falha se não houver linhas).
-- NÃO colocar COMMIT aqui: o run_migration.py já faz conn.commit() ao fim; um COMMIT
-- explícito deixaria 2 comandos num único execute() (ORA-00933). Uma só sentença DML.

DELETE FROM profile_action_permissions WHERE permission_key = 'go_gerenciar';
