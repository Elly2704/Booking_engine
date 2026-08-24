from django.urls import path
from .views import resource_list_view, category_stats_view

app_name = 'resources'

urlpatterns = [
    path('', resource_list_view, name='resource_list'),
    path('stats/', category_stats_view, name='category_stats'),
]