# Travel-Lung-Tung
# MỤC TIÊU cho Version 0.1.0
## XÂY DỰNG CHO CHATBOT TRẢ LỜI TƯ VẤN VÀ WEB/APP THỰC HIỆN ĐƯỢC CHỨC NĂNG CƠ BẢN CỦA MỘT ỨNG DỤNG BOOKING.
# Quy định:
## Các file/folder hỏi trước khi chỉnh sửa và xóa (edit and delete):

1. File nằm trong thư mục base.
2. File nằm trong thư mục scerets
3. main.py tổng và main.py trong thư mục test
4. Thư mục database

## Các file/folder được thêm (add):

1. .env
2. Thư mục secrets
3. Tất cả file không nằm danh sách "phải hỏi" 

# TODO
## 1. Cào dữ liệu
### 1.1. Cào dữ liệu bằng Agent
### 1.2. Cào dữ liệu bằng parse html/pdf thủ công
### 1.3. Nén dữ liệu đã được cào

## 2. Tiền xử lý dữ liệu
### 2.1. Nén tài liệu và chuyển đổi thành dữ liệu dạng vector
### 2.2. Chiết xuất Thực Thể (Entity)
### 2.3. Trích xuất mối quan hệ của các thực thể

## 3. Database
### 3.1. Xây dựng Vector Database
### 3.2. Xây dựng Bussiness Database
### 3.3. Xây dựng knowledge graph database

## 4. Agent
### 4.1. Retriver để lấy dữ liệu từ vector và knowledge graph database
### 4.2. Xây dựng MCP cho agent tương tác với các công cụ: booking, thanh toán, form,...
### 4.3. Xây dựng agent điều phối và trả lời câu hỏi
