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
from multiprocessing import Pool, Manager
import signal
import sys

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Referer': 'https://xc8866.com/',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}
output_xlsx = 'output.xlsx'
base_img_dir = 'images'
crawled_file = 'crawled_posts.txt'
os.makedirs(base_img_dir, exist_ok=True)

excel_headers = ['标题', '价格', 'QQ', '微信', '手机', '图片1', '图片2', '图片3', '帖子链接']

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]', '_', name)

def load_crawled():
    if os.path.exists(crawled_file):
        with open(crawled_file, 'r', encoding='utf-8') as f:
            return [line.strip().split('\t')[0] for line in f]
    return []

def save_crawled(post_id, post_url):
    with open(crawled_file, 'a', encoding='utf-8') as f:
        f.write(post_id + '\t' + post_url + '\n')

def extract_info_from_table(soup):
    # 你的表格解析逻辑
    price = qq = wechat = phone = ''
    table = soup.find('table')
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
        res = requests.get(post_url, headers=headers, timeout=15)
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
        img_tags = soup.find_all('img', class_='img-fluid')
        for img_tag in img_tags:
            src = img_tag.get('src', '')
            # 排除占位图
            if any(x in src for x in ['file/zwzp.jpg', 'default.jpg', 'nopic.jpg']):
                continue
            # 要求有 data-toggle 和 data-target 属性
            if not (img_tag.has_attr('data-toggle') and img_tag.has_attr('data-target')):
                continue
            imgs_with_alt.append(img_tag)

        return title, price, qq, wechat, phone, imgs_with_alt
    except Exception as e:
        log(f'访问帖子失败: {post_url} 错误: {e}')
        return None, None, None, None, None, []

def download_images(img_tags, img_dir):
    image_files = []
    for i, img in enumerate(img_tags):
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

        img_name = f'{i}_image{ext}'
        img_path = os.path.join(img_dir, img_name)

        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            log(f'图片已存在，跳过下载: {img_name}')
            image_files.append(img_path)
            continue

        try:
            resp = requests.get(img_url, headers=headers, timeout=15, stream=True)
            resp.raise_for_status()
            with open(img_path, 'wb') as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)
            image_files.append(img_path)
            log(f'  下载图片 {i+1}: {img_name}')
            time.sleep(random.uniform(0.2, 0.4))
        except Exception as e:
            log(f'图片下载失败: {img_url}, 错误: {e}')
            continue
    return image_files

def append_data_to_excel(rows_with_images, filename='output.xlsx'):
    if os.path.exists(filename):
        wb = load_workbook(filename)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "爬取结果"
        ws.append(excel_headers)

    for row_data in rows_with_images:
        row = row_data['row']
        imgs = row_data['images']
        ws.append(row)
        row_idx = ws.max_row
        for col_offset, img_path in enumerate(imgs[:3]):
            try:
                PILImage.open(img_path).verify()
                xl_img = XLImage(img_path)
                xl_img.width = 100
                xl_img.height = 100
                col_letter = chr(ord('F') + col_offset)
                ws.add_image(xl_img, f"{col_letter}{row_idx}")
            except Exception as e:
                log(f"❌ 图片插入失败: {img_path}, 错误: {e}")

    wb.save(filename)
    log(f"✅ 写入 Excel：{filename}")

def get_next_page_url(soup, current_url):
    a = soup.find('a', class_='page-link', string='▶')
    if a and a.has_attr('href'):
        href = a['href']
        full_url = urljoin(current_url, href)
        return full_url
    return None

def get_page_threads(soup):
    threads = soup.find_all('li', class_='media thread tap')
    links = [t['data-href'] for t in threads if t.has_attr('data-href')]
    return links

def crawl_page(args):
    page_num, start_url, crawled_posts_list = args
    try:
        page_url = re.sub(r'forum-23-\d+\.htm', f'forum-23-{page_num}.htm', start_url)
        log(f'开始爬取第 {page_num} 页：{page_url}')
        res = requests.get(page_url, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'html.parser')

        links = get_page_threads(soup)
        if not links:
            log(f"⚠️ 第 {page_num} 页没有获取到帖子链接")
            return []

        page_data = []
        # 使用本地set来提高查重效率
        crawled_posts_set = set(crawled_posts_list)

        for idx, link in enumerate(links, 1):
            post_id = link.replace('.htm', '').replace('/', '_')
            if post_id in crawled_posts_set:
                log(f'跳过已爬取帖子 {post_id} ({link})')
                continue

            post_url = f'https://xc8866.com/{link}'
            log(f'➡️ 正在爬取帖子 {idx}/{len(links)}: {post_url}')
            title, price, qq, wechat, phone, imgs_with_alt = parse_post(post_url)
            if title is None:
                log(f"⚠️ 帖子解析失败，跳过: {post_url}")
                continue

            thread_img_dir = os.path.join(base_img_dir, sanitize_filename(post_id))
            os.makedirs(thread_img_dir, exist_ok=True)

            image_files = download_images(imgs_with_alt, thread_img_dir)
            log(f'  下载图片 {len(image_files)} 张')

            row = [title, price, qq, wechat, phone, '', '', '', post_url]
            page_data.append({'row': row, 'images': image_files})

            # 更新共享爬取列表
            crawled_posts_list.append(post_id)
            crawled_posts_set.add(post_id)
            save_crawled(post_id, post_url)

            time.sleep(random.uniform(0.8, 1.5))

        return page_data

    except Exception as e:
        log(f"爬取页面失败: {page_url} 错误: {e}")
        return []

def signal_handler(sig, frame):
    log('⏸️ 检测到手动终止 (Ctrl+C)，准备退出...')
    sys.exit(0)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="多进程爬虫")
    parser.add_argument('--start-url', type=str, required=True, help='起始页链接，如 https://xc8866.com/forum-23-1.htm?tagids=151_0_0_0')
    parser.add_argument('--total-pages', type=int, required=True, help='需要爬取多少页')
    parser.add_argument('--processes', type=int, default=4, help='进程数')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_handler)

    manager = Manager()
    crawled_posts_list = manager.list(load_crawled())

    pool = Pool(processes=args.processes)
    task_args = [(page_num, args.start_url, crawled_posts_list) for page_num in range(1, args.total_pages + 1)]

    all_results = []
    try:
        for result in pool.imap_unordered(crawl_page, task_args):
            if result:
                append_data_to_excel(result, output_xlsx)
                all_results.extend(result)
    except KeyboardInterrupt:
        log("⏸️ 主进程捕获到Ctrl+C，准备退出...")

    pool.close()
    pool.join()

    log(f"✅ 爬虫结束，共爬取帖子数：{len(crawled_posts_list)}")

if __name__ == '__main__':
    main()
