from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

@login_required
def auto_jobs_list_view(request):
    return HttpResponse('<h1>Auto Jobs List</h1><p>OK</p>')

@login_required
def auto_job_configure_view(request, pk):
    return HttpResponse('<h1>Configure</h1>')

@login_required
def auto_job_execute_api(request, pk):
    return HttpResponse('Execute')
