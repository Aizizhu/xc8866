import argparse
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://xc8866.com/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


@dataclass(slots=True)
class CrawlConfig:
    start_url: str
    total_pages: int
    threads: int = 6
    output_xlsx: str = "output.xlsx"
    image_dir: str = "images"
    crawled_file: str = "crawled_posts.txt"
    min_delay: float = 0.8
    max_delay: float = 1.5
    request_timeout: tuple[int, int] = (3, 6)
    flush_batch: int = 10


@dataclass(slots=True)
class PostRecord:
    title: str
    price: str
    qq: str
    wechat: str
    phone: str
    post_url: str
    image_files: list[str]


class XC8866Crawler:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        self.output_path = Path(config.output_xlsx)
        self.image_root = Path(config.image_dir)
        self.crawled_path = Path(config.crawled_file)

        self.image_root.mkdir(parents=True, exist_ok=True)

        self.excel_lock = threading.Lock()
        self.crawled_lock = threading.Lock()

    @staticmethod
    def log(msg: str) -> None:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    @staticmethod
    def sanitize_filename(name: str) -> str:
        return re.sub(r"[\\/:*?\"<>|]", "_", name)

    def load_crawled(self) -> set[str]:
        if not self.crawled_path.exists():
            return set()

        crawled: set[str] = set()
        with self.crawled_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                crawled.add(line.split("\t")[0])
        return crawled

    def save_crawled(self, post_id: str, post_url: str) -> None:
        with self.crawled_lock:
            with self.crawled_path.open("a", encoding="utf-8") as file:
                file.write(f"{post_id}\t{post_url}\n")

    @staticmethod
    def normalize_url(url: str, base_url: str) -> str:
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return urljoin(base_url, url)
        return url

    @staticmethod
    def extract_info_from_table(soup: BeautifulSoup) -> tuple[str, str, str, str]:
        table = soup.find("table")
        price = qq = wechat = phone = ""
        if not table:
            return price, qq, wechat, phone

        for row in table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue

            label = th.get_text(strip=True)
            value = td.get_text(strip=True)
            if "价格" in label and not price:
                price = value
            elif "QQ" in label and not qq:
                qq = value
            elif "微信" in label and not wechat:
                wechat = value
            elif "电话" in label or "手机" in label:
                phone = value

        return price, qq, wechat, phone

    def extract_images(self, soup: BeautifulSoup, page_url: str) -> list[str]:
        image_urls: list[str] = []
        valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

        for img in soup.find_all("img", class_="img-fluid"):
            src = img.get("src", "").strip()
            if not src:
                continue

            src_lower = src.lower()
            if any(x in src_lower for x in ("zwzp.jpg", "default.jpg", "nopic.jpg")):
                continue

            if not (img.has_attr("data-toggle") and img.has_attr("data-target")):
                continue

            img_url = self.normalize_url(src, page_url)
            ext = os.path.splitext(urlparse(img_url).path)[-1].lower()
            if ext and ext not in valid_exts:
                continue

            image_urls.append(img_url)

        return image_urls

    def parse_post(self, post_url: str) -> PostRecord | None:
        try:
            response = self.session.get(post_url, timeout=self.config.request_timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                title = meta_desc["content"].strip()
            else:
                title_tag = soup.find("h4", class_="break-all font-weight-bold ")
                title = title_tag.get_text(strip=True) if title_tag else "标题未找到"

            price, qq, wechat, phone = self.extract_info_from_table(soup)
            image_urls = self.extract_images(soup, post_url)

            return PostRecord(
                title=title,
                price=price,
                qq=qq,
                wechat=wechat,
                phone=phone,
                post_url=post_url,
                image_files=self.download_images(image_urls, self.build_post_image_dir(post_url)),
            )
        except Exception as exc:  # noqa: BLE001
            self.log(f"访问帖子失败: {post_url} 错误: {exc}")
            return None

    def build_post_image_dir(self, post_url: str) -> Path:
        post_id = post_url.rstrip("/").split("/")[-1].replace(".htm", "")
        safe_post_id = self.sanitize_filename(post_id)
        image_dir = self.image_root / safe_post_id
        image_dir.mkdir(parents=True, exist_ok=True)
        return image_dir

    def download_images(self, image_urls: Iterable[str], image_dir: Path) -> list[str]:
        downloaded_files: list[str] = []

        for index, img_url in enumerate(image_urls, start=1):
            ext = os.path.splitext(urlparse(img_url).path)[-1].lower()
            if not re.match(r"\.(jpg|jpeg|png|gif|bmp|webp)$", ext):
                ext = ".jpg"

            image_name = f"{index}{ext}"
            image_path = image_dir / image_name

            if image_path.exists():
                downloaded_files.append(str(image_path))
                self.log(f"  跳过已存在图片: {image_name}")
                continue

            try:
                response = self.session.get(
                    img_url,
                    timeout=self.config.request_timeout,
                    stream=True,
                )
                response.raise_for_status()
                with image_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            file.write(chunk)
                downloaded_files.append(str(image_path))
                self.log(f"  下载图片: {image_name}")
                time.sleep(random.uniform(0.2, 0.4))
            except Exception as exc:  # noqa: BLE001
                self.log(f"图片下载失败: {img_url}, 错误: {exc}")

        return downloaded_files

    def append_records_to_excel(self, records: list[PostRecord]) -> None:
        if not records:
            return

        max_imgs = max(3, max(len(record.image_files) for record in records))
        headers = ["标题", "价格", "QQ", "微信", "手机"] + [f"图片{i}" for i in range(1, max_imgs + 1)] + ["帖子链接"]

        if self.output_path.exists():
            workbook = load_workbook(self.output_path)
            worksheet = workbook.active
            existing_headers = [cell.value for cell in worksheet[1]]
            if len(existing_headers) < len(headers):
                for col_idx in range(len(existing_headers) + 1, len(headers) + 1):
                    worksheet.cell(row=1, column=col_idx, value=headers[col_idx - 1])
        else:
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "爬取结果"
            worksheet.append(headers)

        for record in records:
            row_values = [record.title, record.price, record.qq, record.wechat, record.phone]
            worksheet.append(row_values + [""] * max_imgs + [record.post_url])
            row_idx = worksheet.max_row

            for i, image_path in enumerate(record.image_files[:max_imgs]):
                try:
                    PILImage.open(image_path).verify()
                    excel_image = XLImage(image_path)
                    excel_image.width = 100
                    excel_image.height = 100
                    col_letter = chr(ord("F") + i)
                    worksheet.add_image(excel_image, f"{col_letter}{row_idx}")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"❌ 图片插入失败: {image_path}, 错误: {exc}")

        workbook.save(self.output_path)
        self.log(f"✅ 写入 Excel：{self.output_path}")

    @staticmethod
    def get_page_threads(soup: BeautifulSoup) -> list[str]:
        threads = soup.find_all("li", class_="media thread tap")
        return [t["data-href"] for t in threads if t.has_attr("data-href")]

    def crawl_single_page(self, page_url: str, page_num: int, crawled_posts: set[str]) -> None:
        self.log(f"📄 线程爬取第 {page_num} 页：{page_url}")
        batch: list[PostRecord] = []

        try:
            response = self.session.get(page_url, timeout=self.config.request_timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            links = self.get_page_threads(soup)
            if not links:
                self.log(f"⚠️ 第 {page_num} 页没有获取到帖子链接，跳过")
                return

            self.log(f"🔍 本页共发现 {len(links)} 条帖子链接")
            for idx, link in enumerate(links, start=1):
                post_id = link.replace(".htm", "").replace("/", "_")
                if post_id in crawled_posts:
                    self.log(f"跳过已爬取帖子 {post_id} ({link})")
                    continue

                post_url = urljoin("https://xc8866.com/", link)
                self.log(f"➡️ 正在爬取帖子 {idx}/{len(links)}: {post_url}")
                record = self.parse_post(post_url)
                if not record:
                    self.log(f"⚠️ 帖子解析失败，跳过: {post_url}")
                    continue

                self.log(f"  标题: {record.title}")
                self.log(f"  下载图片 {len(record.image_files)} 张")

                batch.append(record)
                self.save_crawled(post_id, post_url)
                crawled_posts.add(post_id)

                if len(batch) >= self.config.flush_batch:
                    with self.excel_lock:
                        self.append_records_to_excel(batch)
                    self.log(f"✅ 已保存 {len(batch)} 条帖子数据")
                    batch.clear()

                time.sleep(random.uniform(self.config.min_delay, self.config.max_delay))

            if batch:
                with self.excel_lock:
                    self.append_records_to_excel(batch)
                self.log(f"✅ 本页剩余 {len(batch)} 条帖子数据已保存")

        except Exception as exc:  # noqa: BLE001
            self.log(f"爬取页面失败: {page_url} 错误: {exc}")

    @staticmethod
    def build_page_urls(start_url: str, total_pages: int) -> list[tuple[int, str]]:
        match = re.search(r"forum-23-(\d+)\.htm", start_url)
        if not match:
            raise ValueError("起始链接格式不正确，应包含 forum-23-页码.htm")

        start_page = int(match.group(1))
        urls: list[tuple[int, str]] = []
        for page_num in range(start_page, start_page + total_pages):
            url = re.sub(r"forum-23-\d+\.htm", f"forum-23-{page_num}.htm", start_url)
            urls.append((page_num, url))
        return urls

    def crawl(self) -> None:
        crawled_posts = self.load_crawled()
        page_urls = self.build_page_urls(self.config.start_url, self.config.total_pages)

        with ThreadPoolExecutor(max_workers=self.config.threads) as executor:
            future_map = {
                executor.submit(self.crawl_single_page, url, page_num, crawled_posts): page_num
                for page_num, url in page_urls
            }
            for future in as_completed(future_map):
                page_num = future_map[future]
                try:
                    future.result()
                    self.log(f"✅ 第 {page_num} 页爬取完成")
                except Exception as exc:  # noqa: BLE001
                    self.log(f"❌ 第 {page_num} 页爬取异常: {exc}")

        self.log("✅ 所有任务完成，程序退出")


def parse_args() -> CrawlConfig:
    parser = argparse.ArgumentParser(description="xc8866 爬虫：抓取帖子、图片并写入 Excel")
    parser.add_argument("--start-url", type=str, required=True, help="起始页链接")
    parser.add_argument("--total-pages", type=int, required=True, help="总共需要爬取多少页")
    parser.add_argument("--threads", type=int, default=6, help="最大线程数，默认 6")
    parser.add_argument("--output", type=str, default="output.xlsx", help="Excel 输出文件，默认 output.xlsx")
    parser.add_argument("--images-dir", type=str, default="images", help="图片输出目录，默认 images")
    parser.add_argument("--state-file", type=str, default="crawled_posts.txt", help="断点状态文件，默认 crawled_posts.txt")
    parser.add_argument("--flush-batch", type=int, default=10, help="累计多少条写入一次 Excel，默认 10")

    args = parser.parse_args()

    return CrawlConfig(
        start_url=args.start_url,
        total_pages=args.total_pages,
        threads=max(1, args.threads),
        output_xlsx=args.output,
        image_dir=args.images_dir,
        crawled_file=args.state_file,
        flush_batch=max(1, args.flush_batch),
    )


def main() -> None:
    config = parse_args()
    crawler = XC8866Crawler(config)
    crawler.crawl()


if __name__ == "__main__":
    main()
