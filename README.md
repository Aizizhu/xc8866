# xc8866
从 xc8866 网站爬取公开交友信息，导出 Excel，并可进一步导入 SQLite 后用网页查询。

> 仅供学习与娱乐，请遵守目标网站规则与法律法规。

## 环境要求
- Python 3.10+
- 建议使用 `venv`

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
pip install -r requirements.txt
```

## 代理设置（可选）
如果网络环境需要代理，可在 `start.bat` 里按需配置：

```bat
set http_proxy=http://127.0.0.1:7890
set https_proxy=http://127.0.0.1:7890
set no_proxy=localhost,127.0.0.1,::1
```

## 爬虫用法（重写版）
重写后的 `main.py` 提供了更清晰的结构（配置对象 + 爬虫类），并支持可配置输出路径。

```bash
python main.py \
  --start-url "https://xc8866.com/forum-23-1.htm" \
  --total-pages 20 \
  --threads 6
```

### 参数说明
- `--start-url`：起始论坛页（必须是 `forum-23-页码.htm`）
- `--total-pages`：从起始页开始连续爬取多少页
- `--threads`：并发线程数（默认 6）
- `--output`：Excel 输出文件（默认 `output.xlsx`）
- `--images-dir`：图片下载目录（默认 `images`）
- `--state-file`：断点续传文件（默认 `crawled_posts.txt`）
- `--flush-batch`：累计多少条写入一次 Excel（默认 10）

### 断点续传
运行时会记录已爬帖子到 `crawled_posts.txt`。再次运行会自动跳过历史帖子，支持中断后续爬。

---

## Excel 导入数据库
爬虫完成后执行：

```bash
python import_excel.py
```

会将 `output.xlsx` 中的数据与图片导入到：
- `data.db`
- `static/images/...`

## 启动查询网页
```bash
python app.py
```
然后打开浏览器访问：
- `http://127.0.0.1:5000/`

支持关键词查询、价格区间筛选、价格排序与图片放大查看。
