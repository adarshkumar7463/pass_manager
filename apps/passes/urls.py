from django.urls import path
from . import views

app_name = 'passes'

urlpatterns = [
    # Public
    path('', views.admin_dashboard, name='home'),
    path('generate-pass/<int:template_id>/', views.generate_pass_page, name='generate_pass'),
    path('pass/<path:unique_id>/', views.view_pass, name='view_pass'),
    path('pass/<path:unique_id>/print/', views.print_pass, name='print_pass'),
    path('pass/<path:unique_id>/pdf/', views.pass_pdf, name='pass_pdf'),

    # Admin
    path('admin-panel/', views.admin_dashboard, name='dashboard'),
    path('admin-panel/templates/', views.template_list, name='template_list'),
    path('admin-panel/templates/create/', views.template_create, name='template_create'),
    path('admin-panel/templates/<int:pk>/', views.template_detail, name='template_detail'),
    path('admin-panel/templates/<int:template_id>/bulk-pdf/', views.bulk_pass_pdf, name='bulk_pass_pdf'),
    path('admin-panel/templates/<int:template_id>/print-all/', views.bulk_print_view, name='bulk_print'),
    path('admin-panel/templates/<int:pk>/toggle/', views.toggle_template, name='toggle_template'),
    path('admin-panel/templates/<int:pk>/delete/', views.template_delete, name='template_delete'),
    path('admin-panel/passes/', views.passes_list, name='passes_list'),
    path('admin-panel/validate/', views.validate_pass_page, name='validate'),
    path('admin-panel/validate/lookup/', views.validate_pass_lookup, name='validate_lookup'),
    path('admin-panel/analytics/', views.analytics, name='analytics'),

    # Location scanning endpoints (hit by QR codes on passes)
    path('scan/<str:unique_id>/<str:prefix>/', views.scan_visit_page, name='scan_visit'),
    path('scan/<str:unique_id>/<str:prefix>/mark-done/', views.mark_visit_done, name='mark_visit_done'),
]