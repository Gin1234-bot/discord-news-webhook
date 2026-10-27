# Discord Breaking News 24/7 Webhook 📰

Hệ thống tự động cập nhật tin tức thời sự nóng hổi 24/7 từ các cơ quan báo chí uy tín hàng đầu Việt Nam (VnExpress & Báo Tuổi Trẻ Online) vào Discord qua Webhook.

## ✨ Tính năng nổi bật
- **Nguồn cấp tin đa dạng & chính thống:** VnExpress & Tuổi Trẻ RSS feeds thời gian thực.
- **Tự động bóc tách đa phương tiện:** Trích xuất ảnh bìa HD của từng bài báo chèn thẳng vào Discord Embed.
- **Tóm tắt thông minh:** Trích xuất nội dung cốt lõi súc tích 2-3 câu kèm link đọc bài gốc.
- **Chống spam & Dedup:** Cơ chế lưu vết `seen_news.json` đảm bảo không bao giờ đăng trùng bài cũ, giới hạn tối đa 3 bài/lần quét.
- **Vận hành tự động:** Tự động chạy mỗi 10 phút trên GitHub Actions, miễn phí 100% vĩnh viễn.

## ⚙️ Cài đặt
1. Cấu hình Webhook Discord vào biến môi trường `DISCORD_WEBHOOK` (file `.env` hoặc GitHub Secrets).
2. Chạy `python news.py check` để quét và đăng tin.
