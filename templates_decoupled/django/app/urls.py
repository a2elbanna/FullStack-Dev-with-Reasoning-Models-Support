from django.urls import path
from . import views

urlpatterns = [
    path('', views.api_root, name='api-root'),
    path('hello/', views.hello_world, name='hello-world'),
    path('users/', views.UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
]