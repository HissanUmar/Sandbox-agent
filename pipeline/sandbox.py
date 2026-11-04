# sandbox.py
import os, sqlite3, tempfile, shutil, contextlib
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn, threading, socket, time

from .validate import validate, ConfigError


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]; s.close(); return port


def _run_sql(db_path, sql, params):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON") 
    try:
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, r)) for r in cur]
        affected = cur.rowcount
        conn.commit()
        return rows, affected
    finally:
        conn.close()

def _build_create_table(tbl, tcfg):
    col_defs = []
    fk_defs = []
    for cname, cspec in tcfg["columns"].items():
        if isinstance(cspec, str):
            ctype, pk, ref = cspec, False, None
        else:
            ctype = cspec.get("type", "text")
            pk = cspec.get("primary_key", False)
            ref = cspec.get("references")
        parts = [cname, ctype]
        if pk:
            parts.append("PRIMARY KEY")
        col_defs.append(" ".join(parts))
        if ref:
            target_tbl, target_col = ref.split(".")
            fk_defs.append(f"FOREIGN KEY ({cname}) REFERENCES {target_tbl}({target_col})")
    body = ", ".join(col_defs + fk_defs)
    return f"CREATE TABLE {tbl} ({body})"

def _check_params(ep, request):
    """Validate declared params against the request. Returns (values, error)."""
    declared = ep.get("params") or {}
    values = []
    for name, spec in declared.items():
        src = spec.get("source", "query")
        if src == "path":
            raw = request.path_params.get(name)
        elif src == "body":
            raw = getattr(request, "_body", {}).get(name)
        else:
            raw = request.query_params.get(name)

        if raw is None:
            if spec.get("required"):
                return None, f"missing required param: {name}"
            values.append(None)
            continue

        t = spec.get("type")
        try:
            if t == "integer":
                v = int(raw)
            elif t == "real":
                v = float(raw)
            else:
                v = str(raw)
        except (ValueError, TypeError):
            return None, f"param {name} expected {t}"

        if "min" in spec and v < spec["min"]:
            return None, f"param {name} must be >= {spec['min']}"
        values.append(v)
    return values, None


def _resolve_body(body_tmpl, rows):
    if isinstance(body_tmpl, str):
        if body_tmpl == "{rows}":
            return rows
        if body_tmpl == "{rows[0]}":
            return rows[0] if rows else {}
        return body_tmpl
    if isinstance(body_tmpl, dict):
        return {k: _resolve_body(v, rows) for k, v in body_tmpl.items()}
    if isinstance(body_tmpl, list):
        return [_resolve_body(v, rows) for v in body_tmpl]
    return body_tmpl


def _substitute(obj, params):
    """Legacy mock-mode placeholder substitution."""
    if isinstance(obj, str) and obj.startswith("{") and obj.endswith("}"):
        return params.get(obj[1:-1], obj)
    if isinstance(obj, dict):
        return {k: _substitute(v, params) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute(v, params) for v in obj]
    return obj

def _cleanup(run_dir):
    import time, shutil
    for attempt in range(3):
        try:
            shutil.rmtree(run_dir)
            return
        except Exception:
            time.sleep(0.2)
    print(f"[sandbox] warning: leaked {run_dir}")


class Sandbox:
    def __init__(self, config):
        self.config = config

    @classmethod
    def from_file(cls, path):
        with open(path) as f:
            config = yaml.safe_load(f)
        try:
            validate(config)
        except ConfigError as e:
            raise ConfigError(f"{path}: {e}") from None
        return cls(config)

    @contextlib.contextmanager
    def run(self):
        run_dir = tempfile.mkdtemp(prefix="sandbox-")
        servers = []
        env = {}
        try:
            # ── databases ────────────────────────────────────────
            for name, dbcfg in (self.config.get("databases") or {}).items():
                db_path = os.path.join(run_dir, f"{name}.db")
                conn = sqlite3.connect(db_path)
                conn.execute("PRAGMA foreign_keys = ON")
                try:
                    for tbl, t in dbcfg["tables"].items():
                        conn.execute(_build_create_table(tbl, t))
                        for row in t.get("seed", []):
                            placeholders = ", ".join("?" * len(row))
                            conn.execute(f"INSERT INTO {tbl} VALUES ({placeholders})", list(row.values()))
                    conn.commit()
                
                finally:
                    conn.close()

                # NOTE: SB_DB_* is intentionally NOT exported. The agent sees only APIs.

            # ── apis ─────────────────────────────────────────────
            for name, apicfg in (self.config.get("apis") or {}).items():
                port = _free_port()
                if apicfg.get("type") == "sql":
                    db_path = os.path.join(run_dir, f"{apicfg['database']}.db")
                    app = self._build_sql_app(apicfg, db_path)
                else:
                    app = self._build_mock_app(apicfg)
                server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
                th = threading.Thread(target=server.run, daemon=True); th.start()
                while not server.started: time.sleep(0.02)
                servers.append(server)
                env[f"SB_API_{name.upper()}"] = f"http://127.0.0.1:{port}"

            os.environ.update(env)
            yield env
        finally:
            for s in servers:
                s.should_exit = True
            time.sleep(0.1)
            try:
                shutil.rmtree(run_dir)
            except Exception as e:
                print(f"[sandbox] warning: could not remove {run_dir}: {e}")


    # ── SQL-backed APIs ──────────────────────────────────────────
    def _build_sql_app(self, apicfg, db_path):
        app = FastAPI()
        for ep in apicfg["endpoints"]:
            path = ep["path"]
            method = ep["method"].upper()

            async def handler(request: Request, _ep=ep, _db=db_path):
                raw = await request.body()
                if raw:
                    try:
                        request._body = await request.json()
                    except Exception:
                        return JSONResponse({"error": "invalid_json"}, status_code=400)
                else:
                    request._body = {}

                values, err = _check_params(_ep, request)
                if err:
                    spec = _ep.get("on_invalid", {"status": 400, "body": {"error": "invalid_input"}})
                    body = _resolve_body(spec["body"], [])
                    if isinstance(body, dict) and "detail" not in body:
                        body = {**body, "detail": err}
                    return JSONResponse(body, status_code=spec["status"])

                try:
                    rows, affected = _run_sql(_db, _ep["sql"], values)
                except Exception as e:
                    return JSONResponse({"error": "internal_error", "detail": str(e)}, status_code=500)

                sql_upper = _ep["sql"].strip().upper()
                is_returning = "RETURNING" in sql_upper or sql_upper.startswith("SELECT")

                if is_returning:
                    key = "on_success"
                elif affected == 0:
                    key = "on_not_found" if "on_not_found" in _ep else "on_conflict"
                else:
                    key = "on_success"

                spec = _ep.get(key) or _ep["on_success"]
                body = _resolve_body(spec["body"], rows)
                return JSONResponse(body, status_code=spec["status"])

            app.add_api_route(path, handler, methods=[method])
        return app

    # ── legacy mock APIs (unchanged behavior) ────────────────────
    def _build_mock_app(self, apicfg):
        app = FastAPI()
        for ep in apicfg["endpoints"]:
            path = ep["path"]
            method = ep["method"].upper()

            async def handler(request: Request, _ep=ep):
                body = await request.json() if await request.body() else {}
                params = {**request.path_params, **body}
                out = _substitute(_ep["response"]["body"], params)
                return JSONResponse(out, status_code=_ep["response"]["status"])

            app.add_api_route(path, handler, methods=[method])
        return app