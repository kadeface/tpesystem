"""
核心模块URL配置
仅保留必要的全局路由
"""
from django.urls import path
from . import views

urlpatterns = [
    # 仅保留普通视图路由
    path('upload/scores/', views.ScoreUploadView.as_view(), name='score_upload'),
    path('import-progress/', views.import_progress_view, name='import_progress'),
]
