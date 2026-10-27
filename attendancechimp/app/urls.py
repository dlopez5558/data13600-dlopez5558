from django.urls import path, include
from . import views

urlpatterns = [
    path('time', views.time_view, name='time'),
    path('sum', views.sum_view, name='sum'),
    path("", views.index, name="home"),
    path("index.html", views.index, name="index_html"),
    path("new", views.signup_view, name="signup"),
    path("createUser", views.createUser, name="createUser"),
    path("accounts/", include("django.contrib.auth.urls")),
]
