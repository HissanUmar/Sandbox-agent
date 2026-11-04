"""Hospital environment — runtime helpers.

Same shape as environments/shop/_runtime.py. Reads SB_API_* from the env
dict stashed by run_agent.py.
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