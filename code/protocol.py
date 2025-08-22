import modem
import ujson as json
from usr import uuid
import usocket as socket
from usr.threading import Thread, Condition,Event
from usr.logging import getLogger
import umqtt
import request
import ubinascii
import ustruct as struct
import utime
import ucryptolib 

logger = getLogger(__name__)

class JsonMessage(object):

    def __init__(self, kwargs):
        self.kwargs = kwargs
    
    def __str__(self):
        return str(self.kwargs)
    
    def to_bytes(self):
        return json.dumps(self.kwargs)
    
    @classmethod
    def from_bytes(cls, data):
        return cls(json.loads(data))

    def __getitem__(self, key):
        return self.kwargs[key]
    
    def __setitem__(self, key, value): 
        self.kwargs[key] = value

aes_opus_info = {
    "type": "hello",
    "version": 3,
    "transport": "udp",
    "udp": {
        "server": "120.24.160.13",
        "port": 8848,
        "encryption": "aes-128-ctr",
        "key": "263094c3aa28cb42f3965a1020cb21a7",
        "nonce": "01000000ccba9720b4bc268100000000"
    },
    "audio_params": {
        "format": "opus",
        "sample_rate": 16000,
        "channels": 1,
        "frame_duration": 100
    },
    "session_id": "b23ebfe9"
}

