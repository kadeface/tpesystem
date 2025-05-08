from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AnalysisTaskViewSet, StudentExamScoresView, TeacherValueAddedView,exams_by_semester_grade, GenerateExamFeaturesView, exam_feature_status, GenerateExamFeaturesView
from .admin import StudentScoreFeaturesAdmin
from django.contrib import admin
from core.admin_site import admin_site

router = DefaultRouter()
router.register(r'tasks', AnalysisTaskViewSet, basename='analysistask')

urlpatterns = [
    path('', include(router.urls)),
    #path('api/admin/exams-by-semester-grade/<str:semester_id>/<str:grade_id>/', exams_by_semester_grade, name='exams-by-semester-grade'),
    path('students/<str:student_id>/scores/', StudentExamScoresView.as_view(), name='student-exam-scores'),
    path('api/', include(router.urls)),
    path('api/v1/', include('api.urls')),
    path('', include('api.urls')),  # 直接路径作为备选
    path('teacher-value-added/', TeacherValueAddedView.as_view(), name='teacher-value-added'),
    path('api/teacher-value-added/', TeacherValueAddedView.as_view(), name='teacher-value-added'),
    path('generate-features/', StudentScoreFeaturesAdmin.generate_features_view, name='generate_features'),
    path('admin/', admin_site.urls),
    #path('admin/api/exams-by-semester/<int:semester_id>/', insights_views.exams_by_semester, name='exams-by-semester'),
    path('api/admin/generate-exam-features/', GenerateExamFeaturesView.as_view(), name='generate_exam_features'),
    path('api/admin/exam-feature-status/<str:exam_id>/', exam_feature_status, name='exam_feature_status'),
]