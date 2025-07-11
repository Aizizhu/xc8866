import requests
from bs4 import BeautifulSoup
import os
import re
import time
import random
from urllib.parse import urljoin
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://xc8866.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}
output_xlsx = 'output.xlsx'
base_img_dir = 'images'
crawled_file = 'crawled_posts.txt'
os.makedirs(base_img_dir, exist_ok=True)

excel_lock = threading.Lock()
crawled_lock = threading.Lock()

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name)

def load_crawled():
    if os.path.exists(crawled_file):
        with open(crawled_file, 'r', encoding='utf-8') as f:
            return set(line.strip().split('\t')[0] for line in f)
    return set()

def save_crawled(post_id, post_url):
    with crawled_lock:
        with open(crawled_file, 'a', encoding='utf-8') as f:
            f.write(post_id + '\t' + post_url + '\n')

def extract_info_from_table(soup):
    table = soup.find('table')
    price = qq = wechat = phone = ''
    if table:
        rows = table.find_all('tr')
        for row in rows:
            th = row.find('th')
            td = row.find('td')
            if not th or not td:
                continue
            label = th.get_text(strip=True)
            value = td.get_text(strip=True)
            if '价格' in label and not price:
                price = value
            elif 'QQ' in label and not qq:
                qq = value
            elif '微信' in label and not wechat:
                wechat = value
            elif '电话' in label or '手机' in label:
                phone = value
    return price, qq, wechat, phone

def parse_post(post_url):
    try:
        res = requests.get(post_url, headers=headers, timeout=(3,5))
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'html.parser')

        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.has_attr('content'):
            title = meta_desc['content'].strip()
        else:
            title_tag = soup.find('h4', class_='break-all font-weight-bold ')
            title = title_tag.get_text(strip=True) if title_tag else '标题未找到'

        price, qq, wechat, phone = extract_info_from_table(soup)

        imgs_with_alt = []
        valid_exts = ['.jpg', '.jpeg', '.png', '.webp']
        img_tags = soup.find_all('img', class_='img-fluid')

        for img in img_tags:
            src = img.get('src', '')
            if not src.startswith('http'):
                continue
            if any(x in src.lower() for x in ['zwzp.jpg', 'default.jpg', 'nopic.jpg']):
                continue
            if not (img.has_attr('data-toggle') and img.has_attr('data-target')):
                continue

            ext = os.path.splitext(src)[-1].lower()
            if ext and ext not in valid_exts:
                continue

            imgs_with_alt.append((img, ''))

        return title, price, qq, wechat, phone, imgs_with_alt
    except Exception as e:
        log(f'访问帖子失败: {post_url} 错误: {e}')
        return None, None, None, None, None, []

def download_images(imgs_with_alt, img_dir):
    image_files = []
    for i, (img, _) in enumerate(imgs_with_alt, start=1):
        img_url = img.get('src')
        if not img_url:
            continue
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = 'https://xc8866.com' + img_url

        ext = os.path.splitext(img_url)[-1].lower()
        if not re.match(r'\.(jpg|jpeg|png|gif|bmp|webp)$', ext):
            ext = '.jpg'

        img_name = f"{i}{ext}"
        img_path = os.path.join(img_dir, img_name)

        if os.path.exists(img_path):
            log(f'  跳过已存在图片: {img_name}')
            image_files.append(img_path)
            continue

        try:
            resp = requests.get(img_url, headers=headers, timeout=(3,5), stream=True)
            resp.raise_for_status()
            with open(img_path, 'wb') as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)
            image_files.append(img_path)
            log(f'  下载图片: {img_name}')
            time.sleep(random.uniform(0.2, 0.4))
        except Exception as e:
            log(f'图片下载失败: {img_url}, 错误: {e}')
            continue
    return image_files

def append_data_to_excel(rows_with_images, filename='output.xlsx'):
    if not rows_with_images:
        return

    max_imgs = max(len(row['images']) for row in rows_with_images)
    max_imgs = max(max_imgs, 3)

    headers = ['标题', '价格', 'QQ', '微信', '手机'] + \
              [f'图片{i}' for i in range(1, max_imgs + 1)] + \
              ['帖子链接']

    if os.path.exists(filename):
        wb = load_workbook(filename)
        ws = wb.active
        existing_headers = [cell.value for cell in ws[1]]
        if len(existing_headers) < len(headers):
            for col_idx in range(len(existing_headers)+1, len(headers)+1):
                ws.cell(row=1, column=col_idx, value=headers[col_idx-1])
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "爬取结果"
        ws.append(headers)

    for row_data in rows_with_images:
        row = row_data['row']
        imgs = row_data['images']

        text_cols = row[:5]
        link_col = row[-1]
        img_placeholders = [''] * max_imgs

        ws.append(text_cols + img_placeholders + [link_col])
        row_idx = ws.max_row

        for i, img_path in enumerate(imgs):
            if i >= max_imgs:
                break
            try:
                PILImage.open(img_path).verify()
                xl_img = XLImage(img_path)
                xl_img.width = 100
                xl_img.height = 100
                col_letter = chr(ord('F') + i)
                ws.add_image(xl_img, f"{col_letter}{row_idx}")
            except Exception as e:
                log(f"❌ 图片插入失败: {img_path}, 错误: {e}")

    wb.save(filename)
    log(f"✅ 写入 Excel：{filename}")