'''
OTA 返回的数据格式
{'websocket': {'url': 'wss://api.tenclass.net/xiaozhi/v1/', 'token': 'test-token'}, 
 'mqtt': {'endpoint': 'mqtt.xiaozhi.me', 'publish_topic': 'device-server', 
        'client_id': 'GID_test@@@64_e8_33_48_ec_c0@@@7c18371a-3594-4380-be56-f1e934f4f2fa', 
        'username': 'eyJpcCI6IjIyMC4yMDAuMTI2LjE5In0=', 'password': 'Kduh/1JI4ZyxmyPSDGs0UMvYXZQxw1+clxXl4YOAOFU=', 
        'subscribe_topic': 'null'}, 'server_time': {'timezone_offset': 480, 'timestamp': 1755139312182}, 
        'firmware': {'url': '', 'version': '1.0.1'}}
'''
class MqttClient(object):
    def __init__(self):
        self._host = 'mqtt.xiaozhi.me'
        self._port = 8883
        self._username = None
        self._password = None
        self.client_id = None 
        self._keepalive = 240
        self._pub_topic = None
        self._sub_topic = None
        self.udp_socket = None
        self._mqtt_recv = None
        self._udp_recv = None
        self.audio_encryptor = None
        self._running = False  # 添加线程运行标志
        self.udp_connect_event = Event()
        self.ota_get()

    def ota_get(self):
        cli_uuid = str(uuid.uuid4())
        head = {
            'Accept-Language': 'zh-CN',
            'Content-Type': 'application/json',
            'User-Agent': 'kevin-box-2/1.0.1',
            'Device-Id': '64:e8:33:48:ec:c0',
            'Client-Id': cli_uuid
        }
        ota_data = JsonMessage({
            "application": {
                "version": "1.0.1",
                "elf_sha256": "c8a8ecb6d6fbcda682494d9675cd1ead240ecf38bdde75282a42365a0e396033"
            },
            "board": {
                "type": "kevin-box",
                "name": "kevin-box-2",
                "carrier": "CHINA UNICOM",
                "csq": "22",
                "imei": "****",
                "iccid": "89860125801125427213"
            }
        })
        ota_url = "https://api.tenclass.net/xiaozhi/ota/"
        #通过OTA得到mqtt的连接参数
        response = request.post(ota_url,data =(ota_data.to_bytes()),headers=head)
        response = response.json()
        print(response)
        self._host = response["mqtt"]["endpoint"]
        self._username = response["mqtt"]["username"]
        self._password = response["mqtt"]["password"]
        self._pub_topic = response["mqtt"]["publish_topic"]
        self._sub_topic = "devices/p2p/#"
        self.client_id = response["mqtt"]["client_id"]
    def __str__(self):
        return "{}(host=\"{}\")".format(type(self).__name__, self._host)

    def __enter__(self):
        #self.connect()
        pass
    def is_state_ok(self):
        if self.cli.get_mqttsta() == 0 :
            return True
        return False
    def __exit__(self, *args, **kwargs):
        logger.debug("__exit__ result udp close")
        self.disconnect()
    def connect(self):
        hello_msg = JsonMessage({
            "type": "hello",
            "version": 3,
            "transport": "udp",
            "features": {
                "consistent_sample_rate": True
            },
            "audio_params": {
                "format": "opus",
                "sample_rate": 16000,
                "channels": 1,
                "frame_duration": 100
            }
        })
        try:
            self.cli = umqtt.MQTTClient(self.client_id, self._host, self._port, self._username, self._password, keepalive=self._keepalive,ssl=True)
            self.cli.set_callback(self.__handle_mqtt_message)
            logger.info("connecting to mqtt...")
            self._running = True  
            self.cli.connect()
            if self.cli.get_mqttsta() == 0:  # 0表示连接成功
                self._mqtt_recv = Thread(target=self._mqtt_recv_thread)
                self._mqtt_recv.start(stack_size=16)
                self.cli.subscribe(self._sub_topic)
                utime.sleep(1)  # 确保订阅完成
                self.mqtt_send(hello_msg.to_bytes())            
            while not self.udp_connect_event.is_set():
                logger.debug("waitting for udp connection")
                utime.sleep(1)
            if self.udp_connect_event.is_set() :
                logger.debug("mqtt and udp connect success")
            else :
                logger.debug("mqtt and udp connect fail")     

        except Exception as e:
            logger.error("{} connect failed: {}".format(self, e))
            self.cli = None
            return False
        # else:
        #     setattr(self, "__client__", self.cli)

    def disconnect(self):
        self._running = False
        self.udp_connect_event.clear()
        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None
        if self.cli:
            self.cli.disconnect()
            self.cli = None
        # 确保线程完全退出后再清理
        if self._udp_recv:
            self._udp_recv.join()
            self._udp_recv = None
        if self._mqtt_recv:
            self._mqtt_recv.join()
            self._mqtt_recv = None
        else:
            logger.info("receive thread already closed")
    def mqtt_send(self, data):
        """send data to server"""
        #logger.info("send data:{} ".format(data))
        self.cli.publish(self._pub_topic,data)

    def udp_send(self, data):
        if self.audio_encryptor is None:
            self.audio_encryptor = AudioEncryptor(aes_opus_info["udp"]["key"], 
                                                aes_opus_info["udp"]["nonce"])

        encrypt_data = self.audio_encryptor.encrypt_packet(data)
        logger.debug("send data:{} ".format(encrypt_data))

        self.udp_socket.sendto(encrypt_data,(aes_opus_info["udp"]["server"],aes_opus_info["udp"]["port"]))
        
    def set_callback(self, audio_message_handler=None, json_message_handler=None):
        if audio_message_handler is not None and callable(audio_message_handler):
            self.__audio_message_handler = audio_message_handler
        else:
            raise TypeError("audio_message_handler must be callable")
        
        if json_message_handler is not None and callable(json_message_handler):
            self.__json_message_handler = json_message_handler
        else:
            raise TypeError("json_message_handler must be callable")
        
    @staticmethod
    def get_mac_address():
        # mac = str(uuid.UUID(int=int(modem.getDevImei())))[-12:]
        # return ":".join([mac[i:i + 2] for i in range(0, 12, 2)])
        return "64:e8:33:48:ec:c0"
    def __handle_mqtt_message(self,topic,msg):
        global aes_opus_info
        msg = JsonMessage.from_bytes(msg)
        logger.info("recv data: ", msg)
        if msg["type"] == "hello":
            #logger.info("recv hello msg: ", msg)
            aes_opus_info = msg
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,socket.IPPROTO_UDP)
            self.udp_socket.connect((aes_opus_info['udp']['server'], aes_opus_info['udp']['port']))
            self.udp_connect_event.set()
            self.udp_socket.settimeout(1)  # 设置0.1秒超时
            self._udp_recv = Thread(target=self._udp_recv_thread)
            self._udp_recv.start(stack_size=24)
        
        elif msg["type"] == "goodbye":
            logger.info("recv goodbye message")
            print(msg)
            aes_opus_info["session_id"] = None  # 清理会话标识
            self.disconnect()
        else:
            self.__handle_json_message(msg)
    def _mqtt_recv_thread(self):
        while self._running:
            try:
                self.cli.wait_msg()
            except Exception as e:
                if self._running:
                    logger.error("recv_thread error: ", e)
    def _udp_recv_thread(self):
        while self._running:
            try:
                raw = self.udp_socket.recv(1024)
                logger.info("udp recv: ", raw)
            except Exception as e:
                if self._running:
                    logger.info("{} recv thread break, Exception details: {}".format(self, repr(e)))
                    
                break
            
            if len(raw) < 16:
                raise ValueError("Invalid packet length")
            
            # 解密
            decrypted_payload = self.audio_encryptor.decrypt_packet(raw)
            
            # 处理解密后的Opus音频数据
            self.__handle_audio_message(decrypted_payload)
                

    def __handle_audio_message(self, raw):
        if self.__audio_message_handler is None:
            logger.warn("audio message handler is None, did you forget to set it?")
            return
        try:
            self.__audio_message_handler(raw)
        except Exception as e:
            logger.error("{} handle audio message failed, Exception details: {}".format(self, repr(e)))

    def __handle_json_message(self, msg):
        if self.__json_message_handler is None:
            logger.warn("json message handler is None, did you forget to set it?")
            return
        try:
            self.__json_message_handler(msg)
        except Exception as e:
            logger.debug("{} handle json message failed, Exception details: {}".format(self, repr(e)))

    def listen(self, state, mode="auto"):
            self.mqtt_send(
                JsonMessage(
                    {
                        "session_id": aes_opus_info["session_id"],  # 会话ID
                        "type": "listen",
                        "state": state,  # "start": 开始识别; "stop": 停止识别; "detect": 唤醒词检测
                        "mode": mode  # "auto": 自动停止; "manual": 手动停止; "realtime": 持续监听
                    }
                ).to_bytes()
            )
    
    def wakeword_detected(self, wakeword):
            self.mqtt_send(
                JsonMessage(
                    {
                        "session_id": aes_opus_info["session_id"],
                        "type": "listen",
                        "state": "detect",
                        "text": wakeword  # 唤醒词
                    }
                ).to_bytes()
            )
    
    def abort(self, reason=""):
            self.mqtt_send(
                JsonMessage(
                    {
                        "session_id": aes_opus_info["session_id"],
                        "type": "abort",
                        "reason": reason
                    }
                ).to_bytes()
            )
    
