"""Locked persistence for tenant-scoped BYO LLM credentials."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from filelock import FileLock

from backend.llm_config import runtime_config
from backend.llm_registry import PROVIDERS


_SALT = "zecure_llm_salt_v1"
@dataclass(frozen=True)
class StoredCredential:
    tenant_id: str
    provider: str
    credential_id: str
    version: int
    api_key: str
    model: str
    enabled: bool

    @property
    def key_reference(self) -> str:
        return f"byo:{self.tenant_id}:{self.provider}:{self.credential_id}:v{self.version}"


def _simple_encrypt(text: str) -> str:
    key = hashlib.sha256(_SALT.encode()).digest()
    data = text.encode()
    encrypted = bytes([data[index] ^ key[index % len(key)] for index in range(len(data))])
    return base64.b64encode(encrypted).decode()


def _simple_decrypt(token: str) -> str:
    key = hashlib.sha256(_SALT.encode()).digest()
    data = base64.b64decode(token.encode())
    return bytes([data[index] ^ key[index % len(key)] for index in range(len(data))]).decode()


def _store_path() -> Path:
    return runtime_config.snapshot().key_store_path


def _lock_path(path: Path) -> str:
    return str(path.with_suffix(path.suffix + ".lock"))


def _empty_store() -> dict:
    return {"schema_version": 2, "tenants": {}, "legacy_unassigned": {}}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _upgrade_entry(provider: str, entry: dict) -> tuple[dict, bool]:
    upgraded = dict(entry)
    changed = False
    if not upgraded.get("credential_id"):
        upgraded["credential_id"] = uuid.uuid4().hex
        changed = True
    if not isinstance(upgraded.get("version"), int):
        upgraded["version"] = 1
        changed = True
    if not upgraded.get("model"):
        upgraded["model"] = PROVIDERS[provider].default_model
        changed = True
    if "enabled" not in upgraded:
        upgraded["enabled"] = True
        changed = True
    if not upgraded.get("provider"):
        upgraded["provider"] = provider
        changed = True
    if not upgraded.get("updated_at"):
        upgraded["updated_at"] = _utc_now()
        changed = True
    return upgraded, changed


def _normalize_store(raw: object) -> tuple[dict, bool]:
    if not isinstance(raw, dict):
        return _empty_store(), True
    if raw.get("schema_version") == 2:
        store = _empty_store()
        store["tenants"] = raw.get("tenants", {}) if isinstance(raw.get("tenants"), dict) else {}
        store["legacy_unassigned"] = raw.get("legacy_unassigned", {}) if isinstance(raw.get("legacy_unassigned"), dict) else {}
        changed = False
        for bucket in (store["tenants"], store["legacy_unassigned"]):
            for tenant_id, entries in list(bucket.items()):
                if not isinstance(entries, dict):
                    bucket[tenant_id] = {}
                    changed = True
                    continue
                for provider, entry in list(entries.items()):
                    if provider not in PROVIDERS or not isinstance(entry, dict):
                        entries.pop(provider, None)
                        changed = True
                        continue
                    entries[provider], entry_changed = _upgrade_entry(provider, entry)
                    changed = changed or entry_changed
        return store, changed

    store = _empty_store()
    changed = True
    for tenant_id, entries in raw.items():
        if not isinstance(entries, dict):
            continue
        destination = store["legacy_unassigned"] if tenant_id == "default" else store["tenants"]
        destination[tenant_id] = {}
        for provider, entry in entries.items():
            if provider not in PROVIDERS or not isinstance(entry, dict):
                continue
            destination[tenant_id][provider], _ = _upgrade_entry(provider, entry)
    return store, changed


def _read_store_unlocked(path: Path) -> tuple[dict, bool]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return _empty_store(), False
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM key store is invalid JSON: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"Unable to read LLM key store: {path}") from exc
    return _normalize_store(raw)


def _write_store_unlocked(path: Path, store: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    try:
        with handle:
            json.dump(store, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        Path(handle.name).replace(path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def _load_store() -> dict:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(_lock_path(path), timeout=10):
        store, changed = _read_store_unlocked(path)
        if changed:
            _write_store_unlocked(path, store)
        return store


def _mutate_store(mutator) -> object:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(_lock_path(path), timeout=10):
        store, _ = _read_store_unlocked(path)
        result = mutator(store)
        _write_store_unlocked(path, store)
        return result


def _normalize_tenant_id(customer_id: Optional[str]) -> str:
    return (customer_id or "").strip() or "default"


def _masked_preview(entry: dict) -> str:
    try:
        key = _simple_decrypt(entry["encrypted_key"])
    except Exception:
        return "****"
    return key[:6] + "..." + key[-4:] if len(key) > 10 else "****"


def save_key(provider: str, api_key: str, model: str = "", customer_id: str = "default") -> dict:
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        return {"success": False, "error": f"Unknown provider: {provider}"}
    api_key = (api_key or "").strip()
    if provider == "ollama" and not api_key:
        api_key = PROVIDERS[provider].endpoint
    if not api_key:
        return {"success": False, "error": "API key cannot be empty"}
    model = (model or "").strip() or PROVIDERS[provider].default_model
    tenant_id = _normalize_tenant_id(customer_id)

    def save(store: dict) -> dict:
        entries = store["tenants"].setdefault(tenant_id, {})
        previous = entries.get(provider, {})
        entries[provider] = {
            "credential_id": previous.get("credential_id", uuid.uuid4().hex),
            "version": int(previous.get("version", 0)) + 1,
            "encrypted_key": _simple_encrypt(api_key),
            "model": model,
            "provider": provider,
            "enabled": True,
            "updated_at": _utc_now(),
        }
        return {"success": True, "provider": provider, "model": model, "tenant_id": tenant_id}

    return _mutate_store(save)


def get_active_credentials(customer_id: str) -> list[StoredCredential]:
    tenant_id = _normalize_tenant_id(customer_id)
    if tenant_id == "default":
        return []
    store = _load_store()
    credentials: list[StoredCredential] = []
    for provider, entry in store["tenants"].get(tenant_id, {}).items():
        if provider not in PROVIDERS or not entry.get("enabled"):
            continue
        try:
            secret = _simple_decrypt(entry["encrypted_key"])
        except Exception:
            continue
        credentials.append(StoredCredential(
            tenant_id=tenant_id,
            provider=provider,
            credential_id=entry["credential_id"],
            version=entry["version"],
            api_key=secret,
            model=entry.get("model") or PROVIDERS[provider].default_model,
            enabled=True,
        ))
    return credentials


def get_all_keys(customer_id: str = "default") -> dict:
    tenant_id = _normalize_tenant_id(customer_id)
    store = _load_store()
    result = {}
    for provider, entry in store["tenants"].get(tenant_id, {}).items():
        if provider not in PROVIDERS:
            continue
        result[provider] = {
            "provider": provider,
            "provider_name": PROVIDERS[provider].display_name,
            "model": entry.get("model") or PROVIDERS[provider].default_model,
            "enabled": bool(entry.get("enabled")),
            "key_preview": _masked_preview(entry),
        }
    return result


def delete_key(provider: str, customer_id: str = "default") -> dict:
    tenant_id = _normalize_tenant_id(customer_id)

    def delete(store: dict) -> dict:
        entries = store["tenants"].get(tenant_id, {})
        if provider not in entries:
            return {"success": False, "error": "Key not found"}
        del entries[provider]
        if not entries:
            store["tenants"].pop(tenant_id, None)
        return {"success": True}

    return _mutate_store(delete)


def toggle_key(provider: str, enabled: bool, customer_id: str = "default") -> dict:
    tenant_id = _normalize_tenant_id(customer_id)

    def toggle(store: dict) -> dict:
        entry = store["tenants"].get(tenant_id, {}).get(provider)
        if not entry:
            return {"success": False, "error": "Key not found"}
        entry["enabled"] = bool(enabled)
        entry["version"] = int(entry.get("version", 0)) + 1
        entry["updated_at"] = _utc_now()
        return {"success": True}

    return _mutate_store(toggle)


def key_store_status() -> dict:
    store = _load_store()
    return {
        "legacy_default_keys_quarantined": len(store["legacy_unassigned"].get("default", {})),
        "tenant_count": len(store["tenants"]),
    }
