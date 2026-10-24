-- 160_drop_criar_ac_permission.sql
-- Remove a permissão de ação LEGADA 'criar_ac' ("Cadastrar Gestor de Conta (AC)").
-- O endpoint POST /auth/register/ac (fluxo antigo: Galpão cadastrava seu AC) foi removido;
-- o cadastro de usuário hoje é por /auth/register/user + Perfil de Acesso (tela Usuários).
-- A chave saiu do catálogo em services/action_permissions.py; aqui só limpamos os grants
-- órfãos já concedidos a perfis (ficariam inertes, mas somem da trilha).
-- Idempotente (DELETE não falha se não houver linhas).
-- NÃO colocar COMMIT aqui: o run_migration.py já faz conn.commit() ao fim; um COMMIT
-- explícito deixaria 2 comandos num único execute() (ORA-00933). Uma só sentença DML.

DELETE FROM profile_action_permissions WHERE permission_key = 'criar_ac';
