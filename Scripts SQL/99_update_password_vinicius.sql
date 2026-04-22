-- Atualiza senha do usuário vinicius@madeingroup.com.br
UPDATE users
SET password_hash = '$2b$12$0/i7JsCrG2jKXmSgHFuNROpMKhyaQmym82rnwznKwyDIXuuPgc9.a'
WHERE email = 'vinicius@madeingroup.com.br';

COMMIT;
