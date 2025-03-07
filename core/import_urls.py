from django.urls import path
from .admin_imports import ImportDataAdmin
from . import views

app_name = 'core_imports'

urlpatterns = [
 
    path('data-import/', ImportDataAdmin.data_import_view, name='data_import'),
    path('scores-import/', ImportDataAdmin.scores_import_view, name='scores_import'),
    path('teacher-import/', ImportDataAdmin.teacher_import_view, name='teacher_import'),
 
    path('teacher-history/', views.teacher_history_view, name='teacher_history'),
    path('rebuild-teacher-history/', views.rebuild_teacher_history, name='rebuild_teacher_history'),
    path('teacher-history-summary/', views.teacher_history_summary, name='teacher_history_summary'),
    path('promote-teachers/', views.promote_teachers_view, name='promote_teachers'),
    path('perform-teacher-promotion/', views.perform_teacher_promotion, name='perform_teacher_promotion'),
] 