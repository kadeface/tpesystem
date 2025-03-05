from django.urls import path
from . import views

urlpatterns = [
    path('import-progress/', views.import_progress, name='import_progress'),
] 