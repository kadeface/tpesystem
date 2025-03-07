"""
URL 配置模块。

此模块定义了系统的 URL 路由规则。
"""

from django.urls import path, include
from core.admin_site import admin_site
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin_site.urls),
    path('core/', include('core.urls')),
    path('admin/import/', include('core.import_urls')),
    path('api/', include('rest_api.urls')),
]

# 仅在开发环境中添加媒体文件URL
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 