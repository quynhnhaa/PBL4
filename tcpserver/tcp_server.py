
import ipaddress
from BKLanManager.settings import BASE_DIR
import json
import os
import socket
import threading
import time
import asyncio
import websockets
from decouple import config
from scapy.all import ARP, Ether, srp
import netifaces as ni
HOST = config('SERVER_HOST')
PORT_TCP = 12345
PORT_WS = 6969

class ServerManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ServerManager, cls).__new__(cls)
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self, host= HOST, port= PORT_TCP):
        if self.__initialized:
            return
        self.HOST = host
        self.PORT = port
        self.BUFFER_SIZE = 4096
        self.SAVE_PATH = os.path.join(BASE_DIR,'media/screenshots')
        #self.SAVE_PATH = './screenshots/'
        self.clientSs = {}
        self.adminCWS = None  # WebSocket của Admin
        self.clientCWS = None
        self.clientCWSIP = None   # WebSocket của client mà admin đang nhắn tin
        self.currentWSRole = None
        self.clientWSs = {}    # Lưu các WebSocket của client dựa trên client-ID
        self.client_screenshot_request = {}
        self.chat_list = []    # Danh sách tin nhắn giữa cient và server
        self.chat_received_event = {} # Danh sách sự kiện cho mỗi client
        self.notification_list = {} # Danh sách thông báo
        self.subnet_list = [] # Danh sách các subnet của từng khoa
        self.active_hosts = {} # Từ điển lưu các ip đang hoạt động trong đó key: ip, value: mac
        self.shutdown_event = threading.Event()
        self.lock = threading.Lock()

        # Tạo thư mục lưu ảnh nếu chưa có
        if not os.path.exists(self.SAVE_PATH):
            os.makedirs(self.SAVE_PATH)

        # Khởi động server TCP
        threading.Thread(target=self.start_server, daemon=True).start()

        # # Khởi động server WebSocket
        self.ws_thread = threading.Thread(target=self.start_ws_server, daemon=True)
        self.ws_thread.start()

        self.__initialized = True

    # Sự kiện thay đổi chat_list
    def initialize_chat_event(self, client_id):
        # Khởi tạo sự kiện mới cho mỗi client
        self.chat_received_event[client_id] = asyncio.Event()

    # Hàm trả về danh sách các IP đang hoạt động
    def get_computers_infos(self,dName):
        from .models import Department, Computer
        '''Trả về danh sách các model có IP đang hoạt động, trong đó model sẽ có dang:
            name, description, department(một liên kết đến khoá ngoại, có thể lấy tên khoa bằng cách 'model.department.name' tương tự cho subnet) và ip" '''            
        result_list = [] # Danh sách trả về 
        for ip, mac in self.active_hosts.items():
            computer = Computer.objects.get(mac_address = mac)
            computer.departmentName = computer.department.name
            computer.ip = ip
            computer.status = "Online"
            if (ip in self.clientSs):
                computer.status = computer.status + " (Đã kết nối)"
            else :
                computer.status = computer.status + " (Chưa kết nối)"

            if (computer.departmentName == dName or dName == 'all') :
                result_list.append(computer)
        return result_list
    
    def get_idle_computers_infos(self,dName) :
        from .models import Department, Computer
        '''Trả về danh sách các model có IP đang hoạt động, trong đó model sẽ có dang:
            name, description, department(một liên kết đến khoá ngoại, có thể lấy tên khoa bằng cách 'model.department.name' tương tự cho subnet) và ip" '''            
        result_list = [] # Danh sách trả về 
        computer_list = Computer.objects.all()
        for computer in computer_list:
            if (not computer.mac_address in self.active_hosts.values()) :
                computer.departmentName = computer.department.name
                computer.status = "Offline"
                if (computer.departmentName == dName or dName == 'all') :
                    result_list.append(computer) 
        return result_list
    
    # Hàm Trả về danh sách các model yêu cầu hình ảnh
    def get_all_screen(self, dName):
        '''Tham số là danh sách các ip yêu cầu hình ảnh
            Trả về danh sách các model yêu cầu hình ảnh có dạng:
                name(tên máy), department(một liên kết đến khoá ngoại, lấy tên khoa bằng cách 'model.department.name' tương tự cho subnet), ip, image_name(tên của ảnh)'''
        result_list = []
        for key in self.clientSs.keys():
            if (computer := self.get_computer_detail(key)):
                if (dName == 'all' or dName == computer.departmentName):
                    result_list.append(computer)
        return result_list
    
    def get_computer_detail(self, ip):
        from .models import Department, Computer
        '''Tham số là địa chỉ ip cần thông tin chi tiết
            Trả về thông tin chi tiết của máy, model có dạng:
                name, description, mac_address, department(foreignkey), ip, image_name'''
        mac_addr= self.active_hosts.get(ip)
        if mac_addr:
            computer = Computer.objects.get(mac_address = mac_addr)
            computer.departmentName = computer.department.name
            computer.ip = ip
            computer.image_name = f"screenshot-{ip}.png"
            return computer
        return None
    
    def get_all_notifications(self):
        from .models import Notification
        result = []
        for clientIp, numOfMessages in self.notification_list.items():
            computer = self.get_computer_detail(clientIp)
            if computer:
                notification = Notification()
                notification.ip = clientIp
                notification.numOfMessages = numOfMessages
                notification.name = computer.name
                result.append(notification)

        return result

            

    # Kiểm tra xem địa chỉ IP có thuộc subnet nào không và trả về index
    def find_subnet_index(self, ip):
        ip_address = ipaddress.ip_address(ip)  # Chuyển đổi địa chỉ IP thành đối tượng IP
        for index, subnet in enumerate(self.subnet_list):  # Sử dụng enumerate để lấy index
            if ip_address in ipaddress.ip_network(subnet):  # Kiểm tra xem IP có thuộc subnet không
                return index  # Trả về index nếu tìm thấy
        return None  # Trả về None nếu không tìm thấy
    
    # Phương thức quét IP
    def scan_ips(self, subnet):
        from .models import Department, Computer
        while not self.shutdown_event.is_set():
            # print(f"Đang quét subnet {subnet}")
            arp = ARP(pdst=subnet)
            ether = Ether(dst="ff:ff:ff:ff:ff:ff")
            packet = ether / arp

            # Gửi gói và nhận phản hồi
            result = srp(packet, timeout=3, verbose=0)[0]

            self.active_hosts = {}  # Khởi tạo dictionary rỗng
            for sent, received in result:
                # Sử dụng địa chỉ IP làm khóa và địa chỉ MAC làm giá trị
                self.active_hosts[received.psrc] = received.hwsrc

            # print("Các máy đang hoạt động:")
            for ip, mac in self.active_hosts.items():
                # Tìm xem địa chỉ IP thuộc subnet của Khoa nào
                department_id = self.find_subnet_index(ip) + 1 # Vì id trong CSDL sẽ + 1 so với self.subnet_list (Ví dụ: index:0 KHoa CNTT trong subnet_list thì trong CSDL id:1)
                try:
                    # Lấy department bằng pk
                    department = Department.objects.get(pk=department_id )   
                except Department.DoesNotExist:
                    department = None  # Hoặc xử lý theo cách khác

                # Cập nhập hoặc tạo bản ghi
                computer, created = Computer.objects.update_or_create(
                    mac_address=mac,
                    defaults={
                        'department': department
                    }
                )

                # Nếu bản ghi được tạo, gán name bằng id của bản ghi
                if created:
                    computer.name = "Máy" + str(computer.id)
                    computer.description="Trường ĐHBK-ĐHĐN"  
                    computer.save()  # Lưu thay đổi
                # print(f"IP: {ip}, MAC: {mac}")
            time.sleep(30)

    def edit_computer_info(self,data):
        from .models import Computer
        try:
            computer = Computer.objects.get(mac_address=data['mac_address'])
            computer.name = data['name']
            computer.description = data['description']
            computer.save()
            return "Thông tin máy đã được cập nhật"
        except Computer.DoesNotExist:
            return "Máy không tồn tại"

    # Hàm nhận và lưu ảnh từ client
    def receive_image(self, conn, addr):
        # filename = f"{addr[0]}_screenshot.png"
        filename = f"screenshot-{addr[0]}.png"
        filepath = os.path.join(self.SAVE_PATH, filename)

        # Nhận kích thước ảnh (4 byte)
        image_size_bytes = conn.recv(4)
        image_size = int.from_bytes(image_size_bytes, 'big')

        # Nhận dữ liệu ảnh
        received_data = b''
        while len(received_data) < image_size:
            packet = conn.recv(self.BUFFER_SIZE)
            if not packet:
                break
            received_data += packet

        # Lưu ảnh vào file
        with open(filepath, "wb") as f:
            f.write(received_data)

        # print(f"[*] Đã nhận ảnh và lưu vào '{filename}'")

    # Hàm nhận và hiển thị tin nhắn từ client
    def receive_message(self, conn):
        # Nhận kích thước tin nhắn (4 byte)
        msg_size_bytes = conn.recv(4)
        msg_size = int.from_bytes(msg_size_bytes, 'big')

        # Nhận tin nhắn
        message = conn.recv(msg_size).decode()
        # print(f"[*] Nhận tin nhắn từ client: {message}")

    # Hàm nhận danh sách tin nhắn giữa client và server
    async def receive_list_chat(self, conn, addr):
        with self.lock:
            # Nhận kích thước của dữ liệu JSON
            list_size_bytes = conn.recv(4) 
            list_size = int.from_bytes(list_size_bytes, 'big')

            # Nhận danh sách tin nhắn từ JSON
            receive_data = conn.recv(list_size)
            self.chat_list = json.loads(receive_data.decode('utf-8'))
            # print(f"[*] Danh sách chat với client {addr}: ")
            # print(self.chat_list)
            if (self.adminCWS and addr[0] == self.clientCWSIP and self.currentWSRole == "admin"):
                print("gửi tất cả tín nhắn cho admin")
                await self.send_messages_to_admin(addr[0])
                await self.adminCWS.send(json.dumps(["cmd","done"]))
            elif (addr[0] in self.clientWSs and self.currentWSRole == "client"): 
                print("gửi tất cả tín nhắn cho client")
                await self.send_messages_to_client(addr[0])
                await self.clientWSs[addr[0]].send(json.dumps(["cmd","done"]))
            # if addr[0] in self.chat_received_event:
            #     self.chat_received_event[addr[0]].set()
            #     print("done")
            

    # Hàm xử lý client kết nối
    def handle_client(self, conn, addr):
        try:
            with self.lock:
                client_id = addr[0]
                self.clientSs[client_id] = conn
                self.client_screenshot_request[client_id] = False  # Chưa có yêu cầu gửi ảnh
            
            while not self.shutdown_event.is_set():
                try:
                    # Nhận loại dữ liệu (3 byte)
                    data_type = conn.recv(3)  # Nhận trực tiếp dưới dạng byte
                    
                    if data_type == b'img':
                        self.receive_image(conn, addr)
                    elif data_type == b'msg':
                        self.receive_message(conn)
                    elif data_type == b'cve':
                        asyncio.run(self.receive_list_chat(conn, addr))
                    elif data_type == b'clo':
                        # print(f"Client {client_id} đóng kết nối")
                        break
                    else:
                        pass # print(f"Không xác định loại dữ liệu từ client {client_id}")
                        
                
                except Exception as e:
                    # print(f"Lỗi khi xử lý client {client_id}: {e}")
                    break
        except Exception as e:
            print(f"Lỗi khi xử lý client {client_id}: {e}")

        finally:
            with self.lock:
                print("Xóa socket: " + str(socket))
                del self.clientSs[client_id]
                del self.client_screenshot_request[client_id]
            conn.close()

    # Hàm gửi tin nhắn đến một client chỉ định
    def send_to_client(self, client_id, message):
        if client_id in self.clientSs:
            print (message)
            self.clientSs[client_id].sendall(message.encode())
        else:
            pass # print(f"Client {client_id} không kết nối")
            

    # Hàm yêu cầu client gửi ảnh liên tục mỗi 5 giây
    def request_screenshot_from_client(self, client_id):
        print("Requesting screenshot"+client_id)
        if not client_id :
            for key in self.clientSs.keys():
                if (not self.client_screenshot_request[key]):
                    self.send_to_client(key, "START_SCREENSHOT\n")
                    self.client_screenshot_request[key] = True
        else :
            if client_id in self.clientSs:
                if (not self.client_screenshot_request[client_id]):
                    self.send_to_client(client_id, "START_SCREENSHOT\n")
                    self.client_screenshot_request[client_id] = True
                    # print(f"Yêu cầu client {client_id} gửi ảnh màn hình mỗi 5 giây.")
            else:
                pass # print(f"Client {client_id} không kết nối")
           

    # Hàm dừng yêu cầu ảnh từ một client
    def stop_screenshot_from_client(self, client_id):
        print("Requestings stop screenshot"+client_id)
        if not client_id :
            for key in self.clientSs.keys():
                if (self.client_screenshot_request[key]):
                    self.send_to_client(key, "STOP_SCREENSHOT\n")
                    self.client_screenshot_request[key] = False
        else :
            if client_id in self.clientSs:
                if (self.client_screenshot_request[client_id]):
                    self.send_to_client(client_id, "STOP_SCREENSHOT\n")
                    self.client_screenshot_request[client_id] = False
                    # print(f"Đã dừng yêu cầu client {client_id} gửi ảnh màn hình.")
            else:
                pass # print(f"Client {client_id} không kết nối")

    # Hàm yêu cầu client gửi danh sách tin nhắn giữa client và server
    async def request_show_chat(self, client_id):
            if client_id in self.clientSs:
                self.send_to_client(client_id, "SEND_CONVERSATION\n")
                # print(f"Đã gửi yêu cầu show conversation cho client {client_id}")
            else:
                if (self.adminCWS and client_id == self.clientCWSIP and self.currentWSRole == "admin"):
                    await self.adminCWS.send(json.dumps(["cmd","done"]))
                elif (client_id in self.clientWSs and self.currentWSRole == "client"):
                    await self.clientWSs[client_id].send(json.dumps(["cmd","done"]))
    
    def generate_subnets(self,start_ip):
        # Tạo một đối tượng mạng IPv4 từ địa chỉ IP bắt đầu
        network = ipaddress.ip_network(start_ip)
        
        # Danh sách để lưu trữ các subnet đã tạo
        subnets = []
        
        # Tạo các subnet
        for i in range(15):
            # Tính toán subnet tiếp theo bằng cách cộng i * 64 (kích thước của /26)
            new_subnet = network.network_address + (i * 64)
            subnets.append(str(ipaddress.ip_network(f"{new_subnet}/26")))  # Thêm subnet vào danh sách
            
        network = ipaddress.ip_network(subnets[-1].split('/')[0])
        del subnets[-1] # Xoá phần tử không cần thiết
        for i in range(8):
            # Tính toán subnet tiếp theo bằng cách cộng i * 16 (kích thước của /28)
            new_subnet = network.network_address + (i * 16)
            subnets.append(str(ipaddress.ip_network(f"{new_subnet}/28")))  # Thêm subnet vào danh sách
        return subnets  # Trả về danh sách các subnet

    # Hàm khởi tạo giá trị subnet cho department
    def set_department_subnet(self, network_add):
        from .models import Department, Computer
        self.subnet_list  = self.generate_subnets(network_add)
        lis = ["CN Nhiệt - Điện lạnh", "CN Thông tin", "Cơ khí", "Cơ khí giao thông", "Điện", "Điện tử viễn thông", "Hoá", "KH CN Tiên tiến","Kiến trúc",
               "Môi trường", "Quản lý Dự án", "XD Cầu - Đường", "XD Công trình thuỷ", "XD Dân dụng & Công nghiệp", "Phòng Tổ chức - Hành chính", "Phòng KHCN & Hợp tác Quốc tế",
               "Phòng công tác sinh viên", "Phòng Cơ sở vật chất", "Phòng Đào tạo", "Phòng Khảo thí và Đảm bảo chất lượng giáo dục", "Phòng Kế hoạch - Tài chính", "Phòng Thanh tra - Pháp chế"]
        for i in range(len(lis)):
            Department.objects.update_or_create(
                pk = i +1, # Vì id trong CSDL bắt đầu = 1, list bắt đầu = 0
                defaults = {
                    'name': lis[i],
                    'subnet': self.subnet_list[i]
                })
            
    # Hàm lấy subnet mask từ địa chỉ IP
    def get_subnet_mask(self, ip_address):
        interfaces = ni.interfaces()
        for interface in interfaces:
            addrs = ni.ifaddresses(interface)
            if ni.AF_INET in addrs:
                for link in addrs[ni.AF_INET]:
                    if link['addr'] == ip_address:
                        return link['netmask']
        return None

    # Hàm tính địa chỉ mạng từ IP và subnet mask
    def get_network_address(self, ip):
        netmask = self.get_subnet_mask(ip)
        # Chuyển IP và subnet mask thành đối tượng mạng (network)
        network = ipaddress.IPv4Network(f'{ip}/{netmask}', strict=False)
        return network.network_address
    
    # Hàm thêm thông báo mới đến từ Client đến Server
    def addNotification(self,clientID) :
        if clientID in self.notification_list :
            numOfMessages = self.notification_list[clientID]
            self.notification_list.pop(clientID)
            self.notification_list[clientID] = numOfMessages + 1
        else :
            self.notification_list[clientID] = 1 
    # Hàm chính cho server
    def start_server(self):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.HOST, self.PORT))
            server_socket.listen(5)
            # print(f"Server đang lắng nghe trên {self.HOST}:{self.PORT}")
            
            # Lấy địa chỉ mạng từ IP và subnet mask
            network_address = str(self.get_network_address(self.HOST))
            
            #Khởi tạo giá trị cho subnet của từng Department trong cơ sở dữ liệu
            self.set_department_subnet(network_address)
            network_address += "/22"
            # Tạo luồng quét IP
            threading.Thread(target=self.scan_ips, args=(network_address,), daemon=True).start()

            while not self.shutdown_event.is_set():
                try:
                    #server_socket.settimeout(3)
                    conn, addr = server_socket.accept()
                    threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()
                except socket.timeout:
                    continue
        finally:
            server_socket.close()
            print("Server đã đóng kết nối.")

    # WebSocket handler
    async def websocket_handler(self, websocket, path):
       # Nhận dữ liệu từ WebSocket
        message = await websocket.recv()
        print(f"Client {message} đã kết nối.")
        # Tách role và client_id từ chuỗi
        role, client_id = message.split('-')

        self.initialize_chat_event(client_id)

        # Nếu là admin, gán WebSocket cho adminCWS và xác định client đang nhắn tin
        if role == 'admin':
            self.adminCWS = websocket
            self.clientCWSIP = client_id
            self.clientCWS = self.clientWSs.get(client_id)
            self.currentWSRole = "admin"
            
            await self.adminCWS.send(json.dumps(["cmd","loading"]))
            
            # Gửi yêu cầu lấy toàn bộ tin nhắn từ client backend
            await self.request_show_chat(client_id)

            
            # # Đợi cho đến khi đã cập nhật xong chat_list
            # await self.chat_received_event[client_id].wait()

            # await self.adminCWS.send(json.dumps(["cmd","done"]))

            # # Nhận lại tin nhắn từ client backend và gửi cho admin
            # await self.send_messages_to_admin(client_id)

        # Nếu là client, gán WebSocket cho clientWSs[client_id] và gửi tin nhắn tới client
        elif role == 'client':
            self.clientWSs[client_id] = websocket
            if (client_id == self.clientCWSIP):
                self.clientCWS = websocket 
            self.currentWSRole = "client"
            
            await self.clientWSs[client_id].send(json.dumps(["cmd","loading"]))

            # Gửi yêu cầu lấy toàn bộ tin nhắn từ client backend
            await self.request_show_chat(client_id)
            # await websocket.send(json.dumps(["cmd","loading"]))
            # # Đợi cho đến khi đã cập nhật xong chat_list
            # await self.chat_received_event[client_id].wait()

            # await websocket.send(json.dumps(["cmd","done"]))


            # # Nhận tin nhắn từ client backend và gửi cho client WebSocket
            # await self.send_messages_to_client(client_id)

        # Lặp để nhận tin nhắn từ admin hoặc client
        try:
            while True:
                message = await websocket.recv()
                # Nếu là admin đang gửi tin nhắn cho client
                if websocket == self.adminCWS:
                    if self.clientCWS:
                        sendMessage = message.split("\n",1)
                        await self.clientCWS.send(sendMessage[0])
                    self.send_to_client(client_id, message)
                    
                    # if client_id in ServerManager.get_instance().clientSs:
                    #     ServerManager.get_instance().clientSs[client_id].sendall(message.encode())

                # Nếu là client đang gửi tin nhắn
                elif websocket == self.clientCWS:
                    if self.adminCWS:
                        sendMessage = message.split("\n",1)
                        await self.adminCWS.send(sendMessage[0])
                    self.send_to_client(client_id, message)
                
                elif client_id in self.clientSs:
                    self.send_to_client(client_id, message)
                    self.addNotification(client_id)

                    # if client_id in ServerManager.get_instance().clientSs:
                    #     ServerManager.get_instance().clientSs[client_id].sendall(message.encode())
        except:
            self.chat_received_event.pop(client_id, None)
            if (role == "admin") :
                print("Admin đã ngắt kết nối WS")
                self.adminCWS = None
                self.clientCWS = None
                self.clientCWSIP = None
            elif (role == "client"):
                print(f"Client {client_id} đã ngắt kết nối WS")
                self.clientWSs.pop(client_id)
                if client_id == self.clientCWSIP:
                    self.clientCWS = None

        

    # Gửi toàn bộ tin nhắn từ client backend tới admin
    async def send_messages_to_admin(self, client_id):
        # client_socket = self.clientSs.get(client_id)
        # if client_socket:
        #     data = client_socket.recv(1024)
        #     messages = data.decode('utf-8')
            # if self.adminCWS:
            #     await self.adminCWS.send(json.dumps({"client_id": client_id, "messages": messages}))
        if self.adminCWS:
            await self.adminCWS.send(json.dumps(self.chat_list))

    # Gửi toàn bộ tin nhắn từ client backend tới client WebSocket
    async def send_messages_to_client(self, client_id):
        # client_socket = ServerManager.get_instance().clientSs.get(client_id)
        # if client_socket:
        #     data = client_socket.recv(1024)
        #     messages = data.decode('utf-8')
        #     if self.clientWSs.get(client_id):
        #         await self.clientWSs[client_id].send(json.dumps({"messages": messages}))
        if self.clientWSs.get(client_id):
            await self.clientWSs[client_id].send(json.dumps(self.chat_list))


    # Khởi động server WebSocket
    async def start_websocket_server(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT_WS))

        # Chuyển socket này cho websockets serve
        server_socket.listen(5)
        
        async with websockets.serve(self.websocket_handler, sock=server_socket):
            await asyncio.Future()  # Chạy mãi mãi

    def start_ws_server(self):
        try:
            asyncio.run(self.start_websocket_server())
        except OSError as e:
            print(f"Lỗi: {e}")
            if e.errno == 10048:
                print("Cổng đã được sử dụng hoặc bị khóa.")

