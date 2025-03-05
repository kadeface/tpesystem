from django.urls import path
from .admin_imports import ImportDataAdmin
from . import views

urlpatterns = [
    path('', ImportDataAdmin.get_import_data_view, name='import-data'),
    path('scores/', ImportDataAdmin.get_import_scores_view, name='import-scores'),
    path('teacher-subjects/', ImportDataAdmin.get_import_teacher_subjects_view, name='import-teacher-subjects'),
    path('teacher-history/', views.teacher_history_view, name='teacher_history'),
    path('rebuild-teacher-history/', views.rebuild_teacher_history, name='rebuild_teacher_history'),
    path('teacher-history-summary/', views.teacher_history_summary, name='teacher_history_summary'),
    path('promote-teachers/', views.promote_teachers_view, name='promote_teachers'),
    path('perform-teacher-promotion/', views.perform_teacher_promotion, name='perform_teacher_promotion'),
] 