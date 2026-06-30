"""Teste da cifragem da senha do certificado A1 (Fernet master key)."""
import pytest

from services.fiscal import cert_crypto


def test_encrypt_decrypt_round_trip():
    master = "uma-master-key-aleatoria-de-teste-1234567890"
    senha = "S3nh@DoCertificado!"
    token = cert_crypto.encrypt(senha, master=master)
    assert token != senha            # cifrado, não em claro
    assert cert_crypto.decrypt(token, master=master) == senha


def test_decrypt_with_wrong_master_fails():
    token = cert_crypto.encrypt("abc", master="key-correta-aaaaaaaaaaaaaaaaaaaa")
    with pytest.raises(cert_crypto.CertCryptoError):
        cert_crypto.decrypt(token, master="key-errada-bbbbbbbbbbbbbbbbbbbbbb")


def test_missing_master_raises():
    with pytest.raises(cert_crypto.CertCryptoError):
        cert_crypto.encrypt("abc", master="")


def test_tokens_are_non_deterministic():
    # Fernet inclui IV/timestamp → dois ciframentos da mesma senha diferem,
    # mas ambos decifram para o mesmo valor.
    master = "m" * 40
    t1 = cert_crypto.encrypt("igual", master=master)
    t2 = cert_crypto.encrypt("igual", master=master)
    assert t1 != t2
    assert cert_crypto.decrypt(t1, master=master) == "igual"
    assert cert_crypto.decrypt(t2, master=master) == "igual"
