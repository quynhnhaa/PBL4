from django.apps import AppConfig
import os
from .tcp_server import ServerManager
import signal

instance = None


class TcpserverConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tcpserver'

    def ready(self):
       if os.environ.get('RUN_MAIN') == 'true':
            global instance
            instance = ServerManager()
            print('origin : ')
            print(instance)

            signal.signal(signal.SIGTERM, self.shutdown_server)
            signal.signal(signal.SIGINT, self.shutdown_server)

    def shutdown_server(self):
        global instance
        if (instance):
            instance.shutdown_event.set()
