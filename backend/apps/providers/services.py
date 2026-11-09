"""Provider configuration services; secrets never leave these services."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.projects.models import Project
from apps.providers.models import ModelConfig, ProviderConfig, ProviderSecret
from apps.workspaces.models import Membership
from apps.workspaces.permissions import require_membership
from common.audit.services import record_event
from common.encryption import decrypt_secret, encrypt_secret
from common.encryption.service import SecretCryptoError
from common.exceptions import ServiceUnavailable
from integrations.providers.adapters import OllamaAdapter, ZaiAdapter
from integrations.providers.http import ProviderRequestError


def _project_for_user(user, project_id, minimum_role=Membership.Role.VIEWER):
    project = (
        Project.objects.select_related("workspace")
        .filter(pk=project_id)
        .first()
    )
    if project is None:
        raise NotFound("Project not found.")
    require_membership(user, project.workspace_id, minimum_role)
    return project


def _provider_for_user(user, provider_id, minimum_role=Membership.Role.VIEWER):
    provider = (
        ProviderConfig.objects.select_related("project", "project__workspace")
        .filter(pk=provider_id)
        .first()
    )
    if provider is None:
        raise NotFound("Provider not found.")
    require_membership(user, provider.project.workspace_id, minimum_role)
    return provider


def list_providers(*, user, project_id):
    project = _project_for_user(user, project_id)
    return ProviderConfig.objects.filter(project=project).prefetch_related("secret", "models")


def get_provider(*, user, provider_id):
    provider = _provider_for_user(user, provider_id)
    return ProviderConfig.objects.prefetch_related("secret", "models").get(pk=provider.pk)


def _audit(*, actor, provider, action, metadata=None):
    record_event(
        actor=actor,
        action=action,
        workspace=provider.project.workspace,
        target_type="provider_config",
        target_id=provider.pk,
        metadata={"project_id": str(provider.project_id), "kind": provider.kind, **(metadata or {})},
    )


def _store_secret(provider, key):
    if key is None:
        return
    try:
        encrypted = encrypt_secret(key)
    except SecretCryptoError as exc:
        raise ServiceUnavailable(
            "Provider credential storage is not configured on this server."
        ) from exc
    ProviderSecret.objects.update_or_create(
        provider=provider,
        defaults={"encrypted_value": encrypted},
    )


@transaction.atomic
def create_provider(*, actor, project_id, validated_data):
    project = _project_for_user(actor, project_id, Membership.Role.ADMIN)
    data = dict(validated_data)
    api_key = data.pop("api_key", None)
    provider = ProviderConfig.objects.create(project=project, **data)
    _store_secret(provider, api_key)
    _audit(actor=actor, provider=provider, action="provider.created")
    return provider


@transaction.atomic
def update_provider(*, actor, provider_id, validated_data):
    provider = _provider_for_user(actor, provider_id, Membership.Role.ADMIN)
    data = dict(validated_data)
    api_key = data.pop("api_key", None)
    changed = []
    for field in ("name", "endpoint", "settings"):
        if field in data and getattr(provider, field) != data[field]:
            setattr(provider, field, data[field])
            changed.append(field)
    if changed:
        provider.save(update_fields=[*changed, "updated_at"])
    if api_key is not None:
        _store_secret(provider, api_key)
        changed.append("credential")
    if changed:
        _audit(actor=actor, provider=provider, action="provider.updated", metadata={"fields": changed})
    return provider


@transaction.atomic
def delete_provider(*, actor, provider_id):
    provider = _provider_for_user(actor, provider_id, Membership.Role.ADMIN)
    _audit(actor=actor, provider=provider, action="provider.deleted", metadata={"name": provider.name})
    provider.delete()


def adapter_for(provider):
    if provider.kind == ProviderConfig.Kind.ZAI:
        try:
            secret = provider.secret
        except ProviderSecret.DoesNotExist:
            raise ValidationError({"api_key": "No API key is stored for this provider."}) from None
        try:
            api_key = decrypt_secret(secret.encrypted_value)
        except SecretCryptoError as exc:
            raise ServiceUnavailable(
                "The stored provider credential cannot be decrypted with the configured keys."
            ) from exc
        return ZaiAdapter(api_key)
    if provider.kind == ProviderConfig.Kind.OLLAMA:
        return OllamaAdapter(provider.endpoint)
    raise ValidationError({"kind": "Unsupported provider type."})


def clean_provider_error(exc: Exception) -> dict[str, str]:
    """Describe a provider failure without echoing secrets or raw payloads."""
    if isinstance(exc, ValidationError):
        detail = exc.detail
        if isinstance(detail, dict):
            message = "; ".join(
                f"{key}: {value[0] if isinstance(value, list) and value else value}"
                for key, value in detail.items()
            )
        else:
            message = str(detail)
        return {"category": "invalid_provider", "message": message[:400]}
    if isinstance(exc, ServiceUnavailable):
        return {"category": "service_unavailable", "message": str(exc.detail)[:400]}
    if isinstance(exc, ValueError):
        return {"category": "invalid_request", "message": str(exc)[:400]}
    return {
        "category": "provider_error",
        "message": "The provider call failed unexpectedly.",
    }


def generate_once(*, provider, model_id, messages, parameters):
    """Run one non-streaming generation through the M3 adapter.

    Returns ``(result, error)`` where exactly one is ``None``. Shared by the
    evaluation runner so it never bypasses the provider integration layer.
    """
    from integrations.providers.base import GenerationRequest

    try:
        adapter = adapter_for(provider)
    except (ValidationError, ServiceUnavailable, ValueError) as exc:
        return None, clean_provider_error(exc)
    try:
        result = adapter.generate(
            GenerationRequest(model_id=model_id, messages=messages, parameters=parameters)
        )
    except Exception:  # noqa: BLE001 - never leak provider SDK/transport details
        return None, {
            "category": "provider_error",
            "message": "The provider call failed unexpectedly.",
        }
    if result.error:
        return None, {
            "category": str(result.error.get("category", "provider_error"))[:80],
            "message": str(result.error.get("message", "Provider call failed."))[:400],
        }
    return result, None


@transaction.atomic
def test_provider(*, actor, provider_id):
    provider = _provider_for_user(actor, provider_id, Membership.Role.ADMIN)
    try:
        result = adapter_for(provider).validate_connection()
        status = "connected" if result.ok else "error"
        detail = result.detail or ("Connection successful." if result.ok else "Connection failed.")
    except (ValidationError, ValueError) as exc:
        status = "error"
        detail = str(exc.detail if isinstance(exc, ValidationError) else exc)
    except ProviderRequestError as exc:
        status, detail = "error", str(exc)
    except Exception:
        # Never return provider SDK or transport exceptions that may contain URL
        # credentials, response bodies, or authorization headers.
        status, detail = "error", "Provider connection could not be verified."

    provider.connection_status = status
    provider.connection_detail = detail[:240]
    provider.last_tested_at = timezone.now()
    provider.save(update_fields=["connection_status", "connection_detail", "last_tested_at", "updated_at"])
    _audit(actor=actor, provider=provider, action="provider.connection_tested", metadata={"status": status})
    return {"ok": status == "connected", "status": status, "detail": detail}


@transaction.atomic
def list_provider_models(*, actor, provider_id):
    provider = _provider_for_user(actor, provider_id, Membership.Role.ADMIN)
    adapter = adapter_for(provider)
    try:
        models = adapter.list_models()
    except ProviderRequestError as exc:
        raise ValidationError({"provider": str(exc)}) from None
    except ValueError as exc:
        raise ValidationError({"provider": str(exc)}) from None
    except Exception:
        # Third-party or socket exceptions may contain URLs, credentials or bodies.
        raise ValidationError({"provider": "Provider models could not be retrieved."}) from None

    saved = []
    for item in models:
        row, _ = ModelConfig.objects.update_or_create(
            provider=provider,
            model_id=item.model_id,
            defaults={"display_name": item.display_name or "", "defaults": item.metadata},
        )
        saved.append(row)
    _audit(actor=actor, provider=provider, action="provider.models_listed", metadata={"count": len(saved)})
    return saved
