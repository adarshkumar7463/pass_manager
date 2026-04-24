from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('apps.passes.urls')),
    path('admin-panel/', include('apps.accounts.urls')),
    path('locations/', include('apps.locations.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
