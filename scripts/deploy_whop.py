"""Deploy the owner Whop broker using an already authorized FREE Cloudflare account.

No SDK, browser login, secret output, subscription mutation, token export, or paid
resource is used. API bindings may be proxy-backed; pass them only to their
configured HTTPS destination. Existing encrypted state and secret bindings are
preserved. Run --preflight first; --apply initializes resources, while
--update-code updates an existing deployment without schema or settings writes.

API contracts: https://github.com/cloudflare/api-schemas/blob/main/openapi.yaml
and https://github.com/cloudflare/cloudflare-python/tree/main/src/cloudflare.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import secrets
import sys
from pathlib import Path

import httpx

API = "https://api.cloudflare.com/client/v4"
WORKER_NAME = "content-rewards-whop"
DATABASE_NAME = "content-rewards-whop-private"
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".data/whop-deployment.json"
ACCOUNT = re.compile(r"[a-fA-F0-9]{32}")
DATABASE = re.compile(r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}")
SUBDOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


class DeploymentBlocked(Exception):
    """Only fixed, nonsensitive messages are exposed to the operator."""


def _free_subscriptions(items: object) -> None:
    """Absence of account subscriptions establishes Workers' default free plan.

    Do not infer free entitlement from price=0 alone: metered or trial products
    can have a zero base price. Unknown active plans require owner clarification.
    """
    if not isinstance(items, list):
        raise DeploymentBlocked("Cloudflare free-plan evidence was malformed; no resources changed")
    for item in items:
        if not isinstance(item, dict):
            raise DeploymentBlocked("Cloudflare free-plan evidence was malformed; no resources changed")
        if item.get("state") in ("Cancelled", "Expired", "Failed"):
            continue
        plan, price = item.get("rate_plan"), item.get("price")
        if (item.get("state") not in ("Provisioned", "Paid") or not isinstance(plan, dict)
                or plan.get("id") not in ("free", "partners_free")
                or isinstance(price, bool) or not isinstance(price, (float, int))
                or not math.isfinite(price) or price != 0 or plan.get("is_contract") not in (None, False)):
            raise DeploymentBlocked("An active paid, trial, or unknown Cloudflare account plan prevents automatic free deployment")


class Cloudflare:
    def __init__(self, token: str, client: httpx.Client):
        if not token or any(character.isspace() for character in token):
            raise DeploymentBlocked("Configure CLOUDFLARE_API_TOKEN only in secure environment settings")
        self._token, self.client = token, client

    def call(self, method: str, path: str, **kwargs) -> tuple[object, dict]:
        try:
            response = self.client.request(
                method, API + path, headers={"Authorization": "Bearer " + self._token},
                follow_redirects=False, timeout=30, **kwargs,
            )
        except httpx.HTTPError:
            raise DeploymentBlocked("Cloudflare HTTPS request failed; check configured access before retrying") from None
        if response.status_code in {401, 403}:
            raise DeploymentBlocked("Cloudflare authorization requires account-scoped Workers Scripts Edit, D1 Edit, Account Settings Read and Billing Read")
        if not 200 <= response.status_code < 300:
            raise DeploymentBlocked(f"Cloudflare returned HTTP {response.status_code}; no upstream body was logged")
        try:
            if len(response.content) > 2_000_000:
                raise ValueError
            data = response.json()
            if not isinstance(data, dict) or data.get("success") is not True or "result" not in data:
                raise ValueError
        except (ValueError, UnicodeError):
            raise DeploymentBlocked("Cloudflare returned an invalid API result; inspect the account dashboard") from None
        info = data.get("result_info", {})
        if not isinstance(info, dict):
            raise DeploymentBlocked("Cloudflare returned invalid pagination evidence")
        return data["result"], info

    def list_all(self, path: str) -> list[dict]:
        result = []
        for page in range(1, 21):
            items, info = self.call("GET", path, params={"page": page, "per_page": 100})
            if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                raise DeploymentBlocked("Cloudflare returned invalid resource-list evidence")
            result.extend(items)
            total = info.get("total_pages")
            if total is not None:
                if type(total) is not int or total < 0:
                    raise DeploymentBlocked("Cloudflare resource pagination was invalid")
                if page >= total:
                    return result
            elif len(items) < 100:
                return result
        raise DeploymentBlocked("Cloudflare resource listing exceeded its safe bound; no resource selection assumed")


def _state(path: Path, account_id: str, origin: str) -> dict | None:
    if not path.exists():
        return None
    try:
        item = json.loads(path.read_text())
        if (not isinstance(item, dict) or item.get("account_id") != account_id
                or item.get("worker_name") != WORKER_NAME or item.get("origin") != origin
                or not isinstance(item.get("database_id"), str)
                or not DATABASE.fullmatch(item["database_id"])
                or item.get("phase") not in {"database_ready", "uploaded", "deployed"}):
            raise ValueError
    except (ValueError, OSError, TypeError):
        raise DeploymentBlocked("Local deployment metadata does not match this account; inspect it before changing resources") from None
    return item


def _save_state(path: Path, state: dict) -> None:
    # This whitelist intentionally cannot contain a token, password or key.
    output = {key: state[key] for key in ("account_id", "worker_name", "origin", "database_id", "phase")}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(output, indent=2) + "\n")
    temporary.replace(path)


def deploy(env: dict, *, apply: bool, client: httpx.Client, state_path: Path = STATE,
           source_root: Path = ROOT) -> dict:
    cf = Cloudflare(env.get("CLOUDFLARE_API_TOKEN", ""), client)
    account_id = env.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not account_id:
        accounts = cf.list_all("/accounts")
        if len(accounts) != 1:
            raise DeploymentBlocked("Select the existing free account using nonsecret CLOUDFLARE_ACCOUNT_ID in environment settings")
        account_id = accounts[0].get("id", "")
    if not isinstance(account_id, str) or not ACCOUNT.fullmatch(account_id):
        raise DeploymentBlocked("CLOUDFLARE_ACCOUNT_ID must identify the existing Cloudflare account")
    base = "/accounts/" + account_id
    subscriptions, _ = cf.call("GET", base + "/subscriptions")
    _free_subscriptions(subscriptions)
    subdomain, _ = cf.call("GET", base + "/workers/subdomain")
    namespace = subdomain.get("subdomain") if isinstance(subdomain, dict) else None
    if not isinstance(namespace, str) or not SUBDOMAIN.fullmatch(namespace):
        raise DeploymentBlocked("Choose your workers.dev subdomain in the existing free Cloudflare Workers dashboard, then retry")
    origin = f"https://{WORKER_NAME}.{namespace}.workers.dev"
    existing_state = _state(state_path, account_id, origin)
    workers = cf.list_all(base + "/workers/scripts")
    existing_worker = [item for item in workers if item.get("id") == WORKER_NAME]
    if len(existing_worker) > 1 or (existing_worker and not existing_state):
        raise DeploymentBlocked("An existing same-name Worker lacks matching local deployment evidence; it was not overwritten")
    if existing_state and not existing_worker and existing_state["phase"] in {"uploaded", "deployed"}:
        raise DeploymentBlocked("The existing Whop Worker is missing; restore its encryption secret instead of replacing it")
    databases = cf.list_all(base + "/d1/database")
    matching = [item for item in databases if item.get("name") == DATABASE_NAME]
    if len(matching) > 1:
        raise DeploymentBlocked("Duplicate Whop databases require inspection; no database was selected")
    if matching and not existing_state:
        raise DeploymentBlocked("An existing same-name private database lacks deployment evidence; its encryption keys were not replaced")
    database_id = matching[0].get("uuid") if matching else None
    if existing_state and existing_state["database_id"] != database_id:
        raise DeploymentBlocked("The saved private database is missing or changed; no empty replacement was created")
    if database_id is not None and (not isinstance(database_id, str) or not DATABASE.fullmatch(database_id)):
        raise DeploymentBlocked("Cloudflare returned an invalid private database identifier")
    secret_names, old_client_id = set(), ""
    if existing_worker:
        settings, _ = cf.call("GET", base + f"/workers/scripts/{WORKER_NAME}/settings")
        bindings = settings.get("bindings") if isinstance(settings, dict) else None
        if not isinstance(bindings, list):
            raise DeploymentBlocked("Existing Worker bindings could not be verified; encryption keys were not changed")
        names = []
        database_bindings = []
        for binding in bindings:
            if not isinstance(binding, dict) or not isinstance(binding.get("name"), str):
                raise DeploymentBlocked("Existing Worker bindings were malformed")
            names.append(binding.get("name"))
            if binding.get("type") == "secret_text":
                secret_names.add(binding.get("name"))
            if binding.get("name") == "WHOP_CLIENT_ID" and binding.get("type") == "plain_text":
                old_client_id = binding.get("text", "")
            if binding.get("name") == "DB":
                database_bindings.append(binding)
        if (any(not isinstance(name, str) for name in names) or len(names) != len(set(names))
                or len(database_bindings) != 1 or database_bindings[0].get("type") != "d1"
                or database_bindings[0].get("id") != database_id):
            raise DeploymentBlocked("Existing Worker database binding changed; no update was uploaded")
        if not {"TOKEN_ENCRYPTION_KEY", "WHOP_BROKER_API_TOKEN"} <= secret_names:
            raise DeploymentBlocked("Existing Worker encryption secret is missing; restore it securely before updating")
    result = {"status": "preflight_passed", "free_account_verified": True, "origin": origin,
              "callback": origin + "/oauth/callback", "live_publishing": False,
              "resources_changed": False, "authorization_complete": False}
    if not apply:
        return result
    worker_file = source_root / "cloud/whop/src/worker.mjs"
    schema_file = source_root / "cloud/whop/migrations/0001_owner_oauth.sql"
    try:
        worker_source, schema = worker_file.read_bytes(), schema_file.read_text()
    except OSError:
        raise DeploymentBlocked("The committed Whop Worker source and migration are required before deploying") from None
    client_id = env.get("WHOP_CLIENT_ID", "") or old_client_id
    if not isinstance(client_id, str) or (client_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", client_id)):
        raise DeploymentBlocked("WHOP_CLIENT_ID must be the nonsecret registered app identifier")
    if database_id is None:
        database, _ = cf.call("POST", base + "/d1/database", json={"name": DATABASE_NAME})
        database_id = database.get("uuid") if isinstance(database, dict) else None
        if not isinstance(database_id, str) or not DATABASE.fullmatch(database_id):
            raise DeploymentBlocked("D1 creation returned no valid identifier; inspect Cloudflare before retrying")
    state = {"account_id": account_id, "worker_name": WORKER_NAME, "origin": origin,
             "database_id": database_id, "phase": "database_ready"}
    _save_state(state_path, state)
    migration, _ = cf.call("POST", base + f"/d1/database/{database_id}/query", json={"sql": schema})
    if not isinstance(migration, list) or not migration or any(not isinstance(q, dict) or q.get("success") is not True for q in migration):
        raise DeploymentBlocked("D1 schema application failed; existing private records were not reset")
    if not existing_worker:
        # A lost Worker must never cause a new key to replace the key required
        # by persistent ciphertext. This also covers an interrupted initial
        # upload whose success was not acknowledged to this process.
        usage, _ = cf.call("POST", base + f"/d1/database/{database_id}/query", json={"sql":
            "SELECT (SELECT COUNT(*) FROM whop_credentials WHERE encrypted_payload IS NOT NULL OR status!='empty') "
            "+(SELECT COUNT(*) FROM oauth_sessions)+(SELECT COUNT(*) FROM oauth_states)"
            "+(SELECT COUNT(*) FROM whop_observations) AS private_rows"})
        try:
            count = usage[0]["results"][0]["private_rows"]
            if type(count) is not int or count != 0 or len(usage) != 1 or usage[0].get("success") is not True:
                raise ValueError
        except (IndexError, KeyError, TypeError, ValueError):
            raise DeploymentBlocked("Private database state exists or could not be verified; restore its encryption secret rather than replacing it") from None
    bindings = [
        {"type": "d1", "name": "DB", "id": database_id},
        {"type": "plain_text", "name": "PUBLIC_ORIGIN", "text": origin},
        {"type": "plain_text", "name": "WHOP_CLIENT_ID", "text": client_id},
        {"type": "plain_text", "name": "REWARDS_LIVE_PUBLISHING", "text": "false"},
    ]
    if not existing_worker:
        # Generated secrets live only in this request and the provider secret
        # store. The owner supplies a login password in the provider dashboard.
        bindings += [
            {"type": "secret_text", "name": "TOKEN_ENCRYPTION_KEY",
             "text": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")},
            {"type": "secret_text", "name": "WHOP_BROKER_API_TOKEN", "text": secrets.token_urlsafe(32)},
        ]
    metadata = {"main_module": "worker.mjs", "compatibility_date": "2026-10-28", "bindings": bindings,
                "keep_bindings": ["secret_text"], "logpush": False, "observability": {"enabled": False}}
    cf.call("PUT", base + f"/workers/scripts/{WORKER_NAME}", files={
        "metadata": (None, json.dumps(metadata), "application/json"),
        "worker.mjs": ("worker.mjs", worker_source, "application/javascript+module"),
    })
    state["phase"] = "uploaded"
    _save_state(state_path, state)
    cf.call("POST", base + f"/workers/scripts/{WORKER_NAME}/subdomain",
            json={"enabled": True, "previews_enabled": False})
    cf.call("PUT", base + f"/workers/scripts/{WORKER_NAME}/schedules", json=[{"cron": "*/30 * * * *"}])
    actual_settings, _ = cf.call("GET", base + f"/workers/scripts/{WORKER_NAME}/settings")
    actual_subdomain, _ = cf.call("GET", base + f"/workers/scripts/{WORKER_NAME}/subdomain")
    actual_schedules, _ = cf.call("GET", base + f"/workers/scripts/{WORKER_NAME}/schedules")
    try:
        actual_bindings = actual_settings["bindings"]
        if not isinstance(actual_bindings, list) or any(not isinstance(binding, dict) for binding in actual_bindings):
            raise ValueError
        actual_names = [binding.get("name") for binding in actual_bindings]
        if any(not isinstance(name, str) for name in actual_names) or len(actual_names) != len(set(actual_names)):
            raise ValueError
        by_name = {binding["name"]: binding for binding in actual_bindings}
        if (by_name["DB"].get("type") != "d1" or by_name["DB"].get("id") != database_id
                or any(by_name[name].get("type") != "secret_text" for name in ("TOKEN_ENCRYPTION_KEY", "WHOP_BROKER_API_TOKEN"))
                or by_name["PUBLIC_ORIGIN"].get("text") != origin
                or by_name["WHOP_CLIENT_ID"].get("text") != client_id
                or by_name["REWARDS_LIVE_PUBLISHING"].get("text") != "false"
                or actual_subdomain.get("enabled") is not True
                or actual_subdomain.get("previews_enabled") is not False
                or not isinstance(actual_schedules.get("schedules"), list)
                or [item.get("cron") for item in actual_schedules["schedules"]] != ["*/30 * * * *"]):
            raise ValueError
        owner_password_configured = by_name.get("OWNER_PASSWORD", {}).get("type") == "secret_text"
    except (IndexError, KeyError, AttributeError, TypeError, ValueError):
        raise DeploymentBlocked("Cloudflare did not confirm the uploaded private bindings, callback route and renewal schedule; inspect the deployment before authorization") from None
    state["phase"] = "deployed"
    _save_state(state_path, state)
    return result | {"status": "deployed_requires_owner_configuration", "resources_changed": True,
                     "client_id_configured": bool(client_id), "owner_password_configured": owner_password_configured,
                     "renewal_schedule_installed": True, "scheduled_execution_verified": False,
                     "next_action": "Set OWNER_PASSWORD securely in the Cloudflare Worker dashboard, register the exact callback in Whop, and configure its nonsecret WHOP_CLIENT_ID"}


def _code_metadata(settings: object) -> tuple[dict, str]:
    """Copy supported runtime settings; fingerprint values without exposing them."""
    if not isinstance(settings, dict) or not isinstance(settings.get("bindings"), list):
        raise DeploymentBlocked("Existing Worker settings were malformed; no code update was verified")
    bindings, names, secret_names = [], set(), []
    for binding in settings["bindings"]:
        if (not isinstance(binding, dict) or not isinstance(binding.get("name"), str)
                or not binding["name"] or binding["name"] in names):
            raise DeploymentBlocked("Existing Worker bindings were malformed; no code update was verified")
        names.add(binding["name"])
        kind = binding.get("type")
        if kind == "secret_text":
            # GET may return secret metadata. Never resend a secret value.
            secret_names.append(binding["name"])
            continue
        if kind == "plain_text" and isinstance(binding.get("text"), str):
            bindings.append(dict(binding))
        elif kind == "d1" and isinstance(binding.get("id"), str) and DATABASE.fullmatch(binding["id"]):
            bindings.append(dict(binding))
        else:
            raise DeploymentBlocked("An unsupported existing Worker binding prevents a code-only update")
    by_name = {binding["name"]: binding for binding in bindings}
    if (by_name.get("REWARDS_LIVE_PUBLISHING", {}).get("type") != "plain_text"
            or by_name["REWARDS_LIVE_PUBLISHING"].get("text") != "false"):
        raise DeploymentBlocked("The existing Worker must keep REWARDS_LIVE_PUBLISHING=false before a code-only update")
    if (not isinstance(settings.get("compatibility_date"), str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", settings["compatibility_date"])
            or ("compatibility_flags" in settings and (not isinstance(settings["compatibility_flags"], list)
                or any(not isinstance(flag, str) for flag in settings["compatibility_flags"])))
            or ("logpush" in settings and type(settings["logpush"]) is not bool)
            or ("observability" in settings and settings["observability"] is not None
                and not isinstance(settings["observability"], dict))):
        raise DeploymentBlocked("Existing Worker runtime settings were malformed; no code update was verified")
    metadata = {key: settings[key] for key in (
        "compatibility_date", "compatibility_flags", "logpush", "observability",
    ) if key in settings}
    metadata.update(main_module="worker.mjs", bindings=bindings, keep_bindings=["secret_text"])
    comparison = metadata | {"bindings": sorted(bindings, key=lambda binding: binding["name"]),
                             "secret_names": sorted(secret_names)}
    fingerprint = hashlib.sha256(json.dumps(comparison, sort_keys=True).encode()).hexdigest()
    return metadata, fingerprint


def update_code(env: dict, *, client: httpx.Client, state_path: Path = STATE,
                source_root: Path = ROOT) -> dict:
    """Upload only source, preserving an existing free deployment and private data."""
    result = deploy(env, apply=False, client=client, state_path=state_path, source_root=source_root)
    try:
        saved = json.loads(state_path.read_text())
        state = _state(state_path, saved["account_id"], result["origin"])
        if state is None or state["phase"] != "deployed" or not ACCOUNT.fullmatch(state["account_id"]):
            raise ValueError
        worker_source = (source_root / "cloud/whop/src/worker.mjs").read_bytes()
    except (OSError, KeyError, TypeError, ValueError):
        raise DeploymentBlocked("A saved completed deployment and committed Worker source are required for --update-code") from None
    cf = Cloudflare(env.get("CLOUDFLARE_API_TOKEN", ""), client)
    path = f"/accounts/{state['account_id']}/workers/scripts/{WORKER_NAME}"
    current, _ = cf.call("GET", path + "/settings")
    metadata, fingerprint = _code_metadata(current)
    schedules, _ = cf.call("GET", path + "/schedules")
    if (not isinstance(schedules, dict) or not isinstance(schedules.get("schedules"), list)
            or any(not isinstance(item, dict) or not isinstance(item.get("cron"), str)
                   for item in schedules["schedules"])):
        raise DeploymentBlocked("Existing Worker schedules could not be verified; no update was uploaded")
    cf.call("PUT", path, files={
        "metadata": (None, json.dumps(metadata), "application/json"),
        "worker.mjs": ("worker.mjs", worker_source, "application/javascript+module"),
    })
    actual, _ = cf.call("GET", path + "/settings")
    actual_schedules, _ = cf.call("GET", path + "/schedules")
    if _code_metadata(actual)[1] != fingerprint or actual_schedules != schedules:
        raise DeploymentBlocked("The uploaded code's settings or schedules did not match; inspect the existing Worker before retrying")
    return result | {"status": "code_updated", "resources_changed": True,
                     "authorization_complete": None, "settings_unchanged_verified": True,
                     "schedules_unchanged_verified": True, "database_mutations_sent": False,
                     "secret_values_sent": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--update-code", action="store_true")
    args = parser.parse_args()
    try:
        with httpx.Client() as client:
            result = (update_code(os.environ, client=client) if args.update_code
                      else deploy(os.environ, apply=args.apply, client=client))
    except (DeploymentBlocked, OSError) as error:
        message = str(error) if isinstance(error, DeploymentBlocked) else "Deployment metadata could not be saved; inspect local filesystem access"
        print(json.dumps({"status": "blocked", "detail": message, "live_publishing": False}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
