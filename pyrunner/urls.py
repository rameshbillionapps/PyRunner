"""
URL configuration for pyrunner project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.http import HttpResponse

from core.views.webhooks import webhook_trigger_view


def simple_test_view(request):
    return HttpResponse("SIMPLE TEST - IF YOU SEE THIS, URLS WORK")


def get_admin_url_slug():
    """
    Get admin URL slug from settings.
    Called at startup - changes require app restart.
    """
    try:
        from core.models import GlobalSettings
        return GlobalSettings.get_settings().admin_url_slug or "django-admin"
    except Exception:
        return "django-admin"


urlpatterns = [
    path(f"{get_admin_url_slug()}/", admin.site.urls),
    path("setup/", include("core.urls.setup")),
    path("auth/", include("core.urls.auth")),
    path("simple-test/", simple_test_view, name="simple_test"),  # Test route
    path("cpanel/", include("core.urls.cpanel")),
    # REST API endpoints (token auth required)
    path("api/v1/", include("core.urls.api")),
    # Public webhook endpoint (no auth required)
    path("webhook/<str:token>/", webhook_trigger_view, name="webhook_trigger"),
    path("", lambda request: redirect("auth:login")),
]
