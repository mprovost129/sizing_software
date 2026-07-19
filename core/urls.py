from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('guide/', views.GuideView.as_view(), name='guide'),
]
