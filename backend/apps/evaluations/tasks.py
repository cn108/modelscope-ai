"""Celery entry point for evaluation runs."""

from celery import shared_task


@shared_task(bind=True, name="apps.evaluations.run_evaluation")
def run_evaluation(self, evaluation_id: str) -> dict:
    """Process one queued evaluation in a worker process.

    The heavy lifting lives in ``execute_evaluation`` so the same code path can
    be invoked eagerly by tests and synchronously by operators if needed.
    """
    from apps.evaluations.services import execute_evaluation

    task_id = getattr(self.request, "id", "") or ""
    return execute_evaluation(evaluation_id=evaluation_id, task_id=task_id)
