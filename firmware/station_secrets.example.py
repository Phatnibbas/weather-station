"""MẪU — copy thành `station_secrets.py` rồi điền giá trị thật.

    cp firmware/station_secrets.example.py firmware/station_secrets.py

`station_secrets.py` nằm trong .gitignore và KHÔNG BAO GIỜ được commit.
File này (bản .example) thì được commit, nên tuyệt đối không điền key thật vào đây.

Phải upload HAI file lên board: firmware của trạm (đổi tên thành `main.py`)
và `station_secrets.py`. Thiếu file thứ hai thì trạm vẫn đọc cảm biến và hiện
LCD bình thường, nhưng không upload được — LCD sẽ hiện ký tự `?` ở góc.
"""

# --- Wi-Fi ------------------------------------------------------------------
WIFI_SSID = "TEN_WIFI_CUA_BAN"
WIFI_PASSWORD = "MAT_KHAU_WIFI"


# --- ThingSpeak Write API Key ----------------------------------------------
#
# Mỗi channel có key riêng. Firmware ưu tiên tên có hậu tố trạm, rồi mới tới
# tên chung bên dưới — nhờ vậy MỘT file này dùng được cho cả hai board mà không
# có đường nào nạp nhầm key của trạm kia.
#
# Nạp nhầm key thì ThingSpeak không báo lỗi rõ ràng, nó chỉ trả về "0". Đó là
# kiểu lỗi im lặng tốn nhiều thời gian nhất để truy ra, và với trạm đặt xa thì
# tốn cả một chuyến đi. Đừng dùng tên chung nếu có nhiều hơn một trạm.
#
# Lấy key tại: ThingSpeak -> Channels -> chọn channel -> API Keys -> Write API Key

THINGSPEAK_WRITE_API_KEY_BAOLOC = "WRITE_API_KEY_CUA_CHANNEL_3448221"
THINGSPEAK_WRITE_API_KEY_SAIGON = "WRITE_API_KEY_CUA_CHANNEL_3428136"

# Tên chung, chỉ dùng khi board chỉ chạy đúng một trạm và không muốn phân biệt.
THINGSPEAK_WRITE_API_KEY = "NHAP_WRITE_API_KEY"
