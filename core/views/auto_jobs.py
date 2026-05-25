"""
Auto Jobs views for webhook-based script execution with dynamic parameters.
"""

import json
import logging
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.urls import reverse

from core.models import Script, Run
from core.tasks import queue_script_run

logger = logging.getLogger(__name__)


@login_required
def auto_jobs_list_view(request):
    jobs = Script.objects.filter(
        is_enabled=True,
        archived_at__isnull=True,
        webhook_token__isnull=False,
    ).exclude(
        webhook_params__isnull=True
    ).select_related('environment')

    job_configs = {}
    for job in jobs:
        try:
            job_configs[str(job.pk)] = {
                'id': str(job.pk),
                'name': job.name,
                'description': job.description,
                'params': job.webhook_params,
                'execute_url': reverse('cpanel:auto_job_execute', kwargs={'pk': job.pk}),
                'configure_url': reverse('cpanel:auto_job_configure', kwargs={'pk': job.pk}),
            }
        except Exception as e:
            logger.error(f"Error preparing job config for {job.pk}: {e}")
            continue

    context = {
        'jobs': jobs,
        'job_configs_json': json.dumps(job_configs),
    }
    return render(request, 'cpanel/auto_jobs/list.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def auto_job_configure_view(request, pk):
    script = get_object_or_404(Script, pk=pk)

    if request.method == 'POST':
        params_json = request.POST.get('webhook_params', '[]').strip()
        try:
            params = json.loads(params_json)
            if not isinstance(params, list):
                raise ValueError('Parameters must be a JSON array')
        except (json.JSONDecodeError, ValueError) as e:
            messages.error(request, f'Invalid JSON: {str(e)}')
            return redirect('cpanel:auto_job_configure', pk=pk)

        script.webhook_params = params
        script.save(update_fields=['webhook_params', 'updated_at'])
        messages.success(request, f'Parameters saved for {script.name}')
        return redirect('cpanel:auto_jobs_list')

    current_params = json.dumps(script.webhook_params or [], indent=2)
    example_schema = [
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
    ]

    context = {
        'script': script,
        'current_params': current_params,
        'example_schema': json.dumps(example_schema, indent=2),
    }
    return render(request, 'cpanel/auto_jobs/configure.html', context)


@login_required
@require_http_methods(["POST"])
def auto_job_execute_api(request, pk):
    script = get_object_or_404(Script, pk=pk)

    if not script.is_auto_job:
        return JsonResponse({'error': 'Script is not configured as an auto-job'}, status=400)

    if not script.can_run:
        reason = 'archived' if script.is_archived else 'disabled'
        return JsonResponse({'error': f'Script is {reason}'}, status=403)

    try:
        body = json.loads(request.body)
        params = body.get('params', {})
        if not isinstance(params, dict):
            return JsonResponse({'error': 'Parameters must be a JSON object'}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)

    schema_errors = _validate_params(script.webhook_params, params)
    if schema_errors:
        return JsonResponse({'error': 'Invalid parameters', 'details': schema_errors}, status=400)

    try:
        run = Run.objects.create(
            script=script,
            status='pending',
            triggered_by=request.user,
            trigger_type='api',
            code_snapshot=script.code,
        )

        webhook_data = {
            'method': 'POST',
            'body': json.dumps(params),
            'body_json': params,
            'query': {},
            'content_type': 'application/json',
        }

        queue_script_run(run, webhook_data=webhook_data)
        logger.info(f"Auto-job {script.name} queued: {run.id}")

        return JsonResponse({
            'status': 'queued',
            'run_id': str(run.id),
            'run_url': reverse('cpanel:run_detail', kwargs={'pk': run.id}),
        })

    except Exception as e:
        logger.error(f"Auto-job execution failed: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to queue script execution'}, status=500)


def _validate_params(schema, params):
    if not schema:
        return []
    errors = []
    for param_def in schema:
        name = param_def.get('name')
        required = param_def.get('required', False)
        param_type = param_def.get('type', 'text')

        if required and name not in params:
            errors.append(f"{param_def.get('label', name)} is required")
            continue

        if name not in params:
            continue

        value = params[name]
        if param_type == 'email' and '@' not in str(value):
            errors.append(f"{param_def.get('label', name)} must be a valid email")
        elif param_type == 'url' and not str(value).startswith(('http://', 'https://')):
            errors.append(f"{param_def.get('label', name)} must be a valid URL")
        elif param_type == 'number':
            try:
                float(value)
            except (TypeError, ValueError):
                errors.append(f"{param_def.get('label', name)} must be a number")

    return errors
