from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


@login_required
def auto_jobs_list_view(request):
    return HttpResponse("Auto Jobs List Page - OK")


@login_required
def auto_job_configure_view(request, pk):
    return HttpResponse("Configure Auto Job - OK")


@login_required
def auto_job_execute_api(request, pk):
    return JsonResponse({"status": "ok"})
