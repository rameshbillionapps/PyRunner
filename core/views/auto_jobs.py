"""
Auto Jobs views for webhook-based script execution with dynamic parameters.
"""

import json
import logging
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse

from core.models import Script, Run
from core.tasks import queue_script_run

logger = logging.getLogger(__name__)


@login_required
def auto_jobs_list_view(request: HttpRequest):
    """
    List all scripts configured as auto-jobs.
    Only shows enabled scripts that have both webhook token and params defined.
    """
    jobs = Script.objects.filter(
        is_enabled=True,
        archived_at__isnull=True,
        webhook_token__isnull=False,
    ).exclude(
        webhook_params__isnull=True
    ).select_related('environment')

    # Prepare job configs for JavaScript
    job_configs = {}
    for job in jobs:
        job_configs[str(job.pk)] = {
            'id': str(job.pk),
            'name': job.name,
            'description': job.description,
            'params': job.webhook_params,
            'execute_url': reverse('cpanel:auto_job_execute', kwargs={'pk': job.pk}),
            'configure_url': reverse('cpanel:auto_job_configure', kwargs={'pk': job.pk}),
            'run_detail_url_pattern': reverse('cpanel:run_detail', kwargs={'pk': '00000000-0000-0000-0000-000000000000'}).replace('00000000-0000-0000-0000-000000000000', '{}'),
        }

    context = {
        'jobs': jobs,
        'job_configs_json': json.dumps(job_configs),
    }
    return render(request, 'cpanel/auto_jobs/list.html', context)


@login_required
def auto_job_configure_view(request: HttpRequest, pk):
    """
    Configure webhook parameters for a script.
    GET: Display form with Monaco JSON editor
    POST: Save webhook_params as JSON
    """
    script = get_object_or_404(Script, pk=pk)

    if request.method == 'POST':
        params_json = request.POST.get('webhook_params', '[]').strip()

        # Validate JSON
        try:
            params = json.loads(params_json)
            if not isinstance(params, list):
                raise ValueError('Parameters must be a JSON array')
        except (json.JSONDecodeError, ValueError) as e:
            messages.error(request, f'Invalid JSON: {str(e)}')
            return redirect('cpanel:auto_job_configure', pk=pk)

        # Save
        script.webhook_params = params
        script.save(update_fields=['webhook_params', 'updated_at'])
        messages.success(request, f'Parameters saved for {script.name}')
        return redirect('cpanel:auto_jobs_list')

    # GET: Show form
    current_params = json.dumps(script.webhook_params or [], indent=2)

    context = {
        'script': script,
        'current_params': current_params,
        'example_schema': json.dumps([
            {
                'name': 'target_url',
                'label': 'Target URL',
                'type': 'url',
                'required': True,
                'placeholder': 'https://example.com',
                'help_text': 'Website URL to audit'
            },
            {
                'name': 'recipient_email',
                'label': 'Recipient Email',
                'type': 'email',
                'required': True,
                'placeholder': 'user@example.com',
                'help_text': 'Email to send report to'
            }
        ], indent=2),
    }
    return render(request, 'cpanel/auto_jobs/configure.html', context)


@login_required
@require_POST
def auto_job_execute_api(request: HttpRequest, pk):
    """
    Execute an auto-job with provided parameters.
    Accepts JSON POST: {"params": {"target_url": "...", "recipient_email": "..."}}
    Returns: {"status": "queued", "run_id": "...", "run_url": "..."}
    """
    script = get_object_or_404(Script, pk=pk)

    # Check if script is configured as auto-job
    if not script.is_auto_job:
        return JsonResponse({
            'error': 'Script is not configured as an auto-job'
        }, status=400)

    # Check if script can run
    if not script.can_run:
        reason = 'archived' if script.is_archived else 'disabled'
        return JsonResponse({
            'error': f'Script is {reason}'
        }, status=403)

    # Parse request body
    try:
        body = json.loads(request.body)
        params = body.get('params', {})
        if not isinstance(params, dict):
            return JsonResponse({
                'error': 'Parameters must be a JSON object'
            }, status=400)
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON in request body'
        }, status=400)

    # Validate required parameters
    schema_errors = _validate_params(script.webhook_params, params)
    if schema_errors:
        return JsonResponse({
            'error': 'Invalid parameters',
            'details': schema_errors
        }, status=400)

    # Create Run record
    run = Run.objects.create(
        script=script,
        status=Run.Status.PENDING,
        triggered_by=request.user,
        trigger_type=Run.TriggerType.API,
        code_snapshot=script.code,
    )

    # Build webhook data
    webhook_data = {
        'method': 'POST',
        'body': json.dumps(params),
        'body_json': params,
        'query': {},
        'content_type': 'application/json',
    }

    # Queue execution
    try:
        queue_script_run(run, webhook_data=webhook_data)
        logger.info(f"Auto-job {script.name} queued by {request.user.username}: run {run.id}")

        return JsonResponse({
            'status': 'queued',
            'run_id': str(run.id),
            'run_url': reverse('cpanel:run_detail', kwargs={'pk': run.id}),
        })

    except Exception as e:
        run.status = Run.Status.FAILED
        run.stderr = f"Failed to queue: {str(e)}"
        run.save()
        logger.error(f"Failed to queue auto-job run {run.id}: {e}")

        return JsonResponse({
            'error': 'Failed to queue script execution'
        }, status=500)


def _validate_params(schema: list, params: dict) -> list:
    """
    Validate provided parameters against schema.
    Returns list of validation errors (empty if valid).
    """
    if not schema:
        return []

    errors = []
    schema_dict = {param['name']: param for param in schema}

    for param_def in schema:
        name = param_def.get('name')
        required = param_def.get('required', False)
        param_type = param_def.get('type', 'text')

        # Check required
        if required and name not in params:
            errors.append(f"{param_def.get('label', name)} is required")
            continue

        # Skip validation if not provided and not required
        if name not in params:
            continue

        value = params[name]

        # Type validation
        if param_type == 'email':
            if '@' not in str(value):
                errors.append(f"{param_def.get('label', name)} must be a valid email")
        elif param_type == 'url':
            if not str(value).startswith(('http://', 'https://')):
                errors.append(f"{param_def.get('label', name)} must be a valid URL")
        elif param_type == 'number':
            try:
                float(value)
            except (TypeError, ValueError):
                errors.append(f"{param_def.get('label', name)} must be a number")

    return errors
