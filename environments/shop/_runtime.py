"""Per-environment runtime helpers. Reads SB_API_* from the sandbox env.

The env dict is stashed here by run_agent.py before agent.main() runs, so
tools don't depend on os.environ (which the sandbox no longer mutates).
"""
_ENV = {}


def configure(env: dict) -> None:
    _ENV.clear()
    _ENV.update(env)


def api_url(name: str) -> str:
    key = f"SB_API_{name.upper()}"
    if key not in _ENV:
        raise RuntimeError(f"{key} not configured; call configure(env) first")
    return _ENV[key]


def call(resp) -> dict | list:
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    if resp.status_code >= 400:
        body = {**body, "_status": resp.status_code}
    return body