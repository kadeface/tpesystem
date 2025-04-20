from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AnalysisTaskViewSet, StudentExamScoresView

router = DefaultRouter()
router.register(r'tasks', AnalysisTaskViewSet, basename='analysistask')

urlpatterns = [
    path('', include(router.urls)),
    path('students/<str:student_id>/scores/', StudentExamScoresView.as_view(), name='student-exam-scores'),
    path('api/', include('api.urls')),
    path('api/v1/', include('api.urls')),
    path('', include('api.urls')),  # 直接路径作为备选
] 