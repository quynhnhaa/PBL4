from django.db import models

# Create your models here.
class Department(models.Model):
    name = models.CharField(max_length= 180, null = False, unique = True)
    subnet = models.CharField(max_length= 30, null = False, unique = True)

class Computer(models.Model):
    name = models.CharField(max_length= 180, null = False)
    description = models.CharField(max_length = 250,null=True)
    mac_address = models.CharField(max_length= 30, null = False, unique = True)
    department = models.ForeignKey(Department, related_name='computers', on_delete=models.SET_NULL, null=True)

class Notification(models.Model):
    name = models.CharField(max_length=180,null= False)

    class Meta:
        managed = False