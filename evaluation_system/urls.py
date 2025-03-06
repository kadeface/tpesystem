"""
URL 配置模块。

此模块定义了系统的 URL 路由规则。
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import (
    RegionViewSet, SemesterViewSet, SchoolViewSet,
    StudentViewSet, ScoreUploadView
)
from core.admin_site import admin_site, dashboard_site
from core.admin_imports import ImportDataAdmin as DataImportToolAdmin
from django.views.generic import RedirectView
from core.models import DataImportTool
from django.conf import settings
from django.conf.urls.static import static
from api.views import import_progress

router = DefaultRouter()
router.register(r'regions', RegionViewSet)
router.register(r'semesters', SemesterViewSet)
router.register(r'schools', SchoolViewSet)
router.register(r'students', StudentViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('core/', include('core.urls')),
    path('upload/scores/', ScoreUploadView.as_view(), name='upload-scores'),
    path('admin/', admin_site.urls),
    path('default-admin/', admin.site.urls),
    path('dashboard/', dashboard_site.urls),
    path('tools/import-data/', admin_site.admin_view(DataImportToolAdmin.get_import_data_view), name='admin-import-data'),
    path('tools/default-admin/import-data/', admin.site.admin_view(DataImportToolAdmin.get_import_data_view), name='default-admin-import-data'),
    path('import-data/', admin_site.admin_view(DataImportToolAdmin.get_import_data_view), name='import-data'),
    path('import-scores/', admin_site.admin_view(DataImportToolAdmin.get_import_scores_view), name='import-scores'),
    path('import-teacher-subjects/', admin_site.admin_view(DataImportToolAdmin.get_import_teacher_subjects_view), name='import-teacher-subjects'),
    path('api/import-progress/<uuid:task_id>/', import_progress, name='import-progress'),
]

# 仅在开发环境中添加媒体文件URL
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 