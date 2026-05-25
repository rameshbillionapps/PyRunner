import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods

from core.models import Script, Run
from core.tasks import queue_script_run


@login_required
def auto_jobs_list_view(request):
    """List all scripts configured as auto-jobs."""
    jobs = Script.objects.filter(
        is_enabled=True,
        archived_at__isnull=True,
        webhook_token__isnull=False,
    ).exclude(
        webhook_params__isnull=True
    ).values('id', 'name', 'description')

    return render(request, 'cpanel/auto_jobs_list.html', {
        'jobs': jobs,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def auto_job_configure_view(request, pk):
    """View/edit auto-job parameter schema."""
    script = get_object_or_404(Script, id=pk, is_enabled=True, archived_at__isnull=True)

    if request.method == 'POST':
        try:
            params_json = request.POST.get('webhook_params', '[]')
            params = json.loads(params_json)
            if not isinstance(params, list):
                raise ValueError("webhook_params must be a JSON array")
            script.webhook_params = params
            script.save(update_fields=['webhook_params'])
            return render(request, 'cpanel/auto_jobs_list.html', {
                'success_message': 'Auto-job configuration saved successfully!'
            })
        except (json.JSONDecodeError, ValueError) as e:
            return render(request, 'cpanel/auto_jobs_configure.html', {
                'script': script,
                'error_message': f'Invalid JSON: {str(e)}'
            })

    return render(request, 'cpanel/auto_jobs_configure.html', {
        'script': script,
        'webhook_params_json': json.dumps(script.webhook_params or []),
    })


@login_required
@require_http_methods(['POST'])
def auto_job_execute_api(request, pk):
    """Execute an auto-job with parameters."""
    script = get_object_or_404(Script, id=pk, is_enabled=True, archived_at__isnull=True)

    if not script.webhook_token or not script.webhook_params:
        return JsonResponse({
            'error': 'Script not configured as auto-job'
        }, status=400)

    try:
        body = json.loads(request.body)
        params = body.get('params', {})
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON in request body'
        }, status=400)

    try:
        run = Run.objects.create(
            script=script,
            status=Run.Status.PENDING,
            triggered_by=request.user,
            trigger_type=Run.TriggerType.API,
            code_snapshot=script.code,
        )

        webhook_data = {
            'method': 'POST',
            'body': json.dumps(params),
            'body_json': params,
            'content_type': 'application/json',
            'query': {}
        }

        queue_script_run(run, webhook_data=webhook_data)

        return JsonResponse({
            'status': 'queued',
            'run_id': str(run.id),
            'run_url': f'/cpanel/runs/{run.id}/'
        })
    except Exception as e:
        return JsonResponse({
            'error': f'Failed to queue run: {str(e)}'
        }, status=500)
