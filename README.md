# Sổ Tính

Ứng dụng tính tiền tin nhắn và tự dò kết quả xổ số miền Trung, miền Bắc.

## Chạy web

Cần Python 3.10 trở lên, không cần cài thư viện:

```powershell
python server.py
```

Mở **http://127.0.0.1:5173/**. Có thể chọn cổng khác bằng `python server.py --port 5174`.

Phải dùng `server.py` cho tính năng lấy kết quả. Mở trực tiếp HTML hoặc chạy `python -m http.server` vẫn dùng được phần tính tiền và nhập trúng tay, nhưng không có API kết quả.

## Tự dò trúng

- Chọn miền ở đầu trang và ngày mở thưởng. Miền Trung tự chọn đúng một đài theo ngày: thứ 2 Phú Yên, thứ 3 Đắk Lắk, thứ 4 Khánh Hòa, thứ 5 Bình Định, thứ 6 Gia Lai, thứ 7 Quảng Ngãi, chủ nhật Khánh Hòa. API bỏ kết quả các đài khác và giao diện không hiển thị nút chọn đài dư. Miền Bắc có một bảng chung.
- Bật **Tự cập nhật mỗi phút**, nhập tin nhắn, bấm **Tính Toán**. Khi đủ kết quả, các ô trúng tự điền và tổng tiền tự cập nhật. Web kiểm tra lại mỗi phút trong lúc trang đang mở.
- Theo giờ Việt Nam, **miền Trung từ 17:15**, **miền Bắc từ 18:15** mới được chọn ngày hôm nay. Trước giờ đó, lịch chỉ cho chọn đến hôm qua và mặc định mở ngày gần nhất được phép. Vẫn dò được các ngày cũ. Đến đúng giờ, hôm nay tự được mở chọn, không cần tải lại trang; nếu đang theo dõi ngày gần nhất, web tự chuyển sang hôm nay. Nếu đã chọn một ngày cũ khác, web giữ ngày đó. API cũng khóa hôm nay trước mốc giờ, không lấy cả dữ liệu cache hoặc dữ liệu nguồn về sớm.
- Ngày luôn hiển thị và được nhập theo **ngày/tháng/năm**. Danh sách đài là lịch mở thưởng, không có nghĩa đã có kết quả. Khi chưa có đủ giải, nút dò bị khóa; **Kiểm tra cập nhật** chỉ kiểm tra lại nguồn, không tạo số trúng.
- Nguồn: [RSS Xổ Số Đại Phát](https://xosodaiphat.com/rss.html), hỗ trợ 7 kỳ gần nhất. Giao diện hiển thị ngày, đài, nguồn, thời gian lấy và bảng kết quả để đối chiếu. Chưa có kết quả, thiếu giải, thiếu đài hoặc mất kết nối đều không được coi là thua; không lấy kết quả hôm qua thay cho hôm nay.
- Chỉ lấy dữ liệu kết quả công khai từ nguồn. Nội dung tin nhắn và số tiền được xử lý tại trình duyệt, không gửi đến nguồn xổ số hay API.
- Các ô sửa tay (kể cả số 0) được giữ khi tính lại, cập nhật nguồn hoặc đổi miền. **Dò lại toàn bộ** thay tất cả bằng kết quả tự dò. **Bỏ trúng** xóa trúng và tắt tự dò. **Xóa Dữ Liệu** xóa tin nhắn cùng toàn bộ trúng, kể cả khi yêu cầu lấy kết quả đang chạy.

### Quy tắc đối chiếu

Luôn dò số cuối dãy: `53046` đối chiếu `46` khi dò 2 số và `046` khi dò 3 chân. Đầu và Đuôi dùng hai tập giải riêng:

| Mục | Miền Trung | Miền Bắc |
| --- | --- | --- |
| Đầu | 2 số cuối giải 8 | 2 số cuối của bốn số giải 7 |
| Đuôi | 2 số cuối giải đặc biệt | 2 số cuối giải đặc biệt |
| Lô | Đếm lượt 2 số cuối ở tất cả giải | Đếm lượt 2 số cuối ở tất cả giải |
| 3 chân | Đếm lượt 3 số cuối, giữ số 0 đầu | Đếm lượt 3 số cuối, giữ số 0 đầu |
| Đá | Các số của cặp cùng xuất hiện trong một đài thì trúng 1 lần | Các số của cặp cùng xuất hiện thì trúng 1 lần |

Đá không nhân theo lượt lặp; không ghép số giữa hai đài. Cặp lặp cùng số cần ít nhất hai lượt xuất hiện. Chỉ dùng kết quả của đài được quy định cho ngày đang dò. Các mục 3 chân có hơn 3 chữ số được để nhập tay và có thông báo.

Lịch đài miền Trung trong `CENTRAL_STATIONS` của `server.py` quy định đài duy nhất được trả về và tự chọn theo ngày. Khi đài này có đủ giải, có thể dò ngay mà không phải chờ đài khác.

## Kiểm tra

```powershell
node --test test.mjs
python -m unittest -v test_server.py
```

`index.html` và `dist/index.html` phải đồng bộ. Font tiếng Việt đã nhúng sẵn, không cần tải từ bên ngoài.
