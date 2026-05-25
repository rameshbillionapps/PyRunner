from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

@login_required
def auto_jobs_list_view(request):
    return render(request, 'cpanel/auto_jobs/list.html', {
        'jobs': [],
        'job_configs_json': '{}',
    })

@login_required
def auto_job_configure_view(request, pk):
    return HttpResponse('Configure')

@login_required
def auto_job_execute_api(request, pk):
    return HttpResponse('Execute')
