from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.observability.models import Trace, TraceRollup, TraceRollupState
from apps.observability.rollups import (
    purge_old_traces,
    rollup_project,
)
from apps.projects.models import Project
from apps.providers.models import ProviderConfig
from apps.workspaces.services import create_workspace
from integrations.providers.http import ProviderRequestError


@pytest.fixture()
def project(user):
    workspace = create_workspace(user=user, name="Rollups")
    return Project.objects.create(workspace=workspace, name="Rollup project", created_by=user)


@pytest.fixture()
def provider(project):
    return ProviderConfig.objects.create(
        project=project,
        name="Local Ollama",
        kind=ProviderConfig.Kind.OLLAMA,
        endpoint="http://localhost:11434",
    )


@pytest.fixture()
def client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture()
def fake_provider(monkeypatch):
    def fake_request(**kwargs):
        payload = kwargs["payload"]
        if payload["model"] == "broken-model":
            raise ProviderRequestError(
                "network_error", "Could not reach the provider endpoint."
            )
        return {
            "message": {"content": "Paris"},
            "prompt_eval_count": 12,
            "eval_count": 8,
            "done_reason": "stop",
        }

    monkeypatch.setattr("integrations.providers.adapters.request_json", fake_request)


def run_playground(client, project, provider, model_id="llama3.2"):
    response = client.post(
        f"/api/v1/projects/{project.id}/executions/",
        {
            "system_prompt": "Be terse.",
            "user_prompt": "Capital of France?",
            "parameters": {"max_tokens": 64},
            "models": [{"provider": str(provider.id), "model_id": model_id}],
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response


def move_trace_to(trace, started_at):
    trace.started_at = started_at
    trace.ended_at = started_at + timedelta(milliseconds=250)
    trace.save(update_fields=["started_at", "ended_at"])


def dashboard(client, project, **params):
    response = client.get(
        f"/api/v1/projects/{project.id}/observability/", params
    )
    assert response.status_code == 200, response.content
    return response.json()


def test_rollups_are_used_for_old_days_without_double_counting(
    client, project, provider, fake_provider
):
    old_day = timezone.now().date() - timedelta(days=5)
    old_response = run_playground(client, project, provider)
    old_trace = Trace.objects.get(execution_result_id=old_response.json()["results"][0]["id"])
    move_trace_to(
        old_trace, timezone.make_aware(datetime.combine(old_day, time.min))
    )

    new_response = run_playground(client, project, provider)
    new_trace = Trace.objects.get(execution_result_id=new_response.json()["results"][0]["id"])

    result = rollup_project(project=project, through_day=old_day)
    assert result["days"] == 1
    assert TraceRollupState.objects.get(project=project).through_day == old_day
    assert TraceRollup.objects.get(project=project, day=old_day).calls == 1

    data = dashboard(client, project)
    assert data["totals"]["calls"] == 2
    assert data["totals"]["succeeded"] == 2
    assert data["totals"]["input_tokens"] == 24
    assert data["rollups"]["through"] == old_day.isoformat()
    assert data["rollups"]["from"] == old_day.isoformat()
    assert data["rollups"]["to"] == old_day.isoformat()

    # Rebuilding must update the bucket, not append a duplicate.
    rollup_project(project=project, through_day=old_day, start_day=old_day)
    assert TraceRollup.objects.filter(project=project, day=old_day).count() == 1
    assert dashboard(client, project)["totals"]["calls"] == 2
    assert Trace.objects.count() == 2
    assert new_trace.pk != old_trace.pk


def test_rollup_filters_costs_and_errors_survive_raw_retention(
    client, project, provider, fake_provider, settings
):
    settings.EXECUTION_PRICING = {
        "ollama:llama3.2": {
            "input_per_million": "1.00",
            "output_per_million": "2.00",
            "currency": "USD",
        }
    }
    old_day = timezone.now().date() - timedelta(days=5)
    success_response = run_playground(client, project, provider)
    success = Trace.objects.get(
        execution_result_id=success_response.json()["results"][0]["id"]
    )
    move_trace_to(
        success,
        timezone.make_aware(
            timezone.datetime.combine(old_day, timezone.datetime.min.time())
        ),
    )

    failed_response = run_playground(client, project, provider, "broken-model")
    failed = Trace.objects.get(
        execution_result_id=failed_response.json()["results"][0]["id"]
    )
    move_trace_to(
        failed,
        timezone.make_aware(datetime.combine(old_day, time.min))
        + timedelta(seconds=1),
    )

    rollup_project(project=project, through_day=old_day)
    result = purge_old_traces(retention_days=1)
    assert result["deleted"] == 2
    assert Trace.objects.count() == 0

    data = dashboard(client, project)
    assert data["totals"]["calls"] == 2
    assert data["totals"]["succeeded"] == 1
    assert data["totals"]["failed"] == 1
    assert data["totals"]["input_tokens"] == 12
    assert data["totals"]["output_tokens"] == 8
    assert data["cost_status"] == "partial"
    assert data["costs"] == [{"currency": "USD", "amount": "0.000028", "calls": 1}]
    assert data["errors"] == [{"category": "network_error", "count": 1}]
    assert data["models"][0]["count"] == 1
    assert {row["model_id"] for row in data["models"]} == {"broken-model", "llama3.2"}

    failed_only = dashboard(client, project, status="failed")
    assert failed_only["totals"]["calls"] == 1
    assert failed_only["totals"]["failed"] == 1
    assert failed_only["models"][0]["model_id"] == "broken-model"
    assert failed_only["cost_status"] == "unavailable"

    llama_only = dashboard(client, project, model="llama3.2")
    assert llama_only["totals"]["calls"] == 1
    assert llama_only["totals"]["input_tokens"] == 12
    assert llama_only["cost_status"] == "estimated"

    provider_only = dashboard(client, project, provider=str(provider.id))
    assert provider_only["totals"]["calls"] == 2

    assert Decimal(data["costs"][0]["amount"]) == Decimal("0.000028")


def test_retention_is_disabled_when_days_are_zero(
    client, project, provider, fake_provider, settings
):
    response = run_playground(client, project, provider)
    trace = Trace.objects.get(execution_result_id=response.json()["results"][0]["id"])
    move_trace_to(trace, timezone.now() - timedelta(days=400))

    settings.OBSERVABILITY_TRACE_RETENTION_DAYS = 0
    result = purge_old_traces()
    assert result["enabled"] is False
    assert Trace.objects.count() == 1


def test_retention_refuses_to_delete_when_rollups_are_disabled(
    client, project, provider, fake_provider, settings
):
    response = run_playground(client, project, provider)
    trace = Trace.objects.get(execution_result_id=response.json()["results"][0]["id"])
    move_trace_to(trace, timezone.now() - timedelta(days=5))
    settings.OBSERVABILITY_ROLLUP_ENABLED = False
    settings.OBSERVABILITY_TRACE_RETENTION_DAYS = 1

    result = purge_old_traces()

    assert result["enabled"] is False
    assert result["deleted"] == 0
    assert Trace.objects.filter(pk=trace.pk).exists()


def test_retention_does_not_delete_when_rollup_fails(
    client, project, provider, fake_provider, settings, monkeypatch
):
    response = run_playground(client, project, provider)
    trace = Trace.objects.get(execution_result_id=response.json()["results"][0]["id"])
    move_trace_to(trace, timezone.now() - timedelta(days=5))
    settings.OBSERVABILITY_TRACE_RETENTION_DAYS = 1

    def fail_rollup(**kwargs):
        raise RuntimeError("rollup unavailable")

    monkeypatch.setattr("apps.observability.rollups.rollup_project", fail_rollup)
    result = purge_old_traces()

    assert result["deleted"] == 0
    assert result["errors"] == 1
    assert Trace.objects.filter(pk=trace.pk).exists()


def test_management_commands_roll_up_and_purge(
    client, project, provider, fake_provider
):
    old_day = timezone.now().date() - timedelta(days=5)
    response = run_playground(client, project, provider)
    trace = Trace.objects.get(execution_result_id=response.json()["results"][0]["id"])
    move_trace_to(
        trace, timezone.make_aware(datetime.combine(old_day, time.min))
    )

    call_command("rollup_traces", "--through", old_day.isoformat(), "--project", str(project.id))
    assert TraceRollup.objects.get(project=project, day=old_day).calls == 1

    call_command("purge_traces", "--days", "1")
    assert Trace.objects.count() == 0
    assert dashboard(client, project)["totals"]["calls"] == 1


def test_rollup_can_be_disabled(settings, project, provider, fake_provider):
    settings.OBSERVABILITY_ROLLUP_ENABLED = False
    result = rollup_project(project=project, through_day=timezone.now().date() - timedelta(days=1))
    assert result["enabled"] is False
    assert TraceRollupState.objects.filter(project=project).count() == 0