class AudioEncryptor:
    def __init__(self, key_hex, nonce_hex):
        self.key = ubinascii.unhexlify(key_hex)
        self.base_nonce = ubinascii.unhexlify(nonce_hex)  # 原始12字节nonce
        self.seq_num = 0

    def encrypt_packet(self, payload):
        """简化加密：整体加密+正确nonce结构"""
        logger.debug("Encrypt: seq={}, len={}".format(self.seq_num, len(payload)))
        # 1. 构造16字节新nonce (4字节base + 2字节长度 + 8字节base + 4字节序列号)
        new_nonce = (
            self.base_nonce[0:4] +
            struct.pack(">H", len(payload)) +
            self.base_nonce[4:12] +
            struct.pack(">I", self.seq_num)
        )
        
        # 2. 整体加密（非分块）
        logger.debug("准备加密数据...")
        aes = ucryptolib.aes(self.key, ucryptolib.MODE_CTR, new_nonce)
        encrypted = aes.encrypt(payload)
        logger.debug("加密完成...")
        # 3. 序列号递增（每个包只增一次）
        self.seq_num = (self.seq_num + 1) % (1 << 32)
        return new_nonce + encrypted

    def decrypt_packet(self, raw):
        """修正解密：前16字节=nonce，剩余=加密数据"""
        logger.debug("开始解密...")
        if len(raw) < 16:
            return None

        nonce = raw[:16]
        ciphertext = raw[16:]

        # 直接整体解密
        aes = ucryptolib.aes(self.key, ucryptolib.MODE_CTR, nonce)
        logger.debug("解密成功。。。")
        return aes.decrypt(ciphertext)  # CTR模式加密=解密




