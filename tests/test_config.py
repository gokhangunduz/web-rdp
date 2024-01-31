import pytest

from config import DEFAULT_PORT, parse_args


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("HOST", "PORT", "USERNAME", "PASSWORD"):
        monkeypatch.delenv(f"WEB_RDP_{name}", raising=False)


def test_defaults_generate_a_password():
    config = parse_args([])
    assert config.port == DEFAULT_PORT
    assert config.username == "admin"
    assert config.password_generated
    assert len(config.password) >= 12
    assert not config.tls


def test_generated_passwords_differ():
    assert parse_args([]).password != parse_args([]).password


def test_explicit_options():
    config = parse_args(["--host", "127.0.0.1", "--port", "8080", "--password", "pw"])
    assert (config.host, config.port, config.password) == ("127.0.0.1", 8080, "pw")
    assert not config.password_generated


def test_environment_variables(monkeypatch):
    monkeypatch.setenv("WEB_RDP_PASSWORD", "from-env")
    monkeypatch.setenv("WEB_RDP_PORT", "9000")
    config = parse_args([])
    assert (config.password, config.port) == ("from-env", 9000)


def test_tls_needs_both_files():
    with pytest.raises(SystemExit):
        parse_args(["--cert", "cert.pem"])
    assert parse_args(["--cert", "cert.pem", "--key", "key.pem"]).tls


@pytest.mark.parametrize("port", ["0", "70000", "-1"])
def test_invalid_port_is_rejected(port):
    with pytest.raises(SystemExit):
        parse_args(["--port", port])
