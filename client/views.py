from django.shortcuts import render
from django.views import View
from django.utils.decorators import method_decorator
from authentication.views import client_required
from tcpserver.apps import instance

# Create your views here.
def getClientIP(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]  # Lấy IP đầu tiên nếu đi qua proxy
    else:
        ip = request.META.get('REMOTE_ADDR')  # Lấy IP từ request trực tiếp
    return ip

class ChatView(View):
    @method_decorator(client_required)
    def get(self, request):
        client_ip = getClientIP(request)
        computer = instance.get_computer_detail(client_ip)
        return render(request, 'client/chat.html', {'computer': computer})
    
