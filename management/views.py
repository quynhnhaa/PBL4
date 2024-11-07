from django.shortcuts import render
from django.http import JsonResponse
from django.views import View
import json
#from tcpserver.instance import instance
from tcpserver.apps import instance
from django.utils.decorators import method_decorator
from authentication.views import admin_required

# Create your views here.

class ObserverView(View):
    @method_decorator(admin_required)
    def get(self, request):
        return render(request, 'management/observer.html')
    
class StopScreenshot(View):
    def post(self, request):
        data = json.loads(request.body)
        client_ip = data['client_ip']
        if (instance) :
            if (client_ip):
                instance.stop_screenshot_from_client(client_ip)
            else :
                instance.stop_screenshot_from_client('')
        return JsonResponse({'success':'true'}, safe=False)
 
class ComputersView(View):
    @method_decorator(admin_required)
    def get(self, request):
        return render(request, 'management/computers.html')
    
class GetAllNotifications(View):
    def get(self, request):
        if (instance) :
            notifications = instance.get_all_notifications()
            notifications_data = [{'name':n.name, 'numOfMessages':n.numOfMessages, 'computerIP' :n.ip} for n in notifications]
            return JsonResponse(notifications_data, safe=False)
        else :
            return JsonResponse([], safe=False)
    

class GetComputersInfos(View):

    def post(self, request):
        data = json.loads(request.body)
        department = data['department']
        if (instance) :
            computers = instance.get_computers_infos(department)
            computers_data = [{'name':c.name, 'department':c.departmentName, 'description' :c.description, 'ip' :c.ip, 'status' : c.status,'mac_address':c.mac_address} for c in computers]
            return JsonResponse(computers_data, safe=False)
        else :
            return JsonResponse([], safe=False)
        
class GetIdleComputersInfos(View):
    
    def post(self, request):
        data = json.loads(request.body)
        department = data['department']
        if (instance) :
            computers = instance.get_idle_computers_infos(department)
            computers_data = [{'name':c.name, 'department':c.departmentName, 'description' :c.description, 'status' : c.status,'mac_address':c.mac_address} for c in computers]
            return JsonResponse(computers_data, safe=False)
        else :
            return JsonResponse([], safe=False)

class EditComputerInfo(View):
    
    def post(self, request):
        data = json.loads(request.body)
        print(data)
        if (instance) :
            instance.edit_computer_info(data)
        return JsonResponse({'success':'true'}, safe=False)

class GetComputersView(View):
    
    def post(self, request):
        data = json.loads(request.body)
        department = data['department']
        print(department)
        if (instance) :
            instance.request_screenshot_from_client('')
            computers = instance.get_all_screen(department)
            computers_data = [{'name':c.name, 'department':c.departmentName, 'ip' :c.ip,'mac_address':c.mac_address} for c in computers]
            return JsonResponse(computers_data, safe=False)
        else :
            return JsonResponse([], safe=False)
    

class DetailView(View):
    
    def post(self, request):
        ip = request.POST.get('ip')
        if ip :
            if (instance) : 
                computer = instance.get_computer_detail(ip)
            else :
                computer = None
        else :
            computer = None
        return render(request, 'management/detail.html', {'computer': computer})


class DistributionView(View):
    @method_decorator(admin_required)
    def post(self, request):
        ip = request.POST.get('ip')
        if ip :
            if (instance) : 
                instance.request_screenshot_from_client(ip)
                computer = instance.get_computer_detail(ip)
            else :
                computer = None
        else :
            computer = None
        return render(request, 'management/distribution.html', {'computer': computer})