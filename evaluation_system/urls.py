"""
URL 配置模块。

此模块定义了系统的 URL 路由规则。
"""

from django.urls import path, include
from core.admin_site import admin_site
from django.conf import settings
from django.conf.urls.static import static
from core import views
from edu_insights.views import StudentExamScoresView, exams_by_semester_grade, exams_by_current_grade, GenerateExamFeaturesView, exam_feature_status

urlpatterns = [
    path('admin/', admin_site.urls),
    path('core/', include('core.urls')),
    path('admin/import/', include('core.import_urls')),
    path('api/', include('rest_api.urls')),
    path('', include('edu_insights.urls')),
    path('api/v1/', include('core.api_urls')),  
    path('api/debug/regions/', views.debug_regions, name='debug_regions'),
    path('api/raw/regions/', views.raw_regions_debug, name='raw_regions_debug'),
    path('api/v1/students/<str:student_id>/scores/', StudentExamScoresView.as_view(), name='student-scores-api-v1'),
    path('api/admin/exams-by-semester-grade/<str:semester_id>/<str:grade_id>/', 
         exams_by_semester_grade, 
         name='exams-by-semester-grade'),
    path('api/admin/grade-timeline/<str:current_grade_id>/', 
         exams_by_current_grade, 
         name='grade-timeline'),
    path('api/admin/generate-exam-features/', GenerateExamFeaturesView.as_view(), name='generate_exam_features'),
    path('api/admin/exam-feature-status/<str:exam_id>/', exam_feature_status, name='exam_feature_status'),
]

# 仅在开发环境中添加媒体文件URL
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) 