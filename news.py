import sys
import os
import re
import html
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

TZ = timezone(timedelta(hours=7))
WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
STATE_FILE = "seen_news.json"

WEBHOOK = os.getenv("DISCORD_WEBHOOK")
if not WEBHOOK and os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("DISCORD_WEBHOOK="):
                WEBHOOK = line.split("=", 1)[1].strip().strip('"').strip("'")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

FEEDS = [
    {
        "source": "VnExpress",
        "category": "Tin Mới Nhất",
        "url": "https://vnexpress.net/rss/tin-moi-nhat.rss",
        "color": 0x9B59B6 # Tím đỏ VnExpress
    },
    {
        "source": "VnExpress",
        "category": "Thời sự",
        "url": "https://vnexpress.net/rss/thoi-su.rss",
        "color": 0x9B59B6
    },
    {
        "source": "Báo Tuổi Trẻ",
        "category": "Tin Mới Nhất",
        "url": "https://tuoitre.vn/rss/tin-moi-nhat.rss",
        "color": 0x2980B9 # Xanh dương Tuổi Trẻ
    },
    {
        "source": "Báo Tuổi Trẻ",
        "category": "Thời sự",
        "url": "https://tuoitre.vn/rss/thoi-su.rss",
        "color": 0x2980B9
    },
    {
        "source": "Báo Thanh Niên",
        "category": "Thời sự 24h",
        "url": "https://thanhnien.vn/rss/home.rss",
        "color": 0x27AE60 # Xanh lá Thanh Niên
    }
]

def clean_html(raw_html):
    if not raw_html:
        return ""
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', raw_html)
    # Unescape HTML entities
    text = html.unescape(text)
    # Collapse multiple whitespaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_image(raw_description, enclosure_url=None):
    if enclosure_url and enclosure_url.startswith("http"):
        return enclosure_url
    if raw_description:
        m = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', raw_description, re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def fetch_feed(feed_config):
    articles = []
    source = feed_config["source"]
    category = feed_config["category"]
    color = feed_config["color"]
    url = feed_config["url"]

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        
        # Parse XML
        root = ET.fromstring(r.content)
        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item"):
            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            raw_desc = item.findtext("description") or ""
            pub_date = item.findtext("pubDate") or ""
            
            enclosure = item.find("enclosure")
            enclosure_url = enclosure.get("url") if enclosure is not None else None

            # Clean fields
            clean_title = clean_html(title)
            summary = clean_html(raw_desc)
            image_url = extract_image(raw_desc, enclosure_url)

            if not clean_title or not link:
                continue

            # Bỏ qua các tin quảng cáo / rao vặt nếu có
            if "quảng cáo" in clean_title.lower() or "tài trợ" in clean_title.lower():
                continue

            articles.append({
                "title": clean_title,
                "link": link.strip(),
                "summary": summary[:300] + ("..." if len(summary) > 300 else ""),
                "image": image_url,
                "source": source,
                "category": category,
                "color": color,
                "pub_date": pub_date
            })
    except Exception as e:
        print(f"[!] Lỗi đọc RSS {source}: {e}")

    return articles

def fetch_all_news():
    all_articles = []
    seen_links = set()
    for f in FEEDS:
        items = fetch_feed(f)
        for it in items:
            if it["link"] not in seen_links:
                seen_links.add(it["link"])
                all_articles.append(it)
    return all_articles

def load_seen():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
                elif isinstance(data, dict):
                    return set(data.get("seen", []))
        except Exception as e:
            print(f"[!] Lỗi đọc state: {e}")
    return set()

