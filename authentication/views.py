from django.shortcuts import render,redirect
from django.http import HttpResponse, JsonResponse
from django.views import View
from decouple import config

# Create your views here.
class LoginView(View):
    def get(self, request):
        return render(request, 'authentication/login.html')
    
    def post(self, request):
        if request.POST.get('guest') == 'true':
            request.session['role'] = 'client'
            return redirect('chat')
        elif request.POST.get('username') == config('ADMIN_USERNAME') and request.POST.get('password') == config('ADMIN_PASSWORD'):
            request.session['role'] = 'admin'
            return redirect('computers')
        return render(request, 'authentication/login.html')
        
    
# class AdminLoginView(View):

#     def post(self,request):
#         username = request.POST.get('username')
#         password = request.POST.get('password')
#         if username == 'admin' and password == 'admin':
#             return render(request, 'home/index.html')
#         else:
#             return render(request, 'authentication/login.html', {'error': 'Invalid credentials'})
        
# class ClientLoginView(View):

#     def get(self, request):
#         return render(request, 'client/chat.html')
    
def admin_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if request.session.get('role') != 'admin':
            return HttpResponse("Unauthorized", status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def client_required(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if request.session.get('role') != 'client':
            return HttpResponse("Unauthorized", status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped_view