from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mairaiy_voice_compose_is_private_pinned_and_low_memory():
    compose = read("docker-compose.hostinger.yml")
    assert "mairaiy-voice:" in compose
    assert 'profiles: ["voice"]' in compose
    assert "palashdeb/omnivoice-studio:0.5.0@sha256:2bf2d4d86591672caedada4384895c0e0ca4fdb3ec7f8efed257210b5abd4629" in compose
    assert "OMNIVOICE_TTS_BACKEND:" in compose and "omnivoice-gguf" in compose
    assert "OMNIVOICE_DEVICE:" in compose and "cpu" in compose
    assert 'expose:' in compose and '"3900"' in compose
    assert "3900:3900" not in compose
    assert "horizon_mairaiy_voice_data" in compose
    assert "horizon_mairaiy_hf_cache" in compose


def test_nginx_voice_proxy_is_lazy_and_not_publicly_bound_to_container_port():
    nginx = read("hostinger/evidence-nginx.conf")
    assert "location /voice/" in nginx
    assert "resolver 127.0.0.11" in nginx
    assert "set $mairaiy_voice_backend http://mairaiy-voice:3900;" in nginx
    assert "proxy_set_header Authorization $http_authorization;" in nginx
    assert "proxy_buffering off;" in nginx
    assert "client_max_body_size 24m;" in nginx


def test_managed_node_proxy_exposes_only_minimal_voice_contract():
    source = read("src/mairaiy_voice_proxy.js")
    assert "GET /health" in source
    assert "GET /.well-known/voicestudio-speech" in source
    assert "GET /v1/audio/voices" in source
    assert "GET /v1/models" in source
    assert "POST /v1/audio/speech" in source
    assert "config.mairaiyVoice.upstreamApiKey" in source
    assert "redirect: 'error'" in source
    assert "url.protocol !== 'https:'" in source
    assert "Readable.fromWeb(upstream.body).pipe(res)" in source

    server = read("server_core.js")
    assert "installMairaiyVoiceProxy(app);" in server
    assert server.index("installMairaiyVoiceProxy(app);") < server.index("app.use(requireQuanticIdentity);")


def test_voice_deploy_script_has_resource_and_secret_guards():
    script = read("scripts/hostinger_deploy.sh")
    assert "MAIRAIY_VOICE_ENABLED" in script
    assert "OMNIVOICE_API_KEY" in script
    assert "7340032" in script
    assert "--profile voice" in script
    assert "/voice/health" in script
    subprocess.run(["bash", "-n", str(ROOT / "scripts/hostinger_deploy.sh")], check=True)


def test_voice_environment_contract_is_documented():
    vps_env = read(".env.hostinger.example")
    node_env = read(".env.node.hostinger.example")
    assert "MAIRAIY_VOICE_ENGINE=omnivoice-gguf" in vps_env
    assert "OMNIVOICE_API_KEY=" in vps_env
    assert "MAIRAIY_VOICE_UPSTREAM_URL=" in node_env
    assert "MAIRAIY_VOICE_PROXY_TOKEN=" in node_env
    assert "MAIRAIY_VOICE_UPSTREAM_API_KEY=" in node_env