def save_seen(seen_set):
    try:
        # Giữ tối đa 500 link gần nhất để file luôn nhẹ
        latest_500 = list(seen_set)[-500:]
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(latest_500, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi lưu state: {e}")

def create_article_embed(art, now):
    embed = {
        "title": f"📰 {art['title']}",
        "url": art["link"],
        "description": (
            f"{art['summary']}\n\n"
            f"[👉 **Bấm vào đây để đọc bài viết chi tiết tại {art['source']}**]({art['link']})"
        ),
        "color": art["color"],
        "footer": {
            "text": f"{art['source']} • Cập nhật tự động 24/7"
        },
        "timestamp": now.isoformat()
    }
    if art.get("image"):
        embed["image"] = {"url": art["image"]}
    return embed

def send_discord(content, embeds):
    if not WEBHOOK:
        print("[!] Lỗi: Chưa cấu hình DISCORD_WEBHOOK!")
        return False
    payload = {"content": content, "embeds": embeds}
    r = requests.post(WEBHOOK, json=payload, timeout=20)
    r.raise_for_status()
    print("[+] Đã gửi tin tức thành công vào Discord!")
    return True

def main(mode="check"):
    now = datetime.now(TZ)
    thu = WEEKDAYS[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")
    time_str = now.strftime("%H:%M")
    ts = int(now.timestamp())

    print(f"[*] Bắt đầu phiên quét tin tức thời sự [{mode}] lúc {time_str} ({thu}, {date_str})...")

    all_news = fetch_all_news()
    print(f"[*] Thu thập được {len(all_news)} tin tức mới nhất từ các nguồn báo chí.")

    seen = load_seen()

    if mode == "test":
        if all_news:
            sample = all_news[0]
            content = (
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 **THỬ NGHIỆM HỆ THỐNG TIN TỨC THỜI SỰ 24H**\n"
                f"⏰ *Phát sóng lúc: {time_str} ({thu}, {date_str})* • <t:{ts}:R>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            embed = create_article_embed(sample, now)
            send_discord(content, [embed])
        else:
            print("[!] Không có tin tức nào để test.")
        return

    if mode == "init":
        for a in all_news:
            seen.add(a["link"])
        save_seen(seen)
        print(f"[+] Đã khởi tạo {len(seen)} tin tức cũ vào bộ nhớ. Hệ thống sẽ bắt đầu gửi tin MỚI từ lần quét sau.")
        return

    # Chế độ check
    if not seen:
        # Lần đầu chạy chưa có file nhớ: lưu toàn bộ tin cũ, gửi 1 tin nóng nhất làm bài khai trương
        for a in all_news:
            seen.add(a["link"])
        save_seen(seen)
        print(f"[+] Lần đầu khởi chạy: Đã nạp {len(seen)} tin tức vào bộ nhớ. Gửi 1 tin nóng nhất khai trương kênh...")
        if all_news:
            top_art = all_news[0]
            content = (
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 **BẢN TIN THỜI SỰ NÓNG 24H • CHÍNH THỨC HOẠT ĐỘNG**\n"
                f"⏰ *Cập nhật lúc: {time_str} ({thu}, {date_str})* • <t:{ts}:R>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            embed = create_article_embed(top_art, now)
            send_discord(content, [embed])
        return

    # Tìm các bài báo mới tinh chưa từng gửi
    new_articles = [a for a in all_news if a["link"] not in seen]

    if new_articles:
        print(f"[!] PHÁT HIỆN {len(new_articles)} BÀI BÁO THỜI SỰ MỚI TINH! ĐĂNG TOÀN BỘ NGAY LẬP TỨC...")
        # Đăng toàn bộ không giới hạn, chia thành các đợt tối đa 5 embeds/tin nhắn để không vượt trần ký tự Discord
        chunk_size = 5
        for i in range(0, len(new_articles), chunk_size):
            batch = new_articles[i:i + chunk_size]
            embeds = [create_article_embed(a, now) for a in batch]

            content = (
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔴 **BẢN TIN THỜI SỰ NÓNG 24H • CẬP NHẬT MỚI ({len(new_articles)} TIN)**\n"
                f"⏰ *Ghi nhận lúc: {time_str} ({thu}, {date_str})* • <t:{ts}:R>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ) if i == 0 else ""

            send_discord(content, embeds)
            time.sleep(1)

        for a in new_articles:
            seen.add(a["link"])
        save_seen(seen)
    else:
        print(f"[*] Không có tin tức mới nào ({len(seen)} tin đã theo dõi). Giữ im lặng.")

if __name__ == "__main__":
    run_mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    main(run_mode)
