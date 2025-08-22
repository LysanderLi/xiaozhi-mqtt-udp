import request
from usr import uuid
import ujson as json
#'Host': 'api.tenclass.net'
#POST /xiaozhi/ota/ HTTP/1.1

uuid = str(uuid.uuid4())
print(uuid)
head = {
'Content-Type': 'application/json',
'User-Agent': 'xioazhi-box-2/1.0.1',
'Device-Id': '64:e8:33:48:ec:c0',
'Client-Id': uuid
}

data = {
  "application": {
    "version": "1.0.1",
    "elf_sha256": "c8a8ecb6d6fbcda682494d9675cd1ead240ecf38bdde75282a42365a0e396033"
  },
  "board": {
    "type": "xioazhi-box",
    "name": "xioazhi-box-2",
    "carrier": "CHINA UNICOM",
    "csq": "22",
    "imei": "****",
    "iccid": "89860125801125426850"
  }
}

url = "https://api.tenclass.net/xiaozhi/ota/"

response = request.post(url,data =json.dumps(data),headers=head)
response = response.json()
print(response)



# # POST /xiaozhi/ota/ HTTP/1.1
# header ={
# 'Content-Type': 'application/json',
# 'User-Agent': 'kevin-box-2/1.0.1',
# 'Device-Id': '11:22:33:44:55:66',
# 'Client-Id': '7b94d69a-9808-4c59-9c9b-704333b38aff'
# }

# data ={
#   "application": {
#     "version": "1.0.1",
#     "elf_sha256": "c8a8ecb6d6fbcda682494d9675cd1ead240ecf38bdde75282a42365a0e396033"
#   },
#   "board": {
#     "type": "kevin-box",
#     "name": "kevin-box-2",
#     "revision": "ML307R-DL-MBRH0S00",
#     "carrier": "CHINA MOBILE",
#     "csq": "22",
#     "imei": "****",
#     "iccid": "****"
#   }
# }
# print(json.dumps(data))
# url = "https://api.tenclass.net"

# response = request.post(url,data =json.dumps(data),headers=header)
# ret = response.json()
# print(ret)

# # for i in response.text:
# #     print(i)