#     def printclientSs(self):
#         print("ClientSs:")
#         for client_id, client_socket in self.clientSs.items():
#             print(f"Client {client_id}: {client_socket}")
# if __name__ == "__main__":
#     server_manager = ServerManager()

#     try:
#         while not server_manager.shutdown_event.is_set():
#             action = input("Nhập 'start', 'stop', 'msg' hoặc 'show_chat' để thực hiện hành động: ").lower()
#             if action in ['start', 'stop', 'msg', 'show_chat','client']:
#                 target_client = input("Nhập IP client để gửi yêu cầu:")
                
#                 if action == 'start':  # Bắt đầu yêu cầu một client nào đó gửi hình ảnh
#                     server_manager.request_screenshot_from_client(target_client)
#                 elif action == 'stop':  # Dừng việc yêu cầu một client nào đó gửi hình ảnh
#                     server_manager.stop_screenshot_from_client(target_client)
#                 elif action == 'msg':  # Gửi tin nhắn đến cho client
#                     message = input("Nhập tin nhắn để gửi: ")
#                     server_manager.send_to_client(target_client, message)
#                 elif action == 'show_chat':  # Gửi yêu cầu cho client và nhận lại danh sách tin nhắn giữa server và client được chỉ định
#                     server_manager.request_show_chat(target_client)
#                 elif action == "client":
#                     server_manager.printclientSs()
#             elif action == 'exit':
#                 server_manager.shutdown_event.set()  # Đặt cờ để báo hiệu dừng
#                 break
#             else:
#                 pass # print("Hành động không hợp lệ. Vui lòng nhập 'start', 'stop', 'msg', hoặc 'exit'.")

#     except KeyboardInterrupt:
#         server_manager.shutdown_event.set()  # Khi nhấn Ctrl+C, dừng server an toàn