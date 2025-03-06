from django.urls import path, include
from .admin_imports import ImportDataAdmin
from . import views
from .views import import_progress_view, debug_trigger_task, debug_progress_file

# 主应用URL
app_urlpatterns = [
    path('import-progress/', import_progress_view, name='import_progress_view'),
    path('admin/import-progress/', import_progress_view, name='admin_import_progress'),
    path('api/import-progress/', views.import_progress, name='import_progress'),
    path('test-progress/', views.test_progress_tracker, name='test_progress'),
    path('direct-progress/<str:task_id>/', views.direct_progress_view, name='direct_progress'),
    path('simple-progress-test/', views.simple_progress_test, name='simple_progress_test'),
    path('start-simple-test/', views.start_simple_test, name='start_simple_test'),
    path('check-simple-test/', views.check_simple_test, name='check_simple_test'),
    path('debug/trigger-task/', debug_trigger_task, name='debug_trigger_task'),
    path('debug/progress-file/<str:task_id>/', debug_progress_file, name='debug_progress_file'),
]

# 导入功能URL
import_urlpatterns = [
    path('', ImportDataAdmin.get_import_data_view, name='import_data'),
    path('scores/', ImportDataAdmin.get_import_scores_view, name='import_scores'),
    path('teacher-subjects/', ImportDataAdmin.get_import_teacher_subjects_view, name='import_teacher_subjects'),
    # ...其他导入相关URL
]

# 合并所有URL
urlpatterns = app_urlpatterns + [
    path('imports/', include((import_urlpatterns, 'core'), namespace='imports'))
] 