'''
class WebSocketClient(object):

    def __init__(self, host=WSS_HOST, debug=WSS_DEBUG):
        self.debug = debug
        self.host = host
        self.__resp_helper = RespHelper()
        self.__recv_thread = None
        self.__audio_message_handler = None
        self.__json_message_handler = None
        self.__last_text_value = None
    
    def __str__(self):
        return "{}(host=\"{}\")".format(type(self).__name__, self.host)

    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args, **kwargs):
        return self.disconnect()

    def set_callback(self, audio_message_handler=None, json_message_handler=None):
        if audio_message_handler is not None and callable(audio_message_handler):
            self.__audio_message_handler = audio_message_handler
        else:
            raise TypeError("audio_message_handler must be callable")
        
        if json_message_handler is not None and callable(json_message_handler):
            self.__json_message_handler = json_message_handler
        else:
            raise TypeError("json_message_handler must be callable")
        
    @staticmethod
    def get_mac_address():
        # mac = str(uuid.UUID(int=int(modem.getDevImei())))[-12:]
        # return ":".join([mac[i:i + 2] for i in range(0, 12, 2)])
        return "64:e8:33:48:ec:c0"

    @staticmethod
    def generate_uuid() -> str:
        return str(uuid.uuid4())

    @property
    def cli(self):
        __client__ = getattr(self, "__client__", None)
        if __client__ is None:
            raise RuntimeError("{} not connected".format(self))
        return __client__

    def is_state_ok(self):
        return self.cli.sock.getsocketsta() == 4
    
    def disconnect(self):
        """disconnect websocket"""
        __client__ = getattr(self, "__client__", None)
        if __client__ is not None:
            __client__.close()
            del self.__client__
        if self.__recv_thread is not None:
            self.__recv_thread.join()
            self.__recv_thread = None

    def connect(self):
        """connect websocket"""
        __client__ = ws.Client.connect(
            self.host, 
            headers={
                "Authorization": "Bearer {}".format(ACCESS_TOKEN),
                "Protocol-Version": PROTOCOL_VERSION,
                "Device-Id": self.get_mac_address(),
                "Client-Id": self.generate_uuid()
            }, 
            debug=self.debug
        )

        try:
            self.__recv_thread = Thread(target=self.__recv_thread_worker)
            self.__recv_thread.start(stack_size=16)
        except Exception as e:
            __client__.close()
            logger.error("{} connect failed, Exception details: {}".format(self, repr(e)))
        else:
            setattr(self, "__client__", __client__)
            return __client__

    def __recv_thread_worker(self):
        while True:
            try:
                raw = self.recv()
            except Exception as e:
                logger.info("{} recv thread break, Exception details: {}".format(self, repr(e)))
                break
            
            if raw is None or raw == "":
                logger.info("{} recv thread break, Exception details: read none bytes, websocket disconnect".format(self))
                break
            
            try:
                m = JsonMessage.from_bytes(raw)
            except Exception as e:
                self.__handle_audio_message(raw)
            else:
                if m["type"] == "hello":
                    with self.__resp_helper:
                        self.__resp_helper.put(m)
                else:
                    self.__handle_json_message(m)

    def __handle_audio_message(self, raw):
        if self.__audio_message_handler is None:
            logger.warn("audio message handler is None, did you forget to set it?")
            return
        try:
            self.__audio_message_handler(raw)
        except Exception as e:
            logger.error("{} handle audio message failed, Exception details: {}".format(self, repr(e)))
    
    def __handle_json_message(self, msg):
        if self.__json_message_handler is None:
            logger.warn("json message handler is None, did you forget to set it?")
            return
        try:
            self.__json_message_handler(msg)
        except Exception as e:
            logger.debug("{} handle json message failed, Exception details: {}".format(self, repr(e)))
            
    # def topic(text_value):
        
            
    def send(self, data):
        """send data to server"""
        # logger.debug("send data: ", data)
        self.cli.send(data)

    def recv(self):
        """receive data from server, return None or "" means disconnection"""
        data = self.cli.recv()
        return data



    def hello(self):
        req = JsonMessage(
            {
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 100
                },
                "features": {
                    "consistent_sample_rate": True
                }
            }
        )
        with self.__resp_helper:
            self.send(req.to_bytes())
            resp = self.__resp_helper.get(req, timeout=10)
            # {'transport': 'websocket', 'type': 'hello', 'session_id': 'd2091edb', 'audio_params': {'frame_duration': 60, 'channels': 1, 'format': 'opus', 'sample_rate': 24000}, 'version': 1}
            # logger.debug("hello resp: ", resp)
            return resp

    def listen(self, state, mode="auto", session_id=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,  # Websocket协议不返回 session_id，所以消息中的会话ID可设置为空
                        "type": "listen",
                        "state": state,  # "start": 开始识别; "stop": 停止识别; "detect": 唤醒词检测
                        "mode": mode  # "auto": 自动停止; "manual": 手动停止; "realtime": 持续监听
                    }
                ).to_bytes()
            )
    
    def wakeword_detected(self, wakeword, session_id=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "listen",
                        "state": "detect",
                        "text": wakeword  # 唤醒词
                    }
                ).to_bytes()
            )
    
    def abort(self, session_id="", reason=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "abort",
                        "reason": reason
                    }
                ).to_bytes()
            )

    def report_iot_descriptors(self, descriptors, session_id=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "iot",
                        "descriptors": descriptors
                    }
                ).to_bytes()
            )

    def report_iot_states(self, states, session_id=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "iot",
                        "states": states
                    }
                ).to_bytes()
            )

'''