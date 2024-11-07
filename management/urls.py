from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from .views import ObserverView, ComputersView,DetailView,DistributionView,GetComputersInfos,GetComputersView,EditComputerInfo,StopScreenshot,GetAllNotifications,GetIdleComputersInfos

urlpatterns = [
    path('observer',ObserverView.as_view(),name = 'observer'),
    path('computers',ComputersView.as_view(),name = 'computers'),
    path('detail',DetailView.as_view(),name = 'detail'),
    path('distribution', csrf_exempt(DistributionView.as_view()), name = 'distribution'),
    path('getComputersInfos',csrf_exempt(GetComputersInfos.as_view())),
    path('editComputerInfo',csrf_exempt(EditComputerInfo.as_view())),
    path('getIdleComputersInfos',csrf_exempt(GetIdleComputersInfos.as_view())), 
    path('stopScreenshot',csrf_exempt(StopScreenshot.as_view())),
    path('getComputersView',csrf_exempt( GetComputersView.as_view())),
    path('getAllNotifications',csrf_exempt(GetAllNotifications.as_view())),
]