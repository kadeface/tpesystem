from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    path('task-status/', views.task_status, name='task_status'),
    path('scores/query/', views.StudentScoresQueryView.as_view(), name='student-scores-query'),
    
] 