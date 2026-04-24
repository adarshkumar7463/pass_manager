from django.urls import path
from . import views

app_name = 'locations'

urlpatterns = [
    path('', views.location_list, name='list'),
    path('create/', views.location_create, name='create'),
    path('<int:pk>/edit/', views.location_edit, name='edit'),
]
