"""
核心模块URL配置
仅保留必要的全局路由
"""
from django.urls import path
from . import views
from . import admin_imports

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
]
