import sys
import os
import re
import html
import json
import time
import email.utils
import urllib.parse
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

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {"seen": set(data), "banner_date": ""}
                elif isinstance(data, dict):
                    return {
                        "seen": set(data.get("seen", [])),
                        "banner_date": data.get("banner_date", "")
                    }
        except Exception as e:
            print(f"[!] Lỗi đọc state: {e}")
    return {"seen": set(), "banner_date": ""}

def save_state(state):
    try:
        # Giữ tối đa 500 link gần nhất để file luôn nhẹ
        latest_500 = list(state["seen"])[-500:]
        payload = {
            "banner_date": state.get("banner_date", ""),
            "seen": latest_500
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi lưu state: {e}")

def parse_pub_date(pub_date_str):
    if not pub_date_str:
        return None
    pub_date_str = pub_date_str.strip()
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str)
        return dt.astimezone(TZ)
    except Exception:
        pass

    formats = [
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT%z",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(pub_date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            else:
                dt = dt.astimezone(TZ)
            return dt
        except Exception:
            pass
    return None

def create_article_embed(art, now):
    dt = parse_pub_date(art.get("pub_date"))
    if dt:
        time_display = f"⏰ **Đăng báo lúc:** `{dt.strftime('%H:%M - %d/%m/%Y')}` (<t:{int(dt.timestamp())}:R>)"
        embed_timestamp = dt.isoformat()
    else:
        time_display = f"⏰ **Ghi nhận lúc:** `{now.strftime('%H:%M - %d/%m/%Y')}`"
        embed_timestamp = now.isoformat()

    embed = {
        "title": f"📰 {art['title']}",
        "url": art["link"],
        "description": (
            f"{art['summary']}\n\n"
            f"{time_display}\n"
            f"[👉 **Bấm vào đây để đọc bài viết chi tiết tại {art['source']}**]({art['link']})"
        ),
        "color": art["color"],
        "footer": {
            "text": f"{art['source']} • Tin Thời Sự 24/7"
        },
        "timestamp": embed_timestamp
    }
    if art.get("image"):
        img_url = art["image"]
        if "vnecdn.net" in img_url:
            img_url = f"https://wsrv.nl/?url={urllib.parse.quote(img_url)}"
        embed["image"] = {"url": img_url}
    return embed

def send_discord(content, embeds):
    if not WEBHOOK:
        print("[!] Lỗi: Chưa cấu hình DISCORD_WEBHOOK!")
        return False
    payload = {"embeds": embeds}
    if content:
        payload["content"] = content
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
    today = now.strftime("%Y-%m-%d")

    print(f"[*] Bắt đầu phiên quét tin tức thời sự [{mode}] lúc {time_str} ({thu}, {date_str})...")

    all_news = fetch_all_news()
    print(f"[*] Thu thập được {len(all_news)} tin tức mới nhất từ các nguồn báo chí.")

    state = load_state()
    seen = state["seen"]

    if mode == "test":
        if all_news:
            sample = all_news[0]
            embed = create_article_embed(sample, now)
            # Theo yêu cầu: Chỉ gửi duy nhất card embed bài báo, không gửi kèm thanh banner ảnh 2
            send_discord("", [embed])
        else:
            print("[!] Không có tin tức nào để test.")
        return

    if mode == "init":
        for a in all_news:
            seen.add(a["link"])
        state["banner_date"] = today
        save_state(state)
        print(f"[+] Đã khởi tạo {len(seen)} tin tức cũ vào bộ nhớ. Hệ thống sẽ bắt đầu gửi tin MỚI từ lần quét sau.")
        return

    # Chế độ check
    if not seen:
        for a in all_news:
            seen.add(a["link"])
        state["banner_date"] = today
        save_state(state)
        print(f"[+] Lần đầu khởi chạy: Đã nạp {len(seen)} tin tức vào bộ nhớ. Gửi 1 tin nóng nhất khai trương kênh...")
        if all_news:
            top_art = all_news[0]
            embed = create_article_embed(top_art, now)
            send_discord("", [embed])
        return

    # Tìm các bài báo mới tinh chưa từng gửi
    new_articles = [a for a in all_news if a["link"] not in seen]

    if new_articles:
        print(f"[!] PHÁT HIỆN {len(new_articles)} BÀI BÁO THỜI SỰ MỚI TINH! ĐĂNG TOÀN BỘ NGAY LẬP TỨC...")
        need_daily_banner = (state.get("banner_date") != today)

        chunk_size = 5
        for idx, i in enumerate(range(0, len(new_articles), chunk_size)):
            batch = new_articles[i:i + chunk_size]
            embeds = [create_article_embed(a, now) for a in batch]

            # Trong cùng 1 ngày: KHÔNG gửi thêm banner (ảnh 2), chỉ gửi duy nhất card embed bài báo
            # Chỉ gửi banner chào ngày mới duy nhất 1 lần vào bài đầu tiên của ngày mới
            if need_daily_banner and idx == 0:
                content = (
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔴 **BẢN TIN THỜI SỰ NÓNG 24H • {thu.upper()}, {date_str}**\n"
                    f"⏰ *Bắt đầu ngày mới lúc: {time_str}* • <t:{ts}:R>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                state["banner_date"] = today
            else:
                content = ""

            send_discord(content, embeds)
            time.sleep(1)

        for a in new_articles:
            seen.add(a["link"])
        save_state(state)
    else:
        print(f"[*] Không có tin tức mới nào ({len(seen)} tin đã theo dõi). Giữ im lặng.")

if __name__ == "__main__":
    run_mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    main(run_mode)
