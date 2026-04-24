from django.urls import path
from . import views

app_name = 'locations'

urlpatterns = [
    path('', views.location_list, name='list'),
    path('create/', views.location_create, name='create'),
    path('edit/<int:pk>/', views.location_edit, name='edit'),
    path('delete/<int:pk>/', views.location_delete, name='delete'),
]
