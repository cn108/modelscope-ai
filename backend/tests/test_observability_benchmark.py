from io import StringIO

from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.observability.benchmark import cleanup_benchmark, seed_benchmark
from apps.observability.services import dashboard


def test_rollup_backed_dashboard_has_bounded_query_count(user):
    dataset = seed_benchmark(
        user=user,
        days=3,
        models=3,
        providers=2,
        raw_traces=30,
        calls_per_bucket=10,
    )
    try:
        with CaptureQueriesContext(connection) as queries:
            result = dashboard(
                user=user, project_id=dataset.project.pk, params={}
            )

        assert result["totals"]["calls"] == dataset.calls_represented + dataset.raw_traces
        assert result["rollups"]["through"] is not None
        assert result["rollups"]["from"] is not None
        assert result["models"]
        assert result["providers"]
        assert result["trend"]

        # The dashboard is a fixed set of aggregate queries. Old history must
        # come from the rollup table rather than one query per raw trace/group.
        assert len(queries) <= 40, [query["sql"] for query in queries]
        assert any(
            "observability_trace_rollup" in query["sql"] for query in queries
        )
    finally:
        cleanup_benchmark(dataset)


def test_benchmark_command_cleans_up_its_temporary_workspace(user):
    output = StringIO()
    call_command(
        "benchmark_observability",
        "--days",
        "1",
        "--models",
        "1",
        "--providers",
        "1",
        "--raw-traces",
        "2",
        "--calls-per-bucket",
        "2",
        "--runs",
        "1",
        stdout=output,
    )

    text = output.getvalue()
    assert '"database"' in text
    assert '"queries"' in text
    assert "Benchmark workspace removed." in text