def get_page_threads(soup):
    threads = soup.find_all('li', class_='media thread tap')
    links = [t['data-href'] for t in threads if t.has_attr('data-href')]
    return links

def crawl_single_page(page_url, page_num, crawled_posts):
    log(f'📄 线程爬取第 {page_num} 页：{page_url}')
    page_data = []
    try:
        res = requests.get(page_url, headers=headers, timeout=(3,5))
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'html.parser')

        links = get_page_threads(soup)
        if not links:
            log(f"⚠️ 第 {page_num} 页没有获取到帖子链接，跳过")
            return []

        log(f'🔍 本页共发现 {len(links)} 条帖子链接')

        save_batch = []
        for idx, link in enumerate(links, 1):
            post_id = link.replace('.htm', '').replace('/', '_')
            if post_id in crawled_posts:
                log(f'跳过已爬取帖子 {post_id} ({link})')
                continue

            post_url = f'https://xc8866.com/{link}'
            log(f'➡️ 正在爬取帖子 {idx}/{len(links)}: {post_url}')
            title, price, qq, wechat, phone, imgs_with_alt = parse_post(post_url)
            if title is None:
                log(f"⚠️ 帖子解析失败，跳过: {post_url}")
                continue

            log(f'  标题: {title}')
            thread_img_dir = os.path.join(base_img_dir, sanitize_filename(post_id))
            os.makedirs(thread_img_dir, exist_ok=True)

            image_files = download_images(imgs_with_alt, thread_img_dir)
            log(f'  下载图片 {len(image_files)} 张')

            row = [title, price, qq, wechat, phone, '', '', '', post_url]
            save_batch.append({'row': row, 'images': image_files})

            save_crawled(post_id, post_url)
            crawled_posts.add(post_id)

            # 每爬10个帖子保存一次Excel
            if len(save_batch) >= 10:
                with excel_lock:
                    append_data_to_excel(save_batch, output_xlsx)
                log(f"✅ 已保存 {len(save_batch)} 条帖子数据")
                save_batch.clear()

            time.sleep(random.uniform(0.8, 1.5))

        # 保存剩余未满10条的帖子数据
        if save_batch:
            with excel_lock:
                append_data_to_excel(save_batch, output_xlsx)
            log(f"✅ 本页剩余 {len(save_batch)} 条帖子数据已保存")

        return []

    except Exception as e:
        log(f"爬取页面失败: {page_url} 错误: {e}")
        return []

def crawl_pages_multithread(start_url, total_pages, max_workers=6):
    match = re.search(r'forum-23-(\d+)\.htm', start_url)
    if not match:
        log("❌ 起始链接格式不正确")
        return
    start_page = int(match.group(1))
    target_page = start_page + total_pages - 1

    crawled_posts = load_crawled()

    page_urls = []
    for page_num in range(start_page, target_page + 1):
        url = re.sub(r'forum-23-\d+\.htm', f'forum-23-{page_num}.htm', start_url)
        page_urls.append(url)

    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {executor.submit(crawl_single_page, url, i, crawled_posts): i
               for i, url in enumerate(page_urls, start=start_page)}

    for future in as_completed(futures):
        page_num = futures[future]
        try:
            future.result()
            log(f"✅ 第 {page_num} 页爬取完成")
        except Exception as e:
            log(f"❌ 第 {page_num} 页爬取异常: {e}")

    executor.shutdown(wait=True)
    log("✅ 所有任务完成，程序退出")

def main():
    parser = argparse.ArgumentParser(description="爬虫起始页链接和总爬取页数")
    parser.add_argument('--start-url', type=str, required=True, help='起始页链接')
    parser.add_argument('--total-pages', type=int, required=True, help='总共需要爬多少页')
    parser.add_argument('--threads', type=int, default=6, help='最大线程数，默认6')
    args = parser.parse_args()

    crawl_pages_multithread(args.start_url, args.total_pages, args.threads)

if __name__ == '__main__':
    main()
