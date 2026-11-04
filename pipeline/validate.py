# pipeline/validate.py
"""Config validation for pipeline/sandbox.yaml.

Pure function: validate(config) -> None, or raises ConfigError with a
precise message naming the offending location. No sqlite, no FastAPI,
no filesystem. Callable from tests without a running sandbox.
"""

_ALLOWED_ON = {"on_success", "on_not_found", "on_conflict", "on_invalid"}
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_ALLOWED_PARAM_SOURCES = {"path", "query", "body"}


class ConfigError(Exception):
    pass


def validate(config: dict) -> None:
    if not isinstance(config, dict):
        raise ConfigError("config root must be a mapping")

    databases = config.get("databases") or {}
    apis = config.get("apis") or {}

    if not isinstance(databases, dict):
        raise ConfigError("'databases' must be a mapping")
    if not isinstance(apis, dict):
        raise ConfigError("'apis' must be a mapping")

    _validate_databases(databases)
    _validate_apis(apis, databases)


def _validate_databases(databases: dict) -> None:
    for db_name, dbcfg in databases.items():
        if not isinstance(dbcfg, dict):
            raise ConfigError(f"databases.{db_name}: must be a mapping")
        if dbcfg.get("type") != "sqlite":
            raise ConfigError(
                f"databases.{db_name}.type: expected 'sqlite', got {dbcfg.get('type')!r}"
            )
        tables = dbcfg.get("tables")
        if not isinstance(tables, dict) or not tables:
            raise ConfigError(f"databases.{db_name}.tables: must be a non-empty mapping")

        for tbl_name, tcfg in tables.items():
            _validate_table(db_name, tbl_name, tcfg)


def _validate_table(db_name: str, tbl_name: str, tcfg) -> None:
    loc = f"databases.{db_name}.tables.{tbl_name}"
    if not isinstance(tcfg, dict):
        raise ConfigError(f"{loc}: must be a mapping")
    cols = tcfg.get("columns")
    if not isinstance(cols, dict) or not cols:
        raise ConfigError(f"{loc}.columns: must be a non-empty mapping")
    colnames = list(cols.keys())
    for row_i, row in enumerate(tcfg.get("seed") or []):
        if not isinstance(row, dict):
            raise ConfigError(f"{loc}.seed[{row_i}]: must be a mapping")
        missing = [c for c in colnames if c not in row]
        if missing:
            raise ConfigError(f"{loc}.seed[{row_i}]: missing column(s) {missing}")
        extra = [k for k in row if k not in cols]
        if extra:
            raise ConfigError(f"{loc}.seed[{row_i}]: unknown column(s) {extra}")


def _validate_apis(apis: dict, databases: dict) -> None:
    for api_name, apicfg in apis.items():
        if not isinstance(apicfg, dict):
            raise ConfigError(f"apis.{api_name}: must be a mapping")
        kind = apicfg.get("type")
        if kind not in ("sql", "mock"):
            raise ConfigError(
                f"apis.{api_name}.type: expected 'sql' or 'mock', got {kind!r}"
            )
        if kind == "sql":
            db_ref = apicfg.get("database")
            if not db_ref:
                raise ConfigError(f"apis.{api_name}.database: required for type 'sql'")
            if db_ref not in databases:
                raise ConfigError(
                    f"apis.{api_name}.database: references {db_ref!r}, "
                    f"but databases has {sorted(databases)}"
                )

        endpoints = apicfg.get("endpoints")
        if not isinstance(endpoints, list) or not endpoints:
            raise ConfigError(f"apis.{api_name}.endpoints: must be a non-empty list")
        for ep_i, ep in enumerate(endpoints):
            _validate_endpoint(api_name, ep_i, ep, kind)


def _validate_endpoint(api_name: str, ep_i: int, ep, kind: str) -> None:
    loc = f"apis.{api_name}.endpoints[{ep_i}]"
    if not isinstance(ep, dict):
        raise ConfigError(f"{loc}: must be a mapping")

    method = (ep.get("method") or "").upper()
    if method not in _ALLOWED_METHODS:
        raise ConfigError(
            f"{loc}.method: expected one of {sorted(_ALLOWED_METHODS)}, got {ep.get('method')!r}"
        )
    path = ep.get("path")
    if not isinstance(path, str) or not path.startswith("/"):
        raise ConfigError(f"{loc}.path: must be a string starting with '/', got {path!r}")

    if kind == "mock":
        resp = ep.get("response")
        if not isinstance(resp, dict) or "status" not in resp or "body" not in resp:
            raise ConfigError(f"{loc}.response: must have 'status' and 'body'")
        return

    _validate_sql_endpoint(loc, ep)


def _validate_sql_endpoint(loc: str, ep: dict) -> None:
    sql = ep.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise ConfigError(f"{loc}.sql: must be a non-empty string")

    params = ep.get("params") or {}
    if not isinstance(params, dict):
        raise ConfigError(f"{loc}.params: must be a mapping")
    for pname, pspec in params.items():
        ploc = f"{loc}.params.{pname}"
        if not isinstance(pspec, dict):
            raise ConfigError(f"{ploc}: must be a mapping")
        if pspec.get("type") not in ("integer", "real", "text"):
            raise ConfigError(
                f"{ploc}.type: expected integer|real|text, got {pspec.get('type')!r}"
            )
        src = pspec.get("source", "query")
        if src not in _ALLOWED_PARAM_SOURCES:
            raise ConfigError(
                f"{ploc}.source: expected {sorted(_ALLOWED_PARAM_SOURCES)}, got {src!r}"
            )

    n_q = sql.count("?")
    n_p = len(params)
    if n_q != n_p:
        raise ConfigError(
            f"{loc}: sql has {n_q} '?' placeholder(s) but params declares {n_p} param(s). "
            f"Declared: {list(params)}."
        )

    unknown_on = {k for k in ep if k.startswith("on_")} - _ALLOWED_ON
    if unknown_on:
        raise ConfigError(
            f"{loc}: unknown outcome(s) {sorted(unknown_on)}; allowed: {sorted(_ALLOWED_ON)}"
        )
    if "on_success" not in ep:
        raise ConfigError(f"{loc}: 'on_success' is required for sql endpoints")



if __name__ == "__main__":
    import sys
    import yaml

    if len(sys.argv) < 2:
        print("usage: python validate.py path/to/sandbox.yaml")
        raise SystemExit(2)

    path = sys.argv[1]
    with open(path) as f:
        cfg = yaml.safe_load(f)

    try:
        validate(cfg)
    except ConfigError as e:
        print(f"INVALID: {e}")
        raise SystemExit(1)

    print(f"ok: {path}")