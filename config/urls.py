# config/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.shortcuts import render
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('home/', lambda r: render(r, 'landing.html'), name='landing'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('billing/expired/', lambda r: render(r, 'billing_expired.html'), name='billing_expired'),
    path('', include('core.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
from core import offline
urlpatterns += [
    path('app/', offline.app_page, name='offline_app'),
    path('app/sw.js', offline.service_worker),
    path('app/manifest.webmanifest', offline.manifest),
    path('app/icon.svg', offline.icon),
    path('app/api/bootstrap/', offline.bootstrap),
    path('app/api/sync/', offline.sync),
]
