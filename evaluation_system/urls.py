"""
URL 配置模块。

此模块定义了系统的 URL 路由规则。
"""

from django.urls import path, include
from core.admin_site import admin_site
from django.conf import settings
from django.conf.urls.static import static
from core import views
from edu_insights.views import StudentExamScoresView

urlpatterns = [
    path('admin/', admin_site.urls),
    path('core/', include('core.urls')),
    path('admin/import/', include('core.import_urls')),
    path('api/', include('rest_api.urls')),
    #path('', include('api.urls')),
    path('api/v1/', include('core.api_urls')),  
    path('api/debug/regions/', views.debug_regions, name='debug_regions'),
    path('api/raw/regions/', views.raw_regions_debug, name='raw_regions_debug'),
    path('api/edu-insights/', include('edu_insights.urls')),
    path('api/v1/students/<str:student_id>/scores/', StudentExamScoresView.as_view(), name='student-scores-api-v1'),
]

# 仅在开发环境中添加媒体文件URL
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 