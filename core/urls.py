"""
核心模块URL配置
仅保留必要的全局路由
"""
from django.urls import path, include
from . import views
from . import admin_imports
from api.views import StudentGrowthAnalysisAPI
from .views import ExamListView


urlpatterns = [
    # 仅保留普通视图路由
    path('upload/scores/', views.ScoreUploadView.as_view(), name='score_upload'),
    path('import-progress/', views.import_progress_view, name='import_progress'),
    # 临时注释掉API路由
    # path('api/task-status/', views.task_status_api, name='task_status_api'),
    path('simple-import-progress/', views.simple_import_progress_view, name='simple_import_progress'),
    path('import-scores/', admin_imports.import_scores_view, name='import_scores'),
    path('import-progress/', admin_imports.import_progress_view, name='import_progress'),
    path('task-progress/<uuid:task_id>/', admin_imports.task_progress_view, name='task_progress'),
    path('api/students/<str:student_id>/growth-analysis/', StudentGrowthAnalysisAPI.as_view(), name='student_growth_analysis'),
    path('api/debug/regions/', views.debug_regions, name='debug_regions'),
    path('api/exams/', ExamListView.as_view(), name='exam-list'),
    path('api/test-exam-route/', views.test_exam_view, name='test-exam-route'),
    path('api/debug-exams/', views.debug_exam_view, name='debug-exams'),

